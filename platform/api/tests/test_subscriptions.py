import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from uuid import uuid4

import psycopg
import pytest
from sqlalchemy.engine import make_url


def plans(p, token):
    return {row["code"]: row for row in p.call("GET", "/platform/subscription-plans", token)["items"]}


def edit(p, token, code="standard", expected=200, **values):
    row = plans(p, token)[code]
    return p.call(
        "PATCH",
        f"/platform/subscription-plans/{row['id']}",
        token,
        expected=expected,
        json={"expected_version": row["configuration_version"], **values},
    )


def test_plan_catalog_required_registration_and_admin_controls(platform):
    p = platform
    admin, _ = p.admin()
    catalog = plans(p, admin)
    assert set(catalog) == {"standard", "advanced"}
    assert catalog["standard"]["price_amount"] == "350000.00"
    assert catalog["advanced"]["price_amount"] == "500000.00"
    assert {(r["currency"], r["billing_period"]) for r in catalog.values()} == {("INR", "unspecified")}
    assert (catalog["standard"]["max_users"], catalog["standard"]["max_devices"]) == (200, 1)
    assert (catalog["advanced"]["max_users"], catalog["advanced"]["max_devices"]) == (500, 3)
    sid = catalog["standard"]["id"]
    p.call("POST", "/organizations", admin, expected=422, json={"name": "Plan required"})
    p.call(
        "POST",
        "/organizations",
        admin,
        expected=409,
        json={"name": "Unknown plan", "subscription_plan_id": str(uuid4())},
    )
    org = p.organization(admin)
    assert org["subscription_plan_id"] == sid and org["subscription_assigned_at"]
    user, _ = p.user("catalog-reader")
    assert len(p.call("GET", "/subscription-plans", user)["items"]) == 2
    p.call("GET", "/platform/subscription-plans", user, expected=403)
    p.call(
        "PATCH",
        f"/platform/subscription-plans/{sid}",
        user,
        expected=403,
        json={"expected_version": 1, "max_users": 99},
    )
    p.call("GET", f"/organizations/{org['id']}/subscription", user, expected=404)
    for values in (
        {"max_users": 0},
        {"max_devices": True},
        {"price_amount": "NaN"},
        {"price_amount": "1.001"},
        {"currency": "XYZ"},
        {"max_users": None},
        {"price_amount": None},
    ):
        edit(p, admin, expected=422, **values)
    changed = edit(p, admin, price_amount="1234.56", currency="USD", billing_period="annual")
    assert changed["price_amount"] == "1234.56" and changed["currency"] == "USD"
    p.call(
        "PATCH",
        f"/platform/subscription-plans/{sid}",
        admin,
        expected=409,
        json={"expected_version": 1, "max_users": 3},
    )
    edit(p, admin, is_active=False)
    assert [r["code"] for r in p.call("GET", "/subscription-plans", user)["items"]] == ["advanced"]
    p.call(
        "POST",
        "/organizations",
        admin,
        expected=409,
        json={"name": "Unavailable", "subscription_plan_id": sid},
    )
    # Catalog deactivation closes new selection; an existing assignment remains usable.
    p.device(admin, org["id"])
    p.call(
        "PATCH",
        f"/organizations/{org['id']}",
        admin,
        expected=422,
        json={"subscription_plan_id": catalog["advanced"]["id"]},
    )
    events = p.sql(
        "SELECT count(*) FROM device_platform.activity_events WHERE event_type='subscription.plan.updated'"
    )
    assert events[0][0] == 2
    price_change = p.sql(
        "SELECT details->'changes'->'price_amount' FROM device_platform.activity_events WHERE event_type='subscription.plan.updated' AND details->'changes' ? 'price_amount'"
    )[0][0]
    assert price_change == {"before": "350000.00", "after": "1234.56"}
    with pytest.raises(psycopg.errors.CheckViolation):
        p.sql("UPDATE device_platform.subscription_plans SET configuration_version=999 WHERE id=%s", (sid,))


