"""Build a Windows transfer archive for the platform API and web UI."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "platform" / "api"
UI = ROOT / "platform" / "ui"
SHARED = ROOT / "shared" / "training-contracts"
WEB_BUILD = UI / "apps" / "web" / ".next"
OUTPUT = ROOT / "start" / "dist"

EXACT_FILES = {
    "platform/api/.env.example",
    "platform/api/README.md",
    "platform/api/alembic.ini",
    "platform/api/pyproject.toml",
    "platform/api/uv.lock",
    "platform/ui/README.md",
    "platform/ui/package.json",
    "platform/ui/package-lock.json",
    "platform/ui/apps/web/.env.example",
    "platform/ui/apps/web/README.md",
    "platform/ui/apps/web/next.config.mjs",
    "platform/ui/apps/web/package.json",
    "platform/ui/apps/web/tsconfig.json",
    "platform/ui/packages/ui/package.json",
    "shared/training-contracts/pyproject.toml",
    "platform/db/README.md",
    "platform/db/init.bat",
    "platform/db/sync.bat",
    "platform/db/sync.py",
    "platform/db/default-roles.json",
}
PREFIXES = (
    "platform/api/src/",
    "platform/api/migrations/",
    "platform/api/deploy/",
    "platform/ui/apps/web/src/",
    "platform/ui/apps/web/public/",
    "platform/ui/packages/ui/src/",
    "shared/training-contracts/src/",
    "platform/db/sql/",
)
SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".keystore"}
SENSITIVE_NAMES = {"credentials.json", "secrets.json", "id_rsa", "id_ed25519"}


def included_source(path: str) -> bool:
    parts = Path(path).parts
    if any(part.startswith(".env") and part != ".env.example" for part in parts):
        return False
    if any(part.lower() in SENSITIVE_NAMES for part in parts):
        return False
    if Path(path).suffix.lower() in SENSITIVE_SUFFIXES:
        return False
    return (
        path in EXACT_FILES
        or path.startswith(PREFIXES)
        or (path.startswith("platform/db/") and path.endswith(".sql"))
    )


def git_paths(*args: str) -> list[str]:
    result = subprocess.run(
        [
            "git",
            *args,
            "-z",
            "--",
            "platform/api",
            "platform/ui",
            "platform/db",
            "shared/training-contracts",
        ],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    return [os.fsdecode(item).replace("\\", "/") for item in result.stdout.split(b"\0") if item]


def source_files() -> list[tuple[Path, str]]:
    untracked = [
        path for path in git_paths("ls-files", "--others", "--exclude-standard") if included_source(path)
    ]
    if untracked:
        raise RuntimeError(
            "Add or remove untracked deployment source before building: " + ", ".join(untracked[:5])
        )
    result = []
    for path in git_paths("ls-files", "--cached"):
        if not included_source(path):
            continue
        absolute = ROOT / path
        if not absolute.is_file() or absolute.is_symlink():
            raise RuntimeError(f"Missing or unsupported deployment source: {path}")
        result.append((absolute, path))
    missing = EXACT_FILES - {name for _, name in result}
    if missing:
        raise RuntimeError("Required deployment source is missing: " + ", ".join(sorted(missing)))
    return result


def web_files() -> list[tuple[Path, str]]:
    if not (WEB_BUILD / "BUILD_ID").is_file() or not (WEB_BUILD / "server").is_dir():
        raise RuntimeError("The Next.js production build is incomplete.")
    result = []
    for path in WEB_BUILD.rglob("*"):
        if path.is_symlink():
            raise RuntimeError(f"Unexpected symlink in web build: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(WEB_BUILD)
        if relative.parts[0] in {"cache", "diagnostics", "types", "standalone"}:
            continue
        if relative.name == "trace" or not included_build_file(relative):
            continue
        result.append((path, f"platform/ui/apps/web/.next/{relative.as_posix()}"))
    return result


def included_build_file(path: Path) -> bool:
    return not any(part.startswith(".env") or part.lower() in SENSITIVE_NAMES for part in path.parts) and (
        path.suffix.lower() not in SENSITIVE_SUFFIXES
    )


def run(command: list[str], cwd: Path) -> None:
    print(
        f"[BUILD] {command[0]} {' '.join(command[1:])} in {cwd.relative_to(ROOT)}",
        flush=True,
    )
    environment = {
        name: value for name, value in os.environ.items() if not name.startswith(("PMS_", "NEXT_PUBLIC_"))
    }
    environment["NEXT_TELEMETRY_DISABLED"] = "1"
    subprocess.run(command, cwd=cwd, check=True, env=environment)


def write_archive(files: list[tuple[Path, str]], destination: Path) -> None:
    seen: set[str] = set()
    entries: dict[str, str] = {}
    temporary = destination.with_suffix(".zip.tmp")
    try:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
            for source, name in sorted(files, key=lambda item: item[1]):
                if name in seen or source.is_symlink() or not source.is_file():
                    raise RuntimeError(f"Duplicate or missing archive entry: {name}")
                seen.add(name)
                data = source.read_bytes()
                entries[name] = hashlib.sha256(data).hexdigest()
                archive.writestr(name, data)
            manifest = {
                "format": 1,
                "built_at_utc": datetime.now(timezone.utc).isoformat(),
                "web_build_id": (WEB_BUILD / "BUILD_ID").read_text(encoding="utf-8").strip(),
                "sha256": entries,
            }
            archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    if os.name != "nt" or sys.version_info < (3, 12) or sys.version_info >= (3, 14):
        raise RuntimeError("Run this batch file on Windows with Python 3.12 or 3.13.")
    for command in ("npm.cmd", "uv", "git"):
        if shutil.which(command) is None:
            raise RuntimeError(f"{command} is required on PATH.")
    local_web_env = [path.name for path in (UI / "apps" / "web").glob(".env*") if path.name != ".env.example"]
    if local_web_env:
        raise RuntimeError("Remove local web environment files before building: " + ", ".join(local_web_env))
    sources = source_files()
    run(["npm.cmd", "ci", "--no-audit", "--no-fund"], UI)
    run(["npm.cmd", "run", "build"], UI)
    with tempfile.TemporaryDirectory(prefix="pms-platform-wheels-") as directory:
        wheels = Path(directory)
        run(["uv", "build", "--wheel", "--out-dir", str(wheels)], SHARED)
        run(["uv", "build", "--wheel", "--out-dir", str(wheels)], API)
        wheel_files = sorted(wheels.glob("*.whl"))
        if len(wheel_files) != 2 or any("-py3-none-any.whl" not in path.name for path in wheel_files):
            raise RuntimeError("Expected two platform-independent Python wheels.")
        files = sources + web_files() + [(path, f"wheels/{path.name}") for path in wheel_files]
        OUTPUT.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        destination = OUTPUT / f"pms-platform-{stamp}-{secrets.token_hex(3)}.zip"
        write_archive(files, destination)
    print(f"[OK] Created {destination} ({destination.stat().st_size / 1024 / 1024:.1f} MiB)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"[ERROR] Platform build failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
