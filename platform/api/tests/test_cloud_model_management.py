"""Cloud model creation, access checks and management without live provider calls."""

from copy import deepcopy

import pytest
from test_unit import settings

from pms_api.core.common import AppError
from pms_api.integrations.llm.client import LLMClient
from pms_api.integrations.providers import AWSProvider, AzureProvider
from pms_api.integrations.whisper_cloud import AzureWhisperProvider
from pms_api.modules.direct_models import ModelDraft, validate_model

AZURE = "https://fixture.openai.azure.com/openai/v1"
URLS = ["https://api.openai.com/v1", AZURE, "https://api.anthropic.com/v1", "https://fixture.example/v1"]


def drafts():
    rows = []
    for provider, url in zip(("openai", "azure_openai", "anthropic", "openai_compatible"), URLS, strict=True):
        rows.append(
            dict(
                name=provider,
                kind="llm",
                location="cloud",
                provider=provider,
                engine="llm",
                model_key="fixture-model",
                settings={"base_url": url},
                credentials={"api_key": "fixture-secret"},
            )
        )
    for kind, engine in (("asr", "aws_transcribe"), ("tts", "aws_polly"), ("video", "aws_rekognition")):
        rows.append(
            dict(
                name=engine,
                kind=kind,
                location="cloud",
                provider="aws",
                engine=engine,
                model_key=engine,
                settings={
                    "region": "ap-south-1",
                    "auth_mode": "access_key",
                    **({"staging_bucket": "fixture-private-bucket"} if kind != "tts" else {}),
                },
                credentials={
                    "access_key_id": "fixture-id",
                    "secret_access_key": "fixture-secret",
                    "session_token": "fixture-session",
                },
            )
        )
    for kind in ("asr", "tts"):
        rows.append(
            dict(
                name="azure_" + kind,
                kind=kind,
                location="cloud",
                provider="azure",
                engine="azure_speech",
                model_key="azure_speech",
                settings={"region": "centralindia", "auth_mode": "api_key"},
                credentials={"api_key": "fixture-secret"},
            )
        )
    rows.append(
        dict(
            name="whisper",
            kind="asr",
            location="cloud",
            provider="azure",
            engine="azure_openai_whisper",
            model_key="whisper-deployment",
            settings={"endpoint": AZURE, "api_version": "2024-06-01"},
            credentials={"api_key": "fixture-secret"},
        )
    )
    rows.append(
        dict(
            name="video",
            kind="video",
            location="cloud",
            provider="azure",
            engine="azure_video_indexer",
            model_key="azure_video_indexer",
            settings={
                "auth_mode": "service_principal",
                "subscription_id": "subscription",
                "resource_group": "group",
                "account_name": "account",
                "account_id": "account-id",
                "location": "centralindia",
                "tenant_id": "tenant",
                "client_id": "client",
            },
            credentials={"client_secret": "fixture-secret"},
        )
    )
    return rows


@pytest.mark.parametrize("body", drafts(), ids=lambda value: value["name"])
def test_provider_kind_and_credentials_contract(body):
    config = settings(llm_allowed_base_urls=URLS)
    values, _, credentials = validate_model(ModelDraft(**body), config)
    assert credentials == body["credentials"]
    assert values
    wrong = {**body, "provider": "unsupported"}
    with pytest.raises(AppError):
        validate_model(ModelDraft(**wrong), config)
    wrong = deepcopy(body)
    wrong["credentials"][next(iter(wrong["credentials"]))] = "bad\nheader"
    with pytest.raises(AppError):
        validate_model(ModelDraft(**wrong), config)


def test_whisper_requires_allowed_endpoint_and_supported_language():
    body = next(row for row in drafts() if row["name"] == "whisper")
    with pytest.raises(AppError, match="allowed"):
        validate_model(ModelDraft(**body), settings(llm_allowed_base_urls=[]))
    with pytest.raises(AppError, match="language"):
        validate_model(
            ModelDraft(**body, defaults={"language": "en-US"}), settings(llm_allowed_base_urls=URLS)
        )


def enable(p, token):
    p.settings.external_calls_enabled = True
    p.settings.llm_allowed_base_urls = URLS
    current = p.call("GET", "/platform/settings", token)
    p.call(
        "PATCH",
        "/platform/settings",
        token,
        json={"expected_version": current["configuration_version"], "enabled_providers": ["aws", "azure"]},
    )


def test_cloud_matrix_create_test_edit_and_delete(platform, monkeypatch):
    p = platform
    token, _ = p.admin()
    tenant, _ = p.user("tenant-model-review")
    enable(p, token)
    calls = []

    async def llm(self, url, model, key, provider):
        assert key == "fixture-secret" and model == "fixture-model"
        calls.append((provider, "llm"))

    async def media(self, operation, sample=False):
        assert sample is False
        credentials = self.credentials
        assert "fixture-secret" in credentials.values()
        calls.append((type(self).__name__, operation))
        return True

    monkeypatch.setattr(LLMClient, "health", llm)
    for cls in (AWSProvider, AzureProvider, AzureWhisperProvider):
        monkeypatch.setattr(cls, "validate", media)
    base = "/platform/runtime-models"
    for body in drafts():
        row = p.call("POST", base, token, expected=201, json=body)
        assert row["has_credentials"] and "fixture-secret" not in str(row)
        path = base + "/" + row["id"]
        result = p.call("POST", path + "/test", token, json={"expected_revision": 1})
        assert result["status"] == "passed" and result["inference_verified"] is False
        p.call("POST", path + "/test", tenant, expected=403, json={"expected_revision": 1})
        p.call("POST", path + "/test", token, expected=409, json={"expected_revision": 99})
        edited = {k: v for k, v in body.items() if k != "credentials"}
        edited.update(name="Renamed " + body["name"], expected_revision=1)
        row = p.call("PUT", path, token, json=edited)
        assert row["revision"] == 2 and row["has_credentials"]
        p.call("POST", path + "/test", token, json={"expected_revision": 2})
        p.call("PUT", path, token, json={**edited, "expected_revision": 2, "is_active": False})
        p.call("POST", path + "/test", token, expected=409, json={"expected_revision": 3})
        p.call("DELETE", path + "?expected_revision=3", token)
        p.call("POST", path + "/test", token, expected=404, json={"expected_revision": 4})
    assert len(calls) == 2 * len(drafts())
    audits = p.sql("SELECT details FROM device_platform.activity_events WHERE event_type='model.tested'")
    assert len(audits) == len(calls) and "fixture-secret" not in str(audits)


