from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import EmailStr, TypeAdapter
from sqlalchemy import and_, func, or_, select

from pms_api.core.common import AppError, new_token, now, require, required, token_hash
from pms_api.core.dependencies import Session
from pms_api.database.models import (
    Department,
    Device,
    LocalCredential,
    MemberCapability,
    Membership,
    Organization,
    PlatformSettings,
    ProcessingRun,
    User,
)
from pms_api.database.session import lock_administration
from pms_api.integrations.email import send_invitation
from pms_api.modules.common import audit, commit, directory_page, public
from pms_api.modules.patching import changes, update_fields
from pms_api.modules.patient_catalog import seed_tenant_clinical_defaults
from pms_api.modules.schemas import (
    AdminAssignment,
    DepartmentCreate,
    DepartmentPatch,
    Input,
    InvitationCreate,
    LocalUserCreate,
    MembershipPatch,
    OrganizationCreate,
    OrganizationPatch,
    PlatformPatch,
    Restore,
    TokenInput,
    UserAdminPatch,
    UserPatch,
)
from pms_api.modules.subscriptions import active_plan, subscription_view
from pms_api.security.access import (
    Actor,
    Principal,
    bearer,
    capability_eligible,
    human,
    organization_access,
    platform_access,
    scoped_query,
    scoped_record,
)
from pms_api.security.local_auth import (
    create_action_token,
    normalize_email,
    revoke_user_actions,
    revoke_user_sessions,
)

router = APIRouter()
Limit = Annotated[int, Query(ge=1, le=100)]


def check_version(row, expected_version):
    require(
        expected_version is None or expected_version == row.management_version,
        "version_conflict",
        "This record changed; refresh before retrying",
        409,
    )


def tenant_administrator_query():
    return (
        select(Membership.user_id)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(
            Membership.role == "org_admin",
            Membership.archived_at.is_(None),
            Organization.archived_at.is_(None),
            or_(
                Membership.invitation_status == "accepted",
                and_(Membership.invitation_status == "pending", Membership.invitation_expires_at > now()),
            ),
        )
    )


async def user_view(session, row):
    result = public(row)
    credential = await session.get(LocalCredential, row.id) if row.auth_method == "local" else None
    result["setup_pending"] = bool(credential and credential.setup_completed_at is None)
    result["tenant_admin"] = bool(
        await session.scalar(
            tenant_administrator_query().where(Membership.user_id == row.id).exists().select()
        )
    )
    return result


async def member_view(session, row):
    result = public(row)
    user = await session.get(User, row.user_id) if row.user_id else None
    result["user"] = (
        {
            "id": user.id,
            "display_name": user.display_name,
            "email": user.email,
            "auth_method": user.auth_method,
            "is_active": user.is_active,
            "archived_at": user.archived_at,
        }
        if user
        else None
    )
    return result


@router.post("/identity/sync", tags=["Identity"])
async def synchronize_identity(
    request: Request,
    session: Session,
    credential: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
):
    require(
        credential is not None and credential.scheme.lower() == "bearer",
        "authentication_required",
        "Bearer authentication is required",
        401,
    )
    assert credential is not None
    claims = await request.app.state.oidc.verify(credential.credentials)
    require(
        isinstance(claims.get("email"), str),
        "email_required",
        "The identity provider must supply an email",
        422,
    )
    try:
        email = str(TypeAdapter(EmailStr).validate_python(claims["email"]))
    except ValueError as error:
        raise AppError(422, "invalid_identity_email", "The identity provider email is invalid") from error
    require(
        len((claims["iss"] + claims["sub"]).encode()) <= 2048,
        "identity_too_long",
        "Identity identifiers exceed supported length",
    )
    await lock_administration(session)
    user = await session.scalar(
        select(User)
        .where(User.identity_issuer == claims["iss"], User.identity_subject == claims["sub"])
        .with_for_update()
    )
    if user:
        require(
            user.auth_method == "oidc" and user.is_active and user.archived_at is None,
            "identity_inactive",
            "This identity is inactive",
            403,
        )
        user.email = email
        user.email_verified = claims.get("email_verified") is True
        user.last_login_at = now()
    else:
        user = User(
            id=uuid4(),
            identity_issuer=claims["iss"],
            identity_subject=claims["sub"],
            display_name=str(claims.get("name") or email)[:256],
            email=email,
            email_verified=claims.get("email_verified") is True,
            last_login_at=now(),
            auth_method="oidc",
        )
        session.add(user)
        await session.flush()
        await audit(session, Principal(user=user), "identity.registered", "user", user.id)
    await commit(session, user)
    return public(user)


@router.get("/me", tags=["Identity"])
async def me(session: Session, actor: Actor):
    user = human(actor)
    memberships = (await session.scalars(select(Membership).where(Membership.user_id == user.id))).all()
    value = public(user)
    value["authentication_methods"] = [user.auth_method]
    value["password_management"] = user.auth_method == "local"
    return {"user": value, "memberships": [public(m) for m in memberships]}


@router.patch("/me", tags=["Identity"])
async def patch_me(body: UserPatch, session: Session, actor: Actor):
    user = human(actor)
    update_fields(user, changes(body))
    await audit(session, actor, "identity.updated", "user", user.id)
    await commit(session, user)
    return public(user)


@router.get("/platform/settings", tags=["Platform"])
async def platform_settings(session: Session, actor: Actor):
    platform_access(actor, "platform.settings.read")
    return public(await session.get(PlatformSettings, 1))


@router.patch("/platform/settings", tags=["Platform"])
async def patch_platform(body: PlatformPatch, session: Session, actor: Actor):
    platform_access(actor, "platform.settings.manage")
    row = await session.scalar(select(PlatformSettings).where(PlatformSettings.id == 1).with_for_update())
    row = required(row)
    require(
        row.configuration_version == body.expected_version,
        "version_conflict",
        "Platform settings changed; refresh before retrying",
        409,
    )
    values = changes(body, {"expected_version"})
    if "enabled_providers" in values:
        require(
            values["enabled_providers"] is not None, "invalid_providers", "Enabled providers must be a list"
        )
        require(
            len(set(values["enabled_providers"])) == len(values["enabled_providers"]),
            "duplicate_provider",
            "Provider entries must be unique",
        )
    if {"default_organization_policy", "policy_limits"} & values.keys():
        from pms_api.modules.configuration import within

        defaults = values.get("default_organization_policy", row.default_organization_policy)
        limits = values.get("policy_limits", row.policy_limits)
        require(
            within(defaults, limits),
            "policy_limit",
            "Default organization policy exceeds platform limits",
        )
    update_fields(row, values)
    row.updated_by = actor.id
    await audit(
        session,
        actor,
        "platform.settings.updated",
        "platform_settings",
        None,
        details={"fields": sorted(values)},
    )
    await commit(session, row)
    return public(row)


@router.get("/platform/organizations", tags=["Platform"])
async def platform_organizations(
    request: Request,
    session: Session,
    actor: Actor,
    limit: Limit = 50,
    cursor: str | None = None,
    q: Annotated[str | None, Query(max_length=128)] = None,
    is_active: bool | None = None,
    archived: bool | None = None,
    sort_by: Literal["id", "name", "created_at", "updated_at"] = "id",
    sort_order: Literal["asc", "desc"] = "asc",
    include_total: bool = False,
):
    platform_access(actor, "platform.organizations.read")
    query = select(Organization)
    if q:
        query = query.where(Organization.name.icontains(q, autoescape=True))
    if is_active is not None:
        query = query.where(Organization.is_active == is_active)
    if archived is not None:
        query = query.where(
            Organization.archived_at.is_not(None) if archived else Organization.archived_at.is_(None)
        )
    expression = getattr(Organization, sort_by)
    binding = f"platform-organizations|{q}|{is_active}|{archived}|{sort_by}|{sort_order}"
    secret = request.app.state.settings.token_pepper.get_secret_value()
    rows, next_cursor, has_more, total = await directory_page(
        session,
        query,
        Organization,
        limit=limit,
        cursor=cursor,
        sort=sort_by,
        direction=sort_order,
        expression=expression,
        binding=binding,
        secret=secret,
        kind="uuid" if sort_by == "id" else "datetime" if sort_by.endswith("_at") else "string",
        include_total=include_total,
        legacy_id=True,
    )
    return {
        "items": [public(r) for r in rows],
        "next_cursor": next_cursor,
        "has_more": has_more,
        **({"total": total} if include_total else {}),
    }


