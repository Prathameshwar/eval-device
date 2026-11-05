import asyncio
import ipaddress
import json
import secrets
import time
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from starlette.requests import HTTPConnection

from .config import Settings
from .privacy import StorageError
from .protocol import Start, StreamRules
from .recorder import Recorder


def authenticated(connection: HTTPConnection, settings: Settings) -> str | None:
    if connection.headers.get("origin") is not None or connection.scope.get("query_string"):
        return None
    if connection.url.scheme not in {"https", "wss"}:
        try:
            if not connection.client or not ipaddress.ip_address(connection.client.host).is_loopback:
                return None
        except ValueError:
            return None
    authorization = connection.headers.get("authorization", "")
    if not authorization.startswith("Bearer ") or not authorization.isascii() or len(authorization) > 4096:
        return None
    supplied = authorization[7:]
    owner = None
    for identity, token in settings.client_tokens.items():
        if secrets.compare_digest(supplied, token.get_secret_value()):
            owner = identity
    return owner


async def disk_result(future: Any, seconds: float) -> Any:
    # A timeout stops waiting; it does not cancel an in-flight native write.
    wrapped = asyncio.wrap_future(future)
    wrapped.add_done_callback(lambda done: None if done.cancelled() else done.exception())
    return await asyncio.wait_for(asyncio.shield(wrapped), seconds)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    active: set[str] = set()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        recorder = Recorder(settings)
        app.state.recorder = recorder
        try:
            try:
                await disk_result(recorder.started, settings.disk_wait_seconds)
            except (TimeoutError, StorageError):
                pass
            yield
        finally:
            await asyncio.to_thread(recorder.stop)

    app = FastAPI(
        title="Local video recording", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
    )

    def owner(request: Request) -> str:
        identity = authenticated(request, settings)
        if identity is None:
            raise HTTPException(401, "authentication_required")
        return identity

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/health/ready")
    async def ready(request: Request) -> dict[str, Any]:
        owner(request)
        recorder = app.state.recorder
        if not recorder.ready or recorder.stopping:
            raise HTTPException(503, "storage_unavailable")
        return {"status": "ready", "active_streams": len(active)}

    @app.get("/v1/recordings/{recording_id}")
    async def recording(recording_id: str, request: Request) -> dict[str, Any]:
        data = app.state.recorder.status(recording_id, owner(request))
        if data is None:
            raise HTTPException(404, "recording_not_found")
        return data

    @app.websocket("/v1/video/stream")
    async def stream(websocket: WebSocket) -> None:
        identity = authenticated(websocket, settings)
        recorder: Recorder = app.state.recorder
        if identity is None:
            await websocket.close(1008)
            return
        if len(active) >= settings.max_sessions or not recorder.ready or recorder.stopping:
            await websocket.close(1013)
            return
        recording_id = str(uuid4())
        active.add(recording_id)
        count, submitted, connected = 0, False, True
        reason: str | None = "disconnected"
        deadline = time.monotonic() + settings.max_session_seconds

        async def send(data: dict[str, Any]) -> None:
            await asyncio.wait_for(websocket.send_json(data), settings.send_seconds)

        async def receive() -> dict[str, Any]:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError("duration_limit")
            message = await asyncio.wait_for(websocket.receive(), min(settings.idle_seconds, remaining))
            if message["type"] == "websocket.disconnect":
                raise WebSocketDisconnect()
            return dict(message)

        try:
            await asyncio.wait_for(websocket.accept(), settings.send_seconds)
            message = await receive()
            text = message.get("text")
            if text is None or len(text) > 2048:
                raise ValueError("invalid_start")
            try:
                start = Start.model_validate_json(text)
            except ValueError:
                raise ValueError("invalid_start") from None
            rules = StreamRules(start, settings)
            future = recorder.submit("start", recording_id, identity, start)
            submitted = True
            await disk_result(future, settings.disk_wait_seconds)
            await send(
                {
                    "type": "ready",
                    "recording_id": recording_id,
                    "max_frame_bytes": settings.max_frame_bytes,
                    "status": "pending",
                }
            )
            while True:
                message = await receive()
                data = recorder.status(recording_id, identity)
                if data and data["status"] == "incomplete":
                    raise StorageError("recording_failed")
                if message.get("bytes") is not None:
                    frame = rules.frame(message["bytes"])
                    recorder.submit("frame", recording_id, frame, weight=len(frame.jpeg))
                    count += 1
                    await send(
                        {
                            "type": "accepted",
                            "sequence": frame.sequence,
                            "timestamp_us": frame.timestamp_us,
                            "status": "pending",
                        }
                    )
                else:
                    control = message.get("text", "")
                    if len(control) > 128 or json.loads(control) != {"type": "stop"}:
                        raise ValueError("invalid_control")
                    reason = None
                    break
        except WebSocketDisconnect:
            connected = False
        except TimeoutError:
            reason = "stream_timeout"
        except (ValueError, StorageError) as exc:
            reason = str(exc) if isinstance(exc, StorageError) else "invalid_stream"
        except asyncio.CancelledError:
            connected = False
            reason = "cancelled"
            raise
        except Exception:
            reason = "stream_error"
        finally:
            try:
                receipt = None
                if submitted:
                    try:
                        future = recorder.submit("finish", recording_id, reason, count)
                        receipt = await disk_result(future, settings.disk_wait_seconds)
                    except (TimeoutError, StorageError, asyncio.CancelledError):
                        receipt = recorder.status(recording_id, identity)
                if connected:
                    try:
                        if reason:
                            await send({"type": "error", "code": reason})
                        if submitted:
                            await send(
                                {
                                    "type": "complete",
                                    "recording_id": recording_id,
                                    "recording": receipt or {"status": "pending", "finalized": False},
                                }
                            )
                        await asyncio.wait_for(
                            websocket.close(1000 if reason is None else 1011), settings.send_seconds
                        )
                    except (TimeoutError, RuntimeError, WebSocketDisconnect, OSError):
                        pass
            finally:
                active.discard(recording_id)

    return app
