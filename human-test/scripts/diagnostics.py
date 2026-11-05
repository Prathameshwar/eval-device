"""Discard child output; retain only allowlisted operational failure categories."""

import re
import threading
from collections import deque

FRAME = re.compile(r'^\s*File "[^"]*[/\\]([A-Za-z0-9_.-]+\.(?:py|pyx))", line (\d+), in ([A-Za-z0-9_.<>]+)')
ERROR_TYPE = re.compile(r"^([A-Za-z][A-Za-z0-9_.]*(?:Error|Exception))(?::|$)")

CATEGORIES = (
    (
        (
            "gpu is unavailable",
            "gpu offloading did not match",
            "cuda device is unavailable",
            "does not support int8_float16",
        ),
        "gpu_unavailable",
        False,
        "Inspect compute settings in Manage Local Models.",
    ),
    (
        ("integrity failure", "checksum mismatch", "model size mismatch"),
        "asset_integrity_failed",
        False,
        "Verify the assigned assets in Manage Local Models.",
    ),
    (
        ("an instance is already running", "configured port is in use"),
        "existing_instance",
        False,
        "Another desktop owns this connection; use that window or close it first.",
    ),
    (
        ("modulenotfounderror", "importerror", "dll load failed"),
        "dependency_missing",
        False,
        "Check this service's Python environment and required native packages.",
    ),
    (
        ("filenotfounderror", "model files are not installed", "not installed; run", "model/runtime missing"),
        "asset_missing",
        False,
        "Check the desktop installation; inspect model assets separately in Manage Local Models.",
    ),
    (
        ("permissionerror", "access is denied", "winerror 5"),
        "permission_denied",
        False,
        "Use the same Windows account that owns the private files and check their permissions.",
    ),
    (
        ("out of memory", "bad_alloc", "memoryerror", "needs free vram"),
        "memory_unavailable",
        False,
        "Free RAM/VRAM or explicitly select a smaller model or CPU configuration.",
    ),
    (
        ("validationerror",),
        "invalid_configuration",
        False,
        "Check the service configuration; retrying unchanged settings will not repair it.",
    ),
    (
        ("winerror 10048", "address already in use"),
        "port_conflict",
        False,
        "Check the occupied service port; no unrelated process will be stopped.",
    ),
)


class Diagnostics:
    def __init__(self, stream, observe=None):
        self.stream = stream
        self.observe = observe
        self.category = None
        self.frames = deque(maxlen=24)
        self.mutex = threading.Lock()
        self.thread = threading.Thread(target=self.consume, daemon=True, name="safe-service-diagnostics")
        self.thread.start()

    def consume(self):
        try:
            while block := self.stream.readline(8192):
                text = block.decode("utf-8", errors="replace")
                if self.observe:
                    self.observe(text)
                # Keep structural traceback metadata, never messages, code, paths or transcripts.
                frame = FRAME.match(text)
                kind = ERROR_TYPE.match(text)
                if frame or kind:
                    detail = (
                        f"  at {frame[1]}:{frame[2]} in {frame[3]}" if frame else f"exception={kind[1][:80]}"
                    )
                    with self.mutex:
                        self.frames.append(detail)
                line = text.lower()
                for patterns, code, retryable, hint in CATEGORIES:
                    if any(pattern in line for pattern in patterns):
                        if self.category is None:
                            self.category = (code, retryable, hint)
                        break
        except (OSError, ValueError):
            pass

    def failure(self, process):
        if process.poll() is not None:
            self.thread.join(timeout=0.2)
        if self.category:
            return self.category
        code = process.poll()
        if code is None:
            return "readiness_timeout", True, "The service did not reach readiness before its deadline."
        return (
            "process_exit",
            True,
            f"Exit code {code} (0x{code & 0xFFFFFFFF:08X}); the process stopped or crashed.",
        )

    def trace(self):
        with self.mutex:
            return "\n".join(self.frames) or "No structural child traceback was emitted."

    def close(self):
        self.thread.join(timeout=2)
        if not self.thread.is_alive():
            self.stream.close()
