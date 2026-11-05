"""A laptop reports the turns it ran on its own local model; the platform only counts them.

These records exist so training activity stays visible when the model never leaves the
laptop. They must therefore carry no prompt, transcript or answer, and they must never look
like something the platform could replay.
"""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest

SPOKEN = "My chest has been hurting since this morning."


@pytest.fixture
def local(platform):
    h = platform
    h.settings.llm_enabled = True
    token, user = h.user("local-user")
    org = h.organization(token)["id"]
    platform_admin, _ = h.admin("local-model-admin")
    conn = h.call(
        "POST",
        f"/organizations/{org}/llm/connections",
        platform_admin,
        expected=201,
        json={"name": "Local Qwen", "api_key": "private-local-key"},
    )
    assert conn["provider"] == "local_llama_cpp"
    route = h.call(
        "POST", f"/organizations/{org}/model-profiles", platform_admin, json={"llm_connection_id": conn["id"]}
    )
    assert route["llm"]["execution"] == "caller" and route["llm"]["local_port"] == 8787
    return h, token, user, org, f"/organizations/{org}/llm/local-turns", conn, route


def event(route, **overrides):
    """The metadata a completed two-call patient turn reports."""
    return {
        "turn_key": str(uuid4()),
        "profile_revision_id": route["profile_revision_id"],
        "configuration_hash": route["configuration_hash"],
        "connection_id": route["llm"]["connection_id"],
        "connection_revision": route["llm"]["connection_revision"],
        "practice_id": str(uuid4()),
        "practice_revision": 1,
        "practice_snapshot_hash": "a" * 64,
        "language": "en",
        "answer_source": "patient_voice",
        "routing_status": "matched",
        "kind": "topic",
        "topics": ["chest_pain"],
        "provider_calls": 2,
        "finish_reason": "stop",
        "prompt_tokens": 812,
        "completion_tokens": 24,
        "first_token_ms": 140,
        "total_ms": 1600,
        "occurred_at": (datetime.now(UTC) - timedelta(seconds=2)).isoformat(),
        **overrides,
    }


def test_local_turn_is_recorded_without_text_and_cannot_be_amended(local):
    h, t, u, org, turns, conn, route = local
    body = event(route)
    row = h.call("POST", turns, t, json=body)
    assert row["turn_key"] == body["turn_key"]
    assert (row["answer_source"], row["topics"], row["provider_calls"]) == (
        "patient_voice",
        ["chest_pain"],
        2,
    )
    assert h.call("GET", turns, t)["items"] == [row]
    # Nowhere to put the words: the schema refuses anything it did not ask for.
    for extra in [{"answer": SPOKEN}, {"transcript": SPOKEN}, {"messages": [{"role": "user"}]}]:
        h.call("POST", turns, t, expected=422, json={**event(route), **extra})
    columns = {
        name
        for (name,) in h.sql(
            """SELECT column_name FROM information_schema.columns
               WHERE table_schema='device_platform' AND table_name='local_turns'"""
        )
    }
    assert not columns & {"prompt", "messages", "transcript", "answer", "text", "result", "request_key"}
    assert SPOKEN not in json.dumps(h.sql("SELECT to_jsonb(r)::text FROM device_platform.local_turns r"))
    # Nothing here was executed by this service, so nothing here is resumable or repairable.
    assert h.sql("SELECT count(*) FROM device_platform.llm_requests")[0][0] == 0
    with pytest.raises(psycopg.errors.CheckViolation):
        h.sql("UPDATE device_platform.local_turns SET total_ms=1 WHERE id=%s", (row["id"],))
    with pytest.raises(psycopg.errors.CheckViolation):
        h.sql("DELETE FROM device_platform.local_turns WHERE id=%s", (row["id"],))
    assert (
        h.sql(
            "SELECT count(*) FROM device_platform.activity_events WHERE event_type=%s",
            ("llm.local_turn.recorded",),
        )[0][0]
        == 1
    )