@router.post("/platform/organizations", status_code=201, tags=["Platform"])
async def platform_organization_create(body: OrganizationCreate, session: Session, actor: Actor):
    platform_access(actor, "platform.organizations.manage")
    await active_plan(session, body.subscription_plan_id)
    settings = required(await session.get(PlatformSettings, 1))
    from pms_api.modules.configuration import within

    policy = (
        body.policy_settings.model_dump() if body.policy_settings else settings.default_organization_policy
    )
    require(within(policy, settings.policy_limits), "policy_limit", "Policy exceeds platform limits")
    values = body.model_dump(mode="python", exclude={"policy_settings"})
    row = Organization(
        id=uuid4(),
        created_by=actor.id,
        is_active=False,
        suspension_source="platform",
        status_reason="pending_activation",
        policy_settings=policy,
        **values,
    )
    session.add(row)
    await session.flush()
    await seed_tenant_clinical_defaults(session, row.id, actor)
    await audit(session, actor, "platform.organization.created", "organization", row.id, row.id)
    await commit(session, row)
    return public(row)


@router.get("/platform/organizations/{organization_id}", tags=["Platform"])
async def platform_organization_detail(organization_id: UUID, session: Session, actor: Actor):
    platform_access(actor, "platform.organizations.read")
    return public(required(await session.get(Organization, organization_id)))


