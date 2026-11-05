"""Tenant-scoped LLM calls; one generation per endpoint, never POST replay."""

import asyncio
import json
import time
from contextlib import aclosing, suppress
from datetime import timedelta
from uuid import UUID, uuid4

import anyio
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, text
from training_contracts import fingerprint as document_fingerprint
from training_contracts.patient_conversation import (
    SAFETY_MARGIN,
    conversation_history,
    output_budget,
    run_conversation,
    select_messages,
)
from training_contracts.patient_turn import TurnError

from pms_api.core.common import AppError, canonical, digest, now, require, required, token_hash
from pms_api.core.dependencies import Session
from pms_api.database.models import (
    Department,
    LLMConnection,
    LLMRequest,
    Organization,
    PatientConversation,
    PlatformSettings,
    RuntimeModel,
)
from pms_api.integrations.llm.budget import fit_patient_prompt
from pms_api.integrations.llm.capabilities import generation_options
from pms_api.integrations.llm.client import LLMError
from pms_api.integrations.llm.policy import configured_endpoint
from pms_api.integrations.llm.quota import reported_total, reserve_total
from pms_api.integrations.llm.runner import ProviderRunner, app_error
from pms_api.integrations.vault import CredentialVault
from pms_api.modules.common import audit, commit
from pms_api.modules.llm_schemas import Completion
from pms_api.modules.patient_practice import practice_for_request
from pms_api.security.access import Actor, reload_actor
from pms_api.security.practice_access import actor_identity, is_owner, owner_values
from pms_api.security.practice_access import execution_access as organization_access

router = APIRouter(tags=["LLM"])
BASE = "/organizations/{organization_id}/llm"


class LLMStreamingResponse(StreamingResponse):
    """Observe disconnects even when middleware hides transport send errors."""

    async def __call__(self, scope, receive, send):
        try:
            async with anyio.create_task_group() as group:

                async def stream():
                    await self.stream_response(send)
                    group.cancel_scope.cancel()

                group.start_soon(stream)
                await self.listen_for_disconnect(receive)
                group.cancel_scope.cancel()
        finally:
            with anyio.move_on_after(8, shield=True):
                close = getattr(self.body_iterator, "aclose", None)
                if close:
                    await close()


def enabled(request):
    require(request.app.state.settings.llm_enabled, "llm_disabled", "LLM access is disabled", 503)


async def scope(session, actor, org, department, permission="org.processing.execute", resolve_default=True):
    access = await organization_access(session, actor, org, permission)
    if resolve_default:
        department = department or access.department_id
    if actor.device or access.department_id:
        require(department == access.department_id, "not_found", "Scope not found", 404)
    if department:
        row = required(await session.get(Department, department, populate_existing=True))
        require(row.organization_id == org, "not_found", "Scope not found", 404)
        require(row.is_active, "department_inactive", "Department is inactive", 409)
    return access, department


async def connection(session, org, id):
    model = await session.get(RuntimeModel, id, populate_existing=True)
    if model:
        require(
            model.kind == "llm" and model.organization_id in {None, org}, "not_found", "Model not found", 404
        )
        return model
    row = await session.scalar(
        select(LLMConnection)
        .where(LLMConnection.organization_id == org, LLMConnection.id == id)
        .execution_options(populate_existing=True)
    )
    return required(row)


def request_view(row, cached=False):
    return {
        "request_key": str(row.request_key),
        "id": str(row.id),
        "status": row.status,
        "cached": cached,
        "result": row.result,
        "error_code": row.error_code,
        "expires_at": row.expires_at.isoformat(),
    }


