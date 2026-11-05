"""Device-only desktop pairing and Practice against disposable PostgreSQL."""

import asyncio
import json
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import psycopg
import pytest
from test_device_model_review import assign
from test_llm_api import Model
from test_local_conversation_turns import event


def fixture_reply(messages):
    """Honor the current fact-selection contract without making inference calls."""
    system = "\n".join(message["content"] for message in messages if message["role"] == "system")
    if "\nSOURCE:\n" not in system:
        return "hello", "hello"
    sources = json.loads(system.split("\nSOURCE:\n", 1)[1].split("\nEND SOURCE.", 1)[0])
    assert sources, "The interview fixture must supply an answerable fact"
    key = next(iter(sources))
    return json.dumps([key]), sources[key]["text"]


class PairingModel(Model):
    last_answer = "hello"

    async def events(self, **params):
        reply, self.last_answer = fixture_reply(params["messages"])
        async for item in super().events(**params):
            yield {**item, "text": reply}


@pytest.mark.parametrize("cloud,department", [(False, False), (True, False), (False, True), (True, True)])
@pytest.mark.parametrize("device_type", ["manikin", "laptop"])
def test_device_pairing_practice_isolation_and_revocation(
    platform, monkeypatch, tmp_path, cloud, department, device_type
):
    root = Path(__file__).resolve().parents[3]
    monkeypatch.syspath_prepend(str(root / "human-test/src"))
    monkeypatch.syspath_prepend(str(root / "local-models/client/src"))
    from human_test.config import Settings
    from human_test.connection import ConnectionError, PairingClient, read_connection
    from training_client.controller import Controller
    from training_client.pms_client import ClientError

    p = platform
    tenant, _ = p.user("pairing-tenant")
    admin, _ = p.admin()
    org = p.organization(tenant, plan="advanced")["id"]
    dept = (
        p.call(
            "POST", f"/organizations/{org}/departments", tenant, expected=201, json={"name": "Practice lab"}
        )["id"]
        if department
        else None
    )
    device = p.device(
        tenant, org, device_unique_id="Demo-Desk-01", department_id=dept, device_type=device_type
    )
    neighbor = p.device(tenant, org, device_unique_id="Demo-Desk-02")
    neighbor_token = p.enroll(tenant, org, neighbor["id"])
    p.settings.llm_enabled = p.settings.local_history_enabled = True
    p.settings.patient_remote_context_tokens = 16384
    p.settings.external_calls_enabled = True
    p.settings.llm_allowed_base_urls = ["https://api.openai.com/v1"]
    model = PairingModel()
    p.client.app.state.llm = model
    models = p.call("GET", "/platform/runtime-models", admin)["items"]
    if cloud:
        models = [
            p.call(
                "POST",
                "/platform/runtime-models",
                admin,
                expected=201,
                json={
                    "name": "Pairing cloud",
                    "kind": "llm",
                    "location": "cloud",
                    "provider": "openai",
                    "engine": "llm",
                    "model_key": "test-model",
                    "settings": {"base_url": "https://api.openai.com/v1"},
                    "credentials": {"api_key": "mock-key"},
                },
            )
        ]
    assign(p, admin, device["id"], models, mode="cloud" if cloud else "local")
    issued = p.call("POST", f"/organizations/{org}/devices/{device['id']}/enrollment", tenant)
    users_before = p.sql("SELECT count(*) FROM device_platform.users")

    def bridge(req):
        response = p.client.request(req.method, str(req.url), headers=dict(req.headers), content=req.content)
        return httpx.Response(response.status_code, content=response.content, headers=response.headers)

    pairing = PairingClient(
        "http://127.0.0.1",
        transport=httpx.MockTransport(bridge),
        path=tmp_path / "private" / "connection.json",
    )
    try:
        with pytest.raises(ConnectionError, match="incorrect or expired"):
            pairing.pair("wrong-device", issued["enrollment_token"])
        paired = pairing.pair("demo-desk-01", issued["enrollment_token"])
        assert paired["device_id"] == device["id"] and paired["organization_id"] == org
        assert read_connection(pairing.path) == paired
        assert pairing.resume(paired) == paired
        with pytest.raises(ConnectionError):
            pairing.pair("demo-desk-01", issued["enrollment_token"])
    finally:
        pairing.close()
    token = paired["credential"]
    # Exercise the actual desktop startup report immediately after enrollment.
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "human-test/scripts"))
    from types import SimpleNamespace

    from external_pms import report_local_models
    from pydantic import SecretStr

    with httpx.Client(transport=httpx.MockTransport(bridge)) as http:
        assert report_local_models(
            SimpleNamespace(
                http=http,
                pms_url="http://127.0.0.1",
                external_settings=SimpleNamespace(
                    device_id=UUID(device["id"]), device_token=SecretStr(token)
                ),
            ),
            {"models": []},
        )
    assert p.sql("SELECT count(*) FROM device_platform.users") == users_before
    base = f"/organizations/{org}"
    p.call("GET", "/platform/runtime-models", token, expected=403)
    p.call("GET", base + "/members", token, expected=403)
    p.call("GET", base + "/patient-practice/catalog", token, expected=403)
    p.call("GET", f"/organizations/{uuid4()}/patient-practice/scenario-options", token, expected=404)
    p.call("GET", base + f"/model-config?device_id={neighbor['id']}", token, expected=422)

    async def exercise():
        from training_client.conversation_history import HistoryRecorder

        monkeypatch.setattr(
            "training_client.controller.HistoryRecorder",
            lambda settings, emit: HistoryRecorder(settings, emit, transport=httpx.MockTransport(bridge)),
        )
        events = []
        controller = Controller(
            Settings(
                _env_file=None,
                session_sync_enabled=False,
                history_dir=tmp_path / "history",
                pms_url="http://127.0.0.1",
                organization_id=org,
                device_id=device["id"],
                department_id=dept,
                pms_token=token,
                use_pms_models=True,
                streaming=False,
                local_models_key="local-fixture-key",
            ),
            lambda *event: events.append(event),
        )
        client = controller.pms
        await client.http.aclose()
        client.http = httpx.AsyncClient(
            base_url="http://testserver",
            transport=httpx.MockTransport(bridge),
            headers={"Authorization": "Bearer " + token},
        )
        try:
            route = await client.model_config()
            controller.use_models(route)
            scenario = (await client.scenario_options())["items"][0]
            selected = await client.save_scenario_selection(
                {
                    "expected_revision": 0,
                    "scenario_id": scenario["id"],
                    "language": "en",
                    "vitals": scenario["vitals"],
                }
            )
            controller.use_selection(selected)
            conversation = await client.ensure_conversation("text")
            context = conversation["context"]
            assert context["owner_id"] == device["id"]
            assert p.sql("SELECT user_id,device_id FROM device_platform.patient_practice_selections") == [
                (None, UUID(device["id"]))
            ]
            path = base + "/patient-practice/conversations/" + context["conversation_id"]
            assert p.sql(
                "SELECT device_id FROM device_platform.activity_events WHERE event_type='patient.conversation.started'"
            ) == [(UUID(device["id"]),)]
            with pytest.raises(psycopg.errors.CheckViolation):
                p.sql(
                    "UPDATE device_platform.patient_practice_selections SET device_id=%s,revision=revision+1 WHERE id=%s",
                    (neighbor["id"], selected["id"]),
                )
            with pytest.raises(psycopg.errors.CheckViolation):
                p.sql(
                    "UPDATE device_platform.patient_conversations SET device_id=%s WHERE id=%s",
                    (neighbor["id"], context["conversation_id"]),
                )
            p.call("GET", path, neighbor_token, expected=404)
            p.call("GET", path, tenant, expected=404)
            p.call("POST", path + "/close", neighbor_token, expected=404)
            if cloud:
                result = await client.answer([{"role": "user", "content": "Hello"}], lambda *args: None)
                assert result["status"] == "succeeded" and model.calls == 1
                p.call("GET", base + "/llm/requests/" + result["request_key"], neighbor_token, expected=404)
            else:
                record = event(
                    route,
                    department_id=None,
                    conversation_id=context["conversation_id"],
                    practice_id=selected["id"],
                    practice_revision=selected["revision"],
                    practice_snapshot_hash=context["case_snapshot_hash"],
                    answer_source="patient_conversation",
                    policy_version="patient-conversation-v1",
                    context_ref={
                        key: context[key]
                        for key in (
                            "conversation_id",
                            "language_pack_version",
                            "language_pack_hash",
                            "compiler_version",
                        )
                    },
                )
                history = base + "/llm/local-conversation-turns"
                written = p.call("POST", history, token, json=record)
                assert written["department_id"] == dept
                assert p.call("POST", history, token, json=record) == written
                assert p.call("POST", history, token, json={**record, "department_id": dept}) == written
                p.call(
                    "POST",
                    history,
                    token,
                    expected=404,
                    json={**record, "turn_key": str(uuid4()), "department_id": str(uuid4())},
                )
                assert p.call("GET", history, neighbor_token)["items"] == []
                p.call("GET", history + "/" + record["turn_key"], neighbor_token, expected=404)
                assert (await client.local_history())["items"][0]["turn_key"] == record["turn_key"]
                from pms_api.modules.local_turns import LocalTurnEvent

                metadata = {key: value for key, value in record.items() if key in LocalTurnEvent.model_fields}
                metadata.update(provider_calls=1, total_ms=15)
                await client.record_local_turn(metadata)
                assert (
                    p.call("POST", base + "/llm/local-turns", token, json=metadata)["turn_key"]
                    == record["turn_key"]
                )
                p.call(
                    "POST",
                    base + "/llm/local-turns",
                    token,
                    expected=404,
                    json={**metadata, "turn_key": str(uuid4()), "department_id": str(uuid4())},
                )
                assert (
                    p.call("GET", base + "/llm/local-turns", token)["items"][0]["turn_key"]
                    == record["turn_key"]
                )
                metadata.update(turn_key=str(uuid4()), context_ref=None)
                p.call("POST", base + "/llm/local-turns", token, expected=422, json=metadata)
                identity = p.call("GET", history + "/identity", token)
                assert identity["issuer"] == "urn:pms:device" and identity["subject"] == device["id"]
            await client.close_conversation(context["conversation_id"])
            if not cloud:
                delayed = {**record, "turn_key": str(uuid4()), "sequence": 2}
                p.call("POST", history, neighbor_token, expected=404, json=delayed)
                assert p.call("POST", history, token, json=delayed)["department_id"] == dept
            # Drive actual desktop conversation orchestration against this API/database.
            # Only inference is mocked; context admission, authorization, telemetry,
            # history isolation and conversation close remain real.
            local_calls = []
            local_answers = []

            def local_server(request):
                assert request.url.host == "127.0.0.1"
                assert request.headers["authorization"] == "Bearer local-fixture-key"
                payload = json.loads(request.content) if request.content else {}
                path = request.url.path
                if path == "/v1/capabilities":
                    return httpx.Response(
                        200,
                        json={
                            "version": 1,
                            "revision": 1,
                            "models": [
                                {
                                    "id": "fixture",
                                    "alias": route["llm"]["model"],
                                    "capability": "llm",
                                    "name": "Fixture LLM",
                                }
                            ],
                            "services": {"llm": {"model_id": "fixture", "ready": True, "state": "Ready"}},
                        },
                    )
                if path == "/v1/llm/inspect":
                    assert payload["model"] == route["llm"]["model"]
                    operation, data = payload["operation"], payload["payload"]
                    if operation == "props":
                        return httpx.Response(200, json={"default_generation_settings": {"n_ctx": 16384}})
                    if operation == "apply-template":
                        return httpx.Response(200, json={"prompt": json.dumps(data["messages"])})
                    assert operation == "tokenize"
                    # Mock estimate; native context fitting is checked separately.
                    return httpx.Response(200, json={"tokens": [1] * (len(data["content"]) // 4)})
                assert path == "/v1/infer/llm"
                assert payload["model"] == route["llm"]["model"]
                local_calls.append(payload)
                reply, spoken = fixture_reply(payload["messages"])
                local_answers.append(spoken)
                return httpx.Response(
                    200,
                    json={
                        "choices": [{"message": {"content": reply}, "finish_reason": "stop"}],
                        "usage": {"prompt_tokens": 20, "completion_tokens": 1},
                    },
                )

            if not cloud:
                controller._local_http = httpx.AsyncClient(transport=httpx.MockTransport(local_server))
            controller.reset()
            for question in ("What brings you in today?", "When did it start?"):
                answer = await controller.text_turn(question)
                assert answer["answer"] == (model.last_answer if cloud else local_answers[-1])
            assert len(controller.history) == 4 and not controller.busy
            interview = client.conversation["context"]["conversation_id"]
            assert sum(kind == "speak" for kind, _ in events) == 2
            if not cloud:
                await asyncio.wait_for(controller.metrics_reporter.queue.join(), 5)
                async with asyncio.timeout(10):
                    while p.sql(
                        "SELECT count(*) FROM device_platform.local_turns WHERE device_id=%s",
                        (device["id"],),
                    ) != [(3,)] or any(
                        row["save_status"] == "saved_locally" for row in controller.recorder.pending()
                    ):
                        await asyncio.sleep(0.02)
                assert len(local_calls) == 2 and model.calls == 0
                assert p.sql(
                    "SELECT count(*) FROM device_platform.local_turns WHERE device_id=%s", (device["id"],)
                ) == [(3,)]
            controller.reset()
            assert not controller.history and client.conversation is None
            await asyncio.gather(*controller._closing_tasks)
            assert (
                p.call("GET", base + "/patient-practice/conversations/" + interview, token, expected=409)[
                    "error"
                ]["code"]
                == "conversation_closed"
            )
            assert p.sql(
                "SELECT status FROM device_platform.patient_conversations WHERE id=%s", (interview,)
            ) == [("closed",)]
            await controller.text_turn("How are you feeling now?")
            assert client.conversation["context"]["conversation_id"] != interview
            # Scope lifecycle changes invalidate an otherwise valid device credential.
            for table, identity in [("organizations", org), ("devices", device["id"])]:
                suspend = ",suspension_source='platform'" if table == "organizations" else ""
                restore = ",suspension_source=NULL" if table == "organizations" else ""
                p.sql(
                    f"UPDATE device_platform.{table} SET is_active=false{suspend} WHERE id=%s",
                    (identity,),
                )
                p.call("GET", "/device/identity", token, expected=409)
                p.call("GET", base + "/patient-practice/scenario-options", token, expected=409)
                p.sql(f"UPDATE device_platform.{table} SET is_active=true{restore} WHERE id=%s", (identity,))
            if dept:
                p.sql(
                    "UPDATE device_platform.departments SET is_active=false,status_reason='fixture' WHERE id=%s",
                    (dept,),
                )
                p.call("GET", "/device/identity", token, expected=409)
                p.sql("UPDATE device_platform.departments SET is_active=true WHERE id=%s", (dept,))
            if cloud:

                async def changed_during_health(*args, **kwargs):
                    await asyncio.to_thread(assign, p, admin, device["id"], [], version=1, mode="cloud")

                model.health = changed_during_health
                p.call(
                    "GET", base + f"/llm/models/{route['llm']['connection_id']}/status", token, expected=409
                )
            p.call("POST", f"{base}/devices/{device['id']}/revoke", tenant)
            p.call("GET", "/device/identity", token, expected=401)
            p.call("GET", base + "/patient-practice/scenario-options", token, expected=401)
            before = (model.calls, len(local_calls))
            with pytest.raises(ClientError):
                await controller.text_turn("This revoked device must not run inference")
            assert before == (model.calls, len(local_calls)) and not controller.busy
        finally:
            await controller.close()

    asyncio.run(exercise())
