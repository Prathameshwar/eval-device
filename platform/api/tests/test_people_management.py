"""User/member CRUD through the runtime role on an isolated PostgreSQL database."""

import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_auth_sessions import OLD, action_token

from pms_api.modules.schemas import InvitationCreate, LocalUserCreate, MembershipPatch, UserAdminPatch


@pytest.fixture(autouse=True)
def no_live_email(monkeypatch):
    async def undelivered(*_):
        return False

    monkeypatch.setattr("pms_api.modules.management.send_invitation", undelivered)


@pytest.mark.parametrize("value", ["null\x00text", "invalid\ud800"])
@pytest.mark.parametrize(
    "schema,body,field",
    [
        (LocalUserCreate, {"email": "user@example.com"}, "display_name"),
        (UserAdminPatch, {}, "display_name"),
        (MembershipPatch, {}, "status_reason"),
        (InvitationCreate, {"email": "user@example.com", "role": "org_user"}, "local_display_name"),
    ],
)
def test_people_reject_invalid_database_text(schema, body, field, value):
    with pytest.raises(ValueError):
        schema(**{**body, field: value})


def test_user_crud_setup_projection_versions_and_archive(platform):
    h = platform
    admin, owner = h.admin("people-owner")
    created = h.call(
        "POST",
        "/platform/users",
        admin,
        expected=201,
        json={"email": "person@example.com", "display_name": "Person"},
    )
    row = created["user"]
    assert row["setup_pending"] and "setup_token" not in json.dumps(created)
    path = "/platform/users/" + row["id"]
    assert h.call("GET", path, admin) == row
    assert h.call("GET", "/platform/users?platform_role=none&include_total=true", admin)["total"] == 1
    h.call(
        "POST",
        "/platform/users",
        admin,
        expected=409,
        json={"email": "PERSON@example.com", "display_name": "Duplicate"},
    )
    updated = h.call(
        "PATCH", path, admin, json={"expected_version": 1, "display_name": "Renamed", "phone": "123"}
    )
    assert updated["display_name"] == "Renamed" and updated["management_version"] == 2
    h.call("DELETE", path + "?expected_version=1", admin, expected=409)
    archived = h.call("DELETE", path + "?expected_version=2", admin)
    assert archived["archived_at"] and not archived["is_active"]
    h.call("POST", path + "/setup/resend", admin, expected=409)
    h.call("PATCH", path, admin, expected=409, json={"display_name": "Unavailable"})
    assert h.call("GET", "/platform/users?archived=true", admin)["items"] == [archived]
    h.call("POST", path + "/restore", admin, expected=409, json={"expected_version": 1})
    restored = h.call("POST", path + "/restore", admin, json={"expected_version": 3})
    assert restored["archived_at"] is None and not restored["is_active"]
    h.call("PATCH", path, admin, json={"expected_version": 4, "is_active": True})
    h.call("POST", path + "/setup/resend", admin)
    h.call(
        "POST", "/auth/password/setup", json={"token": action_token(h, row["id"], "setup"), "password": OLD}
    )
    assert not h.call("GET", path, admin)["setup_pending"]
    h.call("POST", path + "/setup/resend", admin, expected=409)
    h.call(
        "PATCH",
        "/platform/users/" + owner["id"],
        admin,
        expected=409,
        json={"display_name": "External overwrite"},
    )
    h.call("DELETE", "/platform/users/" + owner["id"], admin, expected=403)
    events = h.sql("SELECT event_type FROM device_platform.activity_events WHERE entity_id=%s", (row["id"],))
    assert {e[0] for e in events} >= {
        "platform.user.created",
        "platform.user.updated",
        "platform.user.archived",
        "platform.user.restored",
        "platform.user.setup_resent",
    }


def test_tenant_administrator_and_user_cannot_disable_or_archive_own_membership(platform):
    h = platform
    platform_token, _ = h.admin("self-access-platform")
    owner_token, owner = h.user("self-access-owner")
    org = h.organization(owner_token)
    base = f"/organizations/{org['id']}/members"
    own = next(row for row in h.call("GET", base, owner_token)["items"] if row["user_id"] == owner["id"])
    _, other_admin = h.user("self-access-other-admin")
    h.call(
        "POST",
        f"/platform/organizations/{org['id']}/administrators",
        platform_token,
        json={"user_id": other_admin["id"]},
    )
    for method, path, body in (
        (
            "PATCH",
            base + "/" + own["id"],
            {"expected_version": own["management_version"], "is_active": False},
        ),
        ("DELETE", base + "/" + own["id"] + f"?expected_version={own['management_version']}", None),
    ):
        result = h.call(method, path, owner_token, expected=403, **({"json": body} if body else {}))
        assert result["error"]["code"] == "self_membership_action"
    unchanged = h.call("GET", base + "/" + own["id"], owner_token)
    assert unchanged["is_active"] and unchanged["archived_at"] is None
    assert unchanged["management_version"] == own["management_version"]

    user_token, user = h.user("self-access-member")
    member = h.call(
        "POST",
        f"/platform/organizations/{org['id']}/members",
        platform_token,
        expected=201,
        json={"user_id": user["id"], "role": "org_user"},
    )
    for method, path, body in (
        (
            "PATCH",
            base + "/" + member["id"],
            {"expected_version": member["management_version"], "is_active": False},
        ),
        ("DELETE", base + "/" + member["id"] + f"?expected_version={member['management_version']}", None),
    ):
        h.call(method, path, user_token, expected=403, **({"json": body} if body else {}))
    assert h.call("GET", base + "/" + member["id"], owner_token)["is_active"]


