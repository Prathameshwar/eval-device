import hashlib
import math
from datetime import timedelta
from uuid import UUID, uuid4

import jwt
from fastapi import APIRouter, Request
from fastapi.responses import Response
from sqlalchemy import and_, case, func, or_, select

from pms_api.core.common import AppError, canonical, digest, now, require, required
from pms_api.core.dependencies import Session
from pms_api.database.models import (
    Device,
    Organization,
    ProcessingRun,
    ProfileRevision,
    ProviderConnection,
    TrainingSession,
    User,
)
from pms_api.integrations.contracts import validate_submission
from pms_api.integrations.media import inspect_media
from pms_api.integrations.storage import LocalStorage
from pms_api.modules.common import audit, commit, page, public
from pms_api.modules.configuration import REGISTRY, resolved_configuration
from pms_api.modules.management import Limit
from pms_api.modules.runtime_model_store import runtime_model
from pms_api.modules.schemas import PlaybackAck, RunCreate, RunResult, SubmissionResolution
from pms_api.modules.speech_usage import speech_usage
from pms_api.security.access import (
    Actor,
    Principal,
    device_access,
    organization_access,
    scoped_query,
    scoped_record,
)

router = APIRouter()
TERMINAL = {"succeeded", "failed", "cancelled", "expired"}
CONTENT_TYPES = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "flac": "audio/flac",
    "ogg": "audio/ogg",
    "mp4": "video/mp4",
    "pcm": "application/octet-stream",
}


def run_view(row):
    value = public(
        row,
        exclude={
            "media_manifest",
            "lease_token",
            "effective_settings",
            "request",
            "provider_job_id",
            "usage",
        },
    )
    if row.expires_at <= now():
        value["result"] = None
        value["error"] = None
    value["media_available"] = (
        row.media_expires_at is not None
        and row.media_expires_at > now()
        and row.cleanup_status not in {"succeeded"}
    )
    return value


async def authorized_run(session, actor, run_id, org_id=None, permission="org.results.read", lock=False):
    if actor.device:
        device = await device_access(
            session, actor, True, allow_maintenance=permission in {"org.results.read", "org.media.read"}
        )
        require(org_id in {None, device.organization_id}, "not_found", "Run not found", 404)
        query = select(ProcessingRun).where(
            ProcessingRun.id == run_id,
            ProcessingRun.organization_id == device.organization_id,
            ProcessingRun.device_id == device.id,
        )
        if lock:
            query = query.with_for_update()
        row = await session.scalar(query)
        require(row is not None, "not_found", "Run not found", 404)
        assert row is not None
        # Inactive devices cannot download results even though health/config are allowed.
        return row
    require(org_id is not None, "organization_required", "Organization is required")
    access = await organization_access(session, actor, org_id, permission)
    return await scoped_record(session, ProcessingRun, access, run_id, lock)


