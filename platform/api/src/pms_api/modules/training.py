"""Organization-scoped patient interview authorizations. Media never passes through this API."""

from datetime import timedelta
from uuid import UUID, uuid4

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import APIRouter, Request
from sqlalchemy import and_, case, func, select, update
from training_contracts import (
    Approval,
    Feedback,
    SessionCreate,
    SessionResult,
    fingerprint,
)
from training_contracts.clinical_cases import parse_runtime

from pms_api.core.common import now, require, required
from pms_api.core.dependencies import Session
from pms_api.database.models import (
    Device,
    Membership,
    Organization,
    PracticeSession,
    ProcessingRun,
    TenantScenarioDefault,
    TrainingScenario,
    TrainingSession,
    User,
)
from pms_api.modules.common import audit, commit, directory_page, public
from pms_api.modules.configuration import resolved_configuration
from pms_api.modules.management import Limit
from pms_api.modules.scenarios import require_runtime, reviewer_access
from pms_api.modules.speech_usage import speech_usage
from pms_api.security.access import (
    Actor,
    Principal,
    device_access,
    organization_access,
    reload_actor,
    scoped_query,
    scoped_record,
)

router = APIRouter(tags=["Training"])
ACTIVE = ("authorized", "active")


def signing_key(request: Request):
    path = request.app.state.settings.training_key_file
    require(
        path is not None and path.is_file(),
        "training_not_configured",
        "Configure the training signing key",
        503,
    )
    try:
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    except (OSError, ValueError, TypeError):
        require(False, "training_key_invalid", "Training signing key is unavailable", 503)
        raise AssertionError("unreachable") from None
    require(
        isinstance(key, Ed25519PrivateKey),
        "training_key_invalid",
        "Training signing key must be Ed25519",
        503,
    )
    return key


@router.get("/training/verification-key")
async def verification_key(request: Request):
    key = (
        signing_key(request)
        .public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    )
    return {"algorithm": "EdDSA", "issuer": "pms-training-v1", "public_key": key.decode()}


async def scenario_row(session, organization_id, scenario_id, lock=False):
    query = select(TrainingScenario).where(
        TrainingScenario.organization_id == organization_id, TrainingScenario.id == scenario_id
    )
    if lock:
        query = query.with_for_update()
    return required(await session.scalar(query))


@router.post("/organizations/{organization_id}/training/scenarios/{scenario_id}/approve")
async def approve_scenario(
    organization_id: UUID, scenario_id: UUID, body: Approval, actor: Actor, session: Session
):
    await reviewer_access(session, actor, organization_id, lock=True)
    row = await scenario_row(session, organization_id, scenario_id, True)
    await reviewer_access(session, actor, organization_id, lock=True)
    require(
        row.created_by != actor.id,
        "reviewer_is_author",
        "A different reviewer must approve this scenario",
        403,
    )
    require_runtime(row.document)
    require(row.approved_at is None, "already_approved", "Scenario version is already approved", 409)
    row.approved_by, row.approved_at, row.approval = actor.id, now(), body.model_dump()
    await audit(session, actor, "training.scenario.approved", "training_scenario", row.id, organization_id)
    await commit(session, row)
    return {"id": row.id, "approved": True}


@router.post("/organizations/{organization_id}/training/scenarios/{scenario_id}/retire")
async def retire_scenario(organization_id: UUID, scenario_id: UUID, actor: Actor, session: Session):
    await reviewer_access(session, actor, organization_id, lock=True)
    row = await scenario_row(session, organization_id, scenario_id, True)
    await reviewer_access(session, actor, organization_id, lock=True)
    if row.is_active:
        default = await session.get(TenantScenarioDefault, organization_id)
        require(
            default is None or default.scenario_id != row.id,
            "scenario_is_default",
            "Choose another Practice default before retiring this scenario",
            409,
        )
        row.is_active = False
        await audit(session, actor, "training.scenario.retired", "training_scenario", row.id, organization_id)
        await commit(session)
    return {"id": row.id, "is_active": False}


