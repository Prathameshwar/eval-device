import hashlib
import json
import time
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from training_contracts.inference import ISSUER

from local_model_gateway.app import Settings, create_app
from local_model_gateway.security import Grants, Receipts, Rejected
from local_model_gateway.streams import HEADER, Frames


@pytest.fixture
def setup(tmp_path):
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    path = tmp_path / "public.pem"
    path.write_bytes(public)
    state = tmp_path / "manager"
    state.mkdir()
    (state / "client-key.txt").write_text("K" * 64)
    settings = Settings(
        host_id=uuid4(), public_key_file=path, manager_state=state, data_dir=tmp_path / "state"
    )
    return key, public, settings


def token(key, settings, method="POST", path="/v1/infer/llm", raw=b"{}", **changes):
    stamp = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": str(settings.host_id),
        "sub": str(uuid4()),
        "org": str(uuid4()),
        "jti": str(uuid4()),
        "iat": stamp,
        "nbf": stamp,
        "exp": stamp + 30,
        "deadline": stamp + 180,
        "method": method,
        "path": path,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "model": None,
        "max_tokens": 1024,
        "max_audio_seconds": 30,
    }
    claims.update(changes)
    return "Bearer " + jwt.encode(claims, key, algorithm="EdDSA"), claims


@pytest.mark.parametrize(
    "changes",
    [
        {"aud": str(uuid4())},
        {"iss": "other"},
        {"exp": int(time.time()) - 1},
        {"exp": int(time.time()) + 500},
        {"path": "/v1/actions/start"},
        {"sha256": "0" * 64},
        {"method": "GET"},
        {"sub": "not-a-device"},
    ],
)
def test_grants_reject_wrong_scope_and_expiry(setup, changes):
    key, public, settings = setup
    header, _ = token(key, settings, **changes)
    with pytest.raises(Rejected):
        Grants(public, settings.host_id).verify(header, "POST", "/v1/infer/llm", b"{}")


async def test_forwarding_replay_and_management_isolation(setup):
    key, _, settings = setup
    calls = []

    def upstream(request):
        calls.append(request)
        assert request.url.host == "127.0.0.1"
        assert request.headers["authorization"] == "Bearer " + "K" * 64
        return httpx.Response(200, json={"answer": "fixture"})

    app = create_app(settings, transport=httpx.MockTransport(upstream))
    raw = json.dumps({"model": "test", "max_tokens": 32}).encode()
    authorization, claims = token(key, settings, raw=raw, model="test")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://gateway") as client:
        result = await client.post("/v1/infer/llm", content=raw, headers={"Authorization": authorization})
        assert result.status_code == 200
        result = await client.post("/v1/infer/llm", content=raw, headers={"Authorization": authorization})
        assert result.status_code == 409 and result.json()["code"] == "replay"
        result = await client.post("/v1/actions/start", content=raw, headers={"Authorization": authorization})
        assert result.status_code == 403
    assert len(calls) == 1
    restarted = Receipts(settings.data_dir)
    assert restarted.status(claims["jti"], claims["sub"], claims["org"]) == "completed"
    assert restarted.status(claims["jti"], str(uuid4()), claims["org"]) == "not_found"
    with pytest.raises(Rejected):
        restarted.claim(claims)


async def test_unknown_external_outcome_is_not_replayed(setup):
    key, _, settings = setup
    calls = []

    def upstream(request):
        calls.append(request)
        raise httpx.ReadTimeout("private details")

    app = create_app(settings, transport=httpx.MockTransport(upstream))
    raw = b'{"max_tokens":32}'
    authorization, claims = token(key, settings, raw=raw)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://gateway") as client:
        assert (
            await client.post("/v1/infer/llm", content=raw, headers={"Authorization": authorization})
        ).status_code == 503
        assert (
            await client.post("/v1/infer/llm", content=raw, headers={"Authorization": authorization})
        ).status_code == 409
    assert len(calls) == 1
    assert app.state.receipts.status(claims["jti"], claims["sub"], claims["org"]) == "unknown"


def test_stream_sequence_size_and_independence():
    audio, video = Frames("audio"), Frames("video")
    audio.accept(HEADER.pack(0, 1) + bytes(3200))
    video.accept(HEADER.pack(0, 1) + b"\xff\xd8a\xff\xd9")
    with pytest.raises(Rejected):
        audio.accept(HEADER.pack(0, 2) + bytes(3200))
    with pytest.raises(Rejected):
        audio.accept(HEADER.pack(1, 2) + bytes(3201))
    for index in range(1, 300):
        audio.accept(HEADER.pack(index, index + 1) + bytes(3200))
    with pytest.raises(Rejected):
        audio.accept(HEADER.pack(300, 301) + bytes(3200))
    assert len(audio.pcm) == 960000
    assert video.sequence == 1 and not video.pcm


def test_websocket_audio_requires_explicit_end_before_inference(setup):
    from fastapi.testclient import TestClient

    key, _, settings = setup
    calls = []

    def upstream(request):
        calls.append(request)
        return httpx.Response(200, json={"text": "fixture", "language": "en"})

    app = create_app(settings, transport=httpx.MockTransport(upstream))
    metadata = '{"model":"large-v3","language":"en"}'
    with TestClient(app, base_url="https://gateway") as client:
        authorization, _ = token(
            key, settings, method="GET", path="/v1/stream/audio", raw=metadata.encode(), model="large-v3"
        )
        with client.websocket_connect(
            "wss://gateway/v1/stream/audio", headers={"Authorization": authorization}
        ) as socket:
            socket.send_text(metadata)
            assert socket.receive_json()["type"] == "ready"
            socket.send_bytes(HEADER.pack(0, 1) + bytes(3200))
            assert socket.receive_json() == {"type": "ack", "sequence": 0}
        assert not calls
        authorization, _ = token(
            key, settings, method="GET", path="/v1/stream/audio", raw=metadata.encode(), model="large-v3"
        )
        with client.websocket_connect(
            "wss://gateway/v1/stream/audio", headers={"Authorization": authorization}
        ) as socket:
            socket.send_text(metadata)
            assert socket.receive_json()["type"] == "ready"
            socket.send_bytes(HEADER.pack(0, 1) + bytes(3200))
            socket.receive_json()
            socket.send_text('{"type":"end"}')
            assert socket.receive_json()["result"]["text"] == "fixture"
    assert len(calls) == 1
    assert calls[0].url.path == "/v1/infer/asr"


async def test_grant_output_budget_is_enforced_before_upstream(setup):
    key, _, settings = setup
    app = create_app(settings, transport=httpx.MockTransport(lambda _: pytest.fail("Over-budget inference")))
    raw = b'{"model":"test","max_tokens":1025}'
    authorization, _ = token(key, settings, raw=raw, model="test")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://gateway") as client:
        response = await client.post("/v1/infer/llm", content=raw, headers={"Authorization": authorization})
    assert response.status_code == 422


def test_device_admission_limit_is_durable_and_scoped(setup):
    key, _, settings = setup
    _, claims = token(key, settings)
    receipts = Receipts(settings.data_dir, requests_per_minute=1)
    receipts.claim(claims)
    restarted = Receipts(settings.data_dir, requests_per_minute=1)
    with pytest.raises(Rejected) as rejected:
        restarted.claim({**claims, "jti": str(uuid4())})
    assert rejected.value.status == 429
    restarted.claim({**claims, "jti": str(uuid4()), "sub": str(uuid4())})
