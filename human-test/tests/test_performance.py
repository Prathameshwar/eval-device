"""Latency optimizations must preserve durable playback, ordering and cancellation."""

import asyncio
import gc
import json
import sys
import threading
from types import SimpleNamespace

import pytest
from test_flow import settings
from test_speech import installed_voice, wait_until
from training_client import speech
from training_client.controller import Controller
from training_client.performance import PlaybackGate, TurnTiming
from training_client.pms_client import ClientError
from training_client.session_sync import SaveQueue, SessionSync


def test_timings_are_monotonic_stages_without_content_or_absolute_timestamps():
    now = [10.0]
    timing = TurnTiming(clock=lambda: now[0])
    timing.mark("speech_end")
    now[0] += 0.8
    timing.mark("endpoint")
    now[0] += 0.2
    timing.mark("worker")
    now[0] += 3.8
    timing.mark("output")
    timing.output_latency_ms = 250
    result = timing.snapshot()
    assert result["endpoint_ms"] == 800 and result["queue_ms"] == 200
    assert result["output_submission_ms"] == 4800 and result["estimated_audible_ms"] == 5050
    assert result["slow"] and result["playback_complete_ms"] is None
    assert not any(key in result for key in ("text", "answer", "question", "timestamps"))
    with pytest.raises(ValueError):
        timing.mark("question text")


def test_result_priority_preserves_context_and_media_order_without_starvation():
    work = SaveQueue(maxsize=256)
    media = [("audio_start", "s", (), 0), ("audio", "s", (), 0), ("audio_end", "s", (), 0)]
    for item in media:
        work.put_nowait(item)
    work.put_nowait(("begin", "s", (), 0))
    for index in range(10):
        work.put_nowait(("turn", "s", (index,), 0))
    consumed = []
    while not work.empty():
        consumed.append(work.get_nowait())
        work.task_done()
    assert consumed[0][0] == "begin"
    assert consumed[8] == media[0]
    assert [item for item in consumed if item[0].startswith("audio")] == media
    assert [item[2][0] for item in consumed if item[0] == "turn"] == list(range(10))
    assert work.unfinished_tasks == 0


def test_frame_saturation_preserves_room_for_results_and_stream_closure():
    sync = SessionSync.__new__(SessionSync)
    sync.queue = SaveQueue(maxsize=256)
    sync.stop, sync.ready = threading.Event(), threading.Event()
    sync.ready.set()
    sync.disk_ok = True
    sync.guard = threading.Lock()
    sync.pending_bytes = 0
    sync.failed = set()
    sync.emit = lambda *_: None
    for _ in range(248):
        assert sync.submit("audio", "session", "stream", bytes(320), 16000, "microphone")
    assert not sync.submit("audio", "session", "stream", bytes(320), 16000, "microphone")
    assert sync.submit("audio_end", "session", "stream")
    assert sync.submit("end", "session", "completed")
    assert sync.submit("turn", "session", {"input_text": "Question", "response_text": "Answer"})


@pytest.mark.parametrize("saved", [True, False])
async def test_controller_prepares_while_saving_and_never_releases_failed_result(monkeypatch, saved):
    events = []
    controller = Controller(settings(), lambda kind, value: events.append((kind, value)))

    async def conversation(_):
        return None

    async def answer(*_):
        return {"text": "A reviewed answer.", "finish_reason": "stop", "total_ms": 10}

    async def save(*_):
        prepared = next(value for kind, value in events if kind == "prepare_speech")
        assert not prepared["gate"].finished.is_set()
        await asyncio.sleep(0)
        return saved

    monkeypatch.setattr(controller.pms, "ensure_conversation", conversation)
    monkeypatch.setattr(controller.pms, "answer", answer)
    controller.sync = SimpleNamespace(current="session", save_turn=save)
    try:
        if saved:
            result = await controller.respond({"text": "Question", "asr_finalize_ms": 0}, 0)
            assert result["answer"] == "A reviewed answer." and len(controller.history) == 2
        else:
            with pytest.raises(ClientError, match="Audio was withheld"):
                await controller.respond({"text": "Question", "asr_finalize_ms": 0}, 0)
            assert not controller.history
        prepared = next(value for kind, value in events if kind == "prepare_speech")
        assert prepared["gate"].finished.is_set() and prepared["gate"].saved is saved
        assert not any(kind == "speak" for kind, _ in events)
    finally:
        controller.sync = None
        await controller.close()


