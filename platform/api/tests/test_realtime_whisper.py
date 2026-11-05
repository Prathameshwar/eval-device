import asyncio
import base64
import json
import socket
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_cloud_models import AZURE, configure, wav
from test_cloud_models import llm as llm
from websockets.datastructures import Headers
from websockets.exceptions import InvalidStatus
from websockets.http11 import Response

from pms_api.core.common import AppError
from pms_api.integrations import realtime_whisper as rt
from pms_api.integrations.whisper_cloud import speech_health, transcribe
from pms_api.modules.configuration import validate_connection


def settings():
    return SimpleNamespace(
        llm_allowed_ports=[],
        llm_allowed_base_urls=[AZURE],
        external_calls_enabled=True,
        provider_timeout_seconds=3,
        health_timeout_seconds=3,
    )


def connection():
    return SimpleNamespace(settings={"endpoint": AZURE, "deployment": rt.MODEL, "model": rt.MODEL})


class Socket:
    def __init__(self, failure=None):
        self.sent, self.events = [], asyncio.Queue()
        self.failure, self.closed = failure, False

    async def send(self, raw):
        event = json.loads(raw)
        self.sent.append(event)
        if event["type"] == "session.update":
            await self.events.put({"type": "session.updated", "session": {"type": "transcription"}})
        if event["type"] == "input_audio_buffer.append" and self.failure == "disconnect":
            raise OSError("private failure details")
        if event["type"] == "input_audio_buffer.commit":
            if self.failure == "busy":
                await self.events.put({"type": "error", "error": {"code": "rate_limit_exceeded"}})
            elif self.failure == "timeout":
                return
            else:
                await self.events.put({"type": "input_audio_buffer.committed", "item_id": "one"})
                await self.events.put(
                    {
                        "type": "conversation.item.input_audio_transcription.completed",
                        "item_id": "other" if self.failure == "mismatch" else "one",
                        "transcript": " What's your name? ",
                    }
                )

    async def recv(self):
        return json.dumps(await self.events.get())


def transport(monkeypatch, failure=None):
    sockets = []

    @asynccontextmanager
    async def open_socket(endpoint, key):
        assert endpoint == AZURE and key == "fixture-secret"
        ws = Socket(failure)
        sockets.append(ws)
        try:
            yield ws
        finally:
            ws.closed = True

    monkeypatch.setattr(rt, "websocket", open_socket)
    return sockets


@pytest.mark.parametrize("language", ["en", "hi", "auto"])
async def test_selectable_adapter_converts_and_submits_once(monkeypatch, language):
    sockets = transport(monkeypatch)
    result = await transcribe(None, settings(), connection(), "fixture-secret", wav(0.2), language, "key")
    assert result["text"] == "What's your name?" and result["model"] == rt.MODEL
    (ws,) = sockets
    config = ws.sent[0]["session"]["audio"]["input"]
    assert config["format"] == {"type": "audio/pcm", "rate": 24000}
    assert config["turn_detection"] is None
    assert ("language" in config["transcription"]) == (language != "auto")
    pcm = b"".join(base64.b64decode(e["audio"]) for e in ws.sent if "audio" in e)
    assert len(pcm) == 9600 and pcm == b"\x01\x00" * 4800
    assert sum(e["type"] == "input_audio_buffer.commit" for e in ws.sent) == 1
    assert ws.closed


async def test_health_configures_session_without_audio(monkeypatch):
    sockets = transport(monkeypatch)
    await speech_health(None, settings(), connection(), "fixture-secret")
    assert len(sockets) == 1 and sockets[0].closed
    assert [e["type"] for e in sockets[0].sent] == ["session.update"]