def test_user_seats_reserve_invitations_and_cover_admin_paths(platform):
    p = platform
    admin, _ = p.admin()
    edit(p, admin, max_users=2)
    oid = p.organization(admin)["id"]
    invitation = p.call(
        "POST",
        f"/organizations/{oid}/invitations",
        admin,
        expected=201,
        json={"email": "trainee@example.com", "role": "org_trainee"},
    )
    rejected = p.call(
        "POST",
        f"/organizations/{oid}/invitations",
        admin,
        expected=409,
        json={"email": "second@example.com", "role": "org_user"},
    )
    assert rejected["error"]["code"] == "subscription_user_limit"
    summary = p.call("GET", f"/organizations/{oid}/subscription", admin)
    assert summary["usage"] == {"active_users": 1, "pending_invitations": 1, "users": 2, "devices": 0}
    trainee, _ = p.user("trainee")
    member = p.call("POST", "/invitations/accept", trainee, json={"token": invitation["invitation_token"]})
    mid = member["id"]
    assert p.call("GET", f"/organizations/{oid}/subscription", admin)["usage"]["active_users"] == 2
    p.call("PATCH", f"/organizations/{oid}/members/{mid}", admin, json={"is_active": False})
    pending = p.call(
        "POST",
        f"/organizations/{oid}/invitations",
        admin,
        expected=201,
        json={"email": "second@example.com", "role": "org_user"},
    )["membership"]["id"]
    p.call("PATCH", f"/organizations/{oid}/members/{mid}", admin, expected=409, json={"is_active": True})
    p.sql(
        "UPDATE device_platform.organization_memberships SET invitation_expires_at=clock_timestamp() WHERE id=%s",
        (pending,),
    )
    p.call("PATCH", f"/organizations/{oid}/members/{mid}", admin, json={"is_active": True})
    resend = p.call("POST", f"/organizations/{oid}/invitations/{pending}/resend", admin, expected=409)
    assert resend["error"]["code"] == "subscription_user_limit"
    _, replacement = p.user("replacement")
    p.call(
        "POST",
        f"/platform/organizations/{oid}/administrators",
        admin,
        expected=409,
        json={"user_id": replacement["id"]},
    )
    p.call("PATCH", f"/organizations/{oid}/members/{mid}", admin, json={"is_active": False})
    p.call(
        "POST", f"/platform/organizations/{oid}/administrators", admin, json={"user_id": replacement["id"]}
    )
    # Global account suspension does not silently release an active organization membership.
    p.call("PATCH", f"/platform/users/{replacement['id']}", admin, json={"is_active": False})
    assert p.call("GET", f"/organizations/{oid}/subscription", admin)["remaining"]["users"] == 0
    with pytest.raises(psycopg.errors.CheckViolation) as rejected_sql:
        p.sql("UPDATE device_platform.organization_memberships SET is_active=true WHERE id=%s", (mid,))
    assert rejected_sql.value.diag.constraint_name == "subscription_user_limit"
    p.call("PATCH", f"/platform/users/{replacement['id']}", admin, json={"is_active": True})


def test_device_capacity_reactivation_and_concurrent_sql(platform):
    p = platform
    admin, _ = p.admin()
    oid = p.organization(admin)["id"]
    first = p.device(admin, oid)["id"]
    body = {
        "organization_id": oid,
        "name": "Beyond capacity",
        "device_type": "laptop",
        "device_unique_id": str(uuid4()),
    }
    blocked = p.call("POST", "/platform/devices", admin, expected=409, json=body)
    assert blocked["error"]["code"] == "subscription_device_limit"
    p.call("POST", f"/organizations/{oid}/devices/{first}/revoke", admin)
    p.call("POST", "/platform/devices", admin, expected=409, json=body)
    p.call("PATCH", f"/organizations/{oid}/devices/{first}", admin, json={"is_active": False})
    second = p.device(admin, oid)["id"]
    p.call("PATCH", f"/organizations/{oid}/devices/{first}", admin, expected=409, json={"is_active": True})
    p.call("POST", f"/organizations/{oid}/devices/{second}/retire", admin)
    ready, release, barrier = Event(), Event(), Barrier(2)
    url = (
        make_url(p.settings.database_url.get_secret_value())
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )

    def insert_device():
        try:
            with psycopg.connect(url) as connection:
                barrier.wait(timeout=20)
                unique_id = str(uuid4())
                connection.execute(
                    "INSERT INTO device_platform.device_identities(device_unique_id) VALUES(%s)",
                    (unique_id,),
                )
                connection.execute(
                    "INSERT INTO device_platform.devices(id,organization_id,device_unique_id,name,device_type) VALUES(%s,%s,%s,'Concurrent device','laptop')",
                    (uuid4(), oid, unique_id),
                )
                ready.set()
                assert release.wait(timeout=20)
            return "created"
        except psycopg.errors.CheckViolation as error:
            return error.diag.constraint_name

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(insert_device) for _ in range(2)]
        try:
            assert ready.wait(timeout=20)
            deadline = time.monotonic() + 10
            while True:
                waiting = p.sql(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND usename=%s AND wait_event_type='Lock'",
                    (make_url(url).username,),
                )[0][0]
                if waiting or time.monotonic() >= deadline:
                    break
                Event().wait(0.05)
            assert waiting, "The competing writer must wait while the final slot is uncommitted"
        finally:
            release.set()
        results = [future.result(timeout=30) for future in futures]
    assert sorted(results) == ["created", "subscription_device_limit"]
    assert p.call("GET", f"/organizations/{oid}/subscription", admin)["usage"]["devices"] == 1
    other = p.organization(admin, "Independent quota")["id"]
    p.device(admin, other)
    assert p.call("GET", f"/organizations/{other}/subscription", admin)["usage"]["devices"] == 1


