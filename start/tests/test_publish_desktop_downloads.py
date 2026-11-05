"""Only verified, protected Human-test client releases may enter its catalog."""

import hashlib
import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
spec = importlib.util.spec_from_file_location(
    "publish_downloads", Path(__file__).parents[1] / "publish_desktop_downloads.py"
)
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


def release(tmp_path, content=b"MZportable", extra=None, *, metadata=None, native=None):
    from protect_human_test import NATIVE_MODULES

    source = tmp_path / "Human-test-windows-x64-runtime-protected-test.zip"
    native = (
        native
        if native is not None
        else {
            name: tree + "/" + name.replace(".", "/") + ".cp312-win_amd64.pyd"
            for tree, modules in NATIVE_MODULES.items()
            for name in modules
        }
    )
    files = {
        "Human-test.exe": content,
        "portable-runtime.json": json.dumps(
            metadata
            or {
                "version": 2,
                "application": "human-test",
                "role": "client",
                "python": "3.12.9",
                "protection": "cython",
            }
        ).encode(),
        "protection-manifest.json": json.dumps(
            {"mode": "cython", "native": native}
        ).encode(),
        **{name: b"MZnative" for name in native.values()},
        **(extra or {}),
    }
    files["manifest.json"] = json.dumps(
        {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    ).encode()
    with zipfile.ZipFile(source, "w") as archive:
        for name, data in files.items():
            archive.writestr("Desktop-App/" + name, data)
    source.with_suffix(".zip.sha256").write_text(
        hashlib.sha256(source.read_bytes()).hexdigest()
    )
    root = tmp_path / "downloads"
    root.mkdir(exist_ok=True)
    return source, root


def test_verified_release_is_immutable_and_repeatable(tmp_path):
    source, root = release(tmp_path)
    original = source.read_bytes()
    published = publisher.install(source, root)
    assert published["id"] == "desktop-runtime"
    assert (root / published["filename"]).read_bytes() == original
    assert publisher.install(source, root) == published
    release(tmp_path, b"MZdifferent release")
    with pytest.raises(ValueError, match="immutable"):
        publisher.install(source, root)
    assert (root / published["filename"]).read_bytes() == original
    assert not list(root.glob("*.partial"))


def test_native_manifest_cannot_reuse_one_module_for_all_imports(tmp_path):
    from human_test_package import APP_NATIVE_MODULES

    path = "human-test/src/human_test/manikin.cp312-win_amd64.pyd"
    source, root = release(tmp_path, native=dict.fromkeys(APP_NATIVE_MODULES, path))
    with pytest.raises(ValueError, match="protected client"):
        publisher.install(source, root)


def test_corrupt_or_legacy_edition_is_never_published(tmp_path):
    source, root = release(tmp_path)
    legacy = source.with_name(source.name.replace("-runtime-", "-cuda-"))
    legacy.write_bytes(source.read_bytes())
    with pytest.raises(ValueError, match="protected"):
        publisher.install(legacy, root)
    source.write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="verification"):
        publisher.install(source, root)
    assert not list(root.iterdir())


def test_source_debug_packages_are_refused(tmp_path):
    source, root = release(tmp_path)
    debug = source.with_name(source.name.replace("protected", "debug-source"))
    source.rename(debug)
    with pytest.raises(ValueError, match="protected"):
        publisher.install(debug, root)


def test_failed_update_preserves_the_previous_catalog(tmp_path, monkeypatch):
    source, root = release(tmp_path)
    monkeypatch.setattr(
        sys, "argv", ["publish", "--root", str(root), "--client", str(source)]
    )
    publisher.main()
    before = (root / "catalog.json").read_bytes()
    assert [entry["id"] for entry in json.loads(before)] == ["desktop-runtime"]
    source.write_bytes(b"corrupt update")
    with pytest.raises(ValueError, match="verification"):
        publisher.main()
    assert (root / "catalog.json").read_bytes() == before
    assert not list(root.glob("*.partial"))


def test_publication_never_overwrites_a_concurrent_release(tmp_path, monkeypatch):
    source, root = release(tmp_path)
    original_link = publisher.os.link

    def concurrent_link(temporary, target):
        Path(target).write_bytes(b"concurrent release")
        original_link(temporary, target)

    monkeypatch.setattr(publisher.os, "link", concurrent_link)
    with pytest.raises(ValueError, match="immutable"):
        publisher.install(source, root)
    assert (root / source.name).read_bytes() == b"concurrent release"
    assert not list(root.glob("*.partial"))


def test_catalog_describes_verified_copy_when_source_changes(tmp_path, monkeypatch):
    source, root = release(tmp_path)
    original = source.read_bytes()
    prepare = publisher.prepare_metadata

    def mutate_source(path, directory):
        source.write_bytes(b"new source bytes after copy")
        prepare(path, directory)

    monkeypatch.setattr(publisher, "prepare_metadata", mutate_source)
    published = publisher.install(source, root)
    assert published["size_bytes"] == len(original)
    assert (root / source.name).read_bytes() == original


@pytest.mark.parametrize(
    "relative",
    [
        "local-models/service/worker.py",
        "local-models/.models/test.gguf",
        "human-test/.local/device.json",
        "human-test/.venv/Scripts/Lib/site-packages/piper/__init__.py",
        "human-test/scripts/offline_install.py",
        "../outside.py",
    ],
)
def test_model_management_or_private_files_cannot_be_published(tmp_path, relative):
    source, root = release(tmp_path, extra={relative: b"forbidden fixture"})
    with pytest.raises(ValueError):
        publisher.install(source, root)
    assert not list(root.iterdir())


def test_wrong_runtime_role_or_old_model_metadata_is_rejected(tmp_path):
    source, root = release(
        tmp_path,
        metadata={"cuda": False, "bundled_models": False, "protection": "cython"},
    )
    with pytest.raises(ValueError, match="runtime metadata"):
        publisher.install(source, root)
    assert not list(root.iterdir())


def test_native_protection_cannot_include_shared_inference_modules(tmp_path):
    native = {
        "training_contracts." + str(index): "human-test/src/human_test/test"
        + str(index)
        + ".pyd"
        for index in range(8)
    }
    source, root = release(tmp_path, native=native)
    with pytest.raises(ValueError, match="Human-test code"):
        publisher.install(source, root)
    assert not list(root.iterdir())
