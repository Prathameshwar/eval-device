"""Quota reservation, one execution grant, ownership and device cancellation on PostgreSQL."""

import asyncio
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from test_device_model_review import assign
from test_session_queue import queue_device  # noqa: F401


def prepare_video(fixture, tmp_path):
    p, owner, admin, org, device, credential, _, _, case = fixture
    key = Ed25519PrivateKey.generate()
    path = tmp_path / "signing.pem"
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
    p.settings.training_key_file = path
    target = {"host_id": str(uuid4()), "origin": "https://gpu.test", "video_transport": True}
    device_path = f"/organizations/{org}/devices/{device['id']}"
    current = p.call("GET", device_path, owner)
    p.call(
        "PATCH",
        device_path,
        owner,
        json={"expected_etag": current["management_etag"], "details": {"inference": target}},
    )
    video = p.call(
        "POST",
        "/platform/runtime-models",
        admin,
        expected=201,
        json={
            "name": "Motion processor",
            "kind": "video",
            "location": "local",
            "provider": "local",
            "engine": "opencv_motion",
            "model_key": "opencv_motion",
        },
    )
    models = p.call("GET", "/platform/runtime-models", admin)["items"]
    assert video in models
    assign(p, admin, device["id"], models, version=1)
    config = p.call("GET", "/device/config", credential)
    p.call(
        "POST",
        "/device/heartbeat",
        credential,
        json={
            "boot_id": str(uuid4()),
            "sequence_number": 0,
            "applied_profile_revision_id": config["profile_revision_id"],
            "applied_configuration_hash": config["configuration_hash"],
        },
    )
    base = f"/organizations/{org}/patient-practice"
    selection = p.call(
        "PUT",
        base + "/scenario-selection",
        credential,
        json={
            "expected_revision": 0,
            "scenario_id": case["id"],
            "language": "en",
            "vitals": case["vitals"],
        },
    )["selection"]
    route = p.call("GET", f"/organizations/{org}/model-config", credential)
    conversation = p.call(
        "POST",
        base + "/conversations",
        credential,
        json={
            "request_key": str(uuid4()),
            "practice_id": selection["id"],
            "practice_revision": selection["revision"],
            "connection_id": route["llm"]["connection_id"],
            "language": "en",
            "profile_revision_id": route["profile_revision_id"],
            "configuration_hash": route["configuration_hash"],
        },
    )["context"]["conversation_id"]
    run = p.call(
        "POST",
        "/device/runs",
        credential,
        expected=202,
        json={
            "request_key": str(uuid4()),
            "operation": "video.motion",
            "profile_revision_id": config["profile_revision_id"],
            "duration_seconds": 2,
        },
    )["run"]
    body = {
        "host_id": target["host_id"],
        "origin": target["origin"],
        "request_id": str(uuid4()),
        "method": "GET",
        "path": "/v1/stream/video",
        "body_sha256": hashlib.sha256(b"{}").hexdigest(),
        "model": "opencv_motion",
        "processing_run_id": run["id"],
        "conversation_id": conversation,
    }
    return p, credential, run, body, key


def test_video_run_authorizes_once_even_with_concurrent_grants(queue_device, tmp_path):  # noqa: F811
    p, credential, run, body, key = prepare_video(queue_device, tmp_path)

    def grant(_):
        return p.client.post(
            "/api/v1/device/inference/grants",
            headers={"Authorization": "Bearer " + credential},
            json={**body, "request_id": str(uuid4())},
        )

    with ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(grant, range(2)))
    assert sorted(response.status_code for response in responses) == [200, 409], [
        response.text for response in responses
    ]
    encoded = next(response.json()["grant"] for response in responses if response.status_code == 200)
    claims = jwt.decode(encoded, key.public_key(), algorithms=["EdDSA"], audience=body["host_id"])
    assert claims["processing_run_id"] == run["id"]
    assert claims["max_video_seconds"] == 2 and claims["video_operation"] == "video.motion"
    state, usage = p.sql(
        "SELECT status,usage FROM device_platform.processing_runs WHERE id=%s", (run["id"],)
    )[0]
    assert state == "running" and usage["reserved"] == 2
    p.call(
        "POST",
        f"/device/runs/{run['id']}/result",
        credential,
        json={"status": "succeeded", "result": {"motion_detected": True}},
    )
    p.call("POST", "/device/inference/grants", credential, json=body, expected=409)


