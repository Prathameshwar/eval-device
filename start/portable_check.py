"""Offline portable-package check; no enrollment, models, camera or cloud calls."""

import importlib
import json
import multiprocessing
import os
import subprocess
import sys
from importlib.machinery import ExtensionFileLoader
from pathlib import Path


def spawn_worker(queue):
    queue.put("spawn-ready")


def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "human-test/scripts"))
    sys.path.insert(0, str(root / "start"))
    from external_pms import ExternalPMS
    from human_test.config import Settings
    from human_test.connection import DEFAULT_PLATFORM
    from human_test_package import (
        APP_NATIVE_MODULES,
        validate_client_path,
        validate_runtime,
    )

    protection = root / "protection-manifest.json"
    runtime = validate_runtime(json.loads((root / "portable-runtime.json").read_text()))
    # The release manifest is fixed at build time. A running desktop later creates
    # human-test/.env and .local; those private files are not distribution content.
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise RuntimeError("Invalid portable release manifest")
    for relative in manifest:
        validate_client_path(relative)
        if not (root / relative).is_file():
            raise RuntimeError("Portable release is missing a packaged file")
    if runtime.get("protection") == "cython":
        manifest = json.loads(protection.read_text())
        if manifest.get("mode") != "cython" or set(manifest["native"]) != set(
            APP_NATIVE_MODULES
        ):
            raise RuntimeError("Incomplete native protection manifest")
        for name, relative in manifest["native"].items():
            path = root / relative
            if not path.resolve().is_relative_to(root):
                raise RuntimeError("Invalid protected module path")
            module = importlib.import_module(name)
            if (
                not isinstance(module.__loader__, ExtensionFileLoader)
                or Path(module.__file__).resolve() != path.resolve()
                or path.with_name(path.name.split(".")[0] + ".py").exists()
                or path.with_name(path.name.split(".")[0] + ".pyc").exists()
            ):
                raise RuntimeError(f"Protected module is not native: {name}")
        for relative in manifest["bytecode"]:
            path = root / relative
            if not path.resolve().is_relative_to(root) or not path.is_file():
                raise RuntimeError("Missing protected bytecode")
        print(
            f"OK: {len(APP_NATIVE_MODULES)} native protected client modules and application bytecode",
            flush=True,
        )

    if (
        DEFAULT_PLATFORM != "https://eval.centralindia.cloudapp.azure.com"
        or Settings.model_fields["pms_url"].default != DEFAULT_PLATFORM
        or ExternalPMS.model_fields["pms_url"].default != DEFAULT_PLATFORM
    ):
        raise RuntimeError("Portable hosted API defaults do not match")
    projects = {
        "human-test": "human_test.app,training_client.runtime,training_contracts,local_model_client,sounddevice,cv2,av,tkinter,ownership,process_guard"
    }
    for project, modules in projects.items():
        python = root / project / ".venv/Scripts/python.exe"
        code = (
            "import importlib,json,sys,pathlib; "
            f"[importlib.import_module(n) for n in {modules.split(',')!r}]; "
            "print(json.dumps({'prefix':sys.prefix,'paths':sys.path}))"
        )
        result = subprocess.run(
            [str(python), "-B", "-c", code],
            cwd=root,
            env={**os.environ, "PYTHONHOME": "invalid", "PYTHONPATH": "invalid"},
            capture_output=True,
            text=True,
            timeout=90,
            check=True,
        )
        paths = json.loads(result.stdout)
        for path in [paths["prefix"], *paths["paths"]]:
            if not Path(path).resolve().is_relative_to(root):
                raise RuntimeError("Portable runtime contains an external Python path")
        print(f"OK: {project} private runtime and native imports", flush=True)
    import tkinter

    interpreter = tkinter.Tcl()
    print(f"OK: bundled Tcl {interpreter.eval('info patchlevel')}", flush=True)
    context = multiprocessing.get_context("spawn")
    queue = context.Queue(maxsize=1)
    child = context.Process(target=spawn_worker, args=(queue,))
    child.start()
    try:
        if queue.get(timeout=30) != "spawn-ready":
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
    print("OK: spawned recording-process runtime", flush=True)
    print(
        "Offline checks passed; enrollment and physical-device checks are separate.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
