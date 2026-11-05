"""Pinned, restartable speech-voice installation. Python standard library only.

    uv run python scripts/install_voices.py            install every pinned voice
    uv run python scripts/install_voices.py --verify    check installed files only

Voices are pinned by URL, byte size and SHA-256 in `voices.lock.json`, verified before
publication and extracted member by member. Nothing is downloaded at conversation time.
"""

import argparse
import hashlib
import json
import os
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import suppress
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
VOICES = ROOT / ".voices"
TIMEOUT = 60


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class InstallLock:
    """Refuse concurrent installers before any download or extraction.

    The lock is a byte range held by this process, so Windows releases it even if the
    installer is killed. A leftover lock file never blocks a later run.
    """

    def __init__(self, path):
        self.path = path
        self.stream = None

    def __enter__(self):
        import msvcrt

        self.stream = self.path.open("a+b")
        try:
            msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            self.stream.close()
            self.stream = None
            raise SystemExit("Voice setup is already running; wait for it to finish") from None
        return self

    def __exit__(self, *_):
        import msvcrt

        if self.stream is not None:
            with suppress(OSError):
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            self.stream.close()
            self.stream = None


def fetch(spec, cache):
    """Return the verified archive, reusing a complete cached download."""
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / spec["archive"]
    if target.exists():
        if target.stat().st_size == spec["bytes"] and digest(target) == spec["sha256"]:
            print("Verified cached " + target.name, flush=True)
            return target
        # A partial or altered download is never published.
        target.unlink()
    for attempt in range(5):
        handle, temporary_name = tempfile.mkstemp(dir=cache, suffix=".part")
        temporary = Path(temporary_name)
        try:
            request = urllib.request.Request(spec["url"], headers={"User-Agent": "local-models-voice-setup"})
            hashed = hashlib.sha256()
            size = 0
            with (
                os.fdopen(handle, "wb") as stream,
                urllib.request.urlopen(request, timeout=TIMEOUT) as response,
            ):
                if response.status != 200:
                    raise urllib.error.URLError(f"unexpected status {response.status}")
                while block := response.read(1024 * 1024):
                    size += len(block)
                    if size > spec["bytes"]:
                        raise ValueError("Download exceeds the pinned size")
                    hashed.update(block)
                    stream.write(block)
            if size != spec["bytes"] or hashed.hexdigest() != spec["sha256"]:
                raise ValueError("Download failed its pinned size or SHA-256 check")
            temporary.replace(target)
            print(f"Downloaded {target.name} ({size} bytes)", flush=True)
            return target
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            temporary.unlink(missing_ok=True)
            if attempt == 4:
                raise SystemExit(f"Could not download {spec['archive']}: {error}") from None
            print(f"Transient download failure; retrying ({attempt + 1}/5)", flush=True)
            time.sleep(2**attempt)
        except ValueError as error:
            # A corrupt or substituted file is permanent: stop cleanly instead of retrying.
            temporary.unlink(missing_ok=True)
            raise SystemExit(f"{spec['archive']}: {error}") from None
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    raise SystemExit("Download did not complete")


def publish(spec, archive, destination):
    """Extract only the two expected members; never trust a name inside the archive."""
    destination.mkdir(parents=True, exist_ok=True)
    wanted = {spec["model"], spec["config"]}
    prefix = spec.get("archive_prefix", "")
    if prefix and (PurePosixPath(prefix).is_absolute() or ".." in PurePosixPath(prefix).parts):
        raise SystemExit("Unexpected archive prefix")
    with tarfile.open(archive, "r:*") as bundle:
        for name in wanted:
            if Path(name).name != name or PurePosixPath(name).name != name:
                raise SystemExit("Unexpected archive member: " + name)
            member = bundle.getmember(str(PurePosixPath(prefix) / name))
            if not member.isfile():
                raise SystemExit("Unexpected archive member: " + name)
            expected = spec.get("files", {}).get(name)
            if expected and member.size != expected["bytes"]:
                raise SystemExit("Archive member failed its pinned size check: " + name)
            source = bundle.extractfile(member)
            if source is None:
                raise SystemExit("Unreadable archive member: " + name)
            staged_path = None
            try:
                with source, tempfile.NamedTemporaryFile(dir=destination, delete=False) as staged:
                    staged_path = Path(staged.name)
                    while block := source.read(1024 * 1024):
                        staged.write(block)
                if expected and digest(staged_path) != expected["sha256"]:
                    raise SystemExit("Archive member failed its pinned SHA-256 check: " + name)
                staged_path.replace(destination / name)
            finally:
                if staged_path is not None:
                    staged_path.unlink(missing_ok=True)
    return destination / spec["model"], destination / spec["config"]


def installed(spec, language):
    directory = VOICES / language
    model, config = directory / spec["model"], directory / spec["config"]
    if not model.is_file() or not config.is_file():
        return None
    for path in (model, config):
        info = spec.get("files", {}).get(path.name)
        if info and (path.stat().st_size != info["bytes"] or digest(path) != info["sha256"]):
            return None
    return model


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="Report installed voices without downloading")
    arguments = parser.parse_args()
    specs = json.loads((ROOT / "voices.lock.json").read_text(encoding="utf-8"))["voices"]
    if arguments.verify:
        missing = []
        for language, spec in sorted(specs.items()):
            state = "installed" if installed(spec, language) else "MISSING"
            print(f"{spec.get('label', language)}: {spec['model']} {state}")
            if state == "MISSING":
                missing.append(language)
        if missing:
            raise SystemExit("Run scripts/install_voices.py to install or repair missing voices")
        return
    VOICES.mkdir(parents=True, exist_ok=True)
    with InstallLock(VOICES / ".install.lock"):
        for language, spec in sorted(specs.items()):
            if installed(spec, language):
                print(f"{language}: {spec['model']} already installed", flush=True)
                continue
            archive = fetch(spec, VOICES / "cache")
            model, _ = publish(spec, archive, VOICES / language)
            if not installed(spec, language):
                raise SystemExit(f"{language}: voice verification failed after installation")
            print(f"{language}: installed {model.name}", flush=True)
    print("Voice setup complete. Cached archives under .local/voices/cache can be deleted.", flush=True)


if __name__ == "__main__":
    main()
