import os
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from dotenv import dotenv_values
from fastapi.testclient import TestClient

from pms_api.cli import init_local
from pms_api.core.config import Settings
from pms_api.main import create_app
from pms_api.security import training_keys as keys


def test_fresh_local_configuration_signs_and_keeps_private_material_out_of_output(tmp_path, capsys):
    config = tmp_path / ".env"
    init_local(config)
    key_path = Path(dotenv_values(config)[keys.SETTING])
    key = keys.load_training_key(key_path)
    key.public_key().verify(key.sign(b"training-grant"), b"training-grant")
    assert key_path.parent == tmp_path / ".local/training"
    assert key_path.read_text() not in capsys.readouterr().out
    before = (config.read_bytes(), key_path.read_bytes())
    with pytest.raises(RuntimeError, match="overwrite"):
        init_local(config)
    assert before == (config.read_bytes(), key_path.read_bytes())


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_upgrade_preserves_configuration_and_reuses_key(tmp_path, newline):
    config = tmp_path / ".env"
    original = f"# Existing deployment{newline}PMS_TOKEN_PEPPER=private-placeholder{newline}"
    config.write_bytes(original.encode())
    key_path = keys.ensure_training_configuration(config)
    assert config.read_bytes().startswith(original.encode())
    before = (config.read_bytes(), key_path.read_bytes())
    assert keys.ensure_training_configuration(config) == key_path
    assert before == (config.read_bytes(), key_path.read_bytes())
    assert config.read_bytes().count(keys.SETTING.encode()) == 1


def test_generated_key_is_usable_by_the_api_verification_route(tmp_path):
    config = tmp_path / ".env"
    config.write_text("# isolated API fixture\n")
    key_path = keys.ensure_training_configuration(config)
    settings = Settings(
        _env_file=None, token_pepper="p" * 40, media_signing_key="m" * 40, training_key_file=key_path
    )
    # This route has no database dependency; do not start application background workers.
    response = TestClient(create_app(settings)).get("/api/v1/training/verification-key")
    assert response.status_code == 200
    assert response.json()["algorithm"] == "EdDSA"
    verifier = serialization.load_pem_public_key(response.json()["public_key"].encode())
    verifier.verify(keys.load_training_key(key_path).sign(b"grant"), b"grant")
    assert "PRIVATE KEY" not in response.text


def test_existing_custom_key_resolves_from_runtime_directory_and_is_not_rotated(tmp_path):
    config = tmp_path / "api.env"
    config.write_text("PMS_OTHER=unchanged\n")
    key_path = keys.ensure_training_configuration(config)
    before = key_path.read_bytes()
    config.write_text(f'{keys.SETTING}="training-private.pem"\nPMS_OTHER=unchanged\n')
    assert keys.ensure_training_configuration(config, runtime_directory=key_path.parent) == key_path
    assert key_path.read_bytes() == before
    assert dotenv_values(config)["PMS_OTHER"] == "unchanged"


@pytest.mark.parametrize("kind", ["missing", "invalid", "rsa"])
def test_broken_configured_identity_is_never_replaced(tmp_path, kind):
    config = tmp_path / ".env"
    key_path = tmp_path / "original.pem"
    config.write_text(f'{keys.SETTING}="{key_path.as_posix()}"\n')
    before = None
    if kind == "invalid":
        before = b"private-corrupt-key-never-log"
    elif kind == "rsa":
        before = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    if before is not None:
        key_path.write_bytes(before)
        keys.private_directory(key_path)
    original = config.read_bytes()
    with pytest.raises(keys.TrainingKeyError) as error:
        keys.ensure_training_configuration(config)
    assert "private-corrupt" not in str(error.value)
    assert config.read_bytes() == original
    assert (key_path.read_bytes() if key_path.exists() else None) == before
    assert not (tmp_path / ".local").exists()