@router.get(BASE + "/models/{connection_id}/status")
async def connection_status(
    organization_id: UUID, connection_id: UUID, request: Request, actor: Actor, session: Session
):
    enabled(request)
    await organization_access(session, actor, organization_id, "org.processing.execute")
    if actor.device:
        from pms_api.modules.model_routing import effective_route

        route = await effective_route(session, actor, organization_id, request.app.state.settings)
        require(route["llm"]["connection_id"] == str(connection_id), "not_found", "Model not assigned", 404)
    row = await connection(session, organization_id, connection_id)
    require(row.is_active, "llm_connection_inactive", "Connection is inactive", 409)
    platform = required(await session.get(PlatformSettings, 1, populate_existing=True))
    require(
        row.provider != "azure_openai" or "azure" in platform.enabled_providers,
        "provider_disabled",
        "Azure is disabled in platform settings",
        503,
    )
    url = configured_endpoint(row, request.app.state.settings, dispatch=True)
    if row.provider == "local_llama_cpp":
        # Reachable only from the machine it runs on, so this is a configuration check.
        # Whoever executes the turn verifies the server itself before recording.
        return {
            "status": "declared",
            "model": row.model,
            "revision": row.revision,
            "provider": row.provider,
            "check": "configuration_only",
            "inference_verified": False,
            "execution": "caller",
        }
    key = CredentialVault(request.app.state.settings).decrypt(row)["api_key"]
    model, revision, provider = row.model, row.revision, row.provider
    identity = actor_identity(actor)
    await session.rollback()
    await request.app.state.llm.health(url, model, key, provider=provider)
    check_expiry(actor)
    reloaded = await reload_actor(session, **identity)
    await organization_access(session, reloaded, organization_id, "org.processing.execute")
    if reloaded.device:
        route = await effective_route(session, reloaded, organization_id, request.app.state.settings)
        require(route["llm"]["connection_id"] == str(connection_id), "not_found", "Model not assigned", 404)
    current = await connection(session, organization_id, connection_id)
    require(
        current.is_active and current.revision == revision,
        "llm_connection_changed",
        "LLM connection changed",
        409,
    )
    configured_endpoint(current, request.app.state.settings, dispatch=True)
    enabled(request)
    platform = required(await session.get(PlatformSettings, 1, populate_existing=True))
    require(
        provider != "azure_openai" or "azure" in platform.enabled_providers,
        "provider_disabled",
        "Azure is disabled in platform settings",
        503,
    )
    return {
        "status": "ready",
        "model": model,
        "revision": revision,
        "provider": provider,
        "check": "authenticated_api_access" if provider == "azure_openai" else "model_catalog",
        "inference_verified": False,
    }


async def recover(session, target):
    stale = (
        await session.scalars(
            select(LLMRequest)
            .where(
                LLMRequest.target_key == target,
                LLMRequest.status == "running",
                LLMRequest.lease_expires_at <= now(),
            )
            .with_for_update()
        )
    ).all()
    for row in stale:
        row.status, row.error_code, row.completed_at = "unknown", "llm_lease_expired", now()
        await audit(
            session,
            None,
            "llm.request.unknown",
            "llm_request",
            row.id,
            row.organization_id,
            department_id=row.department_id,
        )
    await session.flush()


@router.get(BASE + "/requests/{request_key}")
async def get_request(
    organization_id: UUID, request_key: UUID, request: Request, actor: Actor, session: Session
):
    enabled(request)
    row = required(
        await session.scalar(
            select(LLMRequest).where(
                LLMRequest.organization_id == organization_id, LLMRequest.request_key == request_key
            )
        )
    )
    access, _ = await scope(
        session, actor, organization_id, row.department_id, "org.results.read", resolve_default=False
    )
    require(is_owner(row, actor) or access.role == "org_admin", "not_found", "Request not found", 404)
    require(row.expires_at > now(), "llm_result_expired", "Result has expired", 410)
    if row.status == "running" and row.lease_expires_at <= now():
        await recover(session, row.target_key)
        await commit(session, row)
    return request_view(row, row.status == "succeeded")


