"""Distribution privacy and relative interpreter paths are release invariants."""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "start"))
spec = importlib.util.spec_from_file_location(
    "build_human_test", ROOT / "start/build_human_test.py"
)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
protection_spec = importlib.util.spec_from_file_location(
    "protect_human_test", ROOT / "start/protect_human_test.py"
)
protection = importlib.util.module_from_spec(protection_spec)
protection_spec.loader.exec_module(protection)


def test_source_allowlist_excludes_private_state_and_tests():
    for relative in (
        "human-test/.env",
        "human-test/.local/platform-connection/connection.json",
        "human-test/scripts/tests/test_provisioning.py",
        "local-models/.state/api-key.txt",
        "device/audio-process/.models/small/model.bin",
        "platform/api/.env",
        "human-test/src/human_test/__pycache__/app.pyc",
        "human-test/src/human_test/history.sqlite",
        "human-test/scripts/provider-credentials.json",
        "human-test/scripts/recording.wav",
        "human-test/src/human_test/debug.pdb",
    ):
        assert not builder.included(relative)
    assert not builder.included("human-test/src/human_test/input-ignore.json")
    assert builder.included("human-test/.env.example")
    assert (
        builder.CLIENT_DEPENDENCIES["training_client"]
        == "shared/training-client/src/training_client"
    )
    assert not builder.included("local-models/assets.lock.json")
    assert not builder.included("local-models/client/src/local_model_client/llm.py")
    assert not builder.included(
        "shared/training-contracts/src/training_contracts/languages/packs/en/instructions.txt"
    )


