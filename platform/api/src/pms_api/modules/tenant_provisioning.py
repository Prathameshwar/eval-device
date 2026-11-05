"""Atomic platform onboarding of a tenant, administrator, and device."""

from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Request, Response
from pydantic import EmailStr, Field, SecretStr, model_validator
from sqlalchemy import select

from pms_api.core.common import now, require, required
from pms_api.core.dependencies import Session
from pms_api.database.models import Device, LocalCredential, Membership, Organization, PlatformSettings, User
from pms_api.database.session import lock_administration
from pms_api.modules.common import audit, commit, public
from pms_api.modules.configuration import within
from pms_api.modules.device_management import (
    available_tenant,
    fleet_response,
    reserve_device_identity,
    revoke_registration,
)
from pms_api.modules.devices import check_etag
from pms_api.modules.patient_catalog import seed_tenant_clinical_defaults
from pms_api.modules.schemas import DeviceUniqueId, Input, Name, OrganizationCreate
from pms_api.modules.subscriptions import active_plan
from pms_api.security.access import Actor, platform_access
from pms_api.security.local_auth import hash_password, normalize_email

router = APIRouter(tags=["Platform"])
Etag = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class ProvisionDevice(Input):
    kind: Literal["new", "existing"]
    device_unique_id: DeviceUniqueId | None = None
    name: Name | None = None
    device_type: Literal["manikin", "laptop"] | None = None
    device_id: UUID | None = None
    expected_etag: Etag | None = None

    @model_validator(mode="after")
    def complete_choice(self):
        valid = (
            self.kind == "new"
            and self.name is not None
            and self.device_type is not None
            and self.device_unique_id is not None
            and self.device_id is None
            and self.expected_etag is None
        ) or (
            self.kind == "existing"
            and self.device_id is not None
            and self.expected_etag is not None
            and self.name is None
            and self.device_type is None
            and self.device_unique_id is None
        )
        if not valid:
            raise ValueError("Complete one device choice")
        return self


class ProvisionAdministrator(Input):
    kind: Literal["new", "existing"]
    email: EmailStr | None = None
    display_name: Name | None = None
    password: SecretStr | None = Field(default=None, min_length=12, max_length=1024)
    user_id: UUID | None = None

    @model_validator(mode="after")
    def complete_choice(self):
        valid = (
            self.kind == "new"
            and self.email is not None
            and self.display_name is not None
            and self.password is not None
            and self.user_id is None
        ) or (
            self.kind == "existing"
            and self.user_id is not None
            and self.email is None
            and self.display_name is None
            and self.password is None
        )
        if not valid:
            raise ValueError("Complete one administrator choice")
        return self


class ProvisionTenant(Input):
    tenant: OrganizationCreate
    device: ProvisionDevice
    administrator: ProvisionAdministrator