def test_failed_config_write_keeps_old_config_and_reuses_generated_key_on_retry(tmp_path, monkeypatch):
    config = tmp_path / ".env"
    config.write_text("PMS_OTHER=preserved\n")
    original = config.read_bytes()
    with monkeypatch.context() as patch:
        patch.setattr(keys.os, "replace", lambda *args: (_ for _ in ()).throw(OSError("private-error")))
        with pytest.raises(keys.TrainingKeyError, match="Could not provision"):
            keys.ensure_training_configuration(config)
    assert config.read_bytes() == original
    key_path = tmp_path / ".local/training/training-private.pem"
    before = key_path.read_bytes()
    keys.ensure_training_configuration(config)
    assert key_path.read_bytes() == before


def test_duplicate_settings_and_linked_files_are_rejected_without_changes(tmp_path):
    config = tmp_path / ".env"
    original = f"{keys.SETTING}=\n{keys.SETTING}=\n"
    config.write_text(original)
    with pytest.raises(keys.TrainingKeyError, match="Duplicate"):
        keys.ensure_training_configuration(config)
    assert config.read_text() == original
    config.write_text("PMS_OTHER=preserved\n")
    os.link(config, tmp_path / "alias.env")
    with pytest.raises(keys.TrainingKeyError):
        keys.ensure_training_configuration(config)
    assert config.read_text() == "PMS_OTHER=preserved\n"


def test_environment_override_is_validated_without_modifying_dotenv(tmp_path, monkeypatch):
    config = tmp_path / ".env"
    config.write_text("PMS_OTHER=preserved\n")
    key_path = keys.ensure_training_configuration(config)
    config.write_text("PMS_OTHER=preserved\n")
    monkeypatch.setenv(keys.SETTING, str(key_path))
    assert keys.prepare_local_training(config) == key_path
    assert config.read_text() == "PMS_OTHER=preserved\n"
    monkeypatch.setenv(keys.SETTING, str(tmp_path / "missing.pem"))
    with pytest.raises(keys.TrainingKeyError):
        keys.prepare_local_training(config)
    monkeypatch.setenv(keys.SETTING, "")
    with pytest.raises(keys.TrainingKeyError, match="empty"):
        keys.prepare_local_training(config)


def test_concurrent_setup_publishes_one_stable_signing_identity(tmp_path):
    config = tmp_path / ".env"
    config.write_text("PMS_OTHER=preserved\n")
    command = [
        sys.executable,
        "-c",
        "import sys; from pathlib import Path; from pms_api.security.training_keys import ensure_training_configuration; "
        "ensure_training_configuration(Path(sys.argv[1]))",
        str(config),
    ]
    children = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
    for child in children:
        output, error = child.communicate(timeout=30)
        assert child.returncode == 0, error.decode()
        assert not output
    key_path = Path(dotenv_values(config)[keys.SETTING])
    keys.load_training_key(key_path)
    before = key_path.read_bytes()
    keys.ensure_training_configuration(config)
    assert key_path.read_bytes() == before
    assert len(list(key_path.parent.glob("*.pem"))) == 1


@pytest.mark.skipif(sys.platform == "win32", reason="Unix service-group permissions")
def test_unix_generated_key_and_config_permissions(tmp_path):
    import grp

    config = tmp_path / "api.env"
    config.write_text("PMS_OTHER=preserved\n")
    config.chmod(0o600)
    runtime = tmp_path / "api"
    group = grp.getgrgid(os.getgid()).gr_name
    key_path = keys.ensure_training_configuration(
        config, default_key=runtime / "training-private.pem", key_group=group
    )
    assert key_path.stat().st_mode & 0o777 == 0o640
    assert runtime.stat().st_mode & 0o777 == 0o750 and runtime.stat().st_gid == os.getgid()
    assert config.stat().st_mode & 0o777 == 0o600
    assert key_path.stat().st_gid == os.getgid()
    key_path.chmod(0o644)
    with pytest.raises(keys.TrainingKeyError):
        keys.ensure_training_configuration(config)
