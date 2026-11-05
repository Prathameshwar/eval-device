import json
import os
from datetime import timedelta
from uuid import UUID, uuid4

import anyio
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select, text, update

from pms_api.core.common import AppError, canonical, new_token, now, require, token_hash
from pms_api.database.models import (
    AccountActionToken,
    AccountEmailOutbox,
    LocalCredential,
    LocalSession,
    User,
)
from pms_api.integrations.vault import CredentialVault

PASSWORDS = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1, hash_len=32, salt_len=16)
PASSWORD_HASH_LIMIT = anyio.CapacityLimiter(4)
DUMMY_PASSWORD_HASH = PASSWORDS.hash("invalid-account-timing-value")
LOCAL_ISSUER = "pms-local"
LOCAL_AUDIENCE = "pms-api"


def normalize_email(value: str) -> str:
    return value.strip().lower()


async def hash_password(value: str) -> str:
    if len(value) < 12 or len(value) > 1024:
        raise AppError(422, "invalid_password", "Password must contain between 12 and 1024 characters")
    if value.casefold() in {"password1234", "password12345", "qwerty123456", "letmein123456"}:
        raise AppError(422, "invalid_password", "Choose a less common password")
    return await anyio.to_thread.run_sync(PASSWORDS.hash, value, limiter=PASSWORD_HASH_LIMIT)


async def verify_password(encoded: str | None, value: str) -> bool:
    if len(value) > 1024:
        return False
    candidate = encoded or DUMMY_PASSWORD_HASH

    def verify() -> bool:
        try:
            return PASSWORDS.verify(candidate, value) and encoded is not None
        except (InvalidHashError, VerifyMismatchError):
            return False

    return await anyio.to_thread.run_sync(verify, limiter=PASSWORD_HASH_LIMIT)


def password_needs_rehash(encoded: str) -> bool:
    return PASSWORDS.check_needs_rehash(encoded)


def refresh_hash(token: str, settings) -> str:
    return token_hash(token, settings.token_pepper.get_secret_value())


def access_token(user: User, session: LocalSession, settings) -> tuple[str, int]:
    issued = now()
    seconds = settings.local_access_minutes * 60
    claims = {
        "iss": LOCAL_ISSUER,
        "aud": LOCAL_AUDIENCE,
        "sub": str(user.id),
        "sid": str(session.id),
        "cv": session.credential_version,
        "typ": "access",
        "iat": issued,
        "exp": issued + timedelta(seconds=seconds),
    }
    encoded = jwt.encode(claims, settings.local_token_signing_key.get_secret_value(), algorithm="HS256")
    return "pms_" + encoded, seconds


async def issue_session(session, user: User, credential: LocalCredential, settings, family_id=None):
    raw = new_token("ref_")
    timestamp = now()
    row = LocalSession(
        id=uuid4(),
        user_id=user.id,
        family_id=family_id or uuid4(),
        refresh_token_hash=refresh_hash(raw, settings),
        credential_version=credential.credential_version,
        created_at=timestamp,
        last_used_at=timestamp,
        expires_at=timestamp + timedelta(days=settings.local_refresh_days),
    )
    session.add(row)
    await session.flush()
    access, expires_in = access_token(user, row, settings)
    return row, {
        "access_token": access,
        "refresh_token": raw,
        "token_type": "bearer",
        "expires_in": expires_in,
    }


async def lock_local_identity(session, user_id):
    """All auth writers lock user -> credential -> sessions/actions, refreshing cached ORM rows."""
    user = await session.get(User, user_id, with_for_update=True, populate_existing=True)
    credential = await session.get(LocalCredential, user_id, with_for_update=True, populate_existing=True)
    return user, credential


def usable_identity(user, credential) -> bool:
    return bool(
        user
        and credential
        and user.auth_method == "local"
        and user.is_active
        and user.archived_at is None
        and user.email_verified
        and credential.setup_completed_at
        and credential.password_hash
    )


