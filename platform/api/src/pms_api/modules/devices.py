from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, Request
from sqlalchemy import Text, func, or_, select
from sqlalchemy.dialects.postgresql import insert

from pms_api.core.common import digest, new_token, now, require, required, token_hash
from pms_api.core.dependencies import Session
from pms_api.database.models import (
    ActivityEvent,
    Department,
    Device,
    DeviceModelSelection,
    Organization,
    PlatformSettings,
    TelemetrySample,
)
from pms_api.database.session import lock_administration
from pms_api.modules.common import audit, commit, directory_page, page, public
from pms_api.modules.configuration import resolved_configuration
from pms_api.modules.management import Limit, validate_department
from pms_api.modules.patching import changes, update_fields
from pms_api.modules.schemas import DeviceCreate, DevicePatch, Enrollment, EventBatch, Heartbeat
from pms_api.security.access import (
    Actor,
    device_access,
    organization_access,
    platform_access,
    scoped_query,
    scoped_record,
)

router = APIRouter()
SUMMARY = {
    "device_unique_id",
    "preferred_language",
    "id",
    "organization_id",
    "department_id",
    "name",
    "device_type",
    "is_active",
    "enrollment_state",
    "created_at",
    "enrolled_at",
    "last_seen_at",
    "last_activity_at",
    "registered_at",
}


def device_view(row, summary=False, offline_after_seconds=180):
    values = public(
        row,
        exclude={"latest_health", "credential_issued_at", "credential_revoked_at", "credential_version"}
        if summary
        else set(),
    )
    result = {k: v for k, v in values.items() if k in SUMMARY} if summary else values
    if not summary:
        result["management_etag"] = management_etag(row)
    result["summary_only"] = summary
    result["connectivity"] = (
        "online"
        if row.last_seen_at and row.last_seen_at >= now() - timedelta(seconds=offline_after_seconds)
        else "offline"
    )
    result["credential_status"] = (
        "revoked"
        if row.credential_revoked_at
        else "active"
        if row.credential_hash and row.enrollment_state == "enrolled"
        else "not_issued"
    )
    return result


def management_etag(row):
    # Stable across heartbeats. Compare under the device row lock before a mutation.
    fields = (
        "id",
        "organization_id",
        "status_reason",
        "name",
        "device_type",
        "department_id",
        "is_active",
        "details",
        "location",
        "contact_name",
        "contact_email",
        "contact_phone",
        "preferred_language",
        "enrollment_state",
        "enrollment_expires_at",
        "credential_version",
        "credential_revoked_at",
    )
    return digest({field: getattr(row, field) for field in fields})


def check_etag(row, expected):
    require(
        expected is None or expected == management_etag(row),
        "version_conflict",
        "Device changed; refresh before retrying",
        409,
    )


def validate_details(values):
    require(isinstance(values, dict), "invalid_details", "Device details must be an object")
    if "inference" in values:
        from pydantic import ValidationError
        from training_contracts.inference import Binding

        try:
            if values["inference"] is not None:
                values["inference"] = Binding.model_validate(values["inference"]).model_dump(mode="json")
        except ValidationError:
            require(False, "invalid_details", "Invalid inference host binding")
        values = {key: value for key, value in values.items() if key != "inference"}
    require(
        set(values) <= {"model", "serial_number", "os_name", "os_version", "agent_version", "notes"},
        "invalid_details",
        "Unsupported device details",
    )
    require(
        all(
            value is None
            or isinstance(value, str)
            and len(value) <= (4000 if key == "notes" else 256)
            and "\x00" not in value
            and not any(0xD800 <= ord(c) <= 0xDFFF for c in value)
            for key, value in values.items()
        ),
        "invalid_details",
        "Device details must be bounded text",
    )


