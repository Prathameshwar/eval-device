"""Explicit English medical checkpoint conversion; no downloads during serving."""

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path


def no_link(path: Path) -> None:
    if path.is_symlink():
        raise ValueError("model paths must not be links")
    if path.exists():
        info = path.lstat()
        if getattr(info, "st_file_attributes", 0) & 0x400 or (path.is_file() and info.st_nlink != 1):
            raise ValueError("model paths must not be links")


NAME = "whisper-medical-v1"
REPO = "Crystalcareai/Whisper-Medicalv1"
REVISION = "0ed71770b69e504df1e830694d855e2aeeeb3db3"
SOURCE_FILES = (
    "model.safetensors",
    "config.json",
    "generation_config.json",
    "preprocessor_config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.json",
    "merges.txt",
    "added_tokens.json",
    "special_tokens_map.json",
    "normalizer.json",
)
REQUIRED = {"model.bin", "config.json", "tokenizer.json", "preprocessor_config.json", "vocabulary.json"}


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_medical(directory: Path) -> dict:
    for parent in reversed(directory.absolute().parents):
        no_link(parent)
    no_link(directory)
    manifest_path = directory / "medical-manifest.json"
    no_link(manifest_path)
    if manifest_path.stat().st_size > 65536:
        raise ValueError("invalid medical model manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("repo"), manifest.get("revision"), manifest.get("quantization")) != (
        REPO,
        REVISION,
        "int8_float16",
    ):
        raise ValueError("unexpected medical model provenance")
    files = manifest.get("files", {})
    if not isinstance(files, dict) or not REQUIRED <= files.keys() or len(files) > 16:
        raise ValueError("incomplete medical model manifest")
    for name, spec in files.items():
        if name not in REQUIRED:
            raise ValueError("unexpected medical model file")
        path = directory / name
        no_link(path)
        if path.stat().st_size != spec["bytes"] or digest(path) != spec["sha256"]:
            raise ValueError("medical model integrity check failed")
    return manifest


def verify_source(path: Path, info) -> dict[str, str | int]:
    no_link(path)
    size = path.stat().st_size
    limit = 1_700_000_000 if path.name == "model.safetensors" else 8_000_000
    if not 0 < size <= limit or size != info.size:
        raise ValueError("medical source size mismatch")
    actual = digest(path)
    if info.lfs:
        expected = info.lfs.sha256
        if not re.fullmatch(r"[a-f0-9]{64}", expected) or actual != expected:
            raise ValueError("medical source SHA-256 mismatch")
    else:
        # Git's object hash includes the blob header. Small configs are not LFS objects.
        git = hashlib.sha1(b"blob " + str(size).encode("ascii") + b"\0", usedforsecurity=False)
        git.update(path.read_bytes())
        if git.hexdigest() != info.blob_id:
            raise ValueError("medical source Git blob mismatch")
    return {"bytes": size, "sha256": actual}


def download_medical(destination: Path) -> None:
    destination = destination.absolute()
    for parent in reversed(destination.parents):
        no_link(parent)
    if destination.exists() or destination.is_symlink():
        verify_medical(destination)
        print("Verified installed Whisper Medical; no download or conversion needed.")
        return
    try:
        import torch
        import transformers
        import truststore
        from ctranslate2 import __version__ as ct2_version
        from ctranslate2.converters import TransformersConverter
        from filelock import FileLock
        from huggingface_hub import HfApi, hf_hub_download
    except ImportError:
        raise RuntimeError("Run setup-medical.bat to install the isolated conversion dependencies") from None
    truststore.inject_into_ssl()  # Honor Windows enterprise roots; TLS verification stays enabled.
    destination.parent.mkdir(parents=True, exist_ok=True)
    parent = destination.parent.resolve()
    cache = parent / ".whisper-medical-source"
    cache.mkdir(exist_ok=True)
    no_link(cache)
    # The installer is resumable, serialized, and publishes only complete conversions.
    with FileLock(str(cache / "install.lock"), timeout=0):
        if destination.exists():
            verify_medical(destination)
            return
        api = HfApi(endpoint="https://huggingface.co", token=False)
        metadata = api.model_info(REPO, revision=REVISION, files_metadata=True, token=False, timeout=30)
        if metadata.sha != REVISION or metadata.id != REPO:
            raise ValueError("unexpected medical source revision")
        source_info = {file.rfilename: file for file in (metadata.siblings or [])}
        if not set(SOURCE_FILES) <= source_info.keys():
            raise ValueError("medical checkpoint is incomplete")
        # Download exactly the FP16 safetensors checkpoint and tokenizer/config files.
        # No pickle, ONNX duplicates, model code, saved login tokens or remote endpoints.
        source_hashes = {}
        for name in SOURCE_FILES:
            info = source_info[name]
            limit = 1_700_000_000 if name == "model.safetensors" else 8_000_000
            if type(info.size) is not int or not 0 < info.size <= limit:
                raise ValueError("medical source exceeds its size limit")
            path = Path(
                hf_hub_download(
                    REPO,
                    name,
                    revision=REVISION,
                    token=False,
                    endpoint="https://huggingface.co",
                    local_dir=cache / "source",
                    etag_timeout=30,
                )
            )
            source_hashes[name] = verify_source(path, info)
        with tempfile.TemporaryDirectory(prefix=".whisper-medical-", dir=parent) as temp:
            staging = Path(temp).resolve() / "model"
            # Explicitly local, safe-tensor-only conversion. Runtime never imports torch.
            old = {key: os.environ.get(key) for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")}
            try:
                os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
                torch.set_num_threads(4)

                class LocalSafeConverter(TransformersConverter):
                    def load_model(self, model_class, model_name_or_path, **kwargs):
                        return model_class.from_pretrained(
                            model_name_or_path, **kwargs, use_safetensors=True, local_files_only=True
                        )

                    def load_tokenizer(self, tokenizer_class, model_name_or_path, **kwargs):
                        return tokenizer_class.from_pretrained(
                            model_name_or_path, **kwargs, local_files_only=True
                        )

                converter = LocalSafeConverter(
                    str(cache / "source"),
                    load_as_float16=True,
                    trust_remote_code=False,
                    copy_files=["tokenizer.json", "preprocessor_config.json"],
                )
                converter.convert(str(staging), quantization="int8_float16")
            finally:
                for key, value in old.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
            actual_files = {p.name for p in staging.iterdir()}
            if actual_files != REQUIRED:
                raise ValueError("unexpected converted medical model files")
            files = {
                name: {"bytes": (staging / name).stat().st_size, "sha256": digest(staging / name)}
                for name in sorted(actual_files)
            }
            manifest = {
                "repo": REPO,
                "revision": REVISION,
                "quantization": "int8_float16",
                "languages": ["en"],
                "files": files,
                "source_files": source_hashes,
                "converter": {
                    "ctranslate2": ct2_version,
                    "transformers": transformers.__version__,
                    "torch": torch.__version__,
                },
            }
            (staging / "medical-manifest.json").write_text(
                json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
            )
            verify_medical(staging)
            if destination.exists() or destination.parent.resolve() != parent:
                raise ValueError("medical model destination changed during conversion")
            # Move only our newly created directory within the checked model parent.
            staging.rename(destination)
        print("Whisper Medical installed. Select whisper-medical-v1 and language=en.")