async def participant(session, organization_id, user_id, department_id):
    user = required(await session.get(User, user_id, populate_existing=True))
    row = await session.scalar(
        select(Membership)
        .where(
            Membership.organization_id == organization_id,
            Membership.user_id == user_id,
            Membership.is_active.is_(True),
            Membership.invitation_status == "accepted",
        )
        .execution_options(populate_existing=True)
    )
    require(
        user.is_active and row is not None and row.department_id in {None, department_id},
        "participant_unavailable",
        "Participant is not active in the device scope",
        403,
    )


async def configuration(session, device):
    await device_access(session, Principal(device=device), True)
    config = await resolved_configuration(session, device)
    part = config["settings"]["audio_input"]
    speech = config["settings"]["audio_output"]
    conversation = config["settings"].get("conversation", {})
    llm = config["connections"].get("llm", {})
    legacy = part.get("operation") == "training.interview" and part.get("engine") == "patient_interview_v1"
    selected_models = (
        part.get("operation") == "audio.transcribe"
        and part.get("engine") == "local_whisper"
        and speech.get("enabled")
        and speech.get("execution_mode") == "local"
        and speech.get("engine") == "espeak_ng"
        and conversation.get("enabled")
        and conversation.get("execution_mode") == "local"
        and llm.get("is_active")
        and llm.get("provider") == "local_llama_cpp"
    )
    require(
        config["profile_revision_id"]
        and part.get("enabled")
        and part.get("execution_mode") == "local"
        and (legacy or selected_models),
        "training_profile_required",
        "Configure active local conversation, Whisper speech recognition and eSpeak speech output models",
        409,
    )
    require(
        "patient_interview_v1" in device.capabilities.get("engines", []),
        "training_agent_required",
        "Device must advertise the patient interview agent",
        409,
    )
    return config


async def expire_sessions(session, organization_id):
    await session.execute(
        update(TrainingSession)
        .where(
            TrainingSession.organization_id == organization_id,
            TrainingSession.status.in_(ACTIVE),
            TrainingSession.expires_at <= now(),
        )
        .values(status="expired", ended_at=now())
    )


def session_view(row):
    value = public(row, exclude={"fingerprint", "device_credential_version"})
    if row.expires_at <= now() and row.status in ACTIVE:
        value["status"] = "expired"
    if row.results_expires_at <= now():
        value["result"] = value["feedback"] = None
    return value


