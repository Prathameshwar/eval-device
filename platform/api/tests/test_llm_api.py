import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from pms_api.integrations.llm import LLMError


class Model:
    calls = 0
    delay = 0
    failure = None

    async def close(self):
        pass

    async def health(self, *args, **kwargs):
        pass

    async def events(self, **params):
        self.calls += 1
        await asyncio.sleep(self.delay)
        if self.failure:
            raise LLMError(self.failure)
        if params["streaming"]:
            yield {"type": "delta", "text": "hello"}
        yield {
            "type": "done",
            "text": "hello",
            "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
            "finish_reason": "stop",
            "first_token_ms": 1,
            "total_ms": 2,
        }


CLOUD_URL = "https://models.example/v1"


@pytest.fixture
def llm(platform):
    """A platform-executed connection: only a cloud model is dispatched by this service.

    A model published as local is executed by the caller and never reaches /completions.
    """
    h = platform
    h.settings.llm_enabled = True
    h.settings.external_calls_enabled = True
    h.settings.llm_allowed_base_urls = [CLOUD_URL, "https://api.openai.com/v1"]
    model = Model()
    h.client.app.state.llm = model
    token, user = h.user("llm-user")
    org = h.organization(token)["id"]
    # Connection administration is platform-only; this fixture user also has
    # an explicit tenant membership for processing calls.
    h.sql("UPDATE device_platform.users SET platform_role='platform_admin' WHERE id=%s", (user["id"],))
    base = f"/organizations/{org}/llm"
    c = h.call(
        "POST",
        base + "/connections",
        token,
        expected=201,
        json={
            "name": "Qwen",
            "api_key": "private-llm-fixture-key",
            "provider": "openai_compatible",
            "base_url": CLOUD_URL,
            "model": "qwen3-4b-cloud",
            "max_tokens": 100,
        },
    )
    body = {
        "request_key": str(uuid4()),
        "connection_id": c["id"],
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": False,
    }
    return h, token, user, org, base, c, body, model


def test_llm_json_sse_idempotency_and_encryption(llm):
    h, t, u, org, base, c, body, model = llm
    assert "encrypted_credentials" not in c and "api_key" not in json.dumps(c)
    cipher = h.sql(
        "SELECT encrypted_credentials FROM device_platform.llm_connections WHERE id=%s", (c["id"],)
    )[0][0]
    assert b"private-llm-fixture-key" not in cipher
    result = h.call("POST", base + "/completions", t, json=body)
    assert result["text"] == "hello" and not result["cached"]
    assert h.call("POST", base + "/completions", t, json=body)["cached"]
    response = h.client.post(
        "/api/v1" + base + "/completions", headers=h.headers(t), json={**body, "stream": True}
    )
    assert (
        response.status_code == 200 and "event: done" in response.text and '"cached": true' in response.text
    )
    assert model.calls == 1
    changed = {**body, "messages": [{"role": "user", "content": "different"}]}
    h.call("POST", base + "/completions", t, expected=409, json=changed)
    body["request_key"] = str(uuid4())
    body["stream"] = True
    response = h.client.post("/api/v1" + base + "/completions", headers=h.headers(t), json=body)
    assert "event: delta" in response.text and response.text.index("event: delta") < response.text.index(
        "event: done"
    )
    assert h.call("GET", base + "/requests/" + body["request_key"], t)["status"] == "succeeded"
    assert h.call("GET", base + "/connections/" + c["id"] + "/status", t)["status"] == "ready"


def test_llm_tenant_role_lifecycle_and_limits(llm):
    h, t, u, org, base, c, body, model = llm
    other, _ = h.admin("outsider")
    h.call("POST", base + "/completions", other, expected=404, json=body)
    h.call("POST", base + "/completions", expected=401, json=body)
    invalid = {**body, "messages": [{"role": "system", "content": "injected"}]}
    h.call("POST", base + "/completions", t, expected=422, json=invalid)
    h.settings.llm_daily_requests = 1
    h.call("POST", base + "/completions", t, json=body)
    h.call("POST", base + "/completions", t, expected=429, json={**body, "request_key": str(uuid4())})
    h.sql(
        "UPDATE device_platform.organizations SET is_active=false, suspension_source='organization' WHERE id=%s",
        (org,),
    )
    h.call("GET", base + "/requests/" + body["request_key"], t, expected=409)
    assert model.calls == 1


