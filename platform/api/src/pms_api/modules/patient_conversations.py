"""Scoped, fixed interview contexts; local execution never proxies inference."""

from dataclasses import asdict
from datetime import timedelta
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from pydantic import Field
from sqlalchemy import func, select
from training_contracts import fingerprint
from training_contracts.conversation.context import ConversationContext
from training_contracts.languages import DEFAULT_REGISTRY, LanguageTag, get_pack
from training_contracts.languages.capabilities import resolve_capabilities
from training_contracts.localized_cases import localization_ready
from training_contracts.patient_conversation import conversation_context

from pms_api.core.common import now, require, required
from pms_api.core.dependencies import Session
from pms_api.database.models import LLMConnection, LLMRequest, PatientConversation, PlatformSettings
from pms_api.modules.common import audit
from pms_api.modules.model_routing import require_route
from pms_api.modules.patient_practice import (
    access,
    active_template,
    own_selection,
    practice_for_request,
    published_scenario,
    scenario_practice_access,
)
from pms_api.modules.runtime_model_store import runtime_model
from pms_api.modules.schemas import Input
from pms_api.security.access import Actor
from pms_api.security.practice_access import owner_filter, owner_values

router = APIRouter(prefix="/organizations/{organization_id}/patient-practice", tags=["Patient conversations"])


class StartConversation(Input):
    request_key: UUID
    assigned_session_id: UUID | None = None
    practice_id: UUID
    practice_revision: int = Field(ge=1, le=2147483646, strict=True)
    connection_id: UUID
    language: LanguageTag
    department_id: UUID | None = None
    profile_revision_id: UUID | None = None
    configuration_hash: str | None = Field(None, pattern=r"^[a-f0-9]{64}$")
    input_mode: Literal["text", "speech"] = "text"
    output_mode: Literal["text", "speech"] = "text"


def pack_for(language):
    try:
        return get_pack(language)
    except ValueError:
        require(False, "conversation_language_unavailable", "Choose an available interview language", 422)


def view(row):
    return {"context": row.context, "snapshot": row.snapshot, "status": row.status, "sequence": row.sequence}


async def owned(session, actor, org, conversation_id, *, lock=False, active=True):
    await scenario_practice_access(session, actor, org)
    query = (
        select(PatientConversation)
        .where(
            PatientConversation.id == conversation_id,
            PatientConversation.organization_id == org,
            owner_filter(PatientConversation, actor),
        )
        .execution_options(populate_existing=True)
    )
    if lock:
        query = query.with_for_update()
    row = required(await session.scalar(query))
    if active:
        require(
            row.status == "active" and row.expires_at > now(),
            "conversation_closed",
            "Start a new conversation",
            409,
        )
        pack = pack_for(row.context["language"])
        require(
            pack is not None
            and pack.version == row.context["language_pack_version"]
            and pack.content_hash == row.context["language_pack_hash"],
            "language_pack_changed",
            "The language pack changed; start a new conversation",
            409,
        )
        selection = required(await own_selection(session, actor, org))
        require(
            selection.id == row.practice_id and selection.revision == row.context["practice_revision"],
            "patient_setup_changed",
            "Patient setup changed; start a new conversation",
            409,
        )
        if row.scenario_id is not None:
            require(
                selection.scenario_id == row.scenario_id,
                "patient_setup_changed",
                "Practice scenario changed; start a new conversation",
                409,
            )
            await published_scenario(session, org, row.scenario_id, row.context["language"])
        else:
            await access(session, actor, org)
            require(
                selection.tenant_template_id is not None,
                "legacy_patient_setup",
                "Select a published scenario before continuing",
                409,
            )
            await active_template(session, org, selection.tenant_template_id)
    return row