def test_vm_local_manual_setup_and_tenant_invitation_links(platform):
    h = platform
    admin, _ = h.admin("manual-platform-admin")
    owner, _ = h.user("manual-tenant-owner")
    org = h.organization(owner)["id"]
    h.settings.vm_local_mode = True

    response = h.client.post(
        "/api/v1/platform/users",
        headers=h.headers(admin),
        json={
            "email": "manual-admin@example.com",
            "display_name": "Manual administrator",
            "platform_role": "platform_admin",
        },
    )
    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    created = response.json()
    assert created["setup_token"].startswith("act_")
    assert created["user"]["setup_pending"]
    assert "setup_token" not in json.dumps(h.call("GET", "/platform/users", admin))
    assert "setup_token" not in json.dumps(h.call("GET", "/platform/users/" + created["user"]["id"], admin))

    resent = h.client.post(
        "/api/v1/platform/users/" + created["user"]["id"] + "/setup/resend",
        headers=h.headers(admin),
    )
    assert resent.status_code == 200 and resent.headers["cache-control"] == "no-store"
    new_setup_token = resent.json()["setup_token"]
    assert new_setup_token != created["setup_token"]
    h.call(
        "POST", "/auth/password/setup", expected=422, json={"token": created["setup_token"], "password": OLD}
    )
    h.call("POST", "/auth/password/setup", json={"token": new_setup_token, "password": OLD})

    tenant_admin = h.call(
        "POST",
        "/platform/users",
        admin,
        expected=201,
        json={
            "email": "manual-tenant-admin@example.com",
            "display_name": "Manual tenant admin",
            "organization_id": org,
        },
    )
    assert tenant_admin["setup_token"].startswith("act_")
    assert tenant_admin["invitation_token"].startswith("inv_")
    assert tenant_admin["membership"]["role"] == "org_admin"
    regenerated = h.call("POST", "/platform/users/" + tenant_admin["user"]["id"] + "/setup/resend", admin)
    assert regenerated["setup_token"] != tenant_admin["setup_token"]

    invitation = h.client.post(
        f"/api/v1/organizations/{org}/invitations",
        headers=h.headers(owner),
        json={
            "email": "manual-member@example.com",
            "local_display_name": "Manual member",
            "auth_method": "local",
            "role": "org_user",
        },
    )
    assert invitation.status_code == 201 and invitation.headers["cache-control"] == "no-store"
    invited = invitation.json()
    assert invited["setup_token"].startswith("act_")
    assert invited["invitation_token"].startswith("inv_")
    h.call("POST", "/auth/password/setup", json={"token": invited["setup_token"], "password": OLD})
    member_token = h.call(
        "POST", "/auth/login", json={"email": "manual-member@example.com", "password": OLD}
    )["access_token"]
    accepted = h.call(
        "POST", "/invitations/accept", member_token, json={"token": invited["invitation_token"]}
    )
    assert accepted["invitation_status"] == "accepted"


