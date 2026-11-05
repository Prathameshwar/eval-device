"""Pi host, shared conversation engine, signed GPU gateway and isolated PostgreSQL.

Only inference and physical hardware are substituted; no GUI or paid provider is used.
"""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_session_queue import queue_device  # noqa: F401


def test_two_published_scenarios_through_pi_and_authenticated_gpu(queue_device, tmp_path, monkeypatch):  # noqa: F811
    root = Path(__file__).resolve().parents[3]
    for source in ("pi-test/src", "local-models/client/src", "local-models/gateway/src"):
        monkeypatch.syspath_prepend(str(root / source))
    from local_model_gateway.app import Settings as GatewaySettings
    from local_model_gateway.app import create_app
    from pi_test.config import Settings
    from pi_test.service import Service

    h, instructor, _, org, device, token, _, _, _ = queue_device
    key = Ed25519PrivateKey.generate()
    private = tmp_path / "private.pem"
    private.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
    h.settings.training_key_file = private
    public = tmp_path / "public.pem"
    public.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    host = uuid4()
    path = f"/organizations/{org}/devices/{device['id']}"
    row = h.call("GET", path, instructor)
    h.call(
        "PATCH",
        path,
        instructor,
        json={
            "expected_etag": row["management_etag"],
            "details": {"inference": {"host_id": str(host), "origin": "https://gpu.test"}},
        },
    )
    route = h.call("GET", f"/organizations/{org}/model-config", token)
    model = route["llm"]["model"]
    state = tmp_path / "manager"
    state.mkdir()
    (state / "client-key.txt").write_text("K" * 64)
    inference_calls = []

    def manager(request):
        payload = json.loads(request.content or b"{}")
        if request.url.path == "/v1/capabilities":
            return httpx.Response(
                200,
                json={
                    "version": 1,
                    "revision": 1,
                    "models": [
                        {"id": "fixture", "alias": model, "name": "Fixture", "capability": "llm"},
                        {
                            "id": route["audio"]["model"],
                            "name": "Fixture ASR",
                            "capability": "asr",
                            "platform_speech": True,
                        },
                    ],
                    "services": {
                        "llm": {"model_id": "fixture", "ready": True, "state": "Ready"},
                        "asr": {"model_id": route["audio"]["model"], "ready": True, "state": "Ready"},
                    },
                },
            )
        if request.url.path == "/v1/infer/asr":
            assert payload["wav_base64"]
            inference_calls.append(payload)
            return httpx.Response(200, json={"text": "What is your name?", "language": "en"})
        if request.url.path == "/v1/llm/inspect":
            operation = payload["operation"]
            result = {
                "props": {"default_generation_settings": {"n_ctx": 32768}},
                "apply-template": {"prompt": "bounded fixture prompt"},
                "tokenize": {"tokens": [1] * 400},
            }[operation]
            return httpx.Response(200, json=result)
        assert request.url.path == "/v1/infer/llm"
        inference_calls.append(payload)
        system = payload["messages"][0]["content"]
        answer = "My name is Alex."
        if "\nSOURCE:\n" in system:
            sources = json.loads(system.split("\nSOURCE:\n", 1)[1].split("\nEND SOURCE.", 1)[0])
            name = next(key for key, fact in sources.items() if fact["subject"] == "patient.name")
            answer = json.dumps([name])
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": answer}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 400, "completion_tokens": 6},
            },
        )

    gateway = create_app(
        GatewaySettings(
            host_id=host, public_key_file=public, manager_state=state, data_dir=tmp_path / "gateway"
        ),
        transport=httpx.MockTransport(manager),
    )

    def platform_call(request):
        response = h.client.request(
            request.method,
            request.url.raw_path.decode(),
            headers=dict(request.headers),
            content=request.content,
        )
        return httpx.Response(response.status_code, content=response.content, headers=response.headers)

    async def dispatch(request):
        if request.url.host == "central.test":
            return await asyncio.to_thread(platform_call, request)
        assert request.url.host == "gpu.test"
        assert token not in request.headers.get("authorization", "")
        return await httpx.ASGITransport(gateway).handle_async_request(request)

    async def exercise():
        settings = Settings(
            app_root=tmp_path / "pi",
            control_dir=tmp_path / "control",
            pms_url="https://central.test",
            pms_token=token,
            device_id=device["id"],
            organization_id=org,
            inference_url="https://gpu.test",
            inference_host_id=host,
            speaker_output=False,
            session_sync_enabled=False,
            history_enabled=False,
        )
        service = Service(settings)
        service.runtime.inference.async_transport = httpx.MockTransport(dispatch)
        await service.runtime.initialize()
        pms = service.runtime.controller.pms
        await pms.http.aclose()
        pms.http = httpx.AsyncClient(
            base_url=settings.pms_url,
            headers={"Authorization": "Bearer " + token},
            transport=httpx.MockTransport(dispatch),
        )
        service.ready = True
        identities = []
        try:
            catalog, _ = await service.runtime.prepare()
            assert len(catalog["scenarios"]) >= 2
            for scenario in catalog["scenarios"][:2]:
                await service.begin(scenario["id"])
                await service.reconcile()
                await service.runtime.text_turn("What is your name?")
                await service.runtime.controller.preflight()

                async def microphone():
                    yield bytes(3200)

                await service.runtime.controller.turn(microphone())
                identities.append(pms.conversation["context"]["conversation_id"])
                assert service.runtime.controller.history[-1]["role"] == "assistant"
                assert service.runtime.controller.history[-1]["content"] == "My name is Alex."
                await service.finish()
                assert not service.active and pms.conversation is None
            assert len(set(identities)) == 2
        finally:
            await service.runtime.close()
        return identities

    identities = asyncio.run(exercise())
    assert sum("wav_base64" in call for call in inference_calls) == 2
    assert len(inference_calls) >= 4
    for identity in identities:
        assert (
            h.sql("SELECT status FROM device_platform.patient_conversations WHERE id=%s", (identity,))[0][0]
            == "closed"
        )