async def validate_execution(session, actor, row, settings):
    from pms_api.modules.session_queue import validate_conversation_assignment

    await validate_conversation_assignment(session, row, actor)
    from pms_api.modules.llm import scope

    require(settings.llm_enabled, "llm_disabled", "LLM access is disabled", 503)
    await scope(session, actor, row.organization_id, row.department_id, resolve_default=False)
    context = ConversationContext.model_validate(row.context)
    conn = required(
        await runtime_model(session, context.connection_id, LLMConnection, populate_existing=True)
    )
    require(
        conn.organization_id in {None, row.organization_id}
        and conn.is_active
        and conn.archived_at is None
        and conn.revision == context.connection_revision,
        "llm_connection_changed",
        "Model configuration changed; start a new conversation",
        409,
    )
    if context.profile_revision_id:
        await require_route(
            session,
            actor,
            row.organization_id,
            context.profile_revision_id,
            context.configuration_hash,
            settings,
        )
    platform = required(await session.get(PlatformSettings, 1, populate_existing=True))
    require(not platform.maintenance_mode, "maintenance_mode", "New processing is paused", 503)
    require(
        any(item["code"] == context.language and item["is_active"] for item in platform.languages),
        "conversation_language_unavailable",
        "Selected language is disabled",
        409,
    )
    return context


@router.get("/capabilities")
async def capabilities(
    organization_id: UUID,
    request: Request,
    actor: Actor,
    session: Session,
    connection_id: UUID,
    practice_id: UUID,
    practice_revision: int,
):
    selection = await practice_for_request(session, actor, organization_id, practice_id, practice_revision)
    if actor.device:
        from pms_api.modules.model_routing import effective_route

        route = await effective_route(session, actor, organization_id, request.app.state.settings)
        require(route["llm"]["connection_id"] == str(connection_id), "not_found", "Model not assigned", 404)
    conn = required(await runtime_model(session, connection_id, LLMConnection))
    require(
        conn.organization_id in {None, organization_id}
        and conn.is_active
        and getattr(conn, "kind", "llm") == "llm",
        "not_found",
        "Model not found",
        404,
    )
    platform = required(await session.get(PlatformSettings, 1))
    enabled = {item["code"] for item in platform.languages if item["is_active"]}
    values = []
    for pack in DEFAULT_REGISTRY.all():
        localized = selection.document.get("version") in (3, 4, 5) and localization_ready(
            selection.document, pack.language
        )
        ready = resolve_capabilities(
            pack,
            enabled=pack.language in enabled,
            localized=localized,
            llm_languages=request.app.state.settings.patient_enabled_languages,
        )
        values.append(
            {
                **asdict(ready),
                "name": pack.name,
                "native_name": pack.native_name,
                "speech_readiness": "check_execution_host",
                "quality_qualification": "not_certified",
            }
        )
    return {"languages": values}