async def admit(request, actor, session, org, body):
    settings = request.app.state.settings
    if actor.device:
        require(
            body.conversation_id is not None and body.profile_revision_id is not None,
            "conversation_required",
            "Start a device Practice conversation first",
            422,
        )
    access, department = await scope(session, actor, org, body.department_id)
    conn = await connection(session, org, body.connection_id)
    require(conn.is_active, "llm_connection_inactive", "Connection is inactive", 409)
    # A local model runs on the caller's machine; this service is not on that data path and
    # never dials it. The caller executes the turn and reports it to /llm/local-turns.
    require(
        conn.provider != "local_llama_cpp",
        "llm_local_execution_required",
        "This model runs on the caller's own machine; run the turn there",
        409,
    )
    base_url = configured_endpoint(conn, settings)
    profile_hash = None
    if body.profile_revision_id is not None:
        from pms_api.modules.model_routing import require_route

        effective = await require_route(
            session, actor, org, body.profile_revision_id, body.configuration_hash, settings
        )
        require(
            effective["llm"]["connection_id"] == str(conn.id),
            "model_selection_changed",
            "Reload model selection",
            409,
        )
        profile_hash = effective["configuration_hash"]
    else:
        require(
            conn.organization_id is not None,
            "model_selection_required",
            "Select this model on a device before using it",
            409,
        )
        require(
            body.configuration_hash is None, "profile_required", "Supply a profile revision with its hash"
        )
    target = digest(base_url.removesuffix("/v1"))
    # Cross-process, cross-organization capacity for the same native model server.
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": int(target[:15], 16)})
    await session.get(Organization, org, with_for_update=True)
    practice = None
    if body.practice_id:
        require(
            actor.device is not None or department is None,
            "scope_unavailable",
            "Practice requires organization-wide staff access",
            403,
        )
        practice = await practice_for_request(session, actor, org, body.practice_id, body.practice_revision)
        require(
            body.language == practice.language,
            "patient_language_changed",
            "Use the saved patient language",
            409,
        )
    fingerprint = token_hash(
        canonical(
            {
                **body.model_dump(
                    mode="json",
                    exclude={"stream"}
                    | ({"practice_id", "practice_revision"} if practice is None else set())
                    | (
                        {"profile_revision_id", "configuration_hash"}
                        if body.profile_revision_id is None
                        else set()
                    ),
                ),
                "department_id": str(department) if department else None,
            }
        ),
        settings.token_pepper.get_secret_value(),
    )
    existing = await session.scalar(
        select(LLMRequest).where(
            LLMRequest.organization_id == org, LLMRequest.request_key == body.request_key
        )
    )
    if existing:
        require(
            is_owner(existing, actor) and existing.fingerprint == fingerprint,
            "idempotency_conflict",
            "Request key already used with different content or identity",
            409,
        )
        require(
            existing.expires_at > now(),
            "llm_result_expired",
            "Result expired; use a new question/request key",
            410,
        )
        await recover(session, existing.target_key)
        await session.commit()
        return existing, None
    interview = None
    if practice:
        from pms_api.modules.patient_conversations import claim_turn

        require(
            body.conversation_id is not None,
            "conversation_required",
            "Start a patient conversation first",
            409,
        )
        interview = await claim_turn(session, actor, org, body.conversation_id, body, settings)
    configured_endpoint(conn, settings, dispatch=True)
    check_expiry(actor)
    platform = required(await session.get(PlatformSettings, 1, populate_existing=True))
    require(not platform.maintenance_mode, "maintenance_mode", "New processing is paused", 503)
    require(
        conn.provider != "azure_openai" or "azure" in platform.enabled_providers,
        "provider_disabled",
        "Azure is disabled in platform settings",
        503,
    )
    # Every admitted connection is dispatched by this service to a cloud endpoint, so capacity
    # is the configured number of concurrent slots per destination.
    slots = [digest(target + ":cloud:" + str(slot)) for slot in range(settings.llm_cloud_concurrency)]
    for slot in slots:
        await recover(session, slot)
    occupied_slots = set(
        (
            await session.scalars(
                select(LLMRequest.target_key).where(
                    LLMRequest.target_key.in_(slots), LLMRequest.status == "running"
                )
            )
        ).all()
    )
    available_slot = next((slot for slot in slots if slot not in occupied_slots), None)
    require(available_slot is not None, "llm_busy", "Model capacity is busy; no request was submitted", 429)
    assert available_slot is not None
    target = available_slot
    reserve = (
        output_budget(conn.max_tokens, settings.patient_conversation_tokens_remote)
        if practice
        else conn.max_tokens
    )
    key = CredentialVault(settings).decrypt(conn)["api_key"]
    timestamp = now()
    row = LLMRequest(
        id=uuid4(),
        organization_id=org,
        department_id=department,
        **owner_values(actor),
        device_credential_version=actor.device.credential_version if actor.device else None,
        connection_id=conn.id,
        connection_revision=conn.revision,
        request_key=body.request_key,
        fingerprint=fingerprint,
        profile_revision_id=body.profile_revision_id,
        configuration_hash=profile_hash,
        conversation_id=interview.id if interview else None,
        conversation_sequence=interview.sequence + 1 if interview else None,
        conversation_input=body.messages[-1].content if interview else None,
        practice_id=practice.id if practice else None,
        practice_revision=practice.revision if practice else None,
        practice_snapshot_hash=document_fingerprint(practice.document) if practice else None,
        target_key=target,
        status="running",
        reserved_tokens=reserve,
        lease_token=uuid4(),
        lease_expires_at=timestamp + timedelta(seconds=settings.llm_timeout_seconds + 10),
        created_at=timestamp,
        expires_at=timestamp + timedelta(hours=24),
    )
    from training_contracts.languages import get_pack

    try:
        language = "Reply in " + get_pack(body.language).name + "."
    except ValueError:
        require(False, "conversation_language_unavailable", "Choose an available language", 422)
        raise AssertionError("unreachable") from None
    input_messages = (
        [*interview.history, body.messages[-1].model_dump()]
        if interview
        else [m.model_dump() for m in body.messages]
    )
    parameters = {
        "base_url": base_url,
        "model": conn.model,
        "key": key,
        "max_tokens": conn.max_tokens,
        "provider": conn.provider,
        "token_parameter": conn.token_parameter,
        "stream_usage": conn.stream_usage,
        "request_id": str(row.id),
        "messages": [
            {"role": conn.instruction_role, "content": conn.system_prompt + "\n" + language},
            # One history policy for every caller: a device or laptop cannot widen the
            # window by sending more turns, and cost per turn stays bounded.
            *conversation_history(input_messages, settings.patient_history_messages_remote),
        ],
        "streaming": body.stream,
        **generation_options(conn),
    }
    if practice:
        assert interview is not None
        context = dict(interview.snapshot)
        context["conversation_id"] = str(interview.id)
        parameters["messages"][0]["content"] = context["system"]
        original_count = len(parameters["messages"])
        parameters["messages"] = select_messages(context, parameters["messages"])
        omitted_pairs = (original_count - len(parameters["messages"])) // 2
        parameters["max_tokens"] = reserve
        parameters["messages"], budget = await fit_patient_prompt(
            request.app.state.llm, parameters, settings, margin=SAFETY_MARGIN
        )
        from training_contracts.conversation.question_scope import prompt_mode

        budget["prompt_mode"] = prompt_mode(context, parameters["messages"])
        budget["history_pairs_omitted_for_scope"] = omitted_pairs
        context["budget"] = {
            "conversation": budget,
            "practice_id": str(practice.id),
            "practice_revision": practice.revision,
            "snapshot_hash": row.practice_snapshot_hash,
        }
        parameters["_patient_context"] = context
        check_expiry(actor)
    row.reserved_total_tokens = reserve_total(parameters, settings)
    # Organization lock above serializes admission across users, devices and destinations.
    # Pending/uncertain work keeps its reservation; completed usage replaces it once.
    day = row.created_at.replace(hour=0, minute=0, second=0, microsecond=0)
    count, tokens = (
        await session.execute(
            select(
                func.count(),
                func.coalesce(
                    func.sum(
                        func.coalesce(LLMRequest.charged_total_tokens, LLMRequest.reserved_total_tokens)
                    ),
                    0,
                ),
            ).where(
                LLMRequest.organization_id == org,
                LLMRequest.created_at >= day,
                LLMRequest.reserved_total_tokens > 0,
            )
        )
    ).one()
    require(
        not settings.llm_daily_requests or count < settings.llm_daily_requests,
        "llm_daily_request_limit",
        "Organization daily online request allowance reached; resets at 00:00 UTC",
        429,
    )
    require(
        tokens + row.reserved_total_tokens <= settings.llm_daily_total_tokens,
        "llm_daily_limit",
        "Organization daily online input + output token allowance reached; resets at 00:00 UTC",
        429,
    )
    session.add(row)
    await audit(session, actor, "llm.request.accepted", "llm_request", row.id, org, department_id=department)
    await session.commit()
    return row, parameters


