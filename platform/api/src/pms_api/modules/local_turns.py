"""Record turns a laptop executed on its own local model.

The platform is not on the data path for a local model, so it cannot observe these turns and
cannot attest them: what arrives here is a client-reported summary. It is accepted only for a
profile revision whose published LLM really is local, it carries no prompt, transcript or
answer, and it is append-only — there is no result to recover and nothing to resubmit.
"""

from datetime import timedelta
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Query
from pydantic import AwareDatetime, Field, model_validator
from sqlalchemy import select
from training_contracts import fingerprint as report_fingerprint
from training_contracts.conversation.context import TurnContextRef
from training_contracts.languages import LanguageTag

from pms_api.core.common import now, require, required
from pms_api.core.dependencies import Session
from pms_api.database.models import (
    LLMConnection,
    LocalTurn,
    Organization,
    PatientPracticeSelection,
    PlatformSettings,
    ProfileRevision,
)
from pms_api.modules.common import audit, commit
from pms_api.modules.configuration import tighter
from pms_api.modules.llm import scope
from pms_api.modules.runtime_model_store import runtime_model
from pms_api.modules.schemas import Input
from pms_api.security.access import Actor
from pms_api.security.practice_access import execution_access as organization_access
from pms_api.security.practice_access import is_owner, owner_filter, owner_values

router = APIRouter(tags=["LLM"])
BASE = "/organizations/{organization_id}/llm/local-turns"
Limit = Annotated[int, Query(ge=1, le=200)]
# Every authored outcome the shared pipeline can produce, plus a turn with no case selected.
SOURCES = Literal[
    "patient_conversation",
    "patient_voice",
    "patient_deflection",
    "scripted_case",
    "case_backchannel",
    "case_command_ack",
    "case_boundary",
    "case_clarification",
    "routing_invalid",
    "plain_completion",
]
# Outcomes spoken by the model rather than read from the case. Both spend the spoken call.
GENERATED = ("patient_voice", "patient_deflection")


class LocalTurnEvent(Input):
    turn_key: UUID
    department_id: UUID | None = None
    profile_revision_id: UUID
    configuration_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    connection_id: UUID
    connection_revision: int = Field(ge=1, le=2147483646, strict=True)
    practice_id: UUID | None = None
    practice_revision: int | None = Field(default=None, ge=1, le=2147483646, strict=True)
    practice_snapshot_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    language: LanguageTag
    context_ref: TurnContextRef | None = None
    answer_source: SOURCES
    policy_version: Literal["patient-conversation-v1"] | None = None
    routing_status: Literal["matched", "backchannel", "command", "boundary", "unknown", "invalid"] | None = (
        None
    )
    kind: Literal["topic", "backchannel", "command", "boundary", "unknown"] | None = None
    topics: list[str] = Field(default_factory=list, max_length=3)
    # Draft routing, optional spoken wording and independent evidence review.
    provider_calls: int = Field(ge=1, le=3, strict=True)
    finish_reason: Literal["stop", "length"]
    prompt_tokens: int | None = Field(default=None, ge=0, le=1000000, strict=True)
    completion_tokens: int | None = Field(default=None, ge=0, le=1000000, strict=True)
    first_token_ms: int | None = Field(default=None, ge=0, le=600000, strict=True)
    total_ms: int = Field(ge=0, le=600000, strict=True)
    occurred_at: AwareDatetime

    @model_validator(mode="after")
    def consistent(self):
        practice = self.practice_id is not None
        if practice != (self.practice_revision is not None) or practice != (
            self.practice_snapshot_hash is not None
        ):
            raise ValueError("Practice identity, revision and snapshot must be supplied together")
        if self.answer_source == "patient_conversation":
            if (
                not practice
                or self.policy_version != "patient-conversation-v1"
                or self.routing_status is not None
                or self.kind is not None
                or self.topics
                or self.provider_calls != 1
                or self.finish_reason != "stop"
            ):
                raise ValueError(
                    "A patient conversation requires a case, policy, one complete call and no routing"
                )
            return self
        if self.policy_version is not None:
            raise ValueError("Only a patient conversation reports this policy version")
        if practice != (self.routing_status is not None) or practice != (self.kind is not None):
            raise ValueError("A routed turn reports its routing outcome; a plain turn reports none")
        if practice == (self.answer_source == "plain_completion"):
            raise ValueError("Only a turn without a patient case is a plain completion")
        if not practice and (self.topics or self.provider_calls != 1):
            raise ValueError("A plain completion routes no topics and makes one call")
        if any(not 1 <= len(topic) <= 80 or not topic.replace("_", "").isalnum() for topic in self.topics):
            raise ValueError("Invalid routed topic id")
        if len(set(self.topics)) != len(self.topics):
            raise ValueError("Routed topics must be distinct")
        routed = bool(self.topics)
        # Authored facts are selected exactly when routing matched a topic, and only such a turn
        # answers from the case; every other outcome speaks an authored line for its kind.
        if practice and (
            routed != (self.routing_status == "matched")
            or routed != (self.kind == "topic")
            or routed != (self.answer_source in ("patient_voice", "scripted_case"))
        ):
            raise ValueError("A routed topic, a matched outcome and a case answer go together")
        # Generated wording always spends the routing call and the spoken call, and may also
        # have spent a repaired routing attempt between them.
        if self.answer_source in GENERATED and self.provider_calls < 2:
            raise ValueError("Generated wording spends the routing call and the spoken call")
        # A deflection is the one generated outcome that speaks no fact: it answers a question
        # no topic covers. The reverse is deliberately not asserted, because a repaired routing
        # attempt and a rejected deflection are both a second call on an unroutable turn.
        if self.answer_source == "patient_deflection" and not (not routed and self.kind == "unknown"):
            raise ValueError("A generated deflection answers an unroutable question with no topic")
        # Evidence review may replace a generated proposal with a stock reply. All three
        # completions were still spent even when the final result is an authored known kind.
        return self


