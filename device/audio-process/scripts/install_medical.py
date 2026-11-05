"""Run conversion in its optional venv, without importing the audio web service."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from device_audio.medical_download import download_medical

if __name__ == "__main__":
    try:
        download_medical(Path(__file__).resolve().parents[1] / ".models/whisper-medical-v1")
    except Exception as error:
        status = getattr(getattr(error, "response", None), "status_code", None)
        if status:
            print(f"Publisher request refused (HTTP {status}).")
        # HF exceptions may contain signed asset URLs; never echo those.
        print(
            "Whisper Medical setup failed ("
            + type(error).__name__
            + "). Check network access/dependencies; rerun to resume."
        )
        raise SystemExit(1) from None
