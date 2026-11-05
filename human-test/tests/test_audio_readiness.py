"""Bounded recognition transport to the central manager, without model ownership."""

import asyncio
import base64
import io
import json
import wave

import httpx
import pytest
from local_model_client import connection as transport_module
from local_model_client.connection import Connection, ConnectionError
from training_client import audio_client
from training_client.pms_client import ClientError

from human_test.config import Settings


def ready(**changes):
    return {
        "version": 1,
        "revision": 1,
        "models": [{"id": "large-v3", "name": "Whisper large", "capability": "asr", "platform_speech": True}],
        "services": {
            "asr": {"ready": True, "state": "Ready", "model_id": "large-v3", "device": "cpu", **changes}
        },
    }


def transport(monkeypatch, handler):
    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        transport_module.httpx,
        "AsyncClient",
        lambda **kwargs: client_type(transport=httpx.MockTransport(handler), **kwargs),
    )


def settings(**values):
    return Settings(_env_file=None, local_models_key="fixture-inference-key", **values)


@pytest.mark.parametrize("value", ["true", "false", 1, None, False])
async def test_readiness_requires_boolean_true(monkeypatch, value):
    transport(monkeypatch, lambda request: httpx.Response(200, json=ready(ready=value)))
    with pytest.raises(ClientError):
        await audio_client.preflight(settings())


async def test_readiness_rejects_oversized_body(monkeypatch):
    body = ready()
    body["padding"] = "x" * 131073
    transport(monkeypatch, lambda request: httpx.Response(200, json=body))
    with pytest.raises(ClientError, match="limit"):
        await audio_client.preflight(settings())


@pytest.mark.parametrize("body", [b"not-json", b"\xff", b"[]", b'{"ready":'])
async def test_readiness_rejects_malformed_response(monkeypatch, body):
    transport(monkeypatch, lambda request: httpx.Response(200, content=body))
    with pytest.raises(ClientError):
        await audio_client.preflight(settings())


async def test_readiness_has_total_deadline_and_closes_response(monkeypatch):
    closed = []

    class SlowBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            while True:
                yield b" "
                await asyncio.sleep(0.01)

        async def aclose(self):
            closed.append(True)

    monkeypatch.setattr(transport_module, "READINESS_TIMEOUT_SECONDS", 0.03)
    transport(monkeypatch, lambda request: httpx.Response(200, stream=SlowBody()))
    async with asyncio.timeout(1):
        with pytest.raises(ClientError, match="connection failed"):
            await audio_client.preflight(settings())
    assert closed


async def test_bounded_readiness_uses_inference_credential_and_selected_model(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=ready())

    transport(monkeypatch, handler)
    result = await audio_client.preflight(settings())
    assert result["model_id"] == "large-v3"
    assert len(calls) == 1 and calls[0].method == "GET"
    assert calls[0].url.path == "/v1/capabilities" and calls[0].url.port == 8790
    assert calls[0].headers["authorization"] == "Bearer fixture-inference-key"


@pytest.mark.parametrize("failure", [httpx.ConnectError, httpx.ReadTimeout])
async def test_readiness_transport_failures_are_redacted_and_not_replayed(monkeypatch, failure):
    calls = []

    def handler(request):
        calls.append(request)
        raise failure("private-token must not appear in the user error")

    transport(monkeypatch, handler)
    with pytest.raises(ClientError) as caught:
        await audio_client.preflight(settings())
    assert len(calls) == 1 and "private-token" not in str(caught.value)


async def test_readiness_redirect_never_forwards_credentials(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={"location": "https://other.invalid/status"})

    transport(monkeypatch, handler)
    with pytest.raises(ClientError):
        await audio_client.preflight(settings())
    assert len(calls) == 1 and calls[0].url.host == "127.0.0.1"


async def test_changed_model_is_refused_before_recording(monkeypatch):
    transport(monkeypatch, lambda _: httpx.Response(200, json=ready(model_id="small")))
    with pytest.raises(ClientError):
        await audio_client.preflight(settings())


async def test_pcm_is_bounded_pinned_and_sent_once(monkeypatch):
    calls, events, closed = [], [], []
    pcm = b"\x01\x00" * 1600

    async def frames():
        try:
            yield pcm[:1600]
            yield pcm[1600:]
        finally:
            closed.append(True)

    def handler(request):
        calls.append(request)
        data = json.loads(request.content)
        assert data["model"] == "large-v3" and data["language"] == "en"
        with wave.open(io.BytesIO(base64.b64decode(data["wav_base64"])), "rb") as wav:
            assert wav.getframerate() == 16000 and wav.getnchannels() == 1
            assert wav.readframes(1600) == pcm
        return httpx.Response(200, json={"text": "Hello", "language": "en"})

    transport(monkeypatch, handler)
    result = await audio_client.transcribe(settings(), frames(), lambda *event: events.append(event))
    assert result["text"] == "Hello" and result["bytes"] == len(pcm)
    assert len(calls) == 1 and calls[0].url.path == "/v1/infer/asr" and closed


async def test_oversized_microphone_input_closes_without_submission(monkeypatch):
    closed = []

    async def frames():
        try:
            yield bytes(960002)
        finally:
            closed.append(True)

    transport(monkeypatch, lambda _: pytest.fail("invalid audio submitted"))
    with pytest.raises(ClientError, match="duration limit"):
        await audio_client.transcribe(settings(), frames(), lambda *_: None)
    assert closed


async def test_client_cannot_request_management_routes():
    connection = Connection(key="fixture")
    with pytest.raises(ConnectionError, match="Unsupported"):
        await connection.async_request("POST", "/v1/actions/start", {})
