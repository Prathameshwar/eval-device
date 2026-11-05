"""Allowlisted isolated conversion/streaming installers; no private desktop settings."""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "local-models"))
sys.path.insert(0, str(REPO / "device/audio-process/src"))

from service.assets import verify_files  # noqa: E402
from service.security import checked  # noqa: E402
from service.storage import Store  # noqa: E402


def publish_converted(staging):
    target = checked(staging / "converted", staging)
    for path in target.iterdir():
        checked(path, target).rename(checked(staging / path.name, staging))
    target.rmdir()


def completed_staging(staging):
    for name in ("medical-manifest.json", "download-manifest.json"):
        path = checked(staging / name, staging)
        if path.is_file():
            verify_files(staging, Store.read(path, 1_048_576)["files"])
            return True
    return False


def main():
    model, staging_name = sys.argv[1:]
    if model not in {
        "whisper-medical-v1",
        "nemotron-3.5-asr-streaming-0.6b",
        "vosk-model-small-en-us-0.15",
        "vosk-model-small-hi-0.22",
    }:
        raise ValueError("Unsupported installer")
    staging = checked(Path(staging_name), REPO / "local-models/.library")
    # Installers require an absent destination; publish their output back into our staging.
    target = staging / "converted"
    if target.exists():
        publish_converted(staging)
        return
    if completed_staging(staging):
        return
    if model == "whisper-medical-v1":
        from device_audio.medical_download import download_medical

        download_medical(target)
    elif model == "nemotron-3.5-asr-streaming-0.6b":
        from device_audio.model_download import download_nemotron

        download_nemotron(target)
    elif model in {"vosk-model-small-en-us-0.15", "vosk-model-small-hi-0.22"}:
        from device_audio.vosk_download import download_vosk

        download_vosk(model, target, source="huggingface")
    else:
        raise ValueError("Unsupported installer")
    publish_converted(staging)


if __name__ == "__main__":
    main()