async def create_run(session, actor, body: RunCreate, org_id=None):
    require(
        body.operation != "training.interview",
        "training_endpoint_required",
        "Use the training session endpoint",
    )
    if actor.device:
        device = await device_access(session, actor, True)
        require(
            body.device_id in {None, device.id},
            "device_mismatch",
            "Device identity does not match request",
            403,
        )
        require(org_id in {None, device.organization_id}, "not_found", "Organization not found", 404)
        org_id = device.organization_id
    else:
        require(body.device_id is not None, "device_required", "Select a device")
        access = await organization_access(session, actor, org_id, "org.processing.execute")
        if body.playback or body.operation == "audio.playback":
            await organization_access(session, actor, org_id, "org.playback.execute")
        assert body.device_id is not None
        device = await scoped_record(session, Device, access, body.device_id)
        await device_access(session, Principal(device=device), True)
    org = required(await session.get(Organization, org_id, with_for_update=True))
    fingerprint = digest(body.model_dump(mode="json", exclude={"device_id"}))
    existing = await session.scalar(
        select(ProcessingRun).where(
            ProcessingRun.organization_id == org_id,
            ProcessingRun.device_id == device.id,
            ProcessingRun.request_key == body.request_key,
        )
    )
    if existing:
        require(
            existing.request.get("fingerprint") == fingerprint,
            "idempotency_conflict",
            "The request key was used for different content",
            409,
        )
        return existing, False
    config = await resolved_configuration(session, device)
    require(
        config["profile_revision_id"] == str(body.profile_revision_id),
        "revision_mismatch",
        "Request the current published revision",
        409,
    )
    if actor.device:
        require(
            device.applied_profile_revision_id == body.profile_revision_id
            and device.applied_configuration_hash == config["configuration_hash"],
            "configuration_not_applied",
            "Apply and acknowledge the current configuration before submitting work",
            409,
        )
    definition = REGISTRY[body.operation]
    section = config["settings"][definition["section"]]
    require(
        section.get("enabled") and section.get("operation") == body.operation,
        "operation_disabled",
        "This operation is not enabled by the profile",
        409,
    )
    engine = section["engine"]
    mode = section["execution_mode"]
    policy = config["policy"]
    if mode == "local":
        engines = device.capabilities.get("engines", [])
        require(engine in engines, "engine_unavailable", "Device has not advertised this local engine", 409)
    revision = required(await session.get(ProfileRevision, body.profile_revision_id))
    connection_id = getattr(revision, definition["section"] + "_connection_id")
    connection = await runtime_model(session, connection_id, ProviderConnection) if connection_id else None
    if connection:
        validation = connection.validation_results.get(body.operation, {})
        require(
            connection.is_active
            and connection.provider in config["enabled_providers"]
            and (
                getattr(connection, "kind", "legacy_media") != "legacy_media"
                or (
                    validation.get("status") == "valid"
                    and validation.get("configuration_version") == connection.configuration_version
                )
            ),
            "connection_unavailable",
            "Connection must be enabled and validated for this operation",
            409,
        )
    if body.operation == "audio.synthesize":
        require(bool(body.text), "text_required", "Supply text for synthesis")
    else:
        require(body.text is None, "unexpected_text", "This operation does not accept synthesis text")
    validate_submission(engine, body.operation, section, {"text": body.text})
    source = None
    wants_playback = body.playback or body.operation == "audio.playback"
    require(
        not body.playback or body.operation == "audio.synthesize",
        "invalid_playback",
        "Playback can accompany audio synthesis only",
    )
    if body.operation == "audio.playback":
        require(body.source_run_id is not None, "source_required", "Select a successful generated-audio run")
        source = await authorized_run(session, actor, body.source_run_id, org_id, "org.media.read")
        require(
            source.device_id == device.id
            and source.operation == "audio.synthesize"
            and source.status == "succeeded"
            and source.media_expires_at
            and source.media_expires_at > now()
            and source.cleanup_status != "succeeded",
            "source_unavailable",
            "Generated audio is unavailable for this device",
            409,
        )
    else:
        require(body.source_run_id is None, "unexpected_source", "Only playback accepts a source run")
    input_required = mode == "cloud" and body.operation in {"audio.transcribe", "video.labels"}
    require(
        section.get("engine") != "azure_openai_whisper",
        "interactive_speech_required",
        "Use the interactive speech endpoint for Azure OpenAI Whisper",
    )
    require(
        not input_required or body.media_format is not None,
        "media_format_required",
        "Select an input media format",
    )
    require(
        body.media_format is None or input_required,
        "unexpected_media",
        "Local-only and synthesis operations do not upload raw media",
    )
    unit = (
        "tts_characters"
        if body.operation == "audio.synthesize"
        else "video_seconds"
        if body.operation.startswith("video.")
        else "audio_seconds"
    )
    maximum = policy["capture_limits"][
        "max_video_seconds" if unit == "video_seconds" else "max_audio_seconds"
    ]
    reserved = len(body.text) if body.text else math.ceil(body.duration_seconds or maximum)
    if body.duration_seconds:
        require(body.duration_seconds <= maximum, "capture_limit", "Requested duration exceeds policy")
    concurrent = await session.scalar(
        select(func.count())
        .select_from(ProcessingRun)
        .where(ProcessingRun.organization_id == org_id, ProcessingRun.status.not_in(TERMINAL))
    )
    concurrent += (
        await session.scalar(
            select(func.count())
            .select_from(TrainingSession)
            .where(
                TrainingSession.organization_id == org_id,
                TrainingSession.status.in_(("authorized", "active")),
                TrainingSession.expires_at > now(),
            )
        )
    ) or 0
    speech_running, speech_seconds = await speech_usage(session, org_id)
    require(
        concurrent + speech_running < policy["usage_limits"]["max_concurrent_jobs"],
        "concurrency_limit",
        "Organization concurrency limit reached",
        429,
    )
    day = now().replace(hour=0, minute=0, second=0, microsecond=0)
    usage_rows = (
        await session.scalars(
            select(ProcessingRun.usage).where(
                ProcessingRun.organization_id == org_id, ProcessingRun.created_at >= day
            )
        )
    ).all()
    total = sum(u.get("reserved", 0) for u in usage_rows if u.get("unit") == unit)
    if unit == "audio_seconds":
        total += speech_seconds
    training_column = (
        TrainingSession.tts_budget if unit == "tts_characters" else TrainingSession.duration_seconds
    )
    total += (
        await session.scalar(
            select(func.sum(training_column)).where(
                TrainingSession.organization_id == org_id, TrainingSession.created_at >= day
            )
        )
    ) or 0
    require(
        total + reserved <= policy["usage_limits"]["daily_" + unit],
        "daily_usage_limit",
        "Organization daily usage limit reached",
        429,
    )
    timestamp = now()
    run_id = uuid4()
    media_expiry = timestamp + timedelta(hours=policy["media_retention_hours"])
    manifest: list[dict] = []
    if input_required:
        manifest = [
            {
                "role": "input",
                "storage": "platform",
                "key": f"organizations/{org_id}/runs/{run_id}/input.{body.media_format}",
                "format": body.media_format,
                "expires_at": media_expiry.isoformat(),
                "cleanup_status": "pending",
            }
        ]
    if body.operation == "audio.synthesize" and mode == "cloud":
        extension = section.get("format", "mp3")
        manifest = [
            {
                "role": "output",
                "storage": "platform",
                "key": f"organizations/{org_id}/runs/{run_id}/output.{extension}",
                "format": extension,
                "expires_at": media_expiry.isoformat(),
                "cleanup_status": "pending",
            }
        ]
    if source:
        output = next(
            (m for m in source.media_manifest if m["role"] == "output" and m["storage"] == "platform"), None
        )
        require(output is not None, "source_unavailable", "Source run has no generated audio", 409)
        assert output is not None
        media_expiry = min(media_expiry, source.media_expires_at)
        manifest = [
            {**output, "shared": True, "cleanup_status": "pending", "expires_at": media_expiry.isoformat()}
        ]
    status = "awaiting_device" if mode == "local" else "awaiting_upload" if input_required else "queued"
    request = {
        "fingerprint": fingerprint,
        "text": body.text,
        "format": body.media_format,
        "duration_seconds": body.duration_seconds,
        "playback": wants_playback,
        "source_run_id": str(body.source_run_id) if body.source_run_id else None,
    }
    effective = {
        "configuration_hash": config["configuration_hash"],
        "section": section,
        "policy": policy,
        "connection": {
            "settings": connection.settings,
            "configuration_version": connection.configuration_version,
            "provider": connection.provider,
        }
        if connection
        else None,
    }
    row = ProcessingRun(
        id=run_id,
        organization_id=org_id,
        device_id=device.id,
        department_id=device.department_id,
        profile_revision_id=revision.id,
        requested_by=actor.id if actor.user else None,
        capture_id=body.capture_id,
        request_key=body.request_key,
        operation=body.operation,
        execution_mode=mode,
        engine=engine,
        connection_id=connection_id,
        effective_settings=effective,
        request=request,
        status=status,
        created_at=timestamp,
        captured_at=body.captured_at,
        deadline_at=min(media_expiry, timestamp + timedelta(hours=1)),
        expires_at=timestamp + timedelta(days=policy["result_retention_days"]),
        next_attempt_at=timestamp if status == "queued" else None,
        usage={"unit": unit, "reserved": reserved, "accounting_date": day.date().isoformat()},
        media_manifest=manifest,
        media_expires_at=media_expiry if manifest else None,
        cleanup_status="pending" if manifest else "not_required",
        cleanup_next_attempt_at=media_expiry if manifest else None,
        playback_status="pending" if wants_playback else "not_requested",
        playback_expires_at=min(media_expiry, timestamp + timedelta(minutes=10)) if wants_playback else None,
    )
    session.add(row)
    device.last_activity_at = timestamp
    org.last_activity_at = timestamp
    await audit(
        session,
        actor,
        "processing.requested",
        "processing_run",
        run_id,
        org_id,
        {"operation": body.operation},
        category="operational",
        device_id=device.id,
        department_id=device.department_id,
    )
    await commit(session, row)
    return row, True