def test_private_interpreter_has_only_relative_paths(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    for name in ("Lib", "DLLs", "tcl"):
        (base / name).mkdir()
    (base / "Lib/site-packages").mkdir()
    (base / "Lib/site-packages/secret.txt").write_text("excluded")
    (base / "python.exe").write_bytes(b"test")
    package = tmp_path / "package"
    for project in builder.PROJECTS:
        target = package / project / ".venv/Scripts"
        builder.private_python(base, target)
        paths = next(target.glob("python*._pth")).read_text().splitlines()
        for value in paths:
            if value != "import site":
                assert not Path(value).is_absolute()
                assert (target / value).resolve().is_relative_to(package)
        assert not (target / "Lib/site-packages/secret.txt").exists()
        resolved = {
            (target / value).resolve() for value in paths if value != "import site"
        }
        assert (package / "human-test/scripts").resolve() in resolved
        assert not any(
            "local-models" in path.relative_to(package).parts
            or "shared" in path.relative_to(package).parts
            for path in resolved
        )


def test_crt_copy_excludes_debug_and_system_libraries(tmp_path):
    source, target = tmp_path / "redist", tmp_path / "package"
    source.mkdir()
    target.mkdir()
    for name in ("msvcp140.dll", "msvcp140d.dll", "kernel32.dll"):
        (source / name).write_bytes(b"fixture")
    builder.copy_vc_runtime(source, target)
    assert [path.name for path in target.iterdir()] == ["msvcp140.dll"]


def test_latest_crt_is_selected_numerically(tmp_path, monkeypatch):
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    directories = []
    for version in ("14.9.12345", "14.51.36231"):
        directory = (
            tmp_path
            / "Microsoft Visual Studio/18/Community/VC/Redist/MSVC"
            / version
            / "x64/Microsoft.VC145.CRT"
        )
        directory.mkdir(parents=True)
        (directory / "msvcp140.dll").write_bytes(b"fixture")
        directories.append(directory)
    assert builder.find_vc_runtime() == directories[-1]


def test_protected_bytecode_imports_and_script_entrypoints(tmp_path):
    import subprocess
    import sys

    package = tmp_path / "human-test/src/private_app"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("VALUE = 42\n")
    (package / "feature.py").write_text(
        "from . import VALUE\ndef answer(): return VALUE\n"
    )
    scripts = tmp_path / "human-test/scripts"
    scripts.mkdir(parents=True)
    (scripts / "probe.py").write_text(
        "from pathlib import Path\n"
        "def answer(): return 42\n"
        "if __name__ == '__main__': print(answer(), Path(__file__).parent.name)\n"
    )
    bytecode, wrappers = protection.bytecode_sources(tmp_path)
    assert wrappers == ["human-test/scripts/probe.py"]
    assert len(bytecode) == 3
    assert not (package / "feature.py").exists()
    assert (scripts / "probe.py").read_text() == protection.WRAPPER
    code = (
        f"import sys;sys.path[:0]={[str(package.parent), str(scripts)]!r};"
        "import private_app.feature,probe;"
        "assert private_app.feature.answer()==probe.answer()==42;"
        "assert private_app.feature.answer.__code__.co_filename == "
        "'human-test/src/private_app/feature.py'"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
    result = subprocess.run(
        [sys.executable, str(scripts / "probe.py")],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "42 scripts"


def test_native_protection_covers_only_human_test_client_code():
    modules = {name for names in protection.NATIVE_MODULES.values() for name in names}
    assert {
        "training_client.local_turn",
        "training_client.session_sync",
        "training_client.history_outbox",
        "training_client.speech",
    } <= modules
    assert len(modules) == 11
    assert all(name.startswith(("human_test.", "training_client.")) for name in modules)
    assert not any(
        "local-models" in tree or "shared" in tree for tree in protection.SOURCE_TREES
    )


def test_native_failure_never_falls_back_to_unprotected_sources(tmp_path, monkeypatch):
    import pytest

    def fail(*args, **kwargs):
        raise RuntimeError("compiler failed")

    python = tmp_path / "python.exe"
    python.write_bytes(b"test")
    monkeypatch.setattr(builder, "run", fail)
    with pytest.raises(RuntimeError, match="compiler failed"):
        builder.protect_sources(tmp_path, "uv", False, python)
    assert not (tmp_path / "protection-manifest.json").exists()


def test_distribution_rejects_source_and_compiler_artifact_leaks(tmp_path, monkeypatch):
    import pytest

    monkeypatch.syspath_prepend(str(ROOT / "start"))
    native = {}
    for tree, modules in protection.NATIVE_MODULES.items():
        for name in modules:
            path = tmp_path / tree / (name.replace(".", "/") + ".cp312-win_amd64.pyd")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"native fixture")
            native[name] = path.relative_to(tmp_path).as_posix()
    (tmp_path / "protection-manifest.json").write_text(
        json.dumps(
            {
                "mode": "cython",
                "native": native,
                "bytecode": [],
                "entry_shims": [],
            }
        )
    )
    builder.validate_protection(tmp_path)
    leak = tmp_path / "human-test/src/human_test/private.py"
    for suffix, content in (
        (".py", "private source"),
        (".py", protection.WRAPPER),
        (".c", "generated C"),
        (".pdb", "symbols"),
        (".PYX", "native source"),
    ):
        path = leak.with_suffix(suffix)
        path.write_text(content)
        with pytest.raises(RuntimeError, match="leaked"):
            builder.validate_protection(tmp_path)
        path.unlink()
    undeclared = leak.with_suffix(".pyc")
    undeclared.write_bytes(b"unlisted implementation")
    with pytest.raises(RuntimeError, match="inventory"):
        builder.validate_protection(tmp_path)
    undeclared.unlink()
    critical = tmp_path / protection.CLIENT_LIBRARY / "training_client/local_turn.pyc"
    critical.write_bytes(b"recoverable implementation")
    with pytest.raises(RuntimeError, match="Unprotected native module"):
        builder.validate_protection(tmp_path)


def test_release_is_completed_before_finished_names_are_exposed(tmp_path):
    import hashlib
    import zipfile

    stage = tmp_path / ".building-release"
    stage.mkdir()
    (stage / "Human-test.exe").write_bytes(b"launcher fixture")
    release = tmp_path / "Human-test-protected"
    builder.release_package(stage, release)
    assert not stage.exists()
    archive = release.with_suffix(".zip")
    assert not archive.with_suffix(".zip.partial").exists()
    assert (
        archive.with_suffix(".zip.sha256").read_text().split()[0]
        == hashlib.sha256(archive.read_bytes()).hexdigest()
    )
    with zipfile.ZipFile(archive) as bundle:
        manifest = json.loads(bundle.read("Desktop-App/manifest.json"))
        assert (
            hashlib.sha256(bundle.read("Desktop-App/Human-test.exe")).hexdigest()
            == manifest["Human-test.exe"]
        )


def test_failed_relocated_self_test_does_not_publish_release(tmp_path):
    import pytest

    stage = tmp_path / ".building-release"
    stage.mkdir()
    (stage / "Human-test.exe").write_bytes(b"launcher fixture")
    release = tmp_path / "Human-test-protected"

    def fail(_finished):
        raise RuntimeError("relocated self-test failed")

    with pytest.raises(RuntimeError, match="relocated self-test failed"):
        builder.release_package(stage, release, verify_release=fail)
    assert stage.is_dir()
    assert not release.exists()
    assert not release.with_suffix(".zip").exists()
    assert not release.with_suffix(".zip.sha256").exists()
    assert not release.with_suffix(".zip.partial").exists()


def test_client_archive_uses_a_short_extraction_folder(tmp_path):
    import zipfile

    stage = tmp_path / ".building-release"
    stage.mkdir()
    (stage / "Human-test.exe").write_bytes(b"launcher fixture")
    release = tmp_path / "Human-test-windows-x64-runtime-protected-long-release-id"
    builder.release_package(stage, release)
    with zipfile.ZipFile(release.with_suffix(".zip")) as bundle:
        assert {name.split("/")[0] for name in bundle.namelist()} == {"Desktop-App"}
        assert bundle.read("Desktop-App/Human-test.exe") == b"launcher fixture"


def test_interrupted_archive_never_has_a_finished_name(tmp_path, monkeypatch):
    import pytest

    stage = tmp_path / ".building-release"
    stage.mkdir()
    (stage / "Human-test.exe").write_bytes(b"fixture")
    release = tmp_path / "Human-test-protected"

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(builder.zipfile.ZipFile, "open", fail)
    with pytest.raises(OSError, match="disk full"):
        builder.release_package(stage, release)
    assert stage.exists()
    assert not release.exists()
    assert not release.with_suffix(".zip").exists()
    assert not release.with_suffix(".zip.sha256").exists()


def test_release_rejects_private_state_and_linked_parent(tmp_path, monkeypatch):
    import pytest

    stage = tmp_path / ".building-release"
    stage.mkdir()
    (stage / ".env.local").write_text("private fixture")
    with pytest.raises(RuntimeError, match="Private application state"):
        builder.release_package(stage, tmp_path / "release")
    parent = stage / "linked"
    parent.mkdir()
    path = parent / "source.py"
    path.write_text("fixture")
    monkeypatch.setattr(Path, "is_junction", lambda self: self == parent)
    with pytest.raises(RuntimeError, match="Linked paths"):
        builder.checked_build_file(stage, path)


def test_archive_rejects_files_changed_after_manifest_hashing(tmp_path, monkeypatch):
    import pytest

    stage = tmp_path / ".building-release"
    stage.mkdir()
    launcher = stage / "Human-test.exe"
    launcher.write_bytes(b"original")
    release = tmp_path / "release"
    original = builder.zipfile.ZipFile.open

    def change(self, name, *args, **kwargs):
        if name.endswith("/Human-test.exe"):
            launcher.write_bytes(b"changed")
        return original(self, name, *args, **kwargs)

    monkeypatch.setattr(builder.zipfile.ZipFile, "open", change)
    with pytest.raises(RuntimeError, match="changed while writing"):
        builder.release_package(stage, release)
    assert not release.exists() and not release.with_suffix(".zip").exists()


def test_windows_arm64_is_not_mislabeled_as_x64(tmp_path, monkeypatch, capsys):
    import sys

    import pytest

    monkeypatch.setattr(builder.sysconfig, "get_platform", lambda: "win-arm64")
    monkeypatch.setattr(sys, "argv", ["build_human_test.py"])
    with pytest.raises(SystemExit) as error:
        builder.main()
    assert error.value.code == 2
    assert "Windows x64 Python 3.12" in capsys.readouterr().err
    with pytest.raises(RuntimeError, match="Windows x64 Python 3.12"):
        protection.protect(tmp_path, tmp_path)


def test_launcher_starts_with_case_colliding_windows_path_variables(tmp_path):
    import os
    import subprocess

    import pytest

    if os.name != "nt":
        pytest.skip("Windows launcher")
    compiler = (
        Path(os.environ["SystemRoot"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    )
    if not compiler.is_file():
        pytest.skip("Windows .NET Framework compiler unavailable")
    scripts = tmp_path / "human-test/.venv/Scripts"
    scripts.mkdir(parents=True)
    (tmp_path / "start").mkdir()
    (tmp_path / "start/portable_check.py").write_text("# launch marker\n")
    child = tmp_path / "Child.cs"
    child.write_text(
        "using System; class Child { static int Main() { "
        'if (Environment.GetEnvironmentVariable("PYTHONHOME") != null || '
        'Environment.GetEnvironmentVariable("PYTHONPATH") != null || '
        'Environment.GetEnvironmentVariable("PYTHONNOUSERSITE") != "1") return 2; '
        'Console.WriteLine("child-started"); return 0; } }'
    )
    subprocess.run(
        [
            str(compiler),
            "/nologo",
            "/target:exe",
            f"/out:{scripts / 'python.exe'}",
            str(child),
        ],
        check=True,
    )
    subprocess.run(
        [
            str(compiler),
            "/nologo",
            "/target:exe",
            f"/out:{tmp_path / 'Human-test.exe'}",
            str(ROOT / "start/portable/HumanTest.cs"),
        ],
        check=True,
    )
    value = os.environ.get("PATH", "")
    environment = {
        **os.environ,
        "PATH": value,
        "Path": value,
        "PYTHONHOME": "invalid",
        "PYTHONPATH": "invalid",
    }
    result = subprocess.run(
        [str(tmp_path / "Human-test.exe"), "--self-test"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "child-started" in result.stdout