def view(row):
    return {
        "id": str(row.id),
        "turn_key": str(row.turn_key),
        "occurred_at": row.occurred_at.isoformat(),
        "language": row.language,
        "answer_source": row.answer_source,
        "policy_version": row.policy_version,
        "context_ref": row.context_ref,
        "routing_status": row.routing_status,
        "kind": row.kind,
        "topics": row.topics,
        "provider_calls": row.provider_calls,
        "finish_reason": row.finish_reason,
        "prompt_tokens": row.prompt_tokens,
        "completion_tokens": row.completion_tokens,
        "first_token_ms": row.first_token_ms,
        "total_ms": row.total_ms,
        "practice_id": str(row.practice_id) if row.practice_id else None,
        "practice_revision": row.practice_revision,
        "connection_id": str(row.connection_id),
        "connection_revision": row.connection_revision,
        "profile_revision_id": str(row.profile_revision_id),
    }


@router.post(BASE)
async def record(organization_id: UUID, body: LocalTurnEvent, actor: Actor, session: Session):
    # The same scope rule platform-executed turns use: an active department in this organization.
    _, department = await scope(session, actor, organization_id, body.department_id)
    if actor.device and body.department_id is None:
        body = body.model_copy(update={"department_id": department})
    existing = await session.scalar(
        select(LocalTurn).where(
            LocalTurn.organization_id == organization_id, LocalTurn.turn_key == body.turn_key
        )
    )
    if existing:
        # Fire-and-forget senders retry; a recorded turn is never rewritten.
        require(is_owner(existing, actor), "idempotency_conflict", "Turn key already used", 409)
        require(
            existing.request_fingerprint is None
            or existing.request_fingerprint == report_fingerprint(body.model_dump(mode="json")),
            "idempotency_conflict",
            "Turn key already used with different content",
            409,
        )
        return view(existing)
    from pms_api.modules.patient_conversations import validate_report_context

    await validate_report_context(session, actor, organization_id, body)
    revision = required(await session.get(ProfileRevision, body.profile_revision_id))
    require(revision.organization_id == organization_id, "not_found", "Profile revision not found", 404)
    require(
        revision.llm_connection_id == body.connection_id,
        "invalid_request",
        "That model is not the one this profile revision published",
    )
    conn = required(await runtime_model(session, body.connection_id, LLMConnection))
    require(conn.organization_id in {None, organization_id}, "not_found", "Connection not found", 404)
    if body.answer_source == "patient_conversation":
        practice = required(await session.get(PatientPracticeSelection, body.practice_id))
        require(
            practice.organization_id == organization_id and is_owner(practice, actor),
            "not_found",
            "Patient setup not found",
            404,
        )
        require(
            body.practice_revision is not None
            and body.practice_revision <= practice.revision
            and body.connection_revision <= conn.revision,
            "invalid_request",
            "Unknown setup or connection revision",
            409,
        )
    require(
        conn.provider == "local_llama_cpp",
        "llm_local_execution_required",
        "Cloud turns are recorded by the platform itself",
        409,
    )
    organization = required(await session.get(Organization, organization_id, populate_existing=True))
    platform = required(await session.get(PlatformSettings, 1, populate_existing=True))
    limits = tighter(platform.policy_limits, organization.policy_settings)
    timestamp = now()
    require(
        timestamp - timedelta(minutes=55) <= body.occurred_at <= timestamp + timedelta(minutes=5),
        "invalid_request",
        "Report a local turn when it happens",
    )
    # The reporting laptop's clock is not authoritative. A small forward skew is recorded as the
    # arrival time rather than discarding the only record a caller-executed turn will ever have.
    occurred_at = min(body.occurred_at, timestamp)
    row = LocalTurn(
        id=uuid4(),
        organization_id=organization_id,
        department_id=department,
        **owner_values(actor),
        created_at=timestamp,
        expires_at=timestamp + timedelta(days=min(limits["result_retention_days"], 90)),
        occurred_at=occurred_at,
        request_fingerprint=report_fingerprint(body.model_dump(mode="json")),
        context_ref=body.context_ref.model_dump(mode="json") if body.context_ref else None,
        **body.model_dump(exclude={"department_id", "occurred_at", "context_ref"}),
    )
    session.add(row)
    await audit(
        session,
        actor,
        "llm.local_turn.recorded",
        "local_turn",
        row.id,
        organization_id,
        {"answer_source": row.answer_source, "provider_calls": row.provider_calls},
        department_id=department,
    )
    await commit(session, row)
    return view(row)


@router.get(BASE)
async def list_turns(organization_id: UUID, actor: Actor, session: Session, limit: Limit = 50):
    access = await organization_access(session, actor, organization_id, "org.results.read")
    query = select(LocalTurn).where(LocalTurn.organization_id == organization_id)
    if access.role != "org_admin":
        query = query.where(owner_filter(LocalTurn, actor))
    if access.department_id:
        query = query.where(LocalTurn.department_id == access.department_id)
    rows = (
        await session.scalars(
            query.where(LocalTurn.expires_at > now()).order_by(LocalTurn.occurred_at.desc()).limit(limit)
        )
    ).all()
    return {"items": [view(row) for row in rows]}