@router.post("/organizations/{organization_id}/runs", status_code=202, tags=["Processing"])
async def submit_run(organization_id: UUID, body: RunCreate, session: Session, actor: Actor):
    row, created = await create_run(session, actor, body, organization_id)
    return {"run": run_view(row), "created": created}


@router.post("/device/runs", status_code=202, tags=["Device agent"])
async def device_submit(body: RunCreate, session: Session, actor: Actor):
    require(actor.device is not None, "device_identity_required", "Device identity required", 403)
    row, created = await create_run(session, actor, body)
    return {"run": run_view(row), "created": created}


@router.get("/organizations/{organization_id}/runs", tags=["Processing"])
async def runs(
    organization_id: UUID, session: Session, actor: Actor, limit: Limit = 50, cursor: UUID | None = None
):
    access = await organization_access(session, actor, organization_id, "org.results.read")
    rows, next_cursor = await page(
        session,
        scoped_query(ProcessingRun, access).where(ProcessingRun.expires_at > now()),
        ProcessingRun,
        limit,
        cursor,
    )
    return {"items": [run_view(r) for r in rows], "next_cursor": next_cursor}


@router.get("/organizations/{organization_id}/runs/{run_id}", tags=["Processing"])
async def get_run(organization_id: UUID, run_id: UUID, session: Session, actor: Actor):
    return run_view(await authorized_run(session, actor, run_id, organization_id))


