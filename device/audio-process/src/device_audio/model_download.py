"""Explicit, pinned Nemotron installation. Never called by service startup."""

import hashlib
import json
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path

NEMOTRON_NAME = "nemotron-3.5-asr-streaming-0.6b"
ARCHIVE_ROOT = "sherpa-onnx-nemotron-3.5-asr-streaming-0.6b-560ms-int8-2026-06-11"
MODEL_URL = f"https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/{ARCHIVE_ROOT}.tar.bz2"
ARCHIVE_BYTES = 475271763
ARCHIVE_SHA256 = "c6bf5e0df765f9d5b43bc9e0536d4b4b3e7d40bdf5ecf13e45f134c51c05ae3a"
MODEL_FILES = ("encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt")


def extract_model(archive: Path, destination: Path) -> dict[str, dict[str, str | int]]:
    """Copy only regular, exact allowlisted members; never extract archive paths."""
    manifest: dict[str, dict[str, str | int]] = {}
    total = 0
    with tarfile.open(archive, "r:bz2") as source:
        for member in source:
            name = member.name.removeprefix(ARCHIVE_ROOT + "/")
            if name not in MODEL_FILES or member.name != f"{ARCHIVE_ROOT}/{name}":
                continue
            if not member.isfile() or name in manifest or not 0 < member.size <= 800_000_000:
                raise ValueError("invalid model archive member")
            total += member.size
            if total > 900_000_000:
                raise ValueError("model archive exceeds size limit")
            stream = source.extractfile(member)
            if stream is None:
                raise ValueError("missing model archive data")
            digest = hashlib.sha256()
            written = 0
            with stream, (destination / name).open("xb") as target:
                while data := stream.read(1024 * 1024):
                    written += len(data)
                    if written > member.size:
                        raise ValueError("model member exceeds declared size")
                    target.write(data)
                    digest.update(data)
            if written != member.size:
                raise ValueError("truncated model member")
            manifest[name] = {"bytes": written, "sha256": digest.hexdigest()}
    if set(manifest) != set(MODEL_FILES):
        raise ValueError("model archive is incomplete")
    return manifest


def download_nemotron(destination: Path) -> None:
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("model directory already exists; choose a new output directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # The temporary directory and automatic recursive cleanup stay in this resolved parent.
    parent = destination.parent.resolve()
    with tempfile.TemporaryDirectory(prefix=".nemotron-install-", dir=parent) as temporary:
        staging = Path(temporary).resolve()
        if not staging.is_relative_to(parent):
            raise ValueError("invalid staging directory")
        archive = staging / "model.tar.bz2"
        for attempt in range(3):
            try:
                digest = hashlib.sha256()
                size = 0
                request = urllib.request.Request(MODEL_URL, headers={"User-Agent": "device-audio-api"})
                with urllib.request.urlopen(request, timeout=60) as source, archive.open("wb") as target:
                    while data := source.read(1024 * 1024):
                        size += len(data)
                        if size > ARCHIVE_BYTES:
                            raise ValueError("model download exceeds expected size")
                        digest.update(data)
                        target.write(data)
                if size != ARCHIVE_BYTES or digest.hexdigest() != ARCHIVE_SHA256:
                    raise ValueError("model download checksum mismatch")
                break
            except (OSError, TimeoutError):
                if attempt == 2:
                    raise
                time.sleep(0.5 * (2**attempt))
        model = staging / "model"
        model.mkdir()
        files = extract_model(archive, model)
        (model / "download-manifest.json").write_text(
            json.dumps(
                {"url": MODEL_URL, "sha256": ARCHIVE_SHA256, "chunk_ms": 560, "files": files}, indent=2
            )
            + "\n",
            encoding="utf-8",
        )
        if destination.exists():
            raise FileExistsError("model directory appeared during download")
        model.rename(destination)
