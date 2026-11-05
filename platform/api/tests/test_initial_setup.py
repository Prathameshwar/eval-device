import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import anyio
import pytest
from dotenv import dotenv_values
from pydantic import SecretStr, ValidationError

from pms_api.cli import init_local
from pms_api.core.common import AppError
from pms_api.core.config import Settings
from pms_api.modules import initial_setup
from pms_api.security.local_auth import PASSWORDS

KEY = "test-installation-key-for-first-run-only-12345"
DETAILS = {
    "installation_key": KEY,
    "email": "first.admin@example.com",
    "display_name": "First Administrator",
    "password": "a unique initial administrator passphrase",
}


def enable(platform):
    platform.settings.initial_setup_key = SecretStr(KEY)


def test_fresh_setup_requires_private_configuration(platform):
    assert platform.call("GET", "/auth/setup") == {"required": True, "available": False}
    assert (
        platform.call("POST", "/auth/setup", expected=503, json=DETAILS)["error"]["code"]
        == "setup_unavailable"
    )
    enable(platform)
    platform.settings.local_auth_enabled = False
    assert not platform.call("GET", "/auth/setup")["available"]
    platform.call("POST", "/auth/setup/verify", expected=503, json={"installation_key": KEY})
    assert platform.sql("SELECT count(*) FROM device_platform.users") == [(0,)]


def test_setup_creates_hashed_audited_admin_and_closes_with_real_login(platform, caplog):
    enable(platform)
    response = platform.client.get("/api/v1/auth/setup")
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"required": True, "available": True}
    assert platform.call("POST", "/auth/setup/verify", json={"installation_key": KEY}) == {"verified": True}
    assert platform.sql("SELECT count(*) FROM device_platform.users") == [(0,)]
    result = platform.call(
        "POST", "/auth/setup", expected=201, json={**DETAILS, "email": "First.Admin@example.com"}
    )
    assert result == {"completed": True}
    [(name, email, role, verified, password_hash, completed)] = platform.sql(
        "SELECT u.display_name,u.email,u.platform_role,u.email_verified,c.password_hash,c.setup_completed_at "
        "FROM device_platform.users u JOIN device_platform.local_credentials c ON c.user_id=u.id"
    )
    assert (name, email, role, verified) == (
        DETAILS["display_name"],
        DETAILS["email"],
        "platform_admin",
        True,
    )
    assert password_hash.startswith("$argon2id$") and PASSWORDS.verify(password_hash, DETAILS["password"])
    assert completed is not None
    assert platform.sql("SELECT count(*) FROM device_platform.account_email_outbox") == [(0,)]
    assert platform.sql(
        "SELECT details FROM device_platform.activity_events WHERE event_type='platform.initial_admin_created'"
    ) == [({"source": "web_initial_setup", "actor_role": "system", "scope": "platform"},)]
    assert platform.call("GET", "/auth/setup") == {"required": False, "available": False}
    platform.call("POST", "/auth/setup/verify", expected=409, json={"installation_key": KEY})
    assert (
        platform.call("POST", "/auth/setup", expected=409, json=DETAILS)["error"]["code"] == "setup_completed"
    )
    login = platform.call(
        "POST", "/auth/browser/login", json={"email": DETAILS["email"], "password": DETAILS["password"]}
    )
    platform.call("GET", "/platform/dashboard-stats", login["session_token"])
    assert KEY not in caplog.text and DETAILS["password"] not in caplog.text


def test_invalid_keys_and_details_never_create_accounts_or_echo_secrets(platform):
    enable(platform)
    for key in ["incorrect", "invalid-unicode-\u2603"]:
        result = platform.call("POST", "/auth/setup", expected=403, json={**DETAILS, "installation_key": key})
        assert result["error"]["code"] == "invalid_setup_key"
        assert key not in str(result)
    for changes in [
        {"display_name": "   "},
        {"email": "not-an-email"},
        {"password": "short"},
        {"password": "password1234"},
        {"password": "x" * 1025},
        {"platform_role": "platform_admin"},
    ]:
        result = platform.call("POST", "/auth/setup", expected=422, json={**DETAILS, **changes})
        assert KEY not in str(result) and DETAILS["password"] not in str(result)
    assert platform.sql("SELECT count(*) FROM device_platform.users") == [(0,)]