@router.get("/device/runs", tags=["Device agent"])
async def work(session: Session, actor: Actor):
    device = await device_access(session, actor, True, allow_maintenance=True)
    actionable = or_(
        ProcessingRun.status.in_(["awaiting_device", "awaiting_upload", "running"]),
        and_(
            ProcessingRun.playback_status.in_(["pending", "playing"]),
            ProcessingRun.playback_expires_at > now(),
        ),
    )
    rows = (
        await session.scalars(
            select(ProcessingRun)
            .where(
                ProcessingRun.organization_id == device.organization_id,
                ProcessingRun.device_id == device.id,
                ProcessingRun.deadline_at > now(),
                ProcessingRun.status.in_(["awaiting_device", "awaiting_upload", "running", "succeeded"]),
                ProcessingRun.expires_at > now(),
            )
            .order_by(
                case((actionable, 0), else_=1),
                case((actionable, ProcessingRun.created_at)).asc(),
                ProcessingRun.created_at.desc(),
                ProcessingRun.id,
            )
            .limit(50)
        )
    ).all()
    return {
        "items": [
            {
                **run_view(r),
                "input": r.request.get("text") if r.execution_mode == "local" else None,
                "settings": r.effective_settings["section"],
            }
            for r in rows
        ]
    }


@router.get("/device/runs/{run_id}", tags=["Device agent"])
async def device_run(run_id: UUID, session: Session, actor: Actor):
    return run_view(await authorized_run(session, actor, run_id))


async def cancel_run(session, actor, row):
    if row.status in TERMINAL:
        return row
    row.status = "cancelled"
    row.completed_at = now()
    if row.playback_status in {"pending", "playing", "unknown"}:
        row.playback_status = "cancelled"
    if row.media_manifest:
        row.cleanup_status = "pending"
        row.cleanup_next_attempt_at = now()
    await audit(
        session,
        actor,
        "processing.cancelled",
        "processing_run",
        row.id,
        row.organization_id,
        category="operational",
        device_id=row.device_id,
        department_id=row.department_id,
    )
    await commit(session, row)
    return row


@router.post("/organizations/{organization_id}/runs/{run_id}/cancel", tags=["Processing"])
async def cancel(organization_id: UUID, run_id: UUID, session: Session, actor: Actor):
    row = await authorized_run(session, actor, run_id, organization_id, "org.processing.execute", True)
    return run_view(await cancel_run(session, actor, row))


