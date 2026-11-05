"""Tenant association and lifecycle through isolated runtime-role PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from pms_api.modules.device_management import DeviceTransfer, FleetDeviceCreate
from pms_api.modules.schemas import DeviceCreate, DevicePatch


@pytest.mark.parametrize(
    "schema,body",
    [
        (DeviceCreate, {"name": "bad\\x00", "device_unique_id": str(uuid4()), "device_type": "laptop"}),
        (DevicePatch, {"contact_name": "bad\\ud800"}),
        (
            FleetDeviceCreate,
            {
                "organization_id": str(uuid4()),
                "name": "bad\\x00",
                "device_unique_id": str(uuid4()),
                "device_type": "laptop",
            },
        ),
        (DeviceTransfer, {"organization_id": str(uuid4()), "name": "valid"}),
    ],
)
def test_device_input_validation(schema, body):
    body = dict(body)
    if schema is DevicePatch:
        body["contact_name"] = "bad" + chr(0xD800)
    elif schema in (DeviceCreate, FleetDeviceCreate):
        body["name"] = "bad" + chr(0)
    with pytest.raises(ValueError):
        schema(**body)


def test_platform_registration_lifecycle_and_no_tenant_data_access(platform):
    h = platform
    owner, _ = h.user("device-owner")
    org = h.organization(owner)["id"]
    admin, _ = h.admin()
    h.call(
        "POST",
        f"/organizations/{org}/devices",
        owner,
        expected=403,
        json={"name": "Tenant cannot create", "device_unique_id": str(uuid4()), "device_type": "manikin"},
    )
    row = h.call(
        "POST",
        "/platform/devices",
        admin,
        expected=201,
        json={
            "organization_id": org,
            "name": "Assigned",
            "device_unique_id": str(uuid4()),
            "device_type": "laptop",
        },
    )
    assert row["organization_id"] == org and row["summary_only"] and len(row["management_etag"]) == 64
    manikin_org = h.organization(owner, "Manikin tenant")["id"]
    manikin = h.call(
        "POST",
        "/platform/devices",
        admin,
        expected=201,
        json={
            "organization_id": manikin_org,
            "name": "Physical manikin",
            "device_unique_id": str(uuid4()),
            "device_type": "manikin",
        },
    )
    assert manikin["device_type"] == "manikin"
    path = "/platform/devices/" + row["id"]
    h.call(
        "POST",
        "/platform/devices",
        owner,
        expected=403,
        json={
            "organization_id": org,
            "name": "Blocked",
            "device_unique_id": str(uuid4()),
            "device_type": "laptop",
        },
    )
    h.call("PATCH", path, admin, expected=422, json={"name": "Missing version"})
    h.call(
        "PATCH",
        path,
        admin,
        expected=422,
        json={"expected_etag": row["management_etag"], "profile_id": str(uuid4())},
    )
    credential = h.enroll(owner, org, row["id"])
    row = h.call("GET", path, admin)
    off = h.call("PATCH", path, admin, json={"expected_etag": row["management_etag"], "is_active": False})
    assert not off["is_active"]
    assert h.call("GET", "/device/config", credential)["is_active"] is False
    h.call("POST", "/device/heartbeat", credential, json={"boot_id": str(uuid4()), "sequence_number": 1})
    h.call(
        "PATCH", path, admin, expected=409, json={"expected_etag": row["management_etag"], "is_active": True}
    )
    on = h.call("PATCH", path, admin, json={"expected_etag": off["management_etag"], "is_active": True})
    # Global administration never produces a device credential or tenant configuration.
    private = f"/organizations/{org}/devices/{row['id']}"
    h.call("GET", private + "/configuration", admin, expected=404)
    h.call("POST", private + "/enrollment", admin, expected=404)
    h.call("POST", path + "/enrollment", admin, expected=404)
    removed = h.call("DELETE", path + "?expected_etag=" + on["management_etag"], admin)
    assert removed["enrollment_state"] == "retired" and not removed["is_active"]
    h.call("GET", "/device/config", credential, expected=401)
    assert {
        item["id"] for item in h.call("GET", "/platform/devices?enrollment_state=current", admin)["items"]
    } == {manikin["id"]}
    assert h.call("GET", "/platform/devices?enrollment_state=retired", admin)["items"][0]["id"] == row["id"]
    h.call(
        "PATCH",
        path,
        admin,
        expected=409,
        json={"expected_etag": removed["management_etag"], "is_active": True},
    )


def test_platform_assigns_direct_models_without_tenant_private_access(platform):
    h = platform
    owner, _ = h.user("model-owner")
    org = h.organization(owner, "Model tenant")["id"]
    admin, _ = h.admin("fleet-model-admin")
    device = h.device(owner, org)
    path = f"/platform/devices/{device['id']}/models"
    models = h.call("GET", path, admin)["models"]
    assert {row["kind"] for row in models} == {"llm", "asr", "tts"}
    body = {
        "mode": "local",
        "expected_version": 0,
        **{row["kind"] + "_model_id": row["id"] for row in models},
        "model_revisions": {row["id"]: row["revision"] for row in models},
    }
    h.call("PUT", path, owner, expected=403, json=body)
    selected = h.call("PUT", path, admin, json=body)
    assert selected["version"] == 1
    assert h.call("GET", path, admin)["selection"] == selected
    h.call("PUT", path, admin, expected=409, json=body)
    h.call("GET", f"/organizations/{org}/devices/{device['id']}/configuration", admin, expected=404)
    for suffix in ("profiles", "llm/connections", "model-profiles"):
        h.call("POST", f"/organizations/{org}/{suffix}", admin, expected=404, json={})
    h.call("GET", f"/platform/organizations/{org}/device-model-options", admin, expected=404)


def test_transfer_is_atomic_fresh_and_preserves_original_history(platform):
    h = platform
    owner, _ = h.user("association-owner")
    source = h.organization(owner, "Source")["id"]
    target_owner, _ = h.user("target-owner")
    target = h.organization(target_owner, "Target")["id"]
    row = h.device(owner, source, details={"notes": "private source note"}, location="private source room")
    credential = h.enroll(owner, source, row["id"])
    h.call(
        "POST",
        "/device/events",
        credential,
        json={
            "events": [
                {
                    "source_event_id": str(uuid4()),
                    "event_type": "device.status",
                    "occurred_at": "2026-09-24T00:00:00Z",
                    "code": "ready",
                }
            ]
        },
    )
    row = h.call("GET", f"/organizations/{source}/devices/{row['id']}", owner)
    body = {
        "organization_id": target,
        "name": "Destination registration",
        "expected_etag": row["management_etag"],
        "is_active": True,
    }
    # An administrator of just the source cannot push a device into another tenant.
    h.call("POST", f"/organizations/{source}/devices/{row['id']}/transfer", owner, expected=404, json=body)
    admin, _ = h.admin()
    central_path = f"/platform/devices/{row['id']}/transfer"
    h.call("POST", central_path, owner, expected=403, json=body)
    h.call("POST", central_path, target_owner, expected=403, json=body)
    h.call("POST", central_path, admin, expected=422, json={**body, "organization_id": source})
    occupied = h.device(target_owner, target)
    h.call("POST", f"/platform/devices/{row['id']}/transfer", admin, expected=409, json=body)
    unchanged = h.call("GET", f"/organizations/{source}/devices/{row['id']}", owner)
    assert unchanged["management_etag"] == row["management_etag"] and unchanged["is_active"]
    assert h.call("GET", "/device/config", credential)["device_id"] == row["id"]
    h.call(
        "PATCH", f"/organizations/{target}/devices/{occupied['id']}", target_owner, json={"is_active": False}
    )
    result = h.call("POST", f"/platform/devices/{row['id']}/transfer", admin, json=body)
    moved = result["device"]
    assert moved["id"] != row["id"] and moved["organization_id"] == target
    assert moved["enrollment_state"] == "pending" and moved["credential_status"] == "not_issued"
    assert moved["last_seen_at"] is None and moved["enrolled_at"] is None
    h.call("GET", "/device/config", credential, expected=401)
    h.call("POST", f"/platform/devices/{row['id']}/transfer", admin, expected=409, json=body)
    target_row = h.call("GET", f"/organizations/{target}/devices/{moved['id']}", target_owner)
    assert target_row["details"] == {} and target_row["location"] is None
    assert target_row["department_id"] is None
    assert target_row["device_unique_id"] == row["device_unique_id"]
    assert h.sql(
        "SELECT count(*) FROM device_platform.device_model_selections WHERE device_id=%s", (moved["id"],)
    ) == [(0,)]
    assert h.sql("SELECT organization_id::text FROM device_platform.devices WHERE id=%s", (row["id"],)) == [
        (source,)
    ]
    assert (
        h.sql(
            "SELECT count(*) FROM device_platform.activity_events WHERE device_id=%s AND organization_id=%s",
            (row["id"], source),
        )[0][0]
        >= 1
    )
    h.call("GET", f"/organizations/{target}/devices/{row['id']}", target_owner, expected=404)
    assert h.enroll(target_owner, target, moved["id"])
    assert len(h.call("GET", "/platform/audit?q=device.transferred_", admin)["items"]) == 2


def test_deactivation_bypasses_stale_assignment_but_reactivation_validates_it(platform):
    h = platform
    token, _ = h.user("inactive-owner")
    org = h.organization(token)["id"]
    department = h.call(
        "POST", f"/organizations/{org}/departments", token, expected=201, json={"name": "Lab"}
    )
    row = h.device(token, org, department_id=department["id"])
    h.call("PATCH", f"/organizations/{org}/departments/{department['id']}", token, json={"is_active": False})
    base = f"/organizations/{org}/devices/{row['id']}"
    off = h.call(
        "PATCH",
        base,
        token,
        json={"is_active": False, "department_id": department["id"], "expected_etag": row["management_etag"]},
    )
    assert not off["is_active"]
    h.call(
        "PATCH", base, token, expected=422, json={"is_active": True, "expected_etag": off["management_etag"]}
    )
    active = h.call(
        "PATCH",
        base,
        token,
        json={"is_active": True, "department_id": None, "expected_etag": off["management_etag"]},
    )
    assert active["is_active"]


def test_competing_transfers_create_one_destination_registration(platform):
    h = platform
    token, _ = h.user("concurrent-owner")
    source = h.organization(token, "Source")["id"]
    target = h.organization(token, "Target")["id"]
    row = h.device(token, source)
    admin, _ = h.admin("transfer-admin")
    path = f"/api/v1/platform/devices/{row['id']}/transfer"
    body = {"organization_id": target, "name": "Transferred", "expected_etag": row["management_etag"]}

    def move():
        return h.client.post(path, headers=h.headers(admin), json=body).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: move(), range(2))) == [200, 409]
    assert h.sql("SELECT count(*) FROM device_platform.devices WHERE organization_id=%s", (target,)) == [(1,)]
    assert h.call("GET", f"/organizations/{target}/devices", token)["items"][0]["is_active"] is False

    # Two distinct source registrations still compete for the one active target seat.
    contenders = [h.device(token, source), h.device(token, source, is_active=False)]

    def move_active(device):
        return h.client.post(
            f"/api/v1/platform/devices/{device['id']}/transfer",
            headers=h.headers(admin),
            json={
                "organization_id": target,
                "name": device["name"],
                "expected_etag": device["management_etag"],
                "is_active": True,
            },
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(move_active, contenders)) == [200, 409]
    assert h.sql(
        "SELECT count(*) FROM device_platform.devices WHERE organization_id=%s AND is_active",
        (target,),
    ) == [(1,)]
    # The loser retains its original registration; the failed transfer creates no row.
    assert h.sql(
        "SELECT count(*) FROM device_platform.devices WHERE id IN (%s,%s) AND enrollment_state='retired'",
        tuple(device["id"] for device in contenders),
    ) == [(1,)]
