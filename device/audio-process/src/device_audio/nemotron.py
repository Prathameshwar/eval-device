"""Resident CPU model and per-connection streaming state. Native calls stay on SerialWorker."""

import sys
from pathlib import Path
from typing import Any

import numpy as np

from .audio import SAMPLE_RATE, AudioChunk
from .config import Settings
from .engine import Recognition
from .model_download import MODEL_FILES

_windows_ort: Any = None


def prepare_sherpa_runtime() -> None:
    global _windows_ort
    if sys.platform == "win32" and _windows_ort is None:
        import ctypes

        import onnxruntime

        # sherpa's wheel uses the C API DLL. An old system copy can otherwise win
        # Windows DLL resolution, even after importing the Python onnxruntime module.
        path = Path(onnxruntime.__file__).resolve().parent / "capi" / "onnxruntime.dll"
        if not path.is_file():
            raise RuntimeError("install the locked onnxruntime CPU dependency before serving")
        _windows_ort = ctypes.WinDLL(str(path))


class NemotronEngine:
    def __init__(self, settings: Settings):
        path = settings.resolved_model_path.resolve()
        if not all((path / name).is_file() for name in MODEL_FILES):
            raise RuntimeError("local Nemotron model missing; run audio-api download-model before starting")
        prepare_sherpa_runtime()
        import sherpa_onnx

        self.settings = settings
        self.model = sherpa_onnx.OnlineRecognizer.from_transducer(
            encoder=str(path / "encoder.int8.onnx"),
            decoder=str(path / "decoder.int8.onnx"),
            joiner=str(path / "joiner.int8.onnx"),
            tokens=str(path / "tokens.txt"),
            num_threads=settings.cpu_threads,
            sample_rate=SAMPLE_RATE,
            feature_dim=128,
            decoding_method="greedy_search",
            enable_endpoint_detection=False,
            provider="cpu",
        )
        self.transcribe(AudioChunk(bytes(SAMPLE_RATE * 2), 0, SAMPLE_RATE, has_speech=False), "en")

    def new_session(self) -> "NemotronStream":
        # Cheap Python state only. Native stream creation occurs on the inference worker.
        return NemotronStream(self)

    def transcribe(self, chunk: AudioChunk, language: str) -> Recognition:
        # Whole-clip benchmark compatibility. Live API uses new_session() and incremental blocks.
        if not chunk.final:
            raise ValueError("incremental audio requires a session engine")
        return self.new_session().transcribe(chunk, language)


class NemotronStream:
    def __init__(self, engine: NemotronEngine):
        self.engine = engine
        self.stream: Any = None
        self.start_sample = 0
        self.end_sample = 0
        self.language = "auto"

    def transcribe(self, chunk: AudioChunk, language: str) -> Recognition:
        model = self.engine.model
        if self.stream is None:
            self.stream = model.create_stream()
            self.stream.set_option("language", language)
            self.start_sample = self.end_sample = chunk.start_sample
            self.language = language
        if chunk.start_sample != self.end_sample or language != self.language:
            raise ValueError("non-contiguous streaming audio or changed language")
        self.end_sample = chunk.end_sample
        if chunk.pcm:
            samples = np.frombuffer(chunk.pcm, dtype="<i2").astype(np.float32) / 32768.0
            self.stream.accept_waveform(SAMPLE_RATE, samples)
        if chunk.final:
            # Flush encoder lookahead; synthetic padding is never recorded or counted as input.
            self.stream.accept_waveform(SAMPLE_RATE, np.zeros(int(0.66 * SAMPLE_RATE), dtype=np.float32))
            self.stream.input_finished()
        while model.is_ready(self.stream):
            model.decode_stream(self.stream)
        text = model.get_result(self.stream).strip()
        if len(text) > self.engine.settings.max_text_chars:
            raise RuntimeError("transcription output limit exceeded")
        start = self.start_sample
        if not chunk.final:
            return Recognition("", language, [], final=False, start_sample=start)
        self.stream = None
        if not chunk.has_speech:
            text = ""
        segments: list[dict[str, float | str]] = []
        if text:
            segments.append(
                {
                    "start_seconds": start / SAMPLE_RATE,
                    "end_seconds": chunk.end_sample / SAMPLE_RATE,
                    "text": text,
                }
            )
        # sherpa strips language tags; auto is kept explicit rather than inventing a detected language.
        return Recognition(text, language, segments, start_sample=start)
