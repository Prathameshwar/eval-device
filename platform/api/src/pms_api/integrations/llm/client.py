import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import quote

import httpx

from pms_api.core.common import AppError
from pms_api.integrations.llm.policy import api_base
from pms_api.integrations.llm.policy import endpoint as endpoint
from pms_api.integrations.llm.transport import GuardedTransport

# Backoff between readiness attempts. Short on purpose: this runs while an operator waits to
# start recording, and the whole probe is bounded by LLMClient.health_deadline.
HEALTH_BACKOFF = (0.25, 0.75)


class LLMError(AppError):
    def __init__(self, code="llm_unavailable", status=502):
        super().__init__(status, code, "Language-model request failed; it was not retried")


def credential_headers(key, provider):
    # Stored Azure credentials are resource API keys, not Entra access tokens.
    if provider == "anthropic":
        return {"x-api-key": key, "anthropic-version": "2023-06-01"}
    return {"api-key": key} if provider == "azure_openai" else {"Authorization": "Bearer " + key}


def object_json(raw):
    try:
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            raise ValueError()
        return obj
    except (ValueError, UnicodeError):
        raise LLMError("llm_invalid_response") from None


def finish(value):
    if value == "content_filter":
        raise LLMError("llm_content_filtered", 422)
    if value not in ("stop", "length"):
        raise LLMError("llm_invalid_response")
    return value


def usage(value):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise LLMError("llm_invalid_response")
    result: dict[str, Any] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if key in value:
            n = value[key]
            if type(n) is not int or not 0 <= n <= 1000000:
                raise LLMError("llm_invalid_response")
            result[key] = n
    if all(k in result for k in ("prompt_tokens", "completion_tokens", "total_tokens")) and (
        result["total_tokens"] != result["prompt_tokens"] + result["completion_tokens"]
    ):
        raise LLMError("llm_invalid_response")
    for detail, key, parent in (
        ("prompt_tokens_details", "cached_tokens", "prompt_tokens"),
        ("completion_tokens_details", "reasoning_tokens", "completion_tokens"),
    ):
        obj = value.get(detail)
        if obj is not None:
            if not isinstance(obj, dict):
                raise LLMError("llm_invalid_response")
            if key in obj:
                count = obj[key]
                if type(count) is not int or not 0 <= count <= 1000000:
                    raise LLMError("llm_invalid_response")
                # Some compatible providers report inconsistent optional breakdowns.
                # Keep valid totals and the answer; omit an untrustworthy detail
                # instead of turning a completed generation into a failed request.
                if count <= result.get(parent, 1000000):
                    result[detail] = {key: count}
    return result or None


def check_answer(answer, reason):
    if not answer.strip():
        raise LLMError("llm_output_limit" if reason == "length" else "llm_empty_response", 422)
    return answer


