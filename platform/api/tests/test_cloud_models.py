import asyncio
import io
import json
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError
from test_llm_api import llm as llm
from test_patient_practice import setup

from pms_api.core.common import AppError
from pms_api.integrations.llm.capabilities import ModelOptions, aggregate_usage
from pms_api.integrations.llm.client import LLMClient
from pms_api.integrations.llm.policy import endpoint
from pms_api.integrations.whisper_cloud import transcribe, wav_info
from pms_api.modules.llm_schemas import ConnectionCreate

AZURE = "https://alex-fixture.openai.azure.com/openai/v1"


def wav(seconds=0.1, rate=16000):
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        audio.writeframes(b"\x01\x00" * int(seconds * rate))
    return output.getvalue()


def test_model_capability_validation_and_usage():
    with pytest.raises(ValidationError):
        ModelOptions(model_family="gpt_5_reasoning", temperature=0)
    with pytest.raises(ValidationError):
        ModelOptions(model_family="gpt_4_1", reasoning_effort="medium")
    options = ModelOptions(model_family="gpt_5_reasoning", reasoning_effort="none", context_tokens=8192)
    conn = ConnectionCreate(
        provider="azure_openai",
        base_url=AZURE,
        model="patient-deployment",
        name="Azure",
        api_key="fixture",
        model_options=options,
    )
    assert conn.token_parameter == "max_completion_tokens"
    assert endpoint(AZURE, [], "azure_openai", [AZURE]) == AZURE
    with pytest.raises(AppError):
        endpoint("https://other.example/openai/v1", [], "azure_openai", ["https://other.example/openai/v1"])
    value = {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
        "completion_tokens_details": {"reasoning_tokens": 3},
    }
    assert aggregate_usage({"usage": value}, {"usage": value})["total_tokens"] == 30
    assert aggregate_usage({"usage": value}, {"usage": None}) is None


@pytest.mark.parametrize("key", ["line\nbreak", "space key", "unicode-\u0939"])
def test_whisper_rejects_invalid_header_credentials(key):
    from pms_api.modules.configuration import validate_connection

    with pytest.raises(AppError, match="ASCII"):
        validate_connection(
            "azure",
            "azure_openai_whisper",
            "api_key",
            {"endpoint": AZURE, "deployment": "speech"},
            {"api_key": key},
        )


@pytest.mark.parametrize("streaming", [False, True])
async def test_azure_chat_parameters_and_annotations(streaming):
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        if streaming:
            return httpx.Response(
                200,
                content='data: {"choices":[],"prompt_filter_results":[]}\n\n'
                'data: {"choices":[{"delta":{"content":"Hello"},"finish_reason":"stop"}]}\n\n'
                "data: [DONE]\n\n",
            )
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "Hello"}, "finish_reason": "stop"}]}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = [
            event
            async for event in LLMClient(client=http).events(
                base_url=AZURE,
                provider="azure_openai",
                model="custom-deployment",
                key="fixture",
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=1024,
                token_parameter="max_completion_tokens",
                reasoning_effort="none",
                streaming=streaming,
            )
        ]
    assert result[-1]["text"] == "Hello"
    assert seen[0]["model"] == "custom-deployment" and seen[0]["reasoning_effort"] == "none"
    assert seen[0]["store"] is False and "temperature" not in seen[0] and "max_tokens" not in seen[0]


