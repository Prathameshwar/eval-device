"""Local configuration and private API credentials; no extra Python packages."""

import csv
import hashlib
import json
import re
import secrets
import stat
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".state"
MODEL = ROOT / ".models/Qwen3-4B-Q4_K_M.gguf"
ALIAS = "qwen3-4b-local"


def no_link(path):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise RuntimeError("Linked/reparse paths are not allowed for local credentials")
    if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
        raise RuntimeError("Hard-linked files are not allowed")


def private_directory(path: Path) -> None:
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        identity = subprocess.check_output(
            ["whoami", "/user", "/fo", "csv", "/nh"],
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=5,
        )
        sid = next(csv.reader([identity.strip()]))[1]
        if not re.fullmatch(r"S-\d+(?:-\d+)+", sid):
            raise RuntimeError("permissions")
        api = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        pointer = ctypes.c_void_p
        api.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.POINTER(pointer),
            ctypes.POINTER(wintypes.ULONG),
        ]
        api.GetSecurityDescriptorDacl.argtypes = [
            pointer,
            ctypes.POINTER(wintypes.BOOL),
            ctypes.POINTER(pointer),
            ctypes.POINTER(wintypes.BOOL),
        ]
        api.SetNamedSecurityInfoW.argtypes = [
            wintypes.LPWSTR,
            ctypes.c_int,
            wintypes.DWORD,
            pointer,
            pointer,
            pointer,
            pointer,
        ]
        api.SetNamedSecurityInfoW.restype = wintypes.DWORD
        kernel.LocalFree.argtypes = [pointer]
        kernel.LocalFree.restype = pointer
        descriptor = pointer()
        if not api.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            f"D:P(A;OICI;FA;;;{sid})(A;OICI;FA;;;SY)", 1, ctypes.byref(descriptor), None
        ):
            raise RuntimeError("permissions")
        try:
            present, defaulted = wintypes.BOOL(), wintypes.BOOL()
            dacl = pointer()
            if (
                not api.GetSecurityDescriptorDacl(
                    descriptor,
                    ctypes.byref(present),
                    ctypes.byref(dacl),
                    ctypes.byref(defaulted),
                )
                or not present.value
            ):
                raise RuntimeError("permissions")
            # Replace the entire DACL: remove inherited AND explicit grants to other users.
            if api.SetNamedSecurityInfoW(str(path), 1, 0x80000004, None, None, dacl, None):
                raise RuntimeError("permissions")
        finally:
            kernel.LocalFree(descriptor)
    else:
        path.chmod(0o600 if path.is_file() else 0o700)


DEFAULT_MODEL = "qwen3.5-4b"
MODEL_NAMES = ("qwen3-4b", "qwen3-1.7b", "qwen3.5-4b", "qwenmedic-v1")


def model_profile(settings):
    name = settings.get("model", DEFAULT_MODEL)
    if name not in MODEL_NAMES:
        raise ValueError("Unsupported local model")
    if name == "qwen3.5-4b":
        return {
            "name": name,
            "alias": "qwen3.5-4b-local",
            "path": ROOT / ".models/Qwen3.5-4B-Q4_K_M.gguf",
            "minimum_free_vram_mib": 3500,
        }
    if name == "qwen3-1.7b":
        return {
            "name": name,
            "alias": "qwen3-1.7b-local",
            "path": ROOT / ".models/Qwen3-1.7B-Q8_0.gguf",
            "minimum_free_vram_mib": 2400,
        }
    if name == "qwenmedic-v1":
        return {
            "name": name,
            "alias": "qwenmedic-v1-local",
            "path": ROOT / ".models/qwenmedic-v1/QwenMedic-v1-Q4_K_M.gguf",
            "minimum_free_vram_mib": 1800,
        }
    return {"name": name, "alias": ALIAS, "path": MODEL, "minimum_free_vram_mib": 3200}