async def present_devices(session, rows, summary, offline_seconds, platform=False):
    items = [device_view(row, summary, offline_seconds) for row in rows]
    if not rows:
        return items
    if platform:
        configured_ids = set(
            await session.scalars(
                select(DeviceModelSelection.device_id).where(
                    DeviceModelSelection.device_id.in_({row.id for row in rows}),
                    or_(
                        DeviceModelSelection.llm_model_id.is_not(None),
                        DeviceModelSelection.asr_model_id.is_not(None),
                        DeviceModelSelection.tts_model_id.is_not(None),
                        DeviceModelSelection.video_model_id.is_not(None),
                    ),
                )
            )
        )
        names = dict(
            (
                await session.execute(
                    select(Organization.id, Organization.name).where(
                        Organization.id.in_({row.organization_id for row in rows})
                    )
                )
            ).all()
        )
        for item, row in zip(items, rows, strict=True):
            item["organization_name"] = names.get(item["organization_id"])
            item["management_etag"] = management_etag(row)
            item["models_configured"] = row.id in configured_ids
    else:
        departments = dict(
            (
                await session.execute(
                    select(Department.id, Department.name).where(
                        Department.id.in_({row.department_id for row in rows if row.department_id})
                    )
                )
            ).all()
        )
        for item, row in zip(items, rows, strict=True):
            item["department_name"] = departments.get(row.department_id)
    return items


async def device_response(session, row):
    settings = required(await session.get(PlatformSettings, 1))
    return (
        await present_devices(session, [row], False, int(settings.device_defaults["offline_after_seconds"]))
    )[0]


async def validate_language(session, code):
    # Serialize catalog edits and selections to prevent concurrent removal races.
    platform = required(await session.get(PlatformSettings, 1, with_for_update=True))
    require(
        code is None or any(x["code"] == code and x["is_active"] for x in platform.languages),
        "invalid_language",
        "Select an active platform language",
    )


async def validate_assignment(session, org_id, dept_id):
    await validate_department(session, org_id, dept_id)


@router.get("/organizations/{organization_id}/devices", tags=["Devices"])
async def devices(
    organization_id: UUID,
    request: Request,
    session: Session,
    actor: Actor,
    limit: Limit = 50,
    cursor: str | None = None,
    q: Annotated[str | None, Query(max_length=128)] = None,
    department_id: UUID | None = None,
    device_type: Literal["manikin", "laptop", "raspberry_pi", "other"] | None = None,
    is_active: bool | None = None,
    enrollment_state: Literal["pending", "enrolled", "retired", "current"] | None = None,
    online: bool | None = None,
    sort_by: Literal["id", "name", "created_at", "last_seen_at"] = "id",
    sort_order: Literal["asc", "desc"] = "asc",
    include_total: bool = False,
):
    access = await organization_access(session, actor, organization_id, "org.devices.summary.read")
    return await list_device_records(
        request,
        session,
        scoped_query(Device, access),
        f"{organization_id}|{access.department_id}",
        access.role == "org_trainee",
        False,
        limit,
        cursor,
        q,
        department_id,
        device_type,
        is_active,
        enrollment_state,
        online,
        sort_by,
        sort_order,
        include_total,
    )


@router.get("/platform/devices", tags=["Platform"])
async def platform_devices(
    request: Request,
    session: Session,
    actor: Actor,
    limit: Limit = 50,
    cursor: str | None = None,
    q: Annotated[str | None, Query(max_length=128)] = None,
    department_id: UUID | None = None,
    device_type: Literal["manikin", "laptop", "raspberry_pi", "other"] | None = None,
    is_active: bool | None = None,
    enrollment_state: Literal["pending", "enrolled", "retired", "current"] | None = None,
    online: bool | None = None,
    sort_by: Literal["id", "name", "created_at", "last_seen_at"] = "id",
    sort_order: Literal["asc", "desc"] = "asc",
    include_total: bool = False,
    organization_id: UUID | None = None,
    exclude_organization_id: UUID | None = None,
):
    platform_access(actor, "platform.health.read")
    query = (
        select(Device)
        .join(Organization, Organization.id == Device.organization_id)
        .where(Organization.archived_at.is_(None))
    )
    if organization_id:
        query = query.where(Device.organization_id == organization_id)
    if exclude_organization_id:
        query = query.where(Device.organization_id != exclude_organization_id)
    return await list_device_records(
        request,
        session,
        query,
        f"platform|{organization_id}"
        + (f"|exclude:{exclude_organization_id}" if exclude_organization_id else ""),
        True,
        True,
        limit,
        cursor,
        q,
        department_id,
        device_type,
        is_active,
        enrollment_state,
        online,
        sort_by,
        sort_order,
        include_total,
    )