@router.post("/organizations/{organization_id}/training/sessions", status_code=201)
async def create_session(
    organization_id: UUID, body: SessionCreate, request: Request, actor: Actor, session: Session
):
    signing_key(request)
    access = await organization_access(session, actor, organization_id, "org.processing.execute")
    await organization_access(session, actor, organization_id, "org.playback.execute")
    instructor_access = await organization_access(session, actor, organization_id, "org.training.instruct")
    await session.get(Organization, organization_id, with_for_update=True)
    actor = await reload_actor(session, user_id=actor.id)
    access = await organization_access(session, actor, organization_id, "org.processing.execute")
    await organization_access(session, actor, organization_id, "org.playback.execute")
    instructor_access = await organization_access(session, actor, organization_id, "org.training.instruct")
    device = await scoped_record(session, Device, access, body.device_id)
    queued_practice = await session.scalar(
        select(PracticeSession.id).where(
            PracticeSession.device_id == device.id,
            PracticeSession.status.in_(("active", "stopping")),
            PracticeSession.lease_until > now(),
        )
    )
    require(queued_practice is None, "device_busy", "Finish the device's current Practice session first", 409)
    require(
        instructor_access.department_id in {None, device.department_id},
        "scope_unavailable",
        "Instructor is outside the device department",
        403,
    )
    config = await configuration(session, device)
    await participant(session, organization_id, body.learner_id, device.department_id)
    case = await scenario_row(session, organization_id, body.scenario_id)
    runtime = require_runtime(case.document)
    require(
        case.is_active and case.approved_at,
        "scenario_not_approved",
        "An active educator-approved scenario is required",
        409,
    )
    document_hash = fingerprint(body.model_dump(mode="json"))
    existing = await session.scalar(
        select(TrainingSession).where(
            TrainingSession.organization_id == organization_id,
            TrainingSession.request_key == body.request_key,
        )
    )
    if existing:
        require(
            existing.fingerprint == document_hash,
            "idempotency_conflict",
            "Request key already has different content",
            409,
        )
        return session_view(existing)
    await expire_sessions(session, organization_id)
    policy = config["policy"]
    capture = config["settings"]["capture"]
    require(
        body.duration_seconds <= capture["max_session_seconds"],
        "session_duration_limit",
        "Session duration exceeds the published profile",
        409,
    )
    concurrent = (
        await session.scalar(
            select(func.count())
            .select_from(TrainingSession)
            .where(TrainingSession.organization_id == organization_id, TrainingSession.status.in_(ACTIVE))
        )
    ) or 0
    concurrent += (
        await session.scalar(
            select(func.count())
            .select_from(ProcessingRun)
            .where(
                ProcessingRun.organization_id == organization_id,
                ProcessingRun.status.not_in(("succeeded", "failed", "cancelled", "expired")),
            )
        )
    ) or 0
    concurrent += (
        await session.scalar(
            select(func.count())
            .select_from(PracticeSession)
            .where(
                PracticeSession.organization_id == organization_id,
                PracticeSession.status.in_(("active", "stopping")),
                PracticeSession.lease_until > now(),
            )
        )
    ) or 0
    speech_running, speech_seconds = await speech_usage(session, organization_id)
    require(
        concurrent + speech_running < policy["usage_limits"]["max_concurrent_jobs"],
        "concurrency_limit",
        "Organization processing capacity reached",
        429,
    )
    day = now().replace(hour=0, minute=0, second=0, microsecond=0)
    training = (
        await session.scalars(
            select(TrainingSession).where(
                TrainingSession.organization_id == organization_id, TrainingSession.created_at >= day
            )
        )
    ).all()
    processing = (
        await session.scalars(
            select(ProcessingRun.usage).where(
                ProcessingRun.organization_id == organization_id, ProcessingRun.created_at >= day
            )
        )
    ).all()
    budgets = {
        "audio_seconds": body.duration_seconds,
        "video_seconds": body.duration_seconds,
        "tts_characters": 3000,
    }
    for unit, reserve in budgets.items():
        used = sum(row.tts_budget if unit == "tts_characters" else row.duration_seconds for row in training)
        used += sum(value.get("reserved", 0) for value in processing if value.get("unit") == unit)
        if unit == "audio_seconds":
            used += speech_seconds
        require(
            used + reserve <= policy["usage_limits"]["daily_" + unit],
            "daily_usage_limit",
            "Organization daily processing limit reached",
            429,
        )
    timestamp = now()
    limits = {
        "max_turns": 30,
        "max_audio_turn_seconds": min(30, policy["capture_limits"]["max_audio_seconds"]),
        "max_video_segment_seconds": min(2, policy["capture_limits"]["max_video_seconds"]),
        "max_width": min(1280, policy["capture_limits"]["max_width"]),
        "max_height": min(720, policy["capture_limits"]["max_height"]),
        "max_fps": min(15, policy["capture_limits"]["max_fps"]),
        "media_retention_hours": min(24, policy["media_retention_hours"]),
        "profile_revision_id": config["profile_revision_id"],
        "configuration_hash": config["configuration_hash"],
        "scenario_hash": case.fingerprint,
        "scenario_version": case.version,
        "runtime_hash": fingerprint(runtime),
    }
    row = TrainingSession(
        id=uuid4(),
        organization_id=organization_id,
        department_id=device.department_id,
        device_id=device.id,
        learner_id=body.learner_id,
        instructor_id=actor.id,
        scenario_id=case.id,
        request_key=body.request_key,
        fingerprint=document_hash,
        device_credential_version=device.credential_version,
        language=body.language,
        duration_seconds=body.duration_seconds,
        tts_budget=3000,
        limits=limits,
        created_at=timestamp,
        expires_at=timestamp + timedelta(seconds=body.duration_seconds + 60),
        results_expires_at=timestamp + timedelta(days=policy["result_retention_days"]),
    )
    session.add(row)
    await audit(
        session,
        actor,
        "training.session.created",
        "training_session",
        row.id,
        organization_id,
        department_id=device.department_id,
    )
    await commit(session, row)
    return session_view(row)