@pytest.mark.parametrize("failure", ["disconnect", "busy", "mismatch", "timeout"])
async def test_after_audio_any_uncertain_failure_has_no_replay(monkeypatch, failure):
    sockets = transport(monkeypatch, failure)
    cfg = settings()
    cfg.provider_timeout_seconds = 0.1
    with pytest.raises(AppError) as caught:
        await rt.run(cfg, connection(), "fixture-secret", wav(0.2))
    assert caught.value.code == "speech_submission_unknown"
    assert len(sockets) == 1 and sockets[0].closed
    assert "private" not in str(caught.value) and "fixture-secret" not in str(caught.value)


@pytest.mark.parametrize(
    "status,code",
    [
        (429, "speech_busy"),
        (503, "speech_busy"),
        (401, "llm_credentials_rejected"),
        (400, "llm_invalid_parameters"),
    ],
)
async def test_pre_audio_handshake_rejections_are_classified(monkeypatch, status, code):
    @asynccontextmanager
    async def reject(*args):
        raise InvalidStatus(Response(status, "private", Headers(), body=b"secret"))
        yield

    monkeypatch.setattr(rt, "websocket", reject)
    with pytest.raises(AppError) as caught:
        await rt.run(settings(), connection(), "fixture-secret", wav())
    assert caught.value.code == code and "secret" not in str(caught.value)


async def test_cancel_closes_socket_without_finishing_or_retrying(monkeypatch):
    sockets = transport(monkeypatch, "timeout")
    task = asyncio.create_task(rt.run(settings(), connection(), "fixture-secret", wav()))
    while not sockets or not any(e["type"] == "input_audio_buffer.commit" for e in sockets[0].sent):
        await asyncio.sleep(0.001)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(sockets) == 1 and sockets[0].closed


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "224.0.0.1"])
async def test_dns_rebinding_to_private_address_is_rejected(monkeypatch, address):
    async def resolve(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in ("8.8.8.8", address)]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
    with pytest.raises(AppError) as caught:
        async with rt.websocket(AZURE, "fixture-secret"):
            pytest.fail("Private DNS result connected")
    assert caught.value.code == "llm_endpoint_invalid"


async def test_allowed_endpoint_is_checked_before_connect(monkeypatch):
    sockets = transport(monkeypatch)
    cfg = settings()
    cfg.llm_allowed_base_urls = []
    with pytest.raises(AppError):
        await rt.run(cfg, connection(), "fixture-secret", wav())
    assert not sockets


def test_redirects_are_never_followed():
    error = InvalidStatus(Response(302, "Redirect", Headers({"Location": "https://attacker.test"})))
    assert rt.NoRedirect.process_redirect(None, error) is error


@pytest.mark.parametrize("code", [None, {}, [], "private-value"])
def test_malformed_provider_codes_are_redacted(code):
    with pytest.raises(AppError) as caught:
        rt.provider_error({"error": {"code": code, "message": "fixture-secret"}})
    assert caught.value.code == "llm_invalid_parameters"
    assert "private-value" not in str(caught.value) and "fixture-secret" not in str(caught.value)


async def test_public_socket_is_pinned_and_uses_verified_tls_without_proxies(monkeypatch):
    used = []
    sock = SimpleNamespace(setblocking=lambda value: None, close=lambda: used.append("closed"))
    loop = asyncio.get_running_loop()

    async def resolve(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]

    async def connect_socket(actual, address):
        assert actual is sock and address == ("8.8.8.8", 443)
        used.append("pinned")

    @asynccontextmanager
    async def connect_ws(url, **kwargs):
        assert url == AZURE.replace("https:", "wss:") + "/realtime?intent=transcription"
        assert kwargs["sock"] is sock and kwargs["proxy"] is None
        assert kwargs["server_hostname"] == "alex-fixture.openai.azure.com"
        assert kwargs["ssl"].check_hostname and kwargs["ssl"].verify_mode == 2
        assert kwargs["additional_headers"] == {"api-key": "fixture-secret"}
        yield "connected"

    monkeypatch.setattr(loop, "getaddrinfo", resolve)
    monkeypatch.setattr(loop, "sock_connect", connect_socket)
    monkeypatch.setattr(rt.socket, "socket", lambda *args: sock)
    monkeypatch.setattr(rt, "NoRedirect", connect_ws)
    async with rt.websocket(AZURE, "fixture-secret") as ws:
        assert ws == "connected"
    assert used == ["pinned", "closed"]


