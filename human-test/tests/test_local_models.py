import os
import subprocess
import sys
from pathlib import Path

import pytest
from test_flow import settings
from training_client.controller import Controller
from training_client.pms_client import ClientError


def test_model_dialog_in_separate_tk_interpreter():
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("model_dialog_smoke.py"))],
        env={key: value for key, value in os.environ.items() if not key.startswith("HUMAN_")},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "model,language",
    [("vosk-model-small-en-us-0.15", "en"), ("whisper-medical-v1", "en")],
)
def test_language_specific_models_expose_only_supported_choices(model, language):
    value = settings(audio_model=model, language=language)
    assert value.language_choices == (language,)


async def test_vosk_hindi_switch_requires_resaving_supported_patient_language():
    from test_cloud_models import route

    controller = Controller(settings(language="en"), lambda *a: None)
    try:
        chosen = route("local", "local")
        chosen["audio"]["model"] = "vosk-model-small-hi-0.22"
        controller.use_models(chosen)
        with pytest.raises(ClientError, match="installed supported language"):
            await controller.preflight()
    finally:
        await controller.close()


def test_uninstalled_hindi_pack_cannot_be_enabled_by_a_speech_model():
    with pytest.raises(ValueError, match="unavailable"):
        settings(audio_model="vosk-model-small-hi-0.22", language="hi")
