from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def endpoint(value: str, schemes: set[str], local=False):
    u = urlsplit(value)
    if u.scheme not in schemes or not u.hostname or u.username or u.password or u.query or u.fragment:
        raise ValueError("invalid service URL")
    loopback = u.hostname in {"127.0.0.1", "::1"}
    if (local and not loopback) or (u.scheme in {"http", "ws"} and not loopback):
        raise ValueError("remote services require verified TLS; model/media services require loopback")
    return value.rstrip("/")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TRAINING_", env_file=".env", extra="ignore", hide_input_in_errors=True
    )
    organization_id: UUID
    device_id: UUID
    platform_url: str
    public_key_file: Path
    ca_file: Path | None = None
    origin: str = "http://127.0.0.1:8767"
    store: Path = Path(".recordings")
    max_store_bytes: int = Field(1_073_741_824, ge=10_000_000, le=10_737_418_240)
    audio_url: str = "ws://127.0.0.1:8765/v1/audio/stream"
    audio_token: SecretStr
    video_url: str = "ws://127.0.0.1:8766/v1/video/stream"
    video_token: SecretStr
    video_store: Path
    video_client_id: str = "training"
    dialogue_url: str = "http://127.0.0.1:8780"
    dialogue_key_file: Path
    dialogue_model: str = "qwen3-1.7b"
    speech_executable: Path
    io_seconds: float = Field(5, ge=1, le=15)
    response_seconds: float = Field(30, ge=5, le=120)

    @model_validator(mode="after")
    def urls(self):
        self.platform_url = endpoint(self.platform_url, {"http", "https"})
        self.origin = endpoint(self.origin, {"http", "https"})
        self.audio_url = endpoint(self.audio_url, {"ws"}, True)
        self.video_url = endpoint(self.video_url, {"ws"}, True)
        self.dialogue_url = endpoint(self.dialogue_url, {"http"}, True)
        for value in (self.audio_token, self.video_token):
            if len(value.get_secret_value()) < 32:
                raise ValueError("media credentials need at least 32 characters")
        return self
