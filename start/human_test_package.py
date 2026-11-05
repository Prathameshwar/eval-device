"""Scope of the Human-test portable client, shared by build and publication checks."""

from itertools import pairwise
from pathlib import PurePosixPath

APP_NATIVE_MODULES = (
    "training_client.runtime",
    "training_client.sessions",
    "training_client.recording",
    "training_client.controller",
    "training_client.local_turn",
    "training_client.session_sync",
    "training_client.speech",
    "training_client.listening",
    "training_client.conversation_history",
    "training_client.history_outbox",
    "human_test.manikin",
)


def native_module_path(name):
    if name not in APP_NATIVE_MODULES:
        raise ValueError("Unexpected protected client module")
    tree = (
        "human-test/src"
        if name.startswith("human_test.")
        else "human-test/.venv/Scripts/Lib/site-packages"
    )
    return tree + "/" + name.replace(".", "/") + ".cp312-win_amd64.pyd"


APP_SCRIPTS = frozenset(
    {
        "connection_startup.py",
        "connection_window.py",
        "demo.py",
        "diagnostics.py",
        "external_pms.py",
        "ownership.py",
        "process_guard.py",
        "provisioning.py",
        "runtime_environment.py",
        "startup.py",
        "supervisor.py",
    }
)
ROOT_FILES = frozenset(
    {
        "Human-test.exe",
        "manifest.json",
        "portable-runtime.json",
        "protection-manifest.json",
    }
)
START_FILES = frozenset({"launch.py", "portable_check.py", "human_test_package.py"})
PRIVATE_PARTS = frozenset(
    {
        ".local",
        ".state",
        ".manager",
        ".models",
        ".voices",
        ".library",
        ".runtime",
        ".recordings",
        ".downloads",
        "models",
        "weights",
        "checkpoints",
        "voices",
    }
)
ENGINE_PACKAGES = frozenset(
    {
        "device_audio",
        "device_video",
        "llama_cpp",
        "piper",
        "torch",
        "torchaudio",
        "torchvision",
        "tensorflow",
        "transformers",
        "ctranslate2",
        "faster_whisper",
        "whisper",
        "onnxruntime",
        "nvidia",
        "huggingface_hub",
        "sherpa_onnx",
    }
)
MODEL_SUFFIXES = frozenset(
    {
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
)


def validate_client_path(relative):
    """Reject engines/assets, private state and paths outside the client layout."""
    if (
        not isinstance(relative, str)
        or not relative
        or any(c in relative for c in ("\\", ":", "\0"))
    ):
        raise ValueError("Unsafe client package path")
    parts = relative.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Unsafe client package path")
    lower = [part.lower() for part in parts]
    if relative != "human-test/.env.example" and any(
        part in PRIVATE_PARTS or part.startswith(".env") for part in lower
    ):
        raise ValueError("Private application state leaked into distribution")
    path = PurePosixPath(relative)
    opencv_data = any(
        first == "cv2" and second == "data" for first, second in pairwise(lower)
    )
    if (
        path.suffix.lower() in MODEL_SUFFIXES
        or path.name.lower().startswith(("haarcascade_", "lbpcascade_"))
        or (opencv_data and path.suffix.lower() == ".xml")
        or path.name.lower()
        in {
            "model.bin",
            "pytorch_model.bin",
            "llama-server.exe",
            "client-key.txt",
            "api-key.txt",
            "worker-key.txt",
        }
    ):
        raise ValueError("Model assets or inference engines are not part of Human-test")
    if any(part.split("-")[0] in ENGINE_PACKAGES for part in lower):
        raise ValueError("Inference engine dependency is not part of Human-test")
    if any(part in {"test", "tests"} for part in lower):
        raise ValueError("Dependency test suites are not part of Human-test")
    if relative in ROOT_FILES or relative in {
        "docs/human-test-portable.md",
        "human-test/.env.example",
    }:
        return
    if (
        len(parts) == 2
        and parts[0] == "start"
        and path.with_suffix(".py").name in START_FILES
        and path.suffix in {".py", ".pyc"}
    ):
        return
    if relative == "human-test/portable-requirements.txt":
        return
    if relative.startswith("human-test/.venv/Scripts/"):
        return  # Locked desktop dependencies and the private Python/Tcl runtime.
    if relative.startswith("human-test/src/human_test/") and path.suffix in {
        ".py",
        ".pyc",
        ".pyd",
        ".json",
    }:
        return
    if (
        len(parts) == 3
        and parts[:2] == ["human-test", "scripts"]
        and path.with_suffix(".py").name in APP_SCRIPTS
        and path.suffix in {".py", ".pyc"}
    ):
        return
    raise ValueError("File is outside the Human-test client package")


def validate_runtime(value, *, protected=False):
    expected = {"version", "application", "role", "python", "protection"}
    if (
        not isinstance(value, dict)
        or set(value) != expected
        or type(value["version"]) is not int
        or value["version"] != 2
        or value["application"] != "human-test"
        or value["role"] != "client"
        or not isinstance(value["python"], str)
        or not isinstance(value["protection"], str)
        or value["protection"] not in {"cython", "none"}
    ):
        raise ValueError("Invalid Human-test client runtime metadata")
    if protected and value["protection"] != "cython":
        raise ValueError("Only protected client releases may be published")
    return value
