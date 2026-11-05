"""Operator-owned training key provisioning. Never rotate a configured identity implicitly."""

import io
import os
import re
import stat
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from dotenv import dotenv_values
from training_contracts.privacy import no_link, private_directory

SETTING = "PMS_TRAINING_KEY_FILE"
ASSIGNMENT = re.compile(r"^[ \t]*(?:export[ \t]+)?PMS_TRAINING_KEY_FILE[ \t]*=[^\r\n]*", re.MULTILINE)


class TrainingKeyError(RuntimeError):
    """Safe to display: no PEM, environment contents or underlying exception text."""


def checked_path(path: Path) -> Path:
    path = path.absolute()
    for candidate in reversed((path, *path.parents)):
        if candidate.exists() or candidate.is_symlink():
            no_link(candidate)
    return path


def load_training_key(path: Path) -> Ed25519PrivateKey:
    try:
        path = checked_path(path)
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > 16384:
            raise ValueError()
        if os.name == "posix" and info.st_mode & 0o027:
            raise ValueError()
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError()
        return key
    except Exception:
        raise TrainingKeyError(
            "Training signing key is missing, invalid or not private/readable. Restore the configured "
            "Ed25519 key and its permissions; it will not be replaced automatically."
        ) from None


@contextmanager
def configuration_lock(path: Path):
    lock = checked_path(path.with_name(path.name + ".training.lock"))
    fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        private_directory(lock)
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)  # OS releases the lock; keep its inode for waiting setup processes.


def secure_temporary(parent: Path, group: str | None = None) -> tuple[int, Path]:
    fd, name = tempfile.mkstemp(prefix=".env.training-", dir=parent)
    path = Path(name)
    try:
        private_directory(path)
        if group is not None:
            if sys.platform == "win32":
                raise TrainingKeyError("A Unix key group cannot be configured on Windows.")
            else:
                import grp

                os.chown(path, -1, grp.getgrnam(group).gr_gid)
                path.chmod(0o640)
        return fd, path
    except Exception:
        os.close(fd)
        path.unlink()
        raise


def provision_key(path: Path, group: str | None) -> None:
    checked_path(path)
    if path.exists():
        load_training_key(path)
        return
    parent_existed = path.parent.exists()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if group is None:
        private_directory(path.parent)
    elif not parent_existed and sys.platform != "win32":
        import grp

        os.chown(path.parent, -1, grp.getgrnam(group).gr_gid)
        path.parent.chmod(0o750)
    fd, temporary = secure_temporary(path.parent, group)
    try:
        with os.fdopen(fd, "wb") as output:
            key = Ed25519PrivateKey.generate()
            output.write(
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
            output.flush()
            os.fsync(output.fileno())
        try:
            # Publish the complete file without ever replacing a winner from another setup.
            os.link(temporary, path)
        except FileExistsError:
            pass
    finally:
        temporary.unlink()
    load_training_key(path)


def replace_config(path: Path, content: str) -> None:
    info = path.stat()
    fd, temporary = secure_temporary(path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as output:
            if sys.platform != "win32":
                os.fchown(output.fileno(), info.st_uid, info.st_gid)
                os.fchmod(output.fileno(), stat.S_IMODE(info.st_mode) & 0o640)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def ensure_training_configuration(
    env_file: Path,
    *,
    default_key: Path | None = None,
    runtime_directory: Path | None = None,
    key_group: str | None = None,
) -> Path:
    """Provision absent settings, preserving existing key bytes and unrelated configuration."""
    try:
        env_file = checked_path(env_file)
        with configuration_lock(env_file):
            original = env_file.read_bytes().decode("utf-8")
            if len(ASSIGNMENT.findall(original)) > 1:
                raise TrainingKeyError("Duplicate training key settings need operator review.")
            value = dotenv_values(stream=io.StringIO(original), interpolate=False).get(SETTING)
            base = runtime_directory or env_file.parent
            if value:
                key_path = Path(value)
                if not key_path.is_absolute():
                    key_path = base / key_path
                key_path = checked_path(key_path)
                load_training_key(key_path)
            else:
                key_path = checked_path(
                    default_key or env_file.parent / ".local/training/training-private.pem"
                )
                provision_key(key_path, key_group)
            encoded = key_path.as_posix()
            if any(char in encoded for char in '\r\n"$'):
                raise TrainingKeyError("Use a training key path without quotes, newlines or dollar signs.")
            assignment = f'{SETTING}="{encoded}"'
            if ASSIGNMENT.search(original):
                content = ASSIGNMENT.sub(lambda _: assignment, original)
            else:
                newline = "\r\n" if "\r\n" in original else "\n"
                content = original + ("" if original.endswith("\n") else newline) + assignment + newline
            if content != original:
                replace_config(env_file, content)
            return key_path
    except TrainingKeyError:
        raise
    except Exception:
        raise TrainingKeyError(
            "Could not provision the training signing key. Check private configuration paths and permissions; "
            "existing keys were not replaced."
        ) from None


def prepare_local_training(env_file: Path) -> Path:
    """Environment overrides remain operator-owned; persist automatically generated keys in dotenv."""
    override = os.environ.get(SETTING)
    if override is not None and not override.strip():
        raise TrainingKeyError("Remove the empty PMS_TRAINING_KEY_FILE environment override and retry setup.")
    if override:
        path = Path(override).absolute()
        load_training_key(path)
        return path
    return ensure_training_configuration(env_file)
