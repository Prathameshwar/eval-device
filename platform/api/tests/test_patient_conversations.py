"""Real scoped conversation lifecycle and cloud history, on disposable PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest
from test_llm_api import llm as llm
from test_patient_practice import setup


def start_conversation(h, token, org, connection, saved, **changes):
    h.settings.patient_remote_context_tokens = 16384
    body = {
        "request_key": str(uuid4()),
        "practice_id": saved["id"],
        "practice_revision": saved["revision"],
        "connection_id": connection["id"],
        "language": "en",
        **changes,
    }
    base = f"/organizations/{org}/patient-practice/conversations"
    return base, body, h.call("POST", base, token, json=body)


def test_context_one_call_server_history_close_and_idempotency(llm):
    h, token, user, org, llm_base, conn, body, model = llm
    _, _, saved = setup(h, token, org)
    base, start, value = start_conversation(h, token, org, conn, saved)
    context = value["context"]
    assert context["language"] == "en" and context["execution"] == "platform"
    assert "instructor" not in value["snapshot"] and value["sequence"] == 0
    assert h.call("POST", base, token, json=start) == value
    h.call("POST", base, token, json={**start, "language": "hi"}, expected=409)
    request = {
        **body,
        "conversation_id": context["conversation_id"],
        "practice_id": saved["id"],
        "practice_revision": saved["revision"],
        "language": "en",
    }
    result = h.call("POST", llm_base + "/completions", token, json=request)
    assert result["provider_calls"] == model.calls == 1
    assert result["language_pack_hash"] == context["language_pack_hash"]
    assert h.call("POST", llm_base + "/completions", token, json=request)["cached"]
    assert model.calls == 1
    assert h.sql(
        "SELECT sequence,history FROM device_platform.patient_conversations WHERE id=%s",
        (context["conversation_id"],),
    )[0] == (1, [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "hello"}])
    bad = {
        **request,
        "request_key": str(uuid4()),
        "messages": [
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "invented"},
            {"role": "user", "content": "again"},
        ],
    }
    h.call("POST", llm_base + "/completions", token, json=bad, expected=422)
    h.call("POST", base + "/" + context["conversation_id"] + "/close", token)
    h.call("POST", base + "/" + context["conversation_id"] + "/close", token)
    h.call(
        "POST", llm_base + "/completions", token, json={**request, "request_key": str(uuid4())}, expected=409
    )
    assert model.calls == 1


def test_context_scope_pack_revision_and_immutable_database_columns(llm):
    h, token, user, org, _, conn, _, _ = llm
    practice_base, selection, saved = setup(h, token, org)
    base, start, value = start_conversation(h, token, org, conn, saved)
    identity = value["context"]["conversation_id"]
    outsider, _ = h.admin("context-outsider")
    h.call("GET", base + "/" + identity, outsider, expected=404)
    h.call("POST", base + "/" + identity + "/close", outsider, expected=404)
    for column, expression in (
        ("context", 'context || \'{"language":"hi"}\'::jsonb'),
        ("snapshot", "'{}'::jsonb"),
        ("sequence", "2"),
    ):
        with pytest.raises(psycopg.errors.CheckViolation):
            h.sql(
                f"UPDATE device_platform.patient_conversations SET {column}={expression} WHERE id=%s",
                (identity,),
            )
    with pytest.raises(psycopg.errors.CheckViolation):
        h.sql("DELETE FROM device_platform.patient_conversations WHERE id=%s", (identity,))
    h.call(
        "PUT", practice_base + "/selection", token, json={**selection, "expected_revision": saved["revision"]}
    )
    h.call("GET", base + "/" + identity, token, expected=409)


def test_duplicate_start_is_atomic_and_unknown_language_is_not_enabled(llm):
    h, token, user, org, _, conn, _, _ = llm
    _, _, saved = setup(h, token, org)
    base, start, value = start_conversation(h, token, org, conn, saved)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: h.call("POST", base, token, json=start), range(2)))
    assert results == [value, value]
    for language in ("auto", "hi", "fr"):
        expected = 422
        h.call(
            "POST",
            base,
            token,
            json={**start, "request_key": str(uuid4()), "language": language},
            expected=expected,
        )
    assert h.sql("SELECT count(*) FROM device_platform.patient_conversations") == [(1,)]


@pytest.mark.parametrize("revocation", ["closed", "connection", "disabled"])
def test_start_retry_rechecks_context_authorization(llm, revocation):
    h, token, user, org, _, conn, _, model = llm
    _, _, saved = setup(h, token, org)
    base, body, value = start_conversation(h, token, org, conn, saved)
    if revocation == "closed":
        h.call("POST", base + "/" + value["context"]["conversation_id"] + "/close", token)
    elif revocation == "connection":
        h.call(
            "DELETE",
            f"/organizations/{org}/llm/connections/{conn['id']}",
            token,
            params={"expected_revision": conn["revision"]},
        )
    else:
        h.settings.llm_enabled = False
    h.call("POST", base, token, json=body, expected=503 if revocation == "disabled" else 409)
    assert model.calls == 0
