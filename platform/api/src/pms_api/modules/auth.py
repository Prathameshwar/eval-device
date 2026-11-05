from typing import Literal

from fastapi import APIRouter, Request
from pydantic import EmailStr, Field, SecretStr
from sqlalchemy import select, update

from pms_api.core.common import AppError, now, require
from pms_api.core.dependencies import Session
from pms_api.database.models import Department, LocalCredential, LocalSession, Membership, Organization, User
from pms_api.modules.common import audit, commit, public
from pms_api.modules.schemas import Input
from pms_api.security.access import GRANTS, Actor, Principal, effective_permissions, human
from pms_api.security.local_auth import (
    consume_action_token,
    create_action_token,
    enforce_rate_limit,
    hash_password,
    issue_browser_session,
    issue_session,
    lock_local_identity,
    locked_actor,
    normalize_email,
    password_needs_rehash,
    refresh_hash,
    revoke_user_actions,
    revoke_user_sessions,
    usable_identity,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


class Login(Input):
    email: EmailStr
    password: SecretStr = Field(min_length=1, max_length=1024)


class BrowserLogin(Login):
    remember: bool = False


class Refresh(Input):
    refresh_token: SecretStr = Field(min_length=20, max_length=512)


class ActionPassword(Input):
    token: SecretStr = Field(min_length=20, max_length=512)
    password: SecretStr = Field(min_length=12, max_length=1024)


class PasswordChange(Input):
    current_password: SecretStr = Field(min_length=1, max_length=1024)
    new_password: SecretStr = Field(min_length=12, max_length=1024)


class Recovery(Input):
    email: EmailStr


class EmailChange(Input):
    email: EmailStr
    current_password: SecretStr = Field(min_length=1, max_length=1024)


class EmailConfirm(Input):
    token: SecretStr = Field(min_length=20, max_length=512)


def enabled(request: Request):
    require(
        request.app.state.settings.local_auth_enabled,
        "local_auth_disabled",
        "Local account authentication is disabled",
        503,
    )


def email_available(request: Request):
    require(
        not request.app.state.settings.vm_local_mode,
        "email_unavailable",
        "Email actions require an SMTP provider",
        503,
    )


def response_user(user: User) -> dict:
    value = public(user)
    value["authentication_methods"] = [user.auth_method]
    value["password_management"] = user.auth_method == "local"
    return value


@router.post("/login")
async def login(body: Login, request: Request, session: Session):
    return await authenticate_password(body, request, session)


@router.post("/browser/login")
async def browser_login(body: BrowserLogin, request: Request, session: Session):
    return await authenticate_password(body, request, session, browser=True)


async def authenticate_password(body, request, session, browser=False):
    enabled(request)
    email = normalize_email(str(body.email))
    source = request.client.host if request.client else "unknown"
    await enforce_rate_limit(session, request.app.state.settings, "login", source + ":" + email, 10)
    await enforce_rate_limit(session, request.app.state.settings, "login_account", email, 30, 300)
    credential = await session.scalar(select(LocalCredential).where(LocalCredential.login_email == email))
    expected_hash = credential.password_hash if credential else None
    expected_version = credential.credential_version if credential else None
    valid = await verify_password(expected_hash, body.password.get_secret_value())
    if not valid or not credential:
        raise AppError(401, "invalid_credentials", "Email or password is invalid")
    replacement_hash = (
        await hash_password(body.password.get_secret_value())
        if expected_hash and password_needs_rehash(expected_hash)
        else None
    )
    # Hash outside locks, then compare the exact credential that was verified.
    user, credential = await lock_local_identity(session, credential.user_id)
    require(
        usable_identity(user, credential)
        and credential.login_email == email
        and credential.password_hash == expected_hash
        and credential.credential_version == expected_version,
        "invalid_credentials",
        "Email or password is invalid",
        401,
    )
    if replacement_hash:
        credential.password_hash = replacement_hash
        credential.updated_at = now()
    if browser:
        auth_session, tokens = await issue_browser_session(
            session, user, credential, request.app.state.settings
        )
    else:
        auth_session, tokens = await issue_session(session, user, credential, request.app.state.settings)
    user.last_login_at = now()
    await audit(session, Principal(user=user), "identity.local_login", "local_session", auth_session.id)
    await commit(session)
    return {**tokens, "user": response_user(user)}


@router.post("/refresh")
async def refresh(body: Refresh, request: Request, session: Session):
    enabled(request)
    raw = body.refresh_token.get_secret_value()
    source = request.client.host if request.client else "unknown"
    await enforce_rate_limit(session, request.app.state.settings, "refresh", source, 60)
    row = await session.scalar(
        select(LocalSession).where(
            LocalSession.refresh_token_hash == refresh_hash(raw, request.app.state.settings)
        )
    )
    if not row:
        raise AppError(401, "invalid_refresh_token", "Refresh token is invalid")
    user, credential = await lock_local_identity(session, row.user_id)
    row = await session.get(LocalSession, row.id, with_for_update=True, populate_existing=True)
    require(row is not None, "invalid_refresh_token", "Refresh token is invalid", 401)
    assert row is not None
    if row.revoked_at is not None:
        await session.execute(
            update(LocalSession)
            .where(LocalSession.family_id == row.family_id, LocalSession.revoked_at.is_(None))
            .values(revoked_at=now(), revoke_reason="refresh_reuse")
        )
        await session.commit()
        raise AppError(401, "refresh_reuse", "Refresh token reuse was detected")
    require(
        row.expires_at > now()
        and row.browser_token_hash is None
        and usable_identity(user, credential)
        and row.credential_version == credential.credential_version,
        "invalid_refresh_token",
        "Refresh token is invalid",
        401,
    )
    row.revoked_at = now()
    row.revoke_reason = "rotated"
    _, tokens = await issue_session(
        session, user, credential, request.app.state.settings, family_id=row.family_id
    )
    await commit(session)
    return tokens


@router.post("/logout", status_code=204)
async def logout(session: Session, actor: Actor):
    _, _, row = await locked_actor(session, actor)
    if row and row.revoked_at is None:
        row.revoked_at = now()
        row.revoke_reason = "logout"
        await audit(session, actor, "identity.local_logout", "local_session", row.id)
    await commit(session)
    return None


@router.post("/logout-all", status_code=204)
async def logout_all(session: Session, actor: Actor):
    user, _, _ = await locked_actor(session, actor)
    await revoke_user_sessions(session, user.id, "logout_all")
    await audit(session, actor, "identity.local_logout_all", "user", user.id)
    await commit(session)
    return None


async def set_password(
    body: ActionPassword, purpose: Literal["setup", "password_reset"], request: Request, session: Session
):
    enabled(request)
    source = request.client.host if request.client else "unknown"
    await enforce_rate_limit(session, request.app.state.settings, "account_action", source, 20)
    action = await consume_action_token(
        session, request.app.state.settings, body.token.get_secret_value(), purpose
    )
    user, credential = await lock_local_identity(session, action.user_id)
    require(
        user.auth_method == "local" and user.archived_at is None,
        "invalid_action_token",
        "The account action token is invalid or expired",
        422,
    )
    credential.password_hash = await hash_password(body.password.get_secret_value())
    credential.credential_version += 1
    credential.password_changed_at = now()
    credential.setup_completed_at = credential.setup_completed_at or now()
    credential.updated_at = now()
    user.email_verified = True
    await revoke_user_sessions(session, user.id, purpose)
    await revoke_user_actions(session, user.id)
    await audit(session, Principal(user=user), f"identity.{purpose}_completed", "user", user.id)
    await commit(session)
    return {"completed": True}


@router.post("/password/setup")
async def password_setup(body: ActionPassword, request: Request, session: Session):
    return await set_password(body, "setup", request, session)


@router.post("/password/reset")
async def password_reset(body: ActionPassword, request: Request, session: Session):
    return await set_password(body, "password_reset", request, session)


@router.post("/password/change")
async def password_change(body: PasswordChange, request: Request, session: Session, actor: Actor):
    enabled(request)
    await enforce_rate_limit(session, request.app.state.settings, "password_change", str(actor.id), 10, 300)
    user, credential, _ = await locked_actor(session, actor)
    require(
        await verify_password(credential.password_hash, body.current_password.get_secret_value()),
        "invalid_current_password",
        "Current password is invalid",
        422,
    )
    credential.password_hash = await hash_password(body.new_password.get_secret_value())
    credential.credential_version += 1
    credential.password_changed_at = now()
    credential.updated_at = now()
    await revoke_user_sessions(session, user.id, "password_change")
    await revoke_user_actions(session, user.id)
    await audit(session, actor, "identity.password_changed", "user", user.id)
    await commit(session)
    return {"completed": True}


@router.post("/password/forgot", status_code=202)
async def password_forgot(body: Recovery, request: Request, session: Session):
    enabled(request)
    email_available(request)
    email = normalize_email(str(body.email))
    source = request.client.host if request.client else "unknown"
    await enforce_rate_limit(session, request.app.state.settings, "recovery", source + ":" + email, 5, 300)
    await enforce_rate_limit(session, request.app.state.settings, "recovery_account", email, 10, 300)
    credential = await session.scalar(select(LocalCredential).where(LocalCredential.login_email == email))
    user = await session.get(User, credential.user_id) if credential else None
    # Keep the expensive portion of recovery timing independent of account existence.
    await verify_password(None, "recovery-request-timing-value")
    if credential:
        user, credential = await lock_local_identity(session, credential.user_id)
    if user and credential and usable_identity(user, credential) and credential.login_email == email:
        await create_action_token(session, request.app.state.settings, user, "password_reset")
        await audit(session, Principal(user=user), "identity.password_recovery_requested", "user", user.id)
        await commit(session)
    return {"accepted": True}


@router.post("/email/change", status_code=202)
async def email_change(body: EmailChange, request: Request, session: Session, actor: Actor):
    enabled(request)
    email_available(request)
    await enforce_rate_limit(session, request.app.state.settings, "email_change", str(actor.id), 5, 300)
    user, credential, _ = await locked_actor(session, actor)
    require(
        await verify_password(credential.password_hash, body.current_password.get_secret_value()),
        "invalid_current_password",
        "Current password is invalid",
        422,
    )
    target = normalize_email(str(body.email))
    duplicate = await session.scalar(
        select(LocalCredential.user_id).where(
            LocalCredential.login_email == target,
            LocalCredential.user_id != user.id,
        )
    )
    require(not duplicate, "local_identity_exists", "A local account already uses this email", 409)
    await create_action_token(session, request.app.state.settings, user, "email_change", target)
    await audit(session, actor, "identity.email_change_requested", "user", user.id)
    await commit(session)
    return {"accepted": True}


@router.post("/email/confirm")
async def email_confirm(body: EmailConfirm, request: Request, session: Session):
    enabled(request)
    source = request.client.host if request.client else "unknown"
    await enforce_rate_limit(session, request.app.state.settings, "account_action", source, 20)
    action = await consume_action_token(
        session, request.app.state.settings, body.token.get_secret_value(), "email_change"
    )
    require(
        action.target_email, "invalid_action_token", "The account action token is invalid or expired", 422
    )
    user, credential = await lock_local_identity(session, action.user_id)
    require(
        user.auth_method == "local" and user.archived_at is None,
        "invalid_action_token",
        "The account action token is invalid or expired",
        422,
    )
    user.email = action.target_email
    user.email_verified = True
    credential.login_email = action.target_email
    credential.credential_version += 1
    credential.updated_at = now()
    await revoke_user_sessions(session, user.id, "email_change")
    await revoke_user_actions(session, user.id)
    await audit(session, Principal(user=user), "identity.email_changed", "user", user.id)
    await commit(session)
    return {"completed": True}


@router.get("/context")
async def browser_context(session: Session, actor: Actor):
    """Current, separate access contexts; never union platform and tenant grants."""
    user = human(actor)
    contexts = []
    if user.platform_role in GRANTS:
        contexts.append(
            {
                "id": "platform",
                "name": "Platform",
                "role": user.platform_role,
                "department_id": None,
                "permissions": sorted(GRANTS[user.platform_role]),
            }
        )
    rows = (
        await session.execute(
            select(Membership, Organization)
            .join(Organization, Membership.organization_id == Organization.id)
            .outerjoin(Department, Membership.department_id == Department.id)
            .where(
                Membership.user_id == user.id,
                Membership.is_active.is_(True),
                Membership.invitation_status == "accepted",
                Membership.archived_at.is_(None),
                Organization.is_active.is_(True),
                Organization.archived_at.is_(None),
                (Membership.department_id.is_(None))
                | ((Department.is_active.is_(True)) & (Department.archived_at.is_(None))),
            )
            .order_by(Organization.name, Organization.id)
        )
    ).all()
    for membership, organization in rows:
        contexts.append(
            {
                "id": str(organization.id),
                "name": organization.name,
                "role": membership.role,
                "department_id": membership.department_id,
                "permissions": sorted(await effective_permissions(session, membership)),
            }
        )
    return {"user": response_user(user), "contexts": contexts}