async def test_display_backlog_cannot_discard_a_completed_durable_result(monkeypatch):
    from test_flow import settings

    saved = []
    gates = []

    def emit(kind, value):
        if kind == "prepare_speech":
            gates.append(value["gate"])
            raise ClientError("Display backlog")

    controller = Controller(settings(), emit)

    async def conversation(_):
        return None

    async def answer(*_):
        return {"text": "Reviewed answer.", "finish_reason": "stop", "total_ms": 10}

    async def save(sid, record):
        saved.append(record)
        return True

    monkeypatch.setattr(controller.pms, "ensure_conversation", conversation)
    monkeypatch.setattr(controller.pms, "answer", answer)
    controller.sync = SimpleNamespace(current="session", save_turn=save)
    try:
        with pytest.raises(ClientError, match="Display backlog"):
            await controller.respond({"text": "Question", "asr_finalize_ms": 0}, 0)
        assert saved[0]["response_text"] == "Reviewed answer."
        assert gates[0].finished.is_set() and not gates[0].saved
    finally:
        controller.sync = None
        await controller.close()


@pytest.fixture
def engine_fixture(tmp_path, monkeypatch):
    # Earlier GUI tests can leave unreachable Tk variables. Finalize them on
    # their owner thread before starting a synthesis worker, where Tk cleanup
    # would otherwise block and raise "main thread is not in main loop".
    gc.collect()
    installed_voice(tmp_path, monkeypatch)
    synthesizing = threading.Event()
    writes, streams, requests = [], [], []

    class Voice:
        config = SimpleNamespace(sample_rate=22050)

        def synthesize(self, text, tuning):
            requests.append(text)
            synthesizing.set()
            yield SimpleNamespace(audio_int16_bytes=b"\x01\x00" * 4096)
            yield SimpleNamespace(audio_int16_bytes=b"\x02\x00" * 4096)

    class Stream:
        latency = 0.09

        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.closed = False
            streams.append(self)

        def start(self):
            pass

        def write(self, pcm):
            writes.append(pcm)
            return False

        def stop(self):
            pass

        def abort(self):
            pass

        def close(self):
            self.closed = True

    monkeypatch.setitem(sys.modules, "sounddevice", SimpleNamespace(RawOutputStream=Stream))
    engine = speech.ManagerPlayback()
    monkeypatch.setattr(engine, "voice", lambda *_: Voice())
    yield engine, synthesizing, writes, streams, requests
    engine.close()


@pytest.mark.parametrize("saved", [True, False])
def test_native_playback_synthesizes_before_commit_but_writes_only_after_success(engine_fixture, saved):
    engine, synthesizing, writes, streams, _ = engine_fixture
    gate = PlaybackGate()
    timing = TurnTiming("text")
    timing.mark("worker")
    timing.mark("answer")
    thread = threading.Thread(
        target=lambda: engine.play("Answer", "en", lambda: True, gate=gate, performance=timing)
    )
    thread.start()
    try:
        assert synthesizing.wait(2)
        assert wait_until(lambda: timing.snapshot()["first_pcm_ms"] is not None)
        assert not writes and not streams
        gate.resolve(saved)
        thread.join(3)
        assert not thread.is_alive()
        assert bool(writes) is saved
        assert (timing.snapshot()["estimated_audible_ms"] is not None) is saved
    finally:
        gate.resolve(False)
        thread.join(3)


def test_playback_reuses_bounded_pcm_and_stream_and_does_not_reuse_other_text(engine_fixture):
    engine, _, writes, streams, requests = engine_fixture
    engine.play("First.", "en", lambda: True)
    first = list(writes)
    engine.play("First.", "en", lambda: True)
    assert writes == first * 2 and requests == ["First."] and len(streams) == 1
    engine.play("Other.", "en", lambda: True)
    assert requests == ["First.", "Other."]
    assert engine._pcm_bytes <= speech.PCM_CACHE_BYTES
    engine.close()
    assert streams[0].closed and engine._pcm_bytes == 0