@router.post("/device/runs/{run_id}/result", tags=["Device agent"])
async def local_result(run_id: UUID, body: RunResult, session: Session, actor: Actor):
    row = await authorized_run(session, actor, run_id, permission="org.processing.execute", lock=True)
    require(
        row.execution_mode == "local",
        "cloud_result_forbidden",
        "Cloud results are written by the worker",
        403,
    )
    require(
        row.status in {"awaiting_device", "running"} and row.deadline_at > now(),
        "run_closed",
        "Run is closed or expired",
        409,
    )
    require(
        len(canonical(body.result or {}).encode()) <= 1048576,
        "result_too_large",
        "Result exceeds storage limit",
        413,
    )
    row.started_at = row.started_at or now()
    row.completed_at = now()
    row.status = body.status
    row.result = body.result
    row.error = {"code": body.error_code} if body.error_code else None
    await audit(
        session,
        actor,
        "processing.result_received",
        "processing_run",
        row.id,
        row.organization_id,
        {"status": body.status},
        category="operational",
        device_id=row.device_id,
        department_id=row.department_id,
    )
    await commit(session, row)
    return run_view(row)


@router.post("/device/runs/{run_id}/cancel", tags=["Device agent"])
async def device_cancel(run_id: UUID, session: Session, actor: Actor):
    await device_access(session, actor, True)
    row = await authorized_run(session, actor, run_id, permission="org.processing.execute", lock=True)
    return run_view(await cancel_run(session, actor, row))


@router.post("/device/runs/{run_id}/playback", tags=["Device agent"])
async def playback(run_id: UUID, body: PlaybackAck, session: Session, actor: Actor):
    row = await authorized_run(session, actor, run_id, permission="org.playback.execute", lock=True)
    require(
        row.status == "succeeded"
        and row.playback_status in {"pending", "playing", "unknown"}
        and row.playback_expires_at
        and row.playback_expires_at > now(),
        "playback_unavailable",
        "Playback is unavailable or expired",
        409,
    )
    require(
        row.playback_status != "unknown" or body.status in {"succeeded", "failed"},
        "playback_uncertain",
        "Uncertain playback must not be replayed automatically",
        409,
    )
    row.playback_status = body.status
    await audit(
        session,
        actor,
        "processing.playback_acknowledged",
        "processing_run",
        row.id,
        row.organization_id,
        {"status": body.status},
        category="operational",
        device_id=row.device_id,
        department_id=row.department_id,
    )
    if body.status in {"succeeded", "failed"}:
        row.playback_acknowledged_at = now()
    await commit(session, row)
    return run_view(row)


async def media_url(request, session, actor, row, index, method):
    require(
        row.expires_at > now() and row.media_expires_at and row.media_expires_at > now(),
        "media_expired",
        "Media is expired",
        410,
    )
    require(0 <= index < len(row.media_manifest), "not_found", "Media not found", 404)
    media = row.media_manifest[index]
    require(media.get("storage") == "platform", "not_found", "Media not found", 404)
    require(
        method != "PUT" or row.status == "awaiting_upload" and media["role"] == "input",
        "upload_closed",
        "Upload is unavailable",
        409,
    )
    require(
        method != "GET"
        or row.status == "succeeded"
        or (actor.device and row.operation == "audio.playback" and row.status == "awaiting_device"),
        "result_unavailable",
        "Processing result is not available",
        409,
    )
    settings = request.app.state.settings
    storage = request.app.state.storage
    seconds = max(1, min(60, int((row.media_expires_at - now()).total_seconds())))
    content_type = CONTENT_TYPES[media["format"]]
    if isinstance(storage, LocalStorage):
        token = jwt.encode(
            {
                "run": str(row.id),
                "index": index,
                "method": method,
                "actor": str(actor.id),
                "kind": "user" if actor.user else "device",
                "org": str(row.organization_id),
                "exp": int(now().timestamp()) + seconds,
                "credential_version": actor.device.credential_version if actor.device else None,
                "purpose": "media",
            },
            settings.media_signing_key.get_secret_value(),
            algorithm="HS256",
        )
        url = settings.public_base_url + "/api/v1/media/local/" + token
    else:
        url = await storage.signed_url(media["key"], method, seconds, content_type)
    return {
        "url": url,
        "method": method,
        "expires_in": seconds,
        "headers": {"Content-Type": content_type} if method == "PUT" else {},
    }


@router.get("/organizations/{organization_id}/runs/{run_id}/media", tags=["Media"])
async def media_directory(organization_id: UUID, run_id: UUID, session: Session, actor: Actor):
    row = await authorized_run(session, actor, run_id, organization_id, "org.media.read")
    require(
        row.expires_at > now() and row.media_expires_at and row.media_expires_at > now(),
        "media_expired",
        "Media is expired",
        410,
    )
    require(
        row.status == "succeeded" and row.cleanup_status != "succeeded",
        "result_unavailable",
        "Media is unavailable",
        409,
    )
    return {
        "items": [
            {
                "index": index,
                "role": media["role"],
                "format": media["format"],
                "content_type": CONTENT_TYPES[media["format"]],
            }
            for index, media in enumerate(row.media_manifest)
            if media.get("storage") == "platform"
        ]
    }