@router.get("/platform/devices/{device_id}", tags=["Platform"])
async def platform_device_detail(device_id: UUID, session: Session, actor: Actor):
    platform_access(actor, "platform.health.read")
    row = required(
        await session.scalar(
            select(Device)
            .join(Organization, Organization.id == Device.organization_id)
            .where(Device.id == device_id, Organization.archived_at.is_(None))
        )
    )
    settings = required(await session.get(PlatformSettings, 1))
    return (
        await present_devices(
            session, [row], True, int(settings.device_defaults["offline_after_seconds"]), platform=True
        )
    )[0]


async def list_device_records(
    request,
    session,
    query,
    scope,
    summary,
    platform_scope,
    limit,
    cursor,
    q,
    department_id,
    device_type,
    is_active,
    enrollment_state,
    online,
    sort_by,
    sort_order,
    include_total,
):
    platform = required(await session.get(PlatformSettings, 1))
    offline_seconds = int(platform.device_defaults["offline_after_seconds"])
    online_cutoff = now() - timedelta(seconds=offline_seconds)
    if q:
        query = query.where(
            or_(
                Device.name.icontains(q, autoescape=True),
                Device.location.icontains(q, autoescape=True)
                if not summary
                else Device.name.icontains(q, autoescape=True),
                Device.id.cast(Text).icontains(q, autoescape=True),
                Device.device_unique_id.icontains(q, autoescape=True),
            )
        )
    if department_id:
        query = query.where(Device.department_id == department_id)
    if device_type:
        query = query.where(Device.device_type == device_type)
    if is_active is not None:
        query = query.where(Device.is_active == is_active)
    if enrollment_state:
        query = query.where(
            Device.enrollment_state != "retired"
            if enrollment_state == "current"
            else Device.enrollment_state == enrollment_state
        )
    if online is not None:
        query = query.where(
            Device.last_seen_at >= online_cutoff
            if online
            else or_(Device.last_seen_at.is_(None), Device.last_seen_at < online_cutoff)
        )
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    expressions = {
        "id": Device.id,
        "name": Device.name,
        "created_at": Device.created_at,
        "last_seen_at": func.coalesce(Device.last_seen_at, epoch),
    }
    binding = (
        f"devices|{scope}|{q}|{department_id}|{device_type}|"
        f"{is_active}|{enrollment_state}|{online}|{sort_by}|{sort_order}"
    )
    rows, next_cursor, has_more, total = await directory_page(
        session,
        query,
        Device,
        limit=limit,
        cursor=cursor,
        sort=sort_by,
        direction=sort_order,
        expression=expressions[sort_by],
        binding=binding,
        secret=request.app.state.settings.token_pepper.get_secret_value(),
        kind="uuid" if sort_by == "id" else "datetime" if sort_by.endswith("_at") else "string",
        include_total=include_total,
        legacy_id=True,
        value_getter=(lambda row: row.last_seen_at or epoch) if sort_by == "last_seen_at" else None,
    )
    return {
        "items": await present_devices(session, rows, summary, offline_seconds, platform=platform_scope),
        "next_cursor": next_cursor,
        "has_more": has_more,
        **({"total": total} if include_total else {}),
    }


