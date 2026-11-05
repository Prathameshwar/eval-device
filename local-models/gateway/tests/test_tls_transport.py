"""Real loopback TLS and WebSocket transport; fixture issuer/model, no live cloud."""

import asyncio
import ipaddress
import socket
import threading
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import jwt
import uvicorn
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
from cryptography.x509.oid import NameOID
from fastapi import Request
from local_model_client.remote import RemoteConnection
from local_model_client.streams import audio, audio_frames, transmit
from training_contracts.inference import ISSUER

from local_model_gateway.app import Settings, create_app


async def test_https_and_independent_wss_clients_over_verified_tls(tmp_path):
    signing = ed25519.Ed25519PrivateKey.generate()
    public = tmp_path / "platform.pem"
    public.write_bytes(
        signing.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    tls_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "loopback fixture")])
    stamp = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(tls_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(stamp - timedelta(minutes=1))
        .not_valid_after(stamp + timedelta(hours=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False
        )
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(tls_key, hashes.SHA256())
    )
    cert, key = tmp_path / "tls.crt", tmp_path / "tls.key"
    cert.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key.write_bytes(
        tls_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
    manager = tmp_path / "manager"
    manager.mkdir()
    (manager / "client-key.txt").write_text("K" * 64)
    host, device, org = uuid4(), uuid4(), uuid4()
    settings = Settings(
        host_id=host, public_key_file=public, manager_state=manager, data_dir=tmp_path / "receipts"
    )
    upstream = []

    def model(request):
        assert request.headers["authorization"] == "Bearer " + "K" * 64
        upstream.append(request.url.path)
        return httpx.Response(200, json={"text": "fixture answer"})

    app = create_app(settings, transport=httpx.MockTransport(model))

    @app.post("/api/v1/device/inference/grants")
    async def issue(request: Request):
        assert request.headers["authorization"] == "Bearer dev_fixture"
        body = await request.json()
        assert body["host_id"] == str(host)
        now = int(datetime.now(UTC).timestamp())
        claims = {
            "iss": ISSUER,
            "aud": str(host),
            "sub": str(device),
            "org": str(org),
            "jti": body["request_id"],
            "iat": now,
            "nbf": now,
            "exp": now + 30,
            "deadline": now + 180,
            "method": body["method"],
            "path": body["path"],
            "sha256": body["body_sha256"],
            "model": body["model"],
            "voice": body["voice"],
            "max_tokens": 32,
            "max_audio_seconds": 30,
        }
        return {"grant": jwt.encode(claims, signing, algorithm="EdDSA")}

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    origin = f"https://127.0.0.1:{listener.getsockname()[1]}"
    server = uvicorn.Server(
        uvicorn.Config(app, ssl_certfile=str(cert), ssl_keyfile=str(key), access_log=False, log_level="error")
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        async with asyncio.timeout(10):
            while not server.started:
                assert thread.is_alive()
                await asyncio.sleep(0.02)
        connection = RemoteConnection(
            origin, host, origin, "dev_fixture", ca_file=cert, journal_dir=tmp_path / "requests"
        )
        result = await connection.async_request(
            "POST", "/v1/infer/llm", {"model": "fixture", "max_tokens": 32}
        )
        assert result["text"] == "fixture answer"
        assert (await audio(connection, bytes(3200), "fixture", "en"))["text"] == "fixture answer"

        async def frames():
            yield b"\xff\xd8fixture\xff\xd9"

        video = await transmit(connection, "video", {}, frames())
        assert video["frames"] == 1 and video["inference"] == "unsupported"
        assert upstream == ["/v1/infer/llm", "/v1/infer/asr"]
        # Generator resumes only after an acknowledged frame. Capture has not yet
        # ended, and the backend must not receive partial audio for inference.
        during_capture = []

        async def live_frames():
            yield bytes(1600)
            during_capture.append((list(upstream), connection.last_request["status"]))
            yield bytes(1600)

        assert (await audio_frames(connection, live_frames(), "fixture", "en"))["text"] == "fixture answer"
        assert during_capture == [(["/v1/infer/llm", "/v1/infer/asr"], "unknown")]
        assert upstream.count("/v1/infer/asr") == 2
        assert len(connection.journal.recent()) == 4
        assert all(row["status"] == "completed" for row in connection.journal.recent())

        async def lost_frames():
            yield bytes(1600)
            raise ValueError("capture was interrupted")

        import pytest
        from local_model_client import ConnectionError

        with pytest.raises(ConnectionError):
            await audio_frames(connection, lost_frames(), "fixture", "en")
        assert upstream.count("/v1/infer/asr") == 2
        assert connection.last_request["status"] == "unknown"
    finally:
        server.should_exit = True
        await asyncio.to_thread(thread.join, 5)
        listener.close()
        assert not thread.is_alive()
