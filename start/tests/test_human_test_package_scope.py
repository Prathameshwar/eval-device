"""Human-test packages contain the inference client, never local engines or assets."""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "start"))
spec = importlib.util.spec_from_file_location(
    "client_builder", ROOT / "start/build_human_test.py"
)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


@pytest.mark.parametrize(
    "relative",
    [
        "local-models/.models/test.gguf",
        "local-models/.manager/client-key.txt",
        "local-models/.runtime/cpu/llama-server.exe",
        "local-models/.voices/en/voice.onnx",
        "human-test/.venv/Scripts/Lib/site-packages/cv2/data/haarcascade_eye.xml",
        "human-test/.venv/Scripts/Lib/site-packages/cv2/data/nested/detector.xml",
        "human-test/.venv/Scripts/Lib/site-packages/vendor/weights.bin",
        "human-test/.venv/Scripts/Lib/site-packages/vendor/models/weights.dat",
        "local-models/service/worker.py",
        "local-models/scripts/install.py",
        "device/audio-process/src/device_audio/engine.py",
        "human-test/.local/platform-connection/connection.json",
    ],
)
def test_engine_model_and_credentials_are_not_client_sources(relative):
    assert not builder.included(relative)


@pytest.mark.parametrize(
    "relative",
    [
        "local-models/.models/test.gguf",
        "local-models/.manager/client-key.txt",
        "local-models/.runtime/cpu/llama-server.exe",
        "local-models/.voices/en/voice.onnx",
    ],
)
def test_release_rejects_model_assets_and_keys(tmp_path, relative):
    stage = tmp_path / "stage"
    path = stage / relative
    path.parent.mkdir(parents=True)
    path.write_bytes(b"private fixture")
    with pytest.raises(RuntimeError, match="Private application state"):
        builder.release_package(stage, tmp_path / "release")
    assert not (tmp_path / "release.zip").exists()


def test_only_human_test_environment_is_built():
    assert builder.PROJECTS == ("human-test",)
    assert not hasattr(builder, "bundle_models") and not hasattr(
        builder, "write_defaults"
    )
    assert not builder.included("local-models/client/src/local_model_client/audio.py")


def test_only_credential_free_environment_example_is_packaged():
    from human_test_package import validate_client_path

    validate_client_path("human-test/.env.example")
    for relative in (
        "human-test/.env",
        "human-test/.env.backup",
        "human-test/.local/state",
    ):
        with pytest.raises(ValueError, match="Private application state"):
            validate_client_path(relative)


@pytest.mark.parametrize(
    "relative",
    [
        "human-test/.venv/Scripts/Lib/site-packages/torch/__init__.py",
        "human-test/.venv/Scripts/Lib/site-packages/onnxruntime-1.0.dist-info/METADATA",
        "human-test/.venv/Scripts/Lib/site-packages/piper/__init__.py",
        "human-test/.venv/Scripts/Lib/site-packages/cv2/data/haarcascade_eye.xml",
        "human-test/.venv/Scripts/Lib/site-packages/cv2/data/nested/detector.xml",
        "human-test/.venv/Scripts/Lib/site-packages/vendor/weights.bin",
        "human-test/.venv/Scripts/Lib/site-packages/vendor/models/weights.dat",
        "human-test/.venv/Scripts/Lib/site-packages/numpy/random/tests/test_generator.py",
        "human-test/models/weights.onnx",
        "human-test/scripts/install_voices.py",
        "local-models/client/src/local_model_client/audio.py",
    ],
)
def test_release_rejects_engine_dependencies_and_other_apps(tmp_path, relative):
    stage = tmp_path / "stage"
    path = stage / relative
    path.parent.mkdir(parents=True)
    path.write_bytes(b"unexpected package fixture")
    with pytest.raises(RuntimeError):
        builder.release_package(stage, tmp_path / "release")
    assert not (tmp_path / "release.zip").exists()


@pytest.mark.parametrize("option", ["--cuda", "--bundle-models"])
def test_model_options_are_not_build_arguments(monkeypatch, capsys, option):
    monkeypatch.setattr(sys, "argv", ["build_human_test.py", option])
    with pytest.raises(SystemExit) as error:
        builder.main()
    assert error.value.code == 2
    assert "unrecognized arguments" in capsys.readouterr().err


def test_dependencies_install_inside_the_desktop_runtime(tmp_path):
    library = tmp_path / "human-test/.venv/Scripts/Lib/site-packages"
    builder.copy_client_dependencies(library)
    assert (library / "local_model_client/connection.py").is_file()
    assert (
        library / "training_contracts/languages/packs/en/instructions.txt"
    ).is_file()
    assert not (tmp_path / "local-models").exists()
    assert not (tmp_path / "shared").exists()
    assert not list(library.rglob("*.onnx")) and not list(library.rglob("*.gguf"))


def test_opencv_pretrained_cascades_are_removed_without_breaking_cv2_data(tmp_path):
    library = tmp_path / "site-packages"
    data = library / "cv2/data"
    data.mkdir(parents=True)
    (data / "__init__.py").write_text("haarcascades = 'path'\n")
    (data / "haarcascade_eye.xml").write_text("pretrained detector")
    builder.remove_dependency_models(library)
    assert (data / "__init__.py").is_file()
    assert not (data / "haarcascade_eye.xml").exists()


def test_wheel_tests_are_removed_without_touching_runtime_modules(tmp_path):
    library = tmp_path / "site-packages"
    package = library / "numpy"
    (package / "random/tests").mkdir(parents=True)
    (package / "random/tests/test_generator.py").write_text("fixture")
    (package / "random/__init__.py").write_text("fixture")
    builder.remove_dependency_tests(library)
    assert not (package / "random/tests").exists()
    assert (package / "random/__init__.py").is_file()


def test_distribution_excludes_benchmarks_and_repo_setup_metadata():
    for path in (
        "human-test/scripts/benchmark_history.py",
        "human-test/scripts/benchmark_video.py",
        "human-test/pyproject.toml",
        "human-test/uv.lock",
    ):
        assert not builder.included(path)
    assert builder.included("human-test/scripts/connection_startup.py")


@pytest.mark.parametrize("protection", [[], {}, None, 1])
def test_malformed_runtime_metadata_is_rejected_cleanly(protection):
    from human_test_package import validate_runtime

    with pytest.raises(ValueError, match="runtime metadata"):
        validate_runtime(
            {
                "version": 2,
                "application": "human-test",
                "role": "client",
                "python": "3.12.9",
                "protection": protection,
            }
        )


def test_windows_batch_reports_help_and_unknown_options_with_correct_exit_codes():
    import os
    import subprocess

    if os.name != "nt":
        pytest.skip("Windows batch launcher")
    batch = ROOT / "start/build-human-test.bat"
    valid = subprocess.run(
        [str(batch), "--help"], capture_output=True, text=True, timeout=15, check=False
    )
    assert valid.returncode == 0 and "--protection" in valid.stdout and not valid.stderr
    invalid = subprocess.run(
        [str(batch), "--bundle-models"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert (
        invalid.returncode == 2
        and "unrecognized arguments" in invalid.stdout
        and not invalid.stderr
    )
