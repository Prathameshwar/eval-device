"""Explicit model capabilities; Azure deployment labels are not model IDs."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Shared with the laptop runtime so a local turn reports usage the same way.
from training_contracts.patient_turn import aggregate_usage as aggregate_usage


class ModelOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_family: Literal["generic", "gpt_4_1", "gpt_5_reasoning"] = "generic"
    context_tokens: int | None = Field(None, ge=512, le=1048576, strict=True)
    temperature: float | None = Field(None, ge=0, le=2, allow_inf_nan=False)
    reasoning_effort: Literal["none", "low", "medium", "high", "xhigh", "max"] | None = None
    # Ask an OpenAI-compatible server to render the chat template with thinking turned
    # off. Support is per deployment, not per protocol: a server that does not recognise
    # the key ignores it. Measured on nemotron-3-super-120b it cut routing latency about
    # threefold AND collapsed routing accuracy to 4.5%, so it is off unless a specific
    # model has been measured with it on. A local llama.cpp model always renders with
    # thinking disabled and ignores this flag.
    disable_thinking: bool = False

    @model_validator(mode="after")
    def compatible(self):
        if self.model_family == "gpt_5_reasoning":
            if self.temperature is not None:
                raise ValueError("Reasoning model profiles omit temperature")
        elif self.reasoning_effort is not None:
            raise ValueError("Reasoning effort requires an explicit reasoning model profile")
        return self


def options_for(connection):
    return ModelOptions.model_validate(getattr(connection, "model_options", None) or {})


def generation_options(connection):
    options = options_for(connection)
    if connection.provider == "local_llama_cpp":
        return {}
    return {
        "context_tokens": options.context_tokens,
        "temperature": options.temperature,
        "reasoning_effort": options.reasoning_effort,
        "disable_thinking": options.disable_thinking,
    }
