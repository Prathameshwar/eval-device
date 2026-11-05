import io
from types import SimpleNamespace

import pytest
from pydantic import SecretStr
from sqlalchemy.engine import make_url

from pms_api import cli
from pms_api.core.common import AppError
from pms_api.security.local_auth import verify_password


def arguments(**overrides):
    return SimpleNamespace(
        **{
            "email": "developer@example.com",
            "name": "Local administrator",
            "verified_operator": True,
            "local_password_stdin": True,
            **overrides,
        }
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("environment", ["test", "staging", "production"])
async def test_password_bootstrap_is_local_only(monkeypatch, environment):
    monkeypatch.setattr(
        cli, "Settings", lambda: SimpleNamespace(local_auth_enabled=True, environment=environment)
    )
    with pytest.raises(AppError) as denied:
        await cli.bootstrap_local(arguments())
    assert denied.value.code == "local_environment_required"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("password", "verified", "code"),
    [
        ("too-short", True, "invalid_password"),
        ("x" * 1025, True, "invalid_password"),
        ("", True, "invalid_password"),
        ("valid development password", False, "verify_operator"),
    ],
)
async def test_password_bootstrap_checks_input_before_database(monkeypatch, password, verified, code):
    monkeypatch.setattr(
        cli, "Settings", lambda: SimpleNamespace(local_auth_enabled=True, environment="local")
    )
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO(password))
    with pytest.raises(AppError) as denied:
        await cli.bootstrap_local(arguments(verified_operator=verified))
    assert denied.value.code == code


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"email": "not-an-email"},
        {"name": "   "},
        {"name": "x" * 257},
        {"name": "Invalid\x00name"},
        {"name": "Invalid\ud800name"},
    ],
)
async def test_bootstrap_rejects_unusable_identity_before_hashing_or_database(monkeypatch, overrides):
    monkeypatch.setattr(
        cli, "Settings", lambda: SimpleNamespace(local_auth_enabled=True, environment="local")
    )

    def forbidden(*args, **kwargs):
        pytest.fail("Invalid identity reached password hashing or the database")

    monkeypatch.setattr(cli, "hash_password", forbidden)
    monkeypatch.setattr(cli, "engine_for", forbidden)
    with pytest.raises(AppError) as denied:
        await cli.bootstrap_local(arguments(**overrides))
    assert denied.value.code == "invalid_admin_identity"
    assert str(overrides) not in str(denied.value)


@pytest.mark.asyncio
async def test_local_password_bootstrap_is_atomic_audited_and_supports_login(platform, monkeypatch, capsys):
    settings = platform.settings.model_copy(
        update={
            "environment": "local",
            "smtp_host": None,
            "smtp_sender": None,
            "migration_database_url": SecretStr(
                make_url(platform.dsn)
                .set(drivername="postgresql+psycopg")
                .render_as_string(hide_password=False)
            ),
        }
    )
    monkeypatch.setattr(cli, "Settings", lambda: settings)
    password = "a private local development password"
    args = arguments()
    original_audit = cli.audit

    async def fail_audit(*args, **kwargs):
        raise AppError(409, "audit_failed", "Test atomic rollback")

    monkeypatch.setattr(cli, "audit", fail_audit)
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO(password + "\r\n"))
    with pytest.raises(AppError, match="Test atomic rollback"):
        await cli.bootstrap_local(args)
    assert platform.sql("SELECT count(*) FROM device_platform.users") == [(0,)]
    assert platform.sql("SELECT count(*) FROM device_platform.local_credentials") == [(0,)]

    monkeypatch.setattr(cli, "audit", original_audit)
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO(password + "\r\n"))
    await cli.bootstrap_local(args)
    [(role, verified, encoded, completed)] = platform.sql(
        "SELECT u.platform_role,u.email_verified,c.password_hash,c.setup_completed_at "
        "FROM device_platform.users u JOIN device_platform.local_credentials c ON c.user_id=u.id"
    )
    assert (role, verified) == ("platform_admin", True)
    assert completed is not None
    assert await verify_password(encoded, password)
    assert platform.sql("SELECT count(*) FROM device_platform.account_action_tokens") == [(0,)]
    assert platform.sql("SELECT count(*) FROM device_platform.account_email_outbox") == [(0,)]
    assert platform.sql(
        "SELECT details->>'source' FROM device_platform.activity_events "
        "WHERE event_type='platform.local_admin_bootstrapped'"
    ) == [("local_development",)]
    response = platform.call(
        "POST", "/auth/browser/login", json={"email": args.email, "password": password, "remember": True}
    )
    platform.call("GET", "/platform/dashboard-stats", response["session_token"])
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO(password))
    with pytest.raises(AppError) as denied:
        await cli.bootstrap_local(args)
    assert denied.value.code == "bootstrap_completed"
    assert password not in capsys.readouterr().out
