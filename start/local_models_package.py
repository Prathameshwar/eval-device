"""Allowed contents of the separate Manage Local Models portable release."""

from pathlib import PurePosixPath

NATIVE_MODULES = (
    "service.assets",
    "service.catalog",
    "service.manager",
    "service.security",
    "service.storage",
)


def native_module_path(name):
    if name not in NATIVE_MODULES:
        raise ValueError("Unexpected protected manager module")
    return "local-models/" + name.replace(".", "/") + ".cp312-win_amd64.pyd"


def validate_runtime(value):
    if value != {
        "version": 1,
        "application": "local-models",
        "role": "manager",
        "python": "3.12",
        "protection": "cython",
    }:
        raise ValueError("Invalid Local Models runtime metadata")
    return value


ROOT_FILES = {
    "Local-Models.exe",
    "manifest.json",
    "portable-runtime.json",
    "protection-manifest.json",
    "bundled-assets.json",
}
LOCAL_CONFIG = {"assets.lock.json", "voices.lock.json", "config.json"}
ENTRY_SCRIPTS = {"manage_local_models.py", "manage_service.py"}
INSTALL_SCRIPTS = {
    "client.py",
    "common.py",
    "install.py",
    "install_voices.py",
    "medical.py",
    "process_guard.py",
    "run.py",
}
PRIVATE_PARTS = {
    ".manager",
    ".models",
    ".library",
    ".runtime",
    ".state",
    ".downloads",
    ".voices",
    ".local",
    "models",
    "weights",
    "checkpoints",
    "voices",
    "tests",
    "test",
}
MODEL_SUFFIXES = {
    ".bin",
    ".caffemodel",
    ".ckpt",
    ".gguf",
    ".h5",
    ".keras",
    ".mlmodel",
    ".onnx",
    ".pb",
    ".pt",
    ".pth",
    ".safetensors",
    ".tflite",
}


def validate_path(relative, asset_paths=()):
    if (
        not isinstance(relative, str)
        or not relative
        or any(char in relative for char in "\\:\0")
    ):
        raise ValueError("Unsafe Local Models package path")
    parts = relative.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Unsafe Local Models package path")
    lower = [part.lower() for part in parts]
    if any(
        part
        in {
            ".manager",
            ".state",
            ".downloads",
            ".local",
            "tests",
            "test",
            "weights",
            "checkpoints",
        }
        or part.startswith(".env")
        for part in lower
    ):
        raise ValueError("Private state or model assets cannot be packaged")
    path = PurePosixPath(relative)
    if path.name.lower() in {
        "client-key.txt",
        "operator-key.txt",
        "worker-key.txt",
        "api-key.txt",
    }:
        raise ValueError("Model assets or credentials cannot be packaged")
    if relative in asset_paths:
        if relative.startswith(
            (
                "local-models/.library/qwen3.5-4b/",
                "local-models/.library/large-v3/",
                "local-models/.library/piper-en-male/",
                "local-models/.runtime/cpu/",
                "local-models/.runtime/cuda/",
                "local-models/.runtime/environments/asr/",
                "local-models/.runtime/environments/tts/",
            )
        ):
            return
        raise ValueError("Unexpected bundled asset location")
    if (
        any(part in PRIVATE_PARTS for part in lower)
        or path.suffix.lower() in MODEL_SUFFIXES
    ):
        raise ValueError("Unlisted model or runtime asset")
    if relative in ROOT_FILES or relative == "docs/local-models-portable.md":
        return
    if relative in {
        "tools/uv.exe",
        "licenses/uv-LICENSE-APACHE",
        "licenses/uv-LICENSE-MIT",
    }:
        return
    if relative in {f"local-models/{name}" for name in LOCAL_CONFIG}:
        return
    if (
        len(parts) == 2
        and parts[0] == "start"
        and path.name
        in {
            "local_models_check.py",
            "local_models_check.pyc",
            "local_models_package.py",
            "local_models_package.pyc",
        }
    ):
        return
    if (
        len(parts) == 2
        and parts[0] == "local-models"
        and path.name in {item for name in ENTRY_SCRIPTS for item in (name, name + "c")}
    ):
        return
    if relative.startswith("local-models/.venv/Scripts/"):
        return
    if (
        len(parts) == 3
        and parts[:2] == ["local-models", "scripts"]
        and path.name
        in {item for name in INSTALL_SCRIPTS for item in (name, name + "c")}
    ):
        return
    if len(parts) == 3 and parts[:2] in (
        ["local-models", "desktop"],
        ["local-models", "service"],
    ):
        if path.suffix in {".py", ".pyc", ".pyd"}:
            return
    if len(parts) == 4 and parts[:2] == ["local-models", "runtime-projects"]:
        if parts[2] in {"medical", "tts"} and parts[3] in {"pyproject.toml", "uv.lock"}:
            return
    if len(parts) == 3 and parts[:2] == ["device", "audio-process"]:
        if parts[2] in {"pyproject.toml", "uv.lock"}:
            return
    if relative.startswith(
        "device/audio-process/src/device_audio/"
    ) and path.suffix in {".py", ".pyc"}:
        return
    raise ValueError("File is outside the Manage Local Models runtime")
