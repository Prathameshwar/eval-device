"""Physical IDs are immutable and global; registrations remain tenant-scoped."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest
from pydantic import ValidationError
from sqlalchemy.engine import make_url
from test_default_local_models import run_upgrade, upgrade_database  # noqa: F401
from test_direct_models import setup

from pms_api.modules.device_management import FleetDeviceCreate


@pytest.mark.parametrize("value", [None, "", "   ", "x" * 51, "bad\x00id", "bad\nid", "bad\x7fid"])
def test_device_unique_id_validation(value):
    body = {"organization_id": uuid4(), "name": "Device", "device_type": "laptop"}
    if value is not None:
        body["device_unique_id"] = value
    with pytest.raises(ValidationError):
        FleetDeviceCreate(**body)


def test_device_unique_id_accepts_fifty_characters_and_trims():
    body = FleetDeviceCreate(
        organization_id=uuid4(), name="Device", device_type="manikin", device_unique_id="  " + "x" * 50 + "  "
    )
    assert body.device_unique_id == "x" * 50


def test_global_duplicate_race_and_immutable_identity(platform):
    h = platform
    tenant, admin, org = setup(h)
    other = h.organization(tenant, "Other ID tenant")["id"]
    body = {"name": "Unique device", "device_type": "manikin", "device_unique_id": "Manikin-0001"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda organization: h.client.post(
                    "/api/v1/platform/devices",
                    headers=h.headers(admin),
                    json={**body, "organization_id": organization},
                ),
                (org, other),
            )
        )
    assert sorted(response.status_code for response in responses) == [201, 409]
    failure = next(response for response in responses if response.status_code == 409)
    assert failure.json()["error"]["code"] == "device_unique_id_exists"
    row = next(response.json() for response in responses if response.status_code == 201)
    path = f"/platform/devices/{row['id']}"
    h.call(
        "POST",
        "/platform/devices",
        admin,
        expected=409,
        json={**body, "organization_id": other, "device_unique_id": " manikin-0001 "},
    )
    h.call(
        "POST",
        "/platform/devices",
        admin,
        expected=422,
        json={"organization_id": org, "name": "Missing ID", "device_type": "laptop"},
    )
    for url, token in (
        (path, admin),
        (f"/organizations/{row['organization_id']}/devices/{row['id']}", tenant),
    ):
        h.call(
            "PATCH",
            url,
            token,
            expected=422,
            json={"expected_etag": row["management_etag"], "device_unique_id": "new-id"},
        )
    for statement, params in (
        ("UPDATE device_platform.devices SET device_unique_id=%s WHERE id=%s", ("new-id", row["id"])),
        (
            "UPDATE device_platform.device_identities SET device_unique_id=%s WHERE device_unique_id=%s",
            ("new-id", body["device_unique_id"]),
        ),
        (
            "DELETE FROM device_platform.device_identities WHERE device_unique_id=%s",
            (body["device_unique_id"],),
        ),
    ):
        with pytest.raises(psycopg.errors.CheckViolation):
            h.sql(statement, params)
    assert h.sql("SELECT count(*) FROM device_platform.device_identities") == [(1,)]
    assert h.sql(
        "SELECT count(*) FROM device_platform.activity_events WHERE event_type='platform.device.registered'"
    ) == [(1,)]
    found = h.call("GET", "/platform/devices?q=manikin-0001", admin)["items"]
    assert [item["device_unique_id"] for item in found] == [body["device_unique_id"]]
    for key in ("worker_database_url", "retention_database_url"):
        role = make_url(getattr(h.settings, key).get_secret_value()).username
        assert h.sql(
            "SELECT has_table_privilege(%s,'device_platform.device_identities','SELECT,INSERT,UPDATE,DELETE')",
            (role,),
        ) == [(False,)]


def test_transfer_keeps_unique_id_and_retirement_never_releases_it(platform):
    h = platform
    tenant, admin, org = setup(h)
    target = h.organization(tenant, "Transfer destination")["id"]
    row = h.device(tenant, org, device_unique_id="Permanent-Manikin-17", device_type="manikin")
    h.enroll(tenant, org, row["id"])
    row = h.call("GET", f"/platform/devices/{row['id']}", admin)
    moved = h.call(
        "POST",
        f"/platform/devices/{row['id']}/transfer",
        admin,
        json={
            "expected_etag": row["management_etag"],
            "organization_id": target,
            "name": "Transferred",
            "is_active": True,
        },
    )
    current = moved["device"]
    assert current["id"] != row["id"]
    assert moved["source"]["device_unique_id"] == current["device_unique_id"] == "Permanent-Manikin-17"
    assert moved["source"]["enrollment_state"] == "retired"
    assert current["enrollment_state"] == "pending" and current["organization_id"] == target
    assert h.sql("SELECT count(*) FROM device_platform.device_identities") == [(1,)]
    h.call("DELETE", f"/platform/devices/{current['id']}?expected_etag={current['management_etag']}", admin)
    h.call(
        "POST",
        "/platform/devices",
        admin,
        expected=409,
        json={
            "organization_id": org,
            "name": "Duplicate retired identity",
            "device_type": "manikin",
            "device_unique_id": "Permanent-Manikin-17",
        },
    )


def test_upgrade_backfills_existing_uuids_and_preserves_registrations(upgrade_database):  # noqa: F811
    target = upgrade_database
    run_upgrade(target, "0039_default_local_models")
    org, user, first, second = [uuid4() for _ in range(4)]
    with psycopg.connect(target) as c:
        c.execute("SET search_path=device_platform,public")
        c.execute(
            "INSERT INTO users(id,identity_issuer,identity_subject,display_name,email,email_verified) VALUES(%s,'fixture','fixture','Operator','fixture@example.test',true)",
            (user,),
        )
        c.execute(
            "INSERT INTO organizations(id,name,policy_settings,subscription_plan_id) SELECT %s,'Upgrade fixture',default_organization_policy,(SELECT id FROM subscription_plans WHERE code='standard') FROM platform_settings",
            (org,),
        )
        c.execute(
            "INSERT INTO organization_memberships(id,organization_id,user_id,role,is_active,invitation_status,joined_at) VALUES(gen_random_uuid(),%s,%s,'org_admin',true,'accepted',now())",
            (org, user),
        )
        for ident in (first, second):
            c.execute(
                "INSERT INTO devices(id,organization_id,name,device_type,is_active,status_reason,enrollment_state) "
                "VALUES(%s,%s,'Existing manikin','manikin',false,'migration_fixture',%s)",
                (ident, org, "retired" if ident == second else "pending"),
            )
    run_upgrade(target)
    with psycopg.connect(target) as c:
        rows = c.execute(
            "SELECT id,organization_id,device_unique_id FROM device_platform.devices ORDER BY id"
        ).fetchall()
        assert {tuple(row) for row in rows} == {(first, org, str(first)), (second, org, str(second))}
        assert c.execute("SELECT count(*) FROM device_platform.device_identities").fetchone() == (2,)
        assert c.execute(
            "SELECT count(*) FROM device_platform.activity_events WHERE event_type='device.unique_id.initialized'"
        ).fetchone() == (2,)
    run_upgrade(target)
    with psycopg.connect(target) as c:
        assert (
            c.execute(
                "SELECT id,organization_id,device_unique_id FROM device_platform.devices ORDER BY id"
            ).fetchall()
            == rows
        )
        for invalid in (None, "", " ", "x" * 51, "bad\nid"):
            with pytest.raises((psycopg.errors.CheckViolation, psycopg.errors.NotNullViolation)):
                with c.transaction():
                    c.execute(
                        "INSERT INTO device_platform.device_identities(device_unique_id) VALUES(%s)",
                        (invalid,),
                    )
