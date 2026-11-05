import asyncio
import hmac
import logging
from contextlib import asynccontextmanager
from typing import Callable
from uuid import UUID

import httpx
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse

from .audio import VoiceDetector
from .config import LOOPBACK_HOSTS, Settings
from .engine import Engine, create_engine
from .runtime import Runtime, ServiceError
from .session import Session

logger = logging.getLogger("device_audio")


def authenticate(connection: HTTPConnection, settings: Settings) -> str | None:
    if connection.headers.get("origin") is not None:
        return None  # Native clients only; browser-origin access is not enabled.
    host = connection.client.host if connection.client else ""
    if connection.scope["scheme"] not in {"https", "wss"} and host not in LOOPBACK_HOSTS:
        return None
    authorization = connection.headers.get("authorization", "")
    if not authorization.startswith("Bearer ") or len(authorization) > 1024:
        return None
    supplied = authorization[7:].encode("utf-8")
    for client_id, secret in settings.client_tokens.items():
        if hmac.compare_digest(supplied, secret.get_secret_value().encode("ascii")):
            return client_id
    return None


def create_app(
    settings: Settings | None = None,
    engine_factory: Callable[[Settings], Engine] = create_engine,
    callback_transport: httpx.AsyncBaseTransport | None = None,
    detector_factory: Callable[[], VoiceDetector] | None = None,
) -> FastAPI:
    settings = settings or Settings()
    runtime = Runtime(settings, engine_factory, callback_transport)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Third-party request logs may include the private callback URL.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        # Uvicorn WebSocket handshake INFO logs include query strings even with access_log=False.
        for name in ("uvicorn.error", "websockets", "faster_whisper"):
            logging.getLogger(name).setLevel(logging.WARNING)
        await runtime.start()
        try:
            yield
        finally:
            await runtime.stop()

    app = FastAPI(
        title="Standalone Device Audio API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.runtime = runtime

    @app.get("/health/live")
    async def live():
        return {"status": "alive"}

    @app.get("/health/ready")
    async def ready(request: Request):
        if authenticate(request, settings) is None:
            raise HTTPException(401, "unauthorized", headers={"WWW-Authenticate": "Bearer"})
        return JSONResponse({"ready": runtime.ready}, status_code=200 if runtime.ready else 503)

    @app.get("/v1/status")
    async def status(request: Request):
        client_id = authenticate(request, settings)
        if client_id is None:
            raise HTTPException(401, "unauthorized", headers={"WWW-Authenticate": "Bearer"})
        return {
            "ready": runtime.ready,
            "failure": runtime.failure,
            "model": settings.model_name,
            "engine": settings.engine_name,
            "supported_languages": settings.supported_languages,
            "streaming": settings.streaming,
            "compute_type": settings.compute_type,
            "device": settings.inference_device,
            "gpu_enabled": settings.gpu_enabled,
            "gpu_device_index": settings.gpu_device_index if settings.gpu_enabled else None,
            "cpu_threads": settings.effective_cpu_threads,
            "client_streaming": client_id in runtime.active_clients,
            "active_sessions": len(runtime.active_clients),
            "inference_queue_depth": runtime.jobs.qsize(),
            "processed_chunks": runtime.processed_chunks,
            "processed_audio_seconds": round(runtime.processed_audio_seconds, 3),
            "inference_seconds": round(runtime.inference_seconds, 3),
            "model_load_seconds": round(runtime.model_load_seconds, 3),
            "callback_configured": settings.callback_url is not None,
            "console_output": settings.console_output,
            "callback_queue_depth": runtime.callbacks.queue.qsize(),
            "callback_counts": dict(runtime.callbacks.counts),
            "recording": runtime.recorder.status(),
        }

    @app.get("/v1/recordings/{recording_id}")
    async def recording_status(recording_id: UUID, request: Request):
        client_id = authenticate(request, settings)
        if client_id is None:
            raise HTTPException(401, "unauthorized", headers={"WWW-Authenticate": "Bearer"})
        receipt = runtime.recorder.lookup(str(recording_id), client_id)
        if receipt is None:
            raise HTTPException(404, "recording_not_found")
        return receipt

    @app.websocket("/v1/audio/stream")
    async def stream(websocket: WebSocket):
        async def close(code: int) -> None:
            try:
                await asyncio.wait_for(websocket.close(code=code), settings.send_timeout_seconds)
            except (TimeoutError, RuntimeError, WebSocketDisconnect, OSError):
                pass

        client_id = authenticate(websocket, settings)
        if client_id is None:
            await close(1008)
            return
        acquired = False
        session = None
        try:
            runtime.acquire(client_id)
            acquired = True
            await asyncio.wait_for(websocket.accept(), settings.send_timeout_seconds)
            session = Session(
                websocket,
                runtime,
                client_id,
                detector_factory() if detector_factory else None,
            )
            await session.run()
            await close(1000)
        except WebSocketDisconnect:
            logger.info("stream_disconnected")
        except ServiceError as exc:
            logger.info("stream_rejected code=%s", exc.code)
            if session:
                try:
                    await session.send({"type": "error", "code": exc.code})
                except Exception:
                    pass
            await close(exc.close_code)
        except Exception:
            logger.warning("stream_failed")
            await close(1011)
        finally:
            if session and session.recording and not session.recording.ended:
                runtime.recorder.finish(session.recording, "stream_interrupted")
            if acquired:
                runtime.active_clients.discard(client_id)

    return app
