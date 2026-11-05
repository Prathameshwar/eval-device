"""Pinned, restartable local installation. Python standard library only."""

import argparse
import concurrent.futures
import hashlib
import json
import os
import stat
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from common import DEFAULT_MODEL, MODEL_NAMES, FileLock

ROOT = Path(__file__).resolve().parents[1]
STEP = 8 * 1024 * 1024


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download(spec, directory):
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / spec["name"]
    if target.exists():
        if target.stat().st_size != spec["bytes"] or sha256(target) != spec["sha256"]:
            raise ValueError("Existing download failed integrity check: " + target.name)
        print("Verified cached " + target.name, flush=True)
        return target
    parts = directory / (target.name + ".parts")
    parts.mkdir(exist_ok=True)
    size = spec["bytes"]

    def fetch(start):
        end = min(size - 1, start + STEP - 1)
        part = parts / str(start)
        if part.exists() and part.stat().st_size == end - start + 1:
            return
        for attempt in range(3):
            try:
                # Separate cache keys for byte ranges; final publisher SHA-256 is mandatory.
                separator = "&" if "?" in spec["url"] else "?"
                url = spec["url"] + separator + f"local_llm_range={start}-{end}"
                request = urllib.request.Request(
                    url,
                    headers={
                        "Range": f"bytes={start}-{end}",
                        "User-Agent": "local-llm-setup",
                    },
                )
                with urllib.request.urlopen(request, timeout=45) as response:
                    if (
                        response.status != 206
                        or response.headers.get("Content-Range") != f"bytes {start}-{end}/{size}"
                    ):
                        raise ValueError("Download server returned an unexpected byte range")
                    data = response.read(end - start + 2)
                if len(data) != end - start + 1:
                    raise OSError("Incomplete download chunk")
                temporary = part.with_suffix(".partial")
                temporary.write_bytes(data)
                temporary.replace(part)
                return
            except urllib.error.HTTPError as exc:
                code = exc.code
                exc.close()
                if code not in {408, 429, 500, 502, 503, 504} or attempt == 2:
                    raise RuntimeError(f"Download refused (HTTP {code}); check network access") from None
            except (OSError, TimeoutError):
                if attempt == 2:
                    raise RuntimeError(
                        "Download failed after three attempts; rerun setup to resume"
                    ) from None
            time.sleep(0.5 * 2**attempt)

    offsets = list(range(0, size, STEP))
    print(f"Downloading {target.name}: {size / 1e6:.1f} MB", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fetch, start) for start in offsets]
        for count, future in enumerate(concurrent.futures.as_completed(futures), 1):
            try:
                future.result()
            except BaseException:
                for queued in futures:
                    queued.cancel()
                raise
            if count % 16 == 0 or count == len(offsets):
                print(f"  {count}/{len(offsets)} parts", flush=True)
    temporary = target.with_suffix(target.suffix + ".partial")
    digest = hashlib.sha256()
    with temporary.open("wb") as output:
        for start in offsets:
            data = (parts / str(start)).read_bytes()
            output.write(data)
            digest.update(data)
    if temporary.stat().st_size != size or digest.hexdigest() != spec["sha256"]:
        raise ValueError("Publisher SHA-256 mismatch; unverified asset will not be installed")
    temporary.replace(target)
    print("Publisher SHA-256 verified: " + target.name, flush=True)
    return target


def extract_runtime(archives, destination, program="llama-server.exe"):
    if program not in ("llama-server.exe", "llama-quantize.exe"):
        raise ValueError("Unsupported runtime program")
    if destination.exists():
        manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
        for name, expected in manifest.items():
            if Path(name).name != name or sha256(destination / name) != expected:
                raise ValueError("Installed runtime integrity check failed")
        if program not in manifest:
            raise ValueError("Incomplete runtime")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    parent = destination.parent.resolve()
    with tempfile.TemporaryDirectory(dir=parent, prefix=".install-") as temp:
        staging = Path(temp).resolve()
        if not staging.is_relative_to(parent):
            raise ValueError("Invalid staging directory")
        manifest = {}
        total = 0
        for archive in archives:
            with zipfile.ZipFile(archive) as source:
                if len(source.infolist()) > 256:
                    raise ValueError("Too many archive entries")
                for member in source.infolist():
                    name = Path(member.filename).name
                    if not (name == program or name.endswith(".dll") or name.startswith("LICENSE")):
                        continue
                    mode = member.external_attr >> 16
                    if member.is_dir() or stat.S_IFMT(mode) not in (0, stat.S_IFREG) or name in manifest:
                        raise ValueError("Unsafe or duplicate runtime archive entry")
                    total += member.file_size
                    if not 0 < member.file_size < 1_500_000_000 or total > 2_500_000_000:
                        raise ValueError("Runtime archive size limit exceeded")
                    digest = hashlib.sha256()
                    size = 0
                    with (
                        source.open(member) as incoming,
                        (staging / name).open("xb") as outgoing,
                    ):
                        while data := incoming.read(1024 * 1024):
                            size += len(data)
                            if size > member.file_size:
                                raise ValueError("Invalid runtime member size")
                            outgoing.write(data)
                            digest.update(data)
                    if size != member.file_size:
                        raise ValueError("Truncated runtime member")
                    manifest[name] = digest.hexdigest()
        if program not in manifest:
            raise ValueError("Runtime server missing")
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        # Rename only this freshly created staging directory into its checked workspace parent.
        if destination.exists() or destination.parent.resolve() != parent:
            raise ValueError("Installation destination changed")
        if os.name == "nt":
            # These are public runtime binaries, not credentials: restore parent inheritance.
            subprocess.run(
                ["icacls", str(staging), "/reset", "/T", "/Q"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        staging.rename(destination)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cpu", action="store_true", help="Install CPU runtime only; no CUDA libraries")
    parser.add_argument("--model", choices=MODEL_NAMES, default=DEFAULT_MODEL)
    args = parser.parse_args()
    if os.name != "nt":
        raise SystemExit("This installer targets Windows x64")
    with FileLock(ROOT / ".install.lock", "Local LLM setup is already running"):
        specs = json.loads((ROOT / "assets.lock.json").read_text(encoding="utf-8"))
        cpu = download(specs["cpu"], ROOT / ".downloads")
        extract_runtime([cpu], ROOT / ".runtime/cpu")
        if not args.cpu:
            gpu = download(specs["cuda"], ROOT / ".downloads")
            libraries = download(specs["cuda_runtime"], ROOT / ".downloads")
            extract_runtime([gpu, libraries], ROOT / ".runtime/cuda")
        if args.model == "qwenmedic-v1":
            from medical import install_medical

            install_medical(ROOT, specs, cpu)
            print("Setup complete. Run start-qwenmedic.bat (add --cpu for CPU).", flush=True)
            return
        spec = specs["model"] if args.model == "qwen3-4b" else specs["models"][args.model]
        download(spec, ROOT / ".models")
        manifest = "model-manifest.json" if args.model == "qwen3-4b" else f"{args.model}-manifest.json"
        (ROOT / ".models" / manifest).write_text(json.dumps(spec, indent=2), encoding="utf-8")
        mode = " --cpu" if args.cpu else ""
        launcher = "start-llm.bat" if args.model == "qwen3-4b" else f"start-{args.model}.bat"
        print(f"Setup complete. Run {launcher}{mode} to chat.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        from install_errors import HINTS, details, report

        report(exc)
        print("Setup failed: " + HINTS[details(exc)["code"]], flush=True)
        raise SystemExit(1) from None