@router.get("/organizations/{organization_id}/devices/{device_id}", tags=["Devices"])
async def device_detail(organization_id: UUID, device_id: UUID, session: Session, actor: Actor):
    access = await organization_access(session, actor, organization_id, "org.devices.summary.read")
    row = await scoped_record(session, Device, access, device_id)
    platform = required(await session.get(PlatformSettings, 1))
    return (
        await present_devices(
            session,
            [row],
            access.role == "org_trainee",
            int(platform.device_defaults["offline_after_seconds"]),
        )
    )[0]


@router.post("/organizations/{organization_id}/devices", status_code=201, tags=["Devices"])
async def device_create(organization_id: UUID, body: DeviceCreate, session: Session, actor: Actor):
    require(
        False, "platform_registration_required", "Only a platform administrator can register devices", 403
    )
    await lock_administration(session)
    await organization_access(session, actor, organization_id, "org.devices.manage")
    await validate_language(session, body.preferred_language)
    await validate_assignment(session, organization_id, body.department_id)
    validate_details(body.details)
    row = Device(
        id=uuid4(), organization_id=organization_id, created_by=actor.id, **body.model_dump(mode="python")
    )
    session.add(row)
    await audit(session, actor, "device.registered", "device", row.id, organization_id)
    await commit(session, row)
    return await device_response(session, row)


@router.patch("/organizations/{organization_id}/devices/{device_id}", tags=["Devices"])
async def device_update(
    organization_id: UUID, device_id: UUID, body: DevicePatch, session: Session, actor: Actor
):
    await lock_administration(session)
    access = await organization_access(session, actor, organization_id, "org.devices.manage")
    if "preferred_language" in body.model_fields_set:
        await validate_language(session, body.preferred_language)
    row = await scoped_record(session, Device, access, device_id, True)
    check_etag(row, body.expected_etag)
    values = changes(body, {"expected_etag"})
    require(row.enrollment_state != "retired", "device_retired", "Retired devices cannot be edited", 409)
    if "details" in values:
        validate_details(values["details"])
        values["details"] = {**row.details, **values["details"]}
    assignment_changed = any(key in values and values[key] != getattr(row, key) for key in ("department_id",))
    if assignment_changed or (values.get("is_active") is True and not row.is_active):
        await validate_assignment(
            session,
            organization_id,
            values.get("department_id", row.department_id),
        )
    update_fields(row, values)
    row.status_changed_by = actor.id
    await audit(
        session, actor, "device.updated", "device", row.id, organization_id, {"fields": sorted(values)}
    )
    await commit(session, row)
    return await device_response(session, row)


@router.post("/organizations/{organization_id}/devices/{device_id}/enrollment", tags=["Devices"])
async def enrollment_issue(
    organization_id: UUID,
    device_id: UUID,
    request: Request,
    session: Session,
    actor: Actor,
    expected_etag: Annotated[str | None, Query(pattern=r"^[0-9a-f]{64}$")] = None,
):
    await lock_administration(session)
    access = await organization_access(session, actor, organization_id, "org.devices.manage")
    row = await scoped_record(session, Device, access, device_id, True)
    check_etag(row, expected_etag)
    platform = required(await session.get(PlatformSettings, 1))
    require(not platform.maintenance_mode, "maintenance_mode", "New enrollment is paused", 503)
    require(
        row.is_active and row.enrollment_state != "retired",
        "device_inactive",
        "Activate a non-retired device before enrollment",
        409,
    )
    await validate_department(session, organization_id, row.department_id)
    token = new_token("enr_")
    row.enrollment_state = "pending"
    row.credential_hash = None
    row.enrollment_token_hash = token_hash(token, request.app.state.settings.token_pepper.get_secret_value())
    row.enrollment_expires_at = now() + timedelta(minutes=15)
    row.enrollment_attempt_count = 0
    await audit(session, actor, "device.enrollment_issued", "device", row.id, organization_id)
    await commit(session, row)
    return {"device_id": row.id, "enrollment_token": token, "expires_at": row.enrollment_expires_at}


