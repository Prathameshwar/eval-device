import asyncio
import json
import threading

import httpx
import pytest
from conftest import (
    HEADERS,
    OTHER_TOKEN,
    SILENCE,
    SPEECH,
    TOKEN,
    Detector,
    FakeEngine,
    collect,
    send_pcm,
)
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from device_audio.app import create_app
from device_audio.config import Settings


def client_for(settings, engine=None, transport=None, factory=None):
    engine = engine or FakeEngine()
    app = create_app(settings, factory or (lambda _: engine), transport, Detector)
    return TestClient(app, client=("127.0.0.1", 12345))


def start(ws, **kwargs):
    ws.send_json({"type": "start", **kwargs})
    ready = ws.receive_json()
    assert ready["type"] == "ready"
    return ready


def test_model_is_loaded_once_across_streams_and_console_is_default(settings, capsys):
    settings.console_output = True
    engine = FakeEngine()
    loads = []

    def factory(config):
        loads.append(config)
        return engine

    with client_for(settings, factory=factory) as client:
        for _ in range(3):
            with client.websocket_connect("/v1/audio/stream", headers=dict(HEADERS)) as ws:
                ready = start(ws, language="auto")
                assert ready["console_output"] is True
                send_pcm(ws, SPEECH * 6)
                ws.send_json({"type": "finish"})
                events = collect(ws)
                transcript = next(event for event in events if event["type"] == "transcript")
                delivery = next(event for event in events if event["type"] == "delivery")
                assert transcript["text"] == "\u0928\u092e\u0938\u094d\u0924\u0947, hello."
                assert transcript["client_id"] == "pi-1"
                assert delivery["console_status"] == "printed"
                assert delivery["status"] == "not_configured"
                assert events[-1]["transcripts"] == 1
        assert len(loads) == 1
        assert len(engine.calls) == 3
        assert client.get("/health/ready", headers=dict(HEADERS)).json() == {"ready": True}
    assert capsys.readouterr().out.count("\u0928\u092e\u0938\u094d\u0924\u0947, hello.") == 3


def test_authentication_origin_and_transport_boundaries(settings):
    with client_for(settings) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/v1/status").status_code == 401
        assert client.get("/health/ready").status_code == 401
        assert client.get("/v1/status", headers=dict(HEADERS)).status_code == 200
        for headers in ({}, {"Authorization": "Bearer invalid"}, {**HEADERS, "Origin": "https://other"}):
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect("/v1/audio/stream", headers=headers):
                    pass
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/v1/audio/stream?token=" + TOKEN):
                pass
    remote = TestClient(
        create_app(settings, lambda _: FakeEngine(), detector_factory=Detector),
        client=("192.168.1.25", 4321),
    )
    with remote:
        assert remote.get("/v1/status", headers=dict(HEADERS)).status_code == 401


@pytest.mark.parametrize(
    "start_fields",
    [
        {"sample_rate": 48000},
        {"channels": 2},
        {"format": "wav"},
        {"language": "ar"},
        {"callback_url": "http://127.0.0.1/override"},
        {"recording_dir": "../outside"},
    ],
)
def test_invalid_start_cannot_override_audio_or_delivery(settings, start_fields):
    with client_for(settings) as client:
        with client.websocket_connect("/v1/audio/stream", headers=dict(HEADERS)) as ws:
            ws.send_json({"type": "start", **start_fields})
            assert ws.receive_json()["code"] == "invalid_start"


@pytest.mark.parametrize("audio", [b"\x01", b"", b"\0" * 16002], ids=["odd", "empty", "oversized"])
def test_invalid_audio_frames_are_rejected(settings, audio):
    with client_for(settings) as client:
        with client.websocket_connect("/v1/audio/stream", headers=dict(HEADERS)) as ws:
            start(ws)
            ws.send_bytes(audio)
            assert ws.receive_json()["code"] == "invalid_audio_frame"


def test_audio_limit_silence_and_no_callback_for_empty_result(settings):
    settings.max_audio_seconds = 1
    engine = FakeEngine()
    with client_for(settings, engine) as client:
        with client.websocket_connect("/v1/audio/stream", headers=dict(HEADERS)) as ws:
            start(ws)
            send_pcm(ws, SILENCE * 10)
            ws.send_json({"type": "finish"})
            assert collect(ws)[-1]["transcripts"] == 0
        with client.websocket_connect("/v1/audio/stream", headers=dict(HEADERS)) as ws:
            start(ws)
            send_pcm(ws, SILENCE * 40)
            assert ws.receive_json()["code"] == "audio_limit"
    assert engine.calls == []


