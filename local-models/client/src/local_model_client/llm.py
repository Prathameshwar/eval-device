"""Patient runner transport through the central inference manager."""

import asyncio
import time

import httpx
from training_contracts.patient_turn import TurnError

from .connection import validate_capabilities
from .native import LocalModel as NativeModel
from .native import finish_reason, object_json, selection_grammar, usage
from .native import message_for as message_for
from .native import new_client as new_client


class LocalModel(NativeModel):
    connection = None

    async def request_json(self, method, path, payload=None):
        if self.connection is not None:
            from .connection import ConnectionError

            try:
                return await self.connection.async_request(method, path, payload)
            except ConnectionError as error:
                raise TurnError("llm_" + error.code, error.status) from None
        try:
            async with asyncio.timeout(self.timeout):
                async with self.client.stream(
                    method, self.root + path, headers=self.headers, json=payload
                ) as response:
                    raw = bytearray()
                    async for block in response.aiter_bytes():
                        raw.extend(block)
                        if len(raw) > 262144:
                            raise TurnError("llm_response_limit")
                    value = object_json(raw)
                    if response.status_code == 409 and value.get("code") == "model_mismatch":
                        raise TurnError("llm_model_mismatch", 503)
                    self.check(response)
                    return value
        except TimeoutError:
            self.budget_cache.clear()
            raise TurnError("llm_timeout", 504) from None
        except httpx.HTTPError:
            self.budget_cache.clear()
            raise TurnError("llm_unavailable", 503) from None

    async def probe(self):
        info = validate_capabilities(await self.request_json("GET", "/v1/capabilities"))
        service = info["services"].get("llm", {})
        if service.get("ready") is not True or service.get("state") != "Ready":
            raise TurnError("llm_unavailable", 503)
        if not any(
            m.get("id") == service.get("model_id") and m.get("alias") == self.model for m in info["models"]
        ):
            raise TurnError("llm_model_mismatch", 503)
        revision = info.get("revision")
        if self.budget_cache.get("manager_revision") != revision:
            self.budget_cache.clear()
            self.budget_cache["manager_revision"] = revision

    async def native_json(self, method, path, payload=None):
        operation = {
            ("GET", "/props"): "props",
            ("POST", "/apply-template"): "apply-template",
            ("POST", "/tokenize"): "tokenize",
        }.get((method, path))
        if operation is None:
            raise TurnError("llm_invalid_parameters", 422)
        return await self.request_json(
            "POST", "/v1/llm/inspect", {"model": self.model, "operation": operation, "payload": payload}
        )

    async def complete(self, messages, max_tokens):
        started = time.monotonic()
        payload = {"model": self.model, "messages": messages, "max_tokens": max_tokens}
        grammar = selection_grammar(messages)
        if grammar is not None:
            payload["grammar"] = grammar
        result = await self.request_json("POST", "/v1/infer/llm", payload)
        choices = result.get("choices")
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
            raise TurnError("llm_invalid_response")
        choice = choices[0]
        message = choice.get("message")
        if not isinstance(message, dict):
            raise TurnError("llm_invalid_response")
        if message.get("refusal"):
            raise TurnError("llm_content_filtered", 422)
        text = message.get("content")
        reason = finish_reason(choice.get("finish_reason"))
        if not isinstance(text, str):
            raise TurnError("llm_invalid_response")
        if len(text.encode("utf-8")) > 32000:
            raise TurnError("llm_response_limit")
        if not text.strip():
            raise TurnError("llm_output_limit" if reason == "length" else "llm_empty_response", 422)
        return {
            "type": "done",
            "text": text,
            "finish_reason": reason,
            "usage": usage(result.get("usage")),
            "first_token_ms": None,
            "total_ms": round((time.monotonic() - started) * 1000),
        }
