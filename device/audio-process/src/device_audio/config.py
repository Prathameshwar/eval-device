from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MODEL_NAMES = (
    "tiny",
    "base",
    "small",
    "medium",
    "large-v3",
    "large-v3-turbo",
    "whisper-medical-v1",
    "nemotron-3.5-asr-streaming-0.6b",
    "vosk-model-small-en-us-0.15",
    "vosk-model-small-hi-0.22",
)
VOSK_LANGUAGES = {"vosk-model-small-en-us-0.15": "en", "vosk-model-small-hi-0.22": "hi"}
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AUDIO_", env_file=".env", extra="ignore", hide_input_in_errors=True
    )

    client_tokens: dict[str, SecretStr] = Field(default_factory=dict)
    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1, le=65535)
    tls_cert: Path | None = None
    tls_key: Path | None = None
    model_name: Literal[
        "tiny",
        "base",
        "small",
        "medium",
        "large-v3",
        "large-v3-turbo",
        "whisper-medical-v1",
        "nemotron-3.5-asr-streaming-0.6b",
        "vosk-model-small-en-us-0.15",
        "vosk-model-small-hi-0.22",
    ] = "large-v3"
    model_path: Path | None = None
    gpu_enabled: bool = False
    gpu_device_index: int = Field(default=0, ge=0, le=15)
    cpu_threads: int = Field(default=4, ge=1, le=64)
    beam_size: int = Field(default=1, ge=1, le=5)
    max_sessions: int = Field(default=2, ge=1, le=8)
    chunk_queue_size: int = Field(default=2, ge=1, le=8)
    streaming_queue_ms: int = Field(default=5000, ge=500, le=30000)
    max_chunk_seconds: float = Field(default=8.0, ge=1, le=30)
    min_speech_ms: int = Field(default=180, ge=30, le=1000)
    silence_ms: int = Field(default=600, ge=90, le=2000)
    pre_roll_ms: int = Field(default=300, ge=0, le=1000)
    # "silero" is the neural detector bundled with faster-whisper. "webrtc" is the older energy
    # detector: it costs less but calls every frame speech below about 10 dB SNR, which stops
    # silence_ms from ever elapsing and cuts questions at max_chunk_seconds instead of at the
    # speaker's pause. See device_audio.vad and docs/vad-engine-comparison.md.
    vad_engine: Literal["webrtc", "silero"] = "silero"
    vad_aggressiveness: int = Field(default=2, ge=0, le=3)  # webrtc only.
    vad_threshold: float = Field(default=0.5, ge=0.05, le=0.95)  # silero only.
    vad_model_path: Path | None = None  # silero only; defaults to the faster-whisper asset.
    max_audio_seconds: int = Field(default=600, ge=1, le=3600)
    max_session_seconds: int = Field(default=900, ge=10, le=7200)
    idle_timeout_seconds: float = Field(default=30, ge=1, le=120)
    inference_timeout_seconds: float = Field(default=180, ge=1, le=900)
    model_load_timeout_seconds: float = Field(default=180, ge=1, le=900)
    inference_shutdown_seconds: float = Field(default=5, ge=0.1, le=30)
    drain_timeout_seconds: float = Field(default=300, ge=1, le=1800)
    send_timeout_seconds: float = Field(default=5, ge=0.1, le=30)
    max_frame_bytes: int = Field(default=16000, ge=960, le=32000)
    max_text_chars: int = Field(default=12000, ge=100, le=50000)
    console_output: bool = True
    recording_enabled: bool = True
    recording_retry_attempts: int = Field(default=3, ge=1, le=5)
    recording_retry_delay_seconds: float = Field(default=0.05, ge=0.01, le=0.25)
    recording_dir: Path = Path(".recordings")
    recording_queue_items: int = Field(default=256, ge=4, le=4096)
    recording_queue_bytes: int = Field(default=2097152, ge=32768, le=67108864)
    recording_pending_sessions: int = Field(default=8, ge=1, le=64)
    recording_max_bytes: int = Field(default=1000000000, ge=32768, le=1000000000000)
    recording_max_sessions: int = Field(default=1000, ge=1, le=10000)
    recording_retention_hours: float = Field(default=168, ge=1, le=8760)
    recording_min_free_bytes: int = Field(default=67108864, ge=0, le=10000000000)
    recording_flush_seconds: float = Field(default=1, ge=0.05, le=10)
    recording_cleanup_seconds: float = Field(default=60, ge=1, le=3600)
    recording_startup_seconds: float = Field(default=5, ge=0.1, le=30)
    recording_shutdown_seconds: float = Field(default=5, ge=0.1, le=30)
    callback_url: SecretStr | None = None
    callback_token: SecretStr | None = None
    callback_retry_attempts: int = Field(default=3, ge=1, le=5)
    callback_retry_delay_seconds: float = Field(default=0.2, ge=0.01, le=1)
    callback_timeout_seconds: float = Field(default=5, ge=0.1, le=30)
    callback_queue_size: int = Field(default=8, ge=1, le=64)
    callback_workers: int = Field(default=2, ge=1, le=4)

    @property
    def inference_device(self) -> str:
        return "cuda" if self.gpu_enabled else "cpu"

    @property
    def effective_cpu_threads(self) -> int | None:
        # Vosk Python has no equivalent per-recognizer thread-count option.
        return None if self.model_name in VOSK_LANGUAGES else self.cpu_threads

    @property
    def compute_type(self) -> str:
        if self.model_name in VOSK_LANGUAGES:
            return "model_default"
        return "int8_float16" if self.gpu_enabled else "int8"

    @property
    def streaming(self) -> bool:
        return self.model_name == "nemotron-3.5-asr-streaming-0.6b" or self.model_name in VOSK_LANGUAGES

    @property
    def engine_name(self) -> str:
        if self.model_name in VOSK_LANGUAGES:
            return "vosk"
        return "sherpa-onnx" if self.streaming else "faster-whisper"

    @property
    def supported_languages(self) -> tuple[str, ...]:
        if self.model_name == "whisper-medical-v1":
            return ("en",)
        if self.model_name in VOSK_LANGUAGES:
            return (VOSK_LANGUAGES[self.model_name],)
        return ("auto", "hi", "en")

    @property
    def resolved_model_path(self) -> Path:
        return self.model_path or Path(".models") / self.model_name

    @model_validator(mode="after")
    def validate_settings(self) -> "Settings":
        import re

        if self.gpu_enabled and self.streaming:
            raise ValueError(
                "GPU mode currently supports Whisper models; set AUDIO_GPU_ENABLED=false for Nemotron/Vosk"
            )
        if not self.client_tokens:
            raise ValueError("configure at least one AUDIO_CLIENT_TOKENS entry; run audio-api init-local")
        values = []
        for client_id, token in self.client_tokens.items():
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", client_id):
                raise ValueError("client IDs must contain 1-64 letters, digits, underscores or hyphens")
            value = token.get_secret_value()
            if len(value) < 32 or not value.isascii() or any(c.isspace() for c in value):
                raise ValueError("client tokens must contain at least 32 non-whitespace ASCII characters")
            values.append(value)
        if len(values) != len(set(values)):
            raise ValueError("each client must have a distinct token")
        if bool(self.tls_cert) != bool(self.tls_key):
            raise ValueError("configure both AUDIO_TLS_CERT and AUDIO_TLS_KEY")
        if self.host not in LOOPBACK_HOSTS and not self.tls_cert:
            raise ValueError("non-loopback binding requires AUDIO_TLS_CERT and AUDIO_TLS_KEY")
        if self.min_speech_ms >= self.max_chunk_seconds * 1000:
            raise ValueError("minimum speech must be shorter than the maximum chunk")
        if self.vad_model_path is not None:
            if self.vad_engine != "silero":
                raise ValueError("AUDIO_VAD_MODEL_PATH applies only to AUDIO_VAD_ENGINE=silero")
            if not self.vad_model_path.is_file():
                raise ValueError(f"VAD model not found: {self.vad_model_path}")
        if self.callback_url:
            try:
                url = urlsplit(self.callback_url.get_secret_value())
                port = url.port
            except ValueError:
                raise ValueError("invalid callback URL") from None
            if (
                url.scheme not in {"http", "https"}
                or not url.hostname
                or url.username is not None
                or url.password is not None
                or url.fragment
                or (port is not None and not 1 <= port <= 65535)
            ):
                raise ValueError("callback must be an HTTP(S) URL without credentials or fragment")
            if url.scheme == "http" and url.hostname not in LOOPBACK_HOSTS:
                raise ValueError("non-loopback callbacks require HTTPS")
        if self.callback_token:
            value = self.callback_token.get_secret_value()
            if not value or not value.isascii() or any(c.isspace() for c in value):
                raise ValueError("callback token must contain non-whitespace ASCII characters")
        return self