async def test_event_budget_bounds_even_ignored_events():
    ws = Socket()
    events = rt.Events(ws)
    events.count = 2048
    await ws.events.put({"type": "irrelevant"})
    with pytest.raises(AppError) as caught:
        await events.next()
    assert caught.value.code == "speech_response_limit"


def test_model_validation_preserves_whisper_and_accepts_realtime():
    for model in ("whisper", rt.MODEL):
        validate_connection(
            "azure",
            "azure_openai_whisper",
            "api_key",
            {"endpoint": AZURE, "deployment": model, "model": model},
            {"api_key": "fixture"},
        )
    for changes in ({"model": "unknown"}, {"api_version": "2024-06-01"}):
        with pytest.raises(AppError):
            validate_connection(
                "azure",
                "azure_openai_whisper",
                "api_key",
                {**connection().settings, **changes},
                {"api_key": "fixture"},
            )


@pytest.mark.parametrize("failure", [None, "disconnect"])
def test_pms_selection_admission_recording_and_unknown_recovery(llm, monkeypatch, failure):
    p, token, org, remote, whisper, route, _ = configure(llm, monkeypatch)
    base = f"/organizations/{org}"
    sockets = transport(monkeypatch, failure)
    realtime = p.call(
        "POST",
        base + "/connections",
        token,
        expected=201,
        json={
            "name": "Realtime alternative",
            "provider": "azure",
            "connection_type": "azure_openai_whisper",
            "auth_mode": "api_key",
            "settings": connection().settings,
            "credentials": {"api_key": "fixture-secret"},
        },
    )
    p.call(
        "POST",
        base + f"/connections/{realtime['id']}/validate",
        token,
        json={"operation": "audio.transcribe", "sample": False},
    )
    choices = p.call("GET", base + "/model-options", token)["speech"]
    assert {item["id"] for item in choices} == {whisper["id"], realtime["id"]}
    for speech in (realtime, whisper, realtime):
        route = p.call(
            "POST",
            base + "/model-profiles",
            token,
            json={
                "profile_id": route["profile_id"],
                "expected_revision_id": route["profile_revision_id"],
                "llm_connection_id": remote["id"],
                "speech_connection_id": speech["id"],
            },
        )
        assert route["audio"]["connection_id"] == speech["id"]
    ready = p.call("GET", base + "/speech/status", token)
    assert ready["model"] == rt.MODEL and ready["inference_verified"] is False
    params = {
        "request_key": str(uuid4()),
        "profile_revision_id": route["profile_revision_id"],
        "configuration_hash": route["configuration_hash"],
    }

    def submit():
        return p.client.post(
            "/api/v1" + base + "/speech/transcriptions",
            content=wav(0.2),
            params=params,
            headers={**p.headers(token), "Content-Type": "audio/wav"},
        )

    result = submit()
    assert result.status_code == (502 if failure else 200), result.text
    count = len(sockets)
    cached = submit()
    assert len(sockets) == count, "A cached or unknown submission must never resend audio"
    status = p.call("GET", base + "/speech/requests/" + params["request_key"], token)
    assert status["status"] == ("unknown" if failure else "succeeded")
    if not failure:
        assert cached.json()["cached"]
        assert status["result"]["text"] == "What's your name?"
    outsider, _ = p.admin("realtime-outsider")
    p.call("GET", base + "/speech/requests/" + params["request_key"], outsider, expected=404)
    p.settings.speech_daily_seconds = 0
    params["request_key"] = str(uuid4())
    assert submit().status_code == 429 and len(sockets) == count