@router.post("/platform/organizations/provision", status_code=201)
async def provision_tenant(
    body: ProvisionTenant, request: Request, response: Response, session: Session, actor: Actor
):
    platform_access(actor, "platform.organizations.manage")
    platform_access(actor, "platform.organization_admins.manage")
    platform_access(actor, "platform.users.manage")
    require(
        body.administrator.kind != "new" or body.administrator.password is not None,
        "invalid_administrator_choice",
        "Choose an administrator password",
    )
    password_hash = (
        await hash_password(body.administrator.password.get_secret_value())
        if body.administrator.password is not None
        else None
    )
    await lock_administration(session)
    await active_plan(session, body.tenant.subscription_plan_id)
    settings = required(await session.get(PlatformSettings, 1))
    if password_hash is not None:
        require(
            request.app.state.settings.local_auth_enabled,
            "local_auth_disabled",
            "Local account authentication is disabled",
            503,
        )
    policy = (
        body.tenant.policy_settings.model_dump()
        if body.tenant.policy_settings
        else settings.default_organization_policy
    )
    require(within(policy, settings.policy_limits), "policy_limit", "Policy exceeds platform limits")
    org = Organization(
        id=uuid4(),
        created_by=actor.id,
        is_active=False,
        suspension_source="platform",
        status_reason="pending_activation",
        policy_settings=policy,
        **body.tenant.model_dump(mode="python", exclude={"policy_settings"}),
    )
    session.add(org)
    await session.flush()
    await seed_tenant_clinical_defaults(session, org.id, actor)
    if body.administrator.kind == "new":
        assert body.administrator.email is not None and body.administrator.display_name is not None
        email = normalize_email(str(body.administrator.email))
        require(
            await session.scalar(select(LocalCredential.user_id).where(LocalCredential.login_email == email))
            is None,
            "local_identity_exists",
            "A local account already uses this email",
            409,
        )
        user = User(
            id=uuid4(),
            auth_method="local",
            identity_issuer=None,
            identity_subject=None,
            email=email,
            email_verified=True,
            display_name=body.administrator.display_name,
            created_by=actor.id,
        )
        session.add(user)
        await session.flush()
        session.add(
            LocalCredential(
                user_id=user.id,
                login_email=email,
                password_hash=password_hash,
                setup_completed_at=now(),
            )
        )
        await session.flush()
        await audit(session, actor, "platform.user.provisioned", "user", user.id, org.id)
    else:
        user = required(await session.get(User, body.administrator.user_id, with_for_update=True))
        require(
            user.is_active and user.archived_at is None and user.email_verified,
            "administrator_unavailable",
            "Choose an active verified user",
            422,
        )
        if user.auth_method == "local":
            credential = await session.get(LocalCredential, user.id)
            require(
                credential is not None and credential.setup_completed_at is not None,
                "account_setup_required",
                "This user must complete account setup first",
                422,
            )
    membership = Membership(
        id=uuid4(),
        organization_id=org.id,
        user_id=user.id,
        role="org_admin",
        department_id=None,
        is_active=True,
        invitation_status="accepted",
        joined_at=now(),
        created_by=actor.id,
    )
    session.add(membership)
    await session.flush()
    org.is_active = True
    org.suspension_source = None
    org.status_reason = None
    org.status_changed_by = actor.id
    await session.flush()
    await audit(session, actor, "platform.organization.created", "organization", org.id, org.id)
    await audit(session, actor, "platform.organization.admin_assigned", "membership", membership.id, org.id)
    if body.device.kind == "existing":
        source = required(
            await session.scalar(select(Device).where(Device.id == body.device.device_id).with_for_update())
        )
        await available_tenant(session, source.organization_id, False)
        check_etag(source, body.device.expected_etag)
        require(source.enrollment_state != "retired", "device_retired", "Choose a current device", 409)
        device = Device(
            id=uuid4(),
            device_unique_id=source.device_unique_id,
            organization_id=org.id,
            name=source.name,
            device_type=source.device_type,
            is_active=True,
            created_by=actor.id,
        )
        revoke_registration(source, actor, True)
        await audit(
            session,
            actor,
            "platform.device.transferred_out",
            "device",
            source.id,
            source.organization_id,
            {"replacement_device_id": str(device.id)},
        )
        await audit(
            session,
            actor,
            "platform.device.transferred_in",
            "device",
            device.id,
            org.id,
            {"previous_device_id": str(source.id)},
        )
    else:
        assert body.device.name is not None and body.device.device_type is not None
        assert body.device.device_unique_id is not None
        await reserve_device_identity(session, body.device.device_unique_id)
        device = Device(
            id=uuid4(),
            device_unique_id=body.device.device_unique_id,
            organization_id=org.id,
            name=body.device.name,
            device_type=body.device.device_type,
            is_active=True,
            created_by=actor.id,
        )
        await audit(session, actor, "platform.device.registered", "device", device.id, org.id)
    session.add(device)
    await commit(session, org)
    await session.refresh(device)
    response.headers["Cache-Control"] = "no-store"
    return {
        "tenant": public(org),
        "device": await fleet_response(session, device),
        "administrator": {"id": user.id, "display_name": user.display_name, "email": user.email},
    }
