"""Ordered, device-owned Practice sessions assigned by a scoped instructor.

All transitions serialize on the organization row, shared with Practice admission.
The device polls for readiness; only Begin starts the duration and a short lease.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, Request
from pydantic import Field
from sqlalchemy import func, literal, or_, select, union_all
from training_contracts import fingerprint
from training_contracts.languages import LanguageTag

from pms_api.core.common import AppError, now, require, required
from pms_api.core.dependencies import Session
from pms_api.database.models import (
    Device,
    DeviceSessionQueue,
    LocalConversationTurn,
    Membership,
    Organization,
    PatientConversation,
    PracticeSession,
    SessionArchive,
    SessionArchiveItem,
    TrainingScenario,
    TrainingSession,
    User,
)
from pms_api.modules.common import audit, decode_cursor, directory_page, encode_cursor, public
from pms_api.modules.configuration import resolved_configuration
from pms_api.modules.patient_practice import published_scenario
from pms_api.modules.schemas import Input
from pms_api.modules.session_archives import describe as describe_archive
from pms_api.modules.session_archives import read_scope as archive_read_scope
from pms_api.modules.training import participant
from pms_api.security.access import (
    Actor,
    Principal,
    device_access,
    organization_access,
    reload_actor,
    scoped_query,
    scoped_record,
)

router = APIRouter(tags=["Session queue"])
BASE = "/organizations/{organization_id}/devices/{device_id}/session-queue"
DEVICE = "/device/session-queue"
LIVE = ("active", "stopping")


class Assignment(Input):
    learner_id: UUID
    scenario_id: UUID
    language: LanguageTag
    duration_seconds: int = Field(ge=30, le=600, strict=True)


class Plan(Input):
    request_key: UUID
    items: list[Assignment] = Field(min_length=1, max_length=50)


class QueueChange(Input):
    expected_revision: int = Field(ge=1, strict=True)
    order: list[UUID] = Field(max_length=100)
    paused: bool


class Edit(Assignment):
    expected_revision: int = Field(ge=1, strict=True)


class Poll(Input):
    runtime_id: UUID
    runtime_state: Literal["idle", "standalone", "assigned"]
    session_id: UUID | None = None


class Finish(Input):
    runtime_id: UUID
    outcome: Literal["completed", "cancelled", "failed"] = "completed"


class Begin(Input):
    runtime_id: UUID


async def locked_device(session, actor, org, device_id):
    access = await organization_access(session, actor, org, "org.training.instruct")
    await session.get(Organization, org, with_for_update=True, populate_existing=True)
    actor = await reload_actor(session, user_id=actor.id)
    access = await organization_access(session, actor, org, "org.training.instruct")
    await organization_access(session, actor, org, "org.processing.execute")
    await organization_access(session, actor, org, "org.playback.execute")
    return await scoped_record(session, Device, access, device_id)


async def device_lock(session, actor):
    require(actor.device is not None, "permission_denied", "Device authentication required", 403)
    device = actor.device
    await session.get(Organization, device.organization_id, with_for_update=True, populate_existing=True)
    actor = await reload_actor(session, device_id=actor.id, credential_version=device.credential_version)
    return await device_access(session, actor, True)


async def queue_state(session, device):
    state = await session.get(DeviceSessionQueue, device.id, populate_existing=True)
    if state is None:
        state = DeviceSessionQueue(
            device_id=device.id,
            organization_id=device.organization_id,
            paused=False,
            revision=1,
            runtime_state="offline",
        )
        session.add(state)
        await session.flush()
    await expire(session, device, state)
    return state


async def close_context(session, row):
    context = await session.scalar(
        select(PatientConversation).where(PatientConversation.assigned_session_id == row.id)
    )
    if context and context.status == "active":
        context.status, context.closed_at = "closed", now()


async def transition(session, actor, row, status):
    row.status = status
    if status not in LIVE and status != "queued":
        row.ended_at = now()
        await close_context(session, row)
    await audit(
        session,
        actor,
        "practice.session." + status,
        "practice_session",
        row.id,
        row.organization_id,
        department_id=row.department_id,
        details={"learner_id": str(row.learner_id)},
    )


async def expire(session, device, state):
    rows = await session.scalars(
        select(PracticeSession).where(
            PracticeSession.device_id == device.id, PracticeSession.status.in_(("queued", *LIVE))
        )
    )
    for row in rows:
        status = None
        if row.expires_at <= now():
            status = "expired"
        elif row.status in LIVE:
            if row.credential_version != device.credential_version:
                status = "failed"
            elif row.started_at and row.started_at + timedelta(seconds=row.duration_seconds) <= now():
                status = "completed"
            elif row.lease_until and row.lease_until <= now():
                status = "completed" if row.status == "stopping" else "failed"
        if status:
            await transition(session, Principal(device=device), row, status)
            state.revision += 1
    await session.flush()


async def items(session, device, *, queued=False):
    query = select(PracticeSession).where(PracticeSession.device_id == device.id)
    if queued:
        query = query.where(PracticeSession.status == "queued")
    else:
        query = query.where(PracticeSession.status.in_(("queued", *LIVE)))
    return list(await session.scalars(query.order_by(PracticeSession.position, PracticeSession.created_at)))


async def view(session, row):
    result = public(
        row, exclude={"fingerprint", "credential_version", "request_key", "batch_index", "runtime_id"}
    )
    learner = await session.get(User, row.learner_id)
    case = await session.get(TrainingScenario, row.scenario_id)
    result.update(
        learner_name=learner.display_name if learner else "Unavailable trainee",
        scenario_title=case.document.get("title", "Practice case") if case else "Unavailable case",
    )
    return result


async def snapshot(session, device, state):
    rows = await items(session, device)
    recent = await session.scalars(
        select(PracticeSession)
        .where(
            PracticeSession.device_id == device.id,
            PracticeSession.status.not_in(("queued", *LIVE)),
        )
        .order_by(PracticeSession.created_at.desc())
        .limit(50)
    )
    connected = bool(state.last_seen_at and state.last_seen_at > now() - timedelta(seconds=30))
    return {
        "revision": state.revision,
        "paused": state.paused,
        "connected": connected,
        "runtime_state": state.runtime_state if connected else "offline",
        "items": [await view(session, row) for row in rows],
        "history": [await view(session, row) for row in recent],
    }


async def validate_assignment(session, device, body, settings):
    await participant(session, device.organization_id, body.learner_id, device.department_id)
    await published_scenario(session, device.organization_id, body.scenario_id, body.language)
    require(
        body.language in settings.patient_enabled_languages,
        "model_language_unavailable",
        "This language is not enabled for practice",
        409,
    )
    await device_access(session, Principal(device=device), True)
    if isinstance(body, PracticeSession):
        require(
            body.department_id == device.department_id,
            "session_context_changed",
            "The device department changed",
            409,
        )
    config = await resolved_configuration(session, device)
    require(
        config["profile_revision_id"] is not None, "model_selection_required", "Assign device models", 409
    )
    # Capture limits bound each microphone turn. The assignment duration bounds the
    # whole multi-turn practice; existing per-turn admission still enforces usage.
    require(
        config["settings"].get("conversation", {}).get("enabled")
        and config["connections"].get("llm", {}).get("is_active"),
        "model_selection_required",
        "Assign an active conversation model",
        409,
    )
    return config


@router.get(BASE)
async def get_queue(organization_id: UUID, device_id: UUID, actor: Actor, session: Session):
    device = await locked_device(session, actor, organization_id, device_id)
    state = await queue_state(session, device)
    result = await snapshot(session, device, state)
    await session.commit()
    return result


@router.get("/organizations/{organization_id}/session-queue/learners")
async def learners(
    organization_id: UUID,
    device_id: UUID,
    actor: Actor,
    session: Session,
    cursor: UUID | None = None,
    limit: int = Query(100, ge=1, le=100),
):
    device = await locked_device(session, actor, organization_id, device_id)
    query = (
        select(User.id, User.display_name)
        .join(Membership, Membership.user_id == User.id)
        .where(
            Membership.organization_id == organization_id,
            Membership.is_active.is_(True),
            Membership.invitation_status == "accepted",
            User.is_active.is_(True),
        )
    )
    query = query.where(
        (Membership.department_id.is_(None)) | (Membership.department_id == device.department_id)
    )
    if cursor:
        query = query.where(User.id > cursor)
    rows = (await session.execute(query.order_by(User.id).limit(limit + 1))).all()
    return {
        "items": [{"id": row.id, "name": row.display_name} for row in rows[:limit]],
        "next_cursor": str(rows[limit - 1].id) if len(rows) > limit else None,
    }


@router.post(BASE, status_code=201)
async def plan(
    organization_id: UUID, device_id: UUID, body: Plan, request: Request, actor: Actor, session: Session
):
    device = await locked_device(session, actor, organization_id, device_id)
    state = await queue_state(session, device)
    digest = fingerprint(body.model_dump(mode="json"))
    previous = list(
        await session.scalars(
            select(PracticeSession).where(
                PracticeSession.device_id == device_id, PracticeSession.request_key == body.request_key
            )
        )
    )
    if previous:
        require(
            all(row.fingerprint == digest for row in previous),
            "idempotency_conflict",
            "Request already used",
            409,
        )
    else:
        waiting = await items(session, device, queued=True)
        require(
            len(waiting) + len(body.items) <= 100,
            "queue_full",
            "This device already has 100 waiting sessions",
            409,
        )
        position = max((row.position for row in waiting), default=0)
        for index, assignment in enumerate(body.items):
            await validate_assignment(session, device, assignment, request.app.state.settings)
            stamp = now()
            row = PracticeSession(
                id=uuid4(),
                organization_id=organization_id,
                device_id=device.id,
                department_id=device.department_id,
                instructor_id=actor.id,
                **assignment.model_dump(),
                request_key=body.request_key,
                batch_index=index,
                fingerprint=digest,
                position=position + index + 1,
                status="queued",
                created_at=stamp,
                expires_at=stamp + timedelta(hours=24),
            )
            session.add(row)
            await audit(
                session,
                actor,
                "practice.session.queued",
                "practice_session",
                row.id,
                organization_id,
                department_id=device.department_id,
                details={"learner_id": str(row.learner_id)},
            )
        state.revision += 1
    await session.flush()
    result = await snapshot(session, device, state)
    await session.commit()
    return result


@router.put(BASE)
async def reorder(organization_id: UUID, device_id: UUID, body: QueueChange, actor: Actor, session: Session):
    device = await locked_device(session, actor, organization_id, device_id)
    state = await queue_state(session, device)
    rows = await items(session, device, queued=True)
    require(state.revision == body.expected_revision, "queue_changed", "Queue changed; reload and retry", 409)
    require(
        len(body.order) == len(set(body.order)) and set(body.order) == {row.id for row in rows},
        "queue_changed",
        "Reorder all waiting sessions exactly once",
        409,
    )
    for row in rows:
        row.position = body.order.index(row.id) + 1
    state.paused, state.revision = body.paused, state.revision + 1
    await audit(
        session,
        actor,
        "practice.queue.updated",
        "device",
        device.id,
        organization_id,
        department_id=device.department_id,
        details={"paused": state.paused, "order": [str(i) for i in body.order]},
    )
    await session.flush()
    result = await snapshot(session, device, state)
    await session.commit()
    return result


@router.put(BASE + "/{session_id}")
async def edit(
    organization_id: UUID,
    device_id: UUID,
    session_id: UUID,
    body: Edit,
    request: Request,
    actor: Actor,
    session: Session,
):
    device = await locked_device(session, actor, organization_id, device_id)
    state = await queue_state(session, device)
    row = required(
        await session.scalar(
            select(PracticeSession).where(
                PracticeSession.device_id == device_id, PracticeSession.id == session_id
            )
        )
    )
    require(
        state.revision == body.expected_revision and row.status == "queued",
        "queue_changed",
        "Reload the queue",
        409,
    )
    await validate_assignment(session, device, body, request.app.state.settings)
    for key, value in body.model_dump(exclude={"expected_revision"}).items():
        setattr(row, key, value)
    state.revision += 1
    await audit(
        session,
        actor,
        "practice.session.edited",
        "practice_session",
        row.id,
        organization_id,
        department_id=device.department_id,
    )
    await session.flush()
    result = await snapshot(session, device, state)
    await session.commit()
    return result


@router.post(BASE + "/{session_id}/end")
async def end(organization_id: UUID, device_id: UUID, session_id: UUID, actor: Actor, session: Session):
    device = await locked_device(session, actor, organization_id, device_id)
    state = await queue_state(session, device)
    row = required(
        await session.scalar(
            select(PracticeSession).where(
                PracticeSession.device_id == device_id, PracticeSession.id == session_id
            )
        )
    )
    if row.status in ("queued", "active"):
        await transition(session, actor, row, "cancelled" if row.status == "queued" else "stopping")
        state.revision += 1
    await session.flush()
    result = await snapshot(session, device, state)
    await session.commit()
    return result


@router.post(DEVICE + "/poll")
async def poll(body: Poll, request: Request, actor: Actor, session: Session):
    device = await device_lock(session, actor)
    state = await queue_state(session, device)
    state.last_seen_at, state.runtime_state = now(), body.runtime_state
    rows = await items(session, device)
    active = next((row for row in rows if row.status in LIVE), None)
    if (
        active
        and active.status == "active"
        and body.session_id == active.id
        and body.runtime_id == active.runtime_id
    ):
        try:
            await validate_assignment(session, device, active, request.app.state.settings)
        except AppError:
            await transition(session, actor, active, "stopping")
            state.revision += 1
        else:
            active.lease_until = min(
                now() + timedelta(seconds=30),
                active.started_at + timedelta(seconds=active.duration_seconds),
                active.expires_at,
            )
    next_row = next((row for row in rows if row.status == "queued"), None)
    result = {
        "paused": state.paused,
        "active": await view(session, active) if active else None,
        "next": await view(session, next_row) if next_row and not state.paused and not active else None,
        "waiting": sum(row.status == "queued" for row in rows),
        "lease_seconds": 20,
    }
    await session.commit()
    return result


@router.post(DEVICE + "/{session_id}/begin")
async def begin(session_id: UUID, body: Begin, request: Request, actor: Actor, session: Session):
    device = await device_lock(session, actor)
    state = await queue_state(session, device)
    rows = await items(session, device)
    active = next((row for row in rows if row.status in LIVE), None)
    if (
        active
        and active.id == session_id
        and active.status == "active"
        and active.runtime_id == body.runtime_id
    ):
        await validate_assignment(session, device, active, request.app.state.settings)
        await check_active(session, active, device)
        result = await view(session, active)
        await session.commit()
        return result
    require(
        not state.paused and not active, "device_busy", "Finish the current session or resume the queue", 409
    )
    row = next((row for row in rows if row.status == "queued"), None)
    require(
        row is not None and row.id == session_id, "queue_changed", "The next trainee changed; reload", 409
    )
    assert row is not None
    standalone = await session.scalar(
        select(PatientConversation.id).where(
            PatientConversation.device_id == device.id,
            PatientConversation.status == "active",
            PatientConversation.expires_at > now(),
        )
    )
    require(standalone is None, "device_busy", "Finish the current practice first", 409)
    config = await validate_assignment(session, device, row, request.app.state.settings)
    legacy_device = await session.scalar(
        select(TrainingSession.id).where(
            TrainingSession.device_id == device.id,
            TrainingSession.status.in_(("authorized", "active")),
            TrainingSession.expires_at > now(),
        )
    )
    require(legacy_device is None, "device_busy", "Finish the device's current training session first", 409)
    busy = await session.scalar(
        select(func.count())
        .select_from(PracticeSession)
        .where(
            PracticeSession.organization_id == device.organization_id,
            PracticeSession.status.in_(LIVE),
            PracticeSession.lease_until > now(),
        )
    )
    legacy = await session.scalar(
        select(func.count())
        .select_from(TrainingSession)
        .where(
            TrainingSession.organization_id == device.organization_id,
            TrainingSession.status.in_(("authorized", "active")),
            TrainingSession.expires_at > now(),
        )
    )
    require(
        (busy or 0) + (legacy or 0) < config["policy"]["usage_limits"]["max_concurrent_jobs"],
        "concurrency_limit",
        "Organization session capacity reached",
        429,
    )
    row.started_at, row.lease_until = now(), min(now() + timedelta(seconds=30), row.expires_at)
    row.credential_version = device.credential_version
    row.runtime_id = body.runtime_id
    await transition(session, actor, row, "active")
    state.revision += 1
    result = await view(session, row)
    await session.commit()
    return result


@router.post(DEVICE + "/{session_id}/finish")
async def finish(session_id: UUID, body: Finish, actor: Actor, session: Session):
    device = await device_lock(session, actor)
    state = await queue_state(session, device)
    row = required(
        await session.scalar(
            select(PracticeSession).where(
                PracticeSession.device_id == device.id, PracticeSession.id == session_id
            )
        )
    )
    if row.status in LIVE:
        require(row.runtime_id == body.runtime_id, "device_busy", "Session belongs to another runtime", 409)
        await transition(session, actor, row, body.outcome)
        state.revision += 1
    result = await view(session, row)
    await session.commit()
    return result


async def conversation_assignment(session, actor, selection, assigned_session_id):
    if not actor.device:
        require(
            assigned_session_id is None, "permission_denied", "Assigned sessions run on their device", 403
        )
        return
    await queue_state(session, actor.device)
    rows = list(
        await session.scalars(
            select(PracticeSession).where(
                PracticeSession.device_id == actor.id, PracticeSession.status.in_(LIVE)
            )
        )
    )
    if assigned_session_id is None:
        require(not rows, "device_busy", "Finish the assigned session first", 409)
        return
    row = next((r for r in rows if r.id == assigned_session_id), None)
    require(row is not None, "session_closed", "This session is no longer active", 409)
    assert row is not None
    await check_active(session, row, actor.device)
    require(
        row.scenario_id == selection.scenario_id and row.language == selection.language,
        "session_assignment_changed",
        "Use the assigned practice case and language",
        409,
    )


async def check_active(session, row, device):
    require(
        row.status == "active"
        and row.lease_until
        and row.lease_until > now()
        and row.expires_at > now()
        and row.started_at + timedelta(seconds=row.duration_seconds) > now()
        and row.credential_version == device.credential_version,
        "session_closed",
        "This assigned session has ended",
        409,
    )
    require(
        row.department_id == device.department_id,
        "session_context_changed",
        "The device department changed",
        409,
    )
    await participant(session, row.organization_id, row.learner_id, device.department_id)


async def expire_pending(factory):
    """Bounded API-role maintenance, also running when all desktops are disconnected."""
    async with factory() as session:
        due = list(
            await session.scalars(
                select(PracticeSession.device_id)
                .where(
                    PracticeSession.status.in_(("queued", *LIVE)),
                    (PracticeSession.expires_at <= now()) | (PracticeSession.lease_until <= now()),
                )
                .distinct()
                .limit(100)
            )
        )
    for device_id in due:
        async with factory() as session:
            device = await session.get(Device, device_id)
            if not device:
                continue
            organization = await session.scalar(
                select(Organization)
                .where(Organization.id == device.organization_id)
                .with_for_update(skip_locked=True)
            )
            if organization:
                await queue_state(session, device)
                await session.commit()


async def expiry_loop(factory):
    while True:
        try:
            await expire_pending(factory)
        except Exception as error:
            logging.getLogger("pms_api").warning("Session queue expiry unavailable: %s", type(error).__name__)
        await asyncio.sleep(10)


async def validate_conversation_assignment(session, conversation, actor):
    if conversation.assigned_session_id:
        row = required(
            await session.get(PracticeSession, conversation.assigned_session_id, populate_existing=True)
        )
        require(
            actor.device is not None and actor.id == row.device_id,
            "permission_denied",
            "Assigned device required",
            403,
        )
        await check_active(session, row, actor.device)


async def result_scope(session, actor, org):
    access = await organization_access(session, actor, org, "org.results.read")
    query = scoped_query(PracticeSession, access)
    try:
        await organization_access(session, actor, org, "org.training.instruct")
    except AppError as error:
        if error.status != 403:
            raise
        query = query.where(PracticeSession.learner_id == actor.id)
    return query


@router.get("/organizations/{organization_id}/practice-sessions")
async def history(
    organization_id: UUID,
    actor: Actor,
    session: Session,
    request: Request,
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=100),
):
    query = await result_scope(session, actor, organization_id)
    rows, next_cursor, more, total = await directory_page(
        session,
        query,
        PracticeSession,
        limit=limit,
        cursor=cursor,
        sort="created_at",
        direction="desc",
        expression=PracticeSession.created_at,
        binding=f"practice_sessions:{organization_id}:{actor.id}",
        secret=request.app.state.settings.token_pepper.get_secret_value(),
        kind="datetime",
    )
    return {"items": [await view(session, row) for row in rows], "next_cursor": next_cursor, "has_more": more}


@router.get("/organizations/{organization_id}/session-history")
async def combined_history(
    organization_id: UUID,
    actor: Actor,
    session: Session,
    request: Request,
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=100),
):
    assigned = await result_scope(session, actor, organization_id)
    captures = await archive_read_scope(session, actor, organization_id)
    index = union_all(
        assigned.with_only_columns(
            PracticeSession.id, PracticeSession.created_at, literal("assigned").label("kind")
        ),
        captures.where(SessionArchive.assigned_session_id.is_(None)).with_only_columns(
            SessionArchive.id, SessionArchive.created_at, literal("standalone").label("kind")
        ),
    ).subquery()
    query = select(index)
    secret = request.app.state.settings.token_pepper.get_secret_value()
    binding = f"session_history:{organization_id}:{actor.id}"
    if cursor:
        value, identity = decode_cursor(cursor, "created_at", "desc", binding, secret, "string")
        try:
            stamp, kind = value.rsplit("|", 1)
            moment = datetime.fromisoformat(stamp)
            if moment.tzinfo is None or kind not in ("assigned", "standalone"):
                raise ValueError()
        except (AttributeError, TypeError, ValueError):
            raise AppError(422, "invalid_cursor", "Cursor is invalid") from None
        query = query.where(
            or_(
                index.c.created_at < moment,
                (index.c.created_at == moment) & (index.c.id < identity),
                (index.c.created_at == moment) & (index.c.id == identity) & (index.c.kind < kind),
            )
        )
    page = list(
        (
            await session.execute(
                query.order_by(index.c.created_at.desc(), index.c.id.desc(), index.c.kind.desc()).limit(
                    limit + 1
                )
            )
        ).mappings()
    )
    rows = page[:limit]
    assigned_ids = [row["id"] for row in rows if row["kind"] == "assigned"]
    standalone_ids = [row["id"] for row in rows if row["kind"] == "standalone"]
    assignments = {
        row.id: row for row in await session.scalars(assigned.where(PracticeSession.id.in_(assigned_ids)))
    }
    archives = list(
        await session.scalars(
            captures.where(
                or_(
                    SessionArchive.assigned_session_id.in_(assigned_ids),
                    SessionArchive.id.in_(standalone_ids),
                )
            ).order_by(SessionArchive.created_at.desc(), SessionArchive.id.desc())
        )
    )
    linked: dict[UUID, SessionArchive] = {}
    for archive in archives:
        linked.setdefault(archive.assigned_session_id or archive.id, archive)
    count_rows = (
        await session.execute(
            select(SessionArchiveItem.archive_id, func.count())
            .where(
                SessionArchiveItem.archive_id.in_([archive.id for archive in archives]),
                func.jsonb_array_length(SessionArchiveItem.received)
                == func.jsonb_array_length(SessionArchiveItem.document["hashes"]),
            )
            .group_by(SessionArchiveItem.archive_id)
        )
    ).all()
    counts = {archive_id: count for archive_id, count in count_rows}
    items = []
    for row in rows:
        assignment = assignments.get(row["id"])
        archive = linked.get(row["id"])
        if assignment is None and archive is None:
            continue
        items.append(
            {
                "id": row["id"],
                "kind": row["kind"],
                "session": await view(session, assignment) if assignment else None,
                "archive": await describe_archive(session, archive, include_items=False, summary=counts)
                if archive
                else None,
            }
        )
    tail = rows[-1] if rows else None
    next_cursor = (
        encode_cursor(
            tail["created_at"].isoformat() + "|" + tail["kind"],
            tail["id"],
            "created_at",
            "desc",
            binding,
            secret,
        )
        if len(page) > limit and tail
        else None
    )
    return {"items": items, "next_cursor": next_cursor}


@router.get("/organizations/{organization_id}/practice-sessions/{session_id}")
async def result(organization_id: UUID, session_id: UUID, actor: Actor, session: Session):
    query = await result_scope(session, actor, organization_id)
    row = required(await session.scalar(query.where(PracticeSession.id == session_id)))
    conversation = await session.scalar(
        select(PatientConversation).where(
            PatientConversation.assigned_session_id == row.id, PatientConversation.expires_at > now()
        )
    )
    messages = []
    if conversation:
        if conversation.context["execution"] == "caller":
            turns = await session.scalars(
                select(LocalConversationTurn)
                .where(
                    LocalConversationTurn.organization_id == organization_id,
                    LocalConversationTurn.device_id == row.device_id,
                    LocalConversationTurn.conversation_id == conversation.id,
                    LocalConversationTurn.expires_at > now(),
                )
                .order_by(LocalConversationTurn.sequence)
                .limit(200)
            )
            for turn in turns:
                messages.append({"role": "user", "content": turn.input_text})
                if turn.response_text:
                    messages.append({"role": "assistant", "content": turn.response_text})
        else:
            messages = conversation.history
    # Archives can contain the actual turns even when optional local-history
    # reporting was disabled, or when its shorter-lived record has expired.
    archive_id = await session.scalar(
        (await archive_read_scope(session, actor, organization_id))
        .where(SessionArchive.assigned_session_id == row.id)
        .order_by(SessionArchive.created_at.desc(), SessionArchive.id.desc())
        .with_only_columns(SessionArchive.id)
        .limit(1)
    )
    await audit(
        session,
        actor,
        "practice.session.results_read",
        "practice_session",
        row.id,
        organization_id,
        department_id=row.department_id,
    )
    await session.commit()
    return {
        "session": await view(session, row),
        "messages": messages,
        "archive_id": archive_id,
        "history_available": bool(conversation),
        "provenance": "client_reported"
        if conversation and conversation.context["execution"] == "caller"
        else "platform",
    }