@router.post("/organizations/{organization_id}/runs/{run_id}/media/{index}/access", tags=["Media"])
async def access_media(
    organization_id: UUID,
    run_id: UUID,
    index: int,
    request: Request,
    session: Session,
    actor: Actor,
    method: str = "GET",
):
    require(method in {"GET", "PUT"}, "invalid_method", "Use GET or PUT")
    row = await authorized_run(
        session,
        actor,
        run_id,
        organization_id,
        "org.media.read" if method == "GET" else "org.processing.execute",
    )
    return await media_url(request, session, actor, row, index, method)


@router.post("/device/runs/{run_id}/media/{index}/access", tags=["Media"])
async def device_media(
    run_id: UUID, index: int, request: Request, session: Session, actor: Actor, method: str = "GET"
):
    require(method in {"GET", "PUT"}, "invalid_method", "Use GET or PUT")
    row = await authorized_run(
        session, actor, run_id, permission="org.media.read" if method == "GET" else "org.processing.execute"
    )
    return await media_url(request, session, actor, row, index, method)


@router.api_route("/media/local/{token}", methods=["GET", "PUT"], include_in_schema=False)
async def local_media(token: str, request: Request, session: Session):
    settings = request.app.state.settings
    require(
        settings.storage_backend == "local" and settings.environment in {"local", "test"},
        "not_found",
        "Not found",
        404,
    )
    try:
        claims = jwt.decode(
            token,
            settings.media_signing_key.get_secret_value(),
            algorithms=["HS256"],
            options={"require": ["exp", "run", "index", "method", "actor", "kind", "org", "purpose"]},
        )
        require(
            claims["purpose"] == "media" and claims["method"] == request.method,
            "invalid_media_token",
            "Invalid media token",
            403,
        )
        user = await session.get(User, UUID(claims["actor"])) if claims["kind"] == "user" else None
        device = await session.get(Device, UUID(claims["actor"])) if claims["kind"] == "device" else None
        require(
            (user and user.is_active) or (device and device.credential_hash),
            "identity_inactive",
            "Media identity is inactive",
            403,
        )
        require(
            not device or device.credential_version == claims.get("credential_version"),
            "invalid_media_token",
            "Device credential changed",
            403,
        )
        actor = Principal(user=user, device=device)
        row = await authorized_run(
            session,
            actor,
            UUID(claims["run"]),
            UUID(claims["org"]),
            "org.media.read" if request.method == "GET" else "org.processing.execute",
            False,
        )
        index = claims["index"]
        require(
            isinstance(index, int) and 0 <= index < len(row.media_manifest),
            "not_found",
            "Media not found",
            404,
        )
    except (jwt.InvalidTokenError, ValueError, KeyError) as error:
        raise AppError(403, "invalid_media_token", "Invalid or expired media token") from error
    media = row.media_manifest[index]
    require(row.media_expires_at and row.media_expires_at > now(), "media_expired", "Media expired", 410)
    storage = LocalStorage(settings)
    max_bytes = row.effective_settings["policy"]["capture_limits"]["max_upload_bytes"]
    await session.commit()  # Storage I/O must not hold row locks.
    if request.method == "PUT":
        require(
            row.status == "awaiting_upload" and media["role"] == "input",
            "upload_closed",
            "Upload is unavailable",
            409,
        )
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            require(len(data) <= max_bytes, "media_too_large", "Media exceeds policy", 413)
        await storage.write(media["key"], bytes(data), CONTENT_TYPES[media["format"]])
        return {"uploaded": len(data)}
    require(
        row.status == "succeeded"
        or (actor.device and row.operation == "audio.playback" and row.status == "awaiting_device"),
        "result_unavailable",
        "Result unavailable",
        409,
    )
    return Response(
        await storage.read(media["key"], max_bytes),
        media_type=CONTENT_TYPES[media["format"]],
        headers={"Cache-Control": "no-store"},
    )


