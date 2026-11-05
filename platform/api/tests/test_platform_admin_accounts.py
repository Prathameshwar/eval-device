"""Administrator provisioning and self-account protection on isolated PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from test_auth_sessions import OLD, action_token

from pms_api.core.common import AppError
from pms_api.modules import management
from pms_api.modules.schemas import LocalUserCreate
from pms_api.security import access


def new_admin(organization_id, email="new.tenant.admin@example.com"):
    return {"email": email, "display_name": "Tenant administrator", "organization_id": organization_id}


def complete_setup(p, user_id, email):
    p.call("POST", "/auth/password/setup", json={"token": action_token(p, user_id, "setup"), "password": OLD})
    return p.call("POST", "/auth/login", json={"email": email, "password": OLD})["access_token"]


def test_admin_scope_rejects_combined_platform_and_tenant_roles():
    with pytest.raises(ValueError):
        LocalUserCreate(**new_admin(uuid4()), platform_role="platform_admin")


def test_tenant_admin_provisioning_setup_acceptance_and_tenant_isolation(platform):
    p = platform
    admin, _ = p.admin()
    org = p.organization(admin)
    other = p.organization(admin, "Other tenant")
    created = p.call("POST", "/platform/users", admin, expected=201, json=new_admin(org["id"]))
    user, membership = created["user"], created["membership"]
    assert user["tenant_admin"] and user["platform_role"] is None and user["setup_pending"]
    assert membership["user_id"] == user["id"] and membership["role"] == "org_admin"
    assert membership["invitation_status"] == "pending" and not membership["is_active"]
    assert membership["department_id"] is None
    assert created["email_delivered"] is False and created["invitation_token"]
    assert "invitation_token_hash" not in membership
    assert p.call("GET", "/platform/users?platform_role=tenant_admin&q=new.tenant.admin", admin)["items"] == [
        user
    ]
    assert p.call("GET", "/platform/users/" + user["id"], admin)["tenant_admin"]
    token = complete_setup(p, user["id"], user["email"])
    assert p.call("GET", "/auth/context", token)["contexts"] == []
    accepted = p.call("POST", "/invitations/accept", token, json={"token": created["invitation_token"]})
    assert accepted["is_active"] and accepted["invitation_status"] == "accepted"
    contexts = p.call("GET", "/auth/context", token)["contexts"]
    assert [(row["id"], row["role"]) for row in contexts] == [(org["id"], "org_admin")]
    p.call("GET", "/platform/users", token, expected=403)
    p.call("GET", f"/organizations/{other['id']}/members", token, expected=404)
    p.call("POST", "/invitations/accept", token, expected=409, json={"token": created["invitation_token"]})


def test_first_administrator_can_accept_for_inactive_tenant_without_activating_it(platform):
    p = platform
    admin, _ = p.admin()
    plan = p.call("GET", "/subscription-plans", admin)["items"][0]
    org = p.call(
        "POST",
        "/platform/organizations",
        admin,
        expected=201,
        json={"name": "New inactive tenant", "subscription_plan_id": plan["id"]},
    )
    assert not org["is_active"]
    created = p.call("POST", "/platform/users", admin, expected=201, json=new_admin(org["id"]))
    token = complete_setup(p, created["user"]["id"], created["user"]["email"])
    assert (
        p.call(
            "PATCH", "/platform/organizations/" + org["id"], admin, expected=409, json={"is_active": True}
        )["error"]["code"]
        == "organization_admin_required"
    )
    p.call("POST", "/invitations/accept", token, json={"token": created["invitation_token"]})
    assert not p.call("GET", "/platform/organizations/" + org["id"], admin)["is_active"]
    p.call("GET", f"/organizations/{org['id']}/members", token, expected=409)
    p.call("PATCH", "/platform/organizations/" + org["id"], admin, json={"is_active": True})
    p.call("GET", f"/organizations/{org['id']}/members", token)


def test_inactive_tenant_still_rejects_ordinary_member_acceptance(platform):
    p = platform
    admin, _ = p.admin()
    org = p.organization(admin)
    email = "inactive.member@example.com"
    user = p.call(
        "POST", "/platform/users", admin, expected=201, json={"email": email, "display_name": "Member"}
    )["user"]
    token = complete_setup(p, user["id"], email)
    invitation = p.call(
        "POST",
        f"/organizations/{org['id']}/invitations",
        admin,
        expected=201,
        json={"email": email, "auth_method": "local", "role": "org_user"},
    )
    p.call("PATCH", "/platform/organizations/" + org["id"], admin, json={"is_active": False})
    result = p.call(
        "POST", "/invitations/accept", token, expected=409, json={"token": invitation["invitation_token"]}
    )
    assert result["error"]["code"] == "organization_inactive"
    assert p.call("GET", "/auth/context", token)["contexts"] == []


def test_provisioning_rejects_missing_archived_tenants_and_duplicate_accounts(platform):
    p = platform
    admin, _ = p.admin()
    org = p.organization(admin)
    p.call("POST", "/platform/users", admin, expected=201, json=new_admin(org["id"]))
    p.call("POST", "/platform/users", admin, expected=409, json=new_admin(org["id"]))
    p.call(
        "POST", "/platform/users", admin, expected=404, json=new_admin(str(uuid4()), "missing@example.com")
    )
    p.call("DELETE", "/platform/organizations/" + org["id"], admin)
    result = p.call(
        "POST", "/platform/users", admin, expected=409, json=new_admin(org["id"], "archived@example.com")
    )
    assert result["error"]["code"] == "organization_archived"
    assert p.sql(
        "SELECT count(*) FROM device_platform.users WHERE email IN ('missing@example.com','archived@example.com')"
    ) == [(0,)]


def test_provisioning_requires_specific_administrator_permission(platform, monkeypatch):
    p = platform
    admin, _ = p.admin()
    ordinary, _ = p.user("ordinary")
    org = p.organization(admin)
    p.call("POST", "/platform/users", ordinary, expected=403, json=new_admin(org["id"]))
    grants = access.GRANTS["platform_admin"]
    monkeypatch.setitem(
        access.GRANTS, "platform_admin", [g for g in grants if g != "platform.organization_admins.manage"]
    )
    p.call("POST", "/platform/users", admin, expected=403, json=new_admin(org["id"]))
    assert p.sql("SELECT count(*) FROM device_platform.users WHERE email='new.tenant.admin@example.com'") == [
        (0,)
    ]


def test_failed_provisioning_rolls_back_user_credential_invitation_and_outbox(platform, monkeypatch):
    p = platform
    admin, _ = p.admin()
    org = p.organization(admin)
    audit = management.audit

    async def refuse(session, actor, action, *args, **kwargs):
        if action == "platform.user.created":
            raise AppError(409, "test_audit_failure", "Forced audit failure")
        return await audit(session, actor, action, *args, **kwargs)

    monkeypatch.setattr(management, "audit", refuse)
    p.call("POST", "/platform/users", admin, expected=409, json=new_admin(org["id"]))
    for table, field in [
        ("users", "email"),
        ("local_credentials", "login_email"),
        ("organization_memberships", "invited_email"),
        ("account_email_outbox", "recipient"),
    ]:
        assert p.sql(
            f"SELECT count(*) FROM device_platform.{table} WHERE {field}=%s",
            ("new.tenant.admin@example.com",),
        ) == [(0,)]


def test_concurrent_admin_creation_cannot_exceed_last_subscription_seat(platform):
    p = platform
    admin, _ = p.admin()
    org = p.organization(admin)
    p.sql(
        "UPDATE device_platform.subscription_plans SET max_users=2 WHERE id=%s",
        (org["subscription_plan_id"],),
    )

    def create(index):
        return p.client.post(
            "/api/v1/platform/users",
            headers=p.headers(admin),
            json=new_admin(org["id"], f"seat{index}@example.com"),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(create, range(2)))
    assert sorted(response.status_code for response in responses) == [201, 409]
    assert (
        next(response for response in responses if response.status_code == 409).json()["error"]["code"]
        == "subscription_user_limit"
    )
    assert p.sql(
        "SELECT count(*) FROM device_platform.users WHERE email LIKE %s", ("seat%@example.com",)
    ) == [(1,)]
    assert p.sql(
        "SELECT count(*) FROM device_platform.account_email_outbox WHERE recipient LIKE %s",
        ("seat%@example.com",),
    ) == [(1,)]


def test_platform_admin_cannot_disable_or_archive_self_even_with_another_admin(platform):
    p = platform
    admin, owner = p.admin("owner")
    other, _ = p.admin("other")
    path = "/platform/users/" + owner["id"]
    before = p.call("GET", path, admin)
    for method, body in [("PATCH", {"is_active": False}), ("DELETE", None)]:
        result = p.call(method, path, admin, expected=403, **({"json": body} if body else {}))
        assert result["error"]["code"] == "self_account_action"
    assert p.call("GET", path, admin) == before
    p.call("PATCH", path, admin, json={"is_active": True, "status_reason": "Profile reviewed"})
    p.call("PATCH", path, other, json={"is_active": False})
    assert not p.call("GET", path, other)["is_active"]
    p.call("DELETE", path, other)
    assert p.call("GET", path, other)["archived_at"]
