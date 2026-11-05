"""Optional and job-only speech must not break desktop text conversations."""

from unittest.mock import AsyncMock

import pytest
from test_cloud_models import route, settings
from training_client.controller import Controller
from training_client.pms_client import ClientError


@pytest.mark.parametrize("provider,enabled", [("azure_openai", False), ("aws", True), ("azure", True)])
async def test_noninteractive_speech_does_not_require_azure_or_cloud_speech(provider, enabled, monkeypatch):
    controller = Controller(settings(), lambda *event: None)
    selected = route("cloud", "local")
    selected.update(cloud_allowed=False, azure_enabled=False, speech_enabled=False)
    selected["audio"].update(provider=provider, enabled=enabled)
    selected["llm"].update(provider="local_llama_cpp", requires_external=False)
    try:
        controller.use_models(selected)
        assert not controller.speech_available()
        assert not controller.settings.speech_input_enabled
        ready = AsyncMock()
        monkeypatch.setattr(controller.pms, "preflight", ready)
        with pytest.raises(ClientError, match="Use typing"):
            await controller.preflight()
        ready.assert_not_awaited()
        monkeypatch.setattr(controller, "respond", AsyncMock(return_value={"answer": "mocked reply"}))
        assert (await controller.text_turn("How do you feel?"))["answer"] == "mocked reply"
    finally:
        await controller.close()


async def test_disabled_local_asr_does_not_restrict_text_language():
    controller = Controller(settings(), lambda *event: None)
    selected = route("local", "cloud")
    selected["audio"].update(enabled=False, model="vosk-model-small-hi-0.22")
    try:
        controller.use_models(selected)
        assert "en" in controller.settings.language_choices
    finally:
        await controller.close()
