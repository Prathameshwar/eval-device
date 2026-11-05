"""Build a protected Windows Local Models release with selected verified assets."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from build_human_test import (
    checked_build_file,
    copy_vc_runtime,
    find_vc_runtime,
    private_python,
    run,
)
from local_models_package import (
    ENTRY_SCRIPTS,
    INSTALL_SCRIPTS,
    NATIVE_MODULES,
    native_module_path,
    validate_path,
    validate_runtime,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = {
    *(f"local-models/{name}" for name in ENTRY_SCRIPTS),
    *(f"local-models/scripts/{name}" for name in INSTALL_SCRIPTS),
    "local-models/assets.lock.json",
    "local-models/voices.lock.json",
    "local-models/config.json",
    "device/audio-process/pyproject.toml",
    "device/audio-process/uv.lock",
    "local-models/runtime-projects/medical/pyproject.toml",
    "local-models/runtime-projects/medical/uv.lock",
    "local-models/runtime-projects/tts/pyproject.toml",
    "local-models/runtime-projects/tts/uv.lock",
    "start/local_models_check.py",
    "start/local_models_package.py",
    "docs/local-models-portable.md",
}
SOURCE_TREES = (
    "local-models/desktop",
    "local-models/service",
    "device/audio-process/src/device_audio",
)
MODEL_IDS = ("qwen3.5-4b", "large-v3", "piper-en-male")


def bundled_assets(destination, uv, online):
    """Copy only pinned, verified models and working native runtimes."""
    sys.path.insert(0, str(ROOT / "local-models"))
    try:
        from service.assets import Assets, digest
        from service.catalog import Catalog

        catalog = Catalog()
        assets = Assets(catalog)
        selected = {}
        for model_id in MODEL_IDS:
            model = catalog.get(model_id)
            source = assets.verify(model_id)
            if model["method"] == "llm":
                names = (model["spec"]["name"],)
            elif model["method"] == "voice":
                names = tuple(model["spec"]["files"])
            else:
                source_manifest = next(
                    (
                        source / name
                        for name in (
                            "managed-manifest.json",
                            "conversion-manifest.json",
                            "download-manifest.json",
                        )
                        if (source / name).is_file()
                    ),
                    None,
                )
                if source_manifest is None:
                    raise RuntimeError(
                        "Whisper large-v3 has no verified file inventory"
                    )
                names = (
                    *json.loads(source_manifest.read_text(encoding="utf-8"))["files"],
                    source_manifest.name,
                )
            for name in names:
                source_file = checked_build_file(ROOT, source / name)
                target = destination / "local-models/.library" / model_id / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_file, target)
                selected[target.relative_to(destination).as_posix()] = digest(target)
        for kind in ("cpu", "cuda"):
            source = ROOT / "local-models/.runtime" / kind
            manifest = json.loads(
                (source / "manifest.json").read_text(encoding="utf-8")
            )
            if "llama-server.exe" not in manifest:
                raise RuntimeError(f"Incomplete {kind} engine")
            for name, expected in manifest.items():
                if Path(name).name != name or digest(source / name) != expected:
                    raise RuntimeError(f"Corrupt {kind} engine: {name}")
            for name in (*manifest, "manifest.json"):
                source_file = checked_build_file(ROOT, source / name)
                target = destination / "local-models/.runtime" / kind / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_file, target)
                selected[target.relative_to(destination).as_posix()] = digest(target)
    finally:
        sys.path.pop(0)
    python = destination / "local-models/.venv/Scripts/python.exe"
    for capability in ("asr", "tts"):
        project = destination / (
            "device/audio-process"
            if capability == "asr"
            else "local-models/runtime-projects/tts"
        )
        environment = destination / "local-models/.runtime/environments" / capability
        command = [
            uv,
            "sync",
            "--frozen",
            "--no-dev",
            "--no-install-project",
            "--python",
            python,
            "--project",
            project,
        ]
        if capability == "asr":
            command += ["--extra", "cuda"]
        env = {
            **os.environ,
            "UV_PROJECT_ENVIRONMENT": str(environment),
            "UV_LINK_MODE": "copy",
            "UV_PYTHON_DOWNLOADS": "never",
        }
        if not online:
            command.append("--offline")
        subprocess.run(command, env=env, check=True, timeout=1200)
        if not (environment / "Scripts/python.exe").is_file():
            raise RuntimeError(f"Missing {capability} runtime Python")
        for directory in sorted(
            environment.rglob("*"), key=lambda item: len(item.parts), reverse=True
        ):
            if directory.is_dir() and directory.name.lower() in {
                "test",
                "tests",
                "__pycache__",
            }:
                if not directory.resolve().is_relative_to(destination.resolve()):
                    raise RuntimeError(
                        "Runtime cleanup escaped the build staging directory"
                    )
                shutil.rmtree(directory)
        for source_file in environment.rglob("*"):
            if source_file.is_file():
                checked_build_file(destination, source_file)
                selected[source_file.relative_to(destination).as_posix()] = digest(
                    source_file
                )
    (destination / "bundled-assets.json").write_text(
        json.dumps({"version": 1, "models": MODEL_IDS, "files": selected}, indent=2),
        encoding="utf-8",
    )
    return selected


def asset_paths(destination):
    path = destination / "bundled-assets.json"
    if not path.is_file():
        return set()
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        value.get("version") != 1
        or tuple(value.get("models", ())) != MODEL_IDS
        or not isinstance(value.get("files"), dict)
    ):
        raise RuntimeError("Invalid bundled asset inventory")
    return set(value["files"])


def copy_sources(destination):
    paths = set(SOURCE_FILES)
    for tree in SOURCE_TREES:
        paths.update(
            path.relative_to(ROOT).as_posix() for path in (ROOT / tree).rglob("*.py")
        )
    for relative in sorted(paths):
        source = ROOT / relative
        if not source.is_file():
            raise RuntimeError(f"Missing Local Models source: {relative}")
        checked_build_file(ROOT, source)
        validate_path(relative)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def copy_uv(destination, uv):
    tools = destination / "tools"
    tools.mkdir()
    shutil.copy2(uv, tools / "uv.exe")
    version = subprocess.run(
        [str(uv), "--version"], capture_output=True, text=True, timeout=15, check=True
    ).stdout.strip()
    parts = version.split()
    if len(parts) < 2 or parts[0] != "uv":
        raise RuntimeError("Unable to identify bundled uv version")
    source = (
        uv.parent.parent
        / "Lib/site-packages"
        / ("uv-" + parts[1] + ".dist-info/licenses")
    )
    licenses = {
        "uv-LICENSE-APACHE": source / "LICENSE-APACHE",
        "uv-LICENSE-MIT": source / "LICENSE-MIT",
    }
    if not all(path.is_file() for path in licenses.values()):
        raise RuntimeError("Bundled uv requires its Apache and MIT license texts")
    target = destination / "licenses"
    target.mkdir()
    for name, source in licenses.items():
        checked_build_file(uv.parent.parent, source)
        shutil.copy2(source, target / name)


def private_runtime(destination, base, vc_runtime):
    target = destination / "local-models/.venv/Scripts"
    private_python(base, target)
    copy_vc_runtime(vc_runtime, target)
    (target / "python312._pth").write_text(
        "\n".join(
            (
                ".",
                "Lib",
                "DLLs",
                "Lib/site-packages",
                "../../../local-models",
                "../../../device/audio-process/src",
                "../../../start",
                "import site",
                "",
            )
        ),
        encoding="utf-8",
    )


def protect_sources(destination, uv, online, python=None):
    if python is None:
        python = ROOT / "start/.build-tools/protection/Scripts/python.exe"
        if not python.is_file():
            run([uv, "venv", python.parents[1], "--python", sys.executable])
        run(
            [
                uv,
                "pip",
                "install",
                "--python",
                python,
                "--no-build",
                *([] if online else ["--offline"]),
                "Cython==3.1.8",
                "setuptools==80.9.0",
            ]
        )
    python = python.resolve()
    if not python.is_file():
        raise RuntimeError("Protection build interpreter does not exist")
    with tempfile.TemporaryDirectory(prefix="local-models-native-") as work:
        run(
            [python, ROOT / "start/protect_local_models.py", destination, work],
            cwd=destination,
        )


def validate_protection(destination):
    value = json.loads(
        (destination / "protection-manifest.json").read_text(encoding="utf-8")
    )
    if value.get("mode") != "cython" or set(value.get("native", {})) != set(
        NATIVE_MODULES
    ):
        raise RuntimeError("Incomplete native manager protection")
    for name, relative in value["native"].items():
        path = checked_build_file(destination, destination / relative)
        if (
            not path.is_file()
            or path.suffix != ".pyd"
            or (path.parent / (name.split(".")[-1] + ".py")).exists()
        ):
            raise RuntimeError("Protected manager module is missing or has source")
    for relative in value["bytecode"]:
        if not (destination / relative).is_file():
            raise RuntimeError("Protected bytecode is missing")
    wrappers = set(value["entry_shims"])
    for tree in (*SOURCE_TREES, "local-models/scripts", "start"):
        for path in (destination / tree).rglob("*.py"):
            relative = path.relative_to(destination).as_posix()
            if relative not in wrappers:
                raise RuntimeError("Unprotected application source leaked into release")
    for name in ENTRY_SCRIPTS:
        if f"local-models/{name}" not in wrappers:
            raise RuntimeError("Unprotected manager entry point")


def verify_archive(archive):
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        names = {info.filename for info in members}
        if (
            len(names) != len(members)
            or len(members) > 100_000
            or sum(info.file_size for info in members) > 12_000_000_000
            or any(
                info.is_dir()
                or not info.filename.startswith("Local-Models/")
                or ((info.external_attr >> 16) & 0o170000) == 0o120000
                for info in members
            )
        ):
            raise RuntimeError("Invalid Local Models archive inventory")
        manifest = json.loads(bundle.read("Local-Models/manifest.json"))
        bundled = json.loads(bundle.read("Local-Models/bundled-assets.json"))
        if (
            bundled.get("version") != 1
            or tuple(bundled.get("models", ())) != MODEL_IDS
            or not isinstance(bundled.get("files"), dict)
        ):
            raise RuntimeError("Invalid bundled asset inventory")
        assets = bundled["files"]
        required_prefixes = tuple(
            "local-models/.library/" + model + "/" for model in MODEL_IDS
        ) + (
            "local-models/.runtime/cpu/",
            "local-models/.runtime/cuda/",
            "local-models/.runtime/environments/asr/",
            "local-models/.runtime/environments/tts/",
        )
        if any(
            not any(k.startswith(prefix) for k in assets)
            for prefix in required_prefixes
        ):
            raise RuntimeError("Selected model is missing")
        if any(manifest.get(name) != digest for name, digest in assets.items()):
            raise RuntimeError("Bundled asset checksum mismatch")
        if not isinstance(manifest, dict) or names != {
            "Local-Models/" + name for name in manifest
        } | {"Local-Models/manifest.json"}:
            raise RuntimeError("Local Models archive differs from its manifest")
        validate_runtime(json.loads(bundle.read("Local-Models/portable-runtime.json")))
        protection = json.loads(bundle.read("Local-Models/protection-manifest.json"))
        native = protection.get("native") if isinstance(protection, dict) else None
        if (
            not isinstance(native, dict)
            or protection.get("mode") != "cython"
            or set(native) != set(NATIVE_MODULES)
            or any(
                relative != native_module_path(name) or relative not in manifest
                for name, relative in native.items()
            )
        ):
            raise RuntimeError("Incomplete protected manager archive")
        for relative in protection.get("bytecode", ()):
            if relative not in manifest or not relative.endswith(".pyc"):
                raise RuntimeError("Incomplete manager bytecode archive")
        for relative, digest in manifest.items():
            try:
                validate_path(relative, assets)
            except ValueError as error:
                raise ValueError(f"Rejected release file: {relative}") from error
            if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
                raise RuntimeError("Invalid Local Models file checksum")
            with bundle.open("Local-Models/" + relative) as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                    raise RuntimeError("Local Models archive checksum mismatch")


def release_package(destination, release):
    files = {}
    assets = asset_paths(destination)
    for path in sorted(destination.rglob("*")):
        if path.is_file():
            checked_build_file(destination, path)
            relative = path.relative_to(destination).as_posix()
            try:
                validate_path(relative, assets)
            except ValueError as error:
                raise ValueError(f"Rejected release file: {relative}") from error
            with path.open("rb") as stream:
                files[relative] = hashlib.file_digest(stream, "sha256").hexdigest()
    manifest = destination / "manifest.json"
    manifest.write_text(json.dumps(files, indent=2), encoding="utf-8")
    archive = release.with_suffix(".zip")
    partial = archive.with_suffix(".zip.partial")
    checksum = archive.with_suffix(".zip.sha256")
    partial_checksum = checksum.with_suffix(".sha256.partial")
    if release.exists() or archive.exists() or checksum.exists():
        raise RuntimeError("Refusing to replace an existing release")
    with zipfile.ZipFile(
        partial, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=3
    ) as bundle:
        for relative in (*files, "manifest.json"):
            path = checked_build_file(destination, destination / relative)
            bundle.write(
                path,
                "Local-Models/" + relative,
                compress_type=zipfile.ZIP_STORED
                if relative in assets
                else zipfile.ZIP_DEFLATED,
            )
    verify_archive(partial)
    destination.rename(release)
    try:
        run([release / "Local-Models.exe", "--self-test"], cwd=release)
    except BaseException:
        release.rename(destination)
        partial.unlink(missing_ok=True)
        raise
    with partial.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    partial_checksum.write_text(digest + "  " + archive.name + "\n", encoding="ascii")
    partial_checksum.rename(checksum)
    partial.rename(archive)
    print("Portable archive:", archive, flush=True)
    print("SHA-256:", digest, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--online", action="store_true", help="Fetch missing protection build tools"
    )
    parser.add_argument(
        "--protection-python",
        type=Path,
        help="Existing Python with pinned Cython and setuptools",
    )
    parser.add_argument(
        "--vc-runtime", type=Path, help="Visual Studio x64 CRT directory"
    )
    args = parser.parse_args()
    if (
        sys.platform != "win32"
        or sys.version_info[:2] != (3, 12)
        or sysconfig.get_platform() != "win-amd64"
    ):
        parser.error("Build with Windows x64 Python 3.12")
    uv = shutil.which("uv")
    compiler = (
        Path(os.environ["SystemRoot"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    )
    if not uv or not compiler.is_file():
        parser.error("Build requires uv and the Windows .NET Framework C# compiler")
    vc_runtime = find_vc_runtime(args.vc_runtime)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    release = (
        ROOT / "start/dist" / f"Local-Models-windows-x64-runtime-protected-{stamp}"
    )
    destination = release.with_name(".building-" + release.name)
    destination.mkdir(parents=True)
    copy_sources(destination)
    copy_uv(destination, Path(uv))
    private_runtime(destination, Path(sys.base_prefix), vc_runtime)
    (destination / "portable-runtime.json").write_text(
        json.dumps(
            {
                "version": 1,
                "application": "local-models",
                "role": "manager",
                "python": "3.12",
                "protection": "cython",
            }
        ),
        encoding="utf-8",
    )
    protect_sources(destination, uv, args.online, args.protection_python)
    validate_protection(destination)
    bundled_assets(destination, Path(uv), args.online)
    run(
        [
            compiler,
            "/nologo",
            "/target:exe",
            "/platform:x64",
            f"/out:{destination / 'Local-Models.exe'}",
            ROOT / "start/portable/LocalModels.cs",
        ]
    )
    release_package(destination, release)


if __name__ == "__main__":
    main()
