"""Read-only log contracts, redaction and isolated runtime-role PostgreSQL access."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from pms_api.database.models import ActivityEvent
from pms_api.modules.activity import ActivityFilters, activity_view


def seed_event(
    h,
    org=None,
    *,
    category="operational",
    department=None,
    severity="info",
    details=None,
    event_type="fixture.event",
    occurred=None,
    expired=False,
):
    event_id = str(uuid4())
    timestamp = occurred or datetime.now(UTC) - timedelta(days=3 if expired else 0)
    expiry = datetime.now(UTC) + timedelta(days=-1 if expired else 2)
    h.sql(
        """INSERT INTO device_platform.activity_events
        (id,organization_id,department_id,actor_type,category,event_type,severity,occurred_at,received_at,details,expires_at)
        VALUES (%s,%s,%s,'system',%s,%s,%s,%s,%s,%s::jsonb,%s)""",
        (
            event_id,
            org,
            department,
            category,
            event_type,
            severity,
            timestamp,
            timestamp,
            json.dumps(details or {"status": "ready"}),
            expiry,
        ),
    )
    return event_id


def test_log_projection_omits_unapproved_payloads_and_signed_urls():
    row = ActivityEvent(
        id=uuid4(),
        details={
            "status": "succeeded",
            "duration_ms": 32,
            "fields": ["api_key", "is_active"],
            "api_key": "private-test-key",
            "transcript": "private conversation",
            "prompt": "private prompt",
            "before": {"is_active": False, "password": "private-password"},
            "reason": "https://private.invalid/file?sig=test-private",
            "source": "web_" + "x" * 40,
        },
    )
    result = activity_view(row)
    assert result["details_redacted"]
    assert result["details"]["fields"] == ["api_key", "is_active"]
    assert result["details"]["before"] == {"is_active": False}
    assert result["details"]["duration_ms"] == 32
    assert "private" not in json.dumps(result, default=str)
    assert "web_" not in json.dumps(result, default=str)


@pytest.mark.parametrize(
    "values",
    [
        {"q": "bad\x00text"},
        {"q": "bad\ud800"},
        {"limit": 101},
        {"since": "2026-09-24T00:00:00"},
        {"severity": "unknown"},
    ],
)
def test_log_filters_reject_invalid_inputs(values):
    with pytest.raises(ValueError):
        ActivityFilters(**values)


@pytest.fixture(autouse=True)
def no_external_mail(monkeypatch):
    async def undelivered(*_):
        return False

    monkeypatch.setattr("pms_api.modules.management.send_invitation", undelivered)


def test_platform_and_tenant_filters_details_retention_and_read_only(platform):
    h = platform
    admin, _ = h.admin("audit-owner")
    owner, _ = h.user("activity-owner")
    org = h.organization(owner)["id"]
    audit_id = seed_event(
        h,
        org,
        category="audit",
        severity="warning",
        details={"status": "changed", "api_key": "private-value"},
    )
    operation_id = seed_event(h, org, event_type="fixture.device")
    expired = seed_event(h, org, expired=True)
    base = f"/organizations/{org}/activities"
    page = h.call(
        "GET", "/platform/audit?q=fixture.&include_total=true&sort_by=occurred_at&sort_order=desc", admin
    )
    assert page["total"] == 1 and page["items"][0]["id"] == audit_id and not page["has_more"]
    assert h.call("GET", "/platform/audit/" + audit_id, admin) == page["items"][0]
    assert page["items"][0]["details_redacted"]
    h.call("GET", "/platform/audit/" + operation_id, admin, expected=404)
    h.call("GET", "/platform/audit?category=operational", admin, expected=403)
    h.call("GET", "/platform/audit", owner, expected=403)
    h.call("GET", base, admin, expected=404)
    h.call("GET", base + "/" + operation_id, admin, expected=404)
    assert h.call("GET", base + "?q=fixture.&category=all&include_total=true", owner)["total"] == 2
    assert (
        h.call("GET", base + "?q=fixture.&category=all&severity=warning", owner)["items"][0]["id"] == audit_id
    )
    assert h.call("GET", base + "?q=fixture.&actor_type=device", owner)["items"] == []
    assert h.call("GET", base + "?q=private-value&category=audit", owner)["items"] == []
    assert h.call("GET", base + "/" + operation_id, owner)["event_type"] == "fixture.device"
    h.call("GET", base + "/" + expired, owner, expected=404)
    h.call(
        "GET",
        base + "?category=all&since=2026-09-25T00:00:00Z&until=2026-09-24T00:00:00Z",
        owner,
        expected=422,
    )
    for method in ["POST", "PATCH", "DELETE"]:
        response = h.client.request(method, "/api/v1" + base + "/" + operation_id, headers=h.headers(owner))
        assert response.status_code == 405


def test_department_category_and_lifecycle_boundaries(platform):
    h = platform
    owner, _ = h.user("scope-owner")
    org = h.organization(owner)["id"]
    other_org = h.organization(owner, "Other tenant")["id"]
    dept = h.call("POST", f"/organizations/{org}/departments", owner, expected=201, json={"name": "One"})
    other_dept = h.call(
        "POST", f"/organizations/{org}/departments", owner, expected=201, json={"name": "Two"}
    )
    reader, user = h.user("activity-reader")
    invitation = h.call(
        "POST",
        f"/organizations/{org}/invitations",
        owner,
        expected=201,
        json={"email": user["email"], "role": "org_user", "department_id": dept["id"]},
    )
    h.call("POST", "/invitations/accept", reader, json={"token": invitation["invitation_token"]})
    visible = seed_event(h, org, department=dept["id"])
    foreign = seed_event(h, other_org)
    wrong_dept = seed_event(h, org, department=other_dept["id"])
    org_wide = seed_event(h, org)
    audit_id = seed_event(h, org, department=dept["id"], category="audit")
    base = f"/organizations/{org}/activities"
    assert [r["id"] for r in h.call("GET", base + "?q=fixture.", reader)["items"]] == [visible]
    for event in [foreign, wrong_dept, org_wide]:
        h.call("GET", base + "/" + event, reader, expected=404)
    h.call("GET", base + "/" + audit_id, reader, expected=403)
    h.call("GET", base + "?category=all", reader, expected=403)
    h.call("GET", base + "?category=audit", reader, expected=403)
    assert h.call("GET", base + "?department_id=" + other_dept["id"], reader)["items"] == []
    h.call("PATCH", f"/organizations/{org}/departments/{dept['id']}", owner, json={"is_active": False})
    h.call("GET", base, reader, expected=409)
    h.call("GET", base + "/" + visible, reader, expected=409)


def test_log_cursor_ties_filter_binding_and_date_boundaries(platform):
    h = platform
    owner, _ = h.user("cursor-owner")
    org = h.organization(owner)["id"]
    start = datetime(2026, 9, 20, tzinfo=UTC)
    ids = {seed_event(h, org, occurred=start) for _ in range(3)}
    seed_event(h, org, occurred=start + timedelta(days=1))
    base = f"/organizations/{org}/activities?q=fixture.&sort_by=occurred_at&sort_order=desc&limit=1&include_total=true&since=2026-09-20T00:00:00Z&until=2026-09-21T00:00:00Z"
    first = h.call("GET", base, owner)
    assert first["total"] == 3 and first["has_more"]
    second = h.call("GET", base + "&cursor=" + first["next_cursor"], owner)
    third = h.call("GET", base + "&cursor=" + second["next_cursor"], owner)
    assert {p["items"][0]["id"] for p in [first, second, third]} == ids
    assert not third["has_more"] and third["next_cursor"] is None
    h.call("GET", base + "&severity=error&cursor=" + first["next_cursor"], owner, expected=422)
    h.call("GET", base + "&cursor=tampered", owner, expected=422)
    assert h.call("GET", f"/organizations/{org}/activities?q=%25", owner)["items"] == []
