import asyncio
import threading
import time

import pytest
from conftest import SPEECH, FakeEngine

from device_audio.audio import AudioChunk
from device_audio.runtime import Runtime, ServiceError


async def test_expired_stream_queue_audio_never_reaches_model(settings):
    engine = FakeEngine()
    runtime = Runtime(settings, lambda _: engine)
    await runtime.start()
    try:
        with pytest.raises(ServiceError, match="inference_timeout"):
            await runtime.transcribe(
                AudioChunk(SPEECH * 6, 0, 2880),
                "hi",
                time.perf_counter() - settings.inference_timeout_seconds - 1,
            )
        assert not engine.calls and runtime.jobs.empty() and runtime.ready
    finally:
        await runtime.stop()


async def test_native_deadline_fails_readiness_without_shutdown_or_second_inference(settings):
    entered, release = threading.Event(), threading.Event()

    class Blocked(FakeEngine):
        def transcribe(self, chunk, language):
            entered.set()
            release.wait(5)
            return super().transcribe(chunk, language)

    settings.inference_timeout_seconds = 0.1
    engine = Blocked()
    runtime = Runtime(settings, lambda _: engine)
    await runtime.start()
    first = asyncio.create_task(runtime.transcribe(AudioChunk(SPEECH * 6, 0, 2880), "hi"))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        with pytest.raises(ServiceError, match="inference_timeout"):
            await first
        async with asyncio.timeout(1):
            while runtime.ready:
                await asyncio.sleep(0.01)
        assert runtime.failure == "native_inference_timeout"
        with pytest.raises(ServiceError, match="not_ready"):
            await runtime.transcribe(AudioChunk(SPEECH * 6, 0, 2880), "en")
        assert engine.calls == []
        assert runtime.native.thread.is_alive()
    finally:
        release.set()
        await runtime.stop()
        await asyncio.to_thread(runtime.native.closed.wait, 1)
    assert len(engine.calls) == 1
