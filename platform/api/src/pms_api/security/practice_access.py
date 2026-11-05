"""Device-owned Practice execution, without granting tenant administration rights."""

from sqlalchemy import select

from pms_api.core.common import require, required
from pms_api.database.models import Device, Organization
from pms_api.security.access import Access, device_access, organization_access, reload_actor


def owner_filter(model, actor):
    return model.device_id == actor.id if actor.device else model.user_id == actor.id


def owner_values(actor):
    return {"device_id": actor.id, "user_id": None} if actor.device else {"user_id": actor.id}


def is_owner(row, actor):
    return row.device_id == actor.id if actor.device else row.user_id == actor.id


def actor_identity(actor):
    return (
        {"device_id": actor.id, "credential_version": actor.device.credential_version}
        if actor.device
        else {"user_id": actor.id}
    )


async def execution_access(session, actor, org, permission, *, lock=False):
    if actor.device is None:
        return await organization_access(session, actor, org, permission, lock_membership=lock)
    require(
        permission in {"org.processing.execute", "org.results.read"},
        "permission_denied",
        "Device credentials cannot administer tenants",
        403,
    )
    identity = actor_identity(actor)
    require(actor.device.organization_id == org, "not_found", "Organization not found", 404)
    if lock:
        await session.get(Organization, org, with_for_update=True, populate_existing=True)
        await session.scalar(select(Device).where(Device.id == actor.id).with_for_update())
        actor = await reload_actor(session, **identity)
    device = await device_access(session, actor)
    organization = required(await session.get(Organization, org, populate_existing=True))
    return Access(actor, organization, "device", device.department_id, device.id)
