import argparse
import asyncio
import importlib.util
import json
import wave
from pathlib import Path

import pytest
from conftest import TOKEN
from websockets.asyncio.server import serve


def load_sender():
    path = Path(__file__).resolve().parents[1] / "scripts/stream_wav.py"
    spec = importlib.util.spec_from_file_location("audio_reference_sender", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def run_sender(tmp_path, monkeypatch, handler, *, io_timeout=0.15, completion_timeout=0.1):
    monkeypatch.setenv("AUDIO_CLIENT_TOKEN", TOKEN)
    audio = tmp_path / "sample.wav"
    with wave.open(str(audio), "wb") as target:
        target.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        target.writeframes(b"\x01\x00" * 480)
    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        args = argparse.Namespace(
            audio=audio,
            url=f"ws://127.0.0.1:{port}",
            language="en",
            ca_file=None,
            io_timeout=io_timeout,
            completion_timeout=completion_timeout,
        )
        await load_sender().stream(args)


async def handshake(ws):
    assert json.loads(await ws.recv())["type"] == "start"
    await ws.send(json.dumps(dict(type="ready", session_id="session-1", max_frame_bytes=16000)))


async def drain(ws):
    frames = []
    async for message in ws:
        if isinstance(message, str):
            assert json.loads(message) == {"type": "finish"}
            return frames
        frames.append(message)


async def test_audio_sender_success_with_exact_pcm(tmp_path, monkeypatch):
    received = []

    async def handler(ws):
        await handshake(ws)
        received.extend(await drain(ws))
        await ws.send(json.dumps(dict(type="complete", session_id="session-1")))

    await run_sender(tmp_path, monkeypatch, handler)
    assert b"".join(received) == b"\x01\x00" * 480


async def test_audio_sender_rejects_normal_close_without_complete(tmp_path, monkeypatch):
    async def handler(ws):
        await handshake(ws)
        await drain(ws)
        await ws.close()

    with pytest.raises(ExceptionGroup):
        await run_sender(tmp_path, monkeypatch, handler)


async def test_audio_sender_missing_start_reply_is_bounded(tmp_path, monkeypatch):
    async def handler(ws):
        await ws.wait_closed()

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(run_sender(tmp_path, monkeypatch, handler, io_timeout=0.05), 1)


async def test_audio_sender_missing_completion_is_bounded(tmp_path, monkeypatch):
    async def handler(ws):
        await handshake(ws)
        await drain(ws)
        await ws.wait_closed()

    with pytest.raises(ExceptionGroup):
        await asyncio.wait_for(run_sender(tmp_path, monkeypatch, handler), 1)


async def test_audio_sender_wrong_session_receipt_is_failure(tmp_path, monkeypatch):
    async def handler(ws):
        await handshake(ws)
        await drain(ws)
        await ws.send(json.dumps(dict(type="complete", session_id="another-session")))

    with pytest.raises(ExceptionGroup):
        await run_sender(tmp_path, monkeypatch, handler)


async def test_audio_sender_error_reply_stops_both_tasks(tmp_path, monkeypatch):
    async def handler(ws):
        await handshake(ws)
        await ws.send(json.dumps(dict(type="error", code="inference_capacity")))
        await ws.wait_closed()

    with pytest.raises(ExceptionGroup):
        await asyncio.wait_for(run_sender(tmp_path, monkeypatch, handler), 1)
