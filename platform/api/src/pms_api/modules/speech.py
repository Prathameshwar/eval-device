"""Interactive cloud transcription with bounded media and no uncertain replay."""

import asyncio
import hashlib
import logging
import time
from datetime import timedelta
from types import SimpleNamespace
from typing import Literal
from uuid import UUID, uuid4

import anyio
from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from sqlalchemy import func, select

from pms_api.core.common import canonical, now, require, required, token_hash
from pms_api.core.dependencies import Session
from pms_api.database.models import Organization, ProviderConnection
from pms_api.database.speech import SpeechRequest
from pms_api.integrations.vault import CredentialVault
from pms_api.integrations.whisper_cloud import speech_endpoint, speech_health, transcribe, wav_info
from pms_api.modules.common import audit
from pms_api.modules.llm import check_expiry
from pms_api.modules.model_routing import access_for, effective_route, require_route
from pms_api.modules.runtime_model_store import runtime_model
from pms_api.modules.speech_usage import daily_speech_millis, other_audio_usage
from pms_api.security.access import Actor, organization_access, reload_actor

router = APIRouter(tags=["Interactive speech"])
BASE = "/organizations/{organization_id}/speech"


def view(row, cached=False):
    return {
        "id": str(row.id),
        "request_key": str(row.request_key),
        "status": row.status,
        "cached": cached,
        "result": row.result,
        "recording_status": row.recording_status,
        "error_code": row.error_code,
        "expires_at": row.expires_at.isoformat(),
    }


def allowed(route, settings):
    require(settings.speech_enabled, "speech_disabled", "Interactive cloud speech is disabled", 503)
    require(
        route["audio"]["mode"] == "cloud",
        "speech_route_local",
        "This profile uses the laptop audio service",
        409,
    )
    require(
        route["audio"].get("enabled", True) and route["audio"]["provider"] == "azure_openai",
        "interactive_speech_unavailable",
        "This model uses device processing jobs, not interactive speech",
        409,
    )
    require(route["cloud_allowed"], "external_calls_disabled", "Cloud calls are disabled", 503)
    require(route["azure_enabled"], "provider_disabled", "Azure processing is disabled", 503)


@router.get(BASE + "/status")
async def status(
    organization_id: UUID, request: Request, session: Session, actor: Actor, profile_id: UUID | None = None
):
    settings = request.app.state.settings
    route = await effective_route(session, actor, organization_id, settings, profile_id)
    allowed(route, settings)
    connection = required(
        await runtime_model(session, UUID(route["audio"]["connection_id"]), ProviderConnection)
    )
    speech_endpoint(connection, settings)
    speech_connection = SimpleNamespace(settings=dict(connection.settings))
    key = CredentialVault(settings).decrypt(connection)["api_key"]
    # Rollback expires ORM attributes, including actor identity. Snapshot only
    # identity before the network call, then reauthorize with fresh database state.
    identity = {
        "user_id": actor.id if actor.user else None,
        "device_id": actor.id if actor.device else None,
        "credential_version": actor.device.credential_version if actor.device else None,
    }
    await session.rollback()
    await speech_health(request.app.state.llm, settings, speech_connection, key)
    check_expiry(actor)
    principal = await reload_actor(session, **identity)
    await require_route(
        session,
        principal,
        organization_id,
        UUID(route["profile_revision_id"]),
        route["configuration_hash"],
        settings,
    )
    return {
        "status": "ready",
        "model": route["audio"]["model"],
        "device": "cloud",
        "provider": "azure_openai",
        "check": "authenticated_api_access",
        "inference_verified": False,
    }