async def human_session(
    session, actor, organization_id, session_id, permission="org.results.read", lock=False
):
    access = await organization_access(session, actor, organization_id, permission)
    row = await scoped_record(session, TrainingSession, access, session_id, lock)
    require(access.role != "org_trainee" or row.learner_id == actor.id, "not_found", "Session not found", 404)
    return row


@router.get("/organizations/{organization_id}/training/sessions")
async def list_sessions(
    organization_id: UUID,
    request: Request,
    actor: Actor,
    session: Session,
    mine: bool = False,
    limit: Limit = 100,
    cursor: str | None = None,
):
    access = await organization_access(session, actor, organization_id, "org.results.read")
    query = scoped_query(TrainingSession, access).where(TrainingSession.results_expires_at > now())
    if mine or access.role == "org_trainee":
        query = query.where(TrainingSession.learner_id == actor.id)
    rows, next_cursor, has_more, total = await directory_page(
        session,
        query,
        TrainingSession,
        limit=limit,
        cursor=cursor,
        sort="created_at",
        direction="desc",
        expression=TrainingSession.created_at,
        kind="datetime",
        include_total=True,
        binding=f"sessions|{organization_id}|{actor.id}|{access.department_id}|{mine}|{access.role}",
        secret=request.app.state.settings.token_pepper.get_secret_value(),
    )
    return {
        "items": [session_view(row) for row in rows],
        "next_cursor": next_cursor,
        "has_more": has_more,
        "total": total,
    }


@router.get("/organizations/{organization_id}/training/stats")
async def trainee_dashboard_stats(organization_id: UUID, actor: Actor, session: Session):
    access = await organization_access(session, actor, organization_id, "org.results.read")
    scores = func.jsonb_each_text(TrainingSession.feedback["scores"]).table_valued("key", "value")
    score = (
        select(
            func.avg(
                case(
                    (scores.c.value == "met", 100.0),
                    (scores.c.value == "partial", 50.0),
                    (scores.c.value == "not_met", 0.0),
                    else_=None,
                )
            )
        )
        .select_from(scores)
        .correlate(TrainingSession)
        .scalar_subquery()
    )
    query = (
        scoped_query(TrainingSession, access)
        .where(
            TrainingSession.learner_id == actor.id,
            TrainingSession.results_expires_at > now(),
        )
        .with_only_columns(
            func.count().label("sessions"),
            func.sum(
                func.least(
                    TrainingSession.duration_seconds,
                    func.greatest(
                        0, func.extract("epoch", TrainingSession.ended_at - TrainingSession.started_at)
                    ),
                )
            )
            .filter(TrainingSession.status == "completed")
            .label("seconds"),
            func.count()
            .filter(and_(TrainingSession.status == "completed", TrainingSession.feedback.is_(None)))
            .label("awaiting"),
            func.avg(score).filter(TrainingSession.status == "completed").label("score"),
        )
    )
    result = (await session.execute(query)).one()
    practice = (
        await session.execute(
            scoped_query(PracticeSession, access)
            .where(PracticeSession.learner_id == actor.id)
            .with_only_columns(
                func.count().label("sessions"),
                func.sum(
                    func.least(
                        PracticeSession.duration_seconds,
                        func.extract("epoch", PracticeSession.expires_at - PracticeSession.started_at),
                        func.greatest(
                            0, func.extract("epoch", PracticeSession.ended_at - PracticeSession.started_at)
                        ),
                    )
                )
                .filter(PracticeSession.status == "completed")
                .label("seconds"),
            )
        )
    ).one()
    return {
        "sessions": result.sessions + practice.sessions,
        "hours_practiced": round(((result.seconds or 0) + (practice.seconds or 0)) / 3600, 1),
        "average_score": round(result.score) if result.score is not None else None,
        "awaiting_review": result.awaiting,
    }