def test_llm_concurrent_duplicate_and_target_capacity(llm):
    h, t, u, org, base, c, body, model = llm
    model.delay = 0.3
    # One slot makes the second distinct request contend for the same busy model server.
    h.settings.llm_cloud_concurrency = 1

    def call(payload):
        return h.client.post("/api/v1" + base + "/completions", headers=h.headers(t), json=payload)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(call, [body, body]))
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert model.calls == 1
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(call, [{**body, "request_key": str(uuid4())}, {**body, "request_key": str(uuid4())}])
        )
    assert sorted(r.status_code for r in responses) == [200, 429]


def test_llm_uncertain_failure_is_durable_and_not_retried(llm):
    h, t, u, org, base, c, body, model = llm
    model.failure = "llm_transport_unknown"
    h.call("POST", base + "/completions", t, expected=502, json=body)
    assert h.call("GET", base + "/requests/" + body["request_key"], t)["status"] == "unknown"
    h.call("POST", base + "/completions", t, expected=409, json=body)
    assert model.calls == 1


def test_llm_connection_update_and_midflight_revocation(llm):
    h, t, u, org, base, c, body, model = llm
    model.delay = 1.5
    with ThreadPoolExecutor(max_workers=1) as pool:
        work = pool.submit(h.client.post, "/api/v1" + base + "/completions", headers=h.headers(t), json=body)
        import time

        deadline = time.monotonic() + 3
        while not model.calls and time.monotonic() < deadline:
            time.sleep(0.01)
        update = {
            "name": "Qwen",
            "expected_revision": 1,
            "is_active": False,
            "provider": "openai_compatible",
            "base_url": CLOUD_URL,
            "model": "qwen3-4b-cloud",
            "max_tokens": 100,
        }
        c2 = h.call("PUT", base + "/connections/" + c["id"], t, json=update)
        assert c2["revision"] == 2
        assert work.result().status_code == 409
    assert h.sql("SELECT status FROM device_platform.llm_requests")[0][0] == "failed"
    h.call("PUT", base + "/connections/" + c["id"], t, expected=409, json=update)


def test_llm_department_narrowing_and_historical_results(llm):
    h, t, u, org, base, c, body, model = llm
    dept = h.call("POST", f"/organizations/{org}/departments", t, expected=201, json={"name": "Lab"})["id"]
    learner, _ = h.user("llm-learner")
    invite = h.call(
        "POST",
        f"/organizations/{org}/invitations",
        t,
        expected=201,
        json={"email": "llm-learner@example.com", "role": "org_user"},
    )
    h.call("POST", "/invitations/accept", learner, json={"token": invite["invitation_token"]})
    h.call("POST", base + "/completions", learner, json=body)
    h.call(
        "PATCH", f"/organizations/{org}/members/{invite['membership']['id']}", t, json={"department_id": dept}
    )
    h.call("GET", base + "/requests/" + body["request_key"], learner, expected=404)
    h.call("POST", base + "/completions", learner, expected=409, json=body)
    next_body = {**body, "request_key": str(uuid4())}
    h.call("POST", base + "/completions", learner, json=next_body)
    h.call("GET", base + "/requests/" + next_body["request_key"], learner)
    assert (
        str(
            h.sql(
                "SELECT department_id FROM device_platform.llm_requests WHERE request_key=%s",
                (next_body["request_key"],),
            )[0][0]
        )
        == dept
    )
    h.call(
        "POST",
        base + "/connections",
        learner,
        expected=403,
        json={"name": "Unauthorized", "api_key": "private-llm-fixture-key"},
    )


