"""Real desktop client + central FastAPI/PostgreSQL; local inference is deterministic."""

import asyncio
import json
import time
from pathlib import Path

import httpx
import pytest
from test_device_model_review import assign


@pytest.fixture
def desktop_models(platform):
    h = platform
    h.settings.llm_enabled = True
    token, user = h.user("local-user")
    org = h.organization(token)["id"]
    admin, _ = h.admin("desktop-model-admin")
    device = h.device(token, org)
    h.enroll(token, org, device["id"])
    models = h.call("GET", "/platform/runtime-models", admin)["items"]
    assign(h, admin, device["id"], models)
    route = h.call("GET", f"/organizations/{org}/model-config?device_id={device['id']}", token)
    return h, token, user, org, device, route


def prepare_tenant_cases(h, token, user_id, org):
    h.grant_capability(token, org, user_id, "org.clinical.author")
    base = f"/organizations/{org}/clinical-catalog"
    specialty_ids = [row[0] for row in h.sql("SELECT id FROM device_platform.scenario_categories")]
    patient_id = h.sql("SELECT id FROM device_platform.patient_identities LIMIT 1")[0][0]
    case_ids = [
        row[0]
        for row in h.sql(
            "SELECT DISTINCT ON (category_id) id FROM device_platform.patient_case_templates "
            "ORDER BY category_id,code"
        )
    ]
    assert len(specialty_ids) == len(case_ids) == 3
    for kind, identifiers in (
        ("specialties", specialty_ids),
        ("patients", [patient_id]),
        ("cases", case_ids),
    ):
        for global_id in identifiers:
            response = h.client.post(f"/api/v1{base}/import/{kind}/{global_id}", headers=h.headers(token))
            assert response.status_code in (200, 201), response.text
            imported = response.json()
            h.call(
                "POST",
                f"{base}/{kind}/{imported['id']}/restore",
                token,
                json={"expected_version": imported["version"]},
            )