def test_archived_identity_also_closes_initial_setup(platform):
    enable(platform)
    _, user = platform.user("preexisting")
    platform.sql(
        "UPDATE device_platform.users SET is_active=false,archived_at=now() WHERE id=%s", (user["id"],)
    )
    assert platform.call("GET", "/auth/setup") == {"required": False, "available": False}
    platform.call("POST", "/auth/setup", expected=409, json=DETAILS)


def test_invalid_text_is_rejected_before_hashing_or_database(platform, monkeypatch):
    enable(platform)

    async def forbidden(*args, **kwargs):
        pytest.fail("Invalid text reached setup authorization or password hashing")

    monkeypatch.setattr(initial_setup, "authorize", forbidden)
    monkeypatch.setattr(initial_setup, "hash_password", forbidden)
    for field in ("display_name", "installation_key", "password"):
        for invalid in ("\x00", "\ud800", "\udfff"):
            response = platform.client.post(
                "/api/v1/auth/setup",
                content=json.dumps({**DETAILS, field: "synthetic invalid value" + invalid}),
                headers={"Content-Type": "application/json"},
            )
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "invalid_request"
            assert "synthetic invalid value" not in response.text
            assert KEY not in response.text and DETAILS["password"] not in response.text
    assert platform.sql("SELECT count(*) FROM device_platform.users") == [(0,)]


def test_initial_setup_audit_failure_rolls_back_and_allows_retry(platform, monkeypatch):
    enable(platform)
    original = initial_setup.audit

    async def fail(*args, **kwargs):
        raise AppError(409, "audit_failed", "Test atomic rollback")

    monkeypatch.setattr(initial_setup, "audit", fail)
    assert platform.call("POST", "/auth/setup", expected=409, json=DETAILS)["error"]["code"] == "audit_failed"
    assert platform.sql("SELECT count(*) FROM device_platform.users") == [(0,)]
    assert platform.sql("SELECT count(*) FROM device_platform.local_credentials") == [(0,)]
    monkeypatch.setattr(initial_setup, "audit", original)
    platform.call("POST", "/auth/setup", expected=201, json=DETAILS)


def test_concurrent_setup_creates_only_one_administrator(platform, monkeypatch):
    enable(platform)
    barrier = Barrier(2, timeout=10)
    original = initial_setup.hash_password

    async def synchronized_hash(value):
        await anyio.to_thread.run_sync(barrier.wait)
        return await original(value)

    monkeypatch.setattr(initial_setup, "hash_password", synchronized_hash)

    def submit(number):
        return platform.client.post(
            "/api/v1/auth/setup", json={**DETAILS, "email": f"admin{number}@example.com"}
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(submit, [1, 2]))
    assert sorted(statuses) == [201, 409]
    assert platform.sql("SELECT count(*) FROM device_platform.users") == [(1,)]
    assert platform.sql("SELECT count(*) FROM device_platform.local_credentials") == [(1,)]
    assert platform.sql(
        "SELECT count(*) FROM device_platform.activity_events WHERE event_type='platform.initial_admin_created'"
    ) == [(1,)]


def test_setup_attempts_are_rate_limited(platform):
    enable(platform)
    for _ in range(10):
        platform.call("POST", "/auth/setup/verify", expected=403, json={"installation_key": "incorrect"})
    platform.call("POST", "/auth/setup", expected=429, json=DETAILS)
    assert platform.sql("SELECT count(*) FROM device_platform.users") == [(0,)]


def test_init_local_generates_private_independent_key_without_admin_password(tmp_path, capsys):
    path = tmp_path / ".env"
    init_local(path)
    values = dotenv_values(path)
    key = values["PMS_INITIAL_SETUP_KEY"]
    assert key and len(key) >= 32 and values["PMS_LOCAL_AUTH_ENABLED"] == "true"
    assert key not in capsys.readouterr().out
    assert key not in [
        values["PMS_TOKEN_PEPPER"],
        values["PMS_MEDIA_SIGNING_KEY"],
        values["PMS_LOCAL_TOKEN_SIGNING_KEY"],
    ]
    assert not any("PASSWORD" in name for name in values)


@pytest.mark.parametrize("key", ["short", "p" * 40, "x" * 513, " " * 40, "\u2603" * 40])
def test_setup_key_configuration_validation(key):
    with pytest.raises(ValidationError, match="initial_setup_key") as failure:
        Settings(_env_file=None, initial_setup_key=key, token_pepper="p" * 40, media_signing_key="m" * 40)
    assert "input_value" not in str(failure.value)
