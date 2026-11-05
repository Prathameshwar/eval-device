"""Explicit QwenMedic installation; serving never downloads or quantizes models."""

import json
import os
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from common import no_link
from install import download, extract_runtime, sha256

REPO = "ross-dev/QwenMedic-v1-gguf"
SOURCE = "QwenMedic-v1-F16.gguf"
OUTPUT = "QwenMedic-v1-Q4_K_M.gguf"


def source_spec(metadata):
    if not isinstance(metadata, dict):
        raise ValueError("Invalid QwenMedic metadata")
    revision = metadata.get("sha", "")
    if metadata.get("id") != REPO or not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise ValueError("Invalid QwenMedic publisher revision")
    files = [f for f in metadata.get("siblings", []) if f.get("rfilename") == SOURCE]
    if len(files) != 1:
        raise ValueError("Expected QwenMedic F16 asset is missing")
    lfs = files[0].get("lfs", {})
    size, digest = lfs.get("size"), lfs.get("sha256", "")
    if type(size) is not int or not 1_000_000_000 <= size <= 4_000_000_000:
        raise ValueError("Unexpected QwenMedic source size")
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("Missing publisher SHA-256")
    return {
        "name": SOURCE,
        "bytes": size,
        "sha256": digest,
        "url": f"https://huggingface.co/{REPO}/resolve/{revision}/{SOURCE}",
        "repo": REPO,
        "revision": revision,
    }


def resolve_source():
    # Resolve once on first explicit setup; persist the exact commit and publisher hash.
    # Never use local HF credentials, arbitrary endpoints, model Python code or floating
    # revisions for the binary download. Permanent denials are not retried.
    request = urllib.request.Request(
        f"https://huggingface.co/api/models/{REPO}?blobs=true",
        headers={"User-Agent": "local-llm-setup"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read(1_048_577)
            if len(body) > 1_048_576:
                raise ValueError("Publisher metadata exceeded its limit")
            return source_spec(json.loads(body))
        except urllib.error.HTTPError as error:
            code = error.code
            error.close()
            if code not in {408, 429, 500, 502, 503, 504} or attempt == 2:
                raise RuntimeError(
                    f"QwenMedic download refused (HTTP {code}); check network access"
                ) from None
        except (OSError, TimeoutError):
            if attempt == 2:
                raise RuntimeError(
                    "QwenMedic publisher is unreachable; rerun setup when access is available"
                ) from None
        time.sleep(0.5 * 2**attempt)


def validate_source(spec):
    if not isinstance(spec, dict):
        raise ValueError("Invalid QwenMedic source lock")
    expected = source_spec(
        {
            "id": spec.get("repo"),
            "sha": spec.get("revision"),
            "siblings": [
                {
                    "rfilename": spec.get("name"),
                    "lfs": {
                        "size": spec.get("bytes"),
                        "sha256": spec.get("sha256"),
                    },
                }
            ],
        }
    )
    if spec != expected:
        raise ValueError("Invalid QwenMedic source lock")


def verify_medical(directory):
    for parent in reversed(directory.absolute().parents):
        no_link(parent)
    for path in (directory, directory / "manifest.json", directory / OUTPUT):
        no_link(path)
    if (directory / "manifest.json").stat().st_size > 65536:
        raise ValueError("QwenMedic manifest exceeds size limit")
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    validate_source(manifest["source"])
    if manifest.get("quantization") != "Q4_K_M" or manifest.get("name") != OUTPUT:
        raise ValueError("Invalid QwenMedic manifest")
    target = directory / OUTPUT
    if target.stat().st_size != manifest["bytes"] or sha256(target) != manifest["sha256"]:
        raise ValueError("QwenMedic integrity failure; choose a clean installation directory")
    with target.open("rb") as stream:
        if stream.read(4) != b"GGUF":
            raise ValueError("Invalid QwenMedic GGUF")
    return manifest


def install_medical(root, specs, cpu_archive):
    destination = root / ".models/qwenmedic-v1"
    if destination.exists() or destination.is_symlink():
        verify_medical(destination)
        print("Verified cached QwenMedic Q4_K_M.", flush=True)
        return
    cache = root / ".downloads/qwenmedic-v1"
    for parent in reversed(cache.absolute().parents):
        if parent.exists():
            no_link(parent)
    cache.mkdir(parents=True, exist_ok=True)
    no_link(cache)
    lock = cache / "source.lock.json"
    if lock.exists():
        no_link(lock)
        if lock.stat().st_size > 65536:
            raise ValueError("QwenMedic source lock exceeds size limit")
        spec = json.loads(lock.read_text(encoding="utf-8"))
        validate_source(spec)
    else:
        spec = resolve_source()
        with tempfile.TemporaryDirectory(prefix=".source-", dir=cache.resolve()) as temp:
            temporary = Path(temp) / "source.lock.json"
            temporary.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
            temporary.replace(lock)
    source = download(spec, cache)
    # Quantizer and DLLs come from the already pinned, checksum-verified CPU archive.
    if sha256(cpu_archive) != specs["cpu"]["sha256"]:
        raise ValueError("Quantizer archive integrity failure")
    runtime = root / ".runtime/quantize"
    extract_runtime([cpu_archive], runtime, program="llama-quantize.exe")
    destination.parent.mkdir(parents=True, exist_ok=True)
    parent = destination.parent.resolve()
    with tempfile.TemporaryDirectory(prefix=".qwenmedic-", dir=parent) as temp:
        staging = Path(temp).resolve()
        output = staging / OUTPUT
        print("Quantizing QwenMedic to Q4_K_M on CPU; this runs only during setup.", flush=True)
        result = subprocess.run(
            [str(runtime / "llama-quantize.exe"), str(source), str(output), "Q4_K_M", "4"],
            cwd=runtime,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=1800,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if (
            result.returncode
            or not output.is_file()
            or not 300_000_000 < output.stat().st_size < 2_000_000_000
        ):
            raise RuntimeError("QwenMedic quantization failed; no model was installed")
        manifest = {
            "source": spec,
            "name": OUTPUT,
            "quantization": "Q4_K_M",
            "quantizer_archive_sha256": specs["cpu"]["sha256"],
            "bytes": output.stat().st_size,
            "sha256": sha256(output),
        }
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        verify_medical(staging)
        if destination.exists() or destination.parent.resolve() != parent:
            raise ValueError("QwenMedic destination changed during setup")
        if os.name == "nt":
            subprocess.run(
                ["icacls", str(staging), "/reset", "/T", "/Q"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        staging.rename(destination)
