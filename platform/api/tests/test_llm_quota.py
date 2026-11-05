"""Combined cloud budgets, concurrent organization admission, and conservative settlement."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from test_llm_api import llm as llm
from test_local_turns import event
from test_local_turns import local as local

from pms_api.integrations.llm.quota import reported_total, reserve_total


@pytest.mark.parametrize(
    "usage,expected",
    [
        (None, None),
        ({"completion_tokens": 2}, None),
        ({"prompt_tokens": True, "completion_tokens": 2}, None),
        ({"prompt_tokens": -1, "completion_tokens": 2}, None),
        ({"prompt_tokens": "3", "completion_tokens": 2}, None),
        ({"prompt_tokens": 1.5, "completion_tokens": 2}, None),
        ({"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 6}, None),
        ({"prompt_tokens": 2147483647, "completion_tokens": 1}, None),
        ({"prompt_tokens": 0, "completion_tokens": 0}, 0),
        ({"prompt_tokens": 3, "completion_tokens": 2}, 5),
        (
            {
                "prompt_tokens": 3,
                "completion_tokens": 2,
                "completion_tokens_details": {"reasoning_tokens": 1},
            },
            5,
        ),
    ],
)
def test_only_complete_valid_usage_settles_reservation(usage, expected):
    assert reported_total({"usage": usage}) == expected


def test_patient_reserves_one_fitted_generation_and_plain_includes_utf8_prompt():
    settings = SimpleNamespace(patient_remote_context_tokens=8192)
    params = {
        "_patient_context": {
            "budget": {
                "conversation": {
                    "prompt_tokens": 1500,
                    "reserved_output_tokens": 256,
                    "safety_margin_tokens": 128,
                }
            }
        }
    }
    assert reserve_total(params, settings) == 1884
    params["context_tokens"] = 8192
    assert reserve_total(params, settings) == 1884
    assert reserve_total({"messages": [{"content": "\u0939"}], "max_tokens": 100}, settings) == 199


def totals(h):
    return h.sql(
        "SELECT reserved_total_tokens,charged_total_tokens FROM device_platform.llm_requests ORDER BY created_at"
    )


def test_defaults_actual_usage_replay_and_shared_organization_cap(llm):
    h, t, u, org, base, conn, body, model = llm
    assert h.settings.llm_daily_total_tokens == 5000000
    assert h.settings.llm_daily_requests == 5000
    h.call("POST", base + "/completions", t, json=body)
    reserved, charged = totals(h)[0]
    assert reserved > 100 and charged == 4
    h.settings.llm_daily_total_tokens = reserved + charged
    # Exactly enough after releasing unused reservation from the first request.
    h.call("POST", base + "/completions", t, json={**body, "request_key": str(uuid4())})
    assert totals(h) == [(reserved, 4), (reserved, 4)]
    other, _ = h.user("quota-colleague")
    invitation = h.call(
        "POST",
        f"/organizations/{org}/invitations",
        t,
        expected=201,
        json={"email": "quota-colleague@example.com", "role": "org_user"},
    )
    h.call("POST", "/invitations/accept", other, json={"token": invitation["invitation_token"]})
    # A different organization member spends the same pool.
    rejected = h.call(
        "POST", base + "/completions", other, expected=429, json={**body, "request_key": str(uuid4())}
    )
    assert rejected["error"]["code"] == "llm_daily_limit"
    assert h.call("POST", base + "/completions", t, json=body)["cached"]
    assert model.calls == 2 and len(totals(h)) == 2
    with pytest.raises(psycopg.errors.CheckViolation):
        h.sql("UPDATE device_platform.llm_requests SET charged_total_tokens=0")
    with pytest.raises(psycopg.errors.CheckViolation):
        h.sql("UPDATE device_platform.llm_requests SET reserved_total_tokens=0")
    # Other organizations have independent allowances.
    other_org = h.organization(other, name="Independent quota")["id"]
    other_base = f"/organizations/{other_org}/llm"
    other_conn = h.call(
        "POST",
        other_base + "/connections",
        t,
        expected=201,
        json={
            "name": "Other cloud",
            "provider": "openai_compatible",
            "base_url": conn["base_url"],
            "model": conn["model"],
            "max_tokens": 100,
            "api_key": "quota-fixture-key",
        },
    )
    h.call(
        "POST",
        other_base + "/completions",
        other,
        json={**body, "connection_id": other_conn["id"], "request_key": str(uuid4())},
    )


def test_concurrent_cloud_requests_cannot_spend_same_remaining_tokens(llm):
    h, t, u, org, base, conn, body, model = llm
    h.call("POST", base + "/completions", t, json=body)
    reserved, charged = totals(h)[0]
    h.settings.llm_daily_total_tokens = reserved + charged
    model.delay = 0.3
    h.settings.llm_cloud_concurrency = 4

    def submit(_):
        return h.client.post(
            "/api/v1" + base + "/completions",
            headers=h.headers(t),
            json={**body, "request_key": str(uuid4())},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(submit, range(2)))
    assert sorted(r.status_code for r in responses) == [200, 429]
    assert next(r for r in responses if r.status_code == 429).json()["error"]["code"] == "llm_daily_limit"
    assert model.calls == 2


def test_failed_unknown_and_missing_usage_keep_reservations(llm):
    h, t, u, org, base, conn, body, model = llm
    model.failure = "llm_transport_unknown"
    h.call("POST", base + "/completions", t, expected=502, json=body)
    reserve, charge = totals(h)[0]
    assert reserve > 100 and charge is None
    h.settings.llm_daily_total_tokens = reserve
    assert (
        h.call("POST", base + "/completions", t, expected=429, json={**body, "request_key": str(uuid4())})[
            "error"
        ]["code"]
        == "llm_daily_limit"
    )
    assert model.calls == 1


def test_reset_uses_utc_admission_day_and_request_limit_is_distinct(llm, monkeypatch):
    h, t, u, org, base, conn, body, model = llm
    h.call("POST", base + "/completions", t, json=body)
    h.settings.llm_daily_requests = 1
    assert (
        h.call("POST", base + "/completions", t, expected=429, json={**body, "request_key": str(uuid4())})[
            "error"
        ]["code"]
        == "llm_daily_request_limit"
    )
    tomorrow = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    monkeypatch.setattr("pms_api.modules.llm.now", lambda: tomorrow)
    h.call("POST", base + "/completions", t, json={**body, "request_key": str(uuid4())})
    assert model.calls == 2


def test_local_turns_ignore_online_daily_request_and_token_limits(local):
    h, t, u, org, path, conn, route = local
    h.settings.llm_daily_requests = 1
    h.settings.llm_daily_total_tokens = 512
    for _ in range(3):
        h.call("POST", path, t, json=event(route, prompt_tokens=1000000, completion_tokens=1000000))
    assert h.sql("SELECT count(*) FROM device_platform.local_turns")[0][0] == 3
    assert h.sql("SELECT count(*) FROM device_platform.llm_requests")[0][0] == 0
