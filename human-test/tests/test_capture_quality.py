"""Microphone endpointing, adaptive gating and per-turn input quality.

No real device is opened: `sounddevice` is replaced by a scripted stream and the clock is
advanced one block at a time, so every assertion is about the capture logic itself.
"""

import threading
from array import array
from uuid import uuid4

import pytest
import sounddevice as sd
from training_client.capture import (
    BLOCK_MS,
    BLOCK_SAMPLES,
    CaptureQuality,
    _Gate,
    block_levels,
    dbfs,
    microphone,
    probe_microphone,
    resolve_device,
)
from training_client.pms_client import ClientError

from human_test.config import Settings


def settings(**kw):
    return Settings(
        _env_file=None,
        pms_token="fixture",
        audio_token="fixture",
        organization_id=uuid4(),
        connection_id=uuid4(),
        **kw,
    )


def blocks(level, count=1):
    """`count` blocks of a constant magnitude, whose RMS is exactly that magnitude."""
    return [array("h", [level] * BLOCK_SAMPLES).tobytes() for _ in range(count)]


def install(monkeypatch, frames, devices=(("Fixture Mic", 1),), step=BLOCK_MS / 1000):
    """Script a capture: `frames` are delivered when the stream opens, and each clock read
    advances by one block so elapsed-time exits stay realistic without real waiting."""
    opened, closed = {}, []

    class Stream:
        def __init__(self, **kw):
            opened.update(kw)
            self.callback = kw["callback"]

        def __enter__(self):
            for frame in frames:
                self.callback(frame, len(frame) // 2, None, False)
            return self

        def __exit__(self, *args):
            closed.append(True)

    monkeypatch.setattr(sd, "check_input_settings", lambda **kw: None)
    monkeypatch.setattr(sd, "RawInputStream", Stream)
    monkeypatch.setattr(
        sd,
        "query_devices",
        lambda: [{"name": name, "max_input_channels": channels} for name, channels in devices],
    )
    now = [0.0]

    def monotonic():
        now[0] += step
        return now[0]

    monkeypatch.setattr("training_client.capture._now", monotonic)
    monkeypatch.setattr("training_client.capture._default_input_index", lambda: 0)
    return opened, closed


async def drain(frames):
    got = []
    try:
        async for frame in frames:
            got.append(frame)
    finally:
        await frames.aclose()
    return got


# --- The adaptive gate -------------------------------------------------------------------


def test_quiet_room_keeps_the_configured_threshold():
    gate = _Gate(settings())
    for _ in range(6):
        gate.update(20)
    assert gate.calibrated and gate.threshold == 400
    assert gate.update(500) is True


def test_noisy_room_raises_the_threshold_above_the_room():
    """A 500 RMS block is speech in a quiet room and room noise in a 200 RMS room. The fixed
    threshold could not express that, which is how the endpointer used to arm on noise."""
    gate = _Gate(settings())
    for _ in range(6):
        gate.update(200)
    assert gate.threshold == 600
    assert gate.update(500) is False
    assert gate.update(900) is True


def test_calibration_uses_the_quietest_block_so_early_speech_cannot_raise_the_gate():
    gate = _Gate(settings())
    for level in (20, 20, 5000, 5000, 5000, 5000):
        gate.update(level)
    assert gate.floor == 20 and gate.threshold == 400


def test_threshold_never_exceeds_the_configured_ceiling():
    gate = _Gate(settings(energy_ceiling=1000))
    for _ in range(6):
        gate.update(900)
    assert gate.threshold == 1000


def test_settings_reject_a_ceiling_below_the_threshold():
    with pytest.raises(Exception, match="energy_ceiling"):
        settings(energy_threshold=2000, energy_ceiling=1000)


# --- Endpointing ------------------------------------------------------------------------


async def test_isolated_noise_never_arms_the_endpoint(monkeypatch):
    """The regression this replaces: `voiced` only ever accumulated, so three scattered noise
    blocks armed the endpointer permanently and the next pause ended the question."""
    frames = []
    for _ in range(3):
        frames += blocks(5000) + blocks(0, 5)  # A click, then quiet, three times over.
    frames += blocks(0, 20)
    install(monkeypatch, frames)
    quality = CaptureQuality()
    got = await drain(microphone(settings(), threading.Event(), quality))
    # Never armed, so the only way out is the no-speech exit, not a silence endpoint.
    assert quality.ended == "no_speech"
    assert len(got) == len(frames)


async def test_contiguous_speech_then_silence_ends_the_question(monkeypatch):
    quiet_needed = 800 // BLOCK_MS
    frames = blocks(5000, 4) + blocks(0, quiet_needed)
    install(monkeypatch, frames)
    quality = CaptureQuality()
    got = await drain(microphone(settings(silence_ms=800), threading.Event(), quality))
    assert quality.ended == "endpoint"
    assert len(got) == len(frames)
    assert quality.voiced_blocks == 4


async def test_one_dipped_block_mid_word_still_arms(monkeypatch):
    """Real speech dips below any threshold briefly; a single quiet block must not restart the
    run, or a learner with a soft consonant would never arm the endpointer."""
    frames = blocks(5000, 2) + blocks(0) + blocks(5000, 2) + blocks(0, 800 // BLOCK_MS)
    install(monkeypatch, frames)
    quality = CaptureQuality()
    await drain(microphone(settings(silence_ms=800), threading.Event(), quality))
    assert quality.ended == "endpoint"


async def test_the_no_speech_exit_follows_its_setting(monkeypatch):
    """A learner who needs a moment to phrase a question should be able to have one."""
    install(monkeypatch, blocks(0, 40))
    short, long = CaptureQuality(), CaptureQuality()
    brief = await drain(microphone(settings(no_speech_seconds=1.0), threading.Event(), short))
    install(monkeypatch, blocks(0, 40))
    patient = await drain(microphone(settings(no_speech_seconds=5.0), threading.Event(), long))
    assert short.ended == long.ended == "no_speech"
    assert len(brief) < len(patient) == 40


def test_settings_reject_a_no_speech_exit_the_duration_limit_would_pre_empt():
    with pytest.raises(Exception, match="no_speech_seconds"):
        settings(no_speech_seconds=10.0, max_question_seconds=5)


async def test_operator_send_now_wins_immediately(monkeypatch):
    install(monkeypatch, blocks(5000, 10))
    send_now = threading.Event()
    send_now.set()
    quality = CaptureQuality()
    got = await drain(microphone(settings(), send_now, quality))
    assert quality.ended == "operator" and got == []


# --- Losing audio rather than losing the question ----------------------------------------


async def test_overflow_drops_the_oldest_block_and_reports_it(monkeypatch):
    """Two seconds of slack is generous, but this app also runs Tk, OpenCV and video encoding.
    A stalled loop should cost a block, not the learner's whole question."""
    # 55 blocks into 40 slots loses 15 - under the 20-block budget. The speech sits at the
    # end, which is exactly the audio dropping the oldest block is meant to preserve.
    frames = blocks(0, 35) + blocks(5000, 4) + blocks(0, 800 // BLOCK_MS)
    install(monkeypatch, frames)
    quality = CaptureQuality()
    got = await drain(microphone(settings(silence_ms=800), threading.Event(), quality))
    assert quality.dropped_blocks == len(frames) - 40 == 15
    assert quality.ended == "endpoint" and got
    assert any("lost" in reason for reason in quality.concerns())


async def test_overflow_beyond_budget_refuses_the_turn(monkeypatch):
    install(monkeypatch, blocks(5000, 80))
    quality = CaptureQuality()
    frames = microphone(settings(max_lost_blocks=20), threading.Event(), quality)
    try:
        with pytest.raises(ClientError, match="lost about"):
            await anext(frames)
    finally:
        await frames.aclose()
    # A refused turn must still say why, or the snapshot cannot be told from an unfinished one.
    assert quality.ended == "lost_audio"


async def test_device_status_flags_are_kept_not_collapsed(monkeypatch):
    """The old code turned any PortAudio status into a bare failure, losing which fault it was."""
    frames = blocks(5000, 4) + blocks(0, 800 // BLOCK_MS)

    class Stream:
        def __init__(self, **kw):
            self.callback = kw["callback"]

        def __enter__(self):
            for index, frame in enumerate(frames):
                self.callback(frame, len(frame) // 2, None, "input overflow" if index == 0 else False)
            return self

        def __exit__(self, *args):
            pass

    install(monkeypatch, [])
    monkeypatch.setattr(sd, "RawInputStream", Stream)
    quality = CaptureQuality()
    await drain(microphone(settings(silence_ms=800), threading.Event(), quality))
    assert quality.status_blocks == 1 and quality.status_flags == "input overflow"


# --- Reported quality --------------------------------------------------------------------


async def test_frames_reach_the_transcriber_unmodified(monkeypatch):
    """Nothing in capture filters or gains the signal, so recordings stay byte-exact."""
    frames = blocks(1234, 4) + blocks(0, 800 // BLOCK_MS)
    install(monkeypatch, frames)
    got = await drain(microphone(settings(silence_ms=800), threading.Event(), CaptureQuality()))
    assert b"".join(got) == b"".join(frames)


async def test_snapshot_reports_level_snr_and_voiced_ratio(monkeypatch):
    frames = blocks(100, 6) + blocks(8000, 4) + blocks(100, 800 // BLOCK_MS)
    install(monkeypatch, frames)
    quality = CaptureQuality()
    await drain(microphone(settings(silence_ms=800), threading.Event(), quality))
    report = quality.snapshot()
    assert report["device_name"] == "Fixture Mic"
    assert report["audio_ms"] == len(frames) * BLOCK_MS
    assert report["peak_dbfs"] == pytest.approx(dbfs(8000), abs=0.2)
    assert report["snr_db"] > 30
    assert 0 < report["voiced_ratio"] < 1
    assert report["clipped_percent"] == 0.0
    assert report["calibrated"] is True


async def test_clipping_is_measured_and_flagged(monkeypatch):
    frames = blocks(32767, 4) + blocks(0, 800 // BLOCK_MS)
    install(monkeypatch, frames)
    quality = CaptureQuality()
    await drain(microphone(settings(silence_ms=800), threading.Event(), quality))
    assert quality.snapshot()["clipped_percent"] > 0.1
    assert any("clipped" in reason for reason in quality.concerns())


async def test_digital_silence_is_reported(monkeypatch):
    install(monkeypatch, blocks(0, 40))
    quality = CaptureQuality()
    await drain(microphone(settings(), threading.Event(), quality))
    assert quality.ended == "no_speech"
    assert any("digital silence" in reason for reason in quality.concerns())


async def test_low_snr_is_reported(monkeypatch):
    frames = blocks(600, 6) + blocks(1200, 4) + blocks(600, 800 // BLOCK_MS)
    install(monkeypatch, frames)
    quality = CaptureQuality()
    await drain(microphone(settings(silence_ms=800), threading.Event(), quality))
    assert quality.snapshot()["snr_db"] < 15
    assert any("above the room noise" in reason for reason in quality.concerns())


def test_block_levels_and_dbfs():
    assert block_levels(array("h", [1000] * 10).tobytes()) == (1000.0, 1000, 0)
    assert block_levels(b"") == (0.0, 0, 0)
    assert block_levels(array("h", [-32767, 0]).tobytes())[2] == 1
    assert dbfs(0) == -120.0 and dbfs(32768) == 0.0


# --- Device resolution -------------------------------------------------------------------


def test_resolution_prefers_the_saved_name_over_a_stale_index(monkeypatch):
    install(monkeypatch, [], devices=(("Other Mic", 2), ("Headset Mic", 1)))
    index, name, warning = resolve_device(settings(microphone=0, microphone_name="Headset Mic"))
    assert (index, name, warning) == (1, "Headset Mic", None)


def test_resolution_falls_back_to_the_index_and_says_so(monkeypatch):
    install(monkeypatch, [], devices=(("Other Mic", 2),))
    index, name, warning = resolve_device(settings(microphone=0, microphone_name="Headset Mic"))
    assert (index, name) == (0, "Other Mic") and "not connected" in warning


def test_resolution_reports_an_index_that_is_no_longer_an_input(monkeypatch):
    install(monkeypatch, [], devices=(("Only Mic", 1),))
    index, name, warning = resolve_device(settings(microphone=5))
    # Falls back to the system default, and still names whatever that resolves to.
    assert index is None and name == "Only Mic" and "no longer an input device" in warning


def test_resolution_without_configuration_names_the_system_default(monkeypatch):
    """A report must always say which microphone was heard, even on the out-of-box setting."""
    install(monkeypatch, [], devices=(("Only Mic", 1),))
    assert resolve_device(settings()) == (None, "Only Mic", None)


def test_resolution_survives_an_unresolvable_default(monkeypatch):
    install(monkeypatch, [], devices=(("Only Mic", 1),))
    monkeypatch.setattr("training_client.capture._default_input_index", lambda: None)
    assert resolve_device(settings()) == (None, None, None)


def test_resolution_does_not_claim_a_name_it_could_not_confirm(monkeypatch):
    """If enumeration fails, the requested name is still only a request; reporting it as the device
    that was heard would make a quality report say something nothing verified."""
    install(monkeypatch, [])
    monkeypatch.setattr(sd, "query_devices", lambda: (_ for _ in ()).throw(OSError("no host api")))
    index, name, warning = resolve_device(settings(microphone=2, microphone_name="Headset Mic"))
    assert (index, name) == (2, None) and "Could not enumerate" in warning


async def test_microphone_opens_the_resolved_device(monkeypatch):
    opened, closed = install(monkeypatch, blocks(0, 40), devices=(("Other Mic", 2), ("Headset Mic", 1)))
    await drain(microphone(settings(microphone_name="Headset Mic"), threading.Event(), CaptureQuality()))
    assert opened["device"] == 1 and opened["samplerate"] == 16000
    assert opened["blocksize"] == BLOCK_SAMPLES and opened["dtype"] == "int16"
    assert closed == [True]


# --- Startup self-test -------------------------------------------------------------------


async def test_probe_reports_the_room(monkeypatch):
    install(monkeypatch, blocks(150, 20))
    quality = await probe_microphone(settings(), seconds=0.3)
    assert quality.ended == "probe" and quality.blocks > 0
    assert quality.device_name == "Fixture Mic"
    assert quality.snapshot()["noise_floor_dbfs"] < 0


async def test_probe_fails_when_the_device_delivers_nothing(monkeypatch):
    install(monkeypatch, [])
    with pytest.raises(ClientError, match="no audio"):
        await probe_microphone(settings(), seconds=0.3)


async def test_probe_fails_when_the_device_cannot_be_opened(monkeypatch):
    install(monkeypatch, [])

    def refuse(**kw):
        raise OSError("device in use")

    monkeypatch.setattr(sd, "check_input_settings", refuse)
    with pytest.raises(ClientError, match="Microphone unavailable"):
        await probe_microphone(settings(), seconds=0.1)