def test_repeated_report_of_one_turn_records_it_once(local):
    h, t, u, org, turns, conn, route = local
    body = event(route)
    first = h.call("POST", turns, t, json=body)
    # A laptop that loses the response retries; the turn still happened exactly once.
    assert h.call("POST", turns, t, json=body) == first
    h.call("POST", turns, t, expected=409, json={**body, "total_ms": 9000})
    assert h.sql("SELECT total_ms FROM device_platform.local_turns")[0][0] == body["total_ms"]
    other, _ = h.user("second-local-user")
    invite = h.call(
        "POST",
        f"/organizations/{org}/invitations",
        t,
        expected=201,
        json={"email": "second-local-user@example.com", "role": "org_user"},
    )
    h.call("POST", "/invitations/accept", other, json={"token": invite["invitation_token"]})
    conflict = h.call("POST", turns, other, expected=409, json=body)
    assert conflict["error"]["code"] == "idempotency_conflict"
    assert h.sql("SELECT count(*) FROM device_platform.local_turns")[0][0] == 1


def test_single_call_conversation_is_stored_and_database_checks_hold(local):
    from test_patient_practice import setup

    h, token, user, org, turns, conn, route = local
    _, _, practice = setup(h, token, org)
    body = event(
        route,
        practice_id=practice["id"],
        practice_revision=practice["revision"],
        answer_source="patient_conversation",
        policy_version="patient-conversation-v1",
        provider_calls=1,
        routing_status=None,
        kind=None,
        topics=[],
    )
    saved = h.call("POST", turns, token, json=body)
    assert saved["answer_source"] == "patient_conversation"
    assert saved["policy_version"] == "patient-conversation-v1" and saved["provider_calls"] == 1
    assert h.call("POST", turns, token, json=body) == saved
    # Exercise the database checks independently of Pydantic, retaining tenant references.
    for fragment in (
        "'provider_calls',2",
        "'policy_version',NULL",
        "'kind','topic'",
        "'finish_reason','length'",
    ):
        with pytest.raises(psycopg.errors.CheckViolation):
            h.sql(
                "INSERT INTO device_platform.local_turns SELECT (jsonb_populate_record(NULL::device_platform.local_turns, "
                "to_jsonb(t)||jsonb_build_object('id',gen_random_uuid(),'turn_key',gen_random_uuid(),"
                + fragment
                + "))).* FROM device_platform.local_turns t WHERE id=%s",
                (saved["id"],),
            )
    missing = event(
        route,
        **{
            key: body[key]
            for key in (
                "answer_source",
                "policy_version",
                "provider_calls",
                "routing_status",
                "kind",
                "topics",
            )
        },
    )
    h.call("POST", turns, token, expected=404, json=missing)


def test_a_platform_executed_turn_cannot_be_reported_as_local(local):
    h, t, u, org, turns, conn, route = local
    platform_admin, _ = h.admin("cloud-turn-model-admin")
    url = "https://models.example/v1"
    h.settings.llm_allowed_base_urls = [url]
    cloud = h.call(
        "POST",
        f"/organizations/{org}/llm/connections",
        platform_admin,
        expected=201,
        json={
            "name": "Cloud Qwen",
            "api_key": "private-cloud-key",
            "provider": "openai_compatible",
            "base_url": url,
            "model": "qwen3-4b-cloud",
        },
    )
    cloud_route = h.call(
        "POST",
        f"/organizations/{org}/model-profiles",
        platform_admin,
        json={
            "llm_connection_id": cloud["id"],
            "profile_id": route["profile_id"],
            "expected_revision_id": route["profile_revision_id"],
        },
    )
    assert cloud_route["llm"]["execution"] == "platform"
    denied = h.call(
        "POST",
        turns,
        t,
        expected=409,
        json=event(
            cloud_route,
            connection_id=cloud["id"],
            connection_revision=cloud_route["llm"]["connection_revision"],
        ),
    )
    assert denied["error"]["code"] == "llm_local_execution_required"
    assert h.sql("SELECT count(*) FROM device_platform.local_turns")[0][0] == 0