def check_expiry(actor):
    if actor.claims:
        require(actor.claims.get("exp", 0) > time.time(), "authentication_expired", "Sign in again", 401)


async def live_access(session, row, settings=None):
    actor = await reload_actor(
        session,
        user_id=row.user_id,
        device_id=row.device_id,
        credential_version=row.device_credential_version,
    )
    await scope(session, actor, row.organization_id, row.department_id, resolve_default=False)
    if row.conversation_id:
        from pms_api.modules.patient_conversations import owned, validate_execution

        interview = await owned(session, actor, row.organization_id, row.conversation_id)
        if settings is not None:
            await validate_execution(session, actor, interview, settings)
    if row.practice_id:
        practice = await practice_for_request(
            session, actor, row.organization_id, row.practice_id, row.practice_revision
        )
        require(
            document_fingerprint(practice.document) == row.practice_snapshot_hash,
            "patient_setup_changed",
            "Patient setup changed",
            409,
        )
    conn = await connection(session, row.organization_id, row.connection_id)
    require(
        conn.is_active and conn.revision == row.connection_revision,
        "llm_connection_changed",
        "LLM connection changed",
        409,
    )
    if settings is not None:
        require(settings.llm_enabled, "llm_disabled", "LLM access is disabled", 503)
        configured_endpoint(conn, settings, dispatch=True)
        if row.profile_revision_id:
            from pms_api.modules.model_routing import require_route

            await require_route(
                session, actor, row.organization_id, row.profile_revision_id, row.configuration_hash, settings
            )
    platform = required(await session.get(PlatformSettings, 1, populate_existing=True))
    require(not platform.maintenance_mode, "maintenance_mode", "Processing is paused", 503)
    require(
        conn.provider != "azure_openai" or "azure" in platform.enabled_providers,
        "provider_disabled",
        "Azure is disabled in platform settings",
        503,
    )
    require(row.lease_expires_at > now(), "llm_lease_expired", "Request lease expired", 409)
    return actor