def config():
    bounds = {
        "gpu_device_index": (0, 15),
        "gpu_layers": (1, 99),
        "context_size": (512, 8192),
        "max_tokens": (16, 512),
        "cpu_threads": (1, 32),
        "port": (1024, 65535),
        "startup_timeout_seconds": (10, 600),
        "request_timeout_seconds": (5, 300),
    }
    required = {*bounds, "gpu_enabled", "system_prompt"}
    allowed = required | {"model", "prompt_cache_mib"}
    values = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    if not isinstance(values, dict) or (set(values) - allowed or required - set(values)):
        raise ValueError("config.json must contain exactly the supported configuration keys")
    local = ROOT / "config.local.json"
    if local.exists():
        override = json.loads(local.read_text(encoding="utf-8"))
        if not isinstance(override, dict) or set(override) - allowed:
            raise ValueError("Unknown local configuration keys")
        values.update(override)
    values.setdefault("model", DEFAULT_MODEL)
    # Optional for old configuration files; bounded RAM only, never a disk cache.
    values.setdefault("prompt_cache_mib", 256)
    if type(values["prompt_cache_mib"]) is not int or not 0 <= values["prompt_cache_mib"] <= 1024:
        raise ValueError("Invalid setting: prompt_cache_mib")
    model_profile(values)
    if type(values.get("gpu_enabled")) is not bool:
        raise ValueError("gpu_enabled must be true or false")
    for key, (low, high) in bounds.items():
        value = values.get(key)
        if type(value) is not int or not low <= value <= high:
            raise ValueError("Invalid setting: " + key)
    if values["max_tokens"] >= values["context_size"]:
        raise ValueError("max_tokens must be smaller than context_size")
    prompt = values.get("system_prompt")
    if not isinstance(prompt, str) or not 1 <= len(prompt) <= 4000:
        raise ValueError("system_prompt must contain 1-4000 characters")
    return values


class FileLock:
    """Windows process lock. Existing lock files are reusable after process exit."""

    def __init__(self, path, busy_message, timeout=0):
        self.path, self.busy_message, self.timeout = path, busy_message, timeout
        self.stream = None

    def __enter__(self):
        import msvcrt

        if self.path.exists() or self.path.is_symlink():
            no_link(self.path)
        self.stream = self.path.open("a+b")
        deadline = time.monotonic() + self.timeout
        try:
            while True:
                self.stream.seek(0)
                try:
                    msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
                    return self
                except OSError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError(self.busy_message) from None
                    time.sleep(0.02)
        except BaseException:
            self.stream.close()
            self.stream = None
            raise

    def __exit__(self, *_):
        import msvcrt

        try:
            self.stream.seek(0)
            msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            self.stream.close()
            self.stream = None


def credentials():
    for parent in (*reversed(STATE.parents), STATE):
        if parent.exists() or parent.is_symlink():
            no_link(parent)
    STATE.mkdir(exist_ok=True)
    private_directory(STATE)
    with FileLock(STATE / "credentials.lock", "Credential setup is busy; try again", timeout=5):
        path = STATE / "api-key.txt"
        if not path.exists():
            # Parent ACL is already private before any secret bytes are written.
            with path.open("x", encoding="ascii") as stream:
                stream.write(secrets.token_urlsafe(48) + "\n")
        no_link(path)
        private_directory(path)
        key = path.read_text(encoding="ascii").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{48,128}", key):
            raise ValueError("Invalid local API key file")
        return path, key


def verify_install(gpu, settings=None):
    profile = model_profile(settings or {})
    model = profile["path"]
    runtime = ROOT / ".runtime" / ("cuda" if gpu else "cpu")
    executable = runtime / "llama-server.exe"
    setup = {
        "qwenmedic-v1": "setup-qwenmedic.bat",
        "qwen3-1.7b": "setup-qwen3-1.7b.bat",
        "qwen3.5-4b": "setup-qwen3.5-4b.bat",
    }.get(profile["name"], "setup.bat")
    if not executable.is_file() or not model.is_file():
        raise RuntimeError(f"Local model/runtime missing. Run {setup} first.")
    manifest = json.loads((runtime / "manifest.json").read_text(encoding="utf-8"))
    if "llama-server.exe" not in manifest:
        raise RuntimeError("Incomplete runtime manifest; rerun setup.bat")
    for name, expected in manifest.items():
        if Path(name).name != name:
            raise RuntimeError("Invalid runtime manifest")
        with (runtime / name).open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                raise RuntimeError("Runtime integrity failure; rerun setup.bat")
    if profile["name"] == "qwenmedic-v1":
        from medical import verify_medical

        verify_medical(model.parent)
        return executable
    specs = json.loads((ROOT / "assets.lock.json").read_text(encoding="utf-8"))
    spec = specs["model"] if profile["name"] == "qwen3-4b" else specs["models"][profile["name"]]
    if model.stat().st_size != spec["bytes"]:
        raise RuntimeError(f"Model size mismatch; follow README integrity repair, then run {setup}")
    # Verify once per launch before loading, not per request.
    with model.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != spec["sha256"]:
            raise RuntimeError(f"Model checksum mismatch; follow README integrity repair, then run {setup}")
    return executable