@pytest.mark.parametrize("language", ["en", "hi", "auto"])
@pytest.mark.parametrize("api_version", [None, "2024-06-01"])
async def test_whisper_multipart_and_language(language, api_version):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"text": "मुझे दर्द है"})

    settings = SimpleNamespace(
        llm_allowed_ports=[],
        llm_allowed_base_urls=[AZURE],
        external_calls_enabled=True,
        provider_timeout_seconds=5,
    )
    connection = SimpleNamespace(settings={"endpoint": AZURE, "deployment": "speech-deployment"})
    if api_version:
        connection.settings["api_version"] = api_version
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await transcribe(
            LLMClient(client=http), settings, connection, "fixture", wav(), language, uuid4()
        )
    assert result["text"] == "मुझे दर्द है" and len(seen) == 1
    if api_version:
        assert seen[0].url.path == "/openai/deployments/speech-deployment/audio/transcriptions"
        assert dict(seen[0].url.params) == {"api-version": api_version}
        assert b'name="model"' not in seen[0].content
    else:
        assert seen[0].url.path == "/openai/v1/audio/transcriptions"
        assert not seen[0].url.query
        assert b"speech-deployment" in seen[0].content
    assert b'name="file"' in seen[0].content
    assert seen[0].headers["api-key"] == "fixture"
    assert (b'name="language"' in seen[0].content) == (language != "auto")


def test_wav_limits_and_truncation():
    assert wav_info(wav(), 30) == 100
    for data in (b"invalid", wav(rate=8000), wav()[:-20], wav(2)):
        with pytest.raises(AppError):
            wav_info(data, 1)


def configure(llm, monkeypatch, cloud=True):
    p, token, _, org, base, local, body, model = llm
    p.settings.external_calls_enabled = True
    p.settings.speech_enabled = True
    p.settings.llm_allowed_base_urls = [AZURE]
    admin, _ = p.admin("cloud-platform-admin")
    current = p.call("GET", "/platform/settings", admin)
    p.call(
        "PATCH",
        "/platform/settings",
        admin,
        json={"expected_version": current["configuration_version"], "enabled_providers": ["aws", "azure"]},
    )

    async def validate(*args, **kwargs):
        return True

    monkeypatch.setattr("pms_api.integrations.whisper_cloud.AzureWhisperProvider.validate", validate)
    remote = p.call(
        "POST",
        base + "/connections",
        token,
        expected=201,
        json={
            "name": "Cloud LLM",
            "provider": "azure_openai",
            "base_url": AZURE,
            "model": "patient-deployment",
            "api_key": "fixture-cloud-key",
            "max_tokens": 4096,
            "model_options": {
                "model_family": "gpt_5_reasoning",
                "reasoning_effort": "none",
                "context_tokens": 16384,
            },
        },
    )
    speech = p.call(
        "POST",
        f"/organizations/{org}/connections",
        token,
        expected=201,
        json={
            "name": "Cloud speech",
            "provider": "azure",
            "connection_type": "azure_openai_whisper",
            "auth_mode": "api_key",
            "settings": {"endpoint": AZURE, "deployment": "speech-deployment"},
            "credentials": {"api_key": "fixture-speech-key"},
        },
    )
    p.call(
        "POST",
        f"/organizations/{org}/connections/{speech['id']}/validate",
        token,
        json={"operation": "audio.transcribe", "sample": False},
    )
    route = p.call(
        "POST",
        f"/organizations/{org}/model-profiles",
        token,
        json={
            "name": "Practice models",
            "llm_connection_id": remote["id"] if cloud else local["id"],
            "speech_connection_id": speech["id"] if cloud else None,
        },
    )
    return p, token, org, remote, speech, route, body


