"""Archive client-reported exchanges. This module never contacts a model."""

from datetime import timedelta
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, Request
from pydantic import AwareDatetime, Field, model_validator
from sqlalchemy import func, select, tuple_
from training_contracts.conversation.context import TurnContextRef
from training_contracts.languages import LanguageTag

from pms_api.core.common import canonical, digest, now, require, required
from pms_api.core.dependencies import Session
from pms_api.database.models import (
    Department,
    LLMConnection,
    LocalConversationTurn,
    Organization,
    PatientPracticeSelection,
    PlatformSettings,
    ProfileRevision,
)
from pms_api.modules.common import audit, commit
from pms_api.modules.configuration import tighter
from pms_api.modules.llm import scope
from pms_api.modules.local_turns import SOURCES
from pms_api.modules.runtime_model_store import runtime_model
from pms_api.modules.schemas import Input
from pms_api.security.access import Actor
from pms_api.security.practice_access import execution_access as organization_access
from pms_api.security.practice_access import is_owner, owner_filter, owner_values

router = APIRouter(tags=["Local conversation history"])
BASE = "/organizations/{organization_id}/llm/local-conversation-turns"


class Timings(Input):
    asr_finalize_ms: int = Field(0, ge=0, le=3600000)
    total_ms: int = Field(0, ge=0, le=3600000)
    first_token_ms: int | None = Field(None, ge=0, le=3600000)


class ConversationEvent(Input):
    turn_key: UUID
    conversation_id: UUID
    sequence: int = Field(ge=1, le=2147483647, strict=True)
    department_id: UUID | None = None
    profile_revision_id: UUID
    configuration_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    connection_id: UUID
    connection_revision: int = Field(ge=1, le=2147483646, strict=True)
    model: str = Field(min_length=1, max_length=200)
    practice_id: UUID | None = None
    practice_revision: int | None = Field(None, ge=1, le=2147483646)
    practice_snapshot_hash: str | None = Field(None, pattern=r"^[a-f0-9]{64}$")
    language: LanguageTag
    context_ref: TurnContextRef | None = None
    input_source: Literal["text", "speech"]
    audio_mode: Literal["none", "local", "cloud"]
    input_text: str = Field(min_length=1, max_length=8000)
    response_text: str | None = Field(None, min_length=1, max_length=32000)
    outcome: Literal["completed", "failed", "cancelled"]
    answer_source: SOURCES | None = None
    policy_version: Literal["patient-conversation-v1"] | None = None
    finish_reason: Literal["stop", "length"] | None = None
    occurred_at: AwareDatetime
    completed_at: AwareDatetime
    timings: Timings = Field(default_factory=Timings)

    @model_validator(mode="after")
    def consistent(self):
        if self.context_ref and self.context_ref.conversation_id != self.conversation_id:
            raise ValueError("Conversation reference and archive identity disagree")
        for value in (self.input_text, self.response_text, self.model):
            if value is not None:
                value.encode("utf-8")
                if "\x00" in value:
                    raise ValueError("Invalid text")
        if not self.input_text.strip() or "\x00" in self.input_text:
            raise ValueError("Invalid input text")
        if self.response_text is not None and (
            not self.response_text.strip()
            or "\x00" in self.response_text
            or len(self.response_text.encode("utf-8")) > 32000
        ):
            raise ValueError("Invalid response text")
        complete = self.outcome == "completed"
        if self.answer_source == "patient_conversation":
            if (
                not self.practice_id
                or self.policy_version != "patient-conversation-v1"
                or self.finish_reason != "stop"
            ):
                raise ValueError("Patient conversation requires a case, policy and completed reply")
        elif self.policy_version is not None:
            raise ValueError("Only patient conversation reports this policy")
        if any(
            complete != (value is not None)
            for value in (self.response_text, self.answer_source, self.finish_reason)
        ):
            raise ValueError("Completed exchanges require a delivered answer and outcome")
        if (self.input_source == "text") != (self.audio_mode == "none"):
            raise ValueError("Input source and speech mode disagree")
        if self.completed_at < self.occurred_at:
            raise ValueError("Invalid turn times")
        if any(
            (self.practice_id is None) != (value is None)
            for value in (self.practice_revision, self.practice_snapshot_hash)
        ):
            raise ValueError("Supply all patient context identifiers together")
        return self


