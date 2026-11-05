"""NVIDIA runtime setup and a bounded hardware probe for automatic launchers."""

import json
import os
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from typing import Any

_dll_directories: list[Any] = []
_libraries: list[Any] = []
_windows_initialized = False


def prepare_windows_cuda() -> None:
    global _windows_initialized
    if sys.platform != "win32" or _windows_initialized:
        return
    import ctypes

    directories = []
    for package, component in (
        ("nvidia-cuda-runtime-cu12", "cuda_runtime"),
        ("nvidia-cublas-cu12", "cublas"),
        ("nvidia-cudnn-cu12", "cudnn"),
    ):
        try:
            root = Path(str(distribution(package).locate_file(f"nvidia/{component}/bin"))).resolve()
        except PackageNotFoundError:
            # An operator-provisioned CUDA/cuDNN installation on PATH also works.
            continue
        if root.is_dir():
            directories.append(root)
    for root in directories:
        _dll_directories.append(os.add_dll_directory(str(root)))
    if directories:
        # CTranslate2/cuDNN also use LoadLibrary internally; scope this to this process.
        os.environ["PATH"] = (
            os.pathsep.join(str(p) for p in directories) + os.pathsep + os.environ.get("PATH", "")
        )
        for name in ("cudart64_12.dll", "cublasLt64_12.dll", "cublas64_12.dll", "cudnn64_9.dll"):
            path = next((root / name for root in directories if (root / name).is_file()), None)
            if path is not None:
                _libraries.append(ctypes.WinDLL(str(path)))
    _windows_initialized = True


def prepare_whisper_cuda(device_index: int) -> None:
    import ctranslate2

    if device_index >= ctranslate2.get_cuda_device_count():
        raise RuntimeError("requested NVIDIA CUDA device is unavailable; GPU mode does not fall back to CPU")
    if "int8_float16" not in ctranslate2.get_supported_compute_types("cuda", device_index):
        raise RuntimeError("requested GPU does not support int8_float16 execution")
    prepare_windows_cuda()


def detect_whisper_device() -> dict[str, Any]:
    """Choose a usable CUDA device; return only safe operational metadata."""
    import ctranslate2

    result: dict[str, Any] = {
        "device": "cpu",
        "gpu_device_index": None,
        "total_vram_mib": None,
        "reason": "no_compatible_cuda_device",
    }
    try:
        count = min(ctranslate2.get_cuda_device_count(), 16)
        for index in range(count):
            if "int8_float16" not in ctranslate2.get_supported_compute_types("cuda", index):
                continue
            prepare_windows_cuda()
            if sys.platform == "win32":
                import ctypes

                # Also verify operator-provisioned libraries on PATH, not just wheels.
                for name in ("cudart64_12.dll", "cublas64_12.dll", "cudnn64_9.dll"):
                    _libraries.append(ctypes.WinDLL(name))
            result.update(device="cuda", gpu_device_index=index, reason="cuda_available")
            try:
                info = subprocess.run(
                    [
                        "nvidia-smi",
                        "--query-gpu=memory.total",
                        "--format=csv,noheader,nounits",
                        "--id=" + str(index),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if info.returncode == 0:
                    memory = int(info.stdout.strip())
                    if memory > 0:
                        result["total_vram_mib"] = memory
            except (OSError, ValueError, subprocess.TimeoutExpired):
                pass  # CUDA can work without nvidia-smi; retain conservative sharing.
            return result
    except (OSError, RuntimeError):
        result["reason"] = "cuda_runtime_unavailable"
    return result


if __name__ == "__main__":
    print(json.dumps(detect_whisper_device()))