@pytest.mark.parametrize("compound", [False, True])
def test_profiles_azure_tokens_and_revision_fence(llm, monkeypatch, compound):
    p, token, org, remote, speech, route, body = configure(llm, monkeypatch)
    _, _, practice = setup(p, token, org)
    calls = []
    usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}

    class Model:
        async def close(self):
            pass

        async def events(self, **params):
            calls.append(params)
            yield {
                "type": "done",
                "text": "My name is Alex and I am 35." if compound else "My name is Alex.",
                "finish_reason": "stop",
                "usage": usage,
                "total_ms": 1,
            }

    p.client.app.state.llm = Model()
    payload = {
        **body,
        "connection_id": remote["id"],
        "profile_revision_id": route["profile_revision_id"],
        "configuration_hash": route["configuration_hash"],
        "practice_id": practice["id"],
        "practice_revision": practice["revision"],
        "language": "en",
        "messages": [
            {
                "role": "user",
                "content": "What is your name and age?" if compound else "What is your name?",
            }
        ],
    }
    from test_patient_conversations import start_conversation

    _, _, conversation = start_conversation(
        p,
        token,
        org,
        remote,
        practice,
        profile_revision_id=route["profile_revision_id"],
        configuration_hash=route["configuration_hash"],
    )
    payload["conversation_id"] = conversation["context"]["conversation_id"]
    answer = p.call("POST", f"/organizations/{org}/llm/completions", token, json=payload)
    assert answer["usage"]["total_tokens"] == 15
    assert answer["provider_calls"] == len(calls) == 1
    assert answer["answer_source"] == "patient_conversation"
    budget = answer["context"]["conversation"]
    assert p.sql(
        "SELECT reserved_tokens, reserved_total_tokens, charged_total_tokens FROM device_platform.llm_requests"
    ) == [(4096, budget["prompt_tokens"] + 4096 + 128, 15)]
    assert calls[0]["reasoning_effort"] == "none" and calls[0]["max_tokens"] == 4096
    outsider, _ = p.admin("cloud-outsider")
    p.call("GET", f"/organizations/{org}/model-config", outsider, expected=404)
    p.call(
        "POST",
        f"/organizations/{org}/model-profiles",
        token,
        json={
            "profile_id": route["profile_id"],
            "expected_revision_id": route["profile_revision_id"],
            "llm_connection_id": remote["id"],
            "speech_connection_id": speech["id"],
        },
    )
    p.call(
        "POST",
        f"/organizations/{org}/llm/completions",
        token,
        expected=409,
        json={**payload, "request_key": str(uuid4())},
    )
    assert len(calls) == 1