async def finalize(sessions, row, status, result=None, code=None, caller=None, settings=None):
    async with sessions() as session:
        if status == "succeeded":
            # Same order as admission/setup saves: settle usage and accept the answer atomically.
            await session.get(Organization, row.organization_id, with_for_update=True, populate_existing=True)
        current = required(await session.get(LLMRequest, row.id, with_for_update=True))
        require(
            current.status == "running" and current.lease_token == row.lease_token,
            "llm_lease_lost",
            "Request ownership changed",
            409,
        )
        actor = await live_access(session, current, settings) if status == "succeeded" else None
        if status == "succeeded" and caller is not None:
            check_expiry(caller)
        current.status, current.result, current.error_code, current.completed_at = status, result, code, now()
        if status == "succeeded":
            current.charged_total_tokens = reported_total(result)
            if current.conversation_id:
                interview = required(
                    await session.get(PatientConversation, current.conversation_id, with_for_update=True)
                )
                require(
                    interview.status == "active" and interview.sequence + 1 == current.conversation_sequence,
                    "conversation_changed",
                    "Conversation changed before the answer completed",
                    409,
                )
                history = [
                    *interview.history,
                    {"role": "user", "content": current.conversation_input},
                    {"role": "assistant", "content": result["text"]},
                ]
                while (
                    len(history) > 12 or sum(len(item["content"].encode("utf-8")) for item in history) > 48000
                ):
                    del history[:2]
                interview.history = history
                interview.sequence = current.conversation_sequence
        await audit(
            session,
            actor,
            "llm.request." + status,
            "llm_request",
            current.id,
            current.organization_id,
            department_id=current.department_id,
        )
        await session.commit()


async def patient_turn(request, context, params, queue):
    """Run one shared patient conversation completion against this service's provider connection."""
    settings = request.app.state.settings
    runner = ProviderRunner(request.app.state.llm, params, settings)

    try:
        event = await run_conversation(runner, context, params["messages"], params["max_tokens"])
    except TurnError as error:
        raise app_error(error) from None
    await queue.put(event)


