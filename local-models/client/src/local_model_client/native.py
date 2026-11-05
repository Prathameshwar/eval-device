"""Direct loopback client for the laptop's own model server.

A local model runs beside this app, so the turn is executed here and PMS is never on the
data path: no prompt, transcript or answer leaves the machine. Response validation mirrors
the platform's provider client so a local turn accepts exactly the responses a platform
turn would, and the shared pipeline sees the same event shape either way.
"""

import asyncio
import hashlib
import json
import re
import time
import weakref

import httpx
from training_contracts.patient_turn import TurnError

MAX_ANSWER_BYTES = 32000
MAX_STREAM_BYTES = 1048576
MAX_LINE_BYTES = 65536
MAX_NATIVE_BYTES = 262144
# Readiness retries. A local server still loading a multi-billion-parameter model answers its
# model catalogue slowly, and one slow answer must not refuse the operator's question. Three
# attempts here against two for a cloud provider: loopback refuses instantly, so extra attempts
# cost only the backoff rather than a network timeout each.
HEALTH_ATTEMPTS = 3
HEALTH_TIMEOUT = 5
HEALTH_BACKOFF = (0.25, 0.75)

MESSAGES = {
    "llm_busy": "The local model is busy. It will be retried automatically.",
    "llm_timeout": "The local model did not answer in time. Inspect the service before submitting a new question.",
    "llm_unavailable": "The local model server is not responding. Open Manage Local Models and check the assigned service.",
    "llm_invalid_response": "The local model returned an unusable response. Ask the question again.",
    "llm_invalid_parameters": "The local model rejected its parameters. Check service configuration in Manage Local Models.",
    "llm_model_mismatch": "The local model server is running a different model than PMS has published.",
    "llm_content_filtered": "The local model refused to answer. Ask the question again.",
    "llm_empty_response": "The local model returned no text. Ask the question again.",
    "llm_output_limit": "The local answer hit its output limit. Ask a shorter question.",
    "llm_incomplete": "The local model ended its answer early. Inspect the service before submitting a new question.",
    "llm_response_limit": "The local model produced too much output. Ask a shorter question.",
    "llm_credentials_rejected": "The local model server rejected its key. Reconnect Human-test to Manage Local Models.",
    "llm_context_limit_unavailable": "The local model server did not report its context size.",
    "llm_tokenizer_unavailable": "The local model server's tokenizer is not responding.",
    "llm_tokenizer_invalid": "The local model server returned an unusable tokenization.",
    "llm_tokenizer_response_limit": "The local model server's tokenizer returned too much data.",
    "llm_chat_template_invalid": "The local model server returned an unusable chat template.",
    "patient_context_too_long": "The case and question exceed the local model's capacity. Shorten the question, or ask for a shorter case or a larger model context.",
}


def message_for(code):
    return MESSAGES.get(code, "Local model: " + code)


def object_json(raw):
    try:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise TurnError("llm_invalid_response") from None


def finish_reason(value):
    if value == "content_filter":
        raise TurnError("llm_content_filtered", 422)
    if value not in ("stop", "length"):
        raise TurnError("llm_invalid_response")
    return value


