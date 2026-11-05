"""Authorization, upgrade guard and queue maintenance regressions."""

from datetime import datetime, timedelta
from uuid import uuid4

import psycopg
import pytest
from test_session_queue import queue_device as queue_device


def trainee(p, instructor, org, name, department=None):
    token, user = p.user(name)
    invitation = p.call(
        "POST",
        f"/organizations/{org}/invitations",
        instructor,
        expected=201,
        json={"email": name + "@example.com", "role": "org_trainee", "department_id": department},
    )
    p.call("POST", "/invitations/accept", token, json={"token": invitation["invitation_token"]})
    return token, user


def test_individual_trainee_results_and_database_deadline_guard(queue_device, monkeypatch):
    p, instructor, admin, org, device, token, path, item, case = queue_device
    first_token, first = trainee(p, instructor, org, "queue-first")
    second_token, second = trainee(p, instructor, org, "queue-second")
    queue = p.call(
        "POST",
        path,
        instructor,
        expected=201,
        json={
            "request_key": str(uuid4()),
            "items": [{**item, "learner_id": first["id"]}, {**item, "learner_id": second["id"]}],
        },
    )
    rows = queue["items"]
    for who, expected in ((first_token, first), (second_token, second)):
        history = p.call("GET", f"/organizations/{org}/practice-sessions", who)
        assert len(history["items"]) == 1
        assert history["items"][0]["learner_id"] == expected["id"]
        assert p.call("GET", f"/organizations/{org}/training/stats", who)["sessions"] == 1
        p.call("GET", path, who, expected=403)
    p.call("GET", f"/organizations/{org}/practice-sessions/{rows[0]['id']}", second_token, expected=404)
    with pytest.raises(psycopg.errors.CheckViolation):
        p.sql(
            "UPDATE device_platform.practice_sessions SET expires_at=expires_at+interval '1 hour' WHERE id=%s",
            (rows[0]["id"],),
        )
    from pms_api.modules import session_queue

    stamp = max(datetime.fromisoformat(row["expires_at"]) for row in rows) + timedelta(seconds=1)
    monkeypatch.setattr(session_queue, "now", lambda: stamp)
    # Expiry happens even with no desktop and no queue GET request.
    p.client.portal.call(session_queue.expire_pending, p.client.app.state.sessions)
    assert p.sql("SELECT status FROM device_platform.practice_sessions ORDER BY position") == [
        ("expired",),
        ("expired",),
    ]
    assert (
        p.sql(
            "SELECT count(*) FROM device_platform.activity_events WHERE event_type='practice.session.expired'"
        )[0][0]
        == 2
    )


def test_revoked_participant_cannot_begin_and_lease_loss_cannot_resume(queue_device, monkeypatch):
    p, instructor, admin, org, device, token, path, item, case = queue_device
    learner_token, learner = trainee(p, instructor, org, "queue-revoked")
    queue = p.call(
        "POST",
        path,
        instructor,
        expected=201,
        json={"request_key": str(uuid4()), "items": [{**item, "learner_id": learner["id"]}, item]},
    )
    first, second = queue["items"]
    p.sql(
        "UPDATE device_platform.organization_memberships SET is_active=false WHERE organization_id=%s AND user_id=%s",
        (org, learner["id"]),
    )
    runtime = {"runtime_id": str(uuid4())}
    p.call("POST", f"/device/session-queue/{first['id']}/begin", token, json=runtime, expected=403)
    p.call("POST", path + "/" + first["id"] + "/end", instructor)
    active = p.call("POST", f"/device/session-queue/{second['id']}/begin", token, json=runtime)
    from pms_api.modules import session_queue

    monkeypatch.setattr(
        session_queue, "now", lambda: datetime.fromisoformat(active["lease_until"]) + timedelta(seconds=1)
    )
    poll = p.call(
        "POST",
        "/device/session-queue/poll",
        token,
        json={**runtime, "session_id": second["id"], "runtime_state": "assigned"},
    )
    assert poll["active"] is None
    p.call("POST", f"/device/session-queue/{second['id']}/begin", token, json=runtime, expected=409)
    assert (
        p.call(
            "POST",
            f"/device/session-queue/{second['id']}/finish",
            token,
            json={**runtime, "outcome": "completed"},
        )["status"]
        == "failed"
    )


def test_learner_picker_matches_device_scope_admission(queue_device):
    p, instructor, admin, org, device, token, path, item, case = queue_device
    departments = [
        p.call("POST", f"/organizations/{org}/departments", instructor, expected=201, json={"name": name})[
            "id"
        ]
        for name in ("Lab A", "Lab B")
    ]
    _, first = trainee(p, instructor, org, "department-a", departments[0])
    _, second = trainee(p, instructor, org, "department-b", departments[1])
    endpoint = f"/organizations/{org}/session-queue/learners?device_id={device['id']}"
    people = {row["id"] for row in p.call("GET", endpoint, instructor)["items"]}
    assert item["learner_id"] in people
    assert first["id"] not in people and second["id"] not in people
    p.call(
        "POST",
        path,
        instructor,
        expected=403,
        json={"request_key": str(uuid4()), "items": [{**item, "learner_id": first["id"]}]},
    )
    current = p.call("GET", f"/organizations/{org}/devices/{device['id']}", instructor)
    p.call(
        "PATCH",
        f"/organizations/{org}/devices/{device['id']}",
        instructor,
        json={"expected_etag": current["management_etag"], "department_id": departments[0]},
    )
    people = {row["id"] for row in p.call("GET", endpoint, instructor)["items"]}
    assert first["id"] in people and item["learner_id"] in people
    assert second["id"] not in people
    p.call(
        "POST",
        path,
        instructor,
        expected=201,
        json={"request_key": str(uuid4()), "items": [{**item, "learner_id": first["id"]}]},
    )
