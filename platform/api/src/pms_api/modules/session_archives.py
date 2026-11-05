"""Bounded, idempotent archival; uploads never invoke a model or reopen practice."""

import asyncio
import hashlib
import json
import logging
from datetime import timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import AwareDatetime, Field, ValidationError, model_validator
from sqlalchemy import func, select

from pms_api.core.common import AppError, now, require, required
from pms_api.core.dependencies import Session
from pms_api.database.models import (
    Organization,
    PlatformSettings,
    PracticeSession,
    SessionArchive,
    SessionArchiveItem,
    User,
)
from pms_api.modules.common import audit, directory_page, public
from pms_api.modules.configuration import tighter
from pms_api.modules.schemas import Input
from pms_api.security.access import Actor, device_access, organization_access, reload_actor, scoped_query

router = APIRouter(tags=["Session archives"])
BASE = "/device/session-archives/{archive_id}"
READ = "/organizations/{organization_id}/session-archives"
CHUNK = 262144
KINDS = {
    "turn": ("application/json", "json"),
    "microphone": ("audio/wav", "wav"),
    "patient_audio": ("audio/wav", "wav"),
    "video": ("video/x-matroska", "mkv"),
}
Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class Item(Input):
    kind: Literal["turn", "microphone", "patient_audio", "video"]
    byte_size: int = Field(ge=1, le=CHUNK * 1024, strict=True)
    hashes: list[Hash] = Field(min_length=1, max_length=1024)
    sequence: int = Field(ge=0, le=1000000, strict=True)

    @model_validator(mode="after")
    def chunks(self):
        if len(self.hashes) != (self.byte_size + CHUNK - 1) // CHUNK:
            raise ValueError("Chunk count does not match size")
        if self.kind == "turn" and self.byte_size > 131072:
            raise ValueError("Turn exceeds text limit")
        return self


class Manifest(Input):
    items: list[UUID] = Field(max_length=4000)
    incomplete: bool = False
    outcome: Literal["completed", "cancelled", "interrupted"]

    @model_validator(mode="after")
    def unique(self):
        if len(set(self.items)) != len(self.items):
            raise ValueError("Duplicate item")
        return self


class Turn(Input):
    turn_key: UUID
    occurred_at: AwareDatetime
    input_text: str = Field(max_length=8000)
    response_text: str | None = Field(None, max_length=32000)
    outcome: Literal["completed", "failed", "cancelled"]
    execution: Literal["local", "cloud"]
    input_source: Literal["text", "speech"]


async def create_archive(session, conversation, selection):
    if not conversation.device_id or not conversation.scenario_id:
        return
    org = required(await session.get(Organization, conversation.organization_id))
    platform = required(await session.get(PlatformSettings, 1))
    limits = tighter(platform.policy_limits, org.policy_settings)
    stamp = conversation.created_at
    expiry = stamp + timedelta(days=limits["result_retention_days"])
    assignment = (
        await session.get(PracticeSession, conversation.assigned_session_id)
        if conversation.assigned_session_id
        else None
    )
    session.add(
        SessionArchive(
            id=conversation.id,
            organization_id=org.id,
            department_id=conversation.department_id,
            device_id=conversation.device_id,
            learner_id=assignment.learner_id if assignment else None,
            assigned_session_id=conversation.assigned_session_id,
            scenario_id=conversation.scenario_id,
            scenario_title=selection.document.get("title", "Practice"),
            language=conversation.context["language"],
            execution=conversation.context["execution"],
            practice_snapshot=selection.document,
            context=conversation.context,
            created_at=stamp,
            expires_at=expiry,
            media_expires_at=min(expiry, stamp + timedelta(hours=limits["media_retention_hours"])),
            upload_until=min(expiry, stamp + timedelta(days=7)),
            manifest=None,
            finalized_at=None,
        )
    )


async def upload_access(session, actor, archive_id, *, lock=False):
    require(actor.device is not None, "device_identity_required", "A device identity is required", 403)
    actor = await reload_actor(
        session, device_id=actor.id, credential_version=actor.device.credential_version
    )
    device = await device_access(session, actor, True)
    row = required(
        await session.scalar(
            select(SessionArchive)
            .where(
                SessionArchive.id == archive_id,
                SessionArchive.device_id == device.id,
                SessionArchive.organization_id == device.organization_id,
            )
            .with_for_update()
            if lock
            else select(SessionArchive).where(
                SessionArchive.id == archive_id,
                SessionArchive.device_id == device.id,
                SessionArchive.organization_id == device.organization_id,
            )
        )
    )
    require(row.department_id == device.department_id, "scope_unavailable", "Device scope changed", 403)
    require(row.upload_until > now(), "archive_expired", "Archive upload window ended", 410)
    return row