async def generation(request, actor, row, params):
    sessions = request.app.state.sessions
    queue: asyncio.Queue = asyncio.Queue(maxsize=1)
    context = params.get("_patient_context")
    provider_params = {key: value for key, value in params.items() if key != "_patient_context"}

    async def produce():
        try:
            # Keep the entire provider iterator in ONE task: its deadline context owns this task.
            async with asyncio.timeout(request.app.state.settings.llm_timeout_seconds):
                if context:
                    await patient_turn(request, context, provider_params, queue)
                else:
                    async for event in request.app.state.llm.events(**provider_params):
                        await queue.put(event)
            await queue.put(LLMError("llm_incomplete"))
        except asyncio.CancelledError:
            raise
        except Exception as error:
            await queue.put(LLMError("llm_timeout", 504) if isinstance(error, TimeoutError) else error)

    producer = None
    finished = False
    sequence = 0
    next_check = 0.0
    disconnected = None

    async def watch_disconnect():
        while (await request.receive())["type"] != "http.disconnect":
            pass

    try:
        async with sessions() as initial:
            await live_access(initial, row, request.app.state.settings)
            check_expiry(actor)
        producer = asyncio.create_task(produce())
        if not params["streaming"]:
            disconnected = asyncio.create_task(watch_disconnect())
        yield {
            "type": "metadata",
            "id": str(row.id),
            "request_key": str(row.request_key),
            "model": params["model"],
            "cached": False,
        }
        while True:
            if disconnected and disconnected.done():
                raise AppError(499, "client_disconnected", "Caller disconnected")
            if time.monotonic() >= next_check:
                check_expiry(actor)
                async with sessions() as session:
                    await live_access(session, row, request.app.state.settings)
                next_check = time.monotonic() + 1
            try:
                event = await asyncio.wait_for(queue.get(), timeout=max(0.01, next_check - time.monotonic()))
            except TimeoutError:
                continue
            if isinstance(event, Exception):
                raise event
            check_expiry(actor)
            if event["type"] == "done":
                await finalize(
                    sessions, row, "succeeded", event, caller=actor, settings=request.app.state.settings
                )
                finished = True
                if context and params["streaming"]:
                    yield {"type": "delta", "text": event["text"], "sequence": sequence + 1}
                yield {**event, "request_key": str(row.request_key), "status": "succeeded", "cached": False}
                return
            sequence += 1
            yield {**event, "sequence": sequence}
    except (asyncio.CancelledError, GeneratorExit):
        raise
    except Exception as error:
        code = error.code if isinstance(error, AppError) else "llm_internal_error"
        status = (
            "unknown" if code in {"llm_transport_unknown", "llm_timeout", "llm_internal_error"} else "failed"
        )
        await finalize(sessions, row, status, code=code)
        finished = True
        if not params["streaming"]:
            raise (error if isinstance(error, AppError) else LLMError(code)) from None
        yield {
            "type": "error",
            "code": code,
            "status": status,
            "request_key": str(row.request_key),
            "incomplete": True,
        }
    finally:
        # AnyIO cancellation repeats at every await; asyncio.shield alone is insufficient.
        with anyio.move_on_after(7, shield=True):
            for task in (producer, disconnected):
                if task:
                    task.cancel()
                    with suppress(asyncio.CancelledError, Exception):
                        await task
            if not finished:
                with suppress(Exception):
                    await finalize(sessions, row, "cancelled", code="client_cancelled")
                # Failure leaves the durable expiry to record unknown; never resubmit.


def sse(event):
    return "event: " + event["type"] + "\ndata: " + json.dumps(event, ensure_ascii=False) + "\n\n"


@router.post(BASE + "/completions")
async def completions(
    organization_id: UUID, body: Completion, request: Request, actor: Actor, session: Session
):
    enabled(request)
    row, params = await admit(request, actor, session, organization_id, body)
    if params is None:
        require(
            row.status == "succeeded",
            "llm_request_" + row.status,
            "Existing request was not resubmitted; check its status",
            409,
        )
        if not body.stream:
            return {**row.result, "request_key": str(row.request_key), "status": "succeeded", "cached": True}

        async def cached():
            yield sse({"type": "metadata", "request_key": str(row.request_key), "cached": True})
            yield sse(
                {
                    **row.result,
                    "type": "done",
                    "request_key": str(row.request_key),
                    "status": "succeeded",
                    "cached": True,
                }
            )

        return LLMStreamingResponse(
            cached(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"}
        )
    # Release the dependency's connection before any long network operation.
    await session.close()
    if body.stream:

        async def events():
            async with aclosing(generation(request, actor, row, params)) as iterator:
                async for event in iterator:
                    yield sse(event)

        return LLMStreamingResponse(
            events(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"}
        )
    async for event in generation(request, actor, row, params):
        if event["type"] == "done":
            return event
    raise LLMError("llm_incomplete")


async def expiry_loop(sessions):
    """Recover abandoned metadata even when the caller never returns for status."""
    import logging

    while True:
        try:
            async with sessions() as session:
                rows = (
                    await session.scalars(
                        select(LLMRequest)
                        .where(LLMRequest.status == "running", LLMRequest.lease_expires_at <= now())
                        .limit(50)
                        .with_for_update(skip_locked=True)
                    )
                ).all()
                for row in rows:
                    row.status, row.completed_at, row.error_code = "unknown", now(), "llm_lease_expired"
                    await audit(
                        session,
                        None,
                        "llm.request.unknown",
                        "llm_request",
                        row.id,
                        row.organization_id,
                        department_id=row.department_id,
                    )
                await session.commit()
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.getLogger("pms_api").warning("llm_expiry_unavailable")
        await asyncio.sleep(15)