def test_device_cancel_enforces_owner_and_lifecycle(queue_device, tmp_path):  # noqa: F811
    p, credential, run, body, _ = prepare_video(queue_device, tmp_path)
    _, owner, _, org, device, _, _, _, _ = queue_device
    other = p.device(owner, org)
    other_credential = p.enroll(owner, org, other["id"])
    path = f"/device/runs/{run['id']}/cancel"
    p.call("POST", path, other_credential, expected=404)
    p.call("POST", path, owner, expected=403)
    p.call(
        "POST", "/device/inference/grants", credential, json={**body, "conversation_id": None}, expected=409
    )
    assert p.call("POST", path, credential)["status"] == "cancelled"
    assert p.call("POST", path, credential)["status"] == "cancelled"
    p.call("POST", "/device/inference/grants", credential, json=body, expected=409)
    device_path = f"/organizations/{org}/devices/{device['id']}"
    current = p.call("GET", device_path, owner)
    p.call(
        "PATCH", device_path, owner, json={"expected_etag": current["management_etag"], "is_active": False}
    )
    p.call("POST", path, credential, expected=409)


def test_shared_video_processing_crosses_real_api_contract(queue_device, tmp_path, monkeypatch):  # noqa: F811
    """Real shared HTTP client/API/database; substitute only capture and GPU inference."""
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "local-models/client/src"))
    from training_client.config import Settings
    from training_client.pms_client import PMSClient
    from training_client.processing import VideoProcessing

    p, credential, reserved, grant_body, signing = prepare_video(queue_device, tmp_path)
    p.call("POST", f"/device/runs/{reserved['id']}/cancel", credential)
    submissions = []

    def dispatch(request):
        if request.method == "POST" and request.url.path == "/api/v1/device/runs":
            submissions.append(json.loads(request.content))
        response = p.client.request(
            request.method,
            request.url.raw_path.decode(),
            headers=dict(request.headers),
            content=request.content,
        )
        return httpx.Response(response.status_code, content=response.content, headers=response.headers)

    async def transport(request):
        return await asyncio.to_thread(dispatch, request)

    async def exercise():
        settings = Settings(
            app_root=tmp_path / "client",
            pms_url="https://platform.test",
            pms_token=credential,
            organization_id=queue_device[3],
        )
        pms = PMSClient(settings)
        await pms.http.aclose()
        pms.http = httpx.AsyncClient(
            base_url=settings.pms_url,
            headers={"Authorization": "Bearer " + credential},
            transport=httpx.MockTransport(transport),
        )

        async def capabilities(method, path):
            assert (method, path) == ("GET", "/v1/capabilities")
            return {"media": {"video_operations": ["video.motion"]}}

        async def transmit(connection, kind, metadata, frames):
            assert kind == "video" and metadata["processing_run_id"] != reserved["id"]
            granted = await pms.json(
                "POST",
                "/api/v1/device/inference/grants",
                json={
                    **grant_body,
                    "request_id": str(uuid4()),
                    "processing_run_id": metadata["processing_run_id"],
                    "body_sha256": hashlib.sha256(json.dumps(metadata).encode()).hexdigest(),
                },
            )
            claims = jwt.decode(
                granted["grant"], signing.public_key(), algorithms=["EdDSA"], audience=grant_body["host_id"]
            )
            assert claims["max_video_seconds"] == 2
            assert len([frame async for frame in frames]) == 2
            return {"motion_detected": True, "frames": 2}

        async def frames():
            yield b"fixture-frame-one"
            yield b"fixture-frame-two"

        monkeypatch.setattr("local_model_client.streams.transmit", transmit)
        processing = VideoProcessing(settings, pms, SimpleNamespace(remote=True, async_request=capabilities))
        try:
            result = await processing.execute(frames(), 2)
            assert result["status"] == "succeeded" and result["result"]["motion_detected"]
            assert processing.last["state"] == "succeeded"
            return result["run_id"]
        finally:
            await pms.http.aclose()

    identity = asyncio.run(exercise())
    assert len(submissions) == 1
    assert (
        p.sql("SELECT status FROM device_platform.processing_runs WHERE id=%s", (identity,))[0][0]
        == "succeeded"
    )
