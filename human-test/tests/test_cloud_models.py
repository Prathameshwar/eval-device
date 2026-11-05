import io
import json
import wave
from uuid import uuid4

import httpx
import pytest
from training_client import cloud_audio
from training_client.controller import Controller
from training_client.pms_client import ClientError

from human_test.config import Settings


def route(audio="cloud", llm="cloud"):
    return {
        "profile_id": str(uuid4()),
        "profile_name": "Practice",
        "profile_revision_id": str(uuid4()),
        "configuration_hash": "a" * 64,
        "cloud_allowed": True,
        "mode": audio if audio == llm else "custom",
        "audio": {
            "mode": audio,
            "model": "speech-deployment" if audio == "cloud" else "large-v3",
            "max_seconds": 30,
        },
        "llm": {"mode": llm, "connection_id": str(uuid4()), "model": "patient-deployment"},
    }


def settings():
    return Settings(
        _env_file=None, use_pms_models=True, pms_token="fixture-pms-token", organization_id=uuid4()
    )


async def frames():
    yield b"\x00\x10" * 800
    yield b"\x00\x12" * 800


async def test_cloud_audio_needs_no_local_token_and_uses_selected_english():
    configured = settings()
    configured.require_credentials()
    events, calls = [], []
    controller = Controller(configured, lambda *event: events.append(event))
    selected = route()
    controller.use_models(selected)

    def handler(request):
        calls.append(request)
        assert request.headers["authorization"] == "Bearer fixture-pms-token"
        if request.url.path.endswith("/speech/transcriptions"):
            with wave.open(io.BytesIO(request.content)) as audio:
                assert audio.getframerate() == 16000 and audio.getnframes() == 1600
            assert request.url.params["language"] == "en"
            return httpx.Response(
                200,
                json={
                    "status": "succeeded",
                    "request_key": request.url.params["request_key"],
                    "recording_status": "pending",
                    "result": {"text": "What is your name?", "provider_ms": 5},
                },
            )
        data = json.loads(request.content)
        assert data["configuration_hash"] == selected["configuration_hash"]
        assert data["profile_revision_id"] == selected["profile_revision_id"]
        assert data["messages"][-1]["content"] == "What is your name?"
        return httpx.Response(
            200,
            json={
                "request_key": data["request_key"],
                "status": "succeeded",
                "text": "My name is Alex.",
                "finish_reason": "stop",
                "usage": None,
            },
        )

    await controller.pms.http.aclose()
    controller.pms.http = httpx.AsyncClient(
        base_url="http://127.0.0.1",
        transport=httpx.MockTransport(handler),
        headers={"Authorization": "Bearer fixture-pms-token"},
    )
    configured.language, configured.streaming = "en", False
    result = await controller.turn(frames())
    assert result["answer"] == "My name is Alex." and len(calls) == 2
    assert not configured.local_models_key.get_secret_value()
    assert not any("recording could not" in str(event) for event in events)
    await controller.close()