def view(row):
    return {
        **row.document,
        "id": str(row.id),
        "turn_key": str(row.turn_key),
        "input_text": row.input_text,
        "response_text": row.response_text,
        "created_at": row.created_at.isoformat(),
        "expires_at": row.expires_at.isoformat(),
        "provenance": "client_reported",
        "save_status": "saved_to_pms",
    }


@router.get(BASE + "/identity")
async def identity(organization_id: UUID, actor: Actor, session: Session):
    access = await organization_access(session, actor, organization_id, "org.results.read")
    return {
        "issuer": "urn:pms:device" if actor.device else (actor.claims or {}).get("iss"),
        "subject": str(actor.id) if actor.device else (actor.claims or {}).get("sub"),
        "user_id": str(actor.id) if actor.user else None,
        "device_id": str(actor.id) if actor.device else None,
        "organization_id": str(organization_id),
        "department_id": str(access.department_id) if access.department_id else None,
    }


@router.post(BASE)
async def record(
    organization_id: UUID, body: ConversationEvent, request: Request, actor: Actor, session: Session
):
    settings = request.app.state.settings
    require(settings.local_history_enabled, "history_disabled", "Conversation archival is disabled", 503)
    # Serialize tenant capacity and uniqueness checks, then recheck current scope.
    await organization_access(session, actor, organization_id, "org.processing.execute")
    await session.get(Organization, organization_id, with_for_update=True, populate_existing=True)
    _, department = await scope(
        session, actor, organization_id, body.department_id, resolve_default=actor.device is not None
    )
    if actor.device and body.department_id is None:
        body = body.model_copy(update={"department_id": department})
    document = body.model_dump(mode="json")
    # Preserve fingerprints of historical outbox payloads that predate this optional field.
    if body.policy_version is None:
        document.pop("policy_version")
    if body.context_ref is None:
        document.pop("context_ref")
    document["department_id"] = str(department) if department else None
    fingerprint = digest(document)
    existing = await session.scalar(
        select(LocalConversationTurn).where(
            LocalConversationTurn.organization_id == organization_id,
            LocalConversationTurn.turn_key == body.turn_key,
        )
    )
    if existing:
        require(
            is_owner(existing, actor)
            and existing.department_id == department
            and existing.fingerprint == fingerprint,
            "idempotency_conflict",
            "Turn key already used with different content",
            409,
        )
        require(existing.expires_at > now(), "history_expired", "History record has expired", 410)
        return view(existing)
    from pms_api.modules.patient_conversations import validate_report_context

    await validate_report_context(session, actor, organization_id, body)
    revision = required(await session.get(ProfileRevision, body.profile_revision_id))
    require(
        revision.organization_id == organization_id and revision.llm_connection_id == body.connection_id,
        "not_found",
        "Configuration not found",
        404,
    )
    conn = required(await runtime_model(session, body.connection_id, LLMConnection))
    require(
        conn.organization_id in {None, organization_id} and conn.provider == "local_llama_cpp",
        "invalid_local_configuration",
        "Expected a local model configuration",
        409,
    )
    require(
        body.connection_revision <= conn.revision,
        "invalid_local_configuration",
        "Unknown connection revision",
        409,
    )
    if body.practice_id:
        practice = required(await session.get(PatientPracticeSelection, body.practice_id))
        require(
            practice.organization_id == organization_id and is_owner(practice, actor),
            "not_found",
            "Patient setup not found",
            404,
        )
        require(
            body.practice_revision is not None and body.practice_revision <= practice.revision,
            "invalid_request",
            "Unknown setup revision",
            409,
        )
    timestamp = now()
    require(
        timestamp - timedelta(hours=settings.local_history_upload_hours)
        <= body.occurred_at
        <= body.completed_at
        <= timestamp + timedelta(minutes=5),
        "history_upload_expired",
        "Turn is outside the archival upload window",
        410,
    )
    platform = required(await session.get(PlatformSettings, 1))
    organization = required(await session.get(Organization, organization_id))
    limits = tighter(platform.policy_limits, organization.policy_settings)
    size = len(canonical(document).encode("utf-8"))
    require(size <= 131072, "payload_too_large", "History record is too large", 413)
    count, used = (
        await session.execute(
            select(func.count(), func.coalesce(func.sum(LocalConversationTurn.byte_size), 0)).where(
                LocalConversationTurn.organization_id == organization_id
            )
        )
    ).one()
    require(
        count < settings.local_history_max_records and used + size <= settings.local_history_max_bytes,
        "history_storage_limit",
        "Conversation archive capacity reached",
        429,
    )
    row = LocalConversationTurn(
        id=uuid4(),
        organization_id=organization_id,
        department_id=department,
        **owner_values(actor),
        turn_key=body.turn_key,
        conversation_id=body.conversation_id,
        sequence=body.sequence,
        profile_revision_id=body.profile_revision_id,
        connection_id=body.connection_id,
        fingerprint=fingerprint,
        input_text=body.input_text,
        response_text=body.response_text,
        outcome=body.outcome,
        occurred_at=body.occurred_at,
        completed_at=body.completed_at,
        created_at=timestamp,
        expires_at=timestamp
        + timedelta(days=min(settings.local_history_retention_days, limits["result_retention_days"])),
        byte_size=size,
        document={k: v for k, v in document.items() if k not in {"input_text", "response_text"}},
    )
    session.add(row)
    await audit(
        session,
        actor,
        "llm.local_conversation.recorded",
        "local_conversation_turn",
        row.id,
        organization_id,
        {"outcome": body.outcome},
        department_id=department,
    )
    await commit(session, row)
    return view(row)