async def locked_actor(session, actor):
    """Reauthorize a local account mutation after acquiring the credential locks."""
    require(
        actor.user and actor.authentication_method == "local",
        "local_identity_required",
        "Local login is required",
        403,
    )
    user, credential = await lock_local_identity(session, actor.user.id)
    row = (
        await session.get(LocalSession, actor.session_id, populate_existing=True)
        if actor.session_id
        else None
    )
    require(
        usable_identity(user, credential)
        and row
        and row.user_id == user.id
        and row.revoked_at is None
        and row.expires_at > now()
        and row.credential_version == credential.credential_version,
        "invalid_token",
        "Invalid access token",
        401,
    )
    return user, credential, row


async def issue_browser_session(session, user, credential, settings):
    raw = new_token("web_")
    timestamp = now()
    seconds = settings.local_browser_session_hours * 3600
    row = LocalSession(
        id=uuid4(),
        user_id=user.id,
        family_id=uuid4(),
        refresh_token_hash=refresh_hash(new_token("ref_"), settings),
        browser_token_hash=refresh_hash(raw, settings),
        credential_version=credential.credential_version,
        created_at=timestamp,
        last_used_at=timestamp,
        expires_at=timestamp + timedelta(seconds=seconds),
    )
    session.add(row)
    await session.flush()
    return row, {"session_token": raw, "expires_in": seconds}


async def verify_browser_session(session, token, settings):
    if not settings.local_auth_enabled:
        raise AppError(401, "invalid_token", "Invalid access token")
    row = await session.scalar(
        select(LocalSession).where(
            LocalSession.browser_token_hash == refresh_hash(token, settings),
            LocalSession.revoked_at.is_(None),
            LocalSession.expires_at > now(),
        )
    )
    user = await session.get(User, row.user_id) if row else None
    credential = await session.get(LocalCredential, row.user_id) if row else None
    if (
        not row
        or not credential
        or not usable_identity(user, credential)
        or row.credential_version != credential.credential_version
    ):
        raise AppError(401, "invalid_token", "Invalid access token")
    return user, row