def test_cancel_while_commit_pending_does_not_play_or_leak_synthesis_worker(engine_fixture):
    engine, synthesizing, writes, _, _ = engine_fixture
    gate = PlaybackGate()
    thread = threading.Thread(target=lambda: engine.play("Answer", "en", lambda: True, gate=gate))
    thread.start()
    assert synthesizing.wait(2)
    engine.interrupt()
    thread.join(3)
    assert not thread.is_alive() and not writes and not engine._producer.is_alive()


def test_low_latency_open_failure_falls_back_and_underruns_use_high_next_turn(engine_fixture, monkeypatch):
    engine, _, _, streams, _ = engine_fixture
    real = sys.modules["sounddevice"].RawOutputStream
    attempts = []

    def open_stream(**kwargs):
        attempts.append(kwargs["latency"])
        if kwargs["latency"] == "low":
            raise RuntimeError("unsupported device latency")
        return real(**kwargs)

    monkeypatch.setattr(sys.modules["sounddevice"], "RawOutputStream", open_stream)
    engine.play("Answer", "en", lambda: True)
    assert attempts == ["low", "high"] and not streams[0].closed
    engine.play("Answer", "en", lambda: True)
    assert attempts == ["low", "high"]


def test_playback_underrun_is_reported_and_next_answer_uses_high_latency(engine_fixture, monkeypatch):
    engine, _, _, streams, _ = engine_fixture
    calls = [0]

    def write(*_):
        calls[0] += 1
        return calls[0] == 1

    monkeypatch.setattr(sys.modules["sounddevice"].RawOutputStream, "write", write)
    timing = TurnTiming("text")
    engine.play("Answer", "en", lambda: True, performance=timing)
    assert streams[0].kwargs["latency"] == "low" and streams[0].closed
    assert timing.underruns == 1
    engine.play("Answer", "en", lambda: True)
    assert streams[1].kwargs["latency"] == "high"


def test_warm_checks_service_without_submitting_synthesis(engine_fixture, monkeypatch):
    monkeypatch.setattr("local_model_client.Connection.require", lambda *_: {"ready": True})
    engine, _, writes, streams, requests = engine_fixture
    engine.warm("en")
    engine.warm("en")
    assert requests == [] and not writes and not streams


def test_telemetry_serializes_as_plain_bounded_data():
    value = json.dumps(TurnTiming().snapshot())
    assert len(value) < 1024


def test_failed_first_output_is_not_counted_as_audible(engine_fixture, monkeypatch):
    engine, _, _, _, _ = engine_fixture
    stream_type = sys.modules["sounddevice"].RawOutputStream

    def fail(*_):
        raise RuntimeError("output disconnected")

    monkeypatch.setattr(stream_type, "write", fail)
    timing = TurnTiming("text")
    timing.mark("worker")
    with pytest.raises(RuntimeError, match="disconnected"):
        engine.play("Answer", "en", lambda: True, performance=timing)
    assert timing.snapshot()["output_submission_ms"] is None
    assert engine._stream is None and not engine._producer.is_alive()


def test_failed_output_drain_is_interrupted_and_stream_is_not_reused(engine_fixture, monkeypatch):
    engine, _, _, streams, _ = engine_fixture

    def fail(*_):
        raise RuntimeError("output disconnected while draining")

    monkeypatch.setattr(sys.modules["sounddevice"].RawOutputStream, "stop", fail)
    timing = TurnTiming("text")
    engine.play("Answer", "en", lambda: True, performance=timing)
    assert timing.playback_status == "interrupted"
    assert streams[0].closed and engine._stream is None
    engine.play("Next answer", "en", lambda: True)
    assert len(streams) == 2


def test_synthesis_continues_while_first_sentence_playback_is_blocked(engine_fixture, monkeypatch):
    engine, _, _, _, _ = engine_fixture
    second_sentence = threading.Event()
    playback_entered = threading.Event()
    release = threading.Event()

    class Voice:
        config = SimpleNamespace(sample_rate=22050)

        def synthesize(self, *_):
            yield SimpleNamespace(audio_int16_bytes=b"\x01\x00" * 4096)
            second_sentence.set()
            yield SimpleNamespace(audio_int16_bytes=b"\x02\x00" * 4096)

    def write(*_):
        playback_entered.set()
        assert release.wait(3)
        return False

    monkeypatch.setattr(engine, "voice", lambda *_: Voice())
    monkeypatch.setattr(sys.modules["sounddevice"].RawOutputStream, "write", write)
    worker = threading.Thread(target=lambda: engine.play("Two sentences.", "en", lambda: True))
    worker.start()
    try:
        assert playback_entered.wait(2) and second_sentence.wait(1)
    finally:
        release.set()
        worker.join(3)
    assert not worker.is_alive()


