from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PMS_", env_file=".env", extra="ignore", hide_input_in_errors=True
    )
    bind_host: str = "127.0.0.1"
    port: int = Field(8000, ge=1, le=65535)
    environment: Literal["local", "test", "staging", "production"] = "local"
    vm_local_mode: bool = False
    database_url: SecretStr = SecretStr("postgresql+psycopg://pms_api@127.0.0.1:5432/device_platform")
    worker_database_url: SecretStr | None = None
    retention_database_url: SecretStr | None = None
    migration_database_url: SecretStr | None = None
    db_pool_size: int = Field(5, ge=1, le=50)
    db_max_overflow: int = Field(5, ge=0, le=50)
    oidc_issuer: str = ""
    oidc_audience: str = ""
    oidc_jwks_url: str = ""
    oidc_jwks_file: Path | None = None
    local_auth_enabled: bool = False
    initial_setup_key: SecretStr = SecretStr("")
    local_token_signing_key: SecretStr = SecretStr("")
    local_access_minutes: int = Field(15, ge=5, le=60)
    local_refresh_days: int = Field(30, ge=1, le=90)
    local_browser_session_hours: int = Field(24, ge=1, le=168)
    account_action_hours: int = Field(24, ge=1, le=168)
    token_pepper: SecretStr = SecretStr("")
    media_signing_key: SecretStr = SecretStr("")
    credential_keys: dict[str, SecretStr] = {}
    active_credential_key: str = ""
    cors_origins: list[str] = []
    public_base_url: str = "http://127.0.0.1:8000"
    storage_backend: Literal["local", "s3", "azure"] = "local"
    storage_root: Path = Path(".local/media")
    downloads_root: Path = Path(".local/downloads")
    vm_local_storage_limit_bytes: int = Field(5_000_000_000, ge=100_000_000, le=20_000_000_000)
    storage_bucket: str = ""
    aws_region: str = "us-east-1"
    azure_storage_account: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_sender: str = ""
    smtp_starttls: bool = True
    invitation_base_url: str = "http://localhost:3000/invitations/accept"
    account_action_base_url: str = "http://localhost:3000/account"
    request_max_bytes: int = Field(1_048_576, ge=1024, le=10_485_760)
    worker_poll_seconds: float = Field(2, ge=0.1, le=60)
    worker_lease_seconds: int = Field(180, ge=30, le=900)
    worker_concurrency: int = Field(2, ge=1, le=16)
    external_calls_enabled: bool = False
    processing_mode: Literal["local", "cloud", "custom"] = "local"
    llm_cloud_concurrency: int = Field(4, ge=1, le=16)
    local_history_enabled: bool = True
    local_history_upload_hours: int = Field(24, ge=1, le=24)
    local_history_retention_days: int = Field(7, ge=1, le=7)
    local_history_max_records: int = Field(10000, ge=1, le=100000)
    local_history_max_bytes: int = Field(104857600, ge=1024, le=1073741824)
    speech_enabled: bool = False
    speech_max_seconds: int = Field(30, ge=1, le=120)
    speech_daily_seconds: int = Field(3600, ge=30, le=86400)
    speech_concurrency: int = Field(2, ge=1, le=8)
    session_archive_session_bytes: int = Field(512 * 1024 * 1024, ge=1048576, le=10737418240)
    session_archive_org_bytes: int = Field(5 * 1024 * 1024 * 1024, ge=1048576, le=1099511627776)
    speech_recording_max_bytes: int = Field(100_000_000, ge=1_000_000, le=1_000_000_000)
    speech_retention_days: int = Field(7, ge=1, le=30)
    provider_timeout_seconds: int = Field(90, ge=5, le=600)
    ffprobe_path: str = "ffprobe"
    training_key_file: Path | None = None
    training_lease_seconds: int = Field(30, ge=10, le=60)
    llm_enabled: bool = False
    patient_local_context_tokens: int = Field(2048, ge=512, le=131072)
    patient_remote_context_tokens: int | None = Field(None, ge=512, le=1048576)
    # One generation. Remote reasoning models may need the full connection allowance.
    patient_enabled_languages: list[str] = ["en"]
    patient_conversation_tokens_local: int = Field(128, ge=16, le=4096)
    patient_conversation_tokens_remote: int | None = Field(None, ge=16, le=100000)
    # Up to six completed pairs; native token fitting can shorten this further.
    patient_history_messages_remote: int = Field(12, ge=0, le=40)
    patient_history_messages_local: int = Field(4, ge=0, le=40)
    llm_allowed_ports: list[int] = [8787]
    llm_allowed_base_urls: list[str] = ["https://api.openai.com/v1", "https://api.anthropic.com/v1"]
    llm_timeout_seconds: int = Field(120, ge=5, le=300)
    # Readiness probes only. A provider that misses one window is usually reachable a moment
    # later, and a probe must never be the only reason a question is refused.
    health_timeout_seconds: int = Field(5, ge=1, le=60)
    # Two by default: one retry fixes the single missed window that this was reported for, and
    # bounds the wait before recording at about ten seconds. A flaky link can raise it.
    health_attempts: int = Field(2, ge=1, le=5)
    llm_daily_requests: int = Field(5000, ge=0, le=10000)  # Organization-wide; 0 disables this cap.
    llm_daily_total_tokens: int = Field(5000000, ge=512, le=100000000)
    expose_docs: bool = False
    metrics_token: SecretStr = SecretStr("")

    @model_validator(mode="after")
    def secure_configuration(self):
        setup_key = self.initial_setup_key.get_secret_value()
        if setup_key and (
            not 32 <= len(setup_key) <= 512
            or not setup_key.isascii()
            or any(character.isspace() for character in setup_key)
            or setup_key
            in {
                self.token_pepper.get_secret_value(),
                self.media_signing_key.get_secret_value(),
                self.local_token_signing_key.get_secret_value(),
            }
        ):
            raise ValueError(
                "initial_setup_key requires an independent 32-512 character ASCII secret without spaces"
            )
        for field in ("token_pepper", "media_signing_key"):
            if len(getattr(self, field).get_secret_value()) < 32:
                raise ValueError(
                    f"{field} requires at least 32 characters; use independently generated secrets"
                )
        if self.environment in {"staging", "production"}:
            if self.vm_local_mode:
                if (
                    self.environment != "production"
                    or not self.local_auth_enabled
                    or self.oidc_issuer
                    or self.oidc_audience
                    or self.oidc_jwks_url
                    or self.oidc_jwks_file
                    or self.storage_backend != "local"
                    or self.storage_root.as_posix() != "/var/lib/pms-media"
                    or self.smtp_host
                    or self.smtp_sender
                    or self.smtp_username
                    or self.smtp_password.get_secret_value()
                ):
                    raise ValueError(
                        "VM local mode requires password auth, private VM storage and disabled email/OIDC"
                    )
            else:
                if not self.oidc_issuer.startswith("https://") or not self.oidc_audience:
                    raise ValueError("Deployed environments require HTTPS OIDC issuer and audience")
                if self.oidc_jwks_file or self.storage_backend == "local":
                    raise ValueError(
                        "Local identity/storage/secret fixtures are forbidden in deployed environments"
                    )
            if not self.public_base_url.startswith("https://"):
                raise ValueError("Deployed public_base_url must use HTTPS")
            if "*" in self.cors_origins:
                raise ValueError("Explicit CORS origins are required")
        if self.oidc_jwks_file and self.environment not in {"local", "test"}:
            raise ValueError("Fixture JWKS is only available locally")
        if self.vm_local_mode and self.environment != "production":
            raise ValueError("VM local mode is available only in production")
        if self.local_auth_enabled and len(self.local_token_signing_key.get_secret_value()) < 32:
            raise ValueError("local_token_signing_key requires at least 32 characters")
        if self.local_auth_enabled:
            local_key = self.local_token_signing_key.get_secret_value()
            if local_key in {
                self.token_pepper.get_secret_value(),
                self.media_signing_key.get_secret_value(),
            }:
                raise ValueError("local_token_signing_key must be an independent secret")
            if (
                self.environment in {"staging", "production"}
                and not self.vm_local_mode
                and (
                    not self.smtp_host
                    or not self.smtp_sender
                    or not self.account_action_base_url.startswith("https://")
                )
            ):
                raise ValueError("Deployed local authentication requires SMTP and an HTTPS action URL")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