@router.get("/organizations/{organization_id}/training/sessions/{session_id}")
async def get_session(organization_id: UUID, session_id: UUID, actor: Actor, session: Session):
    return session_view(await human_session(session, actor, organization_id, session_id))


async def validate_active(session, row, device):
    require(
        row.status in ACTIVE and row.expires_at > now(),
        "session_closed",
        "Training session is no longer active",
        409,
    )
    require(
        row.device_credential_version == device.credential_version
        and row.department_id == device.department_id,
        "session_context_changed",
        "Device authorization changed",
        409,
    )
    config = await configuration(session, device)
    policy = config["policy"]["usage_limits"]
    concurrent = (
        await session.scalar(
            select(func.count())
            .select_from(TrainingSession)
            .where(
                TrainingSession.organization_id == row.organization_id,
                TrainingSession.status.in_(ACTIVE),
                TrainingSession.expires_at > now(),
            )
        )
    ) or 0
    concurrent += (
        await session.scalar(
            select(func.count())
            .select_from(ProcessingRun)
            .where(
                ProcessingRun.organization_id == row.organization_id,
                ProcessingRun.status.not_in(("succeeded", "failed", "cancelled", "expired")),
            )
        )
    ) or 0
    speech_running, _ = await speech_usage(session, row.organization_id)
    require(
        concurrent + speech_running <= policy["max_concurrent_jobs"],
        "concurrency_limit",
        "Organization processing capacity changed",
        429,
    )
    require(
        row.duration_seconds <= config["settings"]["capture"]["max_session_seconds"],
        "session_duration_limit",
        "Session exceeds the current device profile",
        409,
    )
    require(
        row.limits["configuration_hash"] == config["configuration_hash"],
        "session_configuration_changed",
        "Configuration changed; start a new session",
        409,
    )
    instructor = required(await session.get(User, row.instructor_id, populate_existing=True))
    access = await organization_access(
        session, Principal(user=instructor), row.organization_id, "org.processing.execute"
    )
    await organization_access(
        session, Principal(user=instructor), row.organization_id, "org.playback.execute"
    )
    instructor_grant = await organization_access(
        session,
        Principal(user=instructor),
        row.organization_id,
        "org.training.instruct",
        lock_membership=True,
    )
    require(
        instructor.is_active
        and access.department_id in {None, row.department_id}
        and instructor_grant.department_id in {None, row.department_id},
        "instructor_unavailable",
        "Session instructor authorization changed",
        403,
    )
    await participant(session, row.organization_id, row.learner_id, row.department_id)
    case = await scenario_row(session, row.organization_id, row.scenario_id)
    require(
        row.limits.get("scenario_hash") in {None, case.fingerprint}
        and row.limits.get("scenario_version") in {None, case.version},
        "scenario_snapshot_changed",
        "Scenario snapshot changed; start a new session",
        409,
    )
    runtime = require_runtime(case.document)
    require(
        row.limits.get("runtime_hash") in {None, fingerprint(runtime)},
        "scenario_runtime_changed",
        "Runtime conversion changed; start a new session",
        409,
    )
    require(
        case.is_active and case.approved_at, "scenario_unavailable", "Scenario retired or unapproved", 409
    )
    return case


