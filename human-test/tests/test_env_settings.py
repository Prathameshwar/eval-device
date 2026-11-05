from pathlib import Path
from uuid import UUID

import pytest
from training_client.pms_client import PMSClient

from human_test.config import Settings


def test_hosted_api_is_default_but_explicit_origin_is_preserved(monkeypatch):
    monkeypatch.delenv("HUMAN_PMS_URL", raising=False)
    assert Settings(_env_file=None).pms_url == "https://eval.centralindia.cloudapp.azure.com"
    assert Settings(_env_file=None, pms_url="http://127.0.0.1:8000").pms_url == "http://127.0.0.1:8000"


def test_example_accepts_blank_optional_connection_for_published_models(tmp_path, monkeypatch):
    for key in tuple(__import__("os").environ):
        if key.startswith("HUMAN_"):
            monkeypatch.delenv(key)
    example = Path(__file__).resolve().parents[1] / ".env.example"
    configuration = tmp_path / ".env"
    configuration.write_text(example.read_text(), encoding="utf-8")
    org = UUID("11111111-1111-4111-8111-111111111111")
    settings = Settings(_env_file=configuration, organization_id=org, pms_token="test-session")
    settings.require_credentials()
    assert settings.connection_id is None
    assert settings.use_pms_models
    with pytest.raises(RuntimeError, match="Configure PMS login"):
        Settings(_env_file=configuration).require_credentials()


@pytest.mark.parametrize(
    "name", ["organization_id", "connection_id", "processing_profile_id", "device_id", "department_id"]
)
def test_optional_ids_accept_empty_but_reject_malformed(name):
    assert getattr(Settings(_env_file=None, **{name: ""}), name) is None
    with pytest.raises(ValueError):
        Settings(_env_file=None, **{name: "invalid-id"})


@pytest.mark.asyncio
async def test_model_reads_include_registered_device_binding(monkeypatch):
    org = UUID("11111111-1111-4111-8111-111111111111")
    device = UUID("22222222-2222-4222-8222-222222222222")
    profile = UUID("33333333-3333-4333-8333-333333333333")
    client = PMSClient(
        Settings(_env_file=None, organization_id=org, device_id=device, pms_token="test-session")
    )
    calls = []

    async def read(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {}

    monkeypatch.setattr(client, "json", read)
    try:
        await client.model_config(profile)
    finally:
        await client.http.aclose()
    assert calls == [
        (
            "GET",
            f"/api/v1/organizations/{org}/model-config",
            {"params": {"device_id": str(device)}},
        ),
    ]
