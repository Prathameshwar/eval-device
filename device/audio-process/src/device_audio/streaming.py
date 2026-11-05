"""Incremental PCM framing with bounded utterances, without discarding input samples."""

from .audio import FRAME_BYTES, FRAME_SAMPLES, SAMPLE_RATE, AudioChunk, VoiceDetector
from .config import Settings

BLOCK_MS = 150  # Five VAD frames; the model maintains its own 560 ms encoder cadence.


class StreamingSegmenter:
    def __init__(self, settings: Settings, detector: VoiceDetector | None = None):
        if detector is None:
            from .vad import build_detector

            detector = build_detector(settings)
        self.settings = settings
        self.detector = detector
        self.pending = bytearray()
        self.block = bytearray()
        self.total_samples = 0
        self.position = 0
        self.utterance_start = 0
        self.block_start = 0
        self.speech_ms = 0.0
        self.quiet_ms = 0.0

    def feed(self, pcm: bytes) -> list[AudioChunk]:
        if not pcm or len(pcm) % 2:
            raise ValueError("audio must be non-empty, sample-aligned PCM16LE")
        self.total_samples += len(pcm) // 2
        self.pending.extend(pcm)
        chunks = []
        while len(self.pending) >= FRAME_BYTES:
            frame = bytes(self.pending[:FRAME_BYTES])
            del self.pending[:FRAME_BYTES]
            chunks.extend(self._frame(frame, FRAME_SAMPLES))
        return chunks

    def _frame(self, frame: bytes, samples: int) -> list[AudioChunk]:
        speech = self.detector.is_speech(frame, SAMPLE_RATE)
        duration_ms = samples * 1000 / SAMPLE_RATE
        self.speech_ms += duration_ms if speech else 0
        self.quiet_ms = 0 if speech else self.quiet_ms + duration_ms
        self.block.extend(frame[: samples * 2])
        self.position += samples
        final = (
            self.speech_ms > 0 and self.quiet_ms >= self.settings.silence_ms
        ) or self.position - self.utterance_start >= self.settings.max_chunk_seconds * SAMPLE_RATE
        if final or len(self.block) >= BLOCK_MS * SAMPLE_RATE * 2 // 1000:
            return [self._emit(final)]
        return []

    def _emit(self, final: bool) -> AudioChunk:
        chunk = AudioChunk(
            bytes(self.block),
            self.block_start,
            self.position,
            final=final,
            has_speech=self.speech_ms >= self.settings.min_speech_ms,
        )
        self.block.clear()
        self.block_start = self.position
        if final:
            self.utterance_start = self.position
            self.speech_ms = self.quiet_ms = 0
        return chunk

    def flush(self) -> list[AudioChunk]:
        chunks = []
        if self.pending:
            samples = len(self.pending) // 2
            frame = bytes(self.pending).ljust(FRAME_BYTES, b"\0")
            self.pending.clear()
            chunks.extend(self._frame(frame, samples))
        # A zero-byte final marker is needed when the last block already went to inference.
        if self.position > self.utterance_start:
            chunks.append(self._emit(True))
        return chunks