async def read_scope(session, actor, org):
    access = await organization_access(session, actor, org, "org.results.read")
    query = scoped_query(SessionArchive, access).where(SessionArchive.expires_at > now())
    try:
        await organization_access(session, actor, org, "org.training.instruct")
    except AppError as error:
        if error.status != 403:
            raise
        query = query.where(SessionArchive.learner_id == actor.id)
    return query


def key(item, index):
    return f"{item.organization_id}/session-archives/{item.archive_id}/{item.id}/{index}"


def item_view(item):
    return {
        "id": str(item.id),
        "kind": item.kind,
        "byte_size": item.byte_size,
        "sequence": item.document["sequence"],
        "chunks": len(item.document["hashes"]),
        "received": item.received,
        "available": item.expires_at > now() and len(item.received) == len(item.document["hashes"]),
    }


async def describe(session, row, *, include_items=True, summary=None):
    items = (
        list(
            await session.scalars(
                select(SessionArchiveItem)
                .where(SessionArchiveItem.archive_id == row.id)
                .order_by(SessionArchiveItem.created_at, SessionArchiveItem.id)
            )
        )
        if include_items
        else []
    )
    complete = {str(item.id) for item in items if len(item.received) == len(item.document["hashes"])}
    expected = set(row.manifest["items"]) if row.manifest else set()
    received_count = len(complete) if include_items else (summary or {}).get(row.id, 0)
    transfer = (
        "synced"
        if row.manifest and received_count == len(expected)
        else "upload_expired"
        if row.upload_until <= now()
        else "pending"
    )
    capture = (
        "incomplete"
        if row.manifest and row.manifest["incomplete"]
        else "complete"
        if row.manifest
        else "pending"
    )
    # Keep the legacy display field while exposing transfer independently from capture loss.
    status = "incomplete" if capture == "incomplete" else transfer
    learner = await session.get(User, row.learner_id) if row.learner_id else None
    return {
        **public(
            row, exclude={"manifest"} if include_items else {"manifest", "practice_snapshot", "context"}
        ),
        "learner_name": learner.display_name if learner else "No trainee assigned",
        "sync_status": status,
        "outcome": row.manifest.get("outcome") if row.manifest else None,
        "transfer_status": transfer,
        "capture_status": capture,
        "received_items": received_count,
        "expected_items": len(expected) if row.manifest else None,
        "items": [item_view(item) for item in items] if include_items else [],
    }


@router.get(BASE)
async def status(archive_id: UUID, actor: Actor, session: Session):
    return await describe(session, await upload_access(session, actor, archive_id))


@router.put(BASE + "/items/{item_id}")
async def reserve(
    archive_id: UUID, item_id: UUID, body: Item, request: Request, actor: Actor, session: Session
):
    archive = await upload_access(session, actor, archive_id)
    # Capacity reservation is short and serialized; no blob I/O under this tenant lock.
    await session.get(Organization, archive.organization_id, with_for_update=True, populate_existing=True)
    archive = await upload_access(session, actor, archive_id, lock=True)
    document = body.model_dump(mode="json")
    item = await session.get(SessionArchiveItem, item_id)
    if item:
        require(
            item.archive_id == archive.id and item.document == document,
            "idempotency_conflict",
            "Recording identity already used",
            409,
        )
        require(
            item.expires_at > now() and not item.purged,
            "archive_expired",
            "Recording retention window ended",
            410,
        )
    else:
        require(
            not archive.manifest or str(item_id) in archive.manifest["items"],
            "archive_finalized",
            "Item is not in the final manifest",
            409,
        )
        count, total = (
            await session.execute(
                select(func.count(), func.coalesce(func.sum(SessionArchiveItem.byte_size), 0)).where(
                    SessionArchiveItem.archive_id == archive.id
                )
            )
        ).one()
        used = await session.scalar(
            select(func.coalesce(func.sum(SessionArchiveItem.byte_size), 0)).where(
                SessionArchiveItem.organization_id == archive.organization_id,
                SessionArchiveItem.purged.is_(False),
            )
        )
        require(
            count < 4000
            and total + body.byte_size <= request.app.state.settings.session_archive_session_bytes
            and (used or 0) + body.byte_size <= request.app.state.settings.session_archive_org_bytes,
            "archive_quota",
            "Recording archive capacity reached",
            429,
        )
        expiry = archive.expires_at if body.kind == "turn" else archive.media_expires_at
        require(expiry > now(), "archive_expired", "Recording retention window ended", 410)
        item = SessionArchiveItem(
            id=item_id,
            organization_id=archive.organization_id,
            archive_id=archive.id,
            kind=body.kind,
            byte_size=body.byte_size,
            document=document,
            received=[],
            created_at=now(),
            expires_at=expiry,
        )
        session.add(item)
        await audit(
            session,
            actor,
            "practice.archive.item_reserved",
            "session_archive",
            archive.id,
            archive.organization_id,
            department_id=archive.department_id,
        )
    await session.commit()
    return item_view(item)


