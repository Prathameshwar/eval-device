"""The Silero voice detector and its framing adapter.

These exercise the real ONNX weights that ship with faster-whisper, not a stand-in: the point of
the adapter is that Silero's 512-sample windows and carried LSTM state survive being fed 30 ms
frames, and only the real model can show that. Speech is synthesised rather than recorded so the
suite stays self-contained and deterministic.
"""

import numpy as np
import pytest
import webrtcvad
from conftest import SILENCE

from device_audio.audio import FRAME_BYTES, SAMPLE_RATE, Segmenter
from device_audio.config import Settings
from device_audio.streaming import StreamingSegmenter
from device_audio.vad import (
    CONTEXT_SAMPLES,
    STATE_SHAPE,
    WINDOW_SAMPLES,
    SileroDetector,
    build_detector,
    silero_model_path,
)

VOWELS = [(730, 1090, 2440), (270, 2290, 3010), (570, 840, 2410)]  # /a/, /i/, /o/.


def utterance(seconds=0.8, amp=8000.0):
    """Synthetic syllables: a glottal pulse train with a pitch contour, formants gliding between
    vowel targets, and closures between syllables.

    A steady buzz is not enough. Silero scores a sustained tone at barely 0.5 once it has any
    preceding context, because modulation is most of what distinguishes speech from a machine; this
    stimulus carries that modulation and scores above 0.97 whatever precedes it.
    """
    count = int(seconds * SAMPLE_RATE)
    time = np.arange(count) / SAMPLE_RATE
    pitch = 130 + 25 * np.sin(2 * np.pi * 1.5 * time)
    phase = np.cumsum(2 * np.pi * pitch / SAMPLE_RATE)
    pulses = (np.diff(np.floor(phase / (2 * np.pi)), prepend=0) > 0).astype(float)
    glide = (np.sin(2 * np.pi * 2.5 * time) + 1) / 2 * (len(VOWELS) - 1)
    decay = np.exp(-np.pi * 90 / SAMPLE_RATE)
    signal = np.zeros(count)
    for band, gain in enumerate((1.0, 0.5, 0.25)):
        track = np.interp(glide, np.arange(len(VOWELS)), [vowel[band] for vowel in VOWELS])
        angle = 2 * np.pi * track / SAMPLE_RATE
        # A two-pole resonator stepped per sample, so the formant can actually move mid-syllable.
        resonated = np.zeros(count)
        for at in range(2, count):
            resonated[at] = (
                pulses[at]
                + 2 * decay * np.cos(angle[at]) * resonated[at - 1]
                - decay * decay * resonated[at - 2]
            )
        signal += gain * resonated
    signal *= np.clip(0.55 + 0.75 * np.sin(2 * np.pi * 3.5 * time - 1.2), 0, None) ** 1.5
    return (signal / np.abs(signal).max() * amp).astype("<i2").tobytes()


def noise(seconds=1.0, amp=3000.0, seed=3):
    generator = np.random.default_rng(seed)
    samples = generator.normal(0, amp, int(seconds * SAMPLE_RATE))
    return np.clip(samples, -32768, 32767).astype("<i2").tobytes()


def detector(threshold=0.5):
    return SileroDetector(threshold, silero_model_path(Settings.model_construct(vad_model_path=None)))


def decisions(pcm, engine, frame_bytes=FRAME_BYTES):
    return [
        engine.is_speech(pcm[at : at + frame_bytes], SAMPLE_RATE)
        for at in range(0, len(pcm) - frame_bytes + 1, frame_bytes)
    ]


class ScriptedSession:
    """Returns probabilities from a list, so threshold behaviour can be asserted exactly."""

    def __init__(self, probabilities):
        self.probabilities = list(probabilities)
        self.calls = 0

    def run(self, _outputs, inputs):
        assert inputs["input"].shape == (1, CONTEXT_SAMPLES + WINDOW_SAMPLES)
        value = self.probabilities[min(self.calls, len(self.probabilities) - 1)]
        self.calls += 1
        zeros = np.zeros(STATE_SHAPE, dtype=np.float32)
        return np.array([value], dtype=np.float32), zeros, zeros


# --- Engine selection -------------------------------------------------------------------


def test_silero_is_the_default_engine_and_webrtc_stays_available(settings):
    assert isinstance(build_detector(settings), SileroDetector)
    settings.vad_engine = "webrtc"
    assert isinstance(build_detector(settings), webrtcvad.Vad)


