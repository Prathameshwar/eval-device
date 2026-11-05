"""Real loopback HTTP/WebSocket transport, with a fake inference engine (no downloads)."""

import asyncio
import json
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from conftest import HEADERS, SPEECH, TOKEN, Detector, FakeEngine
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from device_audio.app import create_app


def test_real_uvicorn_transport_reuses_model_caps_frames_and_redacts_query(settings, caplog):
    loads = []
    engine = FakeEngine()

    def factory(_):
        loads.append(1)
        return engine

    app = create_app(settings, factory, detector_factory=Detector)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(16)
        port = listener.getsockname()[1]
        config = uvicorn.Config(
            app,
            log_config=None,
            access_log=False,
            proxy_headers=False,
            ws="websockets",
            ws_max_size=settings.max_frame_bytes,
            ws_max_queue=4,
            ws_per_message_deflate=False,
        )
        server = uvicorn.Server(config)
        thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert server.started
            with httpx.Client(trust_env=False) as client:
                assert (
                    client.get(f"http://127.0.0.1:{port}/health/ready", headers=dict(HEADERS)).status_code
                    == 200
                )

            async def run():
                uri = f"ws://127.0.0.1:{port}/v1/audio/stream"
                with pytest.raises(InvalidStatus):
                    async with connect(uri + "?token=" + TOKEN, proxy=None):
                        pass
                for _ in range(2):
                    async with connect(uri, additional_headers=dict(HEADERS), proxy=None) as ws:
                        await ws.send('{"type":"start","language":"hi"}')
                        assert json.loads(await ws.recv())["type"] == "ready"
                        await ws.send(SPEECH * 6)
                        await ws.send('{"type":"finish"}')
                        events = []
                        async with asyncio.timeout(5):
                            async for raw in ws:
                                events.append(json.loads(raw))
                        assert events[-1]["type"] == "complete"
                        assert any(event["type"] == "transcript" for event in events)
                async with connect(uri, additional_headers=dict(HEADERS), proxy=None) as ws:
                    await ws.send('{"type":"start"}')
                    await ws.recv()
                    await ws.send(b"\0" * (settings.max_frame_bytes + 2))
                    with pytest.raises(ConnectionClosed) as failure:
                        await ws.recv()
                    assert failure.value.rcvd.code == 1009

            try:
                asyncio.run(run())
            except InvalidStatus as exc:
                raise AssertionError(bytes(exc.response.body).decode()) from None
            assert len(loads) == 1
            assert len(engine.calls) == 2
            assert TOKEN not in caplog.text
        finally:
            server.should_exit = True
            thread.join(10)
            assert not thread.is_alive()
