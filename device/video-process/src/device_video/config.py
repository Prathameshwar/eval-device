import re
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOOPBACK = {"127.0.0.1", "::1", "localhost"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VIDEO_", env_file=".env", extra="ignore", hide_input_in_errors=True
    )
    client_tokens: dict[str, SecretStr] = Field(default_factory=dict)
    host: str = "127.0.0.1"
    port: int = Field(default=8766, ge=1, le=65535)
    tls_cert: Path | None = None
    tls_key: Path | None = None
    max_sessions: int = Field(default=2, ge=1, le=8)
    max_width: int = Field(default=1280, ge=16, le=1920)
    max_height: int = Field(default=720, ge=16, le=1080)
    max_fps: int = Field(default=15, ge=1, le=30)
    max_frame_bytes: int = Field(default=524288, ge=4096, le=2097152)
    max_session_seconds: float = Field(default=600, ge=1, le=3600)
    idle_seconds: float = Field(default=15, ge=0.1, le=120)
    send_seconds: float = Field(default=5, ge=0.1, le=30)
    disk_wait_seconds: float = Field(default=5, ge=0.1, le=30)
    queue_bytes: int = Field(default=8388608, ge=65536, le=67108864)
    queue_items: int = Field(default=128, ge=4, le=1024)
    segment_bytes: int = Field(default=2097152, ge=65536, le=8388608)
    segment_seconds: float = Field(default=2, ge=0.1, le=10)
    recording_dir: Path = Path(".recordings")
    recording_max_bytes: int = Field(default=1000000000, ge=262144, le=1000000000000)
    recording_max_sessions: int = Field(default=1000, ge=1, le=10000)
    retention_hours: float = Field(default=168, ge=0.001, le=8760)
    min_free_bytes: int = Field(default=67108864, ge=0, le=10000000000)
    retry_attempts: int = Field(default=3, ge=1, le=5)
    retry_delay_seconds: float = Field(default=0.05, ge=0.001, le=0.25)

    @model_validator(mode="after")
    def validate_settings(self) -> "Settings":
        if not self.client_tokens:
            raise ValueError("run video-api init-local to configure VIDEO_CLIENT_TOKENS")
        tokens = []
        for identity, secret in self.client_tokens.items():
            token = secret.get_secret_value()
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", identity):
                raise ValueError("invalid client ID")
            if len(token) < 32 or not token.isascii() or any(c.isspace() for c in token):
                raise ValueError("tokens require at least 32 non-whitespace ASCII characters")
            tokens.append(token)
        if len(tokens) != len(set(tokens)):
            raise ValueError("client tokens must be distinct")
        if bool(self.tls_cert) != bool(self.tls_key):
            raise ValueError("configure both VIDEO_TLS_CERT and VIDEO_TLS_KEY")
        if self.host not in LOOPBACK and not self.tls_cert:
            raise ValueError("Wi-Fi binding requires TLS")
        if self.max_frame_bytes > self.segment_bytes or self.segment_bytes > self.queue_bytes:
            raise ValueError("require max_frame_bytes <= segment_bytes <= queue_bytes")
        return self
