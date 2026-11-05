"""Authenticated local client. Inference requests are never retried automatically."""

import http.client
import json
import socket
import threading
import time
import urllib.error
from contextlib import contextmanager

from common import model_profile


@contextmanager
def request(port, path, key=None, payload=None, timeout=5):
    """Direct loopback HTTP; one attempt, no proxy/redirect, bounded wall-clock I/O."""
    headers = {"Connection": "close"}
    if key is not None:
        headers["Authorization"] = "Bearer " + key
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    deadline = time.monotonic() + timeout
    expired = threading.Event()
    timer = None
    response = None
    try:
        connection.connect()
        connection.auto_open = 0  # Never reconnect/replay an uncertain POST.
        sock = connection.sock

        def expire():
            expired.set()
            try:
                # shutdown interrupts blocked header/body reads, including slow byte trickles.
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Local API deadline exceeded")
        timer = threading.Timer(remaining, expire)
        timer.daemon = True
        timer.start()
        connection.request("POST" if payload is not None else "GET", path, body=data, headers=headers)
        response = connection.getresponse()
        if response.status >= 300:
            # Do not include native response bodies or follow a Location header with credentials.
            raise urllib.error.HTTPError(
                f"http://127.0.0.1:{port}{path}",
                response.status,
                "Local API request failed",
                response.headers,
                None,
            )
        yield response
        if expired.is_set() or time.monotonic() >= deadline:
            raise TimeoutError("Local API deadline exceeded")
    except Exception:
        if expired.is_set() or time.monotonic() >= deadline:
            raise TimeoutError("Local API deadline exceeded") from None
        raise
    finally:
        if timer:
            timer.cancel()
            timer.join()
        if response:
            response.close()
        connection.close()


def json_request(port, path, key=None, payload=None, timeout=5):
    with request(port, path, key, payload, timeout) as response:
        raw = response.read(1_048_577)
        if len(raw) > 1_048_576:
            raise RuntimeError("Local API response exceeded its limit")
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise RuntimeError("Invalid local API response")
        return result


def infer(settings, key, messages, on_text=None):
    if not isinstance(messages, list) or not messages:
        raise ValueError("Conversation messages must be a non-empty list")
    for message in messages:
        if (
            not isinstance(message, dict)
            or set(message) != {"role", "content"}
            or message["role"] not in ("system", "user", "assistant")
        ):
            raise ValueError("Invalid conversation message")
        if not isinstance(message["content"], str) or len(message["content"]) > 8000:
            raise ValueError("Message too long")
    payload = {
        "model": model_profile(settings)["alias"],
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
        "max_tokens": settings["max_tokens"],
        "temperature": 0.7,
        "top_p": 0.8,
        "top_k": 20,
        "min_p": 0,
        "chat_template_kwargs": {"enable_thinking": False},
        "seed": 42,
    }
    started = time.perf_counter()
    first = None
    texts = []
    size = 0
    finish_reason = None
    usage = None
    # One POST only: a timeout or disconnect must not replay an uncertain inference request.
    try:
        with request(
            settings["port"],
            "/v1/chat/completions",
            key,
            payload,
            settings["request_timeout_seconds"],
        ) as response:
            while True:
                if time.perf_counter() - started > settings["request_timeout_seconds"]:
                    raise TimeoutError("Inference deadline exceeded")
                line = response.readline(65537)
                if not line:
                    raise RuntimeError("Inference stream ended before completion")
                if len(line) > 65536:
                    raise RuntimeError("Inference event exceeded its limit")
                if not line.startswith(b"data: "):
                    continue
                raw = line[6:].strip()
                if raw == b"[DONE]":
                    break
                try:
                    event = json.loads(raw)
                except (ValueError, UnicodeError):
                    raise RuntimeError("Invalid inference response") from None
                if not isinstance(event, dict) or not isinstance(event.get("choices", []), list):
                    raise RuntimeError("Invalid inference response")
                if event.get("usage") is not None:
                    usage = event["usage"]
                if "error" in event:
                    raise RuntimeError("Inference failed; shorten the prompt or reset the conversation")
                for choice in event.get("choices", []):
                    if not isinstance(choice, dict) or not isinstance(choice.get("delta", {}), dict):
                        raise RuntimeError("Invalid inference response")
                    text = choice.get("delta", {}).get("content")
                    if text is None:
                        text = ""
                    if not isinstance(text, str):
                        raise RuntimeError("Invalid inference response")
                    if text:
                        if first is None:
                            first = time.perf_counter() - started
                        size += len(text)
                        if size > 32000:
                            raise RuntimeError("Inference output limit exceeded")
                        texts.append(text)
                        if on_text:
                            on_text(text)
                    reason = choice.get("finish_reason")
                    if reason is not None:
                        if reason not in ("stop", "length", "content_filter", "tool_calls", "function_call"):
                            raise RuntimeError("Invalid inference finish reason")
                        finish_reason = reason
    except (http.client.HTTPException, ConnectionError):
        raise RuntimeError("Inference connection ended unexpectedly; request was not retried") from None
    if finish_reason is None:
        raise RuntimeError("Inference did not report a finish reason")
    return {
        "text": "".join(texts),
        "first_token_seconds": first,
        "total_seconds": time.perf_counter() - started,
        "finish_reason": finish_reason,
        "usage": usage,
    }