@router.put(BASE + "/items/{item_id}/chunks/{index}")
async def chunk(
    archive_id: UUID, item_id: UUID, index: int, request: Request, actor: Actor, session: Session
):
    await upload_access(session, actor, archive_id)
    data = bytearray()
    try:
        async with asyncio.timeout(15):
            async for part in request.stream():
                require(len(data) + len(part) <= CHUNK, "payload_too_large", "Recording chunk too large", 413)
                data.extend(part)
    except TimeoutError:
        raise AppError(408, "upload_timeout", "Recording chunk timed out") from None
    item = required(
        await session.scalar(
            select(SessionArchiveItem)
            .where(SessionArchiveItem.id == item_id, SessionArchiveItem.archive_id == archive_id)
            .with_for_update()
        )
    )
    await upload_access(session, actor, archive_id)
    require(item.expires_at > now(), "archive_expired", "Recording expired", 410)
    hashes = item.document["hashes"]
    require(0 <= index < len(hashes), "invalid_request", "Unknown chunk", 422)
    size = min(CHUNK, item.byte_size - index * CHUNK)
    require(
        len(data) == size and hashlib.sha256(data).hexdigest() == hashes[index],
        "checksum_mismatch",
        "Recording checksum mismatch",
        422,
    )
    if item.kind == "turn":
        try:
            Turn.model_validate_json(bytes(data))
        except ValidationError:
            require(False, "invalid_request", "Invalid conversation record", 422)
    if index not in item.received:
        # Immutable part key makes a retry after an uncertain write safe.
        await request.app.state.storage.write(key(item, index), bytes(data))
        item.received = sorted([*item.received, index])
        await session.commit()
    return {"index": index, "sha256": hashes[index]}


@router.put(BASE + "/manifest")
async def finalize(archive_id: UUID, body: Manifest, actor: Actor, session: Session):
    archive = await upload_access(session, actor, archive_id, lock=True)
    document = body.model_dump(mode="json")
    require(
        not archive.manifest or archive.manifest == document,
        "idempotency_conflict",
        "Manifest is immutable",
        409,
    )
    known = set(
        str(value)
        for value in await session.scalars(
            select(SessionArchiveItem.id).where(SessionArchiveItem.archive_id == archive.id)
        )
    )
    require(known <= set(document["items"]), "manifest_incomplete", "Manifest omits reserved recordings", 422)
    if not archive.manifest:
        archive.manifest, archive.finalized_at = document, now()
        await audit(
            session,
            actor,
            "practice.archive.finalized",
            "session_archive",
            archive.id,
            archive.organization_id,
            department_id=archive.department_id,
        )
    await session.commit()
    return await describe(session, archive)


@router.get(READ)
async def listing(
    organization_id: UUID,
    request: Request,
    actor: Actor,
    session: Session,
    cursor: str | None = None,
    limit: int = Query(25, ge=1, le=100),
):
    query = await read_scope(session, actor, organization_id)
    rows, cursor, more, total = await directory_page(
        session,
        query,
        SessionArchive,
        limit=limit,
        cursor=cursor,
        sort="created_at",
        direction="desc",
        expression=SessionArchive.created_at,
        binding=f"session_archives:{organization_id}:{actor.id}",
        secret=request.app.state.settings.token_pepper.get_secret_value(),
        kind="datetime",
    )
    counts = (
        (
            await session.execute(
                select(SessionArchiveItem.archive_id, func.count())
                .where(
                    SessionArchiveItem.archive_id.in_([row.id for row in rows]),
                    func.jsonb_array_length(SessionArchiveItem.received)
                    == func.jsonb_array_length(SessionArchiveItem.document["hashes"]),
                )
                .group_by(SessionArchiveItem.archive_id)
            )
        ).all()
        if rows
        else []
    )
    summary = {archive_id: count for archive_id, count in counts}
    return {
        "items": [await describe(session, row, include_items=False, summary=summary) for row in rows],
        "next_cursor": cursor,
    }


