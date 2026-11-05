"""Voice activity detection behind the `VoiceDetector` protocol.

Two engines are available. `webrtc` is the 2012 GMM energy detector: cheap, and the baseline every
latency and accuracy figure in `docs/` was measured against. `silero` is the neural detector whose
ONNX weights already ship inside faster-whisper, and it holds up far better on breathy speech, soft
consonants and steady background noise, where the energy detector either clips the start of a word
or calls a fan "speech" forever.

Silero works in fixed 512-sample (32 ms) windows and carries an LSTM state plus a 64-sample lookback
between them. `SileroDetector` keeps both across calls, so an incoming stream is scored as one
continuous signal rather than as a series of unrelated frames. That is the difference between a
detector that knows speech is in progress and one that re-decides from nothing 33 times a second:
faster-whisper's own `SileroVADModel` zeroes the state on every call because it scores whole files,
which makes it unsuitable as-is for live framing.
"""

import threading

from .audio import SAMPLE_RATE, VoiceDetector
from .config import Settings

WINDOW_SAMPLES = 512  # The only window size Silero v6 accepts at 16 kHz.
CONTEXT_SAMPLES = 64  # Lookback prepended to each window; carried over from the previous one.
STATE_SHAPE = (1, 1, 128)
RELEASE_MARGIN = 0.15  # Hysteresis: a run of speech ends at a lower probability than it starts.
FULL_SCALE = 32768.0

_sessions: dict[str, object] = {}
_sessions_lock = threading.Lock()


def silero_model_path(settings: Settings) -> str:
    """Prefer the configured file; otherwise use the copy faster-whisper installs."""
    if settings.vad_model_path is not None:
        return str(settings.vad_model_path)
    from pathlib import Path

    from faster_whisper.vad import get_assets_path

    return str(Path(get_assets_path()) / "silero_vad_v6.onnx")


def _shared_session(path: str) -> object:
    """One ONNX session per model file, shared by every concurrent capture session.

    `InferenceSession.run` is thread safe and the per-stream state lives in the detector, so the
    ~1.2 MB of weights is loaded once rather than once per connection. One intra-op thread keeps
    the detector from competing with the transcription model for cores.
    """
    with _sessions_lock:
        session = _sessions.get(path)
        if session is None:
            import onnxruntime

            options = onnxruntime.SessionOptions()
            options.intra_op_num_threads = 1
            options.inter_op_num_threads = 1
            options.log_severity_level = 3
            session = onnxruntime.InferenceSession(
                path, sess_options=options, providers=["CPUExecutionProvider"]
            )
            _sessions[path] = session
        return session


class SileroDetector:
    """Streaming Silero VAD. One instance per capture session: it is stateful and not thread safe."""

    def __init__(self, threshold: float, model_path: str, session: object | None = None):
        import numpy

        self.numpy = numpy
        self.threshold = threshold
        self.release = max(0.01, threshold - RELEASE_MARGIN)
        self.session = session if session is not None else _shared_session(model_path)
        self.buffer = numpy.zeros(0, dtype=numpy.float32)
        self.context = numpy.zeros(CONTEXT_SAMPLES, dtype=numpy.float32)
        self.h = numpy.zeros(STATE_SHAPE, dtype=numpy.float32)
        self.c = numpy.zeros(STATE_SHAPE, dtype=numpy.float32)
        self.probability = 0.0
        self.speech = False

    def is_speech(self, frame: bytes, sample_rate: int) -> bool:
        if sample_rate != SAMPLE_RATE:
            raise ValueError(f"Silero VAD requires {SAMPLE_RATE} Hz audio")
        if len(frame) % 2:
            raise ValueError("audio must be sample-aligned PCM16LE")
        numpy = self.numpy
        samples = numpy.frombuffer(frame, dtype="<i2").astype(numpy.float32) / FULL_SCALE
        self.buffer = numpy.concatenate((self.buffer, samples))
        # A 30 ms frame is 480 samples, so some calls complete no window and some complete two.
        # Holding the previous decision costs at most 32 samples of lag and keeps framing free to
        # stay at whatever FRAME_MS the segmenters use.
        while len(self.buffer) >= WINDOW_SAMPLES:
            window = self.buffer[:WINDOW_SAMPLES]
            self.buffer = self.buffer[WINDOW_SAMPLES:]
            self._score(window)
        return self.speech

    def _score(self, window) -> None:
        numpy = self.numpy
        batch = numpy.concatenate((self.context, window)).reshape(1, -1)
        probabilities, self.h, self.c = self.session.run(  # type: ignore[attr-defined]
            None, {"input": batch, "h": self.h, "c": self.c}
        )
        self.context = window[-CONTEXT_SAMPLES:].copy()
        self.probability = float(probabilities[-1])
        # Hysteresis, as Silero's own utilities do it: start on `threshold`, release lower. Without
        # it a probability hovering at the threshold flickers and fragments a single word.
        if self.probability >= self.threshold:
            self.speech = True
        elif self.probability < self.release:
            self.speech = False


def build_detector(settings: Settings) -> VoiceDetector:
    """The detector a segmenter uses when the caller does not inject one."""
    if settings.vad_engine == "silero":
        return SileroDetector(settings.vad_threshold, silero_model_path(settings))
    import webrtcvad

    return webrtcvad.Vad(settings.vad_aggressiveness)