def test_cloud_speech_recording_idempotency_and_limits(llm, monkeypatch):
    p, token, org, _, _, route, _ = configure(llm, monkeypatch)
    submitted = []

    def handler(request):
        submitted.append(request)
        return httpx.Response(200, json={"text": "मेरा नाम एलेक्स है"})

    p.client.app.state.llm = LLMClient(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    path = f"/organizations/{org}/speech/transcriptions"
    params = {
        "request_key": str(uuid4()),
        "profile_revision_id": route["profile_revision_id"],
        "configuration_hash": route["configuration_hash"],
        "language": "hi",
    }

    # Harness headers are authoritative; send raw requests explicitly for media.
    def raw(params, data=None):
        return p.client.post(
            "/api/v1" + path,
            headers={**p.headers(token), "Content-Type": "audio/wav"},
            params=params,
            content=wav() if data is None else data,
        )

    response = raw(params)
    assert response.status_code == 200, response.text
    assert response.json()["result"]["text"] == "मेरा नाम एलेक्स है"
    assert raw(params).json()["cached"] and len(submitted) == 1
    assert raw(params, wav(0.2)).status_code == 409
    status_path = f"/organizations/{org}/speech/requests/{params['request_key']}"
    for _ in range(30):
        status = p.call("GET", status_path, token)
        if status["recording_status"] != "pending":
            break
        time.sleep(0.02)
    assert status["recording_status"] == "saved"
    audio = p.client.get("/api/v1" + status_path + "/audio", headers=p.headers(token))
    assert audio.status_code == 200 and audio.content == wav()
    p.settings.speech_daily_seconds = 0
    assert raw({**params, "request_key": str(uuid4())}).status_code == 429
    assert len(submitted) == 1
    outsider, _ = p.admin("speech-outsider")
    p.call("GET", status_path, outsider, expected=404)
    assert "fixture-speech-key" not in json.dumps(p.sql("SELECT result FROM device_platform.speech_requests"))


@pytest.mark.parametrize("device", [False, True])
def test_speech_duplicate_rechecks_department_scope(llm, monkeypatch, device):
    p, admin, org, _, _, route, _ = configure(llm, monkeypatch)
    departments = [
        p.call("POST", f"/organizations/{org}/departments", admin, expected=201, json={"name": name})["id"]
        for name in ("Speech A", "Speech B")
    ]
    if device:
        identity_id = p.device(admin, org, department_id=departments[0])["id"]
        token = p.enroll(admin, org, identity_id)
    else:
        token, user = p.user("speech-scope-user")
        identity_id = user["id"]
        p.sql(
            "INSERT INTO device_platform.organization_memberships "
            "(id, organization_id, user_id, department_id, role, invitation_status, joined_at, is_active) "
            "VALUES (%s,%s,%s,%s,'org_user','accepted',now(),true)",
            (uuid4(), org, identity_id, departments[0]),
        )
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"text": "A private question"})

    p.client.app.state.llm = LLMClient(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    params = {
        "request_key": str(uuid4()),
        "profile_revision_id": route["profile_revision_id"],
        "configuration_hash": route["configuration_hash"],
    }
    base = f"/organizations/{org}/speech"

    def submit():
        return p.client.post(
            "/api/v1" + base + "/transcriptions",
            headers={**p.headers(token), "Content-Type": "audio/wav"},
            params=params,
            content=wav(),
        )

    assert submit().status_code == 200
    assert submit().json()["cached"] and len(calls) == 1
    for department, expected in ((departments[1], 404), (departments[0], 200)):
        if device:
            p.sql(
                "UPDATE device_platform.devices SET department_id=%s WHERE id=%s", (department, identity_id)
            )
        else:
            p.sql(
                "UPDATE device_platform.organization_memberships SET department_id=%s "
                "WHERE organization_id=%s AND user_id=%s",
                (department, org, identity_id),
            )
        p.call("GET", base + "/requests/" + params["request_key"], token, expected=expected)
        assert submit().status_code == expected
        assert len(calls) == 1


def test_cloud_concurrency_does_not_serialize_all_requests(llm, monkeypatch):
    p, token, org, remote, _, _, body = configure(llm, monkeypatch)
    model = llm[-1]
    model.delay = 0.3
    body = {**body, "connection_id": remote["id"]}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: p.client.post(
                    f"/api/v1/organizations/{org}/llm/completions",
                    headers=p.headers(token),
                    json={**body, "request_key": str(uuid4())},
                ),
                range(2),
            )
        )
    assert [r.status_code for r in results] == [200, 200]
    assert model.calls == 2


def test_patient_conversation_uses_one_completion(llm, monkeypatch):
    p, token, org, remote, _, _, body = configure(llm, monkeypatch)
    update = {
        key: remote[key]
        for key in (
            "name",
            "provider",
            "base_url",
            "model",
            "max_tokens",
            "token_parameter",
            "stream_usage",
            "instruction_role",
            "system_prompt",
        )
    }
    p.call(
        "PUT",
        f"/organizations/{org}/llm/connections/{remote['id']}",
        token,
        json={
            **update,
            "expected_revision": remote["revision"],
            "model_options": {"context_tokens": 16384},
        },
    )
    _, _, practice = setup(p, token, org)
    from test_patient_conversations import start_conversation

    _, _, conversation = start_conversation(p, token, org, remote, practice)
    calls = []

    async def events(**params):
        calls.append(params)
        yield {
            "type": "done",
            "text": "My name is Alex.",
            "finish_reason": "stop",
            "usage": {},
            "total_ms": 1,
        }

    monkeypatch.setattr(p.client.app.state.llm, "events", events)
    result = p.call(
        "POST",
        f"/organizations/{org}/llm/completions",
        token,
        json={
            **body,
            "connection_id": remote["id"],
            "practice_id": practice["id"],
            "practice_revision": practice["revision"],
            "conversation_id": conversation["context"]["conversation_id"],
            "language": "en",
        },
    )
    assert result["answer_source"] == "patient_conversation" and len(calls) == 1
    # Reserve one output allowance for the single generation.
    assert p.sql("SELECT reserved_tokens FROM device_platform.llm_requests") == [(remote["max_tokens"],)]


