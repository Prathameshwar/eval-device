"""Bounded private atomic local metadata; no clinical data or platform database."""

import copy
import json
import os
import re
import secrets
import tempfile
import threading
import time
from pathlib import Path

from .errors import require
from .security import checked, identity, protect

DEFAULTS = {
    "cpu_threads": 4,
    "gpu_device_index": 0,
    "gpu_layers": 20,
    "startup_timeout_seconds": 180,
    "drain_timeout_seconds": 30,
    "context_size": 2048,
    "max_tokens": 128,
}


LEGACY_DEFAULTS = {**DEFAULTS, "gpu_layers": 16}


def customized_settings(data):
    return bool(data.get("settings_customized")) or any(
        op.get("action") == "settings" for op in data.get("operations", ())
    )


def runtime_defaults(data):
    """Upgrade untouched factory preferences; preserve explicit operator choices."""
    values = {**DEFAULTS, **data.get("settings", {})}
    if values == LEGACY_DEFAULTS and not customized_settings(data):
        values["gpu_layers"] = DEFAULTS["gpu_layers"]
    return values


class Store:
    def __init__(self, root):
        self.root = checked(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.operator_file = self.root / "operator.json"
        if self.operator_file.exists():
            self.operator = self.read(self.operator_file, 4096)["operator"]
        else:
            self.operator = identity()
        require(self.operator == identity(), "operator", "State belongs to a different operator", 403)
        protect(self.root, self.operator)
        if not self.operator_file.exists():
            self.atomic(self.operator_file, {"operator": self.operator})
        self.lock = threading.RLock()
        self.path = self.root / "state.json"
        self.data = (
            self.read(self.path)
            if self.path.exists()
            else {
                "version": 1,
                "revision": 0,
                "settings": dict(DEFAULTS),
                "services": {},
                "operations": [],
                "logs": [],
                "inventory": {},
                "log_cursor": 0,
            }
        )
        require(self.data.get("version") == 1, "state_version", "Unsupported manager state version")
        defaults = runtime_defaults(self.data)
        if defaults != self.data["settings"]:
            self.data["revision"] += 1
        self.data["settings_customized"] = customized_settings(self.data)
        self.data["settings"] = defaults
        for op in self.data["operations"]:
            if op["state"] in {"queued", "running"}:
                op.update(
                    state="interrupted", error="Manager restarted; inspect state before submitting again."
                )
        self.save()
        self.key_file = self.root / "operator-key.txt"
        if not self.key_file.exists():
            self.atomic_bytes(self.key_file, (secrets.token_urlsafe(48) + "\n").encode("ascii"))
        checked(self.key_file, self.root)
        require(self.key_file.stat().st_size <= 256, "credentials", "Invalid local management credentials")
        self.key = self.key_file.read_text(encoding="ascii").strip()
        require(
            re.fullmatch(r"[A-Za-z0-9_-]{48,128}", self.key),
            "credentials",
            "Invalid local management credentials",
        )
        client_file = self.root / "client-key.txt"
        if not client_file.exists():
            self.atomic_bytes(client_file, (secrets.token_urlsafe(48) + "\n").encode("ascii"))
        checked(client_file, self.root)
        require(client_file.stat().st_size <= 256, "credentials", "Invalid inference credentials")
        self.client_key = client_file.read_text(encoding="ascii").strip()
        require(
            re.fullmatch(r"[A-Za-z0-9_-]{48,128}", self.client_key),
            "credentials",
            "Invalid inference credentials",
        )

    @staticmethod
    def read(path, limit=4 * 1024 * 1024):
        checked(path)
        with path.open("rb") as stream:
            raw = stream.read(limit + 1)
        require(len(raw) <= limit, "state_size", "Local metadata exceeds its limit")
        return json.loads(raw)

    def atomic_bytes(self, path, content):
        checked(path, self.root)
        fd, name = tempfile.mkstemp(prefix=".write-", dir=path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            checked(path, self.root)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def atomic(self, path, content):
        self.atomic_bytes(
            path, (json.dumps(content, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
        )

    def save(self):
        try:
            self.atomic(self.path, self.data)
        except Exception:
            if hasattr(self, "committed"):
                self.data = copy.deepcopy(self.committed)
            raise
        self.committed = copy.deepcopy(self.data)

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.data)

    def log(self, service, level, code):
        # Messages are internal fixed codes, never exception strings/native output.
        with self.lock:
            self.data["log_cursor"] += 1
            self.data["logs"].append(
                {
                    "cursor": self.data["log_cursor"],
                    "time": time.time(),
                    "service": service,
                    "level": level,
                    "message": code,
                }
            )
            self.data["logs"] = self.data["logs"][-1000:]
            self.save()

    def operation(self, request_id):
        with self.lock:
            return next((copy.deepcopy(op) for op in self.data["operations"] if op["id"] == request_id), None)

    def progress(self, request_id, **updates):
        with self.lock:
            op = next(op for op in self.data["operations"] if op["id"] == request_id)
            op.update(updates, updated=time.time())
            self.save()
