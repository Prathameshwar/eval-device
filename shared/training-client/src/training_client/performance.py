"""Process-local monotonic timings. No text, media or provider identifiers."""

import threading
import time
from uuid import uuid4

STAGES = {
    "speech_end",
    "endpoint",
    "worker",
    "preflight",
    "request",
    "transcript",
    "model_start",
    "answer",
    "save_start",
    "saved",
    "speech_queued",
    "pcm",
    "output",
    "loopback",
    "playback_end",
}


class TurnTiming:
    def __init__(self, source="speech", *, clock=time.perf_counter):
        self.source = source
        self.turn_id = str(uuid4())
        self._clock = clock
        self._lock = threading.Lock()
        self._points = {}
        self.output_latency_ms = None
        self.underruns = 0
        self.playback_status = None

    def mark(self, stage, *, at=None, replace=False):
        if stage not in STAGES:
            raise ValueError("Unknown performance stage")
        with self._lock:
            if replace or stage not in self._points:
                self._points[stage] = self._clock() if at is None else at

    def snapshot(self):
        with self._lock:
            points = dict(self._points)
            latency, underruns = self.output_latency_ms, self.underruns

        def duration(start, end):
            if start not in points or end not in points:
                return None
            return round(max(0, points[end] - points[start]) * 1000, 2)

        origin = "speech_end" if self.source == "speech" else "worker"
        output = duration(origin, "output")
        return {
            "turn_id": self.turn_id,
            "source": self.source,
            "endpoint_ms": duration("speech_end", "endpoint"),
            "queue_ms": duration("endpoint", "worker"),
            "preflight_ms": duration("worker", "preflight"),
            "transcript_ms": duration("endpoint", "transcript"),
            "preparation_ms": duration("transcript", "model_start"),
            "model_ms": duration("model_start", "answer"),
            "save_ms": duration("save_start", "saved"),
            "first_pcm_ms": duration("answer", "pcm"),
            "output_submission_ms": output,
            "loopback_detection_ms": duration(origin, "loopback"),
            "estimated_audible_ms": round(output + latency, 2)
            if output is not None and latency is not None
            else None,
            "playback_complete_ms": duration(origin, "playback_end"),
            "output_latency_ms": latency,
            "underruns": underruns,
            "playback_status": self.playback_status,
            "slow": output is not None and output + (latency or 0) > 5000,
        }


class PlaybackGate:
    """Synthesis may overlap persistence; no playback until the result is durable."""

    def __init__(self):
        self.finished = threading.Event()
        self.saved = False

    def resolve(self, saved):
        self.saved = bool(saved)
        self.finished.set()

    def wait(self, current):
        while current():
            if self.finished.wait(0.02):
                return self.saved
        return False