def test_speech_timeout_is_unknown_and_not_replayed(llm, monkeypatch):
    p, token, org, _, _, route, _ = configure(llm, monkeypatch)
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("fixture timeout")

    p.client.app.state.llm = LLMClient(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    params = {
        "request_key": str(uuid4()),
        "profile_revision_id": route["profile_revision_id"],
        "configuration_hash": route["configuration_hash"],
    }
    url = f"/api/v1/organizations/{org}/speech/transcriptions"

    def submit():
        return p.client.post(
            url, headers={**p.headers(token), "Content-Type": "audio/wav"}, params=params, content=wav()
        )

    assert submit().status_code == 502
    replay = submit()
    assert replay.status_code == 200 and replay.json()["status"] == "unknown" and len(calls) == 1
    assert p.sql("SELECT status FROM device_platform.speech_requests") == [("unknown",)]


def test_slow_recording_does_not_delay_transcript_and_policy_is_shared(llm, monkeypatch):
    p, token, org, _, _, route, _ = configure(llm, monkeypatch)
    original = p.client.app.state.storage.write

    async def slow_write(*args, **kwargs):
        await asyncio.sleep(0.6)
        return await original(*args, **kwargs)

    monkeypatch.setattr(p.client.app.state.storage, "write", slow_write)
    p.client.app.state.llm = LLMClient(
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"text": "hello"}))
        )
    )
    params = {
        "request_key": str(uuid4()),
        "profile_revision_id": route["profile_revision_id"],
        "configuration_hash": route["configuration_hash"],
    }
    began = time.monotonic()
    response = p.client.post(
        f"/api/v1/organizations/{org}/speech/transcriptions",
        headers={**p.headers(token), "Content-Type": "audio/wav"},
        params=params,
        content=wav(),
    )
    elapsed = time.monotonic() - began
    assert response.status_code == 200 and response.json()["recording_status"] == "pending"
    assert elapsed < 0.6
    key = params["request_key"]
    for _ in range(50):
        saved = p.call("GET", f"/organizations/{org}/speech/requests/{key}", token)
        if saved["recording_status"] != "pending":
            break
        time.sleep(0.02)
    assert saved["recording_status"] == "saved"
    # Shared admission counts remain conservative even though the file saves later.
    assert p.sql("SELECT sum(duration_ms),sum(byte_size) FROM device_platform.speech_requests")[0] == (
        100,
        len(wav()),
    )


