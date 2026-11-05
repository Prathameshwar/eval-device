import asyncio
import json

import pytest
from conftest import START, TOKEN
from starlette.requests import Request
from starlette.websockets import WebSocket

from device_video.app import create_app


async def test_cancellation_during_final_reply_releases_stream_capacity(settings):
    settings.max_sessions = 1
    app = create_app(settings)
    route = next(route.endpoint for route in app.routes if route.path == "/v1/video/stream")
    health = next(route.endpoint for route in app.routes if route.path == "/health/ready")
    final_reply = asyncio.Event()
    incoming = asyncio.Queue()
    for message in (
        {"type": "websocket.connect"},
        {"type": "websocket.receive", "text": json.dumps(START)},
        {"type": "websocket.receive", "text": '{"type":"stop"}'},
    ):
        incoming.put_nowait(message)

    async def send(message):
        if message["type"] == "websocket.send" and json.loads(message["text"])["type"] == "complete":
            final_reply.set()
            await asyncio.Event().wait()

    scope = dict(
        type="websocket",
        scheme="ws",
        path="/v1/video/stream",
        query_string=b"",
        client=("127.0.0.1", 1234),
        server=("127.0.0.1", 8766),
        headers=[(b"authorization", ("Bearer " + TOKEN).encode())],
    )
    async with app.router.lifespan_context(app):
        task = asyncio.create_task(route(WebSocket(scope, incoming.get, send)))
        await asyncio.wait_for(final_reply.wait(), 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        request = Request(scope | {"type": "http", "scheme": "http", "method": "GET"})
        assert (await health(request))["active_streams"] == 0


@pytest.mark.parametrize("blocked_event", ["websocket.accept", "websocket.close"])
async def test_handshake_has_a_deadline_and_releases_capacity(settings, blocked_event):
    settings.send_seconds = 0.05
    app = create_app(settings)
    route = next(route.endpoint for route in app.routes if route.path == "/v1/video/stream")
    health = next(route.endpoint for route in app.routes if route.path == "/health/ready")
    incoming = asyncio.Queue()
    for message in (
        {"type": "websocket.connect"},
        {"type": "websocket.receive", "text": json.dumps(START)},
        {"type": "websocket.receive", "text": '{"type":"stop"}'},
    ):
        incoming.put_nowait(message)

    async def send(message):
        if message["type"] == blocked_event:
            await asyncio.Event().wait()

    scope = dict(
        type="websocket",
        scheme="ws",
        path="/v1/video/stream",
        query_string=b"",
        client=("127.0.0.1", 1234),
        server=("127.0.0.1", 8766),
        headers=[(b"authorization", ("Bearer " + TOKEN).encode())],
    )
    async with app.router.lifespan_context(app):
        await asyncio.wait_for(route(WebSocket(scope, incoming.get, send)), 1)
        request = Request(scope | {"type": "http", "scheme": "http", "method": "GET"})
        assert (await health(request))["active_streams"] == 0
