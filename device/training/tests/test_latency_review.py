import asyncio
import math
import sys
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_coordinator import acknowledge, start
from test_coordinator import rig as rig

from device_training.hardware import MicrophoneBuffer


async def test_microphone_bounds_bytes_and_pending_loop_callbacks():
    scheduled = []
    buffer = MicrophoneBuffer(SimpleNamespace(call_soon_threadsafe=scheduled.append), capacity=2)
    for _ in range(1000):
        buffer.push(b"x" * 640)
    assert len(scheduled) == 1 and len(buffer.frames) == 2
    scheduled.pop()()
    with pytest.raises(RuntimeError, match="microphone_overflow"):
        await buffer.receive()
    buffer.close()
    buffer.push(b"never retained")
    assert not buffer.frames and not scheduled


async def test_microphone_preserves_order_and_wakes_after_empty():
    buffer = MicrophoneBuffer(asyncio.get_running_loop())
    buffer.push(b"first")
    assert await buffer.receive() == b"first"
    pending = asyncio.create_task(buffer.receive())
    await asyncio.sleep(0)
    await asyncio.to_thread(buffer.push, b"second")
    assert await asyncio.wait_for(pending, 1) == b"second"
    buffer.close()


def submit(rig):
    state = start(rig)
    acknowledge(rig, state["turns"][0]["id"])
    return f"/sessions/{rig.sid}/turns/{uuid4()}"


def test_burst_upload_timing_uses_input_end_not_audio_duration(rig):
    path = submit(rig)
    response = rig.client.post(
        path, headers={**rig.headers(), "X-Capture-Offset-Ms": "111"}, content=bytes(32000 * 20)
    )
    assert response.status_code == 200, response.text
    row = response.json()
    assert row["input_duration_ms"] == 20000
    for name in (
        "input_receive_seconds",
        "asr_after_input_seconds",
        "dialogue_seconds",
        "tts_seconds",
        "processing_seconds",
        "response_save_seconds",
        "response_ready_seconds",
    ):
        assert row[name] >= 0
    assert row["response_ready_seconds"] >= row["processing_seconds"]


@pytest.mark.parametrize("slow_stage", ["dialogue", "speech"])
def test_response_deadline_also_bounds_selection_and_speech(rig, slow_stage):
    path = submit(rig)
    coordinator = rig.app.state.coordinator
    coordinator.settings.response_seconds = 0.05

    async def slow(*args):
        await asyncio.sleep(5)

    if slow_stage == "dialogue":
        coordinator.dialogue.select = slow
    else:
        coordinator.speech.synthesize = slow
    began = time.monotonic()
    response = rig.client.post(
        path, headers={**rig.headers(), "X-Capture-Offset-Ms": "111"}, content=bytes(6400)
    )
    assert response.status_code == 503
    assert time.monotonic() - began < 2
    assert coordinator.data["status"] == "failed"
    assert coordinator.data["turns"][-1]["playback"] == "failed"


def test_expired_authorization_after_selection_does_not_start_speech(rig):
    path = submit(rig)
    coordinator = rig.app.state.coordinator
    calls = []

    async def expired(*args):
        coordinator.claims["exp"] = time.time() - 1
        return "onset"

    async def speech(*args):
        calls.append(1)
        return b""

    coordinator.dialogue.select = expired
    coordinator.speech.synthesize = speech
    response = rig.client.post(
        path, headers={**rig.headers(), "X-Capture-Offset-Ms": "111"}, content=bytes(6400)
    )
    assert response.status_code == 409 and calls == []


async def test_brief_noise_does_not_hold_microphone_for_full_turn(monkeypatch):
    from device_training import hardware

    clock = [0.0]
    closed = []

    class Buffer:
        def __init__(self, loop):
            pass

        async def receive(self):
            clock[0] += 0.02
            return b"loud" if clock[0] < 0.03 else b"quiet"

        def close(self):
            closed.append(True)

    class Stream:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    # Doubles exercise capture lifecycle/timers, not native devices or DSP quality.
    numpy = SimpleNamespace(
        frombuffer=lambda data, **kwargs: SimpleNamespace(
            astype=lambda _: 1000.0 if data == b"loud" else 0.0
        ),
        float32=float,
        mean=lambda value: value,
        sqrt=math.sqrt,
    )
    monkeypatch.setitem(sys.modules, "numpy", numpy)
    monkeypatch.setitem(sys.modules, "sounddevice", SimpleNamespace(RawInputStream=Stream))
    monkeypatch.setattr(hardware, "MicrophoneBuffer", Buffer)
    monkeypatch.setattr(hardware, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    blocks = [block async for block in hardware.microphone(30, lambda: None)]
    assert 5 <= clock[0] < 5.1 and len(blocks) < 260 and closed == [True]


async def test_agent_closing_capture_closes_underlying_microphone(monkeypatch):
    from device_training import agent

    closed = []

    async def microphone(*args):
        try:
            yield b"first frame"
            yield b"second frame"
        finally:
            closed.append(True)

    monkeypatch.setattr(agent, "microphone", microphone)
    owner = SimpleNamespace(
        fixture_audio=None,
        claims={"limits": {"max_audio_turn_seconds": 30}},
        guard=lambda: None,
        s=SimpleNamespace(input_device=None),
    )
    source = agent.Agent.capture(owner)
    assert await anext(source) == b"first frame"
    await source.aclose()
    assert closed == [True]


def test_failed_turn_admission_stops_session_before_asr(rig):
    path = submit(rig)
    coordinator = rig.app.state.coordinator
    original = coordinator.store.call
    calls = []

    async def fail_once(method, *args):
        calls.append(method)
        if len(calls) == 1:
            raise RuntimeError("synthetic disk failure")
        return await original(method, *args)

    async def forbidden(*args):
        pytest.fail("ASR must not run before durable admission")

    coordinator.store.call = fail_once
    coordinator.transcriber.transcribe = forbidden
    response = rig.client.post(
        path, headers={**rig.headers(), "X-Capture-Offset-Ms": "111"}, content=bytes(6400)
    )
    assert response.status_code == 503
    assert coordinator.data["status"] == "failed"
    assert coordinator.data["reason"] == "storage_failed"
    assert coordinator.data["turns"][-1]["playback"] == "failed"