def test_report_must_name_the_route_that_actually_ran_the_turn(local):
    h, t, u, org, turns, conn, route = local
    platform_admin, _ = h.admin("spare-turn-model-admin")
    spare = h.call(
        "POST",
        f"/organizations/{org}/llm/connections",
        platform_admin,
        expected=201,
        json={"name": "Spare local", "api_key": "private-local-key"},
    )
    mismatch = h.call("POST", turns, t, expected=422, json=event(route, connection_id=spare["id"]))
    assert mismatch["error"]["code"] == "invalid_request"
    outsider, _ = h.user("other-org-user")
    h.organization(outsider, name="Other organization")
    h.call("POST", turns, outsider, expected=404, json=event(route))
    h.call("POST", turns, t, expected=404, json=event(route, profile_revision_id=str(uuid4())))
    for occurred in [
        datetime.now(UTC) - timedelta(hours=2),
        datetime.now(UTC) + timedelta(minutes=30),
    ]:
        stale = h.call("POST", turns, t, expected=422, json=event(route, occurred_at=occurred.isoformat()))
        assert stale["error"]["code"] == "invalid_request"
    assert h.sql("SELECT count(*) FROM device_platform.local_turns")[0][0] == 0
    # A laptop clock a minute fast still reports a turn that really happened; it lands at arrival.
    skewed = datetime.now(UTC) + timedelta(minutes=1)
    row = h.call("POST", turns, t, json=event(route, occurred_at=skewed.isoformat()))
    assert datetime.fromisoformat(row["occurred_at"]) < skewed


@pytest.mark.parametrize(
    "overrides",
    [
        # A plain question has no case, so it reports no routing outcome and one call.
        {"practice_id": None},
        {"practice_id": None, "practice_revision": None, "practice_snapshot_hash": None},
        {"answer_source": "plain_completion"},
        # Generated patient wording is the routing call plus the spoken call.
        {"provider_calls": 1},
        # A deflection answers a question no topic covers, so it never reports one.
        {"answer_source": "patient_deflection"},
        {
            "answer_source": "patient_deflection",
            "topics": [],
            "routing_status": "backchannel",
            "kind": "backchannel",
        },
        # Three calls can be valid after routing repair and evidence review.
        # Routing, one repair and the spoken call are every completion a turn can make.
        {"provider_calls": 4},
        # A matched routing outcome, a routed topic and a case answer cannot disagree.
        {"answer_source": "case_boundary", "provider_calls": 1},
        {"routing_status": "unknown", "provider_calls": 1, "answer_source": "scripted_case"},
        {"topics": [], "provider_calls": 1, "answer_source": "scripted_case"},
        # Routed topic ids are distinct authored identifiers.
        {"topics": ["chest_pain", "chest_pain"]},
        {"topics": ["chest pain"]},
        {"topics": ["a", "b", "c", "d"]},
        {"answer_source": "handwritten"},
        {"configuration_hash": "A" * 64},
        {"provider_calls": True},
        {"total_ms": -1},
    ],
)
def test_an_incoherent_report_is_refused(local, overrides):
    h, t, u, org, turns, conn, route = local
    h.call("POST", turns, t, expected=422, json=event(route, **overrides))
    assert h.sql("SELECT count(*) FROM device_platform.local_turns")[0][0] == 0


