"""Short-lived device inference grants. The API never connects to a GPU gateway."""

from datetime import timedelta

import jwt
from fastapi import APIRouter, Request
from pydantic import ValidationError
from training_contracts.inference import ISSUER, PATHS, Binding, GrantRequest

from pms_api.core.common import now, require
from pms_api.core.dependencies import Session
from pms_api.modules.common import audit, commit
from pms_api.modules.model_routing import effective_route
from pms_api.modules.patient_conversations import owned, validate_execution
from pms_api.modules.processing import authorized_run
from pms_api.modules.training import signing_key
from pms_api.security.access import Actor, device_access

router = APIRouter(tags=["Device inference"])


def binding_for(device):
    try:
        return Binding.model_validate(device.details.get("inference"))
    except ValidationError:
        require(False, "inference_not_configured", "Configure this device's inference host", 409)
        raise AssertionError("unreachable") from None


@router.get("/device/inference")
async def binding(session: Session, actor: Actor):
    device = await device_access(session, actor, True)
    return binding_for(device).model_dump(mode="json")


def allow_operation(body, target, route):
    kind = PATHS[body.path]
    require(
        body.method == ("GET" if kind in {"metadata", "audio", "video"} else "POST"),
        "invalid_request",
        "Invalid inference method",
        422,
    )
    if kind in {"llm", "inspect"}:
        chosen = route["llm"]
        allowed = chosen["mode"] == "local" and chosen["model"] == body.model
    elif kind in {"asr", "audio"}:
        chosen = route["audio"]
        allowed = chosen.get("enabled") and chosen["mode"] == "local" and chosen["model"] == body.model
    elif kind == "tts":
        output = route["platform_media"]["audio_output"]["settings"]
        allowed = (
            output.get("enabled")
            and output.get("execution_mode", output.get("mode")) == "local"
            and body.voice in target.tts_voices
        )
    elif kind == "video":
        video = route["platform_media"]["video"]["settings"]
        allowed = target.video_transport and video.get("enabled")
        if body.model is not None:
            allowed = (
                allowed
                and body.model == "opencv_motion"
                and video.get("engine") == "opencv_motion"
                and video.get("execution_mode", video.get("mode")) == "local"
                and video.get("operation") == "video.motion"
                and body.processing_run_id is not None
            )
    else:
        allowed = True
    require(allowed, "inference_not_permitted", "Operation does not match the assigned model", 403)


@router.post("/device/inference/grants")
async def grant(body: GrantRequest, request: Request, session: Session, actor: Actor):
    device = await device_access(session, actor, True)
    target = binding_for(device)
    require(
        body.host_id == target.host_id and body.origin == target.origin,
        "inference_host_changed",
        "Use the configured inference host",
        403,
    )
    route = await effective_route(session, actor, device.organization_id, request.app.state.settings)
    allow_operation(body, target, route)
    stamp = now()
    deadline = stamp + timedelta(seconds=180)
    processing_run = None
    if body.processing_run_id is not None:
        require(
            PATHS[body.path] == "video" and body.model == "opencv_motion",
            "invalid_request",
            "A processing run is only used for video processing",
            422,
        )
        processing_run = await authorized_run(
            session, actor, body.processing_run_id, permission="org.processing.execute", lock=True
        )
        require(
            processing_run.status == "awaiting_device"
            and processing_run.execution_mode == "local"
            and processing_run.operation == "video.motion"
            and processing_run.engine == body.model
            and str(processing_run.profile_revision_id) == route["profile_revision_id"]
            and processing_run.deadline_at > stamp,
            "processing_unavailable",
            "The processing run is not available for execution",
            409,
        )
        deadline = min(deadline, processing_run.deadline_at)
    if PATHS[body.path] not in {"metadata", "inspect", "status"}:
        require(body.conversation_id is not None, "conversation_required", "Begin a conversation first", 409)
        row = await owned(session, actor, device.organization_id, body.conversation_id)
        context = await validate_execution(session, actor, row, request.app.state.settings)
        deadline = min(deadline, context.expires_at)
        if row.assigned_session_id:
            from pms_api.database.models import PracticeSession

            assignment = await session.get(PracticeSession, row.assigned_session_id)
            require(
                assignment is not None and assignment.started_at is not None,
                "session_not_active",
                "Assigned session is not active",
                409,
            )
            assert assignment is not None and assignment.started_at is not None
            deadline = min(
                deadline,
                assignment.expires_at,
                assignment.started_at + timedelta(seconds=assignment.duration_seconds),
            )
    expiry = min(stamp + timedelta(seconds=30), deadline)
    claims = {
        "iss": ISSUER,
        "aud": str(target.host_id),
        "sub": str(device.id),
        "org": str(device.organization_id),
        "jti": str(body.request_id),
        "iat": int(stamp.timestamp()),
        "nbf": int(stamp.timestamp()),
        "exp": int(expiry.timestamp()),
        "deadline": int(deadline.timestamp()),
        "method": body.method,
        "path": body.path,
        "sha256": body.body_sha256,
        "model": body.model,
        "voice": body.voice,
        "conversation": str(body.conversation_id) if body.conversation_id else None,
        "max_tokens": route["llm"]["max_tokens"],
        "max_audio_seconds": min(30, route["audio"]["max_seconds"]),
        "video_operation": "video.motion" if processing_run else None,
        "processing_run_id": str(processing_run.id) if processing_run else None,
        "max_video_seconds": min(
            30,
            route["limits"]["capture_limits"]["max_video_seconds"],
            processing_run.usage["reserved"] if processing_run else 30,
        ),
    }
    encoded = jwt.encode(claims, signing_key(request), algorithm="EdDSA")
    if processing_run:
        # A run reserves usage once and can authorize only one external execution.
        processing_run.status = "running"
        processing_run.started_at = stamp
        await audit(
            session,
            actor,
            "processing.remote_authorized",
            "processing_run",
            processing_run.id,
            device.organization_id,
            {"request_id": str(body.request_id)},
            category="operational",
            device_id=device.id,
            department_id=device.department_id,
        )
        await commit(session, processing_run)
    return {
        "grant": encoded,
        "expires_at": expiry.isoformat(),
        "request_id": str(body.request_id),
    }