async def record(storage, key, data):
    try:
        async with asyncio.timeout(15):
            if hasattr(storage, "path"):

                def prepare_folder():
                    from training_contracts.privacy import no_link, private_directory

                    # Only tighten the new speech subtree, leaving unrelated media alone.
                    candidate = storage.root
                    if candidate.exists() or candidate.is_symlink():
                        no_link(candidate)
                    for part in key.split("/"):
                        candidate = candidate / part
                        if candidate.exists() or candidate.is_symlink():
                            no_link(candidate)
                    folder = storage.path(key).parent
                    folder.mkdir(parents=True, exist_ok=True)
                    no_link(folder)
                    private_directory(folder)

                await asyncio.to_thread(prepare_folder)
            await storage.write(key, data, "audio/wav")
        return "saved"
    except Exception:
        logging.getLogger("pms_api").warning("speech_recording_failed")
        return "failed"


async def current_actor(session, actor):
    return await reload_actor(
        session,
        user_id=actor.id if actor.user else None,
        device_id=actor.id if actor.device else None,
        credential_version=actor.device.credential_version if actor.device else None,
    )


async def save_recording(request, row, data):
    state = await record(request.app.state.storage, row.object_key, data)
    try:
        async with request.app.state.sessions() as session:
            current = await session.get(SpeechRequest, row.id, with_for_update=True)
            if (
                current
                and current.lease_token == row.lease_token
                and current.recording_status == "pending"
                and current.lease_expires_at > now()
            ):
                current.recording_status = state
                await audit(
                    session,
                    None,
                    "speech.recording_" + state,
                    "speech_request",
                    row.id,
                    row.organization_id,
                    department_id=row.department_id,
                    device_id=row.device_id,
                )
                await session.commit()
    except Exception:
        logging.getLogger("pms_api").warning("speech_recording_status_unavailable")


async def finish(request, actor, row, state, result, code, recording):
    settings = request.app.state.settings
    async with request.app.state.sessions() as session:
        current = required(await session.get(SpeechRequest, row.id, with_for_update=True))
        require(
            current.status == "running" and current.lease_token == row.lease_token,
            "speech_lease_lost",
            "Transcription ownership changed",
            409,
        )
        if state == "succeeded":
            require(current.lease_expires_at > now(), "speech_lease_lost", "Transcription lease expired", 409)
            check_expiry(actor)
            principal = await current_actor(session, actor)
            if principal.device:
                require(
                    principal.device.department_id == row.department_id,
                    "scope_changed",
                    "Device scope changed",
                    409,
                )
            else:
                access = await organization_access(
                    session, principal, row.organization_id, "org.processing.execute"
                )
                require(
                    access.department_id is None or access.department_id == row.department_id,
                    "scope_changed",
                    "Staff scope changed",
                    409,
                )
            route = await require_route(
                session,
                principal,
                row.organization_id,
                row.profile_revision_id,
                row.configuration_hash,
                settings,
            )
            allowed(route, settings)
        current.status, current.result, current.error_code = state, result, code
        if recording != "pending":
            current.recording_status = recording
        current.completed_at = now()
        await audit(
            session,
            None,
            "speech." + state,
            "speech_request",
            current.id,
            current.organization_id,
            department_id=current.department_id,
            device_id=current.device_id,
        )
        await session.commit()
        return view(current)