@router.get(READ + "/{archive_id}")
async def detail(organization_id: UUID, archive_id: UUID, actor: Actor, session: Session):
    row = required(
        await session.scalar(
            (await read_scope(session, actor, organization_id)).where(SessionArchive.id == archive_id)
        )
    )
    return await describe(session, row)


@router.get(READ + "/{archive_id}/items/{item_id}")
async def download(
    organization_id: UUID, archive_id: UUID, item_id: UUID, request: Request, actor: Actor, session: Session
):
    archive = required(
        await session.scalar(
            (await read_scope(session, actor, organization_id)).where(SessionArchive.id == archive_id)
        )
    )
    item = required(
        await session.scalar(
            select(SessionArchiveItem).where(
                SessionArchiveItem.archive_id == archive_id, SessionArchiveItem.id == item_id
            )
        )
    )
    require(
        item.expires_at > now() and len(item.received) == len(item.document["hashes"]),
        "recording_unavailable",
        "Recording is pending or expired",
        409,
    )
    await audit(
        session,
        actor,
        "practice.archive.downloaded",
        "session_archive",
        archive.id,
        organization_id,
        department_id=archive.department_id,
    )
    await session.commit()

    async def stream():
        for index, digest in enumerate(item.document["hashes"]):
            data = await request.app.state.storage.read(key(item, index), CHUNK)
            require(
                hashlib.sha256(data).hexdigest() == digest,
                "recording_damaged",
                "Recording checksum failed",
                409,
            )
            yield data

    content_type, extension = KINDS[item.kind]
    return StreamingResponse(
        stream(),
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{item.kind}-{item.id}.{extension}"',
            "Content-Length": str(item.byte_size),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(READ + "/{archive_id}/turns")
async def turns(
    organization_id: UUID,
    archive_id: UUID,
    request: Request,
    actor: Actor,
    session: Session,
    offset: int = Query(0, ge=0, le=4000),
):
    archive = required(
        await session.scalar(
            (await read_scope(session, actor, organization_id)).where(SessionArchive.id == archive_id)
        )
    )
    rows = list(
        await session.scalars(
            select(SessionArchiveItem)
            .where(
                SessionArchiveItem.archive_id == archive.id,
                SessionArchiveItem.kind == "turn",
                SessionArchiveItem.expires_at > now(),
                func.jsonb_array_length(SessionArchiveItem.received) == 1,
            )
            .order_by(
                SessionArchiveItem.document["sequence"].as_integer(),
                SessionArchiveItem.created_at,
                SessionArchiveItem.id,
            )
            .offset(offset)
            .limit(26)
        )
    )
    result = []
    for row in rows[:25]:
        data = await request.app.state.storage.read(key(row, 0), 131072)
        require(
            hashlib.sha256(data).hexdigest() == row.document["hashes"][0],
            "recording_damaged",
            "Conversation record checksum failed",
            409,
        )
        result.append(json.loads(data))
    await audit(
        session,
        actor,
        "practice.archive.history_read",
        "session_archive",
        archive.id,
        organization_id,
        department_id=archive.department_id,
    )
    await session.commit()
    return {
        "items": result,
        "next_offset": offset + 25 if len(rows) > 25 else None,
        "provenance": "client_reported",
    }


async def retention_once(factory, storage):
    # API role owns these tables; remove deterministic part keys even after lost acknowledgements.
    async with factory() as session:
        items = list(
            await session.scalars(
                select(SessionArchiveItem)
                .where(SessionArchiveItem.expires_at <= now(), SessionArchiveItem.purged.is_(False))
                .limit(8)
                .with_for_update(skip_locked=True)
            )
        )
        for item in items:
            for index in range(len(item.document["hashes"])):
                await storage.delete(key(item, index))
            item.purged = True
        rows = await session.scalars(
            select(SessionArchive)
            .where(
                SessionArchive.expires_at <= now(),
                ~select(SessionArchiveItem.id)
                .where(
                    SessionArchiveItem.archive_id == SessionArchive.id, SessionArchiveItem.purged.is_(False)
                )
                .exists(),
            )
            .limit(25)
            .with_for_update(skip_locked=True)
        )
        for row in rows:
            await session.delete(row)
        await session.commit()


async def retention_loop(factory, storage):
    while True:
        try:
            await retention_once(factory, storage)
        except Exception as error:
            logging.getLogger("pms_api").warning("Archive retention unavailable: %s", type(error).__name__)
        await asyncio.sleep(60)
