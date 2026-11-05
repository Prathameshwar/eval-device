import pytest
from conftest import SILENCE, SPEECH, Detector

from device_audio.audio import FRAME_BYTES, SAMPLE_RATE, Segmenter


def test_fragmented_audio_preserves_offsets_preroll_and_final_tail(settings):
    segmenter = Segmenter(settings, Detector())
    audio = SILENCE * 10 + SPEECH * 6 + SILENCE * 20
    chunks = []
    for position in range(0, len(audio), 142):
        chunks.extend(segmenter.feed(audio[position : position + 142]))
    chunks.extend(segmenter.flush())
    assert len(chunks) == 1
    assert chunks[0].start_sample == 0
    assert chunks[0].end_sample == len(audio) // 2
    assert chunks[0].pcm == audio


def test_partial_frame_is_trimmed_not_padded_in_output(settings):
    segmenter = Segmenter(settings, Detector())
    audio = SPEECH * 6 + SPEECH[:140]
    chunks = segmenter.feed(audio) + segmenter.flush()
    assert len(chunks) == 1
    assert chunks[0].pcm == audio
    assert chunks[0].end_sample == len(audio) // 2


def test_continuous_speech_has_bounded_nonoverlapping_chunks(settings):
    settings.max_chunk_seconds = 1
    segmenter = Segmenter(settings, Detector())
    audio = SPEECH * 100
    chunks = segmenter.feed(audio) + segmenter.flush()
    assert len(chunks) == 3
    assert b"".join(chunk.pcm for chunk in chunks) == audio
    assert all(chunk.duration_seconds <= 1.03 for chunk in chunks)
    assert all(left.end_sample == right.start_sample for left, right in zip(chunks, chunks[1:], strict=False))


def test_silence_never_schedules_inference_and_memory_stays_bounded(settings):
    segmenter = Segmenter(settings, Detector())
    for _ in range(1000):
        assert segmenter.feed(SILENCE) == []
        assert len(segmenter.frames) == 0
        assert len(segmenter.pre_roll) <= settings.pre_roll_ms // 30
        assert len(segmenter.pending) < FRAME_BYTES
    assert segmenter.flush() == []
    assert segmenter.total_samples == SAMPLE_RATE * 30


def test_short_noise_and_odd_byte_input(settings):
    segmenter = Segmenter(settings, Detector())
    assert segmenter.feed(SPEECH + SILENCE * 20) == []
    assert segmenter.flush() == []
    with pytest.raises(ValueError):
        segmenter.feed(b"\x01")