async def finalize_upload(request, session, actor, row):
    require(
        row.status == "awaiting_upload" and row.deadline_at > now(),
        "upload_closed",
        "Run is no longer awaiting upload",
        409,
    )
    reference = (
        actor.user.id if actor.user else None,
        actor.device.id if actor.device else None,
        actor.device.credential_version if actor.device else None,
    )
    run_id, org_id = row.id, row.organization_id
    media = next(m for m in row.media_manifest if m["role"] == "input")
    await session.commit()
    data = await request.app.state.storage.read(
        media["key"], row.effective_settings["policy"]["capture_limits"]["max_upload_bytes"]
    )
    info = await inspect_media(
        data, media["format"], request.app.state.settings, row.effective_settings["policy"]
    )
    require(
        (row.operation == "video.labels" and info["has_video"] and not info["has_audio"])
        or (row.operation == "audio.transcribe" and info["has_audio"] and not info["has_video"]),
        "media_modality_mismatch",
        "Upload only the configured modality; video-only processing must omit microphone audio",
    )
    require(
        info["duration_seconds"] <= row.usage["reserved"] + 0.25,
        "reserved_usage_exceeded",
        "Media duration exceeds the reserved duration",
    )
    from pms_api.security.access import reload_actor

    actor = await reload_actor(session, *reference)
    session.expire(row)
    row = await authorized_run(session, actor, run_id, org_id, "org.processing.execute", True)
    require(
        row.status == "awaiting_upload" and row.deadline_at > now(),
        "upload_closed",
        "Upload closed during validation",
        409,
    )
    row.status = "queued"
    row.next_attempt_at = now()
    row.usage = {**row.usage, "actual": info["duration_seconds"]}
    row.media_manifest = [
        {
            **m,
            **(
                {"verified": True, "size": info["size"], "sha256": hashlib.sha256(data).hexdigest()}
                if m["role"] == "input"
                else {}
            ),
        }
        for m in row.media_manifest
    ]
    await commit(session, row)
    return run_view(row)


@router.post("/organizations/{organization_id}/runs/{run_id}/upload-complete", tags=["Media"])
async def upload_complete(
    organization_id: UUID, run_id: UUID, request: Request, session: Session, actor: Actor
):
    row = await authorized_run(session, actor, run_id, organization_id, "org.processing.execute", True)
    return await finalize_upload(request, session, actor, row)


@router.post("/device/runs/{run_id}/upload-complete", tags=["Media"])
async def device_upload_complete(run_id: UUID, request: Request, session: Session, actor: Actor):
    row = await authorized_run(session, actor, run_id, permission="org.processing.execute", lock=True)
    return await finalize_upload(request, session, actor, row)


@router.post("/organizations/{organization_id}/runs/{run_id}/resolve-submission", tags=["Processing"])
async def resolve_submission(
    organization_id: UUID, run_id: UUID, body: SubmissionResolution, session: Session, actor: Actor
):
    await organization_access(session, actor, organization_id, "org.settings.manage")
    row = await authorized_run(session, actor, run_id, organization_id, "org.processing.execute", True)
    require(
        row.provider_submission_status in {"submitting", "unknown"},
        "submission_resolved",
        "Submission is already resolved",
        409,
    )
    require(
        row.lease_expires_at is None or row.lease_expires_at <= now(),
        "run_leased",
        "Wait for the current worker lease to finish",
        409,
    )
    require(
        body.outcome != "job_found" or body.provider_job_id is not None,
        "job_required",
        "Supply the verified provider job identifier",
    )
    if body.outcome == "job_found":
        require(
            row.engine in {"aws_transcribe", "aws_rekognition", "azure_video_indexer"},
            "synchronous_operation",
            "This operation has no recoverable provider job",
        )
        row.provider_job_id = body.provider_job_id
        row.provider_submission_status = "submitted"
        row.next_attempt_at = now()
    else:
        row.provider_submission_status = "not_submitted" if body.outcome == "not_created" else "submitted"
        row.usage = {**row.usage, "provider_complete": True}
        if row.status not in TERMINAL:
            row.status = "failed"
            row.completed_at = now()
        row.error = {"code": "operator_resolved_without_result"}
        if row.media_manifest:
            row.cleanup_next_attempt_at = now()
    await audit(
        session,
        actor,
        "processing.submission_resolved",
        "processing_run",
        row.id,
        organization_id,
        {"outcome": body.outcome, "reason": body.reason},
        device_id=row.device_id,
        department_id=row.department_id,
    )
    await commit(session, row)
    return run_view(row)