def test_invitation_acceptance_full_member_crud_and_scope(platform):
    h = platform
    admin, _ = h.user("tenant-owner")
    org = h.organization(admin)["id"]
    base = f"/organizations/{org}"
    recipient, recipient_user = h.user("recipient")
    outsider, _ = h.admin("platform-outsider")
    other_org = h.organization(outsider)["id"]
    dept = h.call("POST", base + "/departments", admin, expected=201, json={"name": "Training"})
    invite = h.call(
        "POST",
        base + "/invitations",
        admin,
        expected=201,
        json={
            "email": recipient_user["email"],
            "auth_method": "oidc",
            "role": "org_user",
            "department_id": dept["id"],
        },
    )
    row = invite["membership"]
    path = base + "/members/" + row["id"]
    inv = base + "/invitations/" + row["id"]
    h.call("GET", path, outsider, expected=404)
    h.call("GET", path, recipient, expected=404)
    h.call("GET", f"/organizations/{other_org}/members/{row['id']}", outsider, expected=404)
    h.call("GET", "/platform/users", admin, expected=403)
    h.call(
        "POST",
        base + "/invitations",
        admin,
        expected=409,
        json={"email": recipient_user["email"], "role": "org_user"},
    )
    h.call("PATCH", path, admin, expected=409, json={"is_active": True})
    h.call("PATCH", path, admin, expected=422, json={"role": "org_admin"})
    resent = h.call("POST", inv + "/resend?expected_version=1", admin)
    assert resent["membership"]["management_version"] == 2
    h.call("POST", "/invitations/accept", recipient, expected=409, json={"token": invite["invitation_token"]})
    h.call("POST", inv + "/resend?expected_version=1", admin, expected=409)
    h.call("POST", "/invitations/accept", outsider, expected=403, json={"token": resent["invitation_token"]})
    accepted = h.call("POST", "/invitations/accept", recipient, json={"token": resent["invitation_token"]})
    assert accepted["management_version"] == 3
    detail = h.call("GET", path, admin)
    assert detail["user"]["email"] == recipient_user["email"] and detail["user"]["auth_method"] == "oidc"
    assert detail in h.call("GET", base + "/members", admin)["items"]
    assert "invitation_token_hash" not in json.dumps(detail)
    h.call("DELETE", inv + "?expected_version=2", admin, expected=409)
    updated = h.call(
        "PATCH", path, admin, json={"expected_version": 3, "role": "org_read_only", "department_id": None}
    )
    assert updated["role"] == "org_read_only" and updated["department_id"] is None
    h.call("DELETE", path + "?expected_version=3", admin, expected=409)
    archived = h.call("DELETE", path + "?expected_version=4", admin)
    assert archived["archived_at"]
    assert h.call("GET", base + "/members?archived=true", admin)["items"] == [archived]
    restored = h.call("POST", path + "/restore", admin, json={"expected_version": 5})
    assert not restored["is_active"] and not restored["archived_at"]
    h.call("PATCH", "/platform/users/" + recipient_user["id"], outsider, json={"is_active": False})
    h.call("PATCH", path, admin, expected=409, json={"expected_version": 6, "is_active": True})
    h.call("PATCH", "/platform/users/" + recipient_user["id"], outsider, json={"is_active": True})
    h.call("PATCH", path, admin, json={"expected_version": 6, "is_active": True})
    owner = next(m for m in h.call("GET", base + "/members", admin)["items"] if m["role"] == "org_admin")
    denied = h.call("DELETE", base + "/members/" + owner["id"], admin, expected=403)
    assert denied["error"]["code"] == "self_membership_action"


def test_expired_invitations_department_revalidation_revoke_and_pagination(platform):
    h = platform
    admin, _ = h.user("expiry-owner")
    org = h.organization(admin)["id"]
    base = f"/organizations/{org}"
    recipient, user = h.user("expired-recipient")
    dept = h.call("POST", base + "/departments", admin, expected=201, json={"name": "Inactive later"})
    invitation = h.call(
        "POST",
        base + "/invitations",
        admin,
        expected=201,
        json={"email": user["email"], "role": "org_user", "department_id": dept["id"]},
    )
    row = invitation["membership"]
    inv = base + "/invitations/" + row["id"]
    h.call("PATCH", base + "/departments/" + dept["id"], admin, json={"is_active": False})
    h.call(
        "POST", "/invitations/accept", recipient, expected=422, json={"token": invitation["invitation_token"]}
    )
    h.call("POST", inv + "/resend", admin, expected=422)
    h.call("PATCH", base + "/departments/" + dept["id"], admin, json={"is_active": True})
    h.sql(
        "UPDATE device_platform.organization_memberships SET invitation_expires_at=now()-interval '1 hour' WHERE id=%s",
        (row["id"],),
    )
    assert len(h.call("GET", base + "/members?invitation_status=expired", admin)["items"]) == 1
    assert not h.call("GET", base + "/members?invitation_status=pending", admin)["items"]
    resent = h.call("POST", inv + "/resend?expected_version=1", admin)
    h.call(
        "POST",
        base + "/invitations",
        admin,
        expected=201,
        json={"email": "another@example.com", "role": "org_user"},
    )
    first = h.call("GET", base + "/members?sort_by=joined_at&limit=1", admin)
    second = h.call("GET", base + "/members?sort_by=joined_at&limit=1&cursor=" + first["next_cursor"], admin)
    assert first["items"][0]["id"] != second["items"][0]["id"]
    revoked = h.call("DELETE", inv + "?expected_version=2", admin)
    assert revoked["invitation_status"] == "revoked"
    h.call("POST", "/invitations/accept", recipient, expected=409, json={"token": resent["invitation_token"]})
    h.call("POST", inv + "/resend", admin, expected=409)


def test_concurrent_duplicate_invitation_is_atomic(platform):
    h = platform
    admin, _ = h.user("concurrent-owner")
    org = h.organization(admin)["id"]
    path = f"/api/v1/organizations/{org}/invitations"

    def invite(_):
        return h.client.post(
            path,
            headers=h.headers(admin),
            json={
                "email": "same@example.com",
                "auth_method": "local",
                "local_display_name": "Same",
                "role": "org_user",
            },
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(invite, range(2))) == [201, 409]
    assert h.sql("SELECT count(*) FROM device_platform.users WHERE email='same@example.com'") == [(1,)]
    assert h.sql(
        "SELECT count(*) FROM device_platform.account_email_outbox WHERE recipient='same@example.com'"
    ) == [(1,)]