async def readable_query(session, actor, org):
    access = await organization_access(session, actor, org, "org.results.read")
    query = select(LocalConversationTurn).where(
        LocalConversationTurn.organization_id == org, LocalConversationTurn.expires_at > now()
    )
    if access.role != "org_admin":
        query = query.where(owner_filter(LocalConversationTurn, actor))
    if access.department_id:
        query = query.where(LocalConversationTurn.department_id == access.department_id)
    query = query.where(
        (LocalConversationTurn.department_id.is_(None))
        | (
            LocalConversationTurn.department_id.in_(
                select(Department.id).where(Department.organization_id == org, Department.is_active.is_(True))
            )
        )
    )
    return query


@router.get(BASE)
async def list_records(
    organization_id: UUID,
    actor: Actor,
    session: Session,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    conversation_id: UUID | None = None,
    before: UUID | None = None,
    completed_only: bool = True,
    mine: bool = True,
):
    query = await readable_query(session, actor, organization_id)
    if mine:
        query = query.where(owner_filter(LocalConversationTurn, actor))
    if conversation_id:
        query = query.where(LocalConversationTurn.conversation_id == conversation_id)
    if completed_only:
        query = query.where(LocalConversationTurn.outcome == "completed")
    if before:
        anchor = required(await session.scalar(query.where(LocalConversationTurn.id == before)))
        query = query.where(
            tuple_(LocalConversationTurn.occurred_at, LocalConversationTurn.id)
            < tuple_(anchor.occurred_at, anchor.id)
        )
    rows = (
        await session.scalars(
            query.order_by(LocalConversationTurn.occurred_at.desc(), LocalConversationTurn.id.desc()).limit(
                limit + 1
            )
        )
    ).all()
    return {
        "items": [view(row) for row in rows[:limit]],
        "next_before": str(rows[limit - 1].id) if len(rows) > limit else None,
    }


@router.get(BASE + "/{turn_key}")
async def get_record(organization_id: UUID, turn_key: UUID, actor: Actor, session: Session):
    query = await readable_query(session, actor, organization_id)
    return view(required(await session.scalar(query.where(LocalConversationTurn.turn_key == turn_key))))
