"""Install verified portable releases into a private, persistent download directory."""

import argparse
import hashlib
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path

from human_test_package import (
    APP_NATIVE_MODULES,
    native_module_path,
    validate_client_path,
    validate_runtime,
)


def prepare_metadata(path: Path, root: Path) -> None:
    """Preserve the API's read group before an atomic publication becomes visible."""
    path.chmod(0o640)
    if os.name != "nt":
        os.chown(path, -1, root.stat().st_gid)
    with path.open("r+b") as stream:
        os.fsync(stream.fileno())


def sync_directory(root: Path) -> None:
    """Persist directory entries on the Linux download host after atomic publication."""
    if os.name != "nt":
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def verify_client_archive(source):
    """Validate the packaged scope and hashed contents before exposing the release."""
    prefix = "Desktop-App/"
    with zipfile.ZipFile(source) as bundle:
        members = bundle.infolist()
        names = {info.filename for info in members}
        if (
            len(members) != len(names)
            or len(members) > 100_000
            or sum(info.file_size for info in members) > 2_000_000_000
        ):
            raise ValueError("Invalid or oversized client archive")
        for info in members:
            if (
                not info.filename.startswith(prefix)
                or info.is_dir()
                or ((info.external_attr >> 16) & 0o170000) == 0o120000
            ):
                raise ValueError("Invalid client archive entry")
            validate_client_path(info.filename[len(prefix) :])

        def document(name, limit):
            info = bundle.getinfo(prefix + name)
            if info.file_size > limit:
                raise ValueError("Client metadata exceeds its limit")
            return json.loads(bundle.read(info))

        manifest = document("manifest.json", 16_000_000)
        if not isinstance(manifest, dict) or names != {
            prefix + name for name in manifest
        } | {prefix + "manifest.json"}:
            raise ValueError("Client archive inventory differs from its manifest")
        validate_runtime(document("portable-runtime.json", 4096), protected=True)
        protection = document("protection-manifest.json", 1_000_000)
        native = protection.get("native") if isinstance(protection, dict) else None
        if (
            not isinstance(protection, dict)
            or protection.get("mode") != "cython"
            or not isinstance(native, dict)
            or set(native) != set(APP_NATIVE_MODULES)
        ):
            raise ValueError("Only Human-test code may be natively protected")
        if "Human-test.exe" not in manifest or any(
            not isinstance(path, str)
            or path not in manifest
            or path != native_module_path(name)
            for name, path in native.items()
        ):
            raise ValueError("Incomplete protected client package")
        for name, expected in manifest.items():
            if not isinstance(expected, str) or not re.fullmatch(
                r"[a-f0-9]{64}", expected
            ):
                raise ValueError("Invalid client file checksum")
            with bundle.open(prefix + name) as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                    raise ValueError("Client file SHA-256 verification failed")


def install(source: Path, root: Path) -> dict:
    if source.is_symlink() or getattr(source, "is_junction", lambda: False)():
        raise ValueError("Release source must not be a link")
    if not re.fullmatch(
        r"Human-test-windows-x64-runtime-protected-[A-Za-z0-9-]+\.zip",
        source.name,
    ):
        raise ValueError("Only protected portable release ZIPs may be published")
    expected = (
        source.with_suffix(".zip.sha256").read_text(encoding="utf-8").split()[0].lower()
    )
    if not re.fullmatch(r"[a-f0-9]{64}", expected):
        raise ValueError("Invalid SHA-256 sidecar")
    digest = hashlib.sha256()
    size = 0
    fd, temporary = tempfile.mkstemp(prefix=".release-", suffix=".partial", dir=root)
    try:
        with os.fdopen(fd, "wb") as output, source.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if digest.hexdigest() != expected:
            raise ValueError("Release SHA-256 verification failed")
        if not 0 < size <= 10_000_000_000:
            raise ValueError("Release size is outside the supported range")
        verify_client_archive(Path(temporary))
        target = root / source.name
        if target.is_symlink() or getattr(target, "is_junction", lambda: False)():
            raise ValueError("Release target must not be a link")
        prepare_metadata(Path(temporary), root)
        try:
            # Same-directory hard linking publishes atomically without ever replacing
            # another publisher's immutable release, even if it appeared concurrently.
            os.link(temporary, target)
            sync_directory(root)
        except FileExistsError:
            if target.is_symlink() or getattr(target, "is_junction", lambda: False)():
                raise ValueError("Release target must not be a link")
            existing = hashlib.sha256()
            with target.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    existing.update(chunk)
            if existing.hexdigest() != expected:
                raise ValueError("An immutable release with this name already exists")
        return {
            "id": "desktop-runtime",
            "filename": source.name,
            "size_bytes": size,
            "sha256": expected,
        }
    finally:
        Path(temporary).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--client",
        type=Path,
        required=True,
        help="Protected Human-test desktop/runtime ZIP",
    )
    args = parser.parse_args()
    if args.root.is_symlink() or getattr(args.root, "is_junction", lambda: False)():
        raise ValueError("Download directory must not be a link")
    args.root.mkdir(parents=True, exist_ok=True)
    releases = [install(args.client, args.root)]
    fd, temporary = tempfile.mkstemp(
        prefix=".catalog-", suffix=".partial", dir=args.root
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(releases, output, indent=2)
            output.flush()
            os.fsync(output.fileno())
        prepare_metadata(Path(temporary), args.root)
        os.replace(temporary, args.root / "catalog.json")
        sync_directory(args.root)
    finally:
        Path(temporary).unlink(missing_ok=True)
    print(json.dumps({"published": releases}))


if __name__ == "__main__":
    main()
