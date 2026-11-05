"""Verified shared assets, restartable downloads and isolated runtime preparation."""

import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from .catalog import Catalog
from .errors import ManagerError, require
from .process import run_owned
from .security import checked, environment, protect
from .storage import Store

SCRIPT_LOCK = threading.RLock()


def load_script(path, name):
    spec = importlib.util.spec_from_file_location(name, checked(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path):
    checked(path)
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_files(directory, files):
    checked(directory)
    require(isinstance(files, dict) and 0 < len(files) <= 256, "manifest", "Invalid asset manifest")
    for name, spec in files.items():
        require(
            isinstance(name, str)
            and not Path(name).is_absolute()
            and "\\" not in name
            and ":" not in name
            and all(part not in {"", ".", ".."} for part in name.split("/")),
            "manifest",
            "Invalid asset filename",
        )
        require(
            isinstance(spec, dict)
            and type(spec.get("bytes")) is int
            and 0 < spec["bytes"] <= 16_000_000_000
            and isinstance(spec.get("sha256"), str)
            and re.fullmatch(r"[a-f0-9]{64}", spec["sha256"]),
            "manifest",
            "Invalid asset metadata",
        )
        path = checked(directory / name, directory)
        require(
            path.is_file() and path.stat().st_size == spec["bytes"], "integrity", "Asset size check failed"
        )
        require(digest(path) == spec["sha256"], "integrity", "Asset checksum check failed")


class Assets:
    def __init__(self, catalog: Catalog):
        self.catalog = catalog
        self.root, self.repo = catalog.local_root, catalog.repo_root
        self.library = checked(self.root / ".library", self.root)
        self.cache = checked(self.root / ".downloads/manager", self.root)

    def verify(self, model_id):
        model = self.catalog.get(model_id)
        new, legacy = self.catalog.locations(model)
        failures = []
        for directory in (new, legacy):
            if not directory.exists():
                continue
            try:
                manifest = directory / "managed-manifest.json"
                if manifest.exists() and model["method"] not in {"llm", "voice"}:
                    data = Store.read(manifest, 1_048_576)
                    require(data["model_id"] == model_id, "manifest", "Model manifest mismatch")
                    verify_files(directory, data["files"])
                    self._required(model, data["files"])
                    return directory
                if model["method"] == "llm":
                    spec = model["spec"]
                    verify_files(directory, {spec["name"]: spec})
                elif model["method"] == "voice":
                    verify_files(directory, model["spec"]["files"])
                elif model["method"] == "qwenmedic":
                    with SCRIPT_LOCK:
                        sys.path.insert(0, str(self.root / "scripts"))
                        try:
                            medical = load_script(
                                self.root / "scripts/medical.py", "manager_medical_verifier"
                            )
                            medical.verify_medical(directory)
                        finally:
                            sys.path.pop(0)
                else:
                    names = (
                        "conversion-manifest.json",
                        "download-manifest.json",
                        "medical-manifest.json",
                        "manifest.json",
                    )
                    source = next((directory / n for n in names if (directory / n).is_file()), None)
                    require(source is not None, "unverified", "Installed model needs a verified manifest")
                    data = Store.read(source, 1_048_576)
                    files = data.get("files")
                    verify_files(directory, files)
                    self._required(model, files)
                return directory
            except (OSError, ValueError, KeyError, TypeError, ManagerError):
                failures.append(directory)
        if failures:
            raise ManagerError(
                "integrity", "Existing model failed verification; its files were preserved", 409
            )
        raise ManagerError("missing_model", "Download and verify this model first", 409)

    @staticmethod
    def _required(model, files):
        required = {
            "hf": {"model.bin", "config.json", "tokenizer.json"},
            "medical": {
                "model.bin",
                "config.json",
                "tokenizer.json",
                "preprocessor_config.json",
                "vocabulary.json",
            },
            "nemotron": {"encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt"},
            "vosk": {"am/final.mdl", "conf/model.conf", "graph/Gr.fst", "graph/HCLr.fst"},
        }.get(model["method"], set())
        require(required <= files.keys(), "manifest", "Model manifest is incomplete")

    def inventory(self):
        result = {}
        for identifier in self.catalog.models:
            try:
                location = self.verify(identifier)
                result[identifier] = {"status": "Installed", "installed": True, "location": str(location)}
            except ManagerError as error:
                result[identifier] = {
                    "status": "Available" if error.code == "missing_model" else "Unverified",
                    "installed": False,
                    "error": error.message,
                }
            except (OSError, ValueError):
                result[identifier] = {
                    "status": "Unverified",
                    "installed": False,
                    "error": "Asset location is inaccessible or linked; inspect local permissions",
                }
        return result

    def fetch(self, spec, destination, progress):
        """Resume bounded ranges; verify the publisher's hash before publishing a file."""
        checked(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            verify_files(destination.parent, {destination.name: spec})
            return destination
        partial = checked(destination.with_name(destination.name + ".part"))
        total = spec["bytes"]
        require(
            type(total) is int and 0 < total <= 16_000_000_000, "asset_size", "Invalid declared download size"
        )
        require(spec["url"].startswith("https://"), "source", "Downloads require HTTPS")
        for attempt in range(3):
            start = partial.stat().st_size if partial.exists() else 0
            require(start <= total, "integrity", "Partial download exceeds expected size")
            try:
                if start < total:
                    headers = {"User-Agent": "manage-local-models", "Accept-Encoding": "identity"}
                    if start:
                        headers["Range"] = f"bytes={start}-"
                    with urllib.request.urlopen(
                        urllib.request.Request(spec["url"], headers=headers), timeout=30
                    ) as response:
                        if start and response.status == 200:
                            start = 0  # Server does not support ranges: safely replace partial bytes.
                        elif start:
                            require(
                                response.status == 206
                                and response.headers.get("Content-Range", "")
                                == f"bytes {start}-{total - 1}/{total}",
                                "range",
                                "Invalid resumed download response",
                            )
                        elif response.status != 200:
                            raise ManagerError("download_response", "Unexpected download response")
                        mode = "ab" if start else "wb"
                        with partial.open(mode) as target:
                            size = start
                            while block := response.read(1024 * 1024):
                                size += len(block)
                                require(size <= total, "integrity", "Download exceeds its declared size")
                                target.write(block)
                                progress(phase="Downloading", bytes_done=size, bytes_total=total)
                    require(size == total, "incomplete", "Download was incomplete")
                progress(phase="Verifying", bytes_done=total, bytes_total=total)
                verify_files(partial.parent, {partial.name: spec})
                checked(destination)
                partial.replace(destination)
                return destination
            except urllib.error.HTTPError as error:
                retry = error.code in {408, 429, 500, 502, 503, 504}
                error.close()
                if not retry or attempt == 2:
                    raise ManagerError(
                        "download_failed", "Publisher download failed; check network access", 502
                    ) from None
            except (OSError, TimeoutError):
                if attempt == 2:
                    raise ManagerError(
                        "download_failed", "Download failed; verified partial bytes can be resumed", 502
                    ) from None
            time.sleep(0.2 * 2**attempt)
        raise ManagerError("download_failed", "Download did not complete", 502)

    def _hf_specs(self, model):
        lock = checked(self.cache / (model["id"] + ".source.json"), self.root)
        if lock.exists():
            return Store.read(lock, 1_048_576)
        url = f"https://huggingface.co/api/models/{model['repo']}?blobs=true"
        with urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": "manage-local-models"}), timeout=30
        ) as response:
            raw = response.read(1_048_577)
        require(len(raw) <= 1_048_576, "metadata", "Publisher metadata exceeded its limit")
        data = json.loads(raw)
        revision = data.get("sha", "")
        require(
            data.get("id") == model["repo"] and re.fullmatch(r"[a-f0-9]{40}", revision),
            "metadata",
            "Unexpected publisher revision",
        )
        wanted = {
            "model.bin",
            "config.json",
            "tokenizer.json",
            "preprocessor_config.json",
            "vocabulary.json",
            "vocabulary.txt",
        }
        files = {}
        for info in data.get("siblings", []):
            name = info.get("rfilename")
            if name not in wanted:
                continue
            size = info.get("size") or info.get("lfs", {}).get("size")
            require(
                type(size) is int and 0 < size <= 4_000_000_000, "metadata", "Unexpected model asset size"
            )
            lfs = info.get("lfs") or {}
            hash_value = lfs.get("sha256") or info.get("blobId")
            require(
                isinstance(hash_value, str) and re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", hash_value),
                "metadata",
                "Publisher did not supply an asset hash",
            )
            files[name] = {
                "name": name,
                "bytes": size,
                "publisher_hash": hash_value,
                "url": f"https://huggingface.co/{model['repo']}/resolve/{revision}/{name}",
            }
        require(
            {"model.bin", "config.json", "tokenizer.json"} <= files.keys(),
            "metadata",
            "Model assets are incomplete",
        )
        data = {"model_id": model["id"], "repo": model["repo"], "revision": revision, "files": files}
        lock.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_json(lock, data)
        return data

    def _atomic_json(self, path, data):
        checked(path, self.root)
        descriptor, name = tempfile.mkstemp(prefix=".metadata-", dir=path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(data, stream, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            checked(path, self.root)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def _hf_download(self, model, staging, progress):
        source = self._hf_specs(model)
        require(
            source["model_id"] == model["id"] and source["repo"] == model["repo"],
            "metadata",
            "Source lock mismatch",
        )
        require(
            isinstance(source.get("revision"), str) and re.fullmatch(r"[a-f0-9]{40}", source["revision"]),
            "metadata",
            "Invalid source revision",
        )
        require(
            isinstance(source.get("files"), dict) and 3 <= len(source["files"]) <= 6,
            "metadata",
            "Invalid source files",
        )
        self._required(model, source["files"])
        result = {}
        for name, info in source["files"].items():
            require(
                Path(name).name == name
                and name
                in {
                    "model.bin",
                    "config.json",
                    "tokenizer.json",
                    "preprocessor_config.json",
                    "vocabulary.json",
                    "vocabulary.txt",
                },
                "metadata",
                "Unsupported source asset",
            )
            expected = info["publisher_hash"]
            require(
                isinstance(expected, str)
                and re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", expected)
                and info["url"]
                == f"https://huggingface.co/{model['repo']}/resolve/{source['revision']}/{name}"
                and type(info["bytes"]) is int
                and 0 < info["bytes"] <= 4_000_000_000,
                "metadata",
                "Invalid cached source metadata",
            )
            target = checked(staging / name, staging)
            if len(expected) == 64:
                self.fetch({**info, "sha256": expected}, target, progress)
            else:
                require(info["bytes"] <= 8_000_000, "metadata", "Unbounded configuration asset")
                with urllib.request.urlopen(info["url"], timeout=30) as response:
                    body = response.read(info["bytes"] + 1)
                actual = hashlib.sha1(
                    b"blob " + str(len(body)).encode() + b"\0" + body, usedforsecurity=False
                ).hexdigest()
                require(
                    len(body) == info["bytes"] and actual == expected,
                    "integrity",
                    "Publisher Git object check failed",
                )
                target.write_bytes(body)
            result[name] = {"bytes": target.stat().st_size, "sha256": digest(target)}
        return result

    def runtime(self, capability, gpu, progress):
        if capability == "llm":
            self._llm_runtime(gpu, progress)
            return Path(sys.executable)
        project = (
            self.repo / "device/audio-process" if capability == "asr" else self.root / "runtime-projects/tts"
        )
        destination = checked(self.root / ".runtime/environments" / capability, self.root)
        python = destination / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        uv = shutil.which("uv")
        require(uv is not None, "uv_missing", "Install uv to prepare audio/voice runtimes", 409)
        env = environment()
        env["UV_PROJECT_ENVIRONMENT"] = str(destination)
        progress(phase="Preparing runtime")
        args = [
            uv,
            "sync",
            "--frozen",
            "--no-dev",
            "--inexact",
            "--no-install-project",
            "--python",
            sys.executable,
            "--project",
            str(project),
        ]
        if capability == "asr":
            args += ["--extra", "vosk"]
        if capability == "asr" and gpu:
            args += ["--extra", "cuda"]
        completed = run_owned(args, timeout=900, env=env)
        require(
            completed == 0 and python.is_file(),
            "runtime_install",
            "Runtime setup failed; check uv, network and disk space",
            409,
        )
        return python

    def runtime_python(self, capability):
        if capability == "llm":
            return Path(sys.executable)
        dedicated = (
            self.root
            / ".runtime/environments"
            / capability
            / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        )
        # Reuse already provisioned engines without modifying their environments.
        legacy = self.repo / (
            "device/audio-process/.venv/Scripts/python.exe"
            if capability == "asr"
            else "local-models/.runtime/environments/tts/Scripts/python.exe"
        )
        python = dedicated if dedicated.is_file() else legacy
        require(python.is_file(), "runtime_missing", "Download the model/runtime before provisioning", 409)
        checked(python)
        return python

    def _llm_runtime(self, gpu, progress):
        # Existing verified llama.cpp extraction logic; preserve a running installation on failure.
        with SCRIPT_LOCK:
            sys.path.insert(0, str(self.root / "scripts"))
            try:
                installer = load_script(self.root / "scripts/install.py", "manager_llm_installer")
            finally:
                sys.path.pop(0)
        with installer.FileLock(self.root / ".install.lock", "Local LLM setup is already running"):
            self._prepare_llm_runtime(installer, gpu, progress)

    def _prepare_llm_runtime(self, installer, gpu, progress):
        for kind, keys in (("cpu", ("cpu",)), *(([("cuda", ("cuda", "cuda_runtime"))]) if gpu else [])):
            destination = checked(self.root / ".runtime" / kind, self.root)
            if (destination / "manifest.json").exists():
                manifest = json.loads(checked(destination / "manifest.json").read_text(encoding="utf-8"))
                require("llama-server.exe" in manifest, "runtime_integrity", "Runtime manifest is incomplete")
                for name, expected in manifest.items():
                    require(Path(name).name == name, "runtime_integrity", "Invalid runtime file")
                    require(
                        digest(destination / name) == expected,
                        "runtime_integrity",
                        "Existing runtime failed verification",
                    )
                continue
            archives = [
                self.fetch(
                    self.catalog.runtime_specs[key],
                    self.cache / self.catalog.runtime_specs[key]["name"],
                    progress,
                )
                for key in keys
            ]
            progress(phase="Installing runtime")
            installer.extract_runtime(archives, destination)

    def download(self, model_id, gpu, progress):
        model = self.catalog.get(model_id)
        require(not gpu or model["gpu_supported"], "device", "Model supports CPU only")
        self.library.mkdir(parents=True, exist_ok=True)
        self.cache.mkdir(parents=True, exist_ok=True)
        protect(self.library)
        protect(self.cache)
        try:
            existing = self.verify(model_id)
        except ManagerError as error:
            managed, _ = self.catalog.locations(model)
            if error.code != "missing_model" and (error.code != "integrity" or managed.exists()):
                raise
            existing = None
        if not existing:
            require(
                shutil.disk_usage(self.root).free >= max(512_000_000, (model["bytes"] or 2_000_000_000) * 2),
                "disk_space",
                "Insufficient space for staged model installation",
                409,
            )
        python = self.runtime(model["capability"], gpu, progress)
        if existing:
            return existing
        destination, _ = self.catalog.locations(model)
        staging = checked(self.library / (".install-" + model_id), self.library)
        staging.mkdir(exist_ok=True)
        if model["method"] == "llm":
            spec = model["spec"]
            self.fetch(spec, staging / spec["name"], progress)
            files = {spec["name"]: {"bytes": spec["bytes"], "sha256": spec["sha256"]}}
        elif model["method"] == "hf":
            files = self._hf_download(model, staging, progress)
        elif model["method"] == "voice":
            voices = load_script(self.root / "scripts/install_voices.py", "manager_voice_installer")
            spec = model["spec"]
            archive = self.fetch({**spec, "name": spec["archive"]}, self.cache / spec["archive"], progress)
            progress(phase="Extracting voice")
            try:
                voices.publish(spec, archive, staging)
            except SystemExit:
                raise ManagerError(
                    "voice_integrity",
                    "Voice archive failed verification; existing assets were preserved",
                    409,
                ) from None
            files = spec["files"]
        else:
            # Existing pinned/conversion installers run in isolated processes. Raw output is discarded.
            progress(phase="Installing model")
            if model["method"] == "qwenmedic":
                command = [sys.executable, str(self.root / "scripts/install.py"), "--model", "qwenmedic-v1"]
                if not gpu:
                    command += ["--cpu"]
            else:
                if model["method"] == "medical":
                    uv = shutil.which("uv")
                    require(uv is not None, "uv_missing", "Install uv to prepare medical conversion", 409)
                    conversion = checked(self.root / ".runtime/environments/medical", self.root)
                    env = environment()
                    env["UV_PROJECT_ENVIRONMENT"] = str(conversion)
                    result = run_owned(
                        [
                            uv,
                            "sync",
                            "--frozen",
                            "--no-dev",
                            "--python",
                            sys.executable,
                            "--project",
                            str(self.root / "runtime-projects/medical"),
                        ],
                        env=env,
                        timeout=900,
                    )
                    require(
                        result == 0,
                        "conversion_runtime",
                        "Medical conversion runtime setup failed",
                        409,
                    )
                    python = conversion / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
                command = [str(python), str(self.root / "service/install_adapter.py"), model_id, str(staging)]
            result = run_owned(
                command,
                env=environment(),
                timeout=3600,
            )
            require(
                result == 0,
                "model_install",
                "Model installation failed; existing assets were preserved",
                502,
            )
            if model["method"] == "qwenmedic":
                return self.verify(model_id)
            source = next(
                (
                    staging / n
                    for n in ("download-manifest.json", "medical-manifest.json")
                    if (staging / n).is_file()
                ),
                None,
            )
            require(source is not None, "manifest", "Installer did not produce verified metadata")
            files = json.loads(checked(source).read_text(encoding="utf-8"))["files"]
            self._required(model, files)
        progress(phase="Verifying")
        verify_files(staging, files)
        self._atomic_json(staging / "managed-manifest.json", {"model_id": model_id, "files": files})
        require(not destination.exists(), "installation_conflict", "Model installation already exists", 409)
        checked(destination, self.library)
        staging.rename(destination)
        return destination