def usage(value):
    """Keep only counts this server reported consistently; never invent a total."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise TurnError("llm_invalid_response")
    result: dict = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if key in value:
            count = value[key]
            if type(count) is not int or not 0 <= count <= 1000000:
                raise TurnError("llm_invalid_response")
            result[key] = count
    if all(k in result for k in ("prompt_tokens", "completion_tokens", "total_tokens")) and (
        result["total_tokens"] != result["prompt_tokens"] + result["completion_tokens"]
    ):
        raise TurnError("llm_invalid_response")
    for detail, key, parent in (
        ("prompt_tokens_details", "cached_tokens", "prompt_tokens"),
        ("completion_tokens_details", "reasoning_tokens", "completion_tokens"),
    ):
        obj = value.get(detail)
        if isinstance(obj, dict) and key in obj:
            count = obj[key]
            if type(count) is not int or not 0 <= count <= 1000000:
                raise TurnError("llm_invalid_response")
            if count <= result.get(parent, 1000000):
                result[detail] = {key: count}
        elif obj is not None and not isinstance(obj, dict):
            raise TurnError("llm_invalid_response")
    return result or None


def selection_grammar(messages):
    """Constrain the existing patient ID protocol before generation, not by retrying.

    The fact guard still verifies frozen evidence, duplicates and completion. General
    knowledge, greetings and older plain-text case prompts keep ordinary generation.
    """
    if not messages or messages[0].get("role") not in {"system", "developer"}:
        return None
    system = messages[0].get("content", "")
    if not system.startswith("Prompt scope: ") or "\nSOURCE:\n" not in system:
        return None
    try:
        sources = json.loads(system.split("\nSOURCE:\n", 1)[1].split("\nEND SOURCE.", 1)[0])
        if (
            not isinstance(sources, dict)
            or len(sources) > 512
            or any(not re.fullmatch(r"f[0-9]{1,6}", key) for key in sources)
        ):
            raise ValueError()
    except (ValueError, TypeError):
        raise TurnError("llm_invalid_response") from None

    # Quote JSON string tokens again as GBNF terminals; no case text enters grammar.
    def literal(value):
        return json.dumps(json.dumps(value))

    special = " | ".join(literal(key) for key in ("unknown", "clarify", "boundary"))
    rules = [
        'root ::= "[" ws (special' + (" | facts" if sources else "") + ') ws "]" ws',
        "ws ::= [ \\t\\n\\r]{0,16}",
        "special ::= " + special,
    ]
    if sources:
        rules.extend(
            [
                'facts ::= fact (ws "," ws fact){0,2} (ws "," ws ' + literal("unknown") + ")?",
                "fact ::= " + " | ".join(literal(key) for key in sources),
            ]
        )
    return "\n".join(rules) + "\n"


def new_client(timeout):
    """One pool for every local turn, so changing the published model leaks no connections."""
    return httpx.AsyncClient(
        trust_env=False,
        follow_redirects=False,
        timeout=httpx.Timeout(connect=3, read=timeout, write=5, pool=2),
        limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
    )


_BUDGET_CACHES: weakref.WeakKeyDictionary[httpx.AsyncClient, dict] = weakref.WeakKeyDictionary()


class LocalModel:
    """Runs patient turns on this machine and satisfies the shared pipeline's runner protocol."""

    provider = "local_llama_cpp"
    # A native server reports its own context size, so no configured remote limit applies.
    remote_context_tokens = None

    def __init__(self, port, key, model, *, context_cap, timeout=120, client=None, enable_thinking=False):
        if type(port) is not int or not 1 <= port <= 65535:
            raise TurnError("llm_endpoint_invalid", 422)
        if type(context_cap) is not int or not 512 <= context_cap <= 1048576:
            raise TurnError("llm_context_limit_unavailable")
        self.enable_thinking = enable_thinking
        self.root = f"http://127.0.0.1:{port}"
        self.model = model
        self.key = key
        self.local_context_cap = context_cap
        self.timeout = timeout
        # The pool belongs to the caller: a model change must not close a pool still in use.
        self.client = client if client is not None else new_client(timeout)
        caches = _BUDGET_CACHES.setdefault(self.client, {})
        identity = (self.root, model, context_cap, enable_thinking, hashlib.sha256(key.encode()).digest())
        if identity not in caches and len(caches) >= 8:
            caches.clear()
        self.budget_cache = caches.setdefault(identity, {})

    @property
    def headers(self):
        return {"Authorization": "Bearer " + self.key}

    def check(self, response):
        if response.status_code != 200:
            self.budget_cache.clear()
        if response.status_code == 429:
            raise TurnError("llm_busy", 429)
        if response.status_code in (400, 413, 422):
            raise TurnError("llm_invalid_parameters", 422)
        if response.status_code in (401, 403):
            raise TurnError("llm_credentials_rejected", 503)
        if response.status_code != 200:
            raise TurnError()

    async def native_json(self, method, path, payload=None):
        """llama.cpp's own tokenizer routes; used only to bound a prompt before generating."""
        try:
            async with self.client.stream(
                method, self.root + path, headers=self.headers, json=payload
            ) as response:
                self.check(response)
                data = bytearray()
                async for block in response.aiter_bytes():
                    data.extend(block)
                    if len(data) > MAX_NATIVE_BYTES:
                        raise TurnError("llm_tokenizer_response_limit")
                return object_json(data)
        except httpx.HTTPError:
            self.budget_cache.clear()
            raise TurnError("llm_tokenizer_unavailable", 503) from None

    async def health(self):
        """Is the local server up and serving the published model?

        Only `llm_unavailable` is retried - a timeout or a refused connection. A rejected key, a
        different model in the catalogue and a malformed body are decided answers that repeating
        the call cannot change. The probe is a loopback GET of the model list, so it has no side
        effect; a generation whose outcome is unknown is still never resent.
        """
        failure = None
        deadline = HEALTH_ATTEMPTS * HEALTH_TIMEOUT + sum(
            HEALTH_BACKOFF[min(i, len(HEALTH_BACKOFF) - 1)] for i in range(HEALTH_ATTEMPTS - 1)
        )
        try:
            async with asyncio.timeout(deadline):
                for attempt in range(HEALTH_ATTEMPTS):
                    try:
                        await self.probe()
                        return
                    except TurnError as error:
                        if error.code != "llm_unavailable":
                            raise
                        failure = error
                    except (TimeoutError, httpx.HTTPError):
                        failure = TurnError("llm_unavailable", 503)
                    if attempt + 1 < HEALTH_ATTEMPTS:
                        await asyncio.sleep(HEALTH_BACKOFF[min(attempt, len(HEALTH_BACKOFF) - 1)])
        except TimeoutError:
            pass  # The overall budget expired mid-attempt; report the transient failure below.
        raise failure or TurnError("llm_unavailable", 503)

    async def probe(self):
        """One readiness attempt. Transport faults are left for `health` to classify and retry."""
        async with asyncio.timeout(HEALTH_TIMEOUT):
            async with self.client.stream("GET", self.root + "/v1/models", headers=self.headers) as response:
                self.check(response)
                data = bytearray()
                async for block in response.aiter_bytes():
                    data.extend(block)
                    if len(data) > MAX_NATIVE_BYTES:
                        raise TurnError("llm_response_limit")
        models = object_json(data).get("data")
        if not isinstance(models, list) or not any(
            isinstance(m, dict) and m.get("id") == self.model for m in models
        ):
            raise TurnError("llm_model_mismatch", 503)

    async def complete(self, messages, max_tokens):
        """One bounded turn. Deltas are consumed here and never surfaced.

        The spoken call must be checked by the fact guard before any of it is shown, so the
        stream is read only to measure first-token latency, exactly as the platform does.
        """
        started = time.monotonic()
        first = None
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
            "temperature": 0,
            "seed": 42,
            "chat_template_kwargs": {"enable_thinking": self.enable_thinking},
        }
        grammar = selection_grammar(messages)
        if grammar is not None:
            payload["grammar"] = grammar
        try:
            async with asyncio.timeout(self.timeout):
                async with self.client.stream(
                    "POST", self.root + "/v1/chat/completions", headers=self.headers, json=payload
                ) as response:
                    self.check(response)
                    buffer = bytearray()
                    parts: list[str] = []
                    size = total = 0
                    reason = token_usage = None
                    async for block in response.aiter_bytes():
                        total += len(block)
                        if total > MAX_STREAM_BYTES:
                            raise TurnError("llm_response_limit")
                        buffer.extend(block)
                        while b"\n" in buffer:
                            raw, _, rest = buffer.partition(b"\n")
                            buffer = bytearray(rest)
                            if len(raw) > MAX_LINE_BYTES:
                                raise TurnError("llm_response_limit")
                            raw = raw.rstrip(b"\r")
                            if not raw.startswith(b"data:"):
                                continue
                            raw = raw[5:].strip()
                            if raw == b"[DONE]":
                                if reason is None:
                                    raise TurnError("llm_incomplete")
                                text = "".join(parts)
                                if not text.strip():
                                    raise TurnError(
                                        "llm_output_limit" if reason == "length" else "llm_empty_response",
                                        422,
                                    )
                                return {
                                    "type": "done",
                                    "text": text,
                                    "finish_reason": reason,
                                    "usage": token_usage,
                                    "first_token_ms": first,
                                    "total_ms": round((time.monotonic() - started) * 1000),
                                }
                            event = object_json(raw)
                            if "error" in event:
                                raise TurnError()
                            if event.get("usage") is not None:
                                token_usage = usage(event["usage"])
                            choices = event.get("choices", [])
                            if not isinstance(choices, list) or len(choices) > 1:
                                raise TurnError("llm_invalid_response")
                            for choice in choices:
                                if not isinstance(choice, dict) or not isinstance(
                                    choice.get("delta", {}), dict
                                ):
                                    raise TurnError("llm_invalid_response")
                                if choice.get("delta", {}).get("refusal"):
                                    raise TurnError("llm_content_filtered", 422)
                                value = choice.get("delta", {}).get("content")
                                if value is not None:
                                    if not isinstance(value, str) or (reason is not None and value):
                                        raise TurnError("llm_invalid_response")
                                    size += len(value.encode("utf-8"))
                                    if size > MAX_ANSWER_BYTES:
                                        raise TurnError("llm_response_limit")
                                    if value:
                                        if first is None:
                                            first = round((time.monotonic() - started) * 1000)
                                        parts.append(value)
                                if choice.get("finish_reason") is not None:
                                    reason = finish_reason(choice["finish_reason"])
                        if len(buffer) > MAX_LINE_BYTES:
                            raise TurnError("llm_response_limit")
                    raise TurnError("llm_incomplete")
        except TimeoutError:
            raise TurnError("llm_timeout", 504) from None
        except httpx.HTTPError:
            # Loopback, so an interrupted call was not billed and was not partly applied.
            raise TurnError("llm_unavailable", 503) from None
