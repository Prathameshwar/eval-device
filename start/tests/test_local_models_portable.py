"""Portable manager scope, config and release integrity."""

import hashlib
import importlib.util
import json
import os
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "start"))
spec = importlib.util.spec_from_file_location(
    "build_local_models", ROOT / "start/build_local_models.py"
)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def fake_stage(stage):
    from local_models_package import NATIVE_MODULES, native_module_path

    stage.mkdir()
    (stage / "Local-Models.exe").write_bytes(b"launcher fixture")
    (stage / "portable-runtime.json").write_text(
        json.dumps(
            {
                "version": 1,
                "application": "local-models",
                "role": "manager",
                "python": "3.12",
                "protection": "cython",
            }
        )
    )
    native = {name: native_module_path(name) for name in NATIVE_MODULES}
    for relative in native.values():
        path = stage / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"native fixture")
    (stage / "protection-manifest.json").write_text(
        json.dumps(
            {"mode": "cython", "native": native, "bytecode": [], "entry_shims": []}
        )
    )
    asset_files = (
        "local-models/.library/qwen3.5-4b/Qwen3.5-4B-Q4_K_M.gguf",
        "local-models/.library/large-v3/model.bin",
        "local-models/.library/piper-en-male/en_US-ryan-medium.onnx",
        "local-models/.runtime/cpu/llama-server.exe",
        "local-models/.runtime/cuda/llama-server.exe",
        "local-models/.runtime/environments/asr/Scripts/python.exe",
        "local-models/.runtime/environments/tts/Scripts/python.exe",
    )
    bundled = {}
    for relative in asset_files:
        path = stage / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(relative.encode())
        bundled[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    (stage / "bundled-assets.json").write_text(
        json.dumps(
            {
                "version": 1,
                "models": ["qwen3.5-4b", "large-v3", "piper-en-male"],
                "files": bundled,
            }
        )
    )


def test_source_copy_contains_manager_and_runtime_inputs_only(tmp_path):
    builder.copy_sources(tmp_path)
    for relative in (
        "local-models/assets.lock.json",
        "local-models/voices.lock.json",
        "local-models/config.json",
        "local-models/service/daemon.py",
        "local-models/service/worker.py",
        "local-models/scripts/install.py",
        "local-models/scripts/run.py",
        "local-models/scripts/client.py",
        "device/audio-process/src/device_audio/engine.py",
        "device/audio-process/uv.lock",
        "local-models/runtime-projects/medical/uv.lock",
        "local-models/runtime-projects/tts/uv.lock",
    ):
        assert (tmp_path / relative).is_file()
    assert not (tmp_path / "local-models/.models").exists()
    assert not (tmp_path / "local-models/.manager").exists()
    assert not (tmp_path / "local-models/tests").exists()
    assert not (tmp_path / "device/audio-process/tests").exists()


@pytest.mark.parametrize(
    "relative",
    [
        "local-models/.manager/operator-key.txt",
        "local-models/.library/model/weights.gguf",
        "local-models/.runtime/cpu/llama-server.exe",
        "local-models/.models/qwen.gguf",
        "local-models/.voices/en/voice.onnx",
        "local-models/config.local.json",
        "device/audio-process/.models/whisper/model.bin",
        "local-models/tests/test_manager.py",
        "local-models/service/debug.pdb",
        "local-models/../../private.txt",
    ],
)
def test_private_or_unneeded_content_is_rejected(relative):
    from local_models_package import validate_path

    with pytest.raises(ValueError):
        validate_path(relative)


def test_only_selected_asset_paths_are_allowed():
    from local_models_package import validate_path

    selected = {
        "local-models/.library/large-v3/model.bin",
        "local-models/.runtime/cpu/llama-server.exe",
    }
    for relative in selected:
        validate_path(relative, selected)
    for relative in (
        "local-models/.library/small/model.bin",
        "local-models/.manager/operator-key.txt",
        "local-models/.runtime/environments/asr/Lib/site-packages/pkg/tests/test.py",
    ):
        with pytest.raises(ValueError):
            validate_path(relative, {*selected, relative})


def test_release_verifies_manifest_and_does_not_expose_failed_self_test(
    tmp_path, monkeypatch
):
    stage = tmp_path / ".building-manager"
    fake_stage(stage)
    release = tmp_path / "Local-Models-protected"
    calls = []
    monkeypatch.setattr(
        builder, "run", lambda command, **kwargs: calls.append((command, kwargs))
    )
    builder.release_package(stage, release)
    assert calls[0][0] == [release / "Local-Models.exe", "--self-test"]
    archive = release.with_suffix(".zip")
    builder.verify_archive(archive)
    assert (
        archive.with_suffix(".zip.sha256").read_text().split()[0]
        == hashlib.sha256(archive.read_bytes()).hexdigest()
    )
    with zipfile.ZipFile(archive) as bundle:
        assert "Local-Models/Local-Models.exe" in bundle.namelist()
        assert "Local-Models/protection-manifest.json" in bundle.namelist()


def test_failed_relocated_check_keeps_zip_unpublished(tmp_path, monkeypatch):
    stage = tmp_path / ".building-manager"
    fake_stage(stage)
    release = tmp_path / "Local-Models-protected"

    def fail(*_args, **_kwargs):
        raise RuntimeError("self-test failed")

    monkeypatch.setattr(builder, "run", fail)
    with pytest.raises(RuntimeError, match="self-test failed"):
        builder.release_package(stage, release)
    assert stage.is_dir()
    assert not release.exists()
    assert not release.with_suffix(".zip").exists()


def test_release_rejects_missing_native_protection(tmp_path, monkeypatch):
    stage = tmp_path / ".building-manager"
    fake_stage(stage)
    manifest = stage / "protection-manifest.json"
    protection = json.loads(manifest.read_text())
    protection["native"].pop("service.security")
    manifest.write_text(json.dumps(protection))
    release = tmp_path / "Local-Models-protected"
    monkeypatch.setattr(builder, "run", lambda *_args, **_kwargs: None)
    with pytest.raises(RuntimeError, match="Incomplete protected manager archive"):
        builder.release_package(stage, release)
    assert not release.exists() and not release.with_suffix(".zip").exists()


@pytest.mark.parametrize("capability", ["asr", "tts"])
def test_isolated_runtime_uses_manager_python_without_system_install(
    tmp_path, monkeypatch, capability
):
    monkeypatch.syspath_prepend(str(ROOT / "local-models"))
    from service import assets as manager_assets

    local = tmp_path / "local-models"
    local.mkdir()
    catalog = SimpleNamespace(local_root=local, repo_root=tmp_path)
    manager = manager_assets.Assets(catalog)
    monkeypatch.setattr(
        manager_assets.shutil, "which", lambda name: "uv.exe" if name == "uv" else None
    )
    calls = []

    def run_owned(command, *, timeout, env):
        calls.append((command, env))
        python = Path(env["UV_PROJECT_ENVIRONMENT"]) / "Scripts/python.exe"
        python.parent.mkdir(parents=True)
        python.write_bytes(b"fixture")
        return 0

    monkeypatch.setattr(manager_assets, "run_owned", run_owned)
    assert manager.runtime(capability, False, lambda **_values: None).is_file()
    command, env = calls[0]
    assert command[command.index("--python") + 1] == sys.executable
    assert "--frozen" in command and "--no-install-project" in command
    assert os.path.isabs(env["UV_PROJECT_ENVIRONMENT"])