@router.post(BASE + "/transcriptions")
async def submit(
    organization_id: UUID,
    request: Request,
    session: Session,
    actor: Actor,
    request_key: UUID,
    profile_revision_id: UUID,
    configuration_hash: str = Query(pattern=r"^[a-f0-9]{64}$"),
    language: Literal["en", "hi", "auto"] = "auto",
):
    settings = request.app.state.settings
    route = await require_route(
        session, actor, organization_id, profile_revision_id, configuration_hash, settings
    )
    allowed(route, settings)
    require(
        request.headers.get("content-type", "").split(";")[0] == "audio/wav",
        "invalid_audio_type",
        "Send a PCM WAV body with Content-Type audio/wav",
        415,
    )
    data = await request.body()
    duration = wav_info(data, route["audio"]["max_seconds"])
    require(
        len(data) <= route["limits"]["capture_limits"]["max_upload_bytes"],
        "audio_too_large",
        "Audio exceeds the organization upload limit",
        413,
    )
    connection = required(
        await runtime_model(session, UUID(route["audio"]["connection_id"]), ProviderConnection)
    )
    speech_endpoint(connection, settings)
    fingerprint = token_hash(
        canonical(
            {
                "audio": hashlib.sha256(data).hexdigest(),
                "profile": str(profile_revision_id),
                "configuration": configuration_hash,
                "language": language,
            }
        ),
        settings.token_pepper.get_secret_value(),
    )
    await session.get(Organization, organization_id, with_for_update=True)
    existing = await session.scalar(
        select(SpeechRequest).where(
            SpeechRequest.organization_id == organization_id, SpeechRequest.request_key == request_key
        )
    )
    if existing:
        require(
            existing.fingerprint == fingerprint
            and (existing.user_id == actor.id or existing.device_id == actor.id),
            "idempotency_conflict",
            "This request key belongs to another utterance or identity",
            409,
        )
        require(
            existing.expires_at > now(), "speech_result_expired", "Result expired; begin a new utterance", 410
        )
        # A duplicate is also a result read. Recheck its original department after
        # staff/device reassignment, just as the request-status endpoint does.
        await readable(session, actor, organization_id, request_key)
        return view(existing, cached=existing.status == "succeeded")
    pending, stored = (
        await session.execute(
            select(
                func.count().filter(
                    (SpeechRequest.status == "running") | (SpeechRequest.recording_status == "pending")
                ),
                func.coalesce(func.sum(SpeechRequest.byte_size), 0),
            ).where(SpeechRequest.organization_id == organization_id)
        )
    ).one()
    daily_ms = await daily_speech_millis(session, organization_id)
    require(
        pending < settings.speech_concurrency,
        "speech_busy",
        "Speech capacity is busy; nothing was submitted",
        429,
    )
    other_running, other_seconds = await other_audio_usage(session, organization_id)
    require(
        pending + other_running < route["limits"]["usage_limits"]["max_concurrent_jobs"],
        "concurrency_limit",
        "Organization processing capacity reached",
        429,
    )
    require(
        daily_ms / 1000 + other_seconds + duration / 1000
        <= route["limits"]["usage_limits"]["daily_audio_seconds"],
        "daily_usage_limit",
        "Organization daily speech capacity reached",
        429,
    )
    require(
        daily_ms + duration <= settings.speech_daily_seconds * 1000,
        "speech_daily_limit",
        "Daily speech capacity reached",
        429,
    )
    require(
        stored + len(data) <= settings.speech_recording_max_bytes,
        "speech_storage_limit",
        "Speech recording quota reached",
        429,
    )
    check_expiry(actor)
    department = (
        actor.device.department_id
        if actor.device
        else (
            await organization_access(session, actor, organization_id, "org.processing.execute")
        ).department_id
    )
    id, created = uuid4(), now()
    row = SpeechRequest(
        id=id,
        organization_id=organization_id,
        department_id=department,
        user_id=actor.id if actor.user else None,
        device_id=actor.id if actor.device else None,
        request_key=request_key,
        fingerprint=fingerprint,
        profile_revision_id=profile_revision_id,
        configuration_hash=configuration_hash,
        connection_id=connection.id,
        connection_revision=connection.configuration_version,
        status="running",
        byte_size=len(data),
        duration_ms=duration,
        object_key=f"{organization_id}/speech/{id}.wav",
        recording_status="pending",
        lease_token=uuid4(),
        lease_expires_at=created + timedelta(seconds=settings.provider_timeout_seconds + 20),
        created_at=created,
        expires_at=created
        + timedelta(hours=min(settings.speech_retention_days * 24, route["limits"]["media_retention_hours"])),
    )
    key = CredentialVault(settings).decrypt(connection)["api_key"]
    session.add(row)
    await audit(
        session,
        actor,
        "speech.accepted",
        "speech_request",
        id,
        organization_id,
        {"duration_ms": duration},
        department_id=department,
        device_id=row.device_id,
    )
    await session.commit()
    began = time.monotonic()
    recording_task = asyncio.create_task(save_recording(request, row, data))
    request.app.state.speech_tasks.add(recording_task)
    recording_task.add_done_callback(request.app.state.speech_tasks.discard)
    recording = "pending"
    try:
        async with request.app.state.sessions() as admission_check:
            principal = await current_actor(admission_check, actor)
            current_route = await require_route(
                admission_check, principal, organization_id, profile_revision_id, configuration_hash, settings
            )
            allowed(current_route, settings)
        result = await transcribe(request.app.state.llm, settings, connection, key, data, language, id)
        result.update(duration_ms=duration, asr_finalize_ms=round((time.monotonic() - began) * 1000))
        return await finish(request, actor, row, "succeeded", result, None, recording)
    except BaseException as error:
        with anyio.move_on_after(20, shield=True):
            state = (
                "unknown"
                if isinstance(error, asyncio.CancelledError)
                or getattr(error, "code", "") == "speech_submission_unknown"
                else "failed"
            )
            await finish(
                request,
                actor,
                row,
                state,
                None,
                getattr(error, "code", "speech_submission_unknown"),
                recording,
            )
        raise


