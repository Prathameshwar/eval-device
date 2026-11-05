"""Offline portable check; never starts a manager, worker, download or model."""

import importlib
import json
import multiprocessing
import os
import shutil
import subprocess
import sys
from importlib.machinery import ExtensionFileLoader
from pathlib import Path


def child_check(queue):
    queue.put("ready")


def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "local-models"))
    from local_models_package import NATIVE_MODULES, validate_path, validate_runtime
    from service.catalog import Catalog

    validate_runtime(
        json.loads((root / "portable-runtime.json").read_text(encoding="utf-8"))
    )
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise RuntimeError("Invalid release manifest")
    bundled = json.loads((root / "bundled-assets.json").read_text(encoding="utf-8"))
    if bundled.get("version") != 1 or bundled.get("models") != [
        "qwen3.5-4b",
        "large-v3",
        "piper-en-male",
    ]:
        raise RuntimeError("Incomplete model bundle")
    asset_paths = bundled.get("files")
    if not isinstance(asset_paths, dict) or any(
        manifest.get(name) != digest for name, digest in asset_paths.items()
    ):
        raise RuntimeError("Bundled asset inventory differs from release")
    for relative in manifest:
        validate_path(relative, asset_paths)
        if not (root / relative).is_file():
            raise RuntimeError("Portable release is missing a packaged file")
    protection = json.loads(
        (root / "protection-manifest.json").read_text(encoding="utf-8")
    )
    native = protection.get("native") if isinstance(protection, dict) else None
    if (
        protection.get("mode") != "cython"
        or not isinstance(native, dict)
        or set(native) != set(NATIVE_MODULES)
    ):
        raise RuntimeError("Incomplete native protection")
    for name, relative in native.items():
        module = importlib.import_module(name)
        if (
            not isinstance(module.__loader__, ExtensionFileLoader)
            or Path(module.__file__).resolve() != (root / relative).resolve()
        ):
            raise RuntimeError("Protected manager module is not native")
    for relative in protection["bytecode"]:
        if not (root / relative).is_file():
            raise RuntimeError("Missing protected bytecode")
    catalog = Catalog()
    if "qwen3-4b" not in catalog.models or not catalog.runtime_specs:
        raise RuntimeError("Manager model catalog is incomplete")
    for name in ("desktop.app", "service.daemon", "service.worker"):
        importlib.import_module(name)
    sys.path.insert(0, str(root / "local-models/scripts"))
    try:
        importlib.import_module("run")
        importlib.import_module("client")
    finally:
        sys.path.pop(0)
    from service.assets import Assets

    assets = Assets(catalog)
    for model_id in bundled["models"]:
        assets.verify(model_id)
    for capability, imports in (
        ("asr", "import faster_whisper,onnxruntime"),
        ("tts", "import piper"),
    ):
        subprocess.run(
            [str(assets.runtime_python(capability)), "-B", "-c", imports],
            cwd=root,
            capture_output=True,
            timeout=60,
            check=True,
        )
    import tkinter

    tkinter.Tcl()
    python = root / "local-models/.venv/Scripts/python.exe"
    uv = root / "tools/uv.exe"
    if Path(shutil.which("uv") or "").resolve() != uv.resolve():
        raise RuntimeError("Bundled uv is not on the manager process path")
    result = subprocess.run(
        [str(python), "-B", "-c", "import json,sys;print(json.dumps(sys.path))"],
        cwd=root,
        env={**os.environ, "PYTHONHOME": "invalid", "PYTHONPATH": "invalid"},
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    for path in json.loads(result.stdout):
        if not Path(path).resolve().is_relative_to(root):
            raise RuntimeError("Portable runtime contains an external Python path")
    subprocess.run([str(uv), "--version"], capture_output=True, timeout=15, check=True)
    context = multiprocessing.get_context("spawn")
    queue = context.Queue(maxsize=1)
    child = context.Process(target=child_check, args=(queue,))
    child.start()
    try:
        if queue.get(timeout=30) != "ready":
            raise RuntimeError("Portable child startup failed")
        child.join(timeout=30)
        if child.exitcode != 0:
            raise RuntimeError("Portable child shutdown failed")
    finally:
        if child.is_alive():
            child.terminate()
            child.join(timeout=5)
        queue.close()
        queue.join_thread()
    print(
        f"OK: {len(NATIVE_MODULES)} native modules, 3 models, ASR/TTS runtimes, Tcl, uv and private Python",
        flush=True,
    )
    print(
        "Offline bundle checks passed; native inference requires separate qualification.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