def test_cloud_test_rechecks_revision_redacts_failures_and_blocks_disabled_calls(platform, monkeypatch):
    p = platform
    token, admin = p.admin()
    enable(p, token)
    row = p.call("POST", "/platform/runtime-models", token, expected=201, json=drafts()[0])
    path = "/platform/runtime-models/" + row["id"] + "/test"
    count = 0

    async def failed(*args, **kwargs):
        nonlocal count
        count += 1
        raise RuntimeError("fixture-secret https://private.example/?signature=secret")

    monkeypatch.setattr(LLMClient, "health", failed)
    result = p.call("POST", path, token, json={"expected_revision": 1})
    assert result["status"] == "failed" and result["error_code"] == "model_test_failed"
    assert "fixture-secret" not in str(result)
    p.settings.external_calls_enabled = False
    p.call("POST", path, token, expected=503, json={"expected_revision": 1})
    assert count == 1
    p.settings.external_calls_enabled = True

    async def changed(*args, **kwargs):
        p.sql("UPDATE device_platform.runtime_models SET revision=revision+1 WHERE id=%s", (row["id"],))

    monkeypatch.setattr(LLMClient, "health", changed)
    p.call("POST", path, token, expected=409, json={"expected_revision": 1})
    assert (
        p.sql("SELECT count(*) FROM device_platform.activity_events WHERE event_type='model.tested'")[0][0]
        == 1
    )
    p.admin("recovery-admin")

    async def revoked(*args, **kwargs):
        p.sql("UPDATE device_platform.users SET platform_role=NULL WHERE id=%s", (admin["id"],))

    monkeypatch.setattr(LLMClient, "health", revoked)
    p.call("POST", path, token, expected=403, json={"expected_revision": 2})


@pytest.mark.parametrize(
    "engine,auth",
    [
        ("aws_transcribe", "workload_identity"),
        ("aws_rekognition", "assume_role"),
        ("aws_polly", "assume_role"),
        ("azure_speech", "workload_identity"),
        ("azure_speech", "service_principal"),
        ("azure_video_indexer", "workload_identity"),
    ],
)
def test_cloud_identity_authentication_settings(engine, auth):
    body = deepcopy(next(row for row in drafts() if row["engine"] == engine))
    body.pop("credentials")
    body["settings"]["auth_mode"] = auth
    if auth == "assume_role":
        body["settings"].update(role_arn="arn:aws:iam::123456789012:role/fixture", external_id="fixture")
    if engine == "azure_speech":
        body["settings"].update(
            endpoint="https://fixture.cognitiveservices.azure.com",
            resource_id="/subscriptions/fixture/resourceGroups/fixture/providers/Microsoft.CognitiveServices/accounts/fixture",
        )
    if auth == "service_principal":
        body["settings"].update(tenant_id="fixture", client_id="fixture")
        body["credentials"] = {"client_secret": "fixture-secret"}
    values, _, _ = validate_model(ModelDraft(**body), settings(llm_allowed_base_urls=URLS))
    assert values["auth_mode"] == auth


def test_conversation_compatibility_settings_are_validated():
    body = drafts()[3]
    body["settings"].update(
        token_parameter="max_completion_tokens",
        stream_usage=False,
        instruction_role="developer",
        model_options={"model_family": "gpt_5_reasoning", "reasoning_effort": "low"},
    )
    values, _, _ = validate_model(ModelDraft(**body), settings(llm_allowed_base_urls=URLS))
    assert values["stream_usage"] is False and values["model_options"]["reasoning_effort"] == "low"
    for field, value in [
        ("max_tokens", True),
        ("stream_usage", "false"),
        ("token_parameter", "invalid"),
        ("model_options", {"model_family": "gpt_5_reasoning", "temperature": 0.5}),
    ]:
        bad = deepcopy(body)
        bad["settings"][field] = value
        with pytest.raises(AppError) as error:
            validate_model(ModelDraft(**bad), settings(llm_allowed_base_urls=URLS))
        assert error.value.status == 422


def test_authentication_change_clears_stored_keys_and_requires_replacement(platform):
    p = platform
    token, _ = p.admin()
    body = next(row for row in drafts() if row["engine"] == "aws_polly")
    row = p.call("POST", "/platform/runtime-models", token, expected=201, json=body)
    path = "/platform/runtime-models/" + row["id"]
    body.pop("credentials")
    body["settings"]["auth_mode"] = "workload_identity"
    changed = p.call("PUT", path, token, json={**body, "expected_revision": 1})
    assert not changed["has_credentials"]
    assert p.sql(
        "SELECT encrypted_credentials,credential_owner_id,credential_owner_org FROM device_platform.runtime_models WHERE id=%s",
        (row["id"],),
    ) == [(None, None, None)]
    body["settings"]["auth_mode"] = "access_key"
    p.call("PUT", path, token, expected=422, json={**body, "expected_revision": 2})
