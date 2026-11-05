"""Platform association controls enforce tenant boundaries and existing DB invariants."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from test_auth_sessions import OLD, action_token

from pms_api.core.common import AppError
from pms_api.modules import tenant_members
from pms_api.security import access


def setup(p):
    admin, _ = p.admin()
    owner, _ = p.user("tenant-owner")
    org = p.organization(owner)
    other = p.organization(owner, "Other tenant")
    return admin, owner, org, other


def base(org):
    return "/platform/organizations/" + org["id"]


@pytest.mark.parametrize("role", ["org_admin", "org_user", "org_read_only", "org_trainee"])
def test_assignment_roles_scoping_and_no_implicit_content_access(platform, role):
    p = platform
    admin, owner, org, other = setup(p)
    user_token, user = p.user("candidate")
    path = base(org)
    candidates = p.call("GET", path + "/member-candidates?q=candidate", admin)
    assert [row["id"] for row in candidates["items"]] == [user["id"]]
    row = p.call("POST", path + "/members", admin, expected=201, json={"user_id": user["id"], "role": role})
    assert row["role"] == role and row["department_id"] is None
    assert row["is_active"] and row["invitation_status"] == "accepted"
    p.call("POST", path + "/members", admin, expected=409, json={"user_id": user["id"], "role": role})
    assert p.call("GET", path + "/member-candidates?q=candidate", admin)["items"] == []
    assert p.call("GET", path + "/members?q=candidate", admin)["items"][0]["id"] == row["id"]
    assert p.call("GET", base(other) + "/members?q=candidate", admin)["items"] == []
    p.call("GET", path + "/members", owner, expected=403)
    p.call("GET", f"/organizations/{org['id']}/members", admin, expected=404)
    for method, suffix, body in [
        ("PATCH", "", {"expected_version": row["management_version"], "is_active": False}),
        ("DELETE", "?expected_version=1", None),
        ("POST", "/restore", {"expected_version": 1}),
    ]:
        p.call(
            method,
            base(other) + "/members/" + row["id"] + suffix,
            admin,
            expected=404,
            **({"json": body} if body else {}),
        )
    assert any(c["id"] == org["id"] for c in p.call("GET", "/auth/context", user_token)["contexts"])


def test_platform_administrator_promotion_advances_membership_version(platform):
    p = platform
    admin, _, org, _ = setup(p)
    _, user = p.user("promote")
    base_path = base(org)
    member = p.call(
        "POST",
        base_path + "/members",
        admin,
        expected=201,
        json={"user_id": user["id"], "role": "org_user"},
    )
    promoted = p.call(
        "POST",
        base_path + "/administrators",
        admin,
        json={"user_id": user["id"]},
    )
    assert promoted["id"] == member["id"]
    assert promoted["role"] == "org_admin"
    assert promoted["management_version"] == member["management_version"] + 1
    stale = p.call(
        "PATCH",
        base_path + "/members/" + member["id"],
        admin,
        expected=409,
        json={"expected_version": member["management_version"], "role": "org_user"},
    )
    assert stale["error"]["code"] == "version_conflict"
    assert p.call("POST", base_path + "/administrators", admin, json={"user_id": user["id"]}) == promoted


def test_platform_administrator_assignment_rejects_pending_email_and_unverified_identity(platform):
    p = platform
    admin, owner, org, _ = setup(p)
    _, user = p.user("invited-candidate")
    path = base(org) + "/administrators"
    p.call(
        "POST",
        f"/organizations/{org['id']}/invitations",
        owner,
        expected=201,
        json={"email": user["email"], "auth_method": "oidc", "role": "org_user"},
    )
    result = p.call("POST", path, admin, expected=409, json={"user_id": user["id"]})
    assert result["error"]["code"] == "membership_exists"
    assert p.sql(
        "SELECT count(*) FROM device_platform.organization_memberships "
        "WHERE organization_id=%s AND user_id=%s",
        (org["id"], user["id"]),
    ) == [(0,)]
    _, unverified = p.user("unverified-candidate")
    p.sql("UPDATE device_platform.users SET email_verified=false WHERE id=%s", (unverified["id"],))
    result = p.call("POST", path, admin, expected=409, json={"user_id": unverified["id"]})
    assert result["error"]["code"] == "administrator_unavailable"


def test_versioned_role_lifecycle_preserves_account_and_other_tenant(platform):
    p = platform
    admin, _, org, other = setup(p)
    token, user = p.user("multi-tenant")
    row = p.call(
        "POST", base(org) + "/members", admin, expected=201, json={"user_id": user["id"], "role": "org_user"}
    )
    p.call(
        "POST",
        base(other) + "/members",
        admin,
        expected=201,
        json={"user_id": user["id"], "role": "org_trainee"},
    )
    path = base(org) + "/members/" + row["id"]
    p.call("PATCH", path, admin, expected=422, json={"role": "org_admin"})
    changed = p.call(
        "PATCH", path, admin, json={"expected_version": row["management_version"], "role": "org_read_only"}
    )
    p.call("DELETE", path + "?expected_version=" + str(row["management_version"]), admin, expected=409)
    off = p.call(
        "PATCH", path, admin, json={"expected_version": changed["management_version"], "is_active": False}
    )
    assert not off["is_active"]
    removed = p.call("DELETE", path + "?expected_version=" + str(off["management_version"]), admin)
    assert removed["archived_at"]
    assert p.call("GET", "/platform/users/" + user["id"], admin)["is_active"]
    assert [c["id"] for c in p.call("GET", "/auth/context", token)["contexts"]] == [other["id"]]
    restored = p.call(
        "POST", path + "/restore", admin, json={"expected_version": removed["management_version"]}
    )
    assert not restored["archived_at"] and not restored["is_active"]
    enabled = p.call(
        "PATCH", path, admin, json={"expected_version": restored["management_version"], "is_active": True}
    )
    assert enabled["is_active"]
    assert (
        p.sql("SELECT count(*) FROM device_platform.activity_events WHERE entity_id=%s", (row["id"],))[0][0]
        >= 5
    )


def test_last_admin_and_specific_administrator_permission(platform, monkeypatch):
    p = platform
    admin, _, org, _ = setup(p)
    row = p.call("GET", base(org) + "/members?role=org_admin", admin)["items"][0]
    path = base(org) + "/members/" + row["id"]
    for method, body, suffix in [
        ("PATCH", {"is_active": False}, ""),
        ("PATCH", {"role": "org_user"}, ""),
        ("DELETE", None, "?expected_version=" + str(row["management_version"])),
    ]:
        p.call(
            method,
            path + suffix,
            admin,
            expected=409,
            **({"json": {"expected_version": row["management_version"], **body}} if body else {}),
        )
    monkeypatch.setitem(
        access.GRANTS,
        "platform_admin",
        access.GRANTS["platform_admin"] - {"platform.organization_admins.manage"},
    )
    p.call(
        "PATCH",
        path,
        admin,
        expected=403,
        json={"expected_version": row["management_version"], "role": "org_user"},
    )
    _, user = p.user("extra-admin")
    p.call(
        "POST", base(org) + "/members", admin, expected=403, json={"user_id": user["id"], "role": "org_admin"}
    )
    p.call(
        "POST", base(org) + "/members", admin, expected=201, json={"user_id": user["id"], "role": "org_user"}
    )


def test_setup_pending_invitation_and_archived_lifecycle_are_not_bypassed(platform):
    p = platform
    admin, owner, org, _ = setup(p)
    user = p.call(
        "POST",
        "/platform/users",
        admin,
        expected=201,
        json={"email": "pending@example.com", "display_name": "Pending setup"},
    )["user"]
    assert p.call("GET", base(org) + "/member-candidates?q=pending", admin)["items"] == []
    p.call(
        "POST", base(org) + "/members", admin, expected=409, json={"user_id": user["id"], "role": "org_admin"}
    )
    _, user = p.user("invited")
    p.call(
        "POST",
        f"/organizations/{org['id']}/invitations",
        owner,
        expected=201,
        json={"email": user["email"], "auth_method": "oidc", "role": "org_user"},
    )
    assert p.call("GET", base(org) + "/member-candidates?q=invited", admin)["items"] == []
    p.call(
        "POST", base(org) + "/members", admin, expected=409, json={"user_id": user["id"], "role": "org_user"}
    )
    member = p.call("GET", base(org) + "/members?state=pending", admin)["items"][0]
    p.call(
        "PATCH",
        base(org) + "/members/" + member["id"],
        admin,
        expected=409,
        json={"expected_version": member["management_version"], "is_active": True},
    )
    p.call("DELETE", base(org), admin)
    p.call(
        "POST", base(org) + "/members", admin, expected=409, json={"user_id": user["id"], "role": "org_user"}
    )
    assert p.call("GET", base(org) + "/members", admin)["items"]


def test_cursor_is_bound_to_tenant_and_filters(platform):
    p = platform
    admin, _, org, other = setup(p)
    for name in ["One", "Two"]:
        _, user = p.user(name)
        p.call(
            "POST",
            base(org) + "/members",
            admin,
            expected=201,
            json={"user_id": user["id"], "role": "org_user"},
        )
    page = p.call("GET", base(org) + "/members?limit=1", admin)
    assert page["has_more"] and page["total"] == 3
    next_page = p.call("GET", base(org) + "/members?limit=1&cursor=" + page["next_cursor"], admin)
    assert next_page["items"][0]["id"] != page["items"][0]["id"]
    p.call("GET", base(other) + "/members?cursor=" + page["next_cursor"], admin, expected=422)
    p.call("GET", base(org) + "/members?state=archived&cursor=" + page["next_cursor"], admin, expected=422)


def test_restoring_a_removed_account_bound_invitation_requires_setup_and_stays_disabled(platform):
    p = platform
    admin, _, org, _ = setup(p)
    created = p.call(
        "POST",
        "/platform/users",
        admin,
        expected=201,
        json={
            "email": "restore.admin@example.com",
            "display_name": "Restore admin",
            "organization_id": org["id"],
        },
    )
    row = created["membership"]
    path = base(org) + "/members/" + row["id"]
    removed = p.call("DELETE", path + "?expected_version=" + str(row["management_version"]), admin)
    p.call(
        "POST",
        path + "/restore",
        admin,
        expected=409,
        json={"expected_version": removed["management_version"]},
    )
    p.call(
        "POST",
        "/auth/password/setup",
        json={"token": action_token(p, created["user"]["id"], "setup"), "password": OLD},
    )
    restored = p.call(
        "POST", path + "/restore", admin, json={"expected_version": removed["management_version"]}
    )
    assert (
        restored["invitation_status"] == "accepted"
        and not restored["is_active"]
        and not restored["archived_at"]
    )
    assert p.sql(
        "SELECT invitation_token_hash FROM device_platform.organization_memberships WHERE id=%s", (row["id"],)
    ) == [(None,)]


def test_assignment_quota_race_and_atomic_audit_rollback(platform, monkeypatch):
    p = platform
    admin, _, org, _ = setup(p)
    p.sql(
        "UPDATE device_platform.subscription_plans SET max_users=2 WHERE id=%s",
        (org["subscription_plan_id"],),
    )
    users = [p.user("seat-" + str(n))[1] for n in range(2)]

    def assign(user):
        return p.client.post(
            "/api/v1" + base(org) + "/members",
            headers=p.headers(admin),
            json={"user_id": user["id"], "role": "org_user"},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(assign, users))
    assert sorted(response.status_code for response in responses) == [201, 409]
    assert p.call("GET", base(org) + "/members", admin)["total"] == 2
    p.sql(
        "UPDATE device_platform.subscription_plans SET max_users=10 WHERE id=%s",
        (org["subscription_plan_id"],),
    )
    _, new_user = p.user("rollback")

    async def reject(*args, **kwargs):
        raise AppError(409, "forced_audit_failure", "Rollback test")

    monkeypatch.setattr(tenant_members, "audit", reject)
    p.call(
        "POST",
        base(org) + "/members",
        admin,
        expected=409,
        json={"user_id": new_user["id"], "role": "org_user"},
    )
    assert p.sql(
        "SELECT count(*) FROM device_platform.organization_memberships WHERE organization_id=%s AND user_id=%s",
        (org["id"], new_user["id"]),
    ) == [(0,)]


def test_device_candidate_exclusion_is_server_scoped_and_cursor_bound(platform):
    p = platform
    admin, owner, org, other = setup(p)
    p.device(owner, org["id"], name="Own")
    expected = [
        p.device(owner, other["id"], name=name, is_active=False)["id"] for name in ["Other A", "Other B"]
    ]
    query = (
        "/platform/devices?enrollment_state=current&sort_by=name&limit=1&exclude_organization_id=" + org["id"]
    )
    page = p.call("GET", query, admin)
    assert page["items"][0]["id"] in expected and page["has_more"]
    assert page["items"][0]["summary_only"]
    p.call(
        "GET",
        query.replace(org["id"], other["id"]) + "&cursor=" + page["next_cursor"],
        admin,
        expected=422,
    )
    p.call("GET", query, owner, expected=403)
    assert p.call("GET", query + "&organization_id=" + org["id"], admin)["items"] == []
