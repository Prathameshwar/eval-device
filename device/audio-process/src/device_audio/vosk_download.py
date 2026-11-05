"""Explicit Vosk downloads with publisher size/MD5 checks and bounded ZIP extraction."""

import hashlib
import json
import stat
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from .config import VOSK_LANGUAGES
from .vosk_engine import REQUIRED_FILES

# https://alphacephei.com/vosk/models/model-list.json (2026-09-19).
# MD5 is the publisher's available checksum, not a signature. SHA-256 is recorded locally.
MODELS = {
    "vosk-model-small-en-us-0.15": (41205931, "09ab50ccd62b674cbaa231b825f9c1cb"),
    "vosk-model-small-hi-0.22": (44458845, "80f1265262c9a8a515f2707498e1b485"),
}
OPTIONAL_FILES = ("README", "README.md", "LICENSE")


def extract_vosk(archive: Path, name: str, destination: Path) -> dict[str, dict[str, str | int]]:
    """Only copy exact regular allowlisted paths into a new staging directory."""
    manifest: dict[str, dict[str, str | int]] = {}
    total = 0
    with zipfile.ZipFile(archive) as source:
        if len(source.infolist()) > 128:
            raise ValueError("too many model archive members")
        for member in source.infolist():
            relative = member.filename.removeprefix(name + "/")
            if relative not in (*REQUIRED_FILES, *OPTIONAL_FILES) or member.filename != name + "/" + relative:
                continue
            mode = member.external_attr >> 16
            if (
                member.is_dir()
                or stat.S_IFMT(mode) not in (0, stat.S_IFREG)
                or relative in manifest
                or not 0 < member.file_size <= 100_000_000
            ):
                raise ValueError("invalid model archive member")
            total += member.file_size
            if total > 200_000_000:
                raise ValueError("model archive exceeds size limit")
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            written = 0
            with source.open(member) as incoming, target.open("xb") as outgoing:
                while data := incoming.read(1024 * 1024):
                    written += len(data)
                    if written > member.file_size:
                        raise ValueError("model member exceeds declared size")
                    digest.update(data)
                    outgoing.write(data)
            if written != member.file_size:
                raise ValueError("truncated model member")
            manifest[relative] = {"bytes": written, "sha256": digest.hexdigest()}
    if not set(REQUIRED_FILES).issubset(manifest):
        raise ValueError("model archive is incomplete")
    return manifest


def download_vosk(name: str, destination: Path, source: str = "official") -> None:
    if source not in {"official", "huggingface"}:
        raise ValueError("unsupported Vosk download source")
    expected_bytes, expected_md5 = MODELS[name]
    url = "https://alphacephei.com/vosk/models/" + name + ".zip"
    if source == "huggingface":
        revision = "e7ac2109d134b5f2404ba95389b2fb51916d4cab"
        url = (
            f"https://huggingface.co/rhasspy/vosk-models/resolve/{revision}/{VOSK_LANGUAGES[name]}/{name}.zip"
        )
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("model directory already exists; choose a new output directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    parent = destination.parent.resolve()
    with tempfile.TemporaryDirectory(prefix=".vosk-install-", dir=parent) as temporary:
        staging = Path(temporary).resolve()
        if not staging.is_relative_to(parent):
            raise ValueError("invalid staging directory")
        archive = staging / "model.zip"
        for attempt in range(3):
            try:
                md5 = hashlib.md5(usedforsecurity=False)
                sha256 = hashlib.sha256()
                size = 0
                request = urllib.request.Request(url, headers={"User-Agent": "device-audio-api"})
                with urllib.request.urlopen(request, timeout=30) as incoming, archive.open("wb") as outgoing:
                    while data := incoming.read(1024 * 1024):
                        size += len(data)
                        if size > expected_bytes:
                            raise ValueError("model download exceeds expected size")
                        md5.update(data)
                        sha256.update(data)
                        outgoing.write(data)
                if size != expected_bytes or md5.hexdigest() != expected_md5:
                    raise ValueError("model download checksum mismatch")
                break
            except urllib.error.HTTPError as exc:
                if attempt == 2 or exc.code not in {408, 429, 500, 502, 503, 504}:
                    raise
                time.sleep(0.5 * (2**attempt))
            except (OSError, TimeoutError):
                if attempt == 2:
                    raise
                time.sleep(0.5 * (2**attempt))
        model = staging / "model"
        model.mkdir()
        files = extract_vosk(archive, name, model)
        (model / "download-manifest.json").write_text(
            json.dumps(
                {
                    "url": url,
                    "publisher_md5": expected_md5,
                    "sha256": sha256.hexdigest(),
                    "bytes": size,
                    "files": files,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        if destination.exists() or destination.is_symlink():
            raise FileExistsError("model directory appeared during download")
        model.rename(destination)