def test_every_authored_outcome_of_the_shared_pipeline_can_be_reported(local):
    h, t, u, org, turns, conn, route = local
    # The fact guard rejected generated wording after the spoken call ran: two calls, authored text.
    guarded = h.call("POST", turns, t, json=event(route, answer_source="scripted_case"))
    assert (guarded["answer_source"], guarded["provider_calls"]) == ("scripted_case", 2)
    # An objective topic, or an authored-only profile, answers after routing alone.
    literal = h.call("POST", turns, t, json=event(route, answer_source="scripted_case", provider_calls=1))
    assert literal["provider_calls"] == 1
    # An unusable routing object was repaired, and the spoken call then ran and was rejected.
    repaired = h.call("POST", turns, t, json=event(route, answer_source="scripted_case", provider_calls=3))
    assert repaired["provider_calls"] == 3
    for status, kind, source in [
        ("backchannel", "backchannel", "case_backchannel"),
        ("command", "command", "case_command_ack"),
        ("boundary", "boundary", "case_boundary"),
        ("unknown", "unknown", "case_clarification"),
        ("invalid", "unknown", "routing_invalid"),
    ]:
        row = h.call(
            "POST",
            turns,
            t,
            json=event(
                route,
                routing_status=status,
                kind=kind,
                topics=[],
                provider_calls=1,
                answer_source=source,
            ),
        )
        assert (row["routing_status"], row["answer_source"]) == (status, source)
    # An unroutable question answered in character: no topic, no fact, two or three calls.
    for status, calls in (("unknown", 2), ("invalid", 3)):
        spoken = h.call(
            "POST",
            turns,
            t,
            json=event(
                route,
                routing_status=status,
                kind="unknown",
                topics=[],
                provider_calls=calls,
                answer_source="patient_deflection",
            ),
        )
        assert (spoken["answer_source"], spoken["provider_calls"]) == ("patient_deflection", calls)
    assert h.sql("SELECT count(*) FROM device_platform.local_turns")[0][0] == 10


def test_plain_local_turn_without_a_case_is_recorded(local):
    h, t, u, org, turns, conn, route = local
    row = h.call(
        "POST",
        turns,
        t,
        json=event(
            route,
            practice_id=None,
            practice_revision=None,
            practice_snapshot_hash=None,
            routing_status=None,
            kind=None,
            topics=[],
            provider_calls=1,
            answer_source="plain_completion",
        ),
    )
    assert row["practice_id"] is None and row["routing_status"] is None and row["topics"] == []


def test_local_turns_are_scoped_by_role_and_department(local):
    h, t, u, org, turns, conn, route = local
    dept = h.call("POST", f"/organizations/{org}/departments", t, expected=201, json={"name": "Ward"})["id"]
    learner, _ = h.user("local-learner")
    invite = h.call(
        "POST",
        f"/organizations/{org}/invitations",
        t,
        expected=201,
        json={"email": "local-learner@example.com", "role": "org_user"},
    )
    membership = h.call("POST", "/invitations/accept", learner, json={"token": invite["invitation_token"]})
    assert membership
    h.call(
        "PATCH",
        f"/organizations/{org}/members/{invite['membership']['id']}",
        t,
        json={"department_id": dept},
    )
    mine = h.call("POST", turns, t, json=event(route))
    theirs = h.call("POST", turns, learner, json=event(route))
    assert (
        str(h.sql("SELECT department_id FROM device_platform.local_turns WHERE id=%s", (theirs["id"],))[0][0])
        == dept
    )
    # A learner sees their own turns; a department narrows an admin's view to that department.
    assert [row["id"] for row in h.call("GET", turns, learner)["items"]] == [theirs["id"]]
    assert {row["id"] for row in h.call("GET", turns, t)["items"]} == {mine["id"], theirs["id"]}
    h.call("POST", turns, learner, expected=404, json=event(route, department_id=str(uuid4())))
    # An organization-wide actor may attribute a turn only to an existing, active department here.
    unknown = h.call("POST", turns, t, expected=404, json=event(route, department_id=str(uuid4())))
    assert unknown["error"]["code"] == "not_found"
    h.call("PATCH", f"/organizations/{org}/departments/{dept}", t, json={"is_active": False})
    inactive = h.call("POST", turns, t, expected=409, json=event(route, department_id=dept))
    assert inactive["error"]["code"] == "department_inactive"
