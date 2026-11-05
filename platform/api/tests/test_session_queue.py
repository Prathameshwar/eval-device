"""Queue ownership, atomic handoff, deadline and cancellation on disposable PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from test_device_model_review import assign
from test_local_conversation_turns import event


@pytest.fixture
def queue_device(platform):
    p = platform
    instructor, learner = p.user("queue-instructor")
    admin, _ = p.admin()
    org = p.organization(instructor, plan="advanced")["id"]
    p.grant_capability(instructor, org, learner["id"], "org.training.instruct")
    device = p.device(instructor, org)
    token = p.enroll(instructor, org, device["id"])
    models = p.call("GET", "/platform/runtime-models", admin)["items"]
    assign(p, admin, device["id"], models)
    p.settings.llm_enabled = p.settings.local_history_enabled = True
    options = p.call("GET", f"/organizations/{org}/patient-practice/scenario-options", token)
    case = options["items"][0]
    path = f"/organizations/{org}/devices/{device['id']}/session-queue"
    item = {"learner_id": learner["id"], "scenario_id": case["id"], "language": "en", "duration_seconds": 300}
    return p, instructor, admin, org, device, token, path, item, case


def test_queue_order_pause_idempotency_expiry_and_scope(queue_device, monkeypatch):
    p, instructor, admin, org, device, token, path, item, case = queue_device
    body = {"request_key": str(uuid4()), "items": [item, item, item]}
    queue = p.call("POST", path, instructor, expected=201, json=body)
    assert len(queue["items"]) == 3
    assert p.call("POST", path, instructor, expected=201, json=body)["items"] == queue["items"]
    p.call("POST", path, instructor, expected=409, json={**body, "items": [item]})
    p.call("GET", path, token, expected=403)
    p.call("GET", path, admin, expected=404)
    outsider, user = p.user("unrelated-user")
    p.call(
        "POST",
        path,
        instructor,
        expected=403,
        json={"request_key": str(uuid4()), "items": [{**item, "learner_id": user["id"]}]},
    )
    ids = [row["id"] for row in queue["items"]]
    order = {"expected_revision": queue["revision"], "order": ids[::-1], "paused": True}
    paused = p.call("PUT", path, instructor, json=order)
    p.call("PUT", path, instructor, json=order, expected=409)
    runtime = {"runtime_id": str(uuid4())}
    poll = {**runtime, "runtime_state": "idle"}
    assert p.call("POST", "/device/session-queue/poll", token, json=poll)["next"] is None
    p.call("POST", f"/device/session-queue/{ids[-1]}/begin", token, json=runtime, expected=409)
    resumed = p.call(
        "PUT", path, instructor, json={**order, "expected_revision": paused["revision"], "paused": False}
    )
    first = p.call("POST", "/device/session-queue/poll", token, json=poll)["next"]
    assert first["id"] == ids[-1]
    p.call("POST", f"/device/session-queue/{ids[0]}/begin", token, json=runtime, expected=409)
    edited = p.call(
        "PUT",
        path + "/" + ids[-1],
        instructor,
        json={**item, "duration_seconds": 60, "expected_revision": resumed["revision"]},
    )
    assert edited["items"][0]["expires_at"] == first["expires_at"]
    p.call("POST", path + "/" + ids[1] + "/end", instructor)
    assert len(p.call("GET", path, instructor)["items"]) == 2
    from pms_api.modules import session_queue

    future = datetime.fromisoformat(first["created_at"]) + timedelta(hours=24, seconds=1)
    monkeypatch.setattr(session_queue, "now", lambda: future)
    expired = p.call("GET", path, instructor)
    assert expired["items"] == []
    assert sum(row["status"] == "expired" for row in expired["history"]) == 2
    p.call("POST", f"/device/session-queue/{ids[-1]}/begin", token, json=runtime, expected=409)


def test_assigned_conversation_web_stop_and_standalone(queue_device):
    p, instructor, admin, org, device, token, path, item, case = queue_device
    queue = p.call(
        "POST", path, instructor, expected=201, json={"request_key": str(uuid4()), "items": [item, item]}
    )
    first, second = [row["id"] for row in queue["items"]]
    base = f"/organizations/{org}/patient-practice"
    selected = p.call(
        "PUT",
        base + "/scenario-selection",
        token,
        json={"expected_revision": 0, "scenario_id": case["id"], "language": "en", "vitals": case["vitals"]},
    )["selection"]
    route = p.call("GET", f"/organizations/{org}/model-config", token)
    start = {
        "request_key": str(uuid4()),
        "practice_id": selected["id"],
        "practice_revision": selected["revision"],
        "connection_id": route["llm"]["connection_id"],
        "language": "en",
        "profile_revision_id": route["profile_revision_id"],
        "configuration_hash": route["configuration_hash"],
    }
    standalone = p.call("POST", base + "/conversations", token, json=start)
    runtime = {"runtime_id": str(uuid4())}
    p.call("POST", f"/device/session-queue/{first}/begin", token, json=runtime, expected=409)
    p.call("POST", base + "/conversations/" + standalone["context"]["conversation_id"] + "/close", token)
    active = p.call("POST", f"/device/session-queue/{first}/begin", token, json=runtime)
    assert active["status"] == "active"
    p.call(
        "POST", f"/device/session-queue/{first}/begin", token, json={"runtime_id": str(uuid4())}, expected=409
    )
    p.call("POST", f"/device/session-queue/{second}/begin", token, json=runtime, expected=409)
    p.call("POST", base + "/conversations", token, json={**start, "request_key": str(uuid4())}, expected=409)
    conversation = p.call(
        "POST",
        base + "/conversations",
        token,
        json={**start, "request_key": str(uuid4()), "assigned_session_id": first},
    )
    cid = conversation["context"]["conversation_id"]
    context = conversation["context"]
    record = event(
        route,
        department_id=None,
        conversation_id=cid,
        practice_id=selected["id"],
        practice_revision=selected["revision"],
        practice_snapshot_hash=context["case_snapshot_hash"],
        answer_source="patient_conversation",
        policy_version="patient-conversation-v1",
        context_ref={
            key: context[key]
            for key in ("conversation_id", "language_pack_version", "language_pack_hash", "compiler_version")
        },
    )
    p.call("POST", f"/organizations/{org}/llm/local-conversation-turns", token, json=record)
    assert (
        str(
            p.sql(
                "SELECT assigned_session_id FROM device_platform.patient_conversations WHERE id=%s", (cid,)
            )[0][0]
        )
        == first
    )
    stopped = p.call("POST", path + "/" + first + "/end", instructor)
    assert stopped["items"][0]["status"] == "stopping"
    p.call("GET", base + "/conversations/" + cid, token, expected=409)
    p.call("POST", f"/device/session-queue/{first}/finish", token, json={**runtime, "outcome": "completed"})
    assert (
        p.call("POST", "/device/session-queue/poll", token, json={**runtime, "runtime_state": "idle"})[
            "next"
        ]["id"]
        == second
    )
    result = p.call("GET", f"/organizations/{org}/practice-sessions/{first}", instructor)
    assert result["archive_id"] == cid
    assert result["session"]["learner_id"] == item["learner_id"]
    assert result["messages"] == [
        {"role": "user", "content": record["input_text"]},
        {"role": "assistant", "content": record["response_text"]},
    ]
    # One merged history includes the two assignments and the earlier standalone
    # capture, with no duplicate row for an assigned archive.
    combined = f"/organizations/{org}/session-history"
    merged = []
    cursor = None
    for _ in range(4):
        response = p.call(
            "GET", combined, instructor, params={"limit": 1, **({"cursor": cursor} if cursor else {})}
        )
        merged.extend(response["items"])
        cursor = response["next_cursor"]
        if cursor is None:
            break
    assert len(merged) == 3 and len({(row["kind"], row["id"]) for row in merged}) == 3
    assigned = next(row for row in merged if row["id"] == first)
    assert assigned["session"]["status"] == "completed" and assigned["archive"]["id"] == cid
    assert assigned["archive"]["sync_status"] == "pending" and assigned["archive"]["expected_items"] is None
    assert any(row["kind"] == "standalone" and row["session"] is None for row in merged)
    assert next(row for row in merged if row["id"] == second)["archive"] is None
    p.call("GET", combined, instructor, params={"cursor": "forged"}, expected=422)
    p.call("GET", combined, admin, expected=404)
    outsider, _ = p.user("combined-history-outsider")
    p.call("GET", combined, outsider, expected=404)
    p.call("GET", f"/organizations/{org}/practice-sessions/{first}", admin, expected=404)
    p.call("POST", path + "/" + second + "/end", instructor)
    p.call("POST", base + "/conversations", token, json={**start, "request_key": str(uuid4())})


def test_concurrent_begins_and_absolute_deadline(queue_device, monkeypatch):
    p, instructor, admin, org, device, token, path, item, case = queue_device
    queue = p.call(
        "POST", path, instructor, expected=201, json={"request_key": str(uuid4()), "items": [item]}
    )
    row = queue["items"][0]
    from pms_api.modules import session_queue

    expiry = datetime.fromisoformat(row["expires_at"])
    monkeypatch.setattr(session_queue, "now", lambda: expiry - timedelta(seconds=5))

    def begin(_):
        return p.client.post(
            "/api/v1/device/session-queue/" + row["id"] + "/begin",
            headers={"Authorization": "Bearer " + token},
            json={"runtime_id": str(uuid4())},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(begin, range(2))) == [200, 409]
    active = p.call("GET", path, instructor)["items"][0]
    assert active["expires_at"] == row["expires_at"]
    monkeypatch.setattr(session_queue, "now", lambda: expiry + timedelta(seconds=1))
    state = p.call("GET", path, instructor)
    assert not state["items"] and state["history"][0]["status"] == "expired"
