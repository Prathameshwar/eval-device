"""Bounded loopback inference transport; no process or management operations."""

import asyncio
import json
import os
import re
import threading
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path

import httpx
from training_contracts.privacy import no_link

DEFAULT_STATE = Path(__file__).resolve().parents[3] / ".manager"
_config = {"state": None, "port": 8790, "key": None}
_snapshot: dict = {}
_lock = threading.Lock()
MAX_RESPONSE = 6_000_000
READINESS_TIMEOUT_SECONDS = 5


class ConnectionError(Exception):
    def __init__(self, message, code="unavailable", status=503):
        self.code, self.status = code, status
        super().__init__(message)


def configure(*, state=None, port=8790, key=None, capabilities=None):
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ConnectionError("Invalid local manager port", "configuration")
    with _lock:
        _config.update(state=state, port=port, key=key)
        _snapshot.clear()
        if capabilities:
            _snapshot.update(validate_capabilities(capabilities))


def client_key(state=None):
    root = Path(state or os.environ.get("LOCAL_MODELS_STATE_DIR") or DEFAULT_STATE).absolute()
    if ".." in root.parts:
        raise ConnectionError("Invalid local manager state path", "configuration")
    path = root / "client-key.txt"
    try:
        for part in (*reversed(path.parents), path):
            no_link(part)
        if path.stat().st_size > 256:
            raise ValueError()
        key = path.read_text(encoding="ascii").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{48,128}", key):
            raise ValueError()
        return key
    except (OSError, ValueError, UnicodeError):
        raise ConnectionError(
            "Open Manage Local Models and start the assigned services; check the inference connection settings",
            "credentials",
        ) from None


def validate_capabilities(value):
    if (
        not isinstance(value, dict)
        or type(value.get("version")) is not int
        or value["version"] != 1
        or not isinstance(value.get("models"), list)
        or not isinstance(value.get("services"), dict)
    ):
        raise ConnectionError("Invalid manager capabilities", "invalid_response")
    models, services = value["models"], value["services"]
    if (
        len(models) > 256
        or len(services) > 4
        or type(value.get("revision")) is not int
        or value["revision"] < 0
    ):
        raise ConnectionError("Invalid manager capabilities", "invalid_response")
    identifiers = set()
    for model in models:
        if (
            not isinstance(model, dict)
            or not isinstance(model.get("capability"), str)
            or model.get("capability") not in {"llm", "asr", "tts", "video"}
            or any(not isinstance(model.get(k), str) or not 1 <= len(model[k]) <= 200 for k in ("id", "name"))
            or model["id"] in identifiers
        ):
            raise ConnectionError("Invalid manager model catalogue", "invalid_response")
        identifiers.add(model["id"])
        fields = (
            ("alias",)
            if model["capability"] == "llm"
            else ("key", "language", "gender")
            if model["capability"] == "tts"
            else ()
        )
        if any(not isinstance(model.get(k), str) or not 1 <= len(model[k]) <= 200 for k in fields) or (
            model["capability"] == "tts"
            and (model["gender"] not in {"male", "female"} or type(model.get("default")) is not bool)
        ):
            raise ConnectionError("Invalid manager model catalogue", "invalid_response")
    for kind, service in services.items():
        if (
            kind not in {"llm", "asr", "tts", "video"}
            or not isinstance(service, dict)
            or type(service.get("ready")) is not bool
            or not isinstance(service.get("state"), str)
            or not isinstance(service.get("model_id"), str)
        ):
            raise ConnectionError("Invalid manager service status", "invalid_response")
        if service["ready"] and not any(
            m["id"] == service["model_id"] and m["capability"] == kind for m in models
        ):
            raise ConnectionError("Ready service has no verified model", "invalid_response")
    return value


def remember(value):
    validate_capabilities(value)
    with _lock:
        _snapshot.clear()
        _snapshot.update(value)
    return value


def voices(snapshot):
    services = snapshot.get("services", {})
    if not services.get("tts", {}).get("ready"):
        return []
    return [
        {
            "key": m["key"],
            "label": m["name"],
            "language": m["language"],
            "gender": m["gender"],
            "default": m["default"],
        }
        for m in snapshot.get("models", [])
        if m.get("capability") == "tts"
    ]


def catalogue():
    with _lock:
        return voices(_snapshot)


