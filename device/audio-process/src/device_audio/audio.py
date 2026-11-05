"""Bounded 16 kHz PCM segmentation. No audio files or rolling transcript storage."""

from collections import deque
from dataclasses import dataclass
from typing import Protocol

from .config import Settings

SAMPLE_RATE = 16000
FRAME_MS = 30
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000
FRAME_BYTES = FRAME_SAMPLES * 2


class VoiceDetector(Protocol):
    def is_speech(self, frame: bytes, sample_rate: int) -> bool: ...


@dataclass(frozen=True)
class AudioChunk:
    pcm: bytes
    start_sample: int
    end_sample: int
    final: bool = True
    has_speech: bool = True

    @property
    def duration_seconds(self) -> float:
        return (self.end_sample - self.start_sample) / SAMPLE_RATE


class Segmenter:
    def __init__(self, settings: Settings, detector: VoiceDetector | None = None):
        if detector is None:
            from .vad import build_detector

            detector = build_detector(settings)
        self.detector = detector
        self.settings = settings
        self.pending = bytearray()
        self.pre_roll: deque[tuple[int, bytes]] = deque(maxlen=settings.pre_roll_ms // FRAME_MS)
        self.frames: list[bytes] = []
        self.position = 0
        self.start = 0
        self.speech_ms = 0
        self.quiet_ms = 0
        self.total_samples = 0

    def feed(self, pcm: bytes) -> list[AudioChunk]:
        if not pcm or len(pcm) % 2:
            raise ValueError("audio must be non-empty, sample-aligned PCM16LE")
        self.total_samples += len(pcm) // 2
        self.pending.extend(pcm)
        chunks = []
        while len(self.pending) >= FRAME_BYTES:
            frame = bytes(self.pending[:FRAME_BYTES])
            del self.pending[:FRAME_BYTES]
            chunk = self._frame(frame, FRAME_SAMPLES)
            if chunk:
                chunks.append(chunk)
        return chunks

    def _frame(self, frame: bytes, samples: int) -> AudioChunk | None:
        speech = self.detector.is_speech(frame, SAMPLE_RATE)
        actual_frame = frame[: samples * 2]
        if not self.frames and speech:
            self.start = self.pre_roll[0][0] if self.pre_roll else self.position
            self.frames.extend(value for _, value in self.pre_roll)
            self.pre_roll.clear()
        if self.frames or speech:
            self.frames.append(actual_frame)
            self.speech_ms += FRAME_MS if speech else 0
            self.quiet_ms = 0 if speech else self.quiet_ms + FRAME_MS
        else:
            self.pre_roll.append((self.position, actual_frame))
        self.position += samples
        if self.frames and (
            self.quiet_ms >= self.settings.silence_ms
            or (self.position - self.start) / SAMPLE_RATE >= self.settings.max_chunk_seconds
        ):
            return self._emit()
        return None

    def _emit(self) -> AudioChunk | None:
        chunk = None
        if self.frames and self.speech_ms >= self.settings.min_speech_ms:
            chunk = AudioChunk(b"".join(self.frames), self.start, self.position)
        self.frames.clear()
        self.pre_roll.clear()
        self.speech_ms = self.quiet_ms = 0
        return chunk

    def flush(self) -> list[AudioChunk]:
        chunks = []
        if self.pending:
            samples = len(self.pending) // 2
            frame = bytes(self.pending).ljust(FRAME_BYTES, b"\0")
            self.pending.clear()
            chunk = self._frame(frame, samples)
            if chunk:
                chunks.append(chunk)
        chunk = self._emit()
        if chunk:
            chunks.append(chunk)
        self.pre_roll.clear()
        return chunks
