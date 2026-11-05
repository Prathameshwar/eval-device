import base64
import copy
from pathlib import Path
from uuid import uuid4

import pytest

from pms_api.core.common import AppError, token_hash
from pms_api.core.config import Settings
from pms_api.main import create_app
from pms_api.modules.common import decode_cursor, encode_cursor
from pms_api.modules.schemas import ModelDefinitionCreate
from pms_api.security.local_auth import hash_password, normalize_email, verify_password


def test_platform_policy_defaults_must_fit_limits_for_new_tenants(platform):
    p = platform
    admin, _ = p.admin()
    settings = p.call("GET", "/platform/settings", admin)
    limits = copy.deepcopy(settings["policy_limits"])
    limits["audit_retention_days"] = 1
    response = p.call(
        "PATCH",
        "/platform/settings",
        admin,
        expected=422,
        json={"expected_version": settings["configuration_version"], "policy_limits": limits},
    )
    assert response["error"]["code"] == "policy_limit"
    assert (
        p.call("GET", "/platform/settings", admin)["configuration_version"]
        == settings["configuration_version"]
    )

    defaults = copy.deepcopy(settings["default_organization_policy"])
    defaults["audit_retention_days"] = 1
    updated = p.call(
        "PATCH",
        "/platform/settings",
        admin,
        json={
            "expected_version": settings["configuration_version"],
            "default_organization_policy": defaults,
            "policy_limits": limits,
        },
    )
    assert updated["default_organization_policy"]["audit_retention_days"] == 1
    assert updated["policy_limits"]["audit_retention_days"] == 1
    assert p.organization(admin)["policy_settings"]["audit_retention_days"] == 1


@pytest.mark.asyncio
async def test_local_passwords_are_argon2id_and_wrong_values_fail():
    encoded = await hash_password("correct horse battery staple")
    assert encoded.startswith("$argon2id$")
    assert await verify_password(encoded, "correct horse battery staple")
    assert not await verify_password(encoded, "incorrect horse battery staple")
    assert not await verify_password(None, "incorrect horse battery staple")


@pytest.mark.asyncio
async def test_local_password_policy_rejects_short_and_common_values():
    with pytest.raises(AppError):
        await hash_password("too-short")
    with pytest.raises(AppError):
        await hash_password("password1234")
    assert normalize_email("  USER@Example.COM ") == "user@example.com"


