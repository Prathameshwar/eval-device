from dataclasses import dataclass
from typing import Protocol

import numpy as np

from .audio import SAMPLE_RATE, AudioChunk
from .config import Settings


@dataclass(frozen=True)
class Recognition:
    text: str
    language: str
    segments: list[dict[str, float | str]]
    final: bool = True
    start_sample: int | None = None


class Engine(Protocol):
    def transcribe(self, chunk: AudioChunk, language: str) -> Recognition: ...


class StreamingEngine(Engine, Protocol):
    def new_session(self) -> Engine: ...


def create_engine(settings: Settings) -> Engine:
    if settings.engine_name == "vosk":
        from .vosk_engine import VoskEngine

        return VoskEngine(settings)
    if settings.engine_name == "sherpa-onnx":
        from .nemotron import NemotronEngine

        return NemotronEngine(settings)
    return FasterWhisperEngine(settings)


class FasterWhisperEngine:
    def __init__(self, settings: Settings):
        from faster_whisper import WhisperModel

        path = settings.resolved_model_path
        required = ("model.bin", "config.json", "tokenizer.json")
        if not all((path / name).is_file() for name in required):
            # faster-whisper can otherwise fetch a tokenizer even with local_files_only=True.
            raise RuntimeError(
                "local model missing required files; run audio-api download-model before starting"
            )
        if settings.model_name == "whisper-medical-v1":
            from .medical_download import verify_medical

            verify_medical(path)
        self.settings = settings
        if settings.gpu_enabled:
            from .gpu import prepare_whisper_cuda

            prepare_whisper_cuda(settings.gpu_device_index)
        self.model = WhisperModel(
            str(path.resolve()),
            device=settings.inference_device,
            device_index=settings.gpu_device_index if settings.gpu_enabled else 0,
            compute_type=settings.compute_type,
            cpu_threads=settings.cpu_threads,
            num_workers=1,
            local_files_only=True,
        )
        if settings.gpu_enabled and (
            self.model.model.device != "cuda" or self.model.model.compute_type != settings.compute_type
        ):
            raise RuntimeError("GPU execution did not match the requested CUDA compute type")
        # Allocate inference state at startup, before accepting any microphone audio.
        warmup, _ = self.model.transcribe(
            np.zeros(SAMPLE_RATE, dtype=np.float32),
            language="en",
            beam_size=1,
            condition_on_previous_text=False,
            temperature=0.0,
        )
        list(warmup)
        # Load and warm the bundled, cached Silero filter before the first request too.
        from faster_whisper.vad import get_speech_timestamps

        get_speech_timestamps(np.zeros(SAMPLE_RATE, dtype=np.float32))

    def transcribe(self, chunk: AudioChunk, language: str) -> Recognition:
        if language not in self.settings.supported_languages:
            raise ValueError("selected model requires an explicit supported language")
        samples = np.frombuffer(chunk.pcm, dtype="<i2").astype(np.float32) / 32768.0

        def recognize(selected_language: str | None):
            return self.model.transcribe(
                samples,
                language=selected_language,
                task="transcribe",
                beam_size=self.settings.beam_size,
                best_of=1,
                temperature=0.0,
                condition_on_previous_text=False,
                vad_filter=True,
                vad_parameters={"min_speech_duration_ms": 100},
                word_timestamps=False,
            )

        segments, info = recognize(None if language == "auto" else language)
        if language == "auto" and info.language not in self.settings.supported_languages:
            # Short Hindi clips can be identified as Urdu. Auto is restricted to
            # this service's advertised languages, using the model's probabilities.
            # Segments are lazy: no text from the unsupported decoder is consumed.
            candidates = [
                (code, probability)
                for code, probability in info.all_language_probs or []
                if code != "auto" and code in self.settings.supported_languages and 0 <= probability <= 1
            ]
            if not candidates:
                raise RuntimeError("automatic transcription could not select a supported language")
            selected = max(candidates, key=lambda item: item[1])[0]
            segments, info = recognize(selected)
        output: list[dict[str, float | str]] = []
        texts = []
        size = 0
        offset = chunk.start_sample / SAMPLE_RATE
        duration = chunk.duration_seconds
        for segment in segments:
            text = segment.text.strip()
            size += len(text)
            if size > self.settings.max_text_chars or len(output) >= 512:
                raise RuntimeError("transcription output limit exceeded")
            if text:
                texts.append(text)
                output.append(
                    {
                        "start_seconds": offset + min(duration, max(0.0, segment.start)),
                        "end_seconds": offset + min(duration, max(0.0, segment.end)),
                        "text": text,
                    }
                )
        return Recognition(" ".join(texts), info.language, output)