async def readable(session, actor, org, request_key, media=False):
    await access_for(session, actor, org)
    row = required(
        await session.scalar(
            select(SpeechRequest).where(
                SpeechRequest.organization_id == org, SpeechRequest.request_key == request_key
            )
        )
    )
    if actor.device:
        require(row.device_id == actor.id, "not_found", "Recording not found", 404)
        require(actor.device.department_id == row.department_id, "not_found", "Recording not found", 404)
    else:
        access = await organization_access(
            session, actor, org, "org.media.read" if media else "org.results.read"
        )
        require(
            row.user_id == actor.id or access.role == "org_admin", "not_found", "Recording not found", 404
        )
        require(
            access.department_id is None or access.department_id == row.department_id,
            "not_found",
            "Recording not found",
            404,
        )
    require(row.expires_at > now(), "speech_result_expired", "Recording expired", 410)
    return row


@router.get(BASE + "/requests/{request_key}")
async def get_result(organization_id: UUID, request_key: UUID, session: Session, actor: Actor):
    return view(await readable(session, actor, organization_id, request_key))


@router.get(BASE + "/requests/{request_key}/audio")
async def get_audio(
    organization_id: UUID, request_key: UUID, request: Request, session: Session, actor: Actor
):
    row = await readable(session, actor, organization_id, request_key, media=True)
    require(row.recording_status == "saved", "recording_unavailable", "Audio recording is unavailable", 409)
    data = await request.app.state.storage.read(row.object_key, row.byte_size)
    return Response(content=data, media_type="audio/wav", headers={"Cache-Control": "no-store"})


async def retention_once(sessions, storage):
    async with sessions() as session:
        stale = (
            await session.scalars(
                select(SpeechRequest)
                .where(
                    (SpeechRequest.status == "running") | (SpeechRequest.recording_status == "pending"),
                    SpeechRequest.lease_expires_at <= now(),
                )
                .limit(50)
                .with_for_update(skip_locked=True)
            )
        ).all()
        for row in stale:
            if row.status == "running":
                row.status, row.completed_at, row.error_code = "unknown", now(), "speech_lease_expired"
            if row.recording_status == "pending":
                row.recording_status = "failed"
            await audit(
                session,
                None,
                "speech.lease_recovered",
                "speech_request",
                row.id,
                row.organization_id,
                department_id=row.department_id,
                device_id=row.device_id,
            )
        await session.commit()
    async with sessions() as session:
        expired = (
            await session.scalars(
                select(SpeechRequest)
                .where(SpeechRequest.expires_at <= now(), SpeechRequest.status != "running")
                .limit(25)
                .with_for_update(skip_locked=True)
            )
        ).all()
        for row in expired:
            await storage.delete(row.object_key)
            await session.delete(row)
        await session.commit()


async def retention_loop(sessions, storage):
    while True:
        try:
            await retention_once(sessions, storage)
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.getLogger("pms_api").warning("speech_retention_unavailable")
        await asyncio.sleep(15)
