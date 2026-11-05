from uuid import uuid4

import pytest


def test_platform_fleet_is_summary_only_and_tenant_management_requires_membership(platform):
    h = platform
    owner, _ = h.user("owner")
    org = h.organization(owner)["id"]
    device = h.device(owner, org, details={"notes": "Private notes"}, location="Private room")
    admin, _ = h.admin()
    fleet = h.call("GET", "/platform/devices?include_total=true", admin)
    assert fleet["total"] == 1
    summary = fleet["items"][0]
    assert summary["id"] == device["id"] and summary["summary_only"]
    assert not {"details", "latest_health", "location", "credential_hash"} & summary.keys()
    assert not {"profile_id", "profile_name"} & summary.keys()
    assert h.call("GET", "/platform/devices/" + device["id"], admin)["summary_only"]
    base = f"/organizations/{org}/devices"
    h.call("PATCH", base + "/" + device["id"], admin, expected=404, json={"name": "Blocked"})
    h.call("GET", base + "/" + device["id"] + "/configuration", admin, expected=404)
    h.call("GET", "/platform/devices", owner, expected=403)
    assert h.call("GET", base, owner)["items"][0]["details"]["notes"] == "Private notes"
    h.call("DELETE", "/platform/organizations/" + org, admin)
    assert h.call("GET", "/platform/devices", admin)["items"] == []
    h.call("GET", "/platform/devices/" + device["id"], admin, expected=404)


@pytest.mark.parametrize("device_type", ["laptop", "manikin"])
def test_device_registration_edit_enrollment_heartbeat_revoke_and_retire(platform, device_type):
    h = platform
    token, _ = h.user("owner")
    org = h.organization(token)["id"]
    row = h.device(token, org, device_type=device_type, details={"model": "Pi", "notes": "Original"})
    base = f"/organizations/{org}/devices/{row['id']}"
    assert row["enrollment_state"] == "pending" and row["credential_status"] == "not_issued"
    assert len(row["management_etag"]) == 64
    updated = h.call(
        "PATCH",
        base,
        token,
        json={
            "name": "Renamed",
            "details": {"notes": "Updated"},
            "preferred_language": "hi",
            "expected_etag": row["management_etag"],
        },
    )
    assert updated["details"] == {"model": "Pi", "notes": "Updated"}
    assert updated["device_type"] == device_type
    h.call(
        "PATCH", base, token, expected=409, json={"name": "Stale", "expected_etag": row["management_etag"]}
    )
    h.call("PATCH", base, token, expected=422, json={"details": None})
    h.call("PATCH", base, token, expected=422, json={"details": {"notes": "x" * 4001}})
    enrollment = h.call("POST", base + "/enrollment?expected_etag=" + updated["management_etag"], token)
    pending = h.call("GET", base, token)
    assert pending["credential_status"] == "not_issued" and pending["enrollment_state"] == "pending"
    assert pending["device_type"] == device_type
    credential = h.call("POST", "/device/enroll", json={"token": enrollment["enrollment_token"]})[
        "credential"
    ]
    h.call("POST", "/device/enroll", expected=409, json={"token": enrollment["enrollment_token"]})
    enrolled = h.call("GET", base, token)
    assert enrolled["credential_status"] == "active" and enrolled["enrollment_state"] == "enrolled"
    h.call("POST", "/device/heartbeat", credential, json={"boot_id": str(uuid4()), "sequence_number": 1})
    after_heartbeat = h.call("GET", base, token)
    assert after_heartbeat["management_etag"] == enrolled["management_etag"]
    assert after_heartbeat["connectivity"] == "online"
    assert h.call("GET", base + "/configuration", token)["effective_language"] == "hi"
    h.call("POST", base + "/revoke?expected_etag=" + row["management_etag"], token, expected=409)
    revoked = h.call("POST", base + "/revoke?expected_etag=" + enrolled["management_etag"], token)
    assert revoked["credential_status"] == "revoked"
    h.call("GET", "/device/config", credential, expected=401)
    retired = h.call("POST", base + "/retire?expected_etag=" + revoked["management_etag"], token)
    assert not retired["is_active"] and retired["enrollment_state"] == "retired"
    h.call("POST", base + "/enrollment", token, expected=409)
    h.call("PATCH", base, token, expected=409, json={"name": "Blocked"})
    assert h.sql(
        "SELECT count(*) FROM device_platform.activity_events WHERE entity_id=%s AND event_type='device.updated'",
        (row["id"],),
    ) == [(2,)]  # Fixture private-field setup plus the edit under test.


def test_never_seen_device_pagination_and_department_scope(platform):
    h = platform
    owner, _ = h.user("owner")
    org = h.organization(owner)["id"]
    dept = h.call("POST", f"/organizations/{org}/departments", owner, expected=201, json={"name": "One"})[
        "id"
    ]
    rows = [
        h.device(owner, org, name=f"Device {index}", department_id=dept, is_active=False)
        for index in range(3)
    ]
    hidden = h.device(owner, org, name="Outside", is_active=False)
    trainee, _ = h.user("trainee")
    invitation = h.call(
        "POST",
        f"/organizations/{org}/invitations",
        owner,
        expected=201,
        json={"email": "trainee@example.com", "role": "org_trainee", "department_id": dept},
    )
    h.call("POST", "/invitations/accept", trainee, json={"token": invitation["invitation_token"]})
    base = f"/organizations/{org}/devices"
    ids, cursor = [], None
    for _ in range(3):
        query = {"sort_by": "last_seen_at", "limit": 1, "include_total": "true"}
        if cursor:
            query["cursor"] = cursor
        page = h.call("GET", base, trainee, params=query)
        assert page["total"] == 3
        assert page["items"][0]["summary_only"]
        ids.append(page["items"][0]["id"])
        cursor = page["next_cursor"]
    assert len(set(ids)) == 3 and set(ids) == {row["id"] for row in rows}
    assert cursor is None
    h.call("GET", base + "/" + hidden["id"], trainee, expected=404)
    h.call("POST", base + "/" + rows[0]["id"] + "/enrollment", trainee, expected=403)