async def verify_access(session, token: str, settings):
    if not settings.local_auth_enabled:
        raise AppError(401, "invalid_token", "Invalid access token")
    try:
        claims = jwt.decode(
            token.removeprefix("pms_"),
            settings.local_token_signing_key.get_secret_value(),
            algorithms=["HS256"],
            audience=LOCAL_AUDIENCE,
            issuer=LOCAL_ISSUER,
            options={"require": ["exp", "iat", "iss", "aud", "sub", "sid", "cv", "typ"]},
        )
        if claims["typ"] != "access":
            raise ValueError()
        user_id, session_id = UUID(claims["sub"]), UUID(claims["sid"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        raise AppError(401, "invalid_token", "Invalid access token") from None
    row = await session.scalar(
        select(LocalSession).where(
            LocalSession.id == session_id,
            LocalSession.user_id == user_id,
            LocalSession.revoked_at.is_(None),
            LocalSession.expires_at > now(),
        )
    )
    credential = await session.get(LocalCredential, user_id)
    user = await session.get(User, user_id)
    if (
        not row
        or not credential
        or not user
        or not usable_identity(user, credential)
        or row.credential_version != credential.credential_version
        or claims["cv"] != credential.credential_version
    ):
        raise AppError(401, "invalid_token", "Invalid access token")
    return user, row


async def revoke_user_sessions(session, user_id: UUID, reason: str):
    await session.execute(
        update(LocalSession)
        .where(LocalSession.user_id == user_id, LocalSession.revoked_at.is_(None))
        .values(revoked_at=now(), revoke_reason=reason)
    )


async def revoke_user_actions(session, user_id: UUID):
    await session.execute(
        update(AccountActionToken)
        .where(AccountActionToken.user_id == user_id, AccountActionToken.consumed_at.is_(None))
        .values(consumed_at=now())
    )


async def enforce_rate_limit(session, settings, category: str, identity: str, limit: int, seconds: int = 60):
    key = token_hash(category + ":" + identity, settings.token_pepper.get_secret_value())
    timestamp = now()
    row = await session.execute(
        text(
            """
            INSERT INTO device_platform.auth_rate_limits
              (key_hash,category,window_started_at,request_count,expires_at)
            VALUES (:key,:category,:now,1,:expires)
            ON CONFLICT (key_hash,category) DO UPDATE SET
              window_started_at=CASE WHEN device_platform.auth_rate_limits.expires_at<=:now
                THEN :now ELSE device_platform.auth_rate_limits.window_started_at END,
              request_count=CASE WHEN device_platform.auth_rate_limits.expires_at<=:now
                THEN 1 ELSE device_platform.auth_rate_limits.request_count+1 END,
              expires_at=CASE WHEN device_platform.auth_rate_limits.expires_at<=:now
                THEN :expires ELSE device_platform.auth_rate_limits.expires_at END
            RETURNING request_count
            """
        ),
        {
            "key": key,
            "category": category,
            "now": timestamp,
            "expires": timestamp + timedelta(seconds=seconds),
        },
    )
    count = row.scalar_one()
    await session.commit()
    if count > limit:
        raise AppError(429, "rate_limit", "Request rate limit exceeded")


async def create_action_token(session, settings, user: User, purpose: str, target_email: str | None = None):
    user, credential = await lock_local_identity(session, user.id)
    require(
        user and credential and user.auth_method == "local" and user.archived_at is None,
        "invalid_action_token",
        "The account is unavailable",
        422,
    )
    raw = new_token("act_")
    timestamp = now()
    await session.execute(
        update(AccountActionToken)
        .where(
            AccountActionToken.user_id == user.id,
            AccountActionToken.purpose == purpose,
            AccountActionToken.consumed_at.is_(None),
        )
        .values(consumed_at=timestamp)
    )
    action = AccountActionToken(
        id=uuid4(),
        user_id=user.id,
        purpose=purpose,
        token_hash=refresh_hash(raw, settings),
        credential_version=credential.credential_version,
        target_email=normalize_email(target_email) if target_email else None,
        created_at=timestamp,
        expires_at=timestamp + timedelta(hours=settings.account_action_hours),
    )
    outbox_id = uuid4()
    payload = {"token": raw, "purpose": purpose, "user_id": str(user.id)}
    vault = CredentialVault(settings)
    key_id = settings.active_credential_key
    nonce = os.urandom(12)
    encrypted = AESGCM(vault.key(key_id)).encrypt(
        nonce,
        canonical(payload).encode(),
        f"pms:account-email:v1:{user.id}:{outbox_id}".encode(),
    )
    outbox = AccountEmailOutbox(
        id=outbox_id,
        user_id=user.id,
        purpose=purpose,
        recipient=normalize_email(target_email or user.email),
        encrypted_payload=nonce + encrypted,
        key_id=key_id,
        created_at=timestamp,
        expires_at=action.expires_at,
    )
    session.add_all([action, outbox])
    # The raw value is only needed by a freshly authorized manual-delivery response.
    # It is never persisted outside the encrypted outbox or exposed by reads.
    return action, outbox, raw


async def consume_action_token(session, settings, raw: str, purpose: str):
    value = refresh_hash(raw, settings)
    user_id = await session.scalar(
        select(AccountActionToken.user_id).where(
            AccountActionToken.token_hash == value,
            AccountActionToken.purpose == purpose,
        )
    )
    if not user_id:
        raise AppError(422, "invalid_action_token", "The account action token is invalid or expired")
    user, credential = await lock_local_identity(session, user_id)
    if not user or not credential or user.auth_method != "local" or user.archived_at is not None:
        raise AppError(422, "invalid_action_token", "The account action token is invalid or expired")
    action = await session.scalar(
        select(AccountActionToken)
        .where(
            AccountActionToken.token_hash == value,
            AccountActionToken.purpose == purpose,
            AccountActionToken.consumed_at.is_(None),
            AccountActionToken.expires_at > now(),
            AccountActionToken.credential_version == credential.credential_version,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not action:
        raise AppError(422, "invalid_action_token", "The account action token is invalid or expired")
    action.consumed_at = now()
    return action


def decrypt_outbox_payload(row: AccountEmailOutbox, settings) -> dict:
    try:
        vault = CredentialVault(settings)
        plaintext = AESGCM(vault.key(row.key_id)).decrypt(
            row.encrypted_payload[:12],
            row.encrypted_payload[12:],
            f"pms:account-email:v1:{row.user_id}:{row.id}".encode(),
        )
        return json.loads(plaintext)
    except AppError:
        raise
    except Exception as error:
        raise AppError(503, "account_delivery_unavailable", "Account email could not be prepared") from error
