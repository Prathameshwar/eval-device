import copy
from uuid import uuid4

import httpx
import pytest
from test_cloud_models import route
from training_client.controller import Controller
from training_client.pms_client import ClientError, PMSClient

from human_test.config import Settings


async def client_with(handler):
    client = PMSClient(Settings(_env_file=None, organization_id=uuid4(), pms_token="fixture"))
    await client.http.aclose()
    client.http = httpx.AsyncClient(base_url="http://127.0.0.1", transport=httpx.MockTransport(handler))
    return client


async def test_assigned_models_are_not_applied_until_checks_and_hash_match():
    selected, current = route(), route()
    selected["llm"]["connection_revision"] = 2
    options = copy.deepcopy(selected)
    options["configuration_hash"] = "b" * 64

    def handler(request):
        if request.url.path.endswith("/model-config"):
            return httpx.Response(200, json=options)
        return httpx.Response(200, json={"status": "ready", "revision": 2})

    client = await client_with(handler)
    client.use_models(current)
    try:
        with pytest.raises(ClientError, match="changed"):
            await client.check_route(selected)
        assert client.model_route == current
    finally:
        await client.close()


async def test_loopback_compatible_model_does_not_require_cloud_gate():
    controller = Controller(
        Settings(_env_file=None, use_pms_models=True, organization_id=uuid4(), pms_token="fixture"),
        lambda *args: None,
    )
    selected = route("local", "cloud")
    selected["cloud_allowed"] = False
    selected["llm"].update(provider="openai_compatible", requires_external=False)
    try:
        controller.use_models(selected)
        assert controller.pms.model_route == selected
        before = controller.settings.connection_id
        bad = copy.deepcopy(selected)
        bad["llm"]["requires_external"] = True
        with pytest.raises(ClientError):
            controller.use_models(bad)
        assert controller.settings.connection_id == before
    finally:
        await controller.close()


@pytest.mark.parametrize("invalid", ["profile_id", "audio_limit"])
async def test_malformed_route_does_not_partially_apply(invalid):
    client = await client_with(lambda request: httpx.Response(200, json={}))
    selected = route()
    client.use_models(selected)
    before = client.settings.model_dump()
    bad = route()
    if invalid == "profile_id":
        bad["profile_id"] = "invalid"
    else:
        bad["audio"]["max_seconds"] = "invalid"
    try:
        with pytest.raises(ClientError, match="previous selection retained"):
            client.use_models(bad)
        assert client.model_route == selected and client.settings.model_dump() == before
    finally:
        await client.close()
