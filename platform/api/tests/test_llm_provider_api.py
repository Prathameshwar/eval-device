import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import httpx
import pytest
from test_llm_api import llm as llm

from pms_api.integrations.llm.client import LLMClient


@pytest.mark.parametrize("provider", ["openai", "openai_compatible"])
def test_remote_encrypted_connection_json_sse_gates_and_idempotency(llm, provider):
    h, t, u, org, base, local, body, model = llm
    url = "https://api.openai.com/v1" if provider == "openai" else "https://gateway.example/v1"
    h.settings.llm_allowed_base_urls = [url]
    h.settings.external_calls_enabled = False
    secret = "sk-proj-" + ("k" * 600)
    connection = h.call(
        "POST",
        base + "/connections",
        t,
        expected=201,
        json={
            "name": "Remote",
            "provider": provider,
            "base_url": url,
            "model": "explicit-model",
            "max_tokens": 1024,
            "api_key": secret,
        },
    )
    assert secret not in json.dumps(connection) and "credential_key_id" not in connection
    body = {**body, "connection_id": connection["id"]}
    assert (
        h.call("POST", base + "/completions", t, expected=503, json=body)["error"]["code"]
        == "external_calls_disabled"
    )
    h.call("GET", base + "/connections/" + connection["id"] + "/status", t, expected=503)
    assert model.calls == 0 and h.sql("SELECT count(*) FROM device_platform.llm_requests")[0][0] == 0
    calls = []

    def handler(request):
        calls.append(request)
        assert request.headers["authorization"] == "Bearer " + secret
        if request.method == "GET":
            return httpx.Response(
                200,
                json={"id": "explicit-model"}
                if provider == "openai"
                else {"data": [{"id": "explicit-model"}]},
            )
        data = json.loads(request.content)
        if data["stream"]:
            return httpx.Response(
                200,
                content="data: "
                + json.dumps({"choices": [{"delta": {"content": "Hello"}, "finish_reason": "stop"}]})
                + "\n\ndata: [DONE]\n\n",
            )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Hello"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            },
        )

    h.client.app.state.llm = LLMClient(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    h.settings.external_calls_enabled = True
    assert h.call("GET", base + "/connections/" + connection["id"] + "/status", t)["status"] == "ready"
    result = h.call("POST", base + "/completions", t, json=body)
    assert result["text"] == "Hello" and result["usage"]["total_tokens"] == 5
    assert h.call("POST", base + "/completions", t, json=body)["cached"]
    body["request_key"] = str(uuid4())
    response = h.client.post(
        "/api/v1" + base + "/completions", headers=h.headers(t), json={**body, "stream": True}
    )
    assert "event: done" in response.text and '"usage": null' in response.text
    assert len(calls) == 3
    assert h.sql("SELECT sum(reserved_tokens) FROM device_platform.llm_requests")[0][0] == 2048
    quota_rows = h.sql(
        "SELECT reserved_total_tokens,charged_total_tokens FROM device_platform.llm_requests ORDER BY created_at"
    )
    assert quota_rows[0][1] == 5
    assert quota_rows[1][0] > 1024 and quota_rows[1][1] is None  # SSE omitted usage: retain reservation.
    rows = h.sql(
        "SELECT encrypted_credentials FROM device_platform.llm_connections WHERE id=%s", (connection["id"],)
    )
    assert secret.encode() not in rows[0][0]
    for table in ["llm_requests", "activity_events"]:
        assert secret not in json.dumps(
            h.sql("SELECT to_jsonb(t)::text FROM device_platform." + table + " t")
        )
    h.settings.llm_daily_total_tokens = 2048
    h.call("POST", base + "/completions", t, expected=429, json={**body, "request_key": str(uuid4())})
    assert len(calls) == 3
    h.settings.external_calls_enabled = False
    # Reading/replaying a completed result requires no remote call.
    assert h.call("POST", base + "/completions", t, json={**body, "stream": False})["cached"]
    h.settings.llm_allowed_base_urls = []
    h.call("POST", base + "/completions", t, expected=422, json={**body, "request_key": str(uuid4())})
    assert len(calls) == 3


def test_destination_change_requires_fresh_key_and_validation_never_echoes_secret(llm):
    h, t, u, org, base, c, body, model = llm
    update = {"name": "Remote", "expected_revision": 1, "provider": "openai", "model": "explicit"}
    result = h.call("PUT", base + "/connections/" + c["id"], t, expected=422, json=update)
    assert result["error"]["code"] == "llm_fresh_key_required"
    for secret in ["very-private\r\nInjected:key", "private token", "x" * 4097]:
        response = h.client.post(
            "/api/v1" + base + "/connections", headers=h.headers(t), json={"name": "bad", "api_key": secret}
        )
        assert response.status_code == 422 and secret[:12] not in response.text
    key = "new-destination-key"
    c2 = h.call("PUT", base + "/connections/" + c["id"], t, json={**update, "api_key": key})
    assert c2["provider"] == "openai" and c2["revision"] == 2
    assert key not in json.dumps(c2)
    # Revision and all new protocol fields remain guarded by SQL constraints.
    import psycopg

    with pytest.raises(psycopg.errors.CheckViolation):
        h.sql(
            "UPDATE device_platform.llm_connections SET token_parameter='max_tokens',revision=revision+1 WHERE id=%s",
            (c["id"],),
        )


@pytest.mark.parametrize("streaming", [False, True])
def test_expired_caller_during_generation_cannot_receive_success(llm, streaming):
    h, t, u, org, base, c, body, model = llm
    model.delay = 4
    token = h.token("llm-user", exp=int(time.time()) + 3)
    response = h.client.post(
        "/api/v1" + base + "/completions", headers=h.headers(token), json={**body, "stream": streaming}
    )
    if streaming:
        assert (
            "event: error" in response.text
            and "authentication_expired" in response.text
            and "event: done" not in response.text
        )
    else:
        assert response.status_code == 401 and response.json()["error"]["code"] == "authentication_expired"
    assert model.calls == 1
    assert h.sql("SELECT status,error_code,result FROM device_platform.llm_requests")[0] == (
        "failed",
        "authentication_expired",
        None,
    )


def test_disabling_remote_dispatch_cancels_inflight_result(llm):
    h, t, u, org, base, c, body, model = llm
    c = h.call(
        "POST",
        base + "/connections",
        t,
        expected=201,
        json={"name": "Remote", "provider": "openai", "model": "explicit", "api_key": "private-test-key"},
    )
    model.delay = 2
    h.settings.external_calls_enabled = True
    with ThreadPoolExecutor(max_workers=1) as pool:
        task = pool.submit(
            h.client.post,
            "/api/v1" + base + "/completions",
            headers=h.headers(t),
            json={**body, "connection_id": c["id"]},
        )
        deadline = time.monotonic() + 4
        while not model.calls and time.monotonic() < deadline:
            time.sleep(0.01)
        assert model.calls == 1
        h.settings.external_calls_enabled = False
        assert task.result().status_code == 503
    assert h.sql("SELECT status,error_code FROM device_platform.llm_requests")[0] == (
        "failed",
        "external_calls_disabled",
    )


def test_status_rechecks_connection_revision_after_upstream_get(llm):
    h, t, u, org, base, c, body, model = llm

    async def health(*args, **kwargs):
        h.sql(
            "UPDATE device_platform.llm_connections SET is_active=false,revision=revision+1 WHERE id=%s",
            (c["id"],),
        )
        await asyncio.sleep(0)

    model.health = health
    response = h.call("GET", base + "/connections/" + c["id"] + "/status", t, expected=409)
    assert response["error"]["code"] == "llm_connection_changed"