async def test_audio_unknown_outcome_is_not_replayed():
    controller = Controller(settings(), lambda *event: None)
    controller.use_models(route())
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("fixture timeout")

    await controller.pms.http.aclose()
    controller.pms.http = httpx.AsyncClient(
        base_url="http://127.0.0.1", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(ClientError, match="Check last request"):
        await controller.turn(frames())
    assert len(calls) == 1 and controller.pms.last_speech_request and not controller.busy
    await controller.close()


async def test_cloud_audio_bound_before_submission():
    controller = Controller(settings(), lambda *event: None)
    controller.use_models(route())

    async def huge():
        yield b"\0" * (30 * 32000 + 2)

    with pytest.raises(ClientError, match="limit"):
        await cloud_audio.transcribe(controller.settings, controller.pms, huge(), lambda *e: None)
    assert controller.pms.last_speech_request is None
    await controller.close()


async def test_cloud_silence_is_not_submitted():
    """Silence still costs nothing: no upload, no transcription request, no completion."""
    controller = Controller(settings(), lambda *event: None)
    controller.use_models(route())

    async def silence():
        yield b"\0" * 16000

    result = await controller.turn(silence())
    # Empty recognition must remain silent and produce no provider request.
    assert result["answer"] is None and result["ignored"] is True
    assert result["metrics"]["provider_calls"] == 0
    assert controller.pms.last_speech_request is None and controller.pms.last_request is None
    assert controller.history == []
    await controller.close()


async def test_new_conversation_clears_previous_speech_and_response_recovery():
    controller = Controller(settings(), lambda *event: None)
    await controller.pms.http.aclose()
    controller.pms.http = httpx.AsyncClient(
        base_url="http://127.0.0.1",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"status": "succeeded"})),
    )
    controller.pms.last_speech_request = str(uuid4())
    controller.pms.last_request = str(uuid4())
    controller.reset()
    with pytest.raises(ClientError, match="No submitted speech request"):
        await controller.pms.speech_request_status()
    with pytest.raises(ClientError, match="No submitted request"):
        await controller.pms.status()
    await controller.close()


@pytest.mark.parametrize(
    "audio,llm", [("local", "local"), ("local", "cloud"), ("cloud", "local"), ("cloud", "cloud")]
)
async def test_route_selection_and_busy_fence(audio, llm):
    controller = Controller(settings(), lambda *event: None)
    selected = route(audio, llm)
    controller.history = [{"role": "user", "content": "previous"}]
    controller.use_models(selected)
    assert controller.settings.audio_mode == audio and not controller.history
    controller.busy = True
    with pytest.raises(ClientError, match="Finish or cancel"):
        controller.use_models(route())
    await controller.close()


async def test_preflight_reuses_technical_probe_and_keeps_profile_access_current(monkeypatch):
    controller = Controller(settings(), lambda *event: None)
    selected, calls = route(), []
    controller.use_models(selected)

    async def config(*args):
        calls.append("config")
        return selected

    async def ready():
        calls.append("ready")
        return {}

    monkeypatch.setattr(controller.pms, "model_config", config)
    monkeypatch.setattr(controller.pms, "speech_status", ready)
    monkeypatch.setattr(controller.pms, "preflight", ready)
    await controller.preflight()
    await controller.preflight()
    assert calls == ["config", "ready", "ready", "config"]
    controller._preflight_at = 0
    controller.pms.model_route = {**selected, "configuration_hash": "b" * 64}
    with pytest.raises(ClientError, match="changed"):
        await controller.preflight()
    await controller.close()


async def test_medical_model_switch_requires_english_before_capture():
    controller = Controller(settings(), lambda *event: None)
    selected = route("local", "cloud")
    selected["audio"]["model"] = "whisper-medical-v1"
    controller.use_models(selected)
    controller.settings.language = "hi"  # A stale selection cannot reach capture.
    with pytest.raises(ClientError, match="requires English"):
        await controller.preflight()
    await controller.close()


async def test_profile_switch_restores_capture_limit_without_exceeding_client_cap():
    configured = settings()
    configured.max_question_seconds = 20
    controller = Controller(configured, lambda *event: None)
    short = route()
    short["audio"]["max_seconds"] = 5
    controller.use_models(short)
    assert configured.max_question_seconds == 5
    controller.use_models(route())
    assert configured.max_question_seconds == 20
    await controller.close()


async def test_initial_pms_resolution_validates_medical_language(monkeypatch):
    controller = Controller(settings(), lambda *event: None)
    selected = route("local", "cloud")
    selected["audio"]["model"] = "whisper-medical-v1"

    async def config(*args):
        return selected

    monkeypatch.setattr(controller.pms, "model_config", config)
    controller.settings.language = "hi"  # A stale selection cannot reach capture.
    with pytest.raises(ClientError, match="requires English"):
        await controller.preflight()
    await controller.close()