def test_llm_expired_lease_runtime_grants_and_retention(llm):
    import psycopg
    from sqlalchemy.engine import make_url

    h, t, u, org, base, c, body, model = llm
    stale = str(uuid4())
    h.sql(
        """INSERT INTO device_platform.llm_requests
        (id,organization_id,user_id,connection_id,connection_revision,request_key,fingerprint,target_key,
         status,reserved_tokens,reserved_total_tokens,lease_token,created_at,lease_expires_at,expires_at)
        VALUES (%s,%s,%s,%s,1,%s,%s,%s,'running',16,1024,%s,
                now()-interval '2 days',now()-interval '47 hours 59 minutes',now()-interval '1 day')""",
        (str(uuid4()), org, u["id"], c["id"], stale, "a" * 64, "b" * 64, str(uuid4())),
    )
    h.call("GET", base + "/requests/" + stale, t, expected=410)
    # Expired output cannot be fetched; recovery must also work without a returning caller.
    from pms_api.modules.llm import expiry_loop

    async def recover_once():
        task = asyncio.create_task(expiry_loop(h.client.app.state.sessions))
        await asyncio.sleep(0.15)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    h.client.portal.call(recover_once)
    assert h.sql("SELECT status,error_code FROM device_platform.llm_requests WHERE request_key=%s", (stale,))[
        0
    ] == ("unknown", "llm_lease_expired")
    assert model.calls == 0
    assert (
        h.sql("SELECT count(*) FROM device_platform.activity_events WHERE event_type='llm.request.unknown'")[
            0
        ][0]
        == 1
    )
    for url, allowed in [(h.settings.database_url, False), (h.settings.retention_database_url, True)]:
        dsn = (
            make_url(url.get_secret_value())
            .set(drivername="postgresql")
            .render_as_string(hide_password=False)
        )
        with psycopg.connect(dsn) as db:
            if allowed:
                db.execute("DELETE FROM device_platform.llm_requests WHERE request_key=%s", (stale,))
            else:
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    db.execute("DELETE FROM device_platform.llm_requests WHERE request_key=%s", (stale,))
    dsn = (
        make_url(h.settings.worker_database_url.get_secret_value())
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )
    with psycopg.connect(dsn) as db:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            db.execute("SELECT encrypted_credentials FROM device_platform.llm_connections")


def test_llm_connection_limit_serializes_concurrent_creation(llm):
    h, t, u, org, base, c, body, model = llm
    for i in range(8):
        h.call(
            "POST",
            base + "/connections",
            t,
            expected=201,
            json={"name": f"Connection {i}", "api_key": "private-llm-fixture-key"},
        )

    def create(i):
        return h.client.post(
            "/api/v1" + base + "/connections",
            headers=h.headers(t),
            json={"name": f"Last {i}", "api_key": "private-llm-fixture-key"},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(create, range(2)))
    assert sorted(r.status_code for r in responses) == [201, 409]
    assert h.sql("SELECT count(*) FROM device_platform.llm_connections")[0][0] == 10


def test_local_model_is_declared_only_and_never_executed_by_the_platform(llm):
    h, t, u, org, base, c, body, model = llm
    local = h.call(
        "POST",
        base + "/connections",
        t,
        expected=201,
        json={"name": "Local Qwen", "api_key": "private-llm-fixture-key"},
    )
    assert local["provider"] == "local_llama_cpp"
    denied = h.call(
        "POST", base + "/completions", t, expected=409, json={**body, "connection_id": local["id"]}
    )
    assert denied["error"]["code"] == "llm_local_execution_required"
    # Readiness for that model is a configuration check; whoever runs the turn verifies the server.
    assert h.call("GET", base + "/connections/" + local["id"] + "/status", t) == {
        "status": "declared",
        "model": "qwen3.5-4b-local",
        "revision": 1,
        "provider": "local_llama_cpp",
        "check": "configuration_only",
        "inference_verified": False,
        "execution": "caller",
    }
    assert model.calls == 0
    assert h.sql("SELECT count(*) FROM device_platform.llm_requests")[0][0] == 0


def test_llm_vault_rotation_preserves_secret_and_advances_revision(llm, monkeypatch):
    import base64

    from pydantic import SecretStr

    from pms_api import cli

    h, t, u, org, base, c, body, model = llm
    h.settings.credential_keys = {
        **h.settings.credential_keys,
        "next": SecretStr(base64.b64encode(b"n" * 32).decode()),
    }
    h.settings.active_credential_key = "next"
    monkeypatch.setattr(cli, "Settings", lambda: h.settings)
    h.client.portal.call(cli.rotate)
    assert h.sql(
        "SELECT revision,credential_key_id FROM device_platform.llm_connections WHERE id=%s", (c["id"],)
    )[0] == (2, "next")
    assert h.call("POST", base + "/completions", t, json=body)["text"] == "hello"