def test_one_active_stream_per_client_and_global_session_limit(settings):
    settings.max_sessions = 1
    with client_for(settings) as client:
        with client.websocket_connect("/v1/audio/stream", headers=dict(HEADERS)) as ws:
            start(ws)
            for token in (TOKEN, OTHER_TOKEN):
                with pytest.raises(WebSocketDisconnect):
                    with client.websocket_connect(
                        "/v1/audio/stream", headers={"Authorization": "Bearer " + token}
                    ):
                        pass
            ws.send_json({"type": "finish"})
            assert collect(ws)[-1]["type"] == "complete"


def test_callback_payload_matches_stream_and_uses_server_event_id(settings, caplog):
    settings = Settings(
        _env_file=None,
        **{
            **settings.model_dump(),
            "callback_url": "http://127.0.0.1:9999/private-callback",
            "callback_token": "callback-secret",
        },
    )
    requests = []

    def callback(request):
        requests.append(request)
        return httpx.Response(204)

    with client_for(settings, transport=httpx.MockTransport(callback)) as client:
        with client.websocket_connect("/v1/audio/stream", headers=dict(HEADERS)) as ws:
            start(ws, language="hi")
            send_pcm(ws, SPEECH * 6)
            ws.send_json({"type": "finish"})
            events = collect(ws)
    event = next(event for event in events if event["type"] == "transcript")
    assert len(requests) == 1
    assert json.loads(requests[0].content) == event
    assert requests[0].headers["idempotency-key"] == event["event_id"]
    assert requests[0].headers["authorization"] == "Bearer callback-secret"
    assert next(event for event in events if event["type"] == "delivery")["status"] == "delivered"
    assert "private-callback" not in caplog.text
    assert "callback-secret" not in caplog.text
    assert "\u0928\u092e\u0938\u094d\u0924\u0947" not in caplog.text


@pytest.mark.parametrize(
    "mode, expected", [("timeout", "unknown"), ("redirect", "rejected"), ("error", "rejected")]
)
def test_callback_is_never_blindly_retried_or_redirected(settings, mode, expected):
    settings = Settings(
        _env_file=None, **{**settings.model_dump(), "callback_url": "http://127.0.0.1:9999/result"}
    )
    requests = []

    def callback(request):
        requests.append(request)
        if mode == "timeout":
            raise httpx.ReadTimeout("private response or URL must not be logged")
        return httpx.Response(307 if mode == "redirect" else 500, headers={"Location": "https://elsewhere"})

    with client_for(settings, transport=httpx.MockTransport(callback)) as client:
        with client.websocket_connect("/v1/audio/stream", headers=dict(HEADERS)) as ws:
            start(ws)
            send_pcm(ws, SPEECH * 6)
            ws.send_json({"type": "finish"})
            events = collect(ws)
    assert len(requests) == 1
    assert next(event for event in events if event["type"] == "delivery")["status"] == expected
    assert events[-1]["delivery_failures"] == 1


def test_slow_callback_does_not_block_the_next_transcription(settings):
    settings = Settings(
        _env_file=None, **{**settings.model_dump(), "callback_url": "http://127.0.0.1:9999/result"}
    )
    gate = threading.Event()
    engine = FakeEngine()

    async def callback(request):
        await asyncio.to_thread(gate.wait, 5)
        return httpx.Response(204)

    try:
        with client_for(settings, engine, httpx.MockTransport(callback)) as client:
            with client.websocket_connect("/v1/audio/stream", headers=dict(HEADERS)) as ws:
                start(ws)
                for _ in range(2):
                    send_pcm(ws, SPEECH * 6)
                    ws.send_json({"type": "flush"})
                ws.send_json({"type": "finish"})
                transcripts = []
                while len(transcripts) < 2:
                    event = ws.receive_json()
                    if event["type"] == "transcript":
                        transcripts.append(event)
                assert len(engine.calls) == 2
                gate.set()
                assert collect(ws)[-1]["transcripts"] == 2
    finally:
        gate.set()


def test_capture_backlog_is_bounded_while_health_remains_responsive(settings):
    settings.max_chunk_seconds = 1
    settings.chunk_queue_size = 1
    started, release = threading.Event(), threading.Event()

    class SlowEngine(FakeEngine):
        def transcribe(self, chunk, language):
            started.set()
            release.wait(5)
            return super().transcribe(chunk, language)

    try:
        with client_for(settings, SlowEngine()) as client:
            with client.websocket_connect("/v1/audio/stream", headers=dict(HEADERS)) as ws:
                start(ws)
                send_pcm(ws, SPEECH * 34)
                assert started.wait(2)
                assert client.get("/health/ready", headers=dict(HEADERS)).status_code == 200
                send_pcm(ws, SPEECH * 100)
                assert ws.receive_json()["code"] == "audio_backlog"
                release.set()
    finally:
        release.set()