def test_pcm_eviction_is_bounded_and_old_answers_are_resynthesized(engine_fixture, monkeypatch):
    engine, _, _, _, requests = engine_fixture
    monkeypatch.setattr(speech, "PCM_CACHE_BYTES", 20000)
    for text in ("First", "Second", "First"):
        engine.play(text, "en", lambda: True)
    assert requests == ["First", "Second", "First"]
    assert engine._pcm_bytes == 16384 and len(engine._pcm) == 1


def test_old_turn_timings_cannot_replace_the_current_ui():
    from test_speech import FakeWindow

    from human_test.app import Window

    values = []
    window = FakeWindow(timing=SimpleNamespace(set=values.append), performance_turn_id="new")
    old = TurnTiming("text")
    old.mark("worker")
    old.mark("output")
    old.output_latency_ms = 10
    window.emit("performance", old.snapshot())
    Window.drain(window)
    assert not values


def test_preparing_a_durable_answer_does_not_mute_the_microphone():
    from test_speech import FakeWindow

    from human_test.app import Window

    window = FakeWindow()
    window.speaker.speaking = True
    window.speaker.playing = False
    assert Window.capture_allowed(window)
    window.speaker.playing = True
    assert not Window.capture_allowed(window)


def test_speaker_reports_playing_only_after_durable_gate_opens(engine_fixture):
    engine, synthesized, _, _, _ = engine_fixture
    speaker = speech.Speaker(engine=engine)
    gate = PlaybackGate()
    try:
        assert speaker.speak("Answer", "en", gate=gate)
        assert synthesized.wait(2)
        assert speaker.speaking and not speaker.playing
        gate.resolve(False)
        assert wait_until(lambda: not speaker.speaking)
        assert not speaker.playing
    finally:
        gate.resolve(False)
        speaker.close()


async def test_device_readiness_cache_retains_each_authenticated_profile_check(monkeypatch):
    from test_local_execution import route

    controller = Controller(settings(local_models_key="fixture"), lambda *_: None)
    selected = route()
    controller.pms.use_models(selected)
    controller.settings.device_id = "fixture-device"
    controller.settings.use_pms_models = True
    profiles, probes = [], []

    async def profile(*_):
        profiles.append(True)
        return selected

    async def probe(*_, **kwargs):
        probes.append(True)

    monkeypatch.setattr(controller.pms, "model_config", profile)
    monkeypatch.setattr(controller, "local_model", lambda: object())
    monkeypatch.setattr("training_client.local_turn.health", probe)
    monkeypatch.setattr("training_client.audio_client.preflight", probe)
    try:
        await controller.preflight()
        await controller.preflight()
        assert len(profiles) == 2 and len(probes) == 2
        selected = {**selected, "configuration_hash": "d" * 64}
        with pytest.raises(ClientError, match="configuration changed"):
            await controller.preflight()
        assert len(profiles) == 3 and len(probes) == 2
    finally:
        await controller.close()


def test_cached_remote_pcm_preserves_actual_sample_rate(engine_fixture, monkeypatch):
    engine, _, writes, streams, _ = engine_fixture
    calls = []

    class Remote:
        def __init__(self):
            self.config = SimpleNamespace(sample_rate=22050)

        def synthesize(self, text, tuning):
            calls.append(text)
            self.config.sample_rate = 44100
            yield SimpleNamespace(audio_int16_bytes=b"\x01\x00" * 4096)

    monkeypatch.setattr(engine, "voice", lambda *_: Remote())
    engine.play("Cached answer.", "en", lambda: True)
    first = list(writes)
    engine.play("Cached answer.", "en", lambda: True)
    assert writes == first * 2 and calls == ["Cached answer."]
    assert len(streams) == 1 and streams[0].kwargs["samplerate"] == 44100
    assert engine._pcm_bytes == sum(map(len, first))
