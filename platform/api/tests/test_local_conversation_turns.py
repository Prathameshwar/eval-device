"""Disposable PostgreSQL archive tests; no cloud calls."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest
from test_local_turns import local as local


def event(route, **overrides):
    current = datetime.now(UTC)
    return {
        "turn_key": str(uuid4()),
        "conversation_id": str(uuid4()),
        "sequence": 1,
        "profile_revision_id": route["profile_revision_id"],
        "configuration_hash": route["configuration_hash"],
        "connection_id": route["llm"]["connection_id"],
        "connection_revision": route["llm"]["connection_revision"],
        "model": route["llm"]["model"],
        "language": "en",
        "input_source": "text",
        "audio_mode": "none",
        "input_text": "What is your name?",
        "response_text": "My name is Alex.",
        "outcome": "completed",
        "answer_source": "plain_completion",
        "finish_reason": "stop",
        "occurred_at": current.isoformat(),
        "completed_at": current.isoformat(),
        **overrides,
    }


def setup(local):
    h, token, user, org, _, conn, route = local
    h.settings.local_history_enabled = True
    return h, token, org, f"/organizations/{org}/llm/local-conversation-turns", route


def test_exact_pair_delayed_idempotency_and_no_inference(local):
    h, token, org, base, route = setup(local)
    earlier = (datetime.now(UTC) - timedelta(hours=3)).isoformat()
    body = event(route, occurred_at=earlier, completed_at=earlier)
    first = h.call("POST", base, token, json=body)
    assert first["input_text"] == body["input_text"] and first["response_text"] == body["response_text"]
    assert first["provenance"] == "client_reported"
    assert h.call("POST", base, token, json=body) == first
    h.call("POST", base, token, expected=409, json={**body, "response_text": "Changed"})
    assert h.call("GET", base, token)["items"] == [first]
    assert h.call("GET", base + "/" + body["turn_key"], token) == first
    assert h.sql("SELECT count(*) FROM device_platform.llm_requests")[0][0] == 0
    assert h.sql("SELECT count(*) FROM device_platform.local_turns")[0][0] == 0
    assert (
        h.sql(
            "SELECT count(*) FROM device_platform.activity_events WHERE event_type=%s",
            ("llm.local_conversation.recorded",),
        )[0][0]
        == 1
    )


def test_concurrent_duplicate_and_quota_are_atomic(local):
    h, token, org, base, route = setup(local)
    body = event(route)
    with ThreadPoolExecutor(max_workers=3) as pool:
        values = list(pool.map(lambda _: h.call("POST", base, token, json=body), range(3)))
    assert len({v["id"] for v in values}) == 1
    h.settings.local_history_max_records = 2

    def send(_):
        return h.client.post(
            "/api/v1" + base, headers={"Authorization": "Bearer " + token}, json=event(route)
        ).status_code

    with ThreadPoolExecutor(max_workers=3) as pool:
        statuses = sorted(pool.map(send, range(3)))
    assert statuses == [200, 429, 429]
    assert h.sql("SELECT count(*) FROM device_platform.local_conversation_turns")[0][0] == 2


def test_disabled_invalid_oversize_and_expired_upload(local):
    h, token, org, base, route = setup(local)
    h.settings.local_history_enabled = False
    h.call("POST", base, token, expected=503, json=event(route))
    h.settings.local_history_enabled = True
    h.call("POST", base, token, expected=422, json=event(route, response_text=None))
    h.call("POST", base, token, expected=422, json=event(route, response_text="\u0905" * 11000))
    h.call("POST", base, token, expected=422, json=event(route, input_text="\u0000"))
    old = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
    h.call("POST", base, token, expected=410, json=event(route, occurred_at=old, completed_at=old))
    h.call("POST", base, token, expected=413, json=event(route, input_text="x" * 140000))
    h.call("POST", base, token, expected=422, json={**event(route), "api_key": "must never be echoed"})


def test_failed_attempt_pagination_and_expiration(local):
    h, token, org, base, route = setup(local)
    for _ in range(3):
        h.call("POST", base, token, json=event(route))
    h.call(
        "POST",
        base,
        token,
        json=event(route, outcome="cancelled", response_text=None, answer_source=None, finish_reason=None),
    )
    first = h.call("GET", base + "?limit=2", token)
    second = h.call("GET", base + "?limit=2&before=" + first["next_before"], token)
    assert len(first["items"]) == 2 and len(second["items"]) == 1
    assert len(h.call("GET", base + "?completed_only=false", token)["items"]) == 4
    # Only the disposable database owner prepares an expired row; runtime cannot amend it.
    h.sql("ALTER TABLE device_platform.local_conversation_turns DISABLE TRIGGER local_conversation_guard")
    h.sql("""UPDATE device_platform.local_conversation_turns SET
          occurred_at=now()-interval '8 days', completed_at=now()-interval '8 days',
          created_at=now()-interval '8 days', expires_at=now()-interval '1 day'""")
    h.sql("ALTER TABLE device_platform.local_conversation_turns ENABLE TRIGGER local_conversation_guard")
    assert h.call("GET", base, token)["items"] == []
    h.call("GET", base + "/" + first["items"][0]["turn_key"], token, expected=404)
    import asyncio

    from pms_api.database.session import engine_for, sessions_for
    from pms_api.worker.service import retain

    async def cleanup():
        engine = engine_for(h.settings, "retention")
        try:
            await retain(sessions_for(engine))
        finally:
            await engine.dispose()

    asyncio.run(cleanup())
    assert h.sql("SELECT count(*) FROM device_platform.local_conversation_turns")[0][0] == 0


def test_identity_and_scope_do_not_grant_platform_admin_content(local):
    h, token, org, base, route = setup(local)
    own = h.call("POST", base, token, json=event(route))
    other, _ = h.user("history-other")
    h.call("GET", base, other, expected=404)
    h.call("GET", base + "/" + own["turn_key"], other, expected=404)
    admin, _ = h.admin()
    h.call("GET", base, admin, expected=404)
    identity = h.call("GET", base + "/identity", token)
    assert identity["organization_id"] == org and identity["subject"] == "local-user"
    h.call("POST", base, token, expected=404, json=event(route, department_id=str(uuid4())))
    h.call(
        "POST",
        base,
        token,
        expected=404,
        json=event(route, practice_id=str(uuid4()), practice_revision=1, practice_snapshot_hash="a" * 64),
    )


def test_department_and_user_scope_and_storage_bytes(local):
    h, token, org, base, route = setup(local)
    dept = h.call("POST", f"/organizations/{org}/departments", token, expected=201, json={"name": "Ward"})[
        "id"
    ]
    learner, _ = h.user("history-learner")
    invite = h.call(
        "POST",
        f"/organizations/{org}/invitations",
        token,
        expected=201,
        json={"email": "history-learner@example.com", "role": "org_user"},
    )
    h.call("POST", "/invitations/accept", learner, json={"token": invite["invitation_token"]})
    h.call(
        "PATCH",
        f"/organizations/{org}/members/{invite['membership']['id']}",
        token,
        json={"department_id": dept},
    )
    own = h.call("POST", base, token, json=event(route))
    h.call("POST", base, learner, expected=404, json=event(route))
    theirs = h.call("POST", base, learner, json=event(route, department_id=dept))
    assert theirs["department_id"] == dept
    assert [r["id"] for r in h.call("GET", base, learner)["items"]] == [theirs["id"]]
    h.call("GET", base + "/" + own["turn_key"], learner, expected=404)
    assert len(h.call("GET", base + "?mine=false", token)["items"]) == 2
    h.settings.local_history_max_bytes = 1024
    h.call("POST", base, token, expected=429, json=event(route))
    h.call("PATCH", f"/organizations/{org}/departments/{dept}", token, json={"is_active": False})
    h.call("GET", base, learner, expected=409)
    assert [r["id"] for r in h.call("GET", base + "?mine=false", token)["items"]] == [own["id"]]


def test_append_only_database_guard_and_sequence_integrity(local):
    h, token, org, base, route = setup(local)
    body = event(route)
    row = h.call("POST", base, token, json=body)
    h.call("POST", base, token, expected=409, json={**body, "turn_key": str(uuid4())})
    with pytest.raises(psycopg.errors.CheckViolation):
        h.sql(
            "UPDATE device_platform.local_conversation_turns SET response_text='changed' WHERE id=%s",
            (row["id"],),
        )
    with pytest.raises(psycopg.errors.CheckViolation):
        h.sql("DELETE FROM device_platform.local_conversation_turns WHERE id=%s", (row["id"],))
