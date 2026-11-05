"""Optional Vosk CPU streaming; models are resident and recognizers are session-local."""

import json
from typing import Any

from .audio import SAMPLE_RATE, AudioChunk
from .config import VOSK_LANGUAGES, Settings
from .engine import Recognition

REQUIRED_FILES = (
    "am/final.mdl",
    "conf/mfcc.conf",
    "conf/model.conf",
    "graph/HCLr.fst",
    "graph/Gr.fst",
    "graph/phones/word_boundary.int",
    "ivector/final.dubm",
    "ivector/final.ie",
    "ivector/final.mat",
    "ivector/global_cmvn.stats",
    "ivector/online_cmvn.conf",
    "ivector/splice.conf",
)


class VoskEngine:
    def __init__(self, settings: Settings):
        if settings.gpu_enabled:
            raise RuntimeError("Vosk GPU requires a separate CUDA build; this adapter supports CPU only")
        path = settings.resolved_model_path
        if not all((path / name).is_file() for name in REQUIRED_FILES):
            raise RuntimeError("local Vosk model missing; run audio-api download-model before starting")
        try:
            import vosk
        except ImportError:
            raise RuntimeError("Vosk is optional; install with uv sync --extra vosk") from None
        self.settings = settings
        self.language = VOSK_LANGUAGES[settings.model_name]
        self.api = vosk
        vosk.SetLogLevel(-1)
        # A path is mandatory: Vosk's lang/model_name convenience options can download silently.
        self.model = vosk.Model(model_path=str(path.resolve()))
        warmup = self.new_session()
        warmup.transcribe(AudioChunk(bytes(SAMPLE_RATE * 2), 0, SAMPLE_RATE, has_speech=False), self.language)

    def new_session(self) -> "VoskStream":
        # Native state is created lazily on the same serialized worker that owns the model.
        return VoskStream(self)

    def transcribe(self, chunk: AudioChunk, language: str) -> Recognition:
        if not chunk.final:
            raise ValueError("incremental audio requires a session engine")
        return self.new_session().transcribe(chunk, language)


class VoskStream:
    def __init__(self, engine: VoskEngine):
        self.engine = engine
        self.recognizer: Any = None
        self.start_sample = 0
        self.end_sample = 0
        self.parts: list[str] = []
        self.text_size = 0

    def _append_result(self, raw: str) -> None:
        limit = self.engine.settings.max_text_chars
        if len(raw) > limit * 8 + 4096:
            raise RuntimeError("transcription output limit exceeded")
        text = json.loads(raw)["text"]
        if not isinstance(text, str):
            raise RuntimeError("invalid recognizer output")
        text = text.strip()
        if text:
            self.text_size += len(text) + bool(self.parts)
            if self.text_size > limit or len(self.parts) >= 512:
                raise RuntimeError("transcription output limit exceeded")
            self.parts.append(text)

    def transcribe(self, chunk: AudioChunk, language: str) -> Recognition:
        if language != self.engine.language:
            raise ValueError("Vosk requires the configured model's explicit language")
        if len(chunk.pcm) != 2 * (chunk.end_sample - chunk.start_sample):
            raise ValueError("invalid audio sample range")
        if self.recognizer is None:
            self.recognizer = self.engine.api.KaldiRecognizer(self.engine.model, SAMPLE_RATE)
            self.start_sample = self.end_sample = chunk.start_sample
        if chunk.start_sample != self.end_sample:
            raise ValueError("non-contiguous streaming audio")
        self.end_sample = chunk.end_sample
        if chunk.pcm and self.recognizer.AcceptWaveform(chunk.pcm):
            # Vosk may endpoint earlier than the service VAD. Preserve every completed piece.
            self._append_result(self.recognizer.Result())
        start = self.start_sample
        if not chunk.final:
            return Recognition("", language, [], final=False, start_sample=start)
        self._append_result(self.recognizer.FinalResult())
        text = " ".join(self.parts) if chunk.has_speech else ""
        self.recognizer = None
        self.parts = []
        self.text_size = 0
        segments: list[dict[str, float | str]] = []
        if text:
            segments.append(
                {
                    "start_seconds": start / SAMPLE_RATE,
                    "end_seconds": chunk.end_sample / SAMPLE_RATE,
                    "text": text,
                }
            )
        return Recognition(text, language, segments, start_sample=start)