def grant(request, row, case, scope, subject):
    runtime = None
    if scope != "read":
        runtime = require_runtime(case.document)
    timestamp = now()
    end = min(
        timestamp + timedelta(seconds=request.app.state.settings.training_lease_seconds),
        row.results_expires_at if scope == "read" else row.expires_at,
    )
    claims = {
        "iss": "pms-training-v1",
        "aud": "device-training",
        "sub": str(subject),
        "iat": timestamp,
        "nbf": timestamp,
        "exp": end,
        "jti": str(uuid4()),
        "scope": scope,
        "session_id": str(row.id),
        "organization_id": str(row.organization_id),
        "device_id": str(row.device_id),
        "learner_id": str(row.learner_id),
        "instructor_id": str(row.instructor_id),
        "scenario_id": str(row.scenario_id),
        "scenario_hash": row.limits.get("runtime_hash", case.fingerprint),
        "language": row.language,
        "session_deadline": row.expires_at.timestamp(),
        "duration_seconds": row.duration_seconds,
        "tts_budget": row.tts_budget,
        "limits": row.limits,
    }
    return {
        "grant": jwt.encode(claims, signing_key(request), algorithm="EdDSA"),
        "scenario": runtime,
        "expires_at": end,
    }


@router.post("/organizations/{organization_id}/training/sessions/{session_id}/access")
async def access_session(
    organization_id: UUID,
    session_id: UUID,
    request: Request,
    actor: Actor,
    session: Session,
    control: bool = False,
):
    row = await human_session(
        session, actor, organization_id, session_id, "org.processing.execute" if control else "org.media.read"
    )
    require(row.results_expires_at > now(), "results_expired", "Session results expired", 410)
    if control:
        await organization_access(session, actor, organization_id, "org.training.instruct")
        await organization_access(session, actor, organization_id, "org.playback.execute")
        require(row.instructor_id == actor.id, "not_found", "Session not found", 404)
        device = required(await session.get(Device, row.device_id, populate_existing=True))
        case = await validate_active(session, row, device)
    else:
        case = await scenario_row(session, organization_id, row.scenario_id)
    return grant(request, row, case, "control" if control else "read", actor.id)


@router.post("/organizations/{organization_id}/training/sessions/{session_id}/stop")
async def stop_session(organization_id: UUID, session_id: UUID, actor: Actor, session: Session):
    row = await human_session(session, actor, organization_id, session_id, "org.processing.execute", True)
    await organization_access(session, actor, organization_id, "org.training.instruct")
    await organization_access(session, actor, organization_id, "org.playback.execute")
    require(row.instructor_id == actor.id, "not_found", "Session not found", 404)
    if row.status in ACTIVE:
        row.status, row.ended_at = "cancelled", now()
        await audit(
            session,
            actor,
            "training.session.stopped",
            "training_session",
            row.id,
            organization_id,
            department_id=row.department_id,
        )
        await commit(session, row)
    return session_view(row)


@router.post("/organizations/{organization_id}/training/sessions/{session_id}/feedback")
async def feedback(organization_id: UUID, session_id: UUID, body: Feedback, actor: Actor, session: Session):
    row = await human_session(session, actor, organization_id, session_id, "org.processing.execute", True)
    await organization_access(session, actor, organization_id, "org.training.instruct")
    await organization_access(session, actor, organization_id, "org.playback.execute")
    require(row.instructor_id == actor.id, "not_found", "Session not found", 404)
    require(
        row.status not in ACTIVE and row.results_expires_at > now(),
        "session_not_reviewable",
        "Finish the session before recording feedback",
        409,
    )
    require(
        row.feedback_version == body.expected_version,
        "feedback_version_conflict",
        "Feedback changed; reload before editing",
        409,
    )
    stored_case = await scenario_row(session, organization_id, row.scenario_id)
    case = parse_runtime(require_runtime(stored_case.document))
    require(
        set(body.scores) == {item.id for item in case.rubric},
        "rubric_mismatch",
        "Rate each item in the session rubric",
    )
    row.feedback = {
        "scores": body.scores,
        "comments": body.comments,
        "reviewer_id": str(actor.id),
        "reviewed_at": now().isoformat(),
    }
    row.feedback_version += 1
    await audit(
        session,
        actor,
        "training.feedback.saved",
        "training_session",
        row.id,
        organization_id,
        details={"version": row.feedback_version},
        department_id=row.department_id,
    )
    await commit(session, row)
    return session_view(row)


