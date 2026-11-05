"""Real desktop client against current API routes, grants and disposable PostgreSQL."""

import asyncio
from pathlib import Path

import httpx
import pytest
from psycopg.types.json import Jsonb
from test_device_model_review import assign
from test_direct_models import setup
from test_local_conversation_turns import event
from training_contracts import fingerprint
from training_contracts.localized_cases import review_localization


@pytest.mark.parametrize("cloud", [False, True])
@pytest.mark.parametrize("background", [False, True])
def test_desktop_device_scenario_conversation_history_and_revocation(
    platform, monkeypatch, cloud, background
):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "human-test/src"))
    from human_test.config import Settings
    from training_client.pms_client import ClientError, PMSClient

    p = platform
    token, admin, org = setup(p)
    p.settings.llm_enabled = True
    p.settings.local_history_enabled = True
    p.settings.patient_remote_context_tokens = 16384
    device = p.device(token, org)
    p.enroll(token, org, device["id"])
    models = p.call("GET", "/platform/runtime-models", admin)["items"]
    if cloud:
        p.settings.external_calls_enabled = True
        p.settings.llm_allowed_base_urls = ["https://api.openai.com/v1"]
        models = [
            p.call(
                "POST",
                "/platform/runtime-models",
                admin,
                expected=201,
                json={
                    "name": "Desktop cloud fixture",
                    "kind": "llm",
                    "location": "cloud",
                    "provider": "openai",
                    "engine": "llm",
                    "model_key": "gpt-4o-mini",
                    "settings": {"base_url": "https://api.openai.com/v1"},
                    "credentials": {"api_key": "mocked-key"},
                },
            )
        ]
    assign(p, admin, device["id"], models, mode="cloud" if cloud else "local")
    staff, staff_user = p.user("desktop-staff")
    invitation = p.call(
        "POST",
        f"/organizations/{org}/invitations",
        token,
        expected=201,
        json={"email": "desktop-staff@example.com", "role": "org_user"},
    )
    p.call("POST", "/invitations/accept", staff, json={"token": invitation["invitation_token"]})
    token = staff  # Published Practice must work without clinical-author or admin permissions.

    starts = []

    def request(req):
        # Only transport is bridged; real routes, validation, authentication and DB execute.
        response = p.client.request(req.method, str(req.url), headers=dict(req.headers), content=req.content)
        if req.method == "POST" and req.url.path.endswith("/conversations"):
            starts.append(req.content)
            if len(starts) == 1 and response.status_code == 200:
                # The API committed, but the desktop did not receive its response.
                raise httpx.ReadTimeout("Lost context response", request=req)
        return httpx.Response(response.status_code, content=response.content, headers=response.headers)

    async def exercise():
        client = PMSClient(
            Settings(
                _env_file=None,
                pms_url="http://127.0.0.1",
                organization_id=org,
                device_id=device["id"],
                pms_token=token,
                use_pms_models=True,
            )
        )
        await client.http.aclose()
        client.http = httpx.AsyncClient(
            base_url="http://testserver",
            transport=httpx.MockTransport(request),
            headers={"Authorization": "Bearer " + token},
        )
        try:
            route = await client.model_config()
            client.use_models(route)
            assert client.settings.speech_input_enabled is (not cloud)
            choices = await client.scenario_options()
            scenario = choices["items"][0]
            document = p.sql(
                "SELECT document FROM device_platform.training_scenarios WHERE id=%s", (scenario["id"],)
            )[0][0]
            if background:
                # Prepare a published synthetic fixture using the isolated database owner.
                from test_patient_background import background_case

                document.update(version=5, background=background_case()["background"])
                for language in ("en", "hi"):
                    document = review_localization(document, language)
                p.sql(
                    "ALTER TABLE device_platform.training_scenarios DISABLE TRIGGER training_scenario_guard"
                )
                try:
                    p.sql(
                        "UPDATE device_platform.training_scenarios SET document=%s,fingerprint=%s WHERE id=%s",
                        (Jsonb(document), fingerprint(document), scenario["id"]),
                    )
                finally:
                    p.sql(
                        "ALTER TABLE device_platform.training_scenarios ENABLE TRIGGER training_scenario_guard"
                    )
            body = {
                "expected_revision": 0,
                "scenario_id": scenario["id"],
                "language": "en",
                "vitals": scenario["vitals"],
            }
            saved = await client.save_scenario_selection(body)
            assert saved["document"]["version"] == document["version"]
            assert not {"dialogue", "disclosure", "instructor"} & saved["document"].keys()
            client.use_selection(saved)
            with pytest.raises(httpx.ReadTimeout):
                await client.ensure_conversation("speech")
            client.settings.speaker_output = not client.settings.speaker_output
            conversation = await client.ensure_conversation("text")
            assert len(starts) == 2 and starts[0] == starts[1]
            assert conversation["context"]["execution"] == ("platform" if cloud else "caller")
            assert await client.ensure_conversation("text") == conversation
            if background:
                resolved = conversation["snapshot"]["session_background"]
                assert len(resolved) == 1 and resolved[0]["choice_id"] in ("rice", "bread")
                assert resolved[0]["detail"] in conversation["snapshot"]["system"]
            owner = p.token("direct-tenant")
            p.call(
                "POST",
                f"/organizations/{org}/patient-practice/conversations/"
                + conversation["context"]["conversation_id"]
                + "/close",
                owner,
                expected=404,
            )
            with pytest.raises(ClientError) as conflict:
                await client.save_scenario_selection(body)
            assert conflict.value.code == "patient_setup_changed"
            if not cloud:
                record = event(route)
                written = await client.json("POST", client.base + "/local-conversation-turns", json=record)
                assert (await client.local_history())["items"][0]["turn_key"] == written["turn_key"]
                assert (
                    await client.json("POST", client.base + "/local-conversation-turns", json=record)
                    == written
                )
            # Reassignment must invalidate an already-open desktop context before inference.
            assign(p, admin, device["id"], [], version=1, mode="cloud" if cloud else "local")
            with pytest.raises(ClientError):
                await client.ensure_conversation("text")
            identity = conversation["context"]["conversation_id"]
            p.sql(
                "UPDATE device_platform.organization_memberships SET role='org_read_only' "
                "WHERE organization_id=%s AND user_id=%s",
                (org, staff_user["id"]),
            )
            with pytest.raises(ClientError) as denied:
                await client.close_conversation(identity)
            assert denied.value.code == "permission_denied"
            p.sql(
                "UPDATE device_platform.organization_memberships SET role='org_user' "
                "WHERE organization_id=%s AND user_id=%s",
                (org, staff_user["id"]),
            )
            closed = await client.close_conversation(identity)
            assert closed["status"] == "closed"
            assert await client.close_conversation(identity) == closed
            assert p.sql(
                "SELECT count(*) FROM device_platform.activity_events "
                "WHERE event_type='patient.conversation.closed' AND entity_id=%s",
                (identity,),
            ) == [(1,)]
            outsider, _ = p.admin("desktop-outsider")
            client.http.headers["Authorization"] = "Bearer " + outsider
            with pytest.raises(ClientError):
                await client.scenario_options()
        finally:
            await client.close()

    asyncio.run(exercise())
    assert p.sql("SELECT count(*) FROM device_platform.llm_requests") == [(0,)]
