from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from training_contracts.languages import LanguageTag

from pms_api.integrations.llm.capabilities import ModelOptions


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConnectionFields(Strict):
    model_definition_id: UUID | None = None
    name: str = Field(min_length=1, max_length=100)
    base_url: str = Field(default="http://127.0.0.1:8787", max_length=512)
    model: str = Field(default="qwen3.5-4b-local", pattern=r"^[a-zA-Z0-9_.:/-]{1,100}$")
    system_prompt: str = Field(
        default="You are a concise, helpful assistant. Reply in the user's language. If unsure, say so.",
        min_length=1,
        max_length=4000,
    )
    provider: Literal["local_llama_cpp", "openai", "openai_compatible", "azure_openai", "anthropic"] = (
        "local_llama_cpp"
    )
    model_options: ModelOptions = Field(default_factory=ModelOptions)
    token_parameter: Literal["max_tokens", "max_completion_tokens"] = "max_tokens"
    stream_usage: bool = True
    instruction_role: Literal["system", "developer"] = "system"
    max_tokens: int = Field(default=256, ge=16, le=4096, strict=True)

    @field_validator("name", "system_prompt")
    @classmethod
    def nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value or "\x00" in value or any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            raise ValueError("A nonblank, valid Unicode value is required")
        return value

    @model_validator(mode="after")
    def protocol(self):
        if self.provider != "local_llama_cpp" and "model" not in self.model_fields_set:
            raise ValueError("An explicit provider model is required")
        if self.provider != "local_llama_cpp" and "max_tokens" not in self.model_fields_set:
            self.max_tokens = 1024
        if self.provider in {"openai", "azure_openai"}:
            if self.provider == "openai" and "base_url" not in self.model_fields_set:
                self.base_url = "https://api.openai.com/v1"
            if "token_parameter" not in self.model_fields_set:
                self.token_parameter = "max_completion_tokens"
            if self.token_parameter != "max_completion_tokens" or not self.stream_usage:
                raise ValueError("OpenAI requires max_completion_tokens and streamed usage")
        if self.provider == "anthropic":
            if "base_url" not in self.model_fields_set:
                self.base_url = "https://api.anthropic.com/v1"
            if self.token_parameter != "max_tokens" or self.instruction_role != "system":
                raise ValueError("Anthropic requires max_tokens and system instructions")
            self.stream_usage = False
        if self.provider in {"openai_compatible", "azure_openai"} and "base_url" not in self.model_fields_set:
            raise ValueError("An explicit compatible API base URL is required")
        if (
            self.model_options.model_family == "gpt_5_reasoning"
            and self.token_parameter != "max_completion_tokens"
        ):
            raise ValueError("Reasoning profiles require max_completion_tokens")
        if self.provider == "local_llama_cpp" and self.model_options.model_dump(exclude_defaults=True):
            raise ValueError("Local model parameters are managed by the local server")
        if self.provider == "local_llama_cpp" and (
            self.max_tokens > 512
            or self.token_parameter != "max_tokens"
            or not self.stream_usage
            or self.instruction_role != "system"
        ):
            raise ValueError("Local Qwen requires its existing bounded protocol settings")
        return self


def validated_key(value):
    if value is not None:
        raw = value.get_secret_value()
        if not raw.isascii() or any(ord(c) < 33 or ord(c) > 126 for c in raw):
            raise ValueError("API key must contain only printable non-space ASCII characters")
    return value


class ConnectionCreate(ConnectionFields):
    api_key: SecretStr = Field(min_length=1, max_length=4096)
    _key = field_validator("api_key")(validated_key)


class ConnectionUpdate(ConnectionFields):
    api_key: SecretStr | None = Field(default=None, min_length=1, max_length=4096)
    _key = field_validator("api_key")(validated_key)
    expected_revision: int = Field(ge=1)
    is_active: bool = True


class Message(Strict):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class Completion(Strict):
    request_key: UUID
    connection_id: UUID
    department_id: UUID | None = None
    practice_id: UUID | None = None
    conversation_id: UUID | None = None
    practice_revision: int | None = Field(default=None, ge=1, le=2147483646, strict=True)
    messages: list[Message] = Field(min_length=1, max_length=13)
    language: LanguageTag = "en"
    stream: bool = True
    profile_revision_id: UUID | None = None
    configuration_hash: str | None = Field(None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def conversation(self):
        if self.conversation_id is not None and self.practice_id is None:
            raise ValueError("Conversation requires a patient selection")
        if (self.practice_id is None) != (self.practice_revision is None):
            raise ValueError("Practice identity and revision must be supplied together")
        if sum(len(m.content) for m in self.messages) > 16000 or self.messages[-1].role != "user":
            raise ValueError("Conversation limit or final role invalid")
        for i, m in enumerate(self.messages):
            if m.role != ("user" if i % 2 == 0 else "assistant") or not m.content.strip():
                raise ValueError("Conversation must alternate user and assistant turns")
        return self
