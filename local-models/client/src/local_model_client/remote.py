"""HTTPS inference only. Platform device credentials never reach the GPU host."""

import asyncio
import hashlib
import json
import ssl
import time
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from .connection import MAX_RESPONSE, Connection, ConnectionError

OPERATIONS = {
    ("GET", "/v1/capabilities"),
    ("POST", "/v1/infer/asr"),
    ("POST", "/v1/infer/tts"),
    ("POST", "/v1/infer/llm"),
    ("POST", "/v1/llm/inspect"),
    ("GET", "/v1/stream/audio"),
    ("GET", "/v1/stream/video"),
    ("POST", "/v1/requests/status"),
}


def https_origin(value):
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
        raise ValueError("Inference requires an HTTPS origin without credentials or a path")
    return value.rstrip("/")


class RemoteConnection(Connection):
    remote = True

    def __init__(
        self,
        origin,
        host_id,
        platform,
        credential,
        *,
        ca_file=None,
        timeout=180,
        transport=None,
        async_transport=None,
        journal_dir=None,
    ):
        super().__init__(inherit_defaults=False, timeout=timeout)
        self.root = https_origin(origin)
        self.host_id = str(host_id)
        self.platform = platform.rstrip("/")
        self._credential = credential
        self.verify = ssl.create_default_context(cafile=str(ca_file) if ca_file else None)
        self.context = lambda: None
        self.transport, self.async_transport = transport, async_transport
        self.last_request = None
        from .journal import Requests

        self.journal = Requests(journal_dir) if journal_dir else None

    def note(self, identity, state):
        if self.journal:
            self.journal.note(identity, state)
        self.last_request = {"id": identity, "status": state}

    @property
    def headers(self):
        raise ConnectionError("Remote requests require a platform grant", "permission_denied", 403)

    def request_body(self, method, path, payload):
        if (method, path) not in OPERATIONS:
            raise ConnectionError("Unsupported inference operation", "permission_denied", 403)
        raw = (
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
            if payload is not None
            else b""
        )
        if len(raw) > 1500000:
            raise ConnectionError("Inference input exceeds its limit", "input", 422)
        request_id = str(uuid4())
        body = {
            "host_id": self.host_id,
            "origin": self.root,
            "request_id": request_id,
            "method": method,
            "path": path,
            "body_sha256": hashlib.sha256(raw).hexdigest(),
            "model": (payload or {}).get("model"),
            "voice": (payload or {}).get("voice"),
            "conversation_id": self.context(),
            "processing_run_id": (payload or {}).get("processing_run_id"),
        }
        self.note(request_id, "authorizing")
        return raw, body

    def grant_headers(self, response):
        if response.status_code != 200 or len(response.content) > 16384:
            raise ConnectionError("Platform refused inference authorization", "permission_denied", 403)
        try:
            value = response.json()
        except (ValueError, RecursionError):
            raise ConnectionError("Invalid platform grant", "invalid_response") from None
        grant = value.get("grant") if isinstance(value, dict) else None
        if not isinstance(grant, str) or not 32 <= len(grant) <= 8192:
            raise ConnectionError("Invalid platform grant", "invalid_response")
        return {"Authorization": "Bearer " + grant, "Content-Type": "application/json"}

    def decode(self, status, raw, identity):
        if len(raw) > MAX_RESPONSE:
            raise ConnectionError("Inference output exceeds its limit", "invalid_response")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError()
        if status != 200:
            code = value.get("code")
            if code not in {"capacity", "model_mismatch", "input", "unauthorized", "replay", "timeout"}:
                code = "unavailable"
            raise ConnectionError("Remote inference did not complete", code, status)
        self.note(identity, "completed")
        return value

    def grant(self, client, body):
        deadline = time.monotonic() + 10
        with client.stream(
            "POST",
            self.platform + "/api/v1/device/inference/grants",
            json=body,
            headers={"Authorization": "Bearer " + self._credential},
            timeout=10,
        ) as response:
            raw = bytearray()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw) > 16384 or time.monotonic() > deadline:
                    raise ConnectionError("Grant response exceeded its budget")
            return self.grant_headers(httpx.Response(response.status_code, content=bytes(raw)))

    async def async_grant(self, client, body):
        async with asyncio.timeout(10):
            async with client.stream(
                "POST",
                self.platform + "/api/v1/device/inference/grants",
                json=body,
                headers={"Authorization": "Bearer " + self._credential},
            ) as response:
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 16384:
                        raise ConnectionError("Grant response exceeded its budget")
                return self.grant_headers(httpx.Response(response.status_code, content=bytes(raw)))

    def request(self, method, path, payload=None, timeout=None):
        raw, body = self.request_body(method, path, payload)
        try:
            with httpx.Client(
                trust_env=False,
                follow_redirects=False,
                timeout=timeout or self.timeout,
                transport=self.transport,
                verify=self.verify,
            ) as client:
                headers = self.grant(client, body)
                self.note(body["request_id"], "unknown")
                deadline = time.monotonic() + (timeout or self.timeout)
                with client.stream(method, self.root + path, content=raw, headers=headers) as response:
                    result = bytearray()
                    for block in response.iter_bytes():
                        result.extend(block)
                        if len(result) > MAX_RESPONSE or time.monotonic() > deadline:
                            raise ConnectionError("Remote inference response exceeded its budget")
                    return self.decode(response.status_code, result, body["request_id"])
        except (httpx.HTTPError, ValueError, RecursionError):
            raise ConnectionError("Remote inference failed; the request was not replayed") from None

    async def async_request(self, method, path, payload=None):
        raw, body = self.request_body(method, path, payload)
        timeout = min(5, self.timeout) if path == "/v1/capabilities" else self.timeout
        try:
            async with asyncio.timeout(timeout):
                async with httpx.AsyncClient(
                    trust_env=False,
                    follow_redirects=False,
                    timeout=self.timeout,
                    transport=self.async_transport,
                    verify=self.verify,
                ) as client:
                    headers = await self.async_grant(client, body)
                    self.note(body["request_id"], "unknown")
                    async with client.stream(
                        method, self.root + path, content=raw, headers=headers
                    ) as response:
                        result = bytearray()
                        async for block in response.aiter_bytes():
                            result.extend(block)
                            if len(result) > MAX_RESPONSE:
                                raise ConnectionError("Remote inference output exceeds its limit")
                        return self.decode(response.status_code, result, body["request_id"])
        except (httpx.HTTPError, TimeoutError, ValueError, RecursionError):
            raise ConnectionError("Remote inference failed; the request was not replayed") from None