@router.post("/device/enroll", tags=["Device agent"])
async def enroll(body: Enrollment, request: Request, session: Session):
    await lock_administration(session)
    settings = request.app.state.settings
    value = token_hash(body.token.get_secret_value(), settings.token_pepper.get_secret_value())
    row = await session.scalar(select(Device).where(Device.enrollment_token_hash == value).with_for_update())
    require(
        row
        and row.enrollment_expires_at
        and row.enrollment_expires_at > now()
        and row.enrollment_state == "pending",
        "invalid_enrollment",
        "Enrollment token is invalid or expired",
        409,
    )
    assert row is not None
    require(
        body.device_identifier is None
        or body.device_identifier.lower() in {str(row.id), row.device_unique_id.lower()},
        "invalid_enrollment",
        "Device ID and enrollment token do not match",
        409,
    )
    platform = required(await session.get(PlatformSettings, 1))
    org = required(await session.get(Organization, row.organization_id))
    require(row.is_active and org.is_active, "device_inactive", "Device or organization is inactive", 409)
    require(not platform.maintenance_mode, "maintenance_mode", "New enrollment is paused", 503)
    await validate_department(session, row.organization_id, row.department_id)
    token = new_token("dev_")
    row.enrollment_attempt_count += 1
    row.enrollment_state = "enrolled"
    row.enrollment_token_hash = None
    row.enrollment_expires_at = None
    row.credential_hash = token_hash(token, settings.token_pepper.get_secret_value())
    row.credential_revoked_at = None
    row.enrolled_at = row.enrolled_at or now()
    row.last_seen_at = now()
    row.capabilities = {
        key: value
        for key, value in body.capabilities.items()
        if key not in {"local_models", "local_models_received_at", "local_models_source"}
    }
    await audit(session, None, "device.enrolled", "device", row.id, row.organization_id)
    await commit(session, row)
    return {
        **pairing_identity(row, org),
        "credential": token,
        "credential_version": row.credential_version,
    }


def pairing_identity(device, organization):
    return {
        "device_id": device.id,
        "device_unique_id": device.device_unique_id,
        "device_name": device.name,
        "organization_id": organization.id,
        "organization_name": organization.name,
        "department_id": device.department_id,
    }


@router.get("/device/identity", tags=["Device agent"])
async def paired_identity(session: Session, actor: Actor):
    device = await device_access(session, actor)
    organization = required(await session.get(Organization, device.organization_id))
    return pairing_identity(device, organization)


@router.post("/organizations/{organization_id}/devices/{device_id}/revoke", tags=["Devices"])
async def revoke(
    organization_id: UUID,
    device_id: UUID,
    session: Session,
    actor: Actor,
    expected_etag: Annotated[str | None, Query(pattern=r"^[0-9a-f]{64}$")] = None,
):
    await lock_administration(session)
    access = await organization_access(session, actor, organization_id, "org.devices.manage")
    row = await scoped_record(session, Device, access, device_id, True)
    check_etag(row, expected_etag)
    row.credential_hash = None
    row.credential_revoked_at = now()
    row.enrollment_token_hash = None
    row.enrollment_expires_at = None
    await audit(session, actor, "device.credential_revoked", "device", row.id, organization_id)
    await commit(session, row)
    return await device_response(session, row)


@router.post("/organizations/{organization_id}/devices/{device_id}/retire", tags=["Devices"])
async def retire(
    organization_id: UUID,
    device_id: UUID,
    session: Session,
    actor: Actor,
    expected_etag: Annotated[str | None, Query(pattern=r"^[0-9a-f]{64}$")] = None,
):
    await lock_administration(session)
    access = await organization_access(session, actor, organization_id, "org.devices.manage")
    row = await scoped_record(session, Device, access, device_id, True)
    check_etag(row, expected_etag)
    row.enrollment_state = "retired"
    row.is_active = False
    row.status_changed_by = actor.id
    row.credential_hash = None
    row.credential_revoked_at = now()
    row.enrollment_token_hash = None
    row.enrollment_expires_at = None
    await audit(session, actor, "device.retired", "device", row.id, organization_id)
    await commit(session, row)
    return await device_response(session, row)


