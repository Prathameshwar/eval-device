"""Manual status tracks dates without changing processing or historical access."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace

import psycopg
import pytest

from pms_api.core.common import now
from pms_api.modules.manual_subscriptions import ManualSubscriptionPatch
from pms_api.modules.schemas import SubscriptionPlanPatch
from pms_api.modules.subscriptions import subscription_state


@pytest.mark.parametrize(
    "status,start,end,wanted",
    [
        ("active", None, None, "active"),
        ("active", -2, 0, "expired"),
        ("active", 1, 2, "scheduled"),
        ("suspended", -2, -1, "suspended"),
        ("cancelled", 1, 2, "cancelled"),
    ],
)
def test_state_boundaries(status, start, end, wanted):
    at = now()
    row = SimpleNamespace(
        subscription_status=status,
        subscription_starts_at=at + timedelta(days=start) if start is not None else None,
        subscription_ends_at=at + timedelta(days=end) if end is not None else None,
    )
    assert subscription_state(row, at) == wanted


@pytest.mark.parametrize(
    "body",
    [
        {"expected_version": True},
        {"expected_version": 0},
        {"expected_version": 1, "subscription_starts_at": "2026-01-01T00:00:00"},
        {"expected_version": 1, "subscription_notes": "bad" + chr(0)},
        {"expected_version": 1, "subscription_status": "expired"},
    ],
)
def test_invalid_manual_input(body):
    with pytest.raises(ValueError):
        ManualSubscriptionPatch(**body)


def test_invalid_catalog_name():
    with pytest.raises(ValueError):
        SubscriptionPlanPatch(expected_version=1, name="bad" + chr(0))


def test_manual_lifecycle_privacy_scope_and_processing_unchanged(platform):
    h = platform
    owner, _ = h.user("manual-owner")
    org = h.organization(owner)["id"]
    outsider, _ = h.user("manual-outsider")
    admin, _ = h.admin()
    path = f"/platform/organizations/{org}/subscription"
    tenant_path = f"/organizations/{org}/subscription"
    device = h.device(owner, org)
    credential = h.enroll(owner, org, device["id"])
    before = h.call("GET", "/device/config", credential)
    row = h.call("GET", path, admin)
    assert row["state"] == "active" and row["enforcement"] == "tracking_only" and row["version"] == 1
    h.call(
        "PATCH", path, owner, expected=403, json={"expected_version": 1, "subscription_status": "suspended"}
    )
    h.call("PATCH", path, admin, expected=422, json={"subscription_status": "suspended"})
    h.call("GET", tenant_path, admin, expected=404)
    h.call("GET", tenant_path, outsider, expected=404)
    start = (now() - timedelta(days=10)).isoformat()
    end = (now() - timedelta(days=1)).isoformat()
    row = h.call(
        "PATCH",
        path,
        admin,
        json={
            "expected_version": row["version"],
            "subscription_starts_at": start,
            "subscription_ends_at": end,
            "subscription_reference": "Internal agreement",
            "subscription_notes": "private finance note",
        },
    )
    assert row["state"] == "expired" and row["version"] == 2
    tenant = h.call("GET", tenant_path, owner)
    assert tenant["state"] == "expired" and "notes" not in tenant and "reference" not in tenant
    assert "private finance note" not in str(h.call("GET", f"/organizations/{org}", owner))
    for status in ("suspended", "cancelled", "active"):
        row = h.call(
            "PATCH", path, admin, json={"expected_version": row["version"], "subscription_status": status}
        )
        configuration = h.call("GET", "/device/config", credential)
        assert configuration["processing_allowed"] and configuration["is_active"]
        assert configuration["configuration_hash"] == before["configuration_hash"]
        assert h.call("GET", f"/organizations/{org}/devices/{device['id']}", owner)["id"] == device["id"]
    row = h.call(
        "PATCH",
        path,
        admin,
        json={
            "expected_version": row["version"],
            "subscription_ends_at": (now() + timedelta(days=366)).isoformat(),
        },
    )
    assert row["state"] == "active"
    h.call(
        "PATCH", path, admin, expected=409, json={"expected_version": 2, "subscription_status": "cancelled"}
    )
    h.call(
        "PATCH",
        path,
        admin,
        expected=422,
        json={"expected_version": row["version"], "subscription_ends_at": start},
    )
    h.call(
        "PATCH",
        path,
        admin,
        expected=422,
        json={"expected_version": row["version"], "subscription_status": None},
    )
    # Closing the plan catalog must not prevent maintaining an existing assignment.
    plan = row["plan"]
    h.call(
        "PATCH",
        "/platform/subscription-plans/" + plan["id"],
        admin,
        json={"expected_version": plan["configuration_version"], "is_active": False},
    )
    row = h.call(
        "PATCH",
        path,
        admin,
        json={
            "expected_version": row["version"],
            "subscription_plan_id": plan["id"],
            "subscription_reference": "Updated internal agreement",
        },
    )
    assert not row["plan"]["is_active"] and row["state"] == "active"
    history = h.call("GET", tenant_path + "/history?limit=2", owner)
    assert history["has_more"] and len(history["items"]) == 2
    assert "private finance note" not in str(history)
    next_page = h.call("GET", tenant_path + "/history?limit=2&cursor=" + history["next_cursor"], owner)
    assert {r["id"] for r in next_page["items"]}.isdisjoint(r["id"] for r in history["items"])
    h.call("GET", tenant_path + "/history", outsider, expected=404)
    h.call("GET", tenant_path + "/history", admin, expected=404)
    h.call("GET", path + "/history", owner, expected=403)


def test_manual_assignment_quota_concurrency_directory_and_constraints(platform):
    h = platform
    owner, _ = h.user("manual-capacity")
    org = h.organization(owner, "Alpha", plan="advanced")["id"]
    h.organization(owner, "Beta")
    admin, _ = h.admin()
    path = f"/platform/organizations/{org}/subscription"
    row = h.call("GET", path, admin)
    standard = next(
        r for r in h.call("GET", "/subscription-plans", owner)["items"] if r["code"] == "standard"
    )
    first, second = h.device(owner, org), h.device(owner, org)
    audits = h.sql(
        "SELECT count(*) FROM device_platform.activity_events WHERE event_type='platform.organization.subscription_updated'"
    )[0][0]
    h.call(
        "PATCH",
        path,
        admin,
        expected=409,
        json={
            "expected_version": row["version"],
            "subscription_plan_id": standard["id"],
            "subscription_status": "cancelled",
        },
    )
    assert h.call("GET", path, admin)["version"] == row["version"]
    assert (
        h.sql(
            "SELECT count(*) FROM device_platform.activity_events WHERE event_type='platform.organization.subscription_updated'"
        )[0][0]
        == audits
    )
    h.call("PATCH", f"/organizations/{org}/devices/{second['id']}", owner, json={"is_active": False})
    row = h.call(
        "PATCH",
        path,
        admin,
        json={"expected_version": row["version"], "subscription_plan_id": standard["id"]},
    )
    assert row["usage"]["devices"] == 1 and row["plan"]["code"] == "standard"

    def write(status):
        return h.client.patch(
            "/api/v1" + path,
            headers=h.headers(admin),
            json={"expected_version": row["version"], "subscription_status": status},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(write, ["suspended", "cancelled"])) == [200, 409]
    current = h.call("GET", path, admin)
    listed = h.call("GET", "/platform/subscriptions?limit=1", admin)
    assert listed["total"] == 2 and listed["has_more"] and listed["items"][0]["organization_id"] == org
    next_page = h.call("GET", "/platform/subscriptions?limit=1&cursor=" + listed["next_cursor"], admin)
    assert next_page["items"][0]["organization_name"] == "Beta"
    h.call(
        "GET", "/platform/subscriptions?state=expired&cursor=" + listed["next_cursor"], admin, expected=422
    )
    assert h.call("GET", "/platform/subscriptions?state=" + current["state"], admin)["total"] == 1
    assert h.call("GET", "/platform/subscriptions?q=%25", admin)["items"] == []
    h.call("GET", "/platform/subscriptions", owner, expected=403)
    for statement in [
        "UPDATE device_platform.organizations SET subscription_version=99 WHERE id=%s",
        "UPDATE device_platform.organizations SET subscription_starts_at=now(), subscription_ends_at=now() WHERE id=%s",
        "UPDATE device_platform.organizations SET subscription_ends_at='infinity' WHERE id=%s",
    ]:
        with pytest.raises(psycopg.errors.CheckViolation):
            h.sql(statement, (org,))
    # Legacy assignment also invalidates a manual editor's version.
    advanced = next(
        r for r in h.call("GET", "/subscription-plans", owner)["items"] if r["code"] == "advanced"
    )
    h.call("PUT", path, admin, json={"subscription_plan_id": advanced["id"]})
    h.call(
        "PATCH",
        path,
        admin,
        expected=409,
        json={"expected_version": current["version"], "subscription_notes": "stale"},
    )
    h.call("DELETE", f"/platform/organizations/{org}", admin)
    archived = h.call("GET", path, admin)
    h.call(
        "PATCH",
        path,
        admin,
        expected=409,
        json={"expected_version": archived["version"], "subscription_status": "active"},
    )
    assert h.call("GET", "/platform/subscriptions?q=Alpha", admin)["items"] == []
    assert first["organization_id"] == org
