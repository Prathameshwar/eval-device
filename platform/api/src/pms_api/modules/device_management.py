"""Tenant association and limited platform device administration.

A transfer retires the old tenant registration and creates a fresh one. Its
immutable device ID, credentials and historical content never cross tenants.
"""

from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Query
from pydantic import Field
from sqlalchemy import select

from pms_api.core.common import now, require, required
from pms_api.core.dependencies import Session
from pms_api.database.models import (
    Device,
    DeviceIdentity,
    Organization,
    PlatformSettings,
)
from pms_api.database.session import lock_administration
from pms_api.modules.common import audit, commit
from pms_api.modules.devices import (
    check_etag,
    present_devices,
    validate_assignment,
    validate_language,
)
from pms_api.modules.patching import changes, update_fields
from pms_api.modules.schemas import DeviceUniqueId, LanguageCode, Name, PeopleInput
from pms_api.security.access import Actor, platform_access

router = APIRouter()
Etag = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class FleetDeviceCreate(PeopleInput):
    organization_id: UUID
    device_unique_id: DeviceUniqueId
    name: Name
    device_type: Literal["manikin", "laptop"]
    preferred_language: LanguageCode | None = None
    is_active: bool = True


class FleetDevicePatch(PeopleInput):
    expected_etag: Etag
    name: Name | None = None
    is_active: bool | None = None


class DeviceTransfer(PeopleInput):
    expected_etag: Etag
    organization_id: UUID
    name: Name
    is_active: bool = False


async def available_tenant(session, organization_id, active=True):
    row = required(await session.get(Organization, organization_id))
    require(row.archived_at is None, "not_found", "Tenant not found", 404)
    require(not active or row.is_active, "organization_inactive", "Activate the tenant first", 409)
    return row


async def reserve_device_identity(session, device_unique_id):
    # Insert, never upsert: retired identities remain reserved. The database
    # unique index handles races and case-insensitive cross-tenant duplicates.
    session.add(DeviceIdentity(device_unique_id=device_unique_id))
    await session.flush()


async def fleet_record(session, actor, device_id):
    platform_access(actor, "platform.organizations.manage")
    row = required(await session.scalar(select(Device).where(Device.id == device_id).with_for_update()))
    await available_tenant(session, row.organization_id, False)
    return row


async def fleet_response(session, row):
    settings = required(await session.get(PlatformSettings, 1))
    return (
        await present_devices(
            session, [row], True, int(settings.device_defaults["offline_after_seconds"]), platform=True
        )
    )[0]


def revoke_registration(row, actor, retire=False):
    row.credential_hash = None
    row.credential_revoked_at = now()
    row.enrollment_token_hash = None
    row.enrollment_expires_at = None
    if retire:
        row.enrollment_state = "retired"
        row.is_active = False
        row.status_changed_by = actor.id


@router.post("/platform/devices", status_code=201, tags=["Platform"])
async def fleet_create(body: FleetDeviceCreate, session: Session, actor: Actor):
    platform_access(actor, "platform.organizations.manage")
    await lock_administration(session)
    await available_tenant(session, body.organization_id)
    await validate_language(session, body.preferred_language)
    await reserve_device_identity(session, body.device_unique_id)
    row = Device(id=uuid4(), created_by=actor.id, **body.model_dump())
    session.add(row)
    await audit(session, actor, "platform.device.registered", "device", row.id, row.organization_id)
    await commit(session, row)
    return await fleet_response(session, row)


@router.patch("/platform/devices/{device_id}", tags=["Platform"])
async def fleet_update(device_id: UUID, body: FleetDevicePatch, session: Session, actor: Actor):
    await lock_administration(session)
    row = await fleet_record(session, actor, device_id)
    check_etag(row, body.expected_etag)
    require(row.enrollment_state != "retired", "device_retired", "This registration is retired", 409)
    values = changes(body, {"expected_etag"})
    if values.get("is_active") is True and not row.is_active:
        await available_tenant(session, row.organization_id)
        await validate_assignment(session, row.organization_id, row.department_id)
    update_fields(row, values)
    row.status_changed_by = actor.id
    await audit(
        session,
        actor,
        "platform.device.updated",
        "device",
        row.id,
        row.organization_id,
        {"fields": sorted(values)},
    )
    await commit(session, row)
    return await fleet_response(session, row)


@router.post("/platform/devices/{device_id}/revoke", tags=["Platform"])
async def fleet_revoke(
    device_id: UUID,
    session: Session,
    actor: Actor,
    expected_etag: Annotated[str, Query(pattern=r"^[0-9a-f]{64}$")],
):
    await lock_administration(session)
    row = await fleet_record(session, actor, device_id)
    check_etag(row, expected_etag)
    require(row.enrollment_state != "retired", "device_retired", "This registration is retired", 409)
    revoke_registration(row, actor)
    await audit(session, actor, "platform.device.credential_revoked", "device", row.id, row.organization_id)
    await commit(session, row)
    return await fleet_response(session, row)


@router.delete("/platform/devices/{device_id}", tags=["Platform"])
@router.post("/platform/devices/{device_id}/retire", tags=["Platform"])
async def fleet_retire(
    device_id: UUID,
    session: Session,
    actor: Actor,
    expected_etag: Annotated[str, Query(pattern=r"^[0-9a-f]{64}$")],
):
    await lock_administration(session)
    row = await fleet_record(session, actor, device_id)
    check_etag(row, expected_etag)
    if row.enrollment_state != "retired":
        revoke_registration(row, actor, True)
        await audit(session, actor, "platform.device.retired", "device", row.id, row.organization_id)
        await commit(session, row)
    return await fleet_response(session, row)


async def transfer_registration(session, actor, row, body):
    check_etag(row, body.expected_etag)
    require(row.enrollment_state != "retired", "device_retired", "This registration is retired", 409)
    require(row.organization_id != body.organization_id, "same_tenant", "Choose another tenant", 422)
    # Copy only the public registration identity. No configuration, contact,
    # location, capabilities, heartbeat, credential or historical payload crosses.
    target = Device(
        id=uuid4(),
        device_unique_id=row.device_unique_id,
        organization_id=body.organization_id,
        name=body.name,
        device_type=row.device_type,
        is_active=body.is_active,
        created_by=actor.id,
    )
    revoke_registration(row, actor, True)
    # Release the current-registration slot before inserting its replacement.
    await session.flush()
    session.add(target)
    await audit(
        session,
        actor,
        "platform.device.transferred_out",
        "device",
        row.id,
        row.organization_id,
        {"target_organization_id": str(target.organization_id), "replacement_device_id": str(target.id)},
    )
    await audit(
        session,
        actor,
        "platform.device.transferred_in",
        "device",
        target.id,
        target.organization_id,
        {"source_organization_id": str(row.organization_id), "previous_device_id": str(row.id)},
    )
    await commit(session, row)
    await session.refresh(target)
    return {"source": await fleet_response(session, row), "device": await fleet_response(session, target)}


@router.post("/platform/devices/{device_id}/transfer", tags=["Platform"])
async def fleet_transfer(device_id: UUID, body: DeviceTransfer, session: Session, actor: Actor):
    await lock_administration(session)
    row = await fleet_record(session, actor, device_id)
    await available_tenant(session, body.organization_id)
    return await transfer_registration(session, actor, row, body)
