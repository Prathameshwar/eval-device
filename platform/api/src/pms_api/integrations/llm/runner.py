"""Bind the shared patient-turn pipeline to a provider connection reached from this service.

The shared pipeline owns the prompts, guards and events. This runner owns the socket: it
executes one bounded completion, reaches llama.cpp's native tokenizer routes, and translates
transport-neutral failures into this service's error type.
"""

import httpx
from training_contracts.patient_turn import TurnError

from pms_api.core.common import AppError
from pms_api.integrations.llm.client import LLMError, object_json
from pms_api.integrations.llm.policy import api_base


def app_error(error: TurnError) -> AppError:
    """Preserve the shared pipeline's code, status and message exactly."""
    return AppError(error.status, error.code, error.message)


class ProviderRunner:
    """Adapts one prepared parameter set for the shared pipeline."""

    def __init__(self, client, parameters, settings):
        self.client = client
        self.parameters = {key: value for key, value in parameters.items() if key != "_patient_context"}
        self.provider = parameters["provider"]
        self.remote_context_tokens = (
            parameters.get("context_tokens") or settings.patient_remote_context_tokens
        )
        self.local_context_cap = settings.patient_local_context_tokens

    async def native_json(self, method, path, payload=None):
        base = api_base(self.parameters["base_url"], "local_llama_cpp").removesuffix("/v1")
        key = self.parameters["key"]
        try:
            async with self.client.client.stream(
                method, base + path, headers={"Authorization": "Bearer " + key}, json=payload
            ) as response:
                self.client.check(response)
                data = bytearray()
                async for block in response.aiter_bytes():
                    data.extend(block)
                    if len(data) > 262144:
                        raise LLMError("llm_tokenizer_response_limit")
                return object_json(data)
        except httpx.HTTPError:
            raise TurnError("llm_tokenizer_unavailable", 503) from None

    async def complete(self, messages, max_tokens):
        """One bounded non-streamed turn; provider deltas never reach the caller."""
        result = None
        async for event in self.client.events(
            **{**self.parameters, "messages": messages, "max_tokens": max_tokens, "streaming": True}
        ):
            if event["type"] == "done":
                result = event
        if result is None:
            raise LLMError("llm_incomplete")
        return result
