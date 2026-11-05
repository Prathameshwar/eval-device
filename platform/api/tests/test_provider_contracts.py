from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import respx
from test_unit import settings

from pms_api.integrations.providers import AzureProvider


@pytest.mark.asyncio
@respx.mock
async def test_azure_fast_transcription_uses_language_and_resource_endpoint():
    adapter = AzureProvider(
        settings(),
        SimpleNamespace(
            settings={"region": "centralindia", "endpoint": "https://fixture.cognitiveservices.azure.com"},
            connection_type="azure_speech",
            auth_mode="api_key",
        ),
        {"api_key": "fixture-secret"},
    )
    route = respx.post(
        "https://fixture.cognitiveservices.azure.com/speechtotext/transcriptions:transcribe",
        params={"api-version": "2024-11-15"},
    ).mock(return_value=httpx.Response(200, json={"combinedPhrases": [{"text": "नमस्ते"}]}))
    outcome = await adapter.submit(
        uuid4(), "audio.transcribe", {"language": "hi-IN"}, {"format": "wav"}, data=b"bounded-wav-fixture"
    )
    assert outcome.result == {"text": "नमस्ते"}
    assert route.calls[0].request.headers["Ocp-Apim-Subscription-Key"] == "fixture-secret"
    assert (
        b"hi-IN" in route.calls[0].request.content
        and b"bounded-wav-fixture" in route.calls[0].request.content
    )


@pytest.mark.asyncio
@respx.mock
async def test_azure_synthesis_entra_auth_and_escaped_ssml():
    adapter = AzureProvider(
        settings(),
        SimpleNamespace(
            settings={
                "region": "centralindia",
                "endpoint": "https://fixture.cognitiveservices.azure.com",
                "resource_id": "/subscriptions/test/resource",
            },
            connection_type="azure_speech",
            auth_mode="workload_identity",
        ),
        {},
    )

    async def bearer(scope):
        return "fixture-entra-token"

    adapter.bearer = bearer
    route = respx.post("https://fixture.cognitiveservices.azure.com/tts/cognitiveservices/v1").mock(
        return_value=httpx.Response(200, content=b"audio")
    )
    await adapter.submit(
        uuid4(), "audio.synthesize", {"language": "hi-IN", "format": "wav"}, {"text": "Hello < & world"}
    )
    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer aad#/subscriptions/test/resource#fixture-entra-token"
    assert b"hi-IN-SwaraNeural" in request.content and b"Hello &lt; &amp; world" in request.content


@pytest.mark.parametrize(
    "operation,path",
    [
        ("audio.transcribe", "/speechtotext/transcriptions/locales?api-version=2024-11-15"),
        ("audio.synthesize", "/tts/cognitiveservices/voices/list"),
    ],
)
@respx.mock
async def test_speech_check_targets_the_configured_service(operation, path):
    adapter = AzureProvider(
        settings(),
        SimpleNamespace(
            settings={"region": "centralindia", "endpoint": "https://fixture.cognitiveservices.azure.com"},
            connection_type="azure_speech",
            auth_mode="api_key",
        ),
        {"api_key": "fixture-secret"},
    )
    route = respx.get("https://fixture.cognitiveservices.azure.com" + path).mock(
        return_value=httpx.Response(200, json={})
    )
    assert await adapter.validate(operation) is True
    assert route.call_count == 1
    assert route.calls[0].request.headers["Ocp-Apim-Subscription-Key"] == "fixture-secret"