def test_directory_cursor_is_bound_and_tamper_evident():
    row_id = uuid4()
    token = encode_cursor("Acme", row_id, "name", "asc", "organizations|active", "s" * 40)
    assert decode_cursor(token, "name", "asc", "organizations|active", "s" * 40, "string") == (
        "Acme",
        row_id,
    )
    with pytest.raises(AppError):
        decode_cursor(token, "name", "asc", "organizations|inactive", "s" * 40, "string")
    # Change signed bytes, not unused base64 padding bits in the last character.
    raw = bytearray(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
    for position in (0, -1):
        changed = raw.copy()
        changed[position] ^= 1
        tampered = base64.urlsafe_b64encode(changed).decode().rstrip("=")
        with pytest.raises(AppError):
            decode_cursor(tampered, "name", "asc", "organizations|active", "s" * 40, "string")
    uuid_token = encode_cursor(row_id, row_id, "id", "desc", "users", "s" * 40)
    assert decode_cursor(uuid_token, "id", "desc", "users", "s" * 40, "uuid") == (
        row_id,
        row_id,
    )


def test_model_catalog_rejects_duplicate_capabilities():
    with pytest.raises(ValueError):
        ModelDefinitionCreate(
            provider="openai",
            model_key="gpt-test",
            display_name="Test",
            categories=["text", "text"],
            operations=["text.generate"],
        )
    with pytest.raises(ValueError):
        ModelDefinitionCreate(
            provider="openai",
            model_key="gpt-test",
            display_name="Test",
            categories=["text"],
            operations=["text.generate"],
            capabilities={"headers": {"Authorization": "unsafe"}},
        )


def test_management_migration_updates_archive_aware_admin_guards():
    source = (Path(__file__).resolve().parents[1] / "migrations/versions/0020_management_api.py").read_text(
        encoding="utf-8"
    )
    assert 'down_revision = "0019_patient_turn_recovery"' in source
    assert "m.archived_at IS NULL" in source
    assert "u.archived_at IS NULL" in source
    assert source.count("lc.setup_completed_at IS NOT NULL") >= 4
    assert source.count("management_archive_admin_lock") == 3
    assert "CREATE TABLE device_platform.local_credentials" in source
    assert "CREATE TABLE device_platform.model_definitions" in source


def test_local_auth_requires_a_separate_signing_key():
    common = {
        "_env_file": None,
        "token_pepper": "p" * 40,
        "media_signing_key": "m" * 40,
        "active_credential_key": "v1",
        "credential_keys": {"v1": base64.b64encode(b"k" * 32).decode()},
    }
    with pytest.raises(ValueError):
        Settings(local_auth_enabled=True, **common)
    assert Settings(local_auth_enabled=True, local_token_signing_key="l" * 40, **common).local_auth_enabled


def test_management_openapi_contains_auth_lifecycle_and_model_routes():
    settings = Settings(
        token_pepper="p" * 40,
        media_signing_key="m" * 40,
        active_credential_key="v1",
        credential_keys={"v1": base64.b64encode(b"k" * 32).decode()},
        environment="test",
    )
    paths = create_app(settings).openapi()["paths"]
    required = {
        "/api/v1/auth/login",
        "/api/v1/auth/password/change",
        "/api/v1/platform/users",
        "/api/v1/platform/organizations/{organization_id}/restore",
        "/api/v1/organizations/{organization_id}/devices",
        "/api/v1/providers",
        "/api/v1/platform/models",
        "/api/v1/platform/runtime-models",
        "/api/v1/platform/devices/{device_id}/models",
    }
    assert required <= paths.keys()


def test_local_account_setup_login_password_change_and_revocation(platform):
    admin_token, admin_user = platform.admin("local-account-admin")
    created = platform.call(
        "POST",
        "/platform/users",
        admin_token,
        expected=201,
        json={
            "email": "local.user@example.com",
            "display_name": "Local User",
            "platform_role": "platform_admin",
        },
    )
    user_id = created["user"]["id"]
    # Self-disable is denied independently of other administrator accounts.
    conflict = platform.call(
        "PATCH",
        f"/platform/users/{admin_user['id']}",
        admin_token,
        expected=403,
        json={"is_active": False},
    )
    assert conflict["error"]["code"] == "self_account_action"
    organization = platform.organization(admin_token, "Local setup guard")
    conflict = platform.call(
        "POST",
        f"/platform/organizations/{organization['id']}/administrators",
        admin_token,
        expected=409,
        json={"user_id": user_id},
    )
    assert conflict["error"]["code"] == "account_setup_required"
    setup_token = "act_" + "a" * 48
    setup_hash = token_hash(setup_token, platform.settings.token_pepper.get_secret_value())
    platform.sql(
        "UPDATE device_platform.account_action_tokens SET token_hash=%s WHERE user_id=%s AND purpose='setup' AND consumed_at IS NULL",
        (setup_hash, user_id),
    )
    platform.call(
        "POST",
        "/auth/password/setup",
        expected=200,
        json={"token": setup_token, "password": "correct horse battery staple"},
    )
    login = platform.call(
        "POST",
        "/auth/login",
        expected=200,
        json={"email": "local.user@example.com", "password": "correct horse battery staple"},
    )
    access = login["access_token"]
    assert platform.call("GET", "/me", access)["user"]["password_management"] is True
    platform.call(
        "POST",
        "/auth/password/change",
        access,
        json={
            "current_password": "correct horse battery staple",
            "new_password": "another correct horse battery staple",
        },
    )
    platform.call("GET", "/me", access, expected=401)
    platform.call(
        "POST",
        "/auth/login",
        expected=401,
        json={"email": "local.user@example.com", "password": "correct horse battery staple"},
    )
    replacement = platform.call(
        "POST",
        "/auth/login",
        json={"email": "local.user@example.com", "password": "another correct horse battery staple"},
    )
    response = platform.client.post(
        "/api/v1/auth/logout", headers=platform.headers(replacement["access_token"])
    )
    assert response.status_code == 204


def test_local_invitation_creates_parent_and_rolls_back_on_failure(platform, monkeypatch):
    from pms_api.modules import management

    p = platform
    token, _ = p.admin("local-invitation-admin")
    organization = p.organization(token)
    body = {
        "email": "invited.local@example.com",
        "role": "org_user",
        "auth_method": "local",
        "local_display_name": "Invited local user",
    }
    path = f"/organizations/{organization['id']}/invitations"
    response = p.call("POST", path, token, expected=201, json=body)
    assert response["membership"]["invitation_auth_method"] == "local"
    assert p.sql(
        "SELECT u.auth_method,c.password_hash FROM device_platform.users u "
        "JOIN device_platform.local_credentials c ON c.user_id=u.id WHERE u.email=%s",
        (body["email"],),
    ) == [("local", None)]
    original_audit = management.audit

    async def reject_invitation(session, actor, event, *args, **kwargs):
        if event == "membership.invited":
            raise AppError(409, "test_audit_failure", "Test atomic rollback")
        return await original_audit(session, actor, event, *args, **kwargs)

    monkeypatch.setattr(management, "audit", reject_invitation)
    body["email"] = "rolled.back@example.com"
    p.call("POST", path, token, expected=409, json=body)
    assert p.sql("SELECT id FROM device_platform.users WHERE email=%s", (body["email"],)) == []
    assert (
        p.sql("SELECT user_id FROM device_platform.local_credentials WHERE login_email=%s", (body["email"],))
        == []
    )
    assert (
        p.sql("SELECT id FROM device_platform.account_email_outbox WHERE recipient=%s", (body["email"],))
        == []
    )


@pytest.mark.asyncio
async def test_local_admin_bootstrap_persists_identity_before_credentials(platform, monkeypatch):
    from types import SimpleNamespace

    from pydantic import SecretStr
    from sqlalchemy.engine import make_url

    from pms_api import cli

    settings = platform.settings.model_copy(
        update={
            "smtp_host": "smtp.invalid",
            "smtp_sender": "accounts@example.com",
            "migration_database_url": SecretStr(
                make_url(platform.dsn)
                .set(drivername="postgresql+psycopg")
                .render_as_string(hide_password=False)
            ),
        }
    )
    monkeypatch.setattr(cli, "Settings", lambda: settings)
    args = SimpleNamespace(email="first.local@example.com", name="First admin", verified_operator=True)
    await cli.bootstrap_local(args)
    assert platform.sql(
        "SELECT u.platform_role,c.password_hash,c.setup_completed_at FROM device_platform.users u "
        "JOIN device_platform.local_credentials c ON c.user_id=u.id WHERE u.email=%s",
        (args.email,),
    ) == [("platform_admin", None, None)]
    assert platform.sql("SELECT count(*) FROM device_platform.account_action_tokens") == [(1,)]
    assert platform.sql("SELECT count(*) FROM device_platform.account_email_outbox") == [(1,)]
    assert platform.sql(
        "SELECT count(*) FROM device_platform.activity_events WHERE event_type='platform.local_admin_bootstrapped'"
    ) == [(1,)]
    with pytest.raises(AppError) as denied:
        await cli.bootstrap_local(args)
    assert denied.value.code == "bootstrap_completed"


def test_platform_dashboard_stats_and_reports(platform):
    admin_token, _ = platform.admin("stats-admin")

    # 1. Check Platform Dashboard Stats
    stats = platform.call("GET", "/platform/dashboard-stats", admin_token)
    assert "total_devices" in stats
    assert "live_devices" in stats
    assert "live_percentage" in stats
    assert "total_tenants" in stats
    assert "awaiting_enrollment" in stats
    assert stats["inactive_tenants"] == 0
    assert "expired_licenses" not in stats

    # 2. Check Devices By Tenant report
    report = platform.call("GET", "/platform/reports/devices-by-tenant", admin_token)
    assert "items" in report
    for item in report["items"]:
        assert "label" in item
        assert "value" in item


def test_tenant_dashboard_stats(platform):
    admin_token, _ = platform.admin("stats-org-admin")
    org = platform.organization(admin_token, "Stats Org")
    org_id = org["id"]

    # Check Tenant Dashboard Stats
    stats = platform.call("GET", f"/organizations/{org_id}/dashboard-stats", admin_token)
    assert "devices" in stats
    assert "total" in stats["devices"]
    assert "live" in stats["devices"]
    assert "offline" in stats["devices"]
    assert "members" in stats
    assert "active" in stats["members"]
    assert "pending" in stats["members"]
    assert "health_shares" in stats
    assert stats["subscription"]["plan"]["code"] == "standard"
    assert "license_expires_in" not in stats


def test_dashboard_lifecycle_and_platform_tenant_boundary(platform):
    h = platform
    admin, _ = h.admin()
    org = h.organization(admin)["id"]
    device = h.device(admin, org)["id"]
    h.enroll(admin, org, device)
    assert h.call("GET", "/platform/dashboard-stats", admin)["live_devices"] == 1
    h.call("PATCH", f"/organizations/{org}/devices/{device}", admin, json={"is_active": False})
    assert h.call("GET", "/platform/dashboard-stats", admin)["live_devices"] == 0
    health = h.call("GET", f"/organizations/{org}/dashboard-stats", admin)
    assert sum(row["share"] for row in health["health_shares"]) == 1
    outsider, _ = h.admin("outside")
    h.call("GET", f"/organizations/{org}/dashboard-stats", outsider, expected=404)
    reader, _ = h.user("reader")
    invitation = h.call(
        "POST",
        f"/organizations/{org}/invitations",
        admin,
        expected=201,
        json={"email": "reader@example.com", "role": "org_read_only"},
    )
    h.call("POST", "/invitations/accept", reader, json={"token": invitation["invitation_token"]})
    h.call("GET", "/platform/dashboard-stats", reader, expected=403)
    h.call("GET", f"/organizations/{org}/dashboard-stats", reader, expected=403)
    h.call("POST", f"/organizations/{org}/devices/{device}/retire", admin)
    assert h.call("GET", "/platform/dashboard-stats", admin)["total_devices"] == 0
    h.call("DELETE", f"/platform/organizations/{org}", admin)
    assert h.call("GET", "/platform/dashboard-stats", admin)["total_tenants"] == 0
    assert not h.call("GET", "/platform/reports/devices-by-tenant", admin)["items"]


def test_tenant_console_lifecycle_versions_and_admin_visibility(platform):
    h = platform
    admin, user = h.admin()
    plan = h.call("GET", "/subscription-plans", admin)["items"][0]["id"]
    row = h.call(
        "POST",
        "/platform/organizations",
        admin,
        expected=201,
        json={"name": "Console tenant", "subscription_plan_id": plan},
    )
    base = "/platform/organizations/" + row["id"]
    denied = h.call(
        "PATCH",
        base,
        admin,
        expected=409,
        json={"is_active": True, "expected_version": row["management_version"]},
    )
    assert denied["error"]["code"] == "organization_admin_required"
    assert h.call("GET", base + "/administrators", admin)["items"] == []
    h.call("POST", base + "/administrators", admin, json={"user_id": user["id"]})
    assert h.call("GET", base + "/administrators", admin)["items"][0]["id"] == user["id"]
    row = h.call(
        "PATCH", base, admin, json={"is_active": True, "expected_version": row["management_version"]}
    )
    h.call("DELETE", base + "?expected_version=1", admin, expected=409)
    h.call(
        "PUT",
        base + "/subscription",
        admin,
        expected=409,
        json={"subscription_plan_id": plan, "expected_version": 1},
    )
    assert h.call("GET", base, admin)["archived_at"] is None
    row = h.call("DELETE", base + f"?expected_version={row['management_version']}", admin)
    h.call("PUT", base + "/subscription", admin, expected=409, json={"subscription_plan_id": plan})
    h.call("PATCH", base, admin, expected=409, json={"name": "Blocked"})
    row = h.call("POST", base + "/restore", admin, json={"expected_version": row["management_version"]})
    assert not row["is_active"] and row["archived_at"] is None
    reader, _ = h.user("outside-reader")
    h.call("GET", base + "/administrators", reader, expected=403)
    h.call("GET", base, reader, expected=403)
