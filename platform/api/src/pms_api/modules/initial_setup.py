"""One-time, installation-key-authorized creation of the first local administrator."""

import secrets
from uuid import uuid4

from fastapi import APIRouter, Request
from pydantic import EmailStr, Field, SecretStr, field_validator
from sqlalchemy import select

from pms_api.core.common import now, require
from pms_api.core.dependencies import Session
from pms_api.database.models import LocalCredential, User
from pms_api.database.session import lock_administration
from pms_api.modules.common import audit, commit
from pms_api.modules.schemas import Name, PeopleInput
from pms_api.security.local_auth import enforce_rate_limit, hash_password, normalize_email

router = APIRouter(prefix="/auth/setup", tags=["Authentication"])


class SetupKey(PeopleInput):
    installation_key: SecretStr = Field(min_length=1, max_length=512)

    @field_validator("*")
    @classmethod
    def valid_secret_text(cls, value):
        if isinstance(value, SecretStr):
            PeopleInput.valid_text(value.get_secret_value())
        return value


class InitialAdministrator(SetupKey):
    display_name: Name
    email: EmailStr
    password: SecretStr = Field(min_length=12, max_length=1024)


async def is_pristine(session) -> bool:
    # Include inactive/archived/OIDC identities. This is never an account recovery path.
    # The database's last-administrator invariant prevents reopening after setup.
    return await session.scalar(select(User.id).limit(1)) is None


@router.get("")
async def status(request: Request, session: Session):
    settings = request.app.state.settings
    required = await is_pristine(session)
    return {
        "required": required,
        "available": required
        and settings.local_auth_enabled
        and bool(settings.initial_setup_key.get_secret_value()),
    }


async def authorize(body: SetupKey, request: Request, session):
    settings = request.app.state.settings
    require(await is_pristine(session), "setup_completed", "Initial setup is already closed", 409)
    expected = settings.initial_setup_key.get_secret_value()
    require(
        settings.local_auth_enabled and bool(expected),
        "setup_unavailable",
        "Initial setup has not been enabled by the deployment operator",
        503,
    )
    source = request.client.host if request.client else "unknown"
    # Use the existing constrained account-action category with a separate key namespace.
    await enforce_rate_limit(session, settings, "account_action", "initial_setup:" + source, 10, 300)
    require(
        secrets.compare_digest(body.installation_key.get_secret_value().encode(), expected.encode()),
        "invalid_setup_key",
        "The installation key is invalid",
        403,
    )


@router.post("/verify")
async def verify(body: SetupKey, request: Request, session: Session):
    await authorize(body, request, session)
    return {"verified": True}


@router.post("", status_code=201)
async def create(body: InitialAdministrator, request: Request, session: Session):
    await authorize(body, request, session)
    encoded = await hash_password(body.password.get_secret_value())
    await lock_administration(session)
    require(await is_pristine(session), "setup_completed", "Initial setup is already closed", 409)
    email = normalize_email(str(body.email))
    user = User(
        id=uuid4(),
        auth_method="local",
        email=email,
        email_verified=True,
        display_name=body.display_name,
        platform_role="platform_admin",
    )
    session.add(user)
    await session.flush()
    session.add(
        LocalCredential(user_id=user.id, login_email=email, password_hash=encoded, setup_completed_at=now())
    )
    await audit(
        session,
        None,
        "platform.initial_admin_created",
        "user",
        user.id,
        details={"source": "web_initial_setup"},
    )
    await commit(session)
    return {"completed": True}