@pytest.mark.parametrize("published", [False, True], ids=["legacy-case", "published-scenario"])
def test_human_test_setup_turn_history_isolation_and_shutdown(
    desktop_models, monkeypatch, tmp_path, published
):
    root = Path(__file__).resolve().parents[3]
    monkeypatch.syspath_prepend(str(root / "human-test/src"))
    monkeypatch.syspath_prepend(str(root / "local-models/client/src"))
    from human_test.config import Settings
    from training_client import controller as client_module
    from training_client.conversation_history import HistoryRecorder
    from training_client.pms_client import ClientError

    h, token, user, org, device, route = desktop_models
    admin_token = token
    if published:
        from test_scenario_library import member

        h.grant_capability(token, org, user["id"], "org.clinical.review")
        token, user = member(h, admin_token, org, "scenario-learner")
        h.call("GET", f"/organizations/{org}/patient-practice/catalog", token, expected=403)
    else:
        prepare_tenant_cases(h, token, user["id"], org)
    expected_turns = 2 if published else 3
    h.settings.local_history_enabled = True
    other_token, _ = h.user("other-human-test-user")
    other_org = h.organization(other_token, "Other tenant")["id"]
    calls, inference = [], []
    unavailable = False

    def central(request):
        assert request.url.host == "central.test"
        calls.append((request.method, request.url.path))
        if unavailable:
            return httpx.Response(503, json={"error": {"code": "pms_unavailable"}})
        response = h.client.request(
            request.method,
            request.url.raw_path.decode(),
            headers=dict(request.headers),
            content=request.content,
        )
        return httpx.Response(response.status_code, headers=response.headers, content=response.content)

    async def central_async(request):
        return await asyncio.to_thread(central, request)

    def local_model(request):
        assert request.url.host == "127.0.0.1" and request.url.port == 8790
        assert request.headers["Authorization"] == "Bearer " + "K" * 64
        data = json.loads(request.content) if request.content else {}
        if request.url.path == "/v1/capabilities":
            return httpx.Response(
                200,
                json={
                    "version": 1,
                    "revision": 1,
                    "models": [
                        {
                            "id": "fixture",
                            "alias": route["llm"]["model"],
                            "name": "Fixture",
                            "capability": "llm",
                        }
                    ],
                    "services": {"llm": {"model_id": "fixture", "ready": True, "state": "Ready"}},
                },
            )
        if request.url.path == "/v1/llm/inspect":
            result = {
                "props": {"default_generation_settings": {"n_ctx": 32768}},
                "apply-template": {"prompt": "bounded fixture prompt"},
                "tokenize": {"tokens": [1] * 400},
            }[data["operation"]]
            return httpx.Response(200, json=result)
        assert request.url.path == "/v1/infer/llm"
        inference.append(data)
        answer = "My name is Alex."
        system = data["messages"][0]["content"]
        if "\nSOURCE:\n" in system:
            sources = json.loads(system.split("\nSOURCE:\n", 1)[1].split("\nEND SOURCE.", 1)[0])
            name = next(key for key, fact in sources.items() if fact["subject"] == "patient.name")
            answer = json.dumps([name])
        return httpx.Response(
            200, json={"choices": [{"message": {"content": answer}, "finish_reason": "stop"}]}
        )

    monkeypatch.setattr(
        client_module,
        "HistoryRecorder",
        lambda settings, emit: HistoryRecorder(settings, emit, transport=httpx.MockTransport(central)),
    )

    async def exercise():
        nonlocal unavailable
        settings = Settings(
            _env_file=None,
            pms_url="http://127.0.0.1:8000",
            pms_token=token,
            organization_id=org,
            device_id=device["id"],
            use_pms_models=True,
            local_models_key="K" * 64,
            speaker_output=False,
            session_sync_enabled=False,
            history_enabled=True,
            history_dir=tmp_path / "outbox",
        )
        # The bridge uses an explicit fake hostname; every call still passes through the real API.
        settings.pms_url = "https://central.test"
        events = []
        c = client_module.Controller(settings, lambda kind, value: events.append((kind, value)))
        await c.pms.http.aclose()
        c.pms.http = httpx.AsyncClient(
            base_url=settings.pms_url,
            headers={"Authorization": "Bearer " + token},
            transport=httpx.MockTransport(central_async),
        )
        c._local_http = httpx.AsyncClient(transport=httpx.MockTransport(local_model))
        try:
            c.use_models(await c.pms.model_config())
            revision = 0
            if published:
                practice_options = await c.pms.json("GET", c.pms.practice_base + "/scenario-options")
                # Finish on a non-default scenario so retirement exercises its lifecycle guard.
                choices = sorted(
                    practice_options["items"],
                    key=lambda item: item["id"] != practice_options["default"]["scenario_id"],
                )
            else:
                catalog = await c.pms.catalog()
                choices = [
                    next(row for row in catalog["cases"] if row["category_id"] == category["id"])
                    for category in catalog["categories"]
                ]
            for case in choices:
                if published:
                    selected = await c.pms.save_scenario_selection(
                        {
                            "expected_revision": revision,
                            "scenario_id": case["id"],
                            "language": "en",
                            "vitals": {**case["vitals"], "temperature_c": 38.2},
                        }
                    )
                    assert (await c.pms.selection()) == selected
                    assert selected["document"]["vitals"]["temperature_c"] == 38.2
                else:
                    detail = await c.pms.case(case["id"])
                    selected = await c.pms.save_selection(
                        {
                            "expected_revision": revision,
                            "template_id": case["id"],
                            "template_revision": case["revision"],
                            "category_id": case["category_id"],
                            "patient_identity_id": case["patient_identity_id"],
                            "language": "en",
                            "vitals": detail["document"]["vitals"],
                        }
                    )
                revision = selected["revision"]
                c.use_selection(selected)
                result = await c.text_turn("What is your name?")
                assert result["answer"] == "My name is Alex."
                assert c.pms.conversation["status"] == "active"
            assert len(inference) == expected_turns
            inference_count = len(inference)
            deadline = time.monotonic() + 8
            while (
                len([v for k, v in events if k == "history_status" and v["status"] == "saved_to_pms"])
                < expected_turns
            ):
                assert time.monotonic() < deadline, events
                await asyncio.sleep(0.02)
            count = len(calls)
            assert (await c.text_turn("Thanks"))["ignored"]
            assert (await c.respond({"text": "", "asr_finalize_ms": 0}, time.monotonic()))["ignored"]
            assert len(calls) == count
            history = await c.history_items()
            assert len(history["items"]) == expected_turns
            assert all(row["response_text"] == "My name is Alex." for row in history["items"])
            with pytest.raises(ClientError):
                await c.pms.json("GET", f"/api/v1/organizations/{other_org}/patient-practice/catalog")
            unavailable = True
            with pytest.raises(ClientError):
                await c.text_turn("How do you feel?")
            unavailable = False
            c.pms.http.headers["Authorization"] = "Bearer " + h.token(
                "local-user", exp=int(time.time()) - 300
            )
            with pytest.raises(ClientError):
                await c.text_turn("How do you feel?")
            assert len(inference) == inference_count
            if published:
                c.pms.http.headers["Authorization"] = "Bearer " + token
                latest = await c.pms.save_scenario_selection(
                    {
                        "expected_revision": revision,
                        "scenario_id": selected["scenario_id"],
                        "language": "en",
                        "vitals": selected["document"]["vitals"],
                    }
                )
                with pytest.raises(ClientError) as changed:
                    await c.text_turn("How do you feel?")
                assert changed.value.code == "patient_setup_changed"
                c.use_selection(latest)
                h.call(
                    "POST",
                    f"/organizations/{org}/training/scenarios/{selected['scenario_id']}/retire",
                    admin_token,
                )
                with pytest.raises(ClientError) as retired:
                    await c.text_turn("How do you feel?")
                assert retired.value.code == "scenario_unavailable"
                assert len(inference) == inference_count
        finally:
            unavailable = False
            c.pms.http.headers["Authorization"] = "Bearer " + token
            await c.close()
        assert c.pms.http.is_closed and c._local_http.is_closed
        assert not c.recorder.disk.is_alive() and not c.recorder.uploader.is_alive()

    asyncio.run(exercise())
    assert h.sql("SELECT count(*) FROM device_platform.local_conversation_turns")[0][0] == expected_turns
    assert h.sql("SELECT count(*) FROM device_platform.llm_requests")[0][0] == 0
    assert not any(path.endswith("/completions") for _, path in calls)