@router.post("/conversations")
async def start(
    organization_id: UUID, body: StartConversation, request: Request, actor: Actor, session: Session
):
    from pms_api.modules.llm import scope

    await scenario_practice_access(session, actor, organization_id, lock=True)
    _, department = await scope(session, actor, organization_id, body.department_id)
    payload = body.model_dump(mode="json")
    if body.assigned_session_id is None:
        payload.pop("assigned_session_id")  # Preserve standalone retry identities across the upgrade.
    request_hash = fingerprint(payload)
    existing = await session.scalar(
        select(PatientConversation).where(
            PatientConversation.organization_id == organization_id,
            owner_filter(PatientConversation, actor),
            PatientConversation.request_key == body.request_key,
        )
    )
    if existing:
        require(existing.fingerprint == request_hash, "idempotency_conflict", "Request key already used", 409)
        existing = await owned(session, actor, organization_id, existing.id)
        await validate_execution(session, actor, existing, request.app.state.settings)
        return view(existing)
    selection = await practice_for_request(
        session, actor, organization_id, body.practice_id, body.practice_revision
    )
    from pms_api.modules.session_queue import conversation_assignment

    await conversation_assignment(session, actor, selection, body.assigned_session_id)
    pack = pack_for(body.language)
    assert pack is not None
    require(
        body.language == selection.language, "patient_language_changed", "Use the saved patient language", 409
    )
    settings = request.app.state.settings
    require(
        body.language in settings.patient_enabled_languages,
        "model_language_unavailable",
        "This interview language has not been enabled for this installation",
        409,
    )
    require(
        selection.document.get("version") in (3, 4, 5)
        and localization_ready(selection.document, body.language),
        "case_translation_unavailable",
        "Save a complete current translation before starting",
        409,
    )
    conn = required(await runtime_model(session, body.connection_id, LLMConnection, populate_existing=True))
    require(
        not actor.device or body.profile_revision_id is not None,
        "model_selection_required",
        "Use this device's assigned models",
        409,
    )
    require(
        conn.organization_id in {None, organization_id}
        and conn.is_active
        and getattr(conn, "kind", "llm") == "llm",
        "not_found",
        "Model not found",
        404,
    )
    if body.profile_revision_id:
        route = await require_route(
            session, actor, organization_id, body.profile_revision_id, body.configuration_hash, settings
        )
        require(
            route["llm"]["connection_id"] == str(conn.id),
            "model_selection_changed",
            "Use the selected model",
            409,
        )
    else:
        require(
            conn.organization_id is not None,
            "model_selection_required",
            "Select a device model configuration",
            409,
        )
        require(body.configuration_hash is None, "invalid_configuration", "Select a published profile", 422)
    count = await session.scalar(
        select(func.count())
        .select_from(PatientConversation)
        .where(
            PatientConversation.organization_id == organization_id, owner_filter(PatientConversation, actor)
        )
    )
    require((count or 0) < 100, "conversation_capacity", "Conversation storage limit reached", 429)
    stamp, identity = now(), uuid4()
    prompt = conversation_context(selection.document, body.language, "", seed=str(identity))
    context = ConversationContext(
        conversation_id=identity,
        organization_id=organization_id,
        owner_id=actor.id,
        department_id=department,
        practice_id=selection.id,
        practice_revision=selection.revision,
        case_snapshot_hash=fingerprint(selection.document),
        language=pack.language,
        language_pack_version=pack.version,
        language_pack_hash=pack.content_hash,
        localization_revision=selection.document["localizations"][body.language]["revision"],
        policy_version=prompt["policy_version"],
        compiler_version=prompt["compiler_version"],
        profile_revision_id=body.profile_revision_id,
        configuration_hash=body.configuration_hash
        or fingerprint({"connection": str(conn.id), "revision": conn.revision}),
        connection_id=conn.id,
        connection_revision=conn.revision,
        execution="caller" if conn.provider == "local_llama_cpp" else "platform",
        input_mode=body.input_mode,
        output_mode=body.output_mode,
        speech_locale=pack.speech_locales[0],
        created_at=stamp,
        expires_at=stamp + timedelta(hours=24),
    )
    row = PatientConversation(
        id=identity,
        organization_id=organization_id,
        **owner_values(actor),
        assigned_session_id=body.assigned_session_id,
        department_id=department,
        request_key=body.request_key,
        fingerprint=request_hash,
        practice_id=selection.id,
        scenario_id=selection.scenario_id,
        context=context.model_dump(mode="json"),
        snapshot=prompt,
        status="active",
        sequence=0,
        history=[],
        created_at=stamp,
        expires_at=context.expires_at,
    )
    await validate_execution(session, actor, row, settings)
    session.add(row)
    from pms_api.modules.session_archives import create_archive

    await create_archive(session, row, selection)
    await audit(
        session,
        actor,
        "patient.conversation.started",
        "patient_conversation",
        identity,
        organization_id,
        department_id=department,
        details={
            "language": pack.language,
            "pack_version": pack.version,
            "scenario_id": str(selection.scenario_id) if selection.scenario_id else None,
        },
    )
    await session.commit()
    return view(row)


