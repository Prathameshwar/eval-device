"""Final online review: real PMS/DB boundaries with mocked provider transport."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import httpx
import pytest
from test_cloud_models import configure, wav
from test_llm_api import llm as llm
from test_patient_practice import setup

from pms_api.integrations.llm.client import LLMClient


@pytest.mark.parametrize("provider", ["azure_openai", "openai"])
async def test_readiness_uses_provider_specific_credentials_without_inference(provider):
    calls = []

    def handler(request):
        calls.append(request)
        assert request.method == "GET"
        if provider == "azure_openai":
            assert request.headers["api-key"] == "fixture" and "authorization" not in request.headers
        else:
            assert request.headers["authorization"] == "Bearer fixture" and "api-key" not in request.headers
        return httpx.Response(200, json={"data": []} if provider == "azure_openai" else {"id": "gpt-4.1"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await LLMClient(client=client).health("https://api.example/v1", "gpt-4.1", "fixture", provider)
    assert len(calls) == 1


def publish_models(p, token, org, remote, speech, route, **extra):
    return p.call(
        "POST",
        f"/organizations/{org}/model-profiles",
        token,
        json={
            "profile_id": route["profile_id"],
            "expected_revision_id": route["profile_revision_id"],
            "llm_connection_id": remote["id"],
            "speech_connection_id": speech["id"],
        },
        **extra,
    )


def test_model_switch_preserves_drafts_and_published_capture_settings(llm, monkeypatch):
    p, token, org, remote, speech, route, _ = configure(llm, monkeypatch)
    path = f"/organizations/{org}/profiles/{route['profile_id']}"
    draft = p.sql(
        "SELECT draft_settings FROM device_platform.processing_profiles WHERE id=%s", (route["profile_id"],)
    )[0][0]
    draft["audio_input"].update(language="hi", max_duration_seconds=7)
    p.call("PATCH", path, token, json={"draft_settings": draft})
    result = publish_models(p, token, org, remote, speech, route, expected=409)
    assert result["error"]["code"] == "profile_has_unpublished_changes"
    stored = p.sql(
        "SELECT draft_settings,published_revision_id FROM device_platform.processing_profiles WHERE id=%s",
        (route["profile_id"],),
    )[0]
    assert stored[0] == draft and str(stored[1]) == route["profile_revision_id"]
    p.call("POST", path + "/publish", token, json={"expected_revision_id": route["profile_revision_id"]})
    current = p.call("GET", f"/organizations/{org}/model-config", token)
    saved = publish_models(p, token, org, remote, speech, current)
    assert saved["audio"]["language"] == "hi" and saved["audio"]["max_seconds"] == 7


def test_new_model_profile_respects_tightened_operator_duration(llm, monkeypatch):
    p, token, org, remote, speech, route, _ = configure(llm, monkeypatch)
    p.settings.speech_max_seconds = 5
    saved = publish_models(p, token, org, remote, speech, route)
    assert saved["audio"]["max_seconds"] == 5


def disable_azure(p):
    admin, _ = p.admin("review-platform-admin")
    current = p.call("GET", "/platform/settings", admin)
    p.call(
        "PATCH",
        "/platform/settings",
        admin,
        json={"expected_version": current["configuration_version"], "enabled_providers": ["aws"]},
    )


def test_azure_llm_disabled_during_readiness_is_not_reported_ready(llm, monkeypatch):
    p, token, org, remote, _, _, _ = configure(llm, monkeypatch)
    entered, released = Event(), Event()

    async def health(*args, **kwargs):
        entered.set()
        while not released.is_set():
            await asyncio.sleep(0.01)

    monkeypatch.setattr(p.client.app.state.llm, "health", health)
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(
            lambda: p.client.get(
                f"/api/v1/organizations/{org}/llm/connections/{remote['id']}/status", headers=p.headers(token)
            )
        )
        try:
            assert entered.wait(3)
            disable_azure(p)
        finally:
            released.set()
        response = result.result(5)
    assert response.status_code == 503 and response.json()["error"]["code"] == "provider_disabled"
    # LLM-only Azure profiles must honor the platform gate, like Azure speech profiles.
    denied = p.call(
        "POST",
        f"/organizations/{org}/model-profiles",
        token,
        expected=409,
        json={"name": "Disabled Azure", "llm_connection_id": remote["id"]},
    )
    assert denied["error"]["code"] == "provider_disabled"


@pytest.mark.parametrize(
    "provider,streaming",
    [("azure_openai", False), ("azure_openai", True), ("openai", False), ("openai", True)],
)
def test_cloud_audio_to_patient_answer_through_real_pms_transport(llm, monkeypatch, provider, streaming):
    p, token, org, remote, speech, route, body = configure(llm, monkeypatch)
    if provider == "openai":
        p.settings.llm_allowed_base_urls.append("https://api.openai.com/v1")
        remote = p.call(
            "POST",
            f"/organizations/{org}/llm/connections",
            token,
            expected=201,
            json={
                "name": "OpenAI patient",
                "provider": "openai",
                "model": "gpt-4.1",
                "api_key": "fixture-openai",
                "model_options": {"model_family": "gpt_4_1", "temperature": 0.2, "context_tokens": 16384},
            },
        )
        route = publish_models(p, token, org, remote, speech, route)
    _, _, practice = setup(p, token, org)
    calls = []

    def handler(request):
        if request.url.path.endswith("/audio/transcriptions"):
            assert (
                request.headers["api-key"] == "fixture-speech-key" and "authorization" not in request.headers
            )
            return httpx.Response(200, json={"text": "What is your name?"})
        data = json.loads(request.content)
        calls.append(data)
        assert data["model"] == remote["model"] and data["store"] is False
        assert "max_completion_tokens" in data and "max_tokens" not in data
        if provider == "azure_openai":
            assert request.headers["api-key"] == "fixture-cloud-key" and "temperature" not in data
            assert data["reasoning_effort"] == "none"
        else:
            assert request.headers["authorization"] == "Bearer fixture-openai" and data["temperature"] == 0.2
            assert "reasoning_effort" not in data
        text = "My name is Alex."
        usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        if data["stream"]:
            event = {"choices": [{"delta": {"content": text}, "finish_reason": "stop"}], "usage": usage}
            return httpx.Response(200, content="data: " + json.dumps(event) + "\n\ndata: [DONE]\n\n")
        return httpx.Response(
            200, json={"choices": [{"message": {"content": text}, "finish_reason": "stop"}], "usage": usage}
        )

    p.client.app.state.llm = LLMClient(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    selected = {
        "profile_revision_id": route["profile_revision_id"],
        "configuration_hash": route["configuration_hash"],
    }
    from test_patient_conversations import start_conversation

    _, _, conversation = start_conversation(p, token, org, remote, practice, **selected)
    transcript = p.client.post(
        f"/api/v1/organizations/{org}/speech/transcriptions",
        params={**selected, "request_key": str(uuid4()), "language": "en"},
        headers={**p.headers(token), "Content-Type": "audio/wav"},
        content=wav(),
    )
    assert transcript.status_code == 200
    payload = {
        **body,
        **selected,
        "connection_id": remote["id"],
        "stream": streaming,
        "practice_id": practice["id"],
        "practice_revision": practice["revision"],
        "conversation_id": conversation["context"]["conversation_id"],
        "language": "en",
        "messages": [{"role": "user", "content": transcript.json()["result"]["text"]}],
    }
    response = p.client.post(
        f"/api/v1/organizations/{org}/llm/completions", headers=p.headers(token), json=payload
    )
    assert response.status_code == 200, response.text
    result = (
        next(
            json.loads(line[5:])
            for line in response.text.splitlines()
            if line.startswith("data:") and json.loads(line[5:]).get("type") == "done"
        )
        if streaming
        else response.json()
    )
    assert result["text"] == "My name is Alex." and result["usage"]["total_tokens"] == 15
    assert result["provider_calls"] == 1 and result["answer_source"] == "patient_conversation"
    assert len(calls) == 1
    assert p.sql("SELECT status FROM device_platform.llm_requests") == [("succeeded",)]
