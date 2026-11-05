import json
from dataclasses import dataclass
from importlib.resources import files
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pms_api.core.common import AppError, require, required, token_hash
from pms_api.core.dependencies import Session
from pms_api.database.models import (
    Department,
    Device,
    MemberCapability,
    Membership,
    Organization,
    PlatformSettings,
    User,
)

CATALOG = json.loads(files("pms_api.security").joinpath("default-roles.json").read_text())
GRANTS = {role["code"]: frozenset(role["permissions"]) for role in CATALOG["roles"]}
CLINICAL_CAPABILITIES = frozenset(
    {"org.clinical.author", "org.clinical.review", "org.training.instruct", "org.clinical.read"}
)
bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    user: User | None = None
    device: Device | None = None
    claims: dict | None = None
    session_id: UUID | None = None
    authentication_method: str | None = None

    @property
    def id(self):
        if self.user:
            return self.user.id
        assert self.device is not None
        return self.device.id


@dataclass(frozen=True)
class Access:
    principal: Principal
    organization: Organization
    role: str
    department_id: UUID | None
    membership_id: UUID


def capability_eligible(membership: Membership, capability: str) -> bool:
    if capability in {"org.clinical.author", "org.clinical.review"}:
        return membership.role in {"org_admin", "org_user"} and membership.department_id is None
    if capability == "org.training.instruct":
        return membership.role in {"org_admin", "org_user"}
    return capability == "org.clinical.read" and membership.role in {"org_admin", "org_user", "org_read_only"}


async def effective_permissions(session: AsyncSession, membership: Membership) -> set[str]:
    permissions = set(GRANTS.get(membership.role, ()))
    assigned = await session.scalars(
        select(MemberCapability.capability).where(
            MemberCapability.organization_id == membership.organization_id,
            MemberCapability.membership_id == membership.id,
            MemberCapability.revoked_at.is_(None),
        )
    )
    permissions.update(capability for capability in assigned if capability_eligible(membership, capability))
    return permissions


