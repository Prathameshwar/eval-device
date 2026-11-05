import asyncio
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import uvicorn
from conftest import AUTH, START, TOKEN
from websockets.asyncio.client import connect

from device_video.app import create_app
from device_video.protocol import HEADER
from device_video.store import remux


def test_real_loopback_websocket_and_disk(settings, frames, start, tmp_path):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    config = uvicorn.Config(
        create_app(settings),
        host="127.0.0.1",
        port=port,
        ws="websockets",
        ws_max_size=settings.max_frame_bytes + HEADER.size,
        ws_max_queue=2,
        ws_per_message_deflate=False,
        proxy_headers=False,
        access_log=False,
        log_level="error",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()

    async def send():
        async with connect(
            f"ws://127.0.0.1:{port}/v1/video/stream", additional_headers=AUTH.copy(), compression=None
        ) as connection:
            await connection.send(json.dumps(START))
            ready = json.loads(await connection.recv())
            for frame in frames:
                await connection.send(HEADER.pack(b"VPF1", frame.sequence, frame.timestamp_us) + frame.jpeg)
                assert json.loads(await connection.recv())["type"] == "accepted"
            await connection.send('{"type":"stop"}')
            complete = json.loads(await connection.recv())
            assert complete["recording"]["status"] == "saved"
            assert complete["recording"]["saved_frames"] == len(frames)
            return ready["recording_id"]

    try:
        deadline = time.monotonic() + 5
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        identity = asyncio.run(send())
        with httpx.Client(trust_env=False) as http:
            response = http.get(f"http://127.0.0.1:{port}/v1/recordings/{identity}", headers=AUTH.copy())
            assert response.json()["finalized"]
            assert http.get(f"http://127.0.0.1:{port}/health/ready").status_code == 401
        # Run the shipped sender in its own process against actual HTTP/WebSocket I/O.
        source = tmp_path / "sample.mkv"
        source.write_bytes(remux(frames, start))
        sender = Path(__file__).resolve().parents[1] / "scripts" / "stream_file.py"
        result = subprocess.run(
            [
                sys.executable,
                str(sender),
                "--input",
                str(source),
                "--url",
                f"ws://127.0.0.1:{port}/v1/video/stream",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            env=os.environ
            | {
                "VIDEO_CLIENT_TOKENS": json.dumps({"pi-1": TOKEN}),
                "ws_proxy": "http://127.0.0.1:1",
                "WS_PROXY": "http://127.0.0.1:1",
                "no_proxy": "",
                "NO_PROXY": "",
            },
        )
        assert result.returncode == 0, result.stderr
        events = [json.loads(line) for line in result.stdout.splitlines()]
        assert events[-1]["recording"]["status"] == "saved"
        assert events[-1]["recording"]["saved_frames"] == len(frames)
    finally:
        server.should_exit = True
        thread.join(5)
        listener.close()
    assert not thread.is_alive()