class LLMClient:
    def __init__(self, timeout=120, client=None, health_timeout=5, health_attempts=2):
        self.timeout = timeout
        self.health_timeout = health_timeout
        self.health_attempts = max(1, health_attempts)
        self.client = client or httpx.AsyncClient(
            transport=GuardedTransport(),
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(connect=3, read=timeout, write=5, pool=2),
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
        )

    async def close(self):
        await self.client.aclose()

    def check(self, response):
        if response.status_code in (429, 529):
            raise LLMError("llm_busy", 429)
        if response.status_code in (400, 413, 422):
            code = "llm_invalid_parameters"
            try:
                detail = response.json().get("error", {})
                if detail.get("code") in {"context_length_exceeded", "string_above_max_length"}:
                    code = "llm_context_or_input_limit"
            except (ValueError, AttributeError, httpx.ResponseNotRead):
                pass
            if response.status_code == 413:
                code = "llm_context_or_input_limit"
            raise LLMError(code, 422)
        if response.status_code == 404:
            raise LLMError("llm_deployment_not_found", 503)
        if response.status_code in (401, 403):
            raise LLMError("llm_credentials_rejected", 503)
        if response.status_code != 200:
            raise LLMError()

    async def bounded_json(self, response, max_bytes=65536):
        data = bytearray()
        async for block in response.aiter_bytes():
            data.extend(block)
            if len(data) > max_bytes:
                raise LLMError("llm_response_limit")
        return object_json(data)

    @property
    def health_deadline(self):
        """Worst case for a full readiness probe, so callers can bound their own deadlines."""
        backoff = sum(
            HEALTH_BACKOFF[min(i, len(HEALTH_BACKOFF) - 1)] for i in range(self.health_attempts - 1)
        )
        return self.health_attempts * self.health_timeout + backoff

    async def health(self, base_url, model, key, provider="local_llama_cpp"):
        """Is the provider reachable and serving this model?

        Only `llm_unavailable` is retried - a timeout, a transport fault, or an unmapped non-200
        status. Those are the answers that change if you ask again. Rejected credentials, a missing
        deployment, a model the catalog does not list, a malformed body and an explicit busy signal
        are decided answers, so they are raised on the first attempt instead of being repeated.

        Retrying is safe here and nowhere else in this client: the probe is a credentialed GET of
        the model catalog, so it has no side effect and is not billed as inference. A submission
        whose outcome is unknown is still never resent.
        """
        failure = None
        try:
            async with asyncio.timeout(self.health_deadline):
                for attempt in range(self.health_attempts):
                    try:
                        await self.probe(base_url, model, key, provider)
                        return
                    except LLMError as error:
                        if error.code != "llm_unavailable":
                            raise
                        failure = error
                    except (TimeoutError, httpx.HTTPError):
                        failure = LLMError("llm_unavailable", 503)
                    if attempt + 1 < self.health_attempts:
                        await asyncio.sleep(HEALTH_BACKOFF[min(attempt, len(HEALTH_BACKOFF) - 1)])
        except TimeoutError:
            pass  # The overall budget expired mid-attempt; report the transient failure below.
        raise failure or LLMError("llm_unavailable", 503)

    async def probe(self, base_url, model, key, provider="local_llama_cpp"):
        """One readiness attempt. Transport faults are left for `health` to classify and retry."""
        path = "/models/" + quote(model, safe="") if provider in {"openai", "anthropic"} else "/models"
        async with asyncio.timeout(self.health_timeout):
            async with self.client.stream(
                "GET",
                api_base(base_url, provider) + path,
                headers=credential_headers(key, provider),
            ) as response:
                self.check(response)
                # Azure's resource-wide model metadata can exceed the normal
                # response limit. Keep a separate bound for catalog GETs only.
                limit = 1048576 if provider == "azure_openai" else 65536
                result = await self.bounded_json(response, max_bytes=limit)
        models = [result] if provider in {"openai", "anthropic"} else result.get("data")
        if provider == "anthropic" and isinstance(result.get("id"), str):
            # Model aliases can resolve to a dated canonical ID.
            return
        if provider == "azure_openai" and isinstance(models, list):
            # Azure catalog IDs need not match deployment names. This verifies
            # authenticated API access only; inference validates the deployment.
            return
        if not isinstance(models, list) or not any(
            isinstance(m, dict) and m.get("id") == model for m in models
        ):
            raise LLMError("llm_model_mismatch", 503)

    async def events(
        self,
        base_url,
        model,
        key,
        messages,
        max_tokens,
        streaming=True,
        provider="local_llama_cpp",
        token_parameter="max_tokens",
        stream_usage=True,
        request_id=None,
        context_tokens=None,
        temperature=None,
        reasoning_effort=None,
        disable_thinking=False,
    ) -> AsyncIterator[dict]:
        if provider == "anthropic":
            async for event in self.anthropic_events(
                base_url,
                model,
                key,
                messages,
                max_tokens,
                streaming,
                request_id=request_id,
                temperature=temperature,
            ):
                yield event
            return
        started = time.monotonic()
        first = None
        payload = {
            "model": model,
            "messages": messages,
            token_parameter: max_tokens,
            "stream": streaming,
        }
        if provider == "local_llama_cpp":
            payload.update(temperature=0, seed=42, chat_template_kwargs={"enable_thinking": False})
        elif provider in {"openai", "azure_openai"}:
            payload["store"] = False
        if provider != "local_llama_cpp":
            if temperature is not None:
                payload["temperature"] = temperature
            if reasoning_effort is not None:
                payload["reasoning_effort"] = reasoning_effort
            if disable_thinking:
                # The same key llama.cpp uses. A server that does not support it ignores
                # it rather than failing, so this stays safe across OpenAI-compatible
                # deployments; only enable it for a model measured with it on.
                payload["chat_template_kwargs"] = {"enable_thinking": False}
        if streaming and stream_usage:
            payload["stream_options"] = {"include_usage": True}
        headers = credential_headers(key, provider)
        if request_id:
            headers["X-Client-Request-Id"] = request_id
        try:
            async with asyncio.timeout(self.timeout):
                async with self.client.stream(
                    "POST",
                    api_base(base_url, provider) + "/chat/completions",
                    headers=headers,
                    json=payload,
                ) as response:
                    if response.status_code != 200:
                        error_body = bytearray()
                        async for block in response.aiter_bytes():
                            error_body.extend(block)
                            if len(error_body) > 16384:
                                break
                        self.check(httpx.Response(response.status_code, content=bytes(error_body[:16384])))
                    if not streaming:
                        result = await self.bounded_json(response)
                        choices = result.get("choices")
                        if (
                            not isinstance(choices, list)
                            or len(choices) != 1
                            or not isinstance(choices[0], dict)
                        ):
                            raise LLMError("llm_invalid_response")
                        choice = choices[0]
                        reason = finish(choice.get("finish_reason"))
                        message = choice.get("message")
                        if isinstance(message, dict) and message.get("refusal"):
                            raise LLMError("llm_refused", 422)
                        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
                            raise LLMError("llm_invalid_response")
                        answer = check_answer(message["content"], reason)
                        if len(answer.encode("utf-8")) > 32000:
                            raise LLMError("llm_response_limit")
                        yield {
                            "type": "done",
                            "text": answer,
                            "finish_reason": reason,
                            "usage": usage(result.get("usage")),
                            "first_token_ms": None,
                            "total_ms": round((time.monotonic() - started) * 1000),
                        }
                        return
                    buffer = bytearray()
                    answer_parts = []
                    size = total_bytes = 0
                    reason = token_usage = None
                    async for block in response.aiter_bytes():
                        total_bytes += len(block)
                        if total_bytes > 1048576:
                            raise LLMError("llm_response_limit")
                        buffer.extend(block)
                        while b"\n" in buffer:
                            raw, _, remaining = buffer.partition(b"\n")
                            buffer = bytearray(remaining)
                            if len(raw) > 65536:
                                raise LLMError("llm_response_limit")
                            raw = raw.rstrip(b"\r")
                            if not raw.startswith(b"data:"):
                                continue
                            raw = raw[5:].strip()
                            if raw == b"[DONE]":
                                if reason is None:
                                    raise LLMError("llm_incomplete")
                                yield {
                                    "type": "done",
                                    "text": check_answer("".join(answer_parts), reason),
                                    "finish_reason": reason,
                                    "usage": token_usage,
                                    "first_token_ms": first,
                                    "total_ms": round((time.monotonic() - started) * 1000),
                                }
                                return
                            event = object_json(raw)
                            if "error" in event:
                                raise LLMError()
                            if event.get("usage") is not None:
                                token_usage = usage(event["usage"])
                            choices = event.get("choices", [])
                            if not isinstance(choices, list) or len(choices) > 1:
                                raise LLMError("llm_invalid_response")
                            for choice in choices:
                                if not isinstance(choice, dict) or not isinstance(
                                    choice.get("delta", {}), dict
                                ):
                                    raise LLMError("llm_invalid_response")
                                if choice.get("delta", {}).get("refusal"):
                                    raise LLMError("llm_refused", 422)
                                value = choice.get("delta", {}).get("content")
                                if value is not None:
                                    if not isinstance(value, str) or reason is not None and value:
                                        raise LLMError("llm_invalid_response")
                                    size += len(value.encode("utf-8"))
                                    if size > 32000:
                                        raise LLMError("llm_response_limit")
                                    if value:
                                        first = (
                                            first
                                            if first is not None
                                            else round((time.monotonic() - started) * 1000)
                                        )
                                        answer_parts.append(value)
                                        yield {"type": "delta", "text": value}
                                if choice.get("finish_reason") is not None:
                                    reason = finish(choice["finish_reason"])
                        if len(buffer) > 65536:
                            raise LLMError("llm_response_limit")
                    raise LLMError("llm_incomplete")
        except TimeoutError:
            raise LLMError("llm_timeout", 504) from None
        except httpx.HTTPError:
            raise LLMError("llm_transport_unknown") from None

    async def anthropic_events(
        self, base_url, model, key, messages, max_tokens, streaming, *, request_id=None, temperature=None
    ) -> AsyncIterator[dict]:
        """Native Messages API. Text only, bounded, and never retries an unknown POST."""
        started = time.monotonic()
        instructions = [item["content"] for item in messages if item["role"] in {"system", "developer"}]
        turns = [item for item in messages if item["role"] in {"user", "assistant"}]
        if not turns or turns[-1]["role"] != "user":
            raise LLMError("llm_invalid_parameters", 422)
        payload = {"model": model, "messages": turns, "max_tokens": max_tokens, "stream": streaming}
        if instructions:
            payload["system"] = "\n".join(instructions)
        if temperature is not None:
            payload["temperature"] = temperature
        headers = credential_headers(key, "anthropic")
        if request_id:
            headers["X-Client-Request-Id"] = request_id
        try:
            async with asyncio.timeout(self.timeout):
                async with self.client.stream(
                    "POST", base_url + "/messages", headers=headers, json=payload
                ) as response:
                    self.check(response)
                    if not streaming:
                        result = await self.bounded_json(response)
                        blocks = result.get("content")
                        if not isinstance(blocks, list) or any(
                            not isinstance(block, dict)
                            or block.get("type") != "text"
                            or not isinstance(block.get("text"), str)
                            for block in blocks
                        ):
                            raise LLMError("llm_invalid_response")
                        reason = self.anthropic_finish(result.get("stop_reason"))
                        answer = check_answer("".join(block["text"] for block in blocks), reason)
                        if len(answer.encode()) > 32000:
                            raise LLMError("llm_response_limit")
                        yield {
                            "type": "done",
                            "text": answer,
                            "finish_reason": reason,
                            "usage": self.anthropic_usage(result.get("usage")),
                            "first_token_ms": None,
                            "total_ms": round((time.monotonic() - started) * 1000),
                        }
                        return
                    buffer = bytearray()
                    answer_parts: list[str] = []
                    first = None
                    input_tokens = output_tokens = None
                    reason = None
                    total = size = 0
                    async for block in response.aiter_bytes():
                        total += len(block)
                        if total > 1048576:
                            raise LLMError("llm_response_limit")
                        buffer.extend(block)
                        while b"\n" in buffer:
                            raw, _, rest = buffer.partition(b"\n")
                            buffer = bytearray(rest)
                            if len(raw) > 65536:
                                raise LLMError("llm_response_limit")
                            raw = raw.rstrip(b"\r")
                            if not raw.startswith(b"data:"):
                                continue
                            event = object_json(raw[5:].strip())
                            kind = event.get("type")
                            if kind == "error":
                                raise LLMError("llm_unavailable")
                            if kind == "message_start":
                                metrics = self.anthropic_usage(event.get("message", {}).get("usage"))
                                input_tokens = metrics["prompt_tokens"] if metrics else None
                            elif kind == "content_block_delta":
                                delta = event.get("delta", {})
                                if not isinstance(delta, dict):
                                    raise LLMError("llm_invalid_response")
                                if delta.get("type") != "text_delta":
                                    continue
                                value = delta.get("text")
                                if not isinstance(value, str) or reason is not None:
                                    raise LLMError("llm_invalid_response")
                                size += len(value.encode())
                                if size > 32000:
                                    raise LLMError("llm_response_limit")
                                if value:
                                    first = (
                                        first
                                        if first is not None
                                        else round((time.monotonic() - started) * 1000)
                                    )
                                    answer_parts.append(value)
                                    yield {"type": "delta", "text": value}
                            elif kind == "message_delta":
                                delta = event.get("delta", {})
                                if not isinstance(delta, dict):
                                    raise LLMError("llm_invalid_response")
                                reason = self.anthropic_finish(delta.get("stop_reason"))
                                counters = event.get("usage")
                                if counters is not None:
                                    if (
                                        not isinstance(counters, dict)
                                        or type(counters.get("output_tokens")) is not int
                                        or not 0 <= counters["output_tokens"] <= 1000000
                                    ):
                                        raise LLMError("llm_invalid_response")
                                    output_tokens = counters["output_tokens"]
                            elif kind == "message_stop":
                                if reason is None:
                                    raise LLMError("llm_incomplete")
                                answer = check_answer("".join(answer_parts), reason)
                                metrics = None
                                if input_tokens is not None and output_tokens is not None:
                                    metrics = {
                                        "prompt_tokens": input_tokens,
                                        "completion_tokens": output_tokens,
                                        "total_tokens": input_tokens + output_tokens,
                                    }
                                yield {
                                    "type": "done",
                                    "text": answer,
                                    "finish_reason": reason,
                                    "usage": metrics,
                                    "first_token_ms": first,
                                    "total_ms": round((time.monotonic() - started) * 1000),
                                }
                                return
                        if len(buffer) > 65536:
                            raise LLMError("llm_response_limit")
                    raise LLMError("llm_incomplete")
        except TimeoutError:
            raise LLMError("llm_timeout", 504) from None
        except httpx.HTTPError:
            raise LLMError("llm_transport_unknown") from None

    @staticmethod
    def anthropic_finish(value):
        if value == "end_turn" or value == "stop_sequence":
            return "stop"
        if value in {"max_tokens", "model_context_window_exceeded"}:
            return "length"
        if value == "refusal":
            raise LLMError("llm_refused", 422)
        raise LLMError("llm_invalid_response")

    @staticmethod
    def anthropic_usage(value):
        if value is None:
            return None
        if not isinstance(value, dict):
            raise LLMError("llm_invalid_response")
        prompt = value.get("input_tokens")
        completion = value.get("output_tokens")
        if any(type(number) is not int or not 0 <= number <= 1000000 for number in (prompt, completion)):
            raise LLMError("llm_invalid_response")
        assert isinstance(prompt, int) and isinstance(completion, int)
        return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion}

    async def complete(self, **kwargs):
        async for event in self.events(**kwargs, streaming=False):
            if event["type"] == "done":
                return event
        raise LLMError("llm_incomplete")

    def stream(self, **kwargs):
        return self.events(**kwargs, streaming=True)
