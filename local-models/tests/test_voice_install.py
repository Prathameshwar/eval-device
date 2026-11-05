import hashlib
import importlib.util
import io
import tarfile
import urllib.error
from pathlib import Path

import pytest


def installer():
    spec = importlib.util.spec_from_file_location(
        "voice_install", Path(__file__).parents[1] / "scripts/install_voices.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_failed_download_closes_temporary_file_and_retries_five_times(tmp_path, monkeypatch):
    module, calls, waits = installer(), [], []

    def offline(*args, **kwargs):
        calls.append(True)
        raise urllib.error.URLError("fixture offline")

    monkeypatch.setattr(module.urllib.request, "urlopen", offline)
    monkeypatch.setattr(module.time, "sleep", waits.append)
    with pytest.raises(SystemExit, match="Could not download"):
        module.fetch(
            {"url": "https://example.test/voice", "archive": "voice.tar.gz", "bytes": 10, "sha256": "0" * 64},
            tmp_path,
        )
    assert len(calls) == 5 and waits == [1, 2, 4, 8]
    assert list(tmp_path.iterdir()) == []


def test_installed_voice_rejects_corruption_even_at_same_size(tmp_path, monkeypatch):
    module = installer()
    monkeypatch.setattr(module, "VOICES", tmp_path)
    target = tmp_path / "en-male"
    target.mkdir()
    spec = {"model": "voice.onnx", "config": "voice.json", "files": {}}
    for name in (spec["model"], spec["config"]):
        (target / name).write_bytes(b"test")
        spec["files"][name] = {"bytes": 4, "sha256": hashlib.sha256(b"test").hexdigest()}
    assert module.installed(spec, "en-male")
    (target / spec["model"]).write_bytes(b"FAIL")
    assert module.installed(spec, "en-male") is None


@pytest.mark.parametrize("compression,prefix", [("gz", ""), ("bz2", "piper-hindi")])
def test_publish_extracts_only_pinned_voice_files(tmp_path, compression, prefix):
    module = installer()
    spec = {"model": "voice.onnx", "config": "voice.json", "archive_prefix": prefix, "files": {}}
    archive = tmp_path / "voice.tar"
    with tarfile.open(archive, "w:" + compression) as bundle:
        for name in (spec["model"], spec["config"], "../../unwanted"):
            member = tarfile.TarInfo(f"{prefix}/{name}" if prefix else name)
            member.size = 4
            bundle.addfile(member, io.BytesIO(b"test"))
            spec["files"][name] = {"bytes": 4, "sha256": hashlib.sha256(b"test").hexdigest()}
    destination = tmp_path / "installed"
    model, config = module.publish(spec, archive, destination)
    assert model.read_bytes() == config.read_bytes() == b"test"
    assert sorted(p.name for p in destination.iterdir()) == ["voice.json", "voice.onnx"]
    # Repair is safe and leaves no temporary files or extracted auxiliary data.
    module.publish(spec, archive, destination)
    assert len(list(destination.iterdir())) == 2


@pytest.mark.parametrize("symlink", [False, True])
def test_publish_refuses_corrupt_or_linked_model_without_replacing_existing_file(tmp_path, symlink):
    module = installer()
    spec = {
        "model": "voice.onnx",
        "config": "voice.onnx",
        "archive_prefix": "hindi",
        "files": {"voice.onnx": {"bytes": 4, "sha256": hashlib.sha256(b"test").hexdigest()}},
    }
    archive = tmp_path / "voice.tar.bz2"
    with tarfile.open(archive, "w:bz2") as bundle:
        member = tarfile.TarInfo("hindi/voice.onnx")
        if symlink:
            member.type, member.linkname = tarfile.SYMTYPE, "../../outside"
            bundle.addfile(member)
        else:
            member.size = 4
            bundle.addfile(member, io.BytesIO(b"FAIL"))
    destination = tmp_path / "installed"
    destination.mkdir()
    target = destination / "voice.onnx"
    target.write_bytes(b"previous")
    with pytest.raises((SystemExit, ValueError), match="Unexpected archive member|SHA-256"):
        module.publish(spec, archive, destination)
    assert target.read_bytes() == b"previous" and list(destination.iterdir()) == [target]