@router.get("/conversations/{conversation_id}")
async def get(organization_id: UUID, conversation_id: UUID, request: Request, actor: Actor, session: Session):
    row = await owned(session, actor, organization_id, conversation_id)
    await validate_execution(session, actor, row, request.app.state.settings)
    return view(row)


@router.post("/conversations/{conversation_id}/close")
async def close(organization_id: UUID, conversation_id: UUID, actor: Actor, session: Session):
    await scenario_practice_access(session, actor, organization_id, lock=True)
    row = await owned(session, actor, organization_id, conversation_id, lock=True, active=False)
    if row.scenario_id is None:
        await access(session, actor, organization_id)
    if row.status == "active":
        row.status, row.closed_at = "closed", now()
        await audit(
            session,
            actor,
            "patient.conversation.closed",
            "patient_conversation",
            row.id,
            organization_id,
            department_id=row.department_id,
        )
        await session.commit()
    return {"conversation_id": str(row.id), "status": row.status}


async def claim_turn(session, actor, org, conversation_id, body, settings):
    row = await owned(session, actor, org, conversation_id, lock=True)
    context = await validate_execution(session, actor, row, settings)
    require(
        context.execution == "platform" and body.connection_id == context.connection_id,
        "conversation_execution_mismatch",
        "Use this conversation's selected execution host",
        409,
    )
    require(
        body.language == context.language
        and body.practice_id == context.practice_id
        and body.practice_revision == context.practice_revision
        and body.department_id == context.department_id,
        "conversation_context_changed",
        "Use the fixed conversation context",
        409,
    )
    require(len(body.messages) == 1, "conversation_history_managed", "Submit only the current question", 422)
    require(row.sequence < 1000, "conversation_turn_limit", "Start a new conversation", 409)
    running = await session.scalar(
        select(LLMRequest.id).where(LLMRequest.conversation_id == row.id, LLMRequest.status == "running")
    )
    require(running is None, "conversation_busy", "Another question is active in this conversation", 409)
    return row


async def validate_report_context(session, actor, org, body):
    reference = body.context_ref
    require(
        not actor.device or reference is not None,
        "conversation_required",
        "Device reports require their Practice conversation",
        422,
    )
    if reference is None:
        return  # Previously queued reports remain explicitly client-reported.
    row = await owned(session, actor, org, reference.conversation_id, active=False)
    if row.assigned_session_id:
        from pms_api.database.models import PracticeSession

        assignment = required(await session.get(PracticeSession, row.assigned_session_id))
        end = min(
            assignment.expires_at, assignment.started_at + timedelta(seconds=assignment.duration_seconds)
        )
        if assignment.ended_at:
            end = min(end, assignment.ended_at)
        require(
            assignment.started_at - timedelta(seconds=5) <= body.occurred_at <= end,
            "invalid_request",
            "Turn falls outside its assigned session",
            422,
        )
    context = row.context
    require(
        context["execution"] == "caller"
        and context["language"] == body.language
        and context["language_pack_hash"] == reference.language_pack_hash
        and context["language_pack_version"] == reference.language_pack_version
        and context["compiler_version"] == reference.compiler_version
        and context["case_snapshot_hash"] == body.practice_snapshot_hash
        and context["practice_revision"] == body.practice_revision
        and context["practice_id"] == str(body.practice_id)
        and context["connection_id"] == str(body.connection_id)
        and context["connection_revision"] == body.connection_revision
        and context["configuration_hash"] == body.configuration_hash
        and context["profile_revision_id"] == str(body.profile_revision_id)
        and row.department_id == body.department_id,
        "conversation_context_changed",
        "Report does not match the fixed conversation context",
        409,
    )
    require(
        row.created_at - timedelta(minutes=5) <= body.occurred_at <= row.expires_at,
        "invalid_request",
        "Turn falls outside the conversation lifetime",
        422,
    )
