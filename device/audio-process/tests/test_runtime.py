import asyncio
import threading
import time

import httpx
import pytest
from conftest import SPEECH, TOKEN, FakeEngine
from pydantic import ValidationError

from device_audio.audio import AudioChunk
from device_audio.config import Settings
from device_audio.delivery import CallbackDispatcher
from device_audio.engine import FasterWhisperEngine
from device_audio.runtime import Runtime


@pytest.mark.parametrize(
    "overrides",
    [
        {"client_tokens": {}},
        {"client_tokens": {"pi": "short"}},
        {"host": "0.0.0.0"},
        {"callback_url": "http://192.168.1.20/text"},
        {"callback_url": "https://user:pass@example.com/text"},
        {"callback_url": "file:///tmp/text"},
        {"client_tokens": {"pi": TOKEN, "other": TOKEN}},
    ],
)
def test_insecure_or_invalid_configuration_is_rejected(overrides):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{"client_tokens": {"pi": TOKEN}, **overrides})


@pytest.mark.parametrize(
    "present", [[], ["model.bin", "config.json"]], ids=["missing-model", "missing-tokenizer"]
)
def test_missing_model_fails_without_downloading(settings, tmp_path, monkeypatch, present):
    for name in present:
        (tmp_path / name).write_bytes(b"test placeholder")
    settings.model_path = tmp_path
    constructed = []
    monkeypatch.setattr("faster_whisper.WhisperModel", lambda *a, **k: constructed.append(k))
    with pytest.raises(RuntimeError, match="local model missing"):
        FasterWhisperEngine(settings)
    assert constructed == []


async def test_cancelled_request_keeps_native_inference_serialized(settings):
    started, release = threading.Event(), threading.Event()

    class SlowEngine(FakeEngine):
        active = 0
        max_active = 0

        def transcribe(self, chunk, language):
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            started.set()
            release.wait(3)
            try:
                return super().transcribe(chunk, language)
            finally:
                self.active -= 1

    engine = SlowEngine()
    runtime = Runtime(settings, lambda _: engine)
    await runtime.start()
    chunk = AudioChunk(SPEECH * 6, 0, 2880)
    try:
        first = asyncio.create_task(runtime.transcribe(chunk, "hi"))
        assert await asyncio.to_thread(started.wait, 1)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        second = asyncio.create_task(runtime.transcribe(chunk, "en"))
        await asyncio.sleep(0.05)
        assert not second.done()
        release.set()
        await second
        assert engine.max_active == 1
        assert len(engine.calls) == 2
    finally:
        release.set()
        await runtime.stop()


async def test_callback_queue_overflow_is_explicit_and_does_not_grow(settings):
    settings = Settings(
        _env_file=None,
        **{
            **settings.model_dump(),
            "callback_url": "http://127.0.0.1:9999/text",
            "callback_queue_size": 1,
            "callback_workers": 1,
        },
    )
    gate = asyncio.Event()
    started = asyncio.Event()

    async def callback(request):
        started.set()
        await gate.wait()
        return httpx.Response(204)

    dispatcher = CallbackDispatcher(settings, httpx.MockTransport(callback))
    dispatcher.start()
    try:
        first = dispatcher.submit({"event_id": "first", "text": "one"})
        await asyncio.wait_for(started.wait(), 1)
        second = dispatcher.submit({"event_id": "second", "text": "two"})
        third = dispatcher.submit({"event_id": "third", "text": "three"})
        assert (await third).status == "queue_full"
        assert dispatcher.queue.qsize() == 1
        gate.set()
        assert (await first).status == "delivered"
        assert (await second).status == "delivered"
    finally:
        gate.set()
        await dispatcher.stop()


async def test_queue_metric_includes_time_in_the_stream_buffer(settings):
    runtime = Runtime(settings, lambda _: FakeEngine())
    await runtime.start()
    try:
        outcome = await runtime.transcribe(AudioChunk(SPEECH * 6, 0, 2880), "en", time.perf_counter() - 0.25)
        assert outcome.queue_seconds >= 0.25
    finally:
        await runtime.stop()
