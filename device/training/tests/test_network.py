"""Real TCP/HTTP/WebSocket orchestration; ASR/dialogue/speaker are explicit test doubles."""

import asyncio
import io
import socket
import sys
import threading
import time
from contextlib import contextmanager
from fractions import Fraction
from pathlib import Path
from uuid import uuid4

import av
import httpx
import uvicorn
from fastapi import FastAPI, Request, WebSocket
from test_coordinator import Dialogue, Speech, rig  # noqa: F401

from device_training.agent import Agent, AgentSettings
from device_training.app import create_app
from device_training.media import Transcriber, wav

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "video-process/src"))
from device_video.app import create_app as video_app  # noqa: E402
from device_video.config import Settings as VideoSettings  # noqa: E402


@contextmanager
def serve(factory):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(16)
    port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            factory(port),
            host="127.0.0.1",
            port=port,
            log_level="critical",
            access_log=False,
            proxy_headers=False,
        )
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.02)
    assert server.started
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(5)
        sock.close()
        assert not thread.is_alive()


def jpeg():
    codec = av.CodecContext.create("mjpeg", "w")
    codec.width, codec.height = 640, 480
    codec.pix_fmt, codec.time_base = "yuvj420p", Fraction(1, 10)
    frame = av.VideoFrame(640, 480, "yuvj420p")
    for plane in frame.planes:
        plane.update(bytes([128]) * plane.buffer_size)
    return bytes(codec.encode(frame)[0])


async def test_pi_fixture_across_real_media_connections(rig, tmp_path):  # noqa: F811
    received = bytearray()
    audio = FastAPI()

    @audio.get("/v1/status")
    async def status():
        return {
            "ready": True,
            "console_output": False,
            "callback_configured": False,
            "recording": {"enabled": False},
        }

    @audio.websocket("/v1/audio/stream")
    async def stream(ws: WebSocket):
        assert ws.headers["authorization"] == "Bearer " + "a" * 40
        await ws.accept()
        await ws.receive_json()
        recording = str(uuid4())
        await ws.send_json({"type": "ready", "session_id": recording, "max_frame_bytes": 3200})
        while True:
            message = await ws.receive()
            if message.get("bytes") is not None:
                received.extend(message["bytes"])
            else:
                break
        await ws.send_json({"type": "transcript", "text": "When did it start?"})
        await ws.send_json({"type": "complete", "session_id": recording, "recording": {"status": "disabled"}})

    platform = FastAPI()
    saved = []

    @platform.post("/api/v1/device/training/sessions/{sid}/lease")
    async def lease(sid: str):
        return {"grant": rig.headers()["Authorization"][7:], "scenario": rig.document}

    @platform.post("/api/v1/device/training/sessions/{sid}/result")
    async def result(sid: str, request: Request):
        saved.append(await request.json())
        return {"status": "saved"}

    video_settings = VideoSettings(
        _env_file=None,
        client_tokens={"training": "v" * 40},
        recording_dir=tmp_path / "video",
        min_free_bytes=0,
        segment_seconds=0.2,
    )
    with (
        serve(lambda _: audio) as au,
        serve(lambda _: video_app(video_settings)) as vu,
        serve(lambda _: platform) as pu,
    ):
        settings = rig.settings.model_copy(
            update={
                "store": tmp_path / "coordinator",
                "audio_url": au.replace("http:", "ws:") + "/v1/audio/stream",
                "video_url": vu.replace("http:", "ws:") + "/v1/video/stream",
                "platform_url": pu,
                "video_store": video_settings.recording_dir,
            }
        )

        def app(port):
            settings.origin = f"http://127.0.0.1:{port}"
            return create_app(
                settings, dialogue=Dialogue(), speech=Speech(), transcriber=Transcriber(settings)
            )

        with serve(app) as laptop:
            source = tmp_path / "fixture.wav"
            source.write_bytes(wav(bytes(16000)))
            picture = tmp_path / "fixture.jpg"
            picture.write_bytes(jpeg())
            config = AgentSettings(
                _env_file=None,
                platform_url=pu,
                laptop_url=laptop,
                credential="test-only-credential",
                public_key_file=settings.public_key_file,
                organization_id=settings.organization_id,
                device_id=settings.device_id,
            )
            agent = Agent(config, source, picture)
            try:
                await asyncio.wait_for(agent.run_session({"id": rig.sid}), 20)
            finally:
                await agent.client.aclose()
            assert received == bytes(16000)
            assert saved and saved[0]["simulated"] and saved[0]["status"] == "completed"
            assert saved[0]["recording_status"] == "saved", saved[0]
            async with httpx.AsyncClient(base_url=laptop, trust_env=False) as client:
                headers = rig.headers(scope="read")
                response = await client.post(f"/sessions/{rig.sid}/prepare-replay", headers=headers, json={})
                assert response.status_code == 200, response.text
                data = response.json()
                assert data["replay_frames"] and data["simulated"]
                image = await client.get(f"/sessions/{rig.sid}/frames/0.jpg", headers=headers)
                assert image.content == picture.read_bytes()
                rid = data["video"][0]["id"]
                segment = await client.get(f"/sessions/{rig.sid}/video/{rid}/0.mkv", headers=headers)
                with av.open(io.BytesIO(segment.content)) as container:
                    assert all(bytes(p) == picture.read_bytes() for p in container.demux(video=0) if p.size)
                stolen = await client.get(f"/sessions/{rig.sid}/video/{uuid4()}/0.mkv", headers=headers)
                assert stolen.status_code == 503