@router.get("/device/training/next")
async def next_session(actor: Actor, session: Session):
    device = await device_access(session, actor, True)
    row = await session.scalar(
        select(TrainingSession)
        .where(
            TrainingSession.device_id == device.id,
            TrainingSession.organization_id == device.organization_id,
            TrainingSession.status.in_(ACTIVE),
            TrainingSession.expires_at > now(),
        )
        .order_by(TrainingSession.created_at)
        .limit(1)
    )
    return {"session": session_view(row) if row else None}


@router.post("/device/training/sessions/{session_id}/lease")
async def lease(session_id: UUID, request: Request, actor: Actor, session: Session):
    device = await device_access(session, actor, True)
    row = required(
        await session.scalar(
            select(TrainingSession)
            .where(
                TrainingSession.id == session_id,
                TrainingSession.device_id == device.id,
                TrainingSession.organization_id == device.organization_id,
            )
            .with_for_update()
        )
    )
    case = await validate_active(session, row, device)
    result = grant(request, row, case, "device", device.id)
    if row.status == "authorized":
        row.status, row.started_at = "active", now()
        await audit(
            session,
            actor,
            "training.session.started",
            "training_session",
            row.id,
            row.organization_id,
            department_id=row.department_id,
        )
        await commit(session)
    return result


@router.post("/device/training/sessions/{session_id}/result")
async def record_result(session_id: UUID, body: SessionResult, actor: Actor, session: Session):
    device = await device_access(session, actor, True, allow_maintenance=True)
    row = required(
        await session.scalar(
            select(TrainingSession)
            .where(
                TrainingSession.id == session_id,
                TrainingSession.device_id == device.id,
                TrainingSession.organization_id == device.organization_id,
            )
            .with_for_update()
        )
    )
    require(
        row.device_credential_version == device.credential_version
        and row.department_id == device.department_id,
        "session_context_changed",
        "Device authorization changed",
        409,
    )
    require(body.turns <= row.limits["max_turns"], "turn_limit", "Result exceeds session turn limit", 409)
    require(
        len(set(body.audio_recordings)) == len(body.audio_recordings)
        and len(set(body.video_recordings)) == len(body.video_recordings),
        "duplicate_recordings",
        "Recording references must be unique",
        409,
    )
    value = body.model_dump(mode="json")
    if row.result is not None:
        require(row.result == value, "result_conflict", "A different result is already recorded", 409)
        return session_view(row)
    require(row.results_expires_at > now(), "results_expired", "Results expired", 410)
    if row.status in ACTIVE and row.expires_at > now():
        row.status, row.ended_at = body.status, now()
    elif row.status in ACTIVE:
        row.status, row.ended_at = "expired", now()
    # Late receipts may attach once; they never reopen or replace terminal status.
    row.result = value
    await audit(
        session,
        actor,
        "training.session.finished",
        "training_session",
        row.id,
        row.organization_id,
        details={"status": row.status},
        department_id=row.department_id,
    )
    await commit(session, row)
    return session_view(row)


@router.get("/organizations/{organization_id}/training/sessions/{session_id}/rubric")
async def session_rubric(organization_id: UUID, session_id: UUID, actor: Actor, session: Session):
    row = await human_session(session, actor, organization_id, session_id, "org.processing.execute")
    await organization_access(session, actor, organization_id, "org.training.instruct")
    await organization_access(session, actor, organization_id, "org.playback.execute")
    require(row.instructor_id == actor.id, "not_found", "Session not found", 404)
    require(row.results_expires_at > now(), "results_expired", "Session results expired", 410)
    return {"items": []}