@router.delete("/organizations/{organization_id}/devices/{device_id}", tags=["Devices"])
async def retire_delete(
    organization_id: UUID,
    device_id: UUID,
    session: Session,
    actor: Actor,
    expected_etag: Annotated[str | None, Query(pattern=r"^[0-9a-f]{64}$")] = None,
):
    return await retire(organization_id, device_id, session, actor, expected_etag)


@router.get("/device/config", tags=["Device agent"])
async def config(session: Session, actor: Actor):
    device = await device_access(session, actor, False)
    configuration = await resolved_configuration(session, device)
    if not configuration["is_active"]:
        return {
            "device_id": device.id,
            "is_active": False,
            "allowed_actions": ["health", "status"],
            "configuration_hash": configuration["configuration_hash"],
        }
    until = now() + timedelta(hours=configuration["policy"]["offline_authorization_hours"])
    device.offline_authorized_until = until
    await commit(session)
    return {**configuration, "offline_authorized_until": until}


@router.get("/organizations/{organization_id}/devices/{device_id}/configuration", tags=["Devices"])
async def human_configuration(organization_id: UUID, device_id: UUID, session: Session, actor: Actor):
    access = await organization_access(session, actor, organization_id, "org.configuration.read")
    row = await scoped_record(session, Device, access, device_id)
    return await resolved_configuration(session, row)


@router.post("/device/heartbeat", tags=["Device agent"])
async def heartbeat(body: Heartbeat, session: Session, actor: Actor):
    device = await device_access(session, actor, False)
    device = required(await session.get(Device, device.id, with_for_update=True))
    timestamp = now()
    platform = required(await session.get(PlatformSettings, 1))
    org = required(await session.get(Organization, device.organization_id))
    old = device.latest_health or {}
    duplicate = old.get("boot_id") == str(body.boot_id) and body.sequence_number <= old.get(
        "sequence_number", -1
    )
    if old.get("boot_id") and old["boot_id"] != str(body.boot_id):
        duplicate = bool(
            await session.scalar(
                select(TelemetrySample.id)
                .where(TelemetrySample.device_id == device.id, TelemetrySample.boot_id == body.boot_id)
                .limit(1)
            )
        )
    device.last_seen_at = timestamp
    if not duplicate:
        device.latest_health = {
            "boot_id": str(body.boot_id),
            "sequence_number": body.sequence_number,
            "observed_at": body.observed_at.isoformat() if body.observed_at else None,
            "received_at": timestamp.isoformat(),
            "metrics": body.metrics.model_dump(exclude_none=True),
        }
        if body.capabilities is not None:
            # Local inventory is accepted only through the validated, device-authenticated
            # report endpoint. Routine heartbeats must not overwrite or invent it.
            reserved = {
                key: value
                for key, value in device.capabilities.items()
                if key in {"local_models", "local_models_received_at", "local_models_source"}
            }
            device.capabilities = {
                key: value
                for key, value in body.capabilities.items()
                if key not in reserved
                and key not in {"local_models", "local_models_received_at", "local_models_source"}
            } | reserved
        if body.applied_configuration_hash:
            config = await resolved_configuration(session, device)
            require(
                config["configuration_hash"] == body.applied_configuration_hash
                and config["profile_revision_id"]
                == (str(body.applied_profile_revision_id) if body.applied_profile_revision_id else None),
                "configuration_mismatch",
                "Refresh configuration before acknowledging it",
                409,
            )
            device.applied_configuration_hash = body.applied_configuration_hash
            device.applied_profile_revision_id = body.applied_profile_revision_id
        device.config_error = body.config_error
        if (
            not device.last_telemetry_at
            or (timestamp - device.last_telemetry_at).total_seconds()
            >= platform.device_defaults["telemetry_sample_seconds"]
            or old.get("boot_id") != str(body.boot_id)
        ):
            days = min(
                org.policy_settings["telemetry_retention_days"],
                platform.policy_limits["telemetry_retention_days"],
            )
            stmt = (
                insert(TelemetrySample)
                .values(
                    id=uuid4(),
                    organization_id=device.organization_id,
                    device_id=device.id,
                    department_id=device.department_id,
                    boot_id=body.boot_id,
                    sequence_number=body.sequence_number,
                    observed_at=body.observed_at,
                    received_at=timestamp,
                    metrics=body.metrics.model_dump(exclude_none=True),
                    expires_at=timestamp + timedelta(days=days),
                )
                .on_conflict_do_nothing(
                    index_elements=["organization_id", "device_id", "boot_id", "sequence_number"]
                )
            )
            await session.execute(stmt)
            device.last_telemetry_at = timestamp
    await commit(session)
    return {
        "accepted": True,
        "duplicate": duplicate,
        "server_time": timestamp,
        "heartbeat_seconds": platform.device_defaults["heartbeat_seconds"],
    }


