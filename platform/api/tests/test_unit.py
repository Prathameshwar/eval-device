import base64
import io
import wave
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from pms_api.core.common import AppError
from pms_api.core.config import Settings
from pms_api.integrations.providers import AWSProvider
from pms_api.integrations.vault import CredentialVault
from pms_api.modules.schemas import Heartbeat
from pms_api.security.access import GRANTS


def settings(**values):
    return Settings(
        token_pepper="p" * 40,
        media_signing_key="m" * 40,
        active_credential_key="v1",
        credential_keys={"v1": base64.b64encode(b"k" * 32).decode()},
        **values,
    )


def test_encryption_authentication_and_binding():
    vault = CredentialVault(settings())
    org, connection = uuid4(), uuid4()
    ciphertext, kid = vault.encrypt(org, connection, {"api_key": "not-plaintext"})
    row = SimpleNamespace(
        id=connection, organization_id=org, encrypted_credentials=ciphertext, credential_key_id=kid
    )
    assert vault.decrypt(row) == {"api_key": "not-plaintext"}
    row.id = uuid4()
    with pytest.raises(AppError):
        vault.decrypt(row)
    row.id = connection
    row.encrypted_credentials = ciphertext[:-1] + bytes([ciphertext[-1] ^ 1])
    with pytest.raises(AppError):
        vault.decrypt(row)


def test_contracts_reject_naive_time_nonfinite_and_invented_role():
    with pytest.raises(ValidationError):
        Heartbeat(boot_id=uuid4(), sequence_number=0, observed_at="2026-01-01T00:00:00")
    with pytest.raises(ValidationError):
        Heartbeat(boot_id=uuid4(), sequence_number=0, metrics={"temperature_c": float("nan")})
    assert "org.media.read" in GRANTS["org_trainee"]
    assert "org.clinical.author" in GRANTS["org_admin"]
    assert "org.clinical.author" not in GRANTS["org_user"]
    assert "org.clinical.author" not in GRANTS["platform_admin"]
    assert "org.processing.execute" not in GRANTS["org_trainee"]
    assert "org.results.read" not in GRANTS["platform_admin"]
    assert len(GRANTS) == 6


@pytest.mark.asyncio
async def test_polly_hindi_voice_and_real_wav_container():
    calls = []

    def synthesize(**kwargs):
        calls.append(kwargs)
        return {"AudioStream": io.BytesIO(b"\0" * 320)}

    adapter = AWSProvider(
        settings(), SimpleNamespace(settings={"region": "ap-south-1"}, auth_mode="workload_identity"), {}
    )
    adapter.client = lambda service: SimpleNamespace(synthesize_speech=synthesize)
    result = await adapter.submit(
        uuid4(), "audio.synthesize", {"language": "hi-IN", "format": "wav"}, {"text": "नमस्ते"}
    )
    assert (
        calls[0]["VoiceId"] == "Aditi"
        and calls[0]["LanguageCode"] == "hi-IN"
        and calls[0]["OutputFormat"] == "pcm"
    )
    with wave.open(io.BytesIO(result.audio), "rb") as wav:
        assert wav.getframerate() == 16000 and wav.getnchannels() == 1


@pytest.mark.asyncio
async def test_uncertain_rekognition_does_not_issue_a_start_call():
    adapter = AWSProvider(
        settings(), SimpleNamespace(settings={"region": "ap-south-1"}, auth_mode="workload_identity"), {}
    )

    def forbidden(service):
        raise AssertionError("Reconciliation must not submit a new job")

    adapter.client = forbidden
    assert (await adapter.reconcile(uuid4(), "video.labels", {}, {})).status == "unknown"


def test_rate_limiter_bounds_and_fair_keys():
    from pms_api.core.rate_limit import RateLimiter

    limiter = RateLimiter(max_keys=2)
    assert limiter.allow("one", 1) and not limiter.allow("one", 1)
    assert limiter.allow("two", 1) and limiter.allow("three", 1)
    assert len(limiter.entries) == 2


@pytest.mark.asyncio
async def test_aws_synthesis_timeout_does_not_retry_transport(monkeypatch):
    from botocore.exceptions import ReadTimeoutError

    monkeypatch.setenv("AWS_MAX_ATTEMPTS", "7")
    adapter = AWSProvider(
        settings(),
        SimpleNamespace(settings={"region": "ap-south-1"}, auth_mode="access_key"),
        {"access_key_id": "test-access-key", "secret_access_key": "test-secret-key"},
    )
    client = adapter.client("polly")
    attempts = []

    def timeout(request):
        attempts.append(request)
        raise ReadTimeoutError(endpoint_url=request.url)

    monkeypatch.setattr(client._endpoint.http_session, "send", timeout)
    monkeypatch.setattr("botocore.endpoint.time.sleep", lambda seconds: None)
    monkeypatch.setattr(adapter, "client", lambda service: client)
    try:
        with pytest.raises(ReadTimeoutError):
            await adapter.submit(uuid4(), "audio.synthesize", {"language": "en-IN"}, {"text": "Hello"})
        assert len(attempts) == 1
    finally:
        client.close()


def test_synthesis_preflight_matches_engine_limits():
    from pms_api.integrations.contracts import synthesis_parameters

    for section, request, expected in (
        ({"format": "flac"}, {"text": "Hello"}, "unsupported_format"),
        ({"language": "fr-FR"}, {"text": "Bonjour"}, "voice_required"),
        ({}, {"text": "x" * 3001}, "text_too_long"),
    ):
        with pytest.raises(AppError) as caught:
            synthesis_parameters("aws_polly", section, request)
        assert caught.value.code == expected
    assert synthesis_parameters("aws_polly", {"language": "hi-IN"}, {"text": "Hello"})["voice"] == "Aditi"
