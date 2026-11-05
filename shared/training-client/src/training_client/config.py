from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from training_contracts.languages import DEFAULT_REGISTRY, LanguageTag, get_pack
from training_contracts.languages.speech_models import recognition_languages

from .connection import DEFAULT_PLATFORM
from .input_filter import DEFAULT_DICTIONARY


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TRAINING_CLIENT_", extra="ignore", hide_input_in_errors=True
    )
    # Hosts must choose their own writable application directory; installed package
    # locations never determine credential, recording or journal storage.
    app_root: Path
    pms_url: str = DEFAULT_PLATFORM
    pms_token: SecretStr = SecretStr("")
    organization_id: UUID | None = None
    connection_id: UUID | None = None
    use_pms_models: bool = False
    processing_profile_id: UUID | None = None
    device_id: UUID | None = None
    # Inference-only credentials; no lifecycle/operator access.
    local_models_key: SecretStr = SecretStr("")
    local_models_port: int = Field(8790, ge=1024, le=65535)
    local_models_state_dir: Path | None = None
    inference_url: str | None = None
    inference_host_id: UUID | None = None
    inference_ca_file: Path | None = None
    speaker_device_name: str | None = Field(default=None, max_length=200)
    local_models_capabilities: dict = Field(default_factory=dict)
    audio_mode: Literal["local", "cloud"] = "local"
    speech_input_enabled: bool = True
    department_id: UUID | None = None
    audio_model: str = "large-v3"
    audio_device: Literal["cpu", "cuda"] = "cpu"
    microphone: int | None = None
    # Device indices reorder across reboots and USB re-enumeration, so the name is authoritative
    # and the index is only a fallback.
    microphone_name: str | None = Field(default=None, max_length=200)
    microphone_strict: bool = False
    microphone_native_rate: Literal[16000, 44100, 48000] | None = None
    camera_index: int = Field(0, ge=0, le=9)
    video_recording_dir: Path = Path(".local/video-recordings")
    video_max_session_seconds: int = Field(3600, ge=10, le=7200)
    video_quota_mb: int = Field(5120, ge=64, le=102400)
    video_min_free_mb: int = Field(512, ge=64, le=10240)
    session_sync_enabled: bool = True
    session_sync_background: bool = False
    session_sync_dir: Path = Path(".local/session-sync")
    session_sync_max_bytes: int = Field(5 * 1024 * 1024 * 1024, ge=1048576, le=107374182400)
    session_sync_bytes_per_second: int = Field(512 * 1024, ge=32768, le=10485760)
    history_enabled: bool = True
    history_dir: Path = Path(".local/conversation-outbox")
    history_queue_records: int = Field(64, ge=1, le=256)
    history_queue_bytes: int = Field(8 * 1024 * 1024, ge=131072, le=32 * 1024 * 1024)
    history_max_records: int = Field(1000, ge=1, le=10000)
    history_max_bytes: int = Field(64 * 1024 * 1024, ge=131072, le=1024 * 1024 * 1024)
    history_pending_hours: int = Field(24, ge=1, le=24)
    input_ignore_file: Path = DEFAULT_DICTIONARY
    language: LanguageTag = "en"
    streaming: bool = True
    speaker_output: bool = True
    # Installed voice key reported by Manage Local Models; unset follows the patient's sex and language.
    voice: str | None = Field(default=None, max_length=64)
    max_question_seconds: int = Field(30, ge=3, le=60)
    silence_ms: int = Field(800, ge=600, le=2000)
    # The speech gate's lower bound. A quiet room uses exactly this; a noisy one raises the bar to
    # `noise_multiplier` times the measured floor, up to `energy_ceiling`.
    energy_threshold: int = Field(400, ge=50, le=5000)
    energy_ceiling: int = Field(5000, ge=50, le=20000)
    noise_multiplier: float = Field(3.0, ge=1.0, le=10.0)
    calibration_ms: int = Field(300, ge=50, le=2000)
    # Consecutive voiced blocks (50 ms each) before a silence may end the question. Counting
    # consecutive blocks is what stops an isolated cough or chair scrape from arming the endpoint.
    min_voiced_blocks: int = Field(3, ge=1, le=20)
    # Blocks the capture may lose to a stalled loop or device overrun before the turn is refused.
    max_lost_blocks: int = Field(20, ge=0, le=200)
    # How long a single-question capture may stay silent before it gives up, and so only a
    # bound on `capture.microphone`. A listening session never ends on silence: it holds one
    # stream open and simply produces no question, so this does not pace an interview.
    no_speech_seconds: float = Field(5.0, ge=1.0, le=30.0)
    timeout_seconds: int = Field(180, ge=10, le=600)
    speech_retry_rounds: int = Field(10, ge=1, le=10)
    speech_retry_round_pause_seconds: int = Field(3, ge=0, le=60)

    def resolve_path(self, path):
        path = Path(path).expanduser()
        return path if path.is_absolute() else self.app_root / path

    @model_validator(mode="after")
    def paths(self):
        self.app_root = self.app_root.expanduser().absolute()
        for name in ("video_recording_dir", "session_sync_dir", "history_dir", "input_ignore_file"):
            setattr(self, name, self.resolve_path(getattr(self, name)))
        return self

    @property
    def language_choices(self):
        installed = tuple(pack.language for pack in DEFAULT_REGISTRY.all())
        if self.audio_mode == "cloud" or not self.speech_input_enabled:
            return installed
        declared = recognition_languages(self.audio_model)
        return tuple(language for language in installed if language in declared)

    @field_validator("language")
    @classmethod
    def installed_language(cls, value):
        return get_pack(value).language

    @field_validator(
        "organization_id",
        "connection_id",
        "processing_profile_id",
        "device_id",
        "department_id",
        mode="before",
    )
    @classmethod
    def optional_identifier(cls, value):
        # The editable example leaves optional selections blank.
        return None if value == "" else value

    @model_validator(mode="after")
    def gate(self):
        if self.energy_ceiling < self.energy_threshold:
            raise ValueError("energy_ceiling must not be below energy_threshold")
        if self.no_speech_seconds >= self.max_question_seconds:
            # Otherwise a silent question fails on the duration limit, which reads as the learner's
            # fault rather than as a microphone that heard nothing.
            raise ValueError("no_speech_seconds must be below max_question_seconds")
        return self

    @model_validator(mode="after")
    def urls(self):
        if self.language not in self.language_choices:
            raise ValueError("Selected speech model requires language=" + ",".join(self.language_choices))
        for raw, schemes in ((self.pms_url, ("http", "https")),):
            url = urlsplit(raw)
            if (
                url.scheme not in schemes
                or url.username
                or url.password
                or url.query
                or url.fragment
                or not url.hostname
            ):
                raise ValueError("Invalid service URL")
            if url.scheme in ("http", "ws") and url.hostname not in ("127.0.0.1", "::1"):
                raise ValueError("Remote services require verified TLS")
        if urlsplit(self.pms_url).path not in (
            "",
            "/",
        ):
            raise ValueError("Invalid service path")
        return self

    def require_credentials(self):
        if (
            not self.organization_id
            or (not self.use_pms_models and not self.connection_id)
            or not self.pms_token.get_secret_value()
        ):
            raise RuntimeError(
                "Configure PMS login and device enrollment, then ask Platform Admin to assign models"
            )
