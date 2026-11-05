"""A fixed conversation identity shared by local and platform execution."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from training_contracts import fingerprint
from training_contracts.languages import LanguageTag, get_pack


class TurnContextRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    conversation_id: UUID
    language_pack_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$", max_length=32)
    language_pack_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    compiler_version: str = Field(pattern=r"^[0-9]{1,8}$")
    prompt_hash: str | None = Field(None, pattern=r"^[a-f0-9]{64}$")


class ConversationContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    conversation_id: UUID
    organization_id: UUID
    owner_id: UUID
    department_id: UUID | None = None
    practice_id: UUID
    practice_revision: int = Field(ge=1)
    case_snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    language: LanguageTag
    language_pack_version: str
    language_pack_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    localization_revision: int = Field(ge=1)
    policy_version: str
    compiler_version: str
    profile_revision_id: UUID | None = None
    configuration_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    connection_id: UUID
    connection_revision: int = Field(ge=1)
    execution: Literal["caller", "platform"]
    input_mode: Literal["text", "speech"] = "text"
    output_mode: Literal["text", "speech"] = "text"
    speech_locale: LanguageTag
    created_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def valid(self):
        if (
            self.created_at.tzinfo is None
            or self.expires_at.tzinfo is None
            or self.expires_at <= self.created_at
        ):
            raise ValueError("Conversation requires a bounded timezone-aware lifetime")
        return self

    def validate_pack(self):
        return get_pack(
            self.language, version=self.language_pack_version, content_hash=self.language_pack_hash
        )

    @property
    def content_hash(self):
        return fingerprint(self.model_dump(mode="json"))