async def authentication(
    request: Request,
    session: Session,
    credential: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Principal:
    if not credential or credential.scheme.lower() != "bearer":
        raise AppError(401, "authentication_required", "Bearer authentication is required")
    token = credential.credentials
    if len(token) > 16384:
        raise AppError(401, "invalid_token", "Invalid access token")
    if token.startswith("dev_"):
        value = token_hash(token, request.app.state.settings.token_pepper.get_secret_value())
        device = await session.scalar(
            select(Device).where(
                Device.credential_hash == value,
                Device.enrollment_state == "enrolled",
                Device.credential_revoked_at.is_(None),
            )
        )
        if not device:
            raise AppError(401, "invalid_device_credential", "Invalid device credential")
        return Principal(device=device)
    if token.startswith(("pms_", "web_")):
        from pms_api.security.local_auth import verify_access, verify_browser_session

        verifier = verify_browser_session if token.startswith("web_") else verify_access
        user, local_session = await verifier(session, token, request.app.state.settings)
        return Principal(
            user=user,
            session_id=local_session.id,
            authentication_method="local",
        )
    claims = await request.app.state.oidc.verify(token)
    user = await session.scalar(
        select(User).where(User.identity_issuer == claims["iss"], User.identity_subject == claims["sub"])
    )
    if not user:
        raise AppError(403, "identity_not_registered", "Synchronize your verified identity first")
    require(
        user.is_active and user.archived_at is None,
        "identity_inactive",
        "This identity is inactive",
        403,
    )
    return Principal(user=user, claims=claims, authentication_method="oidc")


Actor = Annotated[Principal, Depends(authentication)]


def human(actor: Principal) -> User:
    require(actor.user is not None, "human_identity_required", "A human identity is required", 403)
    assert actor.user is not None
    require(
        actor.user.is_active and actor.user.archived_at is None,
        "identity_inactive",
        "This identity is inactive",
        403,
    )
    return actor.user


def platform_access(actor: Principal, permission: str):
    user = human(actor)
    require(permission in GRANTS.get(user.platform_role, ()), "permission_denied", "Permission denied", 403)


async def organization_access(
    session: AsyncSession,
    actor: Principal,
    organization_id: UUID,
    permission: str,
    allow_inactive: bool = False,
    lock_membership: bool = False,
) -> Access:
    user = human(actor)
    if lock_membership:
        user = required(
            await session.scalar(
                select(User)
                .where(User.id == user.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        require(
            user.is_active and user.archived_at is None,
            "identity_inactive",
            "This identity is inactive",
            403,
        )
    query = (
        select(Membership)
        .where(
            Membership.organization_id == organization_id,
            Membership.user_id == user.id,
            Membership.is_active.is_(True),
            Membership.invitation_status == "accepted",
            Membership.archived_at.is_(None),
        )
        .execution_options(populate_existing=True)
    )
    if lock_membership:
        query = query.with_for_update()
    membership = await session.scalar(query)
    org = required(await session.get(Organization, organization_id, populate_existing=True))
    require(
        org is not None and org.archived_at is None and membership is not None,
        "not_found",
        "Organization not found",
        404,
    )
    assert org is not None
    assert membership is not None
    if permission in CLINICAL_CAPABILITIES:
        require(
            capability_eligible(membership, permission),
            "permission_denied",
            "Permission denied",
            403,
        )
        if permission not in GRANTS[membership.role]:
            assigned = await session.scalar(
                select(MemberCapability.id).where(
                    MemberCapability.organization_id == organization_id,
                    MemberCapability.membership_id == membership.id,
                    MemberCapability.capability == permission,
                    MemberCapability.revoked_at.is_(None),
                )
            )
            require(assigned is not None, "permission_denied", "Permission denied", 403)
    else:
        require(permission in GRANTS[membership.role], "permission_denied", "Permission denied", 403)
    require(org.is_active or allow_inactive, "organization_inactive", "Organization is inactive", 409)
    if membership.department_id:
        department = required(await session.get(Department, membership.department_id, populate_existing=True))
        require(
            department is not None and department.is_active and department.archived_at is None,
            "department_inactive",
            "Department is inactive",
            409,
        )
    return Access(actor, org, membership.role, membership.department_id, membership.id)


async def device_access(
    session: AsyncSession, actor: Principal, operational: bool = True, allow_maintenance: bool = False
) -> Device:
    require(actor.device is not None, "device_identity_required", "A device identity is required", 403)
    device = actor.device
    assert device is not None
    org = required(await session.get(Organization, device.organization_id, populate_existing=True))
    dept = (
        await session.get(Department, device.department_id, populate_existing=True)
        if device.department_id
        else None
    )
    require(
        org.archived_at is None and (dept is None or dept.archived_at is None),
        "device_inactive",
        "Device or its organization/department is inactive",
        409,
    )
    if operational:
        require(
            device.enrollment_state == "enrolled"
            and device.credential_hash
            and not device.credential_revoked_at,
            "device_not_enrolled",
            "Enroll the device with an active credential before processing",
            409,
        )
        platform = required(await session.get(PlatformSettings, 1, populate_existing=True))
        require(
            device.is_active
            and org.is_active
            and org.archived_at is None
            and (dept is None or (dept.is_active and dept.archived_at is None)),
            "device_inactive",
            "Device or its organization/department is inactive",
            409,
        )
        require(
            allow_maintenance or not platform.maintenance_mode,
            "maintenance_mode",
            "New processing is paused",
            503,
        )
    return device


def scoped_query(model, access: Access):
    query = select(model).where(model.organization_id == access.organization.id)
    if access.department_id is not None:
        if model is Department:
            query = query.where(model.id == access.department_id)
        elif hasattr(model, "department_id"):
            query = query.where(model.department_id == access.department_id)
        else:
            raise AppError(403, "scope_unavailable", "This resource requires organization-wide access")
    return query


async def scoped_record(session, model, access: Access, record_id: UUID, lock: bool = False):
    query = scoped_query(model, access).where(model.id == record_id)
    if lock:
        query = query.with_for_update()
    row = await session.scalar(query)
    require(row is not None, "not_found", "Record not found", 404)
    assert row is not None
    return row


async def reload_actor(session, user_id=None, device_id=None, credential_version=None):
    if user_id:
        user = required(await session.get(User, user_id, populate_existing=True))
        require(
            user is not None and user.is_active and user.archived_at is None,
            "identity_inactive",
            "Identity is inactive",
            403,
        )
        assert user is not None
        return Principal(user=user)
    device = required(await session.get(Device, device_id, populate_existing=True))
    require(
        device is not None
        and device.credential_hash
        and device.enrollment_state == "enrolled"
        and not device.credential_revoked_at
        and (credential_version is None or device.credential_version == credential_version),
        "invalid_device_credential",
        "Device credential was revoked",
        401,
    )
    assert device is not None
    return Principal(device=device)