class Connection:
    def __init__(
        self,
        state=None,
        port=None,
        key=None,
        timeout=180,
        client=None,
        *,
        capabilities=None,
        inherit_defaults=True,
    ):
        with _lock:
            defaults = dict(_config) if inherit_defaults else {"state": None, "port": 8790, "key": None}
            snapshot = deepcopy(_snapshot) if inherit_defaults else {}
        self.state = state if state is not None else defaults["state"]
        self.port = port if port is not None else defaults["port"]
        self.key = key if key is not None else defaults["key"]
        if type(self.port) is not int or not 1024 <= self.port <= 65535:
            raise ConnectionError("Invalid local manager port", "configuration")
        self.root = f"http://127.0.0.1:{self.port}"
        self.timeout = timeout
        self.client = client
        self._metadata_lock = threading.Lock()
        self._metadata = {}
        if capabilities or snapshot:
            self.remember(capabilities or snapshot)

    def remember(self, value):
        snapshot = deepcopy(validate_capabilities(value))
        with self._metadata_lock:
            self._metadata = snapshot
        return deepcopy(snapshot)

    def clear_capabilities(self):
        with self._metadata_lock:
            self._metadata = {}

    def catalogue(self):
        with self._metadata_lock:
            return voices(self._metadata)

    @property
    def headers(self):
        return {"Authorization": "Bearer " + (self.key or client_key(self.state))}

    def request(self, method, path, payload=None, timeout=None):
        if (method, path) not in {("GET", "/v1/capabilities"), ("POST", "/v1/infer/tts")}:
            raise ConnectionError("Unsupported inference-client operation", "permission_denied", 403)
        try:
            context = (
                nullcontext(self.client)
                if self.client is not None
                else httpx.Client(trust_env=False, follow_redirects=False, timeout=timeout or self.timeout)
            )
            with context as client:
                with client.stream(method, self.root + path, headers=self.headers, json=payload) as response:
                    raw = bytearray()
                    for block in response.iter_bytes():
                        raw.extend(block)
                        if len(raw) > (131072 if path == "/v1/capabilities" else MAX_RESPONSE):
                            raise ConnectionError("Manager response exceeded its limit", "invalid_response")
                    value = json.loads(raw)
                    if not isinstance(value, dict):
                        raise ValueError()
                    if response.status_code != 200:
                        code = value.get("code", "unavailable")
                        raise ConnectionError(
                            "Local inference is unavailable; inspect Manage Local Models",
                            code
                            if isinstance(code, str)
                            and code
                            in {
                                "not_running",
                                "model_mismatch",
                                "capacity",
                                "language",
                                "input",
                                "stopping",
                                "unauthorized",
                                "permission_denied",
                                "output_limit",
                                "unavailable",
                                "timeout",
                                "internal",
                                "not_found",
                                "integrity",
                                "missing_model",
                                "draining",
                            }
                            else "unavailable",
                            response.status_code,
                        )
                    return value
        except httpx.HTTPError:
            raise ConnectionError(
                "Unable to connect to Manage Local Models; inference was not replayed"
            ) from None
        except (ValueError, UnicodeError, RecursionError):
            raise ConnectionError("Invalid manager response", "invalid_response") from None

    def capabilities(self):
        return self.remember(self.request("GET", "/v1/capabilities", timeout=5))

    def require(self, capability, expected=None):
        info = self.capabilities()
        service = info["services"].get(capability, {})
        if service.get("ready") is not True or service.get("state") != "Ready":
            raise ConnectionError(
                f"Start the {capability} service in Manage Local Models", "not_running", 409
            )
        model = next((m for m in info["models"] if m.get("id") == service.get("model_id")), {})
        if expected and expected not in {model.get("id"), model.get("alias")}:
            raise ConnectionError("Assigned model does not match Manage Local Models", "model_mismatch", 409)
        return service

    async def async_request(self, method, path, payload=None):
        if (method, path) not in {("GET", "/v1/capabilities"), ("POST", "/v1/infer/asr")}:
            raise ConnectionError("Unsupported inference-client operation", "permission_denied", 403)
        owned = self.client is None
        client = self.client or httpx.AsyncClient(
            trust_env=False, follow_redirects=False, timeout=self.timeout
        )
        timeout = READINESS_TIMEOUT_SECONDS if path == "/v1/capabilities" else self.timeout
        try:
            async with asyncio.timeout(timeout):
                async with client.stream(
                    method, self.root + path, headers=self.headers, json=payload
                ) as response:
                    raw = bytearray()
                    async for block in response.aiter_bytes():
                        raw.extend(block)
                        if len(raw) > (131072 if path == "/v1/capabilities" else MAX_RESPONSE):
                            raise ConnectionError("Manager response exceeded its limit", "invalid_response")
                    value = json.loads(raw)
                    if not isinstance(value, dict):
                        raise ValueError()
                    if response.status_code != 200:
                        code = value.get("code", "unavailable")
                        raise ConnectionError(
                            "Local inference is unavailable; inspect Manage Local Models",
                            code
                            if isinstance(code, str)
                            and code
                            in {
                                "not_running",
                                "model_mismatch",
                                "capacity",
                                "language",
                                "input",
                                "stopping",
                                "unauthorized",
                                "permission_denied",
                                "output_limit",
                                "unavailable",
                                "timeout",
                                "internal",
                                "not_found",
                                "integrity",
                                "missing_model",
                                "draining",
                            }
                            else "unavailable",
                            response.status_code,
                        )
                    return value
        except (httpx.HTTPError, TimeoutError):
            raise ConnectionError("Local inference connection failed; the request was not replayed") from None
        except (ValueError, UnicodeError, RecursionError):
            raise ConnectionError("Invalid manager response", "invalid_response") from None
        finally:
            if owned:
                await client.aclose()