def test_speech_revision_change_during_provider_call_blocks_result(llm, monkeypatch):
    p, token, org, remote, speech, route, _ = configure(llm, monkeypatch)
    entered = __import__("threading").Event()

    async def handler(request):
        entered.set()
        await asyncio.sleep(0.35)
        return httpx.Response(200, json={"text": "old configuration"})

    p.client.app.state.llm = LLMClient(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    params = {
        "request_key": str(uuid4()),
        "profile_revision_id": route["profile_revision_id"],
        "configuration_hash": route["configuration_hash"],
    }
    with ThreadPoolExecutor(max_workers=1) as pool:
        job = pool.submit(
            lambda: p.client.post(
                f"/api/v1/organizations/{org}/speech/transcriptions",
                headers={**p.headers(token), "Content-Type": "audio/wav"},
                params=params,
                content=wav(),
            )
        )
        assert entered.wait(3)
        p.call(
            "POST",
            f"/organizations/{org}/model-profiles",
            token,
            json={
                "profile_id": route["profile_id"],
                "expected_revision_id": route["profile_revision_id"],
                "llm_connection_id": remote["id"],
                "speech_connection_id": speech["id"],
            },
        )
        response = job.result(5)
    assert response.status_code == 409
    assert p.sql("SELECT status,result FROM device_platform.speech_requests") == [("failed", None)]


def test_cloud_speech_duplicate_race_only_submits_once(llm, monkeypatch):
    p, token, org, _, _, route, _ = configure(llm, monkeypatch)
    calls = []

    async def handler(request):
        calls.append(request)
        await asyncio.sleep(0.15)
        return httpx.Response(200, json={"text": "one utterance"})

    p.client.app.state.llm = LLMClient(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    params = {
        "request_key": str(uuid4()),
        "profile_revision_id": route["profile_revision_id"],
        "configuration_hash": route["configuration_hash"],
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: p.client.post(
                    f"/api/v1/organizations/{org}/speech/transcriptions",
                    headers={**p.headers(token), "Content-Type": "audio/wav"},
                    params=params,
                    content=wav(),
                ),
                range(2),
            )
        )
    assert all(result.status_code == 200 for result in results)
    assert len(calls) == 1 and p.sql("SELECT count(*) FROM device_platform.speech_requests") == [(1,)]


@pytest.mark.parametrize("completed", [False, True])
def test_expired_recording_lease_recovers_capacity_without_replay(llm, monkeypatch, completed):
    from pms_api.modules.speech import retention_once

    p, token, org, _, speech, route, _ = configure(llm, monkeypatch)
    row_id, request_key = uuid4(), uuid4()
    user_id = llm[2]["id"]
    p.sql(
        """INSERT INTO device_platform.speech_requests
        (id,organization_id,user_id,profile_revision_id,configuration_hash,connection_id,
         connection_revision,request_key,fingerprint,status,byte_size,duration_ms,object_key,
         recording_status,lease_token,lease_expires_at,created_at,expires_at)
        VALUES (%s,%s,%s,%s,%s,%s,1,%s,%s,'running',44,100,%s,'pending',%s,
                now()-interval '1 minute',now()-interval '2 minutes',now()+interval '1 day')""",
        (
            row_id,
            org,
            user_id,
            route["profile_revision_id"],
            route["configuration_hash"],
            speech["id"],
            request_key,
            "a" * 64,
            f"{org}/speech/{row_id}.wav",
            uuid4(),
        ),
    )
    if completed:
        p.sql(
            "UPDATE device_platform.speech_requests SET status='succeeded',completed_at=now(),result='{\"text\":\"saved transcript\"}' WHERE id=%s",
            (row_id,),
        )
    p.client.portal.call(retention_once, p.client.app.state.sessions, p.client.app.state.storage)
    status, recording, result = p.sql(
        "SELECT status,recording_status,result FROM device_platform.speech_requests WHERE id=%s", (row_id,)
    )[0]
    assert recording == "failed" and status == ("succeeded" if completed else "unknown")
    assert result == ({"text": "saved transcript"} if completed else None)


def test_speech_quota_survives_media_cleanup(llm):
    from pms_api.modules.common import audit
    from pms_api.modules.speech_usage import daily_speech_millis

    p, _, _, org, *_ = llm

    async def verify():
        async with p.client.app.state.sessions() as session:
            await audit(
                session, None, "speech.accepted", "speech_request", uuid4(), org, {"duration_ms": 1250}
            )
            await session.commit()
            return await daily_speech_millis(session, org)

    assert p.client.portal.call(verify) == 1250
    assert p.sql("SELECT count(*) FROM device_platform.speech_requests") == [(0,)]


@pytest.mark.parametrize("version", [None, "", 20240601, "2024-06-01&redirect=other", "2024-06-01\n"])
def test_whisper_api_version_rejects_invalid_settings(version):
    from pms_api.modules.configuration import validate_connection

    with pytest.raises(AppError) as error:
        validate_connection(
            "azure",
            "azure_openai_whisper",
            "api_key",
            {"endpoint": AZURE, "deployment": "speech", "api_version": version},
            {"api_key": "fixture"},
        )
    assert error.value.code == "invalid_api_version"


@pytest.mark.parametrize("version", ["2024-06-01", "2024-10-21", "2024-08-01-preview"])
def test_whisper_api_version_accepts_bounded_date_versions(version):
    from pms_api.modules.configuration import validate_connection

    validate_connection(
        "azure",
        "azure_openai_whisper",
        "api_key",
        {"endpoint": AZURE, "deployment": "speech", "api_version": version},
        {"api_key": "fixture"},
    )


async def test_whisper_does_not_fallback_or_replay_missing_v1_deployment():
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(404, json={"error": {"code": "DeploymentNotFound"}})

    settings = SimpleNamespace(
        llm_allowed_ports=[],
        llm_allowed_base_urls=[AZURE],
        external_calls_enabled=True,
        provider_timeout_seconds=5,
    )
    connection = SimpleNamespace(settings={"endpoint": AZURE, "deployment": "fixture"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        with pytest.raises(AppError) as error:
            await transcribe(LLMClient(client=http), settings, connection, "fixture", wav(), "auto", uuid4())
        assert error.value.code == "llm_deployment_not_found"
    assert len(seen) == 1 and seen[0].url.path == "/openai/v1/audio/transcriptions"


@pytest.mark.parametrize("device", [False, True])
@pytest.mark.parametrize("revoked", [False, True])
def test_speech_status_reloads_identity_after_rollback(llm, monkeypatch, device, revoked):
    p, token, org, _, _, _, _ = configure(llm, monkeypatch)
    identity_id = llm[2]["id"]
    if device:
        identity_id = p.device(token, org)["id"]
        token = p.enroll(token, org, identity_id)
    else:
        # Keep the organization administrator active while revoking a caller.
        token, user = p.user("speech-status-user")
        identity_id = user["id"]
        p.sql(
            "INSERT INTO device_platform.organization_memberships "
            "(id, organization_id, user_id, role, invitation_status, joined_at, is_active) "
            "VALUES (%s, %s, %s, 'org_user', 'accepted', now(), true)",
            (uuid4(), org, identity_id),
        )

    async def health(*args, **kwargs):
        if revoked:
            if device:
                p.sql(
                    "UPDATE device_platform.devices SET credential_hash=NULL, credential_revoked_at=now() WHERE id=%s",
                    (identity_id,),
                )
            else:
                p.sql("UPDATE device_platform.users SET is_active=false WHERE id=%s", (identity_id,))

    monkeypatch.setattr(p.client.app.state.llm, "health", health)
    result = p.call(
        "GET",
        f"/organizations/{org}/speech/status",
        token,
        expected=(401 if device else 403) if revoked else 200,
    )
    if revoked:
        assert result["error"]["code"] == ("invalid_device_credential" if device else "identity_inactive")
    else:
        assert result["status"] == "ready" and result["inference_verified"] is False


def test_whisper_version_settings_preserve_encrypted_credentials(llm, monkeypatch):
    p, token, org, _, speech, _, _ = configure(llm, monkeypatch)
    before = p.sql(
        "SELECT encrypted_credentials FROM device_platform.provider_connections WHERE id=%s", (speech["id"],)
    )
    updated = p.call(
        "PATCH",
        f"/organizations/{org}/connections/{speech['id']}",
        token,
        json={
            "expected_version": speech["configuration_version"],
            "settings": {**speech["settings"], "api_version": "2024-06-01"},
        },
    )
    assert updated["settings"]["api_version"] == "2024-06-01" and updated["has_credentials"]
    assert updated["configuration_version"] > speech["configuration_version"]
    assert (
        p.sql(
            "SELECT encrypted_credentials FROM device_platform.provider_connections WHERE id=%s",
            (speech["id"],),
        )
        == before
    )