@router.post("/device/events", tags=["Device agent"])
async def events(body: EventBatch, session: Session, actor: Actor):
    device = await device_access(session, actor, False)
    config = await resolved_configuration(session, device)
    if not config["is_active"]:
        require(
            all(e.event_type in {"device.status", "device.error"} for e in body.events),
            "device_inactive",
            "Inactive devices can report only status/errors",
            409,
        )
    timestamp = now()
    accepted = 0
    for event in body.events:
        stmt = insert(ActivityEvent).values(
            id=uuid4(),
            organization_id=device.organization_id,
            department_id=device.department_id,
            device_id=device.id,
            actor_type="device",
            category="operational",
            event_type=event.event_type,
            severity=event.severity,
            source_event_id=event.source_event_id,
            occurred_at=event.occurred_at,
            received_at=timestamp,
            details={"code": event.code, "historical": event.historical},
            expires_at=timestamp + timedelta(days=config["policy"]["operational_retention_days"]),
        )
        result = await session.execute(
            stmt.on_conflict_do_nothing(
                index_elements=["organization_id", "device_id", "source_event_id"],
                index_where=ActivityEvent.source_event_id.is_not(None),
            ).returning(ActivityEvent.id)
        )
        if result.scalar_one_or_none():
            accepted += 1
            if not event.historical and event.event_type not in {"device.status", "device.error"}:
                device.last_activity_at = timestamp
    await commit(session)
    return {"accepted": accepted, "duplicates": len(body.events) - accepted}


@router.get("/organizations/{organization_id}/devices/{device_id}/telemetry", tags=["Telemetry"])
async def telemetry(
    organization_id: UUID,
    device_id: UUID,
    session: Session,
    actor: Actor,
    limit: Limit = 50,
    cursor: UUID | None = None,
):
    access = await organization_access(session, actor, organization_id, "org.telemetry.read")
    # Historical department context is checked on each sample, independently of current device assignment.
    query = scoped_query(TelemetrySample, access).where(
        TelemetrySample.device_id == device_id, TelemetrySample.expires_at > now()
    )
    rows, next_cursor = await page(session, query, TelemetrySample, limit, cursor)
    return {"items": [public(r) for r in rows], "next_cursor": next_cursor}


@router.get("/languages", tags=["Devices"])
async def available_languages(session: Session, actor: Actor):
    platform = required(await session.get(PlatformSettings, 1))
    return {"default": "en", "items": [x for x in platform.languages if x["is_active"]]}