def test_a_missing_model_is_refused_at_configuration_time(tmp_path, settings):
    fields = {"client_tokens": settings.client_tokens, "_env_file": None}
    with pytest.raises(ValueError, match="VAD model not found"):
        Settings(vad_model_path=tmp_path / "absent.onnx", **fields)
    present = tmp_path / "present.onnx"
    present.write_bytes(b"")
    with pytest.raises(ValueError, match="applies only"):
        Settings(vad_engine="webrtc", vad_model_path=present, **fields)


def test_sessions_share_weights_but_never_share_stream_state():
    """`max_sessions` concurrent captures must not each load their own copy of the model, and must
    not contaminate each other's LSTM state."""
    first, second = detector(), detector()
    assert first.session is second.session
    first.is_speech(utterance(0.1), SAMPLE_RATE)
    assert first.h.any() and not second.h.any()


# --- Framing ----------------------------------------------------------------------------


def test_framing_does_not_change_what_the_model_sees(settings):
    """30 ms frames are 480 samples and Silero scores 512, so the adapter re-frames the stream. It
    must produce the frame-size-independent result, or FRAME_MS could not be changed safely."""
    audio = utterance(0.6)
    whole = detector()
    whole.is_speech(audio, SAMPLE_RATE)
    framed = detector()
    decisions(audio, framed)
    assert framed.probability == pytest.approx(whole.probability, abs=1e-5)
    assert framed.h == pytest.approx(whole.h, abs=1e-5)


def test_a_frame_too_short_to_complete_a_window_holds_the_last_decision():
    engine = detector()
    engine.speech = True
    assert engine.is_speech(b"\x00\x00" * 100, SAMPLE_RATE) is True
    assert len(engine.buffer) == 100  # Buffered, not scored and not discarded.


def test_state_and_lookback_carry_across_calls():
    engine = detector()
    engine.is_speech(utterance(0.1), SAMPLE_RATE)
    first = engine.h.copy()
    assert first.any() and engine.context.any()
    engine.is_speech(utterance(0.1), SAMPLE_RATE)
    # faster-whisper's own SileroVADModel zeroes h/c per call; a streaming detector must not.
    assert not np.array_equal(first, engine.h)


def test_audio_the_model_cannot_score_is_refused():
    engine = detector()
    with pytest.raises(ValueError, match="16000 Hz"):
        engine.is_speech(SILENCE, 8000)
    with pytest.raises(ValueError, match="sample-aligned"):
        engine.is_speech(b"\x01", SAMPLE_RATE)


# --- Decisions --------------------------------------------------------------------------


def test_hysteresis_keeps_a_wavering_probability_from_fragmenting_a_word():
    """A probability sitting near the threshold would otherwise flicker speech/quiet every 32 ms
    and split one word into several chunks."""
    engine = SileroDetector(0.5, "unused", session=ScriptedSession([0.9, 0.42, 0.2, 0.9]))
    window = b"\x00\x00" * WINDOW_SAMPLES
    assert engine.is_speech(window, SAMPLE_RATE) is True  # 0.90: engages at the threshold.
    assert engine.is_speech(window, SAMPLE_RATE) is True  # 0.42: under it, above the release.
    assert engine.is_speech(window, SAMPLE_RATE) is False  # 0.20: under the release.
    assert engine.is_speech(window, SAMPLE_RATE) is True


def test_voiced_audio_is_speech_and_digital_silence_is_not():
    assert sum(decisions(utterance(), detector())) > 15
    assert not any(decisions(b"\x00\x00" * SAMPLE_RATE, detector()))


def test_steady_noise_is_not_speech_where_the_energy_detector_says_it_is():
    """The reason silero is the default. webrtcvad scores loud noise as speech, which stops
    quiet_ms from ever reaching silence_ms, so a question ends at max_chunk_seconds instead of at
    the speaker's pause."""
    hiss = noise()
    assert not any(decisions(hiss, detector()))
    assert any(decisions(hiss, webrtcvad.Vad(2)))


# --- Wiring -----------------------------------------------------------------------------


@pytest.mark.parametrize("engine", ["webrtc", "silero"])
def test_both_segmenters_build_their_own_detector_and_find_the_utterance(settings, engine):
    settings.vad_engine = engine
    audio = SILENCE * 10 + utterance(0.8) + SILENCE * 30
    batch = Segmenter(settings)
    chunks = batch.feed(audio) + batch.flush()
    assert len(chunks) == 1 and chunks[0].duration_seconds > 0.5
    live = StreamingSegmenter(settings)
    blocks = live.feed(audio) + live.flush()
    assert blocks and any(block.has_speech for block in blocks)
    assert b"".join(block.pcm for block in blocks) == audio
