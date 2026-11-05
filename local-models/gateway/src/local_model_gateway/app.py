import asyncio
import base64
import io
import json
import time
import wave
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

import httpx
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse
from local_model_client.connection import MAX_RESPONSE, client_key
from pydantic import BaseModel, ConfigDict, Field

from .security import Grants, Receipts, Rejected


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host_id: UUID
    public_key_file: Path
    manager_state: Path
    data_dir: Path
    manager_port: int = Field(8790, ge=1024, le=65535)
    concurrency: int = Field(2, ge=1, le=8)
    device_requests_per_minute: int = Field(120, ge=1, le=600)


def create_app(settings, *, transport=None):
    grants = Grants(settings.public_key_file.read_bytes(), settings.host_id)
    receipts = Receipts(settings.data_dir, settings.device_requests_per_minute)
    slots = asyncio.Semaphore(settings.concurrency)

    @asynccontextmanager
    async def lifespan(app):
        yield

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.receipts = receipts

    async def forward(claims, method, path, payload):
        remaining = claims["deadline"] - time.time()
        if remaining <= 0:
            raise Rejected("timeout", 408)
        # No redirects, proxies, retries or user-selected upstream addresses.
        async with asyncio.timeout(remaining):
            async with httpx.AsyncClient(
                transport=transport, trust_env=False, follow_redirects=False, timeout=remaining
            ) as client:
                async with client.stream(
                    method,
                    f"http://127.0.0.1:{settings.manager_port}" + path,
                    json=payload,
                    headers={"Authorization": "Bearer " + client_key(settings.manager_state)},
                ) as response:
                    raw = bytearray()
                    async for block in response.aiter_bytes():
                        raw.extend(block)
                        if len(raw) > MAX_RESPONSE:
                            raise Rejected("output_limit", 502)
                    if response.status_code != 200:
                        raise Rejected("unavailable", 503)
                    value = json.loads(raw)
                    if not isinstance(value, dict):
                        raise ValueError()
                    return value

    def validate_payload(claims, payload):
        if not isinstance(payload, dict):
            raise Rejected("input", 422)
        if claims["path"] in {"/v1/infer/asr", "/v1/infer/llm", "/v1/llm/inspect", "/v1/stream/audio"}:
            if payload.get("model") != claims.get("model"):
                raise Rejected()
        if claims["path"] == "/v1/infer/tts" and payload.get("voice") != claims.get("voice"):
            raise Rejected()
        if claims["path"] == "/v1/stream/video":
            if payload.get("model") != claims.get("model") or payload.get("processing_run_id") != claims.get(
                "processing_run_id"
            ):
                raise Rejected()
        if claims["path"] == "/v1/infer/llm":
            maximum = payload.get("max_tokens")
            if type(maximum) is not int or not 1 <= maximum <= claims.get("max_tokens", 0):
                raise Rejected("input", 422)
        if claims["path"] == "/v1/infer/asr":
            try:
                raw = base64.b64decode(payload["wav_base64"], validate=True)
                with wave.open(io.BytesIO(raw)) as wav:
                    if (
                        wav.getframerate() != 16000
                        or wav.getnchannels() != 1
                        or wav.getsampwidth() != 2
                        or not 0 < wav.getnframes() <= 16000 * claims.get("max_audio_seconds", 0)
                    ):
                        raise ValueError()
            except (ValueError, TypeError, KeyError, wave.Error, EOFError):
                raise Rejected("input", 422) from None

    @app.api_route("/v1/{operation:path}", methods=["GET", "POST"])
    async def infer(operation: str, request: Request):
        acquired = False
        claims = None
        try:
            if (
                request.url.scheme != "https"
                or request.headers.get("origin")
                or request.headers.get("cookie")
            ):
                raise Rejected()
            raw = bytearray()
            async with asyncio.timeout(10):
                async for block in request.stream():
                    raw.extend(block)
                    if len(raw) > 1500000:
                        raise Rejected("input", 413)
            path = "/v1/" + operation
            claims = grants.verify(request.headers.get("authorization", ""), request.method, path, raw)
            payload = json.loads(raw) if raw else {}
            validate_payload(claims, payload)
            if slots.locked():
                raise Rejected("capacity", 429)
            await slots.acquire()
            acquired = True
            receipts.claim(claims)
            if path == "/v1/requests/status":
                identity = str(UUID(payload["request_id"]))
                value = {
                    "request_id": identity,
                    "status": receipts.status(identity, claims["sub"], claims["org"]),
                }
            else:
                value = await forward(claims, request.method, path, payload or None)
                if path == "/v1/capabilities":
                    value["media"] = {
                        "video_operations": ["video.motion"],
                        "live_audio_transport": True,
                        "partial_transcripts": False,
                    }
            receipts.finish(claims["jti"], "completed")
            return JSONResponse(value)
        except Rejected as error:
            return JSONResponse({"code": error.code}, status_code=error.status)
        except asyncio.CancelledError:
            raise
        except Exception:
            # An accepted external call may have executed. Keep its durable unknown receipt.
            return JSONResponse({"code": "unavailable"}, status_code=503)
        finally:
            if acquired:
                slots.release()

    @app.websocket("/v1/stream/{kind}")
    async def media(socket: WebSocket, kind: str):
        from .streams import receive

        await receive(socket, kind, grants, receipts, slots, forward, validate_payload)

    return app