def test_plan_assignment_and_limit_edits_cannot_strand_organizations(platform):
    p = platform
    admin, _ = p.admin()
    edit(p, admin, max_users=2, max_devices=1)
    edit(p, admin, code="advanced", max_users=4, max_devices=2)
    catalog = plans(p, admin)
    standard = catalog["standard"]["id"]
    org = p.organization(admin, plan="advanced")
    oid = org["id"]
    p.device(admin, oid)
    second = p.device(admin, oid)["id"]
    path = f"/platform/organizations/{oid}/subscription"
    p.call("PUT", path, admin, expected=409, json={"subscription_plan_id": standard})
    edit(p, admin, code="advanced", max_devices=1, expected=409)
    assert plans(p, admin)["advanced"]["max_devices"] == 2
    p.call("PATCH", f"/organizations/{oid}/devices/{second}", admin, json={"is_active": False})
    changed = p.call("PUT", path, admin, json={"subscription_plan_id": standard})
    assert changed["plan"]["code"] == "standard" and changed["remaining"]["devices"] == 0
    assert changed["assigned_at"] != org["subscription_assigned_at"]
    assert not changed["over_limit"]
    unchanged = p.call("PUT", path, admin, json={"subscription_plan_id": standard})
    assert unchanged["assigned_at"] == changed["assigned_at"]
    owner, owner_user = p.user("tenant-owner")
    p.call("POST", f"/platform/organizations/{oid}/administrators", admin, json={"user_id": owner_user["id"]})
    p.call("PUT", path, owner, expected=403, json={"subscription_plan_id": catalog["advanced"]["id"]})
    p.call("GET", f"/organizations/{oid}/subscription", owner)
    edit(p, admin, max_users=1, expected=409)
    assert p.call("GET", path, admin)["usage"]["users"] == 2
    assert (
        p.sql(
            "SELECT count(*) FROM device_platform.activity_events WHERE event_type='platform.organization.subscription_changed' AND organization_id=%s",
            (oid,),
        )[0][0]
        == 1
    )

    upgraded = p.call("PUT", path, admin, json={"subscription_plan_id": catalog["advanced"]["id"]})
    assert upgraded["plan"]["code"] == "advanced" and upgraded["remaining"]["devices"] == 1
    p.call("PATCH", f"/organizations/{oid}/devices/{second}", admin, json={"is_active": True})
    assert p.call("GET", path, admin)["usage"]["devices"] == 2


@pytest.mark.parametrize("code,user_limit,device_limit", [("standard", 200, 1), ("advanced", 500, 3)])
def test_confirmed_plan_boundaries_enforced_without_customization(platform, code, user_limit, device_limit):
    p = platform
    admin, _ = p.admin()
    oid = p.organization(admin, plan=code)["id"]
    # The creator occupies a seat. Reserve all but the final user seat with SQL,
    # then exercise acceptance/rejection through the public API at the real cap.
    p.sql(
        """
        INSERT INTO device_platform.organization_memberships
          (id,organization_id,role,invited_email,invitation_token_hash,invitation_expires_at)
        SELECT gen_random_uuid(),%s,'org_user','reserved-'||n||'@example.com',
          gen_random_uuid()::text,clock_timestamp()+interval '1 day'
        FROM generate_series(1,%s) n
        """,
        (oid, user_limit - 2),
    )
    p.call(
        "POST",
        f"/organizations/{oid}/invitations",
        admin,
        expected=201,
        json={"email": "last-seat@example.com", "role": "org_trainee"},
    )
    rejected = p.call(
        "POST",
        f"/organizations/{oid}/invitations",
        admin,
        expected=409,
        json={"email": "over-capacity@example.com", "role": "org_user"},
    )
    assert rejected["error"]["code"] == "subscription_user_limit"
    for _ in range(device_limit):
        p.device(admin, oid)
    rejected = p.call(
        "POST",
        "/platform/devices",
        admin,
        expected=409,
        json={
            "organization_id": oid,
            "name": "Over capacity",
            "device_type": "laptop",
            "device_unique_id": str(uuid4()),
        },
    )
    assert rejected["error"]["code"] == "subscription_device_limit"
    summary = p.call("GET", f"/organizations/{oid}/subscription", admin)
    assert summary["usage"]["users"] == user_limit
    assert summary["usage"]["devices"] == device_limit
    assert summary["remaining"] == {"users": 0, "devices": 0}
    assert not summary["over_limit"]