@router.get("/platform/users", tags=["Platform"])
async def platform_users(
    request: Request,
    session: Session,
    actor: Actor,
    limit: Limit = 50,
    cursor: str | None = None,
    q: Annotated[str | None, Query(max_length=128)] = None,
    auth_method: Literal["local", "oidc"] | None = None,
    is_active: bool | None = None,
    archived: bool | None = None,
    platform_role: Literal["platform_admin", "tenant_admin", "none"] | None = None,
    sort_by: Literal["id", "display_name", "email", "created_at"] = "id",
    sort_order: Literal["asc", "desc"] = "asc",
    include_total: bool = False,
):
    platform_access(actor, "platform.users.read")
    query = select(User)
    if q:
        query = query.where(
            or_(User.display_name.icontains(q, autoescape=True), User.email.icontains(q, autoescape=True))
        )
    if auth_method:
        query = query.where(User.auth_method == auth_method)
    if is_active is not None:
        query = query.where(User.is_active == is_active)
    if archived is not None:
        query = query.where(User.archived_at.is_not(None) if archived else User.archived_at.is_(None))
    if platform_role == "tenant_admin":
        query = query.where(User.id.in_(tenant_administrator_query()))
    elif platform_role:
        query = query.where(
            User.platform_role.is_(None) if platform_role == "none" else User.platform_role == platform_role
        )
    expression = getattr(User, sort_by)
    binding = (
        f"platform-users|{q}|{auth_method}|{is_active}|{archived}|{platform_role}|{sort_by}|{sort_order}"
    )
    rows, next_cursor, has_more, total = await directory_page(
        session,
        query,
        User,
        limit=limit,
        cursor=cursor,
        sort=sort_by,
        direction=sort_order,
        expression=expression,
        binding=binding,
        secret=request.app.state.settings.token_pepper.get_secret_value(),
        kind="uuid" if sort_by == "id" else "datetime" if sort_by.endswith("_at") else "string",
        include_total=include_total,
        legacy_id=True,
    )
    pending_ids = set(
        (
            await session.scalars(
                select(LocalCredential.user_id).where(
                    LocalCredential.user_id.in_([row.id for row in rows]),
                    LocalCredential.setup_completed_at.is_(None),
                )
            )
        ).all()
    )
    tenant_admin_ids = set(
        await session.scalars(
            tenant_administrator_query().where(Membership.user_id.in_([row.id for row in rows]))
        )
    )
    return {
        "items": [
            {**public(r), "setup_pending": r.id in pending_ids, "tenant_admin": r.id in tenant_admin_ids}
            for r in rows
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
        **({"total": total} if include_total else {}),
    }


@router.post("/platform/users", status_code=201, tags=["Platform"])
async def platform_user_create(
    body: LocalUserCreate, request: Request, response: Response, session: Session, actor: Actor
):
    platform_access(actor, "platform.users.manage")
    platform_access(
        actor,
        "platform.administrators.manage" if body.platform_role else "platform.users.manage",
    )
    if body.organization_id:
        platform_access(actor, "platform.organization_admins.manage")
    require(
        request.app.state.settings.local_auth_enabled,
        "local_auth_disabled",
        "Local account authentication is disabled",
        503,
    )
    await lock_administration(session)
    if body.organization_id:
        organization = required(await session.get(Organization, body.organization_id, with_for_update=True))
        require(organization.archived_at is None, "organization_archived", "Restore this tenant first", 409)
    email = normalize_email(str(body.email))
    duplicate = await session.scalar(
        select(LocalCredential.user_id).where(LocalCredential.login_email == email)
    )
    require(not duplicate, "local_identity_exists", "A local account already uses this email", 409)
    row = User(
        id=uuid4(),
        auth_method="local",
        identity_issuer=None,
        identity_subject=None,
        email=email,
        email_verified=False,
        display_name=body.display_name,
        phone=body.phone,
        platform_role=body.platform_role,
        created_by=actor.id,
    )
    credential = LocalCredential(user_id=row.id, login_email=email)
    # Mappings intentionally omit DDL foreign keys; persist the parent first.
    # Both flushes still belong to the same audited transaction.
    session.add(row)
    await session.flush()
    session.add(credential)
    await session.flush()
    _, delivery, setup_token = await create_action_token(session, request.app.state.settings, row, "setup")
    invitation = None
    if body.organization_id:
        membership, invitation_token, _ = await create_invitation(
            session,
            request.app.state.settings,
            actor,
            body.organization_id,
            InvitationCreate(email=body.email, auth_method="local", role="org_admin"),
        )
        # Bind the invitation to this newly created identity. Acceptance and password
        # setup are still required; pending memberships reserve a subscription seat.
        membership.user_id = row.id
        invitation = membership, invitation_token
    await audit(session, actor, "platform.user.created", "user", row.id, details={"method": "local"})
    await commit(session, row)
    invitation_result = {}
    if invitation:
        membership, invitation_token = invitation
        delivered = await send_invitation(request.app.state.settings, row.email, invitation_token)
        invitation_result = {
            "membership": public(membership),
            "email_delivered": delivered,
            "invitation_token": invitation_token if not delivered else None,
        }
    response.headers["Cache-Control"] = "no-store"
    return {
        "user": await user_view(session, row),
        "setup_delivery": {"id": delivery.id, "status": delivery.status},
        **({"setup_token": setup_token} if request.app.state.settings.vm_local_mode else {}),
        **invitation_result,
    }


@router.get("/platform/users/{user_id}", tags=["Platform"])
async def platform_user_detail(user_id: UUID, session: Session, actor: Actor):
    platform_access(actor, "platform.users.read")
    return await user_view(session, required(await session.get(User, user_id)))


@router.post("/platform/users/{user_id}/setup/resend", tags=["Platform"])
async def platform_user_setup_resend(
    user_id: UUID,
    request: Request,
    response: Response,
    session: Session,
    actor: Actor,
    expected_version: Annotated[int | None, Query(gt=0)] = None,
):
    platform_access(actor, "platform.users.manage")
    require(
        request.app.state.settings.local_auth_enabled,
        "local_auth_disabled",
        "Local account authentication is disabled",
        503,
    )
    await lock_administration(session)
    row = required(await session.get(User, user_id, with_for_update=True))
    check_version(row, expected_version)
    if row.platform_role == "platform_admin":
        platform_access(actor, "platform.administrators.manage")
    if await session.scalar(
        select(Membership.id).where(Membership.user_id == row.id, Membership.role == "org_admin")
    ):
        platform_access(actor, "platform.organization_admins.manage")
    credential = await session.get(LocalCredential, user_id, with_for_update=True)
    require(
        row.auth_method == "local"
        and row.is_active
        and row.archived_at is None
        and credential is not None
        and credential.setup_completed_at is None,
        "state_conflict",
        "This local account has already completed setup or is unavailable",
        409,
    )
    _, delivery, setup_token = await create_action_token(session, request.app.state.settings, row, "setup")
    row.management_version += 1
    await audit(session, actor, "platform.user.setup_resent", "user", row.id)
    await commit(session, row)
    response.headers["Cache-Control"] = "no-store"
    return {
        "user": await user_view(session, row),
        "delivery": {"id": delivery.id, "status": delivery.status},
        **({"setup_token": setup_token} if request.app.state.settings.vm_local_mode else {}),
    }


@router.patch("/platform/users/{user_id}", tags=["Platform"])
async def platform_user_update(user_id: UUID, body: UserAdminPatch, session: Session, actor: Actor):
    platform_access(actor, "platform.users.manage")
    require(
        user_id != actor.id or body.is_active is not False,
        "self_account_action",
        "You cannot disable your own account",
        403,
    )
    platform_access(
        actor,
        "platform.administrators.manage"
        if "platform_role" in body.model_fields_set
        else "platform.users.manage",
    )
    await lock_administration(session)
    row = required(await session.get(User, user_id, with_for_update=True))
    require(row is not None, "not_found", "User not found", 404)
    assert row is not None
    if row.platform_role == "platform_admin":
        platform_access(actor, "platform.administrators.manage")
    require(row.archived_at is None, "state_conflict", "Restore the user before updating it", 409)
    require(
        body.expected_version is None or body.expected_version == row.management_version,
        "version_conflict",
        "User changed; refresh before retrying",
        409,
    )
    values = changes(body, {"expected_version"})
    require(
        row.auth_method == "local" or not ({"display_name", "phone"} & values.keys()),
        "external_identity_managed",
        "External identity profiles are managed by their provider",
        409,
    )
    update_fields(row, values)
    row.management_version += 1
    row.status_changed_by = actor.id
    if values.get("is_active") is False:
        await revoke_user_sessions(session, row.id, "user_deactivated")
        await revoke_user_actions(session, row.id)
    await audit(session, actor, "platform.user.updated", "user", row.id, details={"fields": sorted(values)})
    await commit(session, row)
    return await user_view(session, row)


@router.delete("/platform/users/{user_id}", tags=["Platform"])
async def platform_user_archive(
    user_id: UUID, session: Session, actor: Actor, expected_version: Annotated[int | None, Query(gt=0)] = None
):
    platform_access(actor, "platform.users.manage")
    require(user_id != actor.id, "self_account_action", "You cannot archive your own account", 403)
    await lock_administration(session)
    row = required(await session.get(User, user_id, with_for_update=True))
    check_version(row, expected_version)
    if row.platform_role == "platform_admin":
        platform_access(actor, "platform.administrators.manage")
    if row.archived_at is None:
        row.archived_at = now()
        row.archived_by = actor.id
        row.is_active = False
        row.status_changed_by = actor.id
        row.status_reason = "archived"
        row.management_version += 1
        await revoke_user_sessions(session, row.id, "user_archived")
        await revoke_user_actions(session, row.id)
        await audit(session, actor, "platform.user.archived", "user", row.id)
    await commit(session, row)
    return await user_view(session, row)


@router.post("/platform/users/{user_id}/restore", tags=["Platform"])
async def platform_user_restore(user_id: UUID, body: Restore, session: Session, actor: Actor):
    platform_access(actor, "platform.users.manage")
    await lock_administration(session)
    row = required(await session.get(User, user_id, with_for_update=True))
    if row.platform_role == "platform_admin":
        platform_access(actor, "platform.administrators.manage")
    require(
        row.management_version == body.expected_version,
        "version_conflict",
        "User changed; refresh before retrying",
        409,
    )
    require(row.archived_at is not None, "state_conflict", "User is not archived", 409)
    row.archived_at = None
    row.archived_by = None
    row.is_active = False
    row.status_reason = "restored_pending_activation"
    row.management_version += 1
    await audit(session, actor, "platform.user.restored", "user", row.id)
    await commit(session, row)
    return await user_view(session, row)


@router.patch("/platform/organizations/{organization_id}", tags=["Platform"])
async def platform_org_update(organization_id: UUID, body: OrganizationPatch, session: Session, actor: Actor):
    platform_access(actor, "platform.organizations.manage")
    await lock_administration(session)
    row = required(await session.get(Organization, organization_id, with_for_update=True))
    require(row is not None, "not_found", "Organization not found", 404)
    assert row is not None
    require(
        row.archived_at is None,
        "state_conflict",
        "Restore the organization before updating it",
        409,
    )
    require(
        body.expected_version is None or body.expected_version == row.management_version,
        "version_conflict",
        "Organization changed; refresh before retrying",
        409,
    )
    values = changes(body, {"expected_version"})
    # Global administration controls directory/status; tenant configuration needs membership.
    require(
        not {"policy_settings"} & values.keys(),
        "tenant_permission_required",
        "Tenant configuration requires organization membership",
        403,
    )
    if values.get("is_active") is True:
        administrator = await session.scalar(
            select(Membership.id)
            .join(User, User.id == Membership.user_id)
            .where(
                Membership.organization_id == row.id,
                Membership.role == "org_admin",
                Membership.is_active.is_(True),
                Membership.invitation_status == "accepted",
                Membership.archived_at.is_(None),
                User.is_active.is_(True),
                User.archived_at.is_(None),
            )
            .limit(1)
        )
        require(
            administrator is not None,
            "organization_admin_required",
            "Assign an active administrator before activating the organization",
            409,
        )
    update_fields(row, values)
    row.management_version += 1
    if "is_active" in values:
        row.suspension_source = None if row.is_active else "platform"
        row.status_changed_by = actor.id
    await audit(
        session,
        actor,
        "platform.organization.updated",
        "organization",
        row.id,
        row.id,
        {"fields": sorted(values)},
    )
    await commit(session, row)
    return public(row)


@router.delete("/platform/organizations/{organization_id}", tags=["Platform"])
async def platform_organization_archive(
    organization_id: UUID,
    session: Session,
    actor: Actor,
    expected_version: Annotated[int | None, Query(gt=0)] = None,
):
    platform_access(actor, "platform.organizations.manage")
    await lock_administration(session)
    row = required(await session.get(Organization, organization_id, with_for_update=True))
    require(
        expected_version is None or row.management_version == expected_version,
        "version_conflict",
        "Organization changed; refresh before retrying",
        409,
    )
    if row.archived_at is None:
        row.archived_at = now()
        row.archived_by = actor.id
        row.is_active = False
        row.suspension_source = "platform"
        row.status_reason = "archived"
        row.status_changed_by = actor.id
        row.management_version += 1
        await audit(session, actor, "platform.organization.archived", "organization", row.id, row.id)
    await commit(session, row)
    return public(row)


@router.post("/platform/organizations/{organization_id}/restore", tags=["Platform"])
async def platform_organization_restore(organization_id: UUID, body: Restore, session: Session, actor: Actor):
    platform_access(actor, "platform.organizations.manage")
    await lock_administration(session)
    row = required(await session.get(Organization, organization_id, with_for_update=True))
    require(
        row.management_version == body.expected_version,
        "version_conflict",
        "Organization changed; refresh before retrying",
        409,
    )
    require(row.archived_at is not None, "state_conflict", "Organization is not archived", 409)
    row.archived_at = None
    row.archived_by = None
    row.is_active = False
    row.suspension_source = "platform"
    row.status_reason = "restored_pending_activation"
    row.management_version += 1
    await audit(session, actor, "platform.organization.restored", "organization", row.id, row.id)
    await commit(session, row)
    return public(row)


@router.get("/platform/organizations/{organization_id}/administrators", tags=["Platform"])
async def organization_administrators(organization_id: UUID, session: Session, actor: Actor):
    platform_access(actor, "platform.organizations.read")
    required(await session.get(Organization, organization_id))
    rows = (
        await session.execute(
            select(User.id, User.display_name, User.email)
            .join(Membership, Membership.user_id == User.id)
            .where(
                Membership.organization_id == organization_id,
                Membership.role == "org_admin",
                Membership.is_active.is_(True),
                Membership.invitation_status == "accepted",
                Membership.archived_at.is_(None),
                User.is_active.is_(True),
                User.archived_at.is_(None),
            )
            .order_by(User.display_name, User.id)
        )
    ).all()
    return {"items": [{"id": row.id, "display_name": row.display_name, "email": row.email} for row in rows]}


@router.post("/platform/organizations/{organization_id}/administrators", tags=["Platform"])
async def assign_org_admin(organization_id: UUID, body: AdminAssignment, session: Session, actor: Actor):
    platform_access(actor, "platform.organization_admins.manage")
    await lock_administration(session)
    org = required(await session.get(Organization, organization_id, with_for_update=True))
    user = required(await session.get(User, body.user_id))
    require(
        org is not None
        and org.archived_at is None
        and user is not None
        and user.is_active
        and user.archived_at is None,
        "not_found",
        "Active user or organization not found",
        404,
    )
    assert org is not None
    if user.auth_method == "local":
        credential = await session.get(LocalCredential, user.id)
        require(
            credential is not None and credential.setup_completed_at is not None,
            "account_setup_required",
            "The local account must complete password setup before administrator access is assigned",
            409,
        )
    require(user.email_verified, "administrator_unavailable", "Choose a verified user", 409)
    row = await session.scalar(
        select(Membership)
        .where(Membership.organization_id == org.id, Membership.user_id == user.id)
        .with_for_update()
    )
    existing = row is not None
    if row is None:
        pending = await session.scalar(
            select(Membership.id).where(
                Membership.organization_id == org.id,
                Membership.invitation_status == "pending",
                func.lower(Membership.invited_email) == user.email.lower(),
            )
        )
        require(
            pending is None,
            "membership_exists",
            "This account has a pending invitation; manage its membership instead",
            409,
        )
        row = Membership(id=uuid4(), organization_id=org.id, user_id=user.id, created_by=actor.id)
        session.add(row)
    else:
        require(
            row.archived_at is None,
            "state_conflict",
            "Restore the membership before assigning administrator access",
            409,
        )
        if row.role == "org_admin" and row.is_active and row.invitation_status == "accepted":
            return public(row)
    row.role = "org_admin"
    row.department_id = None
    row.is_active = True
    row.invitation_status = "accepted"
    row.invitation_token_hash = None
    row.joined_at = row.joined_at or now()
    if existing:
        row.management_version += 1
    row.status_changed_by = actor.id
    await audit(session, actor, "platform.organization.admin_assigned", "membership", row.id, org.id)
    await commit(session, row)
    return public(row)


@router.get("/platform/health", tags=["Platform"])
async def platform_health(session: Session, actor: Actor):
    platform_access(actor, "platform.health.read")
    query = select(
        select(func.count()).select_from(Organization).scalar_subquery().label("organizations"),
        select(func.count()).select_from(Device).scalar_subquery().label("devices"),
        select(func.count())
        .select_from(ProcessingRun)
        .where(ProcessingRun.status.in_(["queued", "running", "awaiting_upload", "awaiting_device"]))
        .scalar_subquery()
        .label("pending_runs"),
    )
    result = (await session.execute(query)).one()
    return {
        "organizations": result.organizations,
        "devices": result.devices,
        "pending_runs": result.pending_runs,
    }


def live_device_condition(cutoff):
    # A recent heartbeat alone does not make a suspended/revoked device operational.
    return and_(
        Device.last_seen_at >= cutoff,
        Device.is_active.is_(True),
        Device.enrollment_state == "enrolled",
        Device.credential_hash.is_not(None),
        Device.credential_revoked_at.is_(None),
        Organization.is_active.is_(True),
        Organization.archived_at.is_(None),
        or_(
            Device.department_id.is_(None),
            select(Department.id)
            .where(
                Department.id == Device.department_id,
                Department.is_active.is_(True),
                Department.archived_at.is_(None),
            )
            .exists(),
        ),
    )


@router.get("/platform/dashboard-stats", tags=["Platform"])
async def platform_dashboard_stats(session: Session, actor: Actor):
    platform_access(actor, "platform.health.read")
    platform = required(await session.get(PlatformSettings, 1))
    offline_seconds = int(platform.device_defaults["offline_after_seconds"])
    fleet = (
        select(
            func.count().label("total"),
            func.count()
            .filter(live_device_condition(now() - timedelta(seconds=offline_seconds)))
            .label("live"),
        )
        .select_from(Device)
        .join(Organization, Organization.id == Device.organization_id)
        .where(Organization.archived_at.is_(None), Device.enrollment_state != "retired")
    )
    devices = (await session.execute(fleet)).one()
    tenants = (
        await session.execute(
            select(
                func.count().label("total"),
                func.count().filter(Organization.is_active.is_(False)).label("inactive"),
                func.count()
                .filter(
                    ~select(Device.id)
                    .where(Device.organization_id == Organization.id, Device.enrollment_state == "enrolled")
                    .exists()
                )
                .label("awaiting"),
            ).where(Organization.archived_at.is_(None))
        )
    ).one()
    return {
        "total_devices": devices.total,
        "live_devices": devices.live,
        "live_percentage": round(devices.live / devices.total * 100, 1) if devices.total else 0,
        "offline_after_seconds": offline_seconds,
        "total_tenants": tenants.total,
        "inactive_tenants": tenants.inactive,
        "awaiting_enrollment": tenants.awaiting,
    }


@router.get("/platform/reports/devices-by-tenant", tags=["Platform"])
async def platform_devices_by_tenant(session: Session, actor: Actor, limit: Limit = 10):
    platform_access(actor, "platform.health.read")
    query = (
        select(Organization.id, Organization.name, func.count(Device.id).label("device_count"))
        .outerjoin(
            Device, and_(Device.organization_id == Organization.id, Device.enrollment_state != "retired")
        )
        .where(Organization.archived_at.is_(None))
        .group_by(Organization.id, Organization.name)
        .order_by(func.count(Device.id).desc(), Organization.id)
        .limit(limit)
    )
    rows = (await session.execute(query)).all()
    return {"items": [{"id": r.id, "label": r.name, "value": str(r.device_count)} for r in rows]}


@router.post("/organizations", status_code=201, tags=["Organizations"])
async def create_organization(body: OrganizationCreate, session: Session, actor: Actor):
    user = human(actor)
    await lock_administration(session)
    settings = required(await session.get(PlatformSettings, 1))
    require(
        user.email_verified,
        "verified_email_required",
        "Verify your email before creating an organization",
        403,
    )
    require(
        settings.registration_mode == "self_service" or user.platform_role == "platform_admin",
        "registration_disabled",
        "Self-service organization creation is disabled",
        403,
    )
    await active_plan(session, body.subscription_plan_id)
    values = body.model_dump(mode="python", exclude={"policy_settings"})
    policy = (
        body.policy_settings.model_dump() if body.policy_settings else settings.default_organization_policy
    )
    from pms_api.modules.configuration import within

    require(
        within(policy, settings.policy_limits), "policy_limit", "Organization policy exceeds platform limits"
    )
    row = Organization(id=uuid4(), created_by=user.id, policy_settings=policy, **values)
    session.add(row)
    await session.flush()
    await seed_tenant_clinical_defaults(session, row.id, actor)
    session.add(
        Membership(
            id=uuid4(),
            organization_id=row.id,
            user_id=user.id,
            role="org_admin",
            is_active=True,
            invitation_status="accepted",
            joined_at=now(),
            created_by=user.id,
        )
    )
    await audit(session, actor, "organization.created", "organization", row.id, row.id)
    await commit(session, row)
    return public(row)


@router.get("/organizations", tags=["Organizations"])
async def organizations(
    request: Request,
    session: Session,
    actor: Actor,
    limit: Limit = 50,
    cursor: str | None = None,
    q: Annotated[str | None, Query(max_length=128)] = None,
    is_active: bool | None = None,
    sort_by: Literal["id", "name", "created_at"] = "id",
    sort_order: Literal["asc", "desc"] = "asc",
    include_total: bool = False,
):
    user = human(actor)
    query = (
        select(Organization)
        .join(Membership, Membership.organization_id == Organization.id)
        .where(
            Membership.user_id == user.id,
            Membership.is_active.is_(True),
            Membership.invitation_status == "accepted",
            Membership.archived_at.is_(None),
            Organization.archived_at.is_(None),
        )
    )
    if q:
        query = query.where(Organization.name.icontains(q, autoescape=True))
    if is_active is not None:
        query = query.where(Organization.is_active == is_active)
    rows, next_cursor, has_more, total = await directory_page(
        session,
        query,
        Organization,
        limit=limit,
        cursor=cursor,
        sort=sort_by,
        direction=sort_order,
        expression=getattr(Organization, sort_by),
        binding=f"organizations|{user.id}|{q}|{is_active}|{sort_by}|{sort_order}",
        secret=request.app.state.settings.token_pepper.get_secret_value(),
        kind="uuid" if sort_by == "id" else "datetime" if sort_by.endswith("_at") else "string",
        include_total=include_total,
        legacy_id=True,
    )
    return {
        "items": [
            {
                "id": r.id,
                "name": r.name,
                "is_active": r.is_active,
                "subscription_plan_id": r.subscription_plan_id,
            }
            for r in rows
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
        **({"total": total} if include_total else {}),
    }


@router.get("/organizations/{organization_id}", tags=["Organizations"])
async def organization(organization_id: UUID, session: Session, actor: Actor):
    access = await organization_access(
        session, actor, organization_id, "org.settings.read", allow_inactive=True
    )
    return public(access.organization)


@router.get("/organizations/{organization_id}/dashboard-stats", tags=["Organizations"])
async def organization_dashboard_stats(organization_id: UUID, session: Session, actor: Actor):
    access = await organization_access(session, actor, organization_id, "org.settings.read")
    platform = required(await session.get(PlatformSettings, 1))
    offline_seconds = int(platform.device_defaults["offline_after_seconds"])
    query = (
        select(
            func.count().label("total"),
            func.count()
            .filter(live_device_condition(now() - timedelta(seconds=offline_seconds)))
            .label("live"),
            func.count().filter(Device.is_active.is_(False)).label("inactive"),
        )
        .select_from(Device)
        .join(Organization, Organization.id == Device.organization_id)
        .where(Device.organization_id == organization_id, Device.enrollment_state != "retired")
    )
    devices = (await session.execute(query)).one()
    subscription = await subscription_view(session, access.organization)
    health = [
        ("live", "Reporting and operational", devices.live, "success"),
        ("offline", "Not reporting or not enrolled", devices.total - devices.live - devices.inactive, "warn"),
        ("inactive", "Inactive devices", devices.inactive, "danger"),
    ]
    return {
        "devices": {"total": devices.total, "live": devices.live, "offline": devices.total - devices.live},
        "members": {
            "active": subscription["usage"]["active_users"],
            "pending": subscription["usage"]["pending_invitations"],
        },
        "subscription": subscription,
        "offline_after_seconds": offline_seconds,
        "health_shares": [
            {
                "id": key,
                "label": label,
                "meta": f"{count} devices",
                "share": count / devices.total if devices.total else 0,
                "tone": tone,
            }
            for key, label, count, tone in health
        ],
    }


@router.patch("/organizations/{organization_id}", tags=["Organizations"])
async def organization_update(organization_id: UUID, body: OrganizationPatch, session: Session, actor: Actor):
    await lock_administration(session)
    await organization_access(session, actor, organization_id, "org.settings.manage", allow_inactive=True)
    row = required(await session.get(Organization, organization_id, with_for_update=True))
    require(
        row.archived_at is None,
        "state_conflict",
        "Restore the organization before updating it",
        409,
    )
    require(
        body.expected_version is None or body.expected_version == row.management_version,
        "version_conflict",
        "Organization changed; refresh before retrying",
        409,
    )
    values = changes(body, {"expected_version"})
    if values.get("is_active"):
        require(
            row.suspension_source != "platform",
            "platform_suspension",
            "Only a platform administrator can remove platform suspension",
            403,
        )
    if "policy_settings" in values:
        from pms_api.modules.configuration import within

        settings = required(await session.get(PlatformSettings, 1))
        require(
            within(values["policy_settings"], settings.policy_limits),
            "policy_limit",
            "Policy exceeds platform limits",
        )
    update_fields(row, values)
    row.management_version += 1
    if "is_active" in values:
        row.suspension_source = None if row.is_active else row.suspension_source or "organization"
        row.status_changed_by = actor.id
    await audit(
        session, actor, "organization.updated", "organization", row.id, row.id, {"fields": sorted(values)}
    )
    await commit(session, row)
    return public(row)


@router.get("/organizations/{organization_id}/departments", tags=["Departments"])
async def departments(
    organization_id: UUID,
    request: Request,
    session: Session,
    actor: Actor,
    limit: Limit = 50,
    cursor: str | None = None,
    q: Annotated[str | None, Query(max_length=128)] = None,
    is_active: bool | None = None,
    archived: bool | None = None,
    sort_by: Literal["id", "name", "created_at", "updated_at"] = "id",
    sort_order: Literal["asc", "desc"] = "asc",
    include_total: bool = False,
):
    access = await organization_access(session, actor, organization_id, "org.departments.manage")
    query = scoped_query(Department, access)
    if q:
        query = query.where(
            or_(
                Department.name.icontains(q, autoescape=True),
                Department.description.icontains(q, autoescape=True),
            )
        )
    if is_active is not None:
        query = query.where(Department.is_active == is_active)
    if archived is not None:
        query = query.where(
            Department.archived_at.is_not(None) if archived else Department.archived_at.is_(None)
        )
    rows, next_cursor, has_more, total = await directory_page(
        session,
        query,
        Department,
        limit=limit,
        cursor=cursor,
        sort=sort_by,
        direction=sort_order,
        expression=getattr(Department, sort_by),
        binding=f"departments|{organization_id}|{q}|{is_active}|{archived}|{sort_by}|{sort_order}",
        secret=request.app.state.settings.token_pepper.get_secret_value(),
        kind="uuid" if sort_by == "id" else "datetime" if sort_by.endswith("_at") else "string",
        include_total=include_total,
        legacy_id=True,
    )
    return {
        "items": [public(r) for r in rows],
        "next_cursor": next_cursor,
        "has_more": has_more,
        **({"total": total} if include_total else {}),
    }


@router.post("/organizations/{organization_id}/departments", status_code=201, tags=["Departments"])
async def department_create(organization_id: UUID, body: DepartmentCreate, session: Session, actor: Actor):
    await organization_access(session, actor, organization_id, "org.departments.manage")
    row = Department(id=uuid4(), organization_id=organization_id, created_by=actor.id, **body.model_dump())
    session.add(row)
    await audit(session, actor, "department.created", "department", row.id, organization_id)
    await commit(session, row)
    return public(row)


@router.get("/organizations/{organization_id}/departments/{department_id}", tags=["Departments"])
async def department_detail(organization_id: UUID, department_id: UUID, session: Session, actor: Actor):
    access = await organization_access(session, actor, organization_id, "org.departments.manage")
    return public(await scoped_record(session, Department, access, department_id))


@router.patch("/organizations/{organization_id}/departments/{department_id}", tags=["Departments"])
async def department_update(
    organization_id: UUID, department_id: UUID, body: DepartmentPatch, session: Session, actor: Actor
):
    access = await organization_access(session, actor, organization_id, "org.departments.manage")
    row = await scoped_record(session, Department, access, department_id, True)
    require(row.archived_at is None, "state_conflict", "Restore the department before updating it", 409)
    require(
        body.expected_version is None or body.expected_version == row.management_version,
        "version_conflict",
        "Department changed; refresh before retrying",
        409,
    )
    update_fields(row, changes(body, {"expected_version"}))
    row.management_version += 1
    row.status_changed_by = actor.id
    await audit(session, actor, "department.updated", "department", row.id, organization_id)
    await commit(session, row)
    return public(row)


@router.delete("/organizations/{organization_id}/departments/{department_id}", tags=["Departments"])
async def department_archive(
    organization_id: UUID,
    department_id: UUID,
    session: Session,
    actor: Actor,
    expected_version: Annotated[int | None, Query(gt=0)] = None,
):
    access = await organization_access(session, actor, organization_id, "org.departments.manage")
    row = await scoped_record(session, Department, access, department_id, True)
    require(
        expected_version is None or row.management_version == expected_version,
        "version_conflict",
        "Department changed; refresh before archiving",
        409,
    )
    assigned_member = await session.scalar(
        select(Membership.id).where(
            Membership.department_id == row.id,
            Membership.is_active.is_(True),
            Membership.archived_at.is_(None),
        )
    )
    assigned_device = await session.scalar(
        select(Device.id).where(Device.department_id == row.id, Device.is_active.is_(True))
    )
    require(
        not assigned_member and not assigned_device,
        "dependency_conflict",
        "Active members or devices remain assigned to this department",
        409,
    )
    if row.archived_at is None:
        row.archived_at = now()
        row.archived_by = actor.id
        row.is_active = False
        row.status_reason = "archived"
        row.status_changed_by = actor.id
        row.management_version += 1
        await audit(session, actor, "department.archived", "department", row.id, organization_id)
    await commit(session, row)
    return public(row)


@router.post("/organizations/{organization_id}/departments/{department_id}/restore", tags=["Departments"])
async def department_restore(
    organization_id: UUID,
    department_id: UUID,
    body: Restore,
    session: Session,
    actor: Actor,
):
    access = await organization_access(session, actor, organization_id, "org.departments.manage")
    row = await scoped_record(session, Department, access, department_id, True)
    require(
        row.management_version == body.expected_version,
        "version_conflict",
        "Department changed; refresh before retrying",
        409,
    )
    require(row.archived_at is not None, "state_conflict", "Department is not archived", 409)
    row.archived_at = None
    row.archived_by = None
    row.is_active = False
    row.status_reason = "restored_pending_activation"
    row.management_version += 1
    await audit(session, actor, "department.restored", "department", row.id, organization_id)
    await commit(session, row)
    return public(row)


@router.get("/organizations/{organization_id}/members", tags=["Memberships"])
async def members(
    organization_id: UUID,
    request: Request,
    session: Session,
    actor: Actor,
    limit: Limit = 50,
    cursor: str | None = None,
    q: Annotated[str | None, Query(max_length=128)] = None,
    role: Literal["org_admin", "org_user", "org_read_only", "org_trainee"] | None = None,
    department_id: UUID | None = None,
    is_active: bool | None = None,
    invitation_status: Literal["pending", "accepted", "revoked", "expired"] | None = None,
    archived: bool | None = None,
    sort_by: Literal["id", "name", "email", "created_at", "joined_at"] = "id",
    sort_order: Literal["asc", "desc"] = "asc",
    include_total: bool = False,
):
    access = await organization_access(session, actor, organization_id, "org.members.manage")
    query = scoped_query(Membership, access).outerjoin(User, User.id == Membership.user_id)
    if q:
        query = query.where(
            or_(
                User.display_name.icontains(q, autoescape=True),
                User.email.icontains(q, autoescape=True),
                Membership.invited_email.icontains(q, autoescape=True),
            )
        )
    if role:
        query = query.where(Membership.role == role)
    if department_id:
        query = query.where(Membership.department_id == department_id)
    if is_active is not None:
        query = query.where(Membership.is_active == is_active)
    if archived is not None:
        query = query.where(
            Membership.archived_at.is_not(None) if archived else Membership.archived_at.is_(None)
        )
    if invitation_status == "expired":
        query = query.where(
            or_(
                Membership.invitation_status == "expired",
                and_(Membership.invitation_status == "pending", Membership.invitation_expires_at <= now()),
            )
        )
    elif invitation_status == "pending":
        query = query.where(
            Membership.invitation_status == "pending", Membership.invitation_expires_at > now()
        )
    elif invitation_status:
        query = query.where(Membership.invitation_status == invitation_status)
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    expressions = {
        "id": Membership.id,
        "name": func.coalesce(User.display_name, Membership.invited_email, ""),
        "email": func.coalesce(User.email, Membership.invited_email, ""),
        "created_at": Membership.created_at,
        "joined_at": func.coalesce(Membership.joined_at, epoch),
    }
    binding = (
        f"members|{organization_id}|{access.department_id}|{q}|{role}|{department_id}|"
        f"{is_active}|{invitation_status}|{archived}|{sort_by}|{sort_order}"
    )
    rows, next_cursor, has_more, total = await directory_page(
        session,
        query,
        Membership,
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
    )
    user_ids = [row.user_id for row in rows if row.user_id]
    users = (
        {row.id: row for row in (await session.scalars(select(User).where(User.id.in_(user_ids)))).all()}
        if user_ids
        else {}
    )
    items = []
    for row in rows:
        item = public(row)
        user = users.get(row.user_id)
        item["user"] = (
            {
                "id": user.id,
                "display_name": user.display_name,
                "email": user.email,
                "auth_method": user.auth_method,
                "is_active": user.is_active,
                "archived_at": user.archived_at,
            }
            if user
            else None
        )
        items.append(item)
    return {
        "items": items,
        "next_cursor": next_cursor,
        "has_more": has_more,
        **({"total": total} if include_total else {}),
    }


@router.get("/organizations/{organization_id}/members/{membership_id}", tags=["Memberships"])
async def member_detail(organization_id: UUID, membership_id: UUID, session: Session, actor: Actor):
    access = await organization_access(session, actor, organization_id, "org.members.manage")
    return await member_view(session, await scoped_record(session, Membership, access, membership_id))


ClinicalCapability = Literal[
    "org.clinical.author", "org.clinical.review", "org.training.instruct", "org.clinical.read"
]


class CapabilityAssignment(Input):
    capability: ClinicalCapability


@router.get("/organizations/{organization_id}/members/{membership_id}/capabilities", tags=["Memberships"])
async def member_capabilities(organization_id: UUID, membership_id: UUID, session: Session, actor: Actor):
    access = await organization_access(session, actor, organization_id, "org.members.manage")
    await scoped_record(session, Membership, access, membership_id)
    rows = (
        await session.scalars(
            select(MemberCapability)
            .where(
                MemberCapability.organization_id == organization_id,
                MemberCapability.membership_id == membership_id,
            )
            .order_by(MemberCapability.capability)
        )
    ).all()
    return {"items": [public(row) for row in rows]}


@router.post("/organizations/{organization_id}/members/{membership_id}/capabilities", tags=["Memberships"])
async def grant_member_capability(
    organization_id: UUID,
    membership_id: UUID,
    body: CapabilityAssignment,
    session: Session,
    actor: Actor,
):
    await lock_administration(session)
    access = await organization_access(
        session, actor, organization_id, "org.members.manage", lock_membership=True
    )
    row = await scoped_record(session, Membership, access, membership_id, True)
    member_user = await session.get(User, row.user_id) if row.user_id else None
    require(
        row.is_active
        and row.invitation_status == "accepted"
        and row.archived_at is None
        and member_user is not None
        and member_user.is_active
        and member_user.archived_at is None
        and capability_eligible(row, body.capability),
        "capability_ineligible",
        "Select an active, eligible staff membership",
        409,
    )
    assignment = await session.scalar(
        select(MemberCapability)
        .where(
            MemberCapability.organization_id == organization_id,
            MemberCapability.membership_id == membership_id,
            MemberCapability.capability == body.capability,
        )
        .with_for_update()
    )
    if assignment is None:
        assignment = MemberCapability(
            id=uuid4(),
            organization_id=organization_id,
            membership_id=membership_id,
            capability=body.capability,
            granted_by=actor.id,
        )
        session.add(assignment)
    elif assignment.revoked_at is not None:
        assignment.granted_at = now()
        assignment.granted_by = actor.id
        assignment.revoked_at = None
        assignment.revoked_by = None
    else:
        return public(assignment)
    await audit(
        session,
        actor,
        "membership.capability.granted",
        "membership",
        membership_id,
        organization_id,
        details={"capability": body.capability},
    )
    await commit(session, assignment)
    return public(assignment)


@router.delete(
    "/organizations/{organization_id}/members/{membership_id}/capabilities/{capability}", tags=["Memberships"]
)
async def revoke_member_capability(
    organization_id: UUID,
    membership_id: UUID,
    capability: ClinicalCapability,
    session: Session,
    actor: Actor,
):
    await lock_administration(session)
    access = await organization_access(
        session, actor, organization_id, "org.members.manage", lock_membership=True
    )
    await scoped_record(session, Membership, access, membership_id, True)
    assignment = required(
        await session.scalar(
            select(MemberCapability)
            .where(
                MemberCapability.organization_id == organization_id,
                MemberCapability.membership_id == membership_id,
                MemberCapability.capability == capability,
            )
            .with_for_update()
        )
    )
    if assignment.revoked_at is None:
        assignment.revoked_at = now()
        assignment.revoked_by = actor.id
        await audit(
            session,
            actor,
            "membership.capability.revoked",
            "membership",
            membership_id,
            organization_id,
            details={"capability": capability},
        )
        await commit(session, assignment)
    return public(assignment)


async def validate_department(session, org_id, department_id):
    if department_id:
        dept = required(await session.get(Department, department_id))
        require(
            dept and dept.organization_id == org_id and dept.is_active and dept.archived_at is None,
            "invalid_department",
            "Select an active department in this organization",
        )


async def create_invitation(session, settings, actor, organization_id, body, *, validate_only=False):
    """Shared invitation rules; caller owns authorization, administration lock and transaction."""
    await validate_department(session, organization_id, body.department_id)
    normalized_email = normalize_email(str(body.email))
    identities = (await session.scalars(select(User).where(func.lower(User.email) == normalized_email))).all()
    matching_ids = [u.id for u in identities if body.auth_method is None or u.auth_method == body.auth_method]
    existing = await session.scalar(
        select(Membership.id).where(
            Membership.organization_id == organization_id,
            or_(
                Membership.user_id.in_(matching_ids),
                and_(
                    func.lower(Membership.invited_email) == normalized_email,
                    Membership.invitation_status == "pending",
                ),
            ),
        )
    )
    require(
        existing is None,
        "membership_exists",
        "This person already has a membership or pending invitation; manage that record instead",
        409,
    )
    require(
        not any((not u.is_active or u.archived_at is not None) for u in identities if u.id in matching_ids),
        "invited_account_inactive",
        "The account must be restored and enabled by a platform administrator first",
        409,
    )
    methods = set(
        (
            await session.scalars(select(User.auth_method).where(func.lower(User.email) == normalized_email))
        ).all()
    )
    require(
        body.auth_method is not None or len(methods) <= 1,
        "ambiguous_invitation_identity",
        "Choose local or external authentication for this invitation",
        409,
    )
    setup_token = None
    if body.auth_method == "local" and "local" not in methods:
        require(
            settings.local_auth_enabled,
            "local_auth_disabled",
            "Local account authentication is disabled",
            503,
        )
        require(
            body.local_display_name is not None,
            "local_display_name_required",
            "A display name is required when creating a local account",
            422,
        )
    require(
        body.role != "org_admin" or body.department_id is None,
        "invalid_scope",
        "Organization administrators cover the whole organization",
    )
    if validate_only:
        return None
    if body.auth_method == "local" and "local" not in methods:
        local_user = User(
            id=uuid4(),
            auth_method="local",
            identity_issuer=None,
            identity_subject=None,
            email=normalized_email,
            email_verified=False,
            display_name=body.local_display_name,
            created_by=actor.id,
        )
        session.add(local_user)
        await session.flush()
        session.add(LocalCredential(user_id=local_user.id, login_email=normalized_email))
        await session.flush()
        _, _, setup_token = await create_action_token(session, settings, local_user, "setup")
        await audit(
            session,
            actor,
            "membership.local_user_created",
            "user",
            local_user.id,
            organization_id,
        )
    token = new_token("inv_")
    row = Membership(
        id=uuid4(),
        organization_id=organization_id,
        role=body.role,
        department_id=body.department_id,
        invited_email=normalized_email,
        invitation_auth_method=body.auth_method or next(iter(methods), None),
        invitation_token_hash=token_hash(token, settings.token_pepper.get_secret_value()),
        invitation_expires_at=now() + timedelta(days=2),
        created_by=actor.id,
    )
    session.add(row)
    await audit(session, actor, "membership.invited", "membership", row.id, organization_id)
    return row, token, setup_token if settings.vm_local_mode else None


@router.post("/organizations/{organization_id}/invitations", status_code=201, tags=["Memberships"])
async def invite(
    organization_id: UUID,
    body: InvitationCreate,
    request: Request,
    response: Response,
    session: Session,
    actor: Actor,
):
    await lock_administration(session)
    await organization_access(session, actor, organization_id, "org.members.manage")
    row, token, setup_token = await create_invitation(
        session, request.app.state.settings, actor, organization_id, body
    )
    await commit(session, row)
    delivered = await send_invitation(request.app.state.settings, row.invited_email or "", token)
    response.headers["Cache-Control"] = "no-store"
    return {
        "membership": public(row),
        "email_delivered": delivered,
        "invitation_token": token if not delivered else None,
        "setup_token": setup_token,
    }


@router.post("/organizations/{organization_id}/invitations/{membership_id}/resend", tags=["Memberships"])
async def resend_invitation(
    organization_id: UUID,
    membership_id: UUID,
    request: Request,
    response: Response,
    session: Session,
    actor: Actor,
    expected_version: Annotated[int | None, Query(gt=0)] = None,
):
    await lock_administration(session)
    access = await organization_access(session, actor, organization_id, "org.members.manage")
    row = await scoped_record(session, Membership, access, membership_id, True)
    check_version(row, expected_version)
    require(row.archived_at is None, "state_conflict", "Restore the membership before updating it", 409)
    require(row.invitation_status in {"pending", "expired"}, "invitation_closed", "Invitation is closed", 409)
    await validate_department(session, organization_id, row.department_id)
    token = new_token("inv_")
    row.invitation_token_hash = token_hash(token, request.app.state.settings.token_pepper.get_secret_value())
    row.invitation_expires_at = now() + timedelta(days=2)
    row.invitation_status = "pending"
    row.management_version += 1
    await audit(session, actor, "membership.invitation_resent", "membership", row.id, organization_id)
    await commit(session, row)
    delivered = await send_invitation(request.app.state.settings, row.invited_email or "", token)
    response.headers["Cache-Control"] = "no-store"
    return {
        "membership": await member_view(session, row),
        "email_delivered": delivered,
        "invitation_token": token if not delivered else None,
    }


@router.delete("/organizations/{organization_id}/invitations/{membership_id}", tags=["Memberships"])
async def cancel_invitation(
    organization_id: UUID,
    membership_id: UUID,
    session: Session,
    actor: Actor,
    expected_version: Annotated[int | None, Query(gt=0)] = None,
):
    await lock_administration(session)
    access = await organization_access(session, actor, organization_id, "org.members.manage")
    row = await scoped_record(session, Membership, access, membership_id, True)
    check_version(row, expected_version)
    require(
        row.archived_at is None and row.invitation_status in {"pending", "expired"},
        "invitation_closed",
        "Invitation is closed",
        409,
    )
    row.invitation_status = "revoked"
    row.invitation_token_hash = None
    row.is_active = False
    row.status_changed_by = actor.id
    row.management_version += 1
    await audit(session, actor, "membership.invitation_cancelled", "membership", row.id, organization_id)
    await commit(session, row)
    return await member_view(session, row)


@router.post("/invitations/accept", tags=["Memberships"])
async def accept_invitation(body: TokenInput, request: Request, session: Session, actor: Actor):
    user = human(actor)
    require(
        user.email_verified,
        "verified_email_required",
        "Verify your email before accepting an invitation",
        403,
    )
    await lock_administration(session)
    value = token_hash(
        body.token.get_secret_value(), request.app.state.settings.token_pepper.get_secret_value()
    )
    row = await session.scalar(
        select(Membership).where(Membership.invitation_token_hash == value).with_for_update()
    )
    require(
        row
        and row.invitation_status == "pending"
        and row.archived_at is None
        and row.invitation_expires_at
        and row.invitation_expires_at > now(),
        "invalid_invitation",
        "Invitation is invalid or expired",
        409,
    )
    assert row is not None
    organization = required(await session.get(Organization, row.organization_id))
    await validate_department(session, row.organization_id, row.department_id)
    require(
        organization.archived_at is None and (organization.is_active or row.role == "org_admin"),
        "organization_inactive",
        "Organization is inactive",
        409,
    )
    require(
        (row.invited_email or "").lower() == user.email.lower(),
        "invitation_identity_mismatch",
        "The invitation belongs to another verified email",
        403,
    )
    require(
        row.invitation_auth_method is None or row.invitation_auth_method == user.auth_method,
        "invitation_identity_mismatch",
        "The invitation requires another authentication method",
        403,
    )
    row.user_id = user.id
    row.invitation_status = "accepted"
    row.invitation_token_hash = None
    row.joined_at = now()
    row.is_active = True
    row.management_version += 1
    await audit(session, actor, "membership.accepted", "membership", row.id, row.organization_id)
    await commit(session, row)
    return public(row)


@router.patch("/organizations/{organization_id}/members/{membership_id}", tags=["Memberships"])
async def membership_update(
    organization_id: UUID, membership_id: UUID, body: MembershipPatch, session: Session, actor: Actor
):
    await lock_administration(session)
    access = await organization_access(session, actor, organization_id, "org.members.manage")
    row = await scoped_record(session, Membership, access, membership_id, True)
    return await update_membership_record(organization_id, row, body, session, actor)


async def update_membership_record(organization_id, row, body, session, actor):
    """Caller must authorize, lock administration, and load the scoped membership."""
    require(row.archived_at is None, "state_conflict", "Restore the membership before updating it", 409)
    require(
        body.expected_version is None or body.expected_version == row.management_version,
        "version_conflict",
        "Membership changed; refresh before retrying",
        409,
    )
    values = changes(body, {"expected_version"})
    require(
        row.user_id != actor.id or values.get("is_active") is not False,
        "self_membership_action",
        "You cannot disable your own tenant access",
        403,
    )
    require(
        row.invitation_status in {"pending", "accepted"},
        "invitation_closed",
        "Invite this person again to change a closed invitation",
        409,
    )
    require(
        values.get("is_active") is not True or row.invitation_status == "accepted",
        "invitation_not_accepted",
        "The recipient must accept the invitation before activation",
        409,
    )
    if values.get("is_active") is True:
        account = await session.get(User, row.user_id)
        require(
            account and account.is_active and account.archived_at is None,
            "membership_account_inactive",
            "A platform administrator must enable the account first",
            409,
        )
    department_id = values.get("department_id", row.department_id)
    require(
        values.get("role", row.role) != "org_admin" or department_id is None,
        "invalid_scope",
        "Organization administrators cover the whole organization",
    )
    if "department_id" in values or values.get("is_active") is True:
        await validate_department(session, organization_id, department_id)
    update_fields(row, values)
    row.management_version += 1
    row.status_changed_by = actor.id
    if row.invitation_status == "pending" and values.get("is_active") is False:
        row.invitation_status = "revoked"
        row.invitation_token_hash = None
    await audit(
        session,
        actor,
        "membership.updated",
        "membership",
        row.id,
        organization_id,
        {"fields": sorted(values)},
    )
    await commit(session, row)
    return await member_view(session, row)


@router.delete("/organizations/{organization_id}/members/{membership_id}", tags=["Memberships"])
async def membership_archive(
    organization_id: UUID,
    membership_id: UUID,
    session: Session,
    actor: Actor,
    expected_version: Annotated[int | None, Query(gt=0)] = None,
):
    await lock_administration(session)
    access = await organization_access(session, actor, organization_id, "org.members.manage")
    row = await scoped_record(session, Membership, access, membership_id, True)
    return await archive_membership_record(organization_id, row, session, actor, expected_version)


async def archive_membership_record(organization_id, row, session, actor, expected_version):
    """Caller must authorize, lock administration, and load the scoped membership."""
    require(
        row.user_id != actor.id,
        "self_membership_action",
        "You cannot archive your own tenant access",
        403,
    )
    check_version(row, expected_version)
    if row.archived_at is None:
        row.archived_at = now()
        row.archived_by = actor.id
        row.is_active = False
        row.invitation_token_hash = None
        if row.invitation_status == "pending":
            row.invitation_status = "revoked"
        row.status_reason = "archived"
        row.status_changed_by = actor.id
        row.management_version += 1
        await audit(session, actor, "membership.archived", "membership", row.id, organization_id)
    await commit(session, row)
    return await member_view(session, row)


@router.post("/organizations/{organization_id}/members/{membership_id}/restore", tags=["Memberships"])
async def membership_restore(
    organization_id: UUID,
    membership_id: UUID,
    body: Restore,
    session: Session,
    actor: Actor,
):
    await lock_administration(session)
    access = await organization_access(session, actor, organization_id, "org.members.manage")
    row = await scoped_record(session, Membership, access, membership_id, True)
    return await restore_membership_record(organization_id, row, body, session, actor)


async def restore_membership_record(organization_id, row, body, session, actor):
    """Caller must authorize, lock administration, and load the scoped membership."""
    require(
        row.management_version == body.expected_version,
        "version_conflict",
        "Membership changed; refresh before retrying",
        409,
    )
    require(
        row.archived_at is not None and row.user_id is not None,
        "state_conflict",
        "Accepted membership is not archived",
        409,
    )
    row.archived_at = None
    row.archived_by = None
    row.is_active = False
    row.status_reason = "restored_pending_activation"
    row.management_version += 1
    await audit(session, actor, "membership.restored", "membership", row.id, organization_id)
    await commit(session, row)
    return await member_view(session, row)
