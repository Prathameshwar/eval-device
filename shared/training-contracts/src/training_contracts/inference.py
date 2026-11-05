"""Device-to-GPU authorization and media protocol; no framework dependencies."""

from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

ISSUER = "pms-inference-v1"
PATHS = {
    "/v1/capabilities": "metadata",
    "/v1/llm/inspect": "inspect",
    "/v1/infer/llm": "llm",
    "/v1/infer/asr": "asr",
    "/v1/infer/tts": "tts",
    "/v1/stream/audio": "audio",
    "/v1/stream/video": "video",
    "/v1/requests/status": "status",
}


class Binding(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    host_id: UUID
    origin: str = Field(max_length=512)
    tts_voices: list[str] = Field(default_factory=list, max_length=32)
    video_transport: bool = False

    @field_validator("origin")
    @classmethod
    def secure_origin(cls, value):
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or any(c.isspace() for c in value)
        ):
            raise ValueError("Use an HTTPS origin")
        return value.rstrip("/")

    @field_validator("tts_voices")
    @classmethod
    def voices(cls, values):
        if any(not 1 <= len(v) <= 120 or not all(c.isalnum() or c in "_.-" for c in v) for v in values):
            raise ValueError("Invalid voice key")
        return values


class GrantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    host_id: UUID
    origin: str = Field(max_length=512)
    request_id: UUID
    method: Literal["GET", "POST"]
    path: str = Field(max_length=64)
    body_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model: str | None = Field(None, max_length=200)
    voice: str | None = Field(None, max_length=120)
    conversation_id: UUID | None = None
    processing_run_id: UUID | None = None

    @field_validator("path")
    @classmethod
    def inference_only(cls, value):
        if value not in PATHS:
            raise ValueError("Unsupported inference operation")
        return value
