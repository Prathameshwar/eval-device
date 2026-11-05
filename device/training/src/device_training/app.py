import asyncio
import ipaddress
import json
import re
import ssl
import struct
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from uuid import UUID

import httpx
from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from training_contracts import Scenario
from training_contracts.clinical_cases import ClinicalRuntime
from training_contracts.privacy import StorageError, no_link
from websockets.asyncio.client import connect

from .auth import Grants
from .config import Settings
from .coordinator import Coordinator
from .engines import Dialogue, Speech
from .media import Transcriber
from .store import Store


class Start(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: ClinicalRuntime | Scenario
    simulated: bool = False
    anchor_unix_ms: int = Field(ge=0, le=9999999999999)


class Playback(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event: Literal["claim", "started", "finished", "failed"]
    offset_ms: float = Field(ge=0, le=660000)


class Finish(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["cancelled", "completed"] = "cancelled"


class Sync(BaseModel):
    status: Literal["saved", "failed", "unknown"]


async def bounded_body(request, maximum=524288):
    body = bytearray()
    async with asyncio.timeout(10):
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > maximum:
                raise HTTPException(413, "request_too_large")
    return bytes(body)


def create_app(settings=None, *, dialogue=None, speech=None, transcriber=None):
    s = settings or Settings()
    grants = Grants(s)

    @asynccontextmanager
    async def lifespan(app):
        store = Store(s.store, s.max_store_bytes)
        await store.ready()
        no_link(s.dialogue_key_file)
        engine = dialogue or Dialogue(
            s.dialogue_url,
            s.dialogue_model,
            timeout=s.response_seconds,
            key=s.dialogue_key_file.read_text().strip(),
        )
        coordinator = Coordinator(
            s, store, engine, speech or Speech(s.speech_executable), transcriber or Transcriber(s)
        )
        app.state.coordinator = coordinator
        context = ssl.create_default_context(cafile=str(s.ca_file) if s.ca_file else None)
        app.state.platform = httpx.AsyncClient(
            base_url=s.platform_url, verify=context, trust_env=False, follow_redirects=False, timeout=10
        )
        watcher = asyncio.create_task(coordinator.watch())
        try:
            yield
        finally:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)
            await coordinator.close()
            await app.state.platform.aclose()
            store.stop()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def boundary(request, call_next):
        try:
            if request.url.scheme != "https" and (
                not request.client or not ipaddress.ip_address(request.client.host).is_loopback
            ):
                return Response(status_code=403)
        except ValueError:
            return Response(status_code=403)
        if request.headers.get("origin") not in {None, s.origin}:
            return Response(status_code=403)
        if request.headers.get("host") != httpx.URL(s.origin).netloc.decode():
            return Response(status_code=403)
        response = await call_next(request)
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; media-src 'self' blob:; img-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            }
        )
        return response

    @app.exception_handler(ValidationError)
    async def validation_error(request, exc):
        return Response('{"detail":"invalid_request"}', status_code=422, media_type="application/json")

    @app.exception_handler(StorageError)
    async def storage_error(request, exc):
        return Response('{"detail":"storage_unavailable"}', status_code=503, media_type="application/json")

    def auth(request, scopes, sid=None):
        if request.scope.get("query_string"):
            raise HTTPException(400, "query_not_supported")
        return grants.verify(request.headers.get("authorization"), scopes, sid)

    async def document(request, sid, scopes=("read", "device", "control")):
        claims = auth(request, scopes, sid)
        c = app.state.coordinator
        data = c.data if c.data and c.data["id"] == str(sid) else json.loads(await c.store.call("read", sid))
        if (
            data["expires_at"] <= time.time()
            or data["organization_id"] != claims["organization_id"]
            or data["device_id"] != claims["device_id"]
            or data["scenario_hash"] != claims["scenario_hash"]
        ):
            raise HTTPException(404, "recording_not_found")
        return data

    @app.get("/")
    async def index():
        return FileResponse(Path(__file__).with_name("static") / "index.html")

    @app.get("/ui/{name}")
    async def static(name: Literal["app.js", "style.css"]):
        return FileResponse(Path(__file__).with_name("static") / name)

    @app.get("/health/live")
    async def live():
        return {"status": "live"}

    # Fixed same-origin proxy for human controls. No arbitrary URLs or credential persistence.
    @app.api_route("/platform/{path:path}", methods=["GET", "POST"])
    async def platform_proxy(path: str, request: Request):
        allowed = rf"organizations/{s.organization_id}/training/(?:scenarios|scenarios/[0-9a-f-]{{36}}/(?:approve|retire)|sessions|sessions/[0-9a-f-]{{36}}(?:/(?:access|stop|feedback|rubric))?)"
        if not re.fullmatch(allowed, path) or request.url.query not in {"", "control=true"}:
            raise HTTPException(404, "route_not_available")
        token = request.headers.get("authorization", "")
        if not token.startswith("Bearer ") or len(token) > 16384:
            raise HTTPException(401, "sign_in_required")
        body = await bounded_body(request)
        try:
            async with app.state.platform.stream(
                request.method,
                "/api/v1/" + path,
                params={"control": "true"} if request.url.query else None,
                content=body,
                headers={"Authorization": token, "Content-Type": "application/json"},
            ) as result:
                content = bytearray()
                async for chunk in result.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > 2_000_000:
                        raise ValueError()
                return Response(bytes(content), result.status_code, media_type="application/json")
        except Exception:
            raise HTTPException(502, "platform_unavailable_outcome_unknown") from None

    @app.get("/configuration")
    async def configuration():
        return {"organization_id": s.organization_id, "device_id": s.device_id}

    @app.post("/sessions/{sid}/start")
    async def start(sid: UUID, request: Request):
        claims = auth(request, {"device"}, sid)
        body = Start.model_validate_json(await bounded_body(request))
        return await app.state.coordinator.start(
            claims, body.scenario.model_dump(mode="json"), body.anchor_unix_ms, body.simulated
        )

    @app.post("/sessions/{sid}/lease")
    async def lease(sid: UUID, request: Request):
        claims = auth(request, {"device"}, sid)
        app.state.coordinator.renew(claims)
        return {"status": "renewed"}

    @app.get("/sessions/{sid}")
    async def state(sid: UUID, request: Request):
        return await document(request, sid)

    @app.post("/sessions/{sid}/stop")
    async def stop(sid: UUID, request: Request):
        claims = auth(request, {"control", "device"}, sid)
        c = app.state.coordinator
        c.same(claims)
        body = await bounded_body(request, 1024)
        status = Finish.model_validate_json(body or b"{}").status
        await c.finish(status, "none" if status == "completed" else "operator_stop")
        return c.data

    @app.post("/sessions/{sid}/recording-failure")
    async def recording_failure(sid: UUID, request: Request):
        claims = auth(request, {"device"}, sid)
        c = app.state.coordinator
        c.same(claims)
        c.data["recording_status"] = "incomplete"
        await c.save()
        return {"status": "incomplete"}

    @app.post("/sessions/{sid}/sync")
    async def sync(sid: UUID, request: Request):
        claims = auth(request, {"device"}, sid)
        c = app.state.coordinator
        c.same(claims)
        body = Sync.model_validate_json(await bounded_body(request, 1024))
        c.data["sync_status"] = body.status
        await c.save()
        return {"status": body.status}

    @app.post("/sessions/{sid}/turns/{tid}")
    async def turn(sid: UUID, tid: UUID, request: Request):
        claims = auth(request, {"device"}, sid)
        c = app.state.coordinator
        try:
            offset = float(request.headers["x-capture-offset-ms"])
        except (KeyError, ValueError):
            raise HTTPException(400, "capture_clock_required") from None
        size = 0
        start = time.monotonic()

        async def chunks():
            nonlocal size
            async for chunk in request.stream():
                c.guard()
                size += len(chunk)
                if (
                    size > claims["limits"]["max_audio_turn_seconds"] * 32000
                    or time.monotonic() - start > claims["limits"]["max_audio_turn_seconds"] + 2
                ):
                    raise HTTPException(413, "audio_limit")
                if chunk:
                    yield chunk

        try:
            return await c.turn(claims, str(tid), offset, chunks())
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, "turn_failed_do_not_replay") from None

    @app.post("/sessions/{sid}/turns/{tid}/playback")
    async def playback(sid: UUID, tid: UUID, request: Request):
        claims = auth(request, {"device"}, sid)
        body = Playback.model_validate_json(await bounded_body(request, 1024))
        return await app.state.coordinator.playback(claims, str(tid), body.event, body.offset_ms)

    @app.get("/sessions/{sid}/turns/{tid}/{kind}.wav")
    async def sound(sid: UUID, tid: UUID, kind: Literal["learner", "patient"], request: Request):
        await document(request, sid)
        data = await app.state.coordinator.store.call("read", sid, f"{tid}-{kind}.wav")
        return Response(data, media_type="audio/wav")

    @app.websocket("/sessions/{sid}/video")
    async def video(sid: UUID, ws: WebSocket):
        c = app.state.coordinator
        owns = False
        entry = None
        try:
            if (
                ws.headers.get("origin") is not None
                or ws.scope.get("query_string")
                or (
                    ws.url.scheme != "wss"
                    and (not ws.client or not ipaddress.ip_address(ws.client.host).is_loopback)
                )
            ):
                raise ValueError()
            claims = grants.verify(ws.headers.get("authorization"), {"device"}, sid)
            c.same(claims)
            c.guard()
            if c.video_active or c.data["video"]:
                raise ValueError("one_capture_per_session")
            c.video_active = owns = True
            await ws.accept()
            raw = await asyncio.wait_for(ws.receive_text(), 5)
            if len(raw) > 2048:
                raise ValueError()
            start = json.loads(raw)
            limits = claims["limits"]
            if start.get("type") != "start" or any(
                type(start.get(k)) is not int or not lo <= start[k] <= limits[hi]
                for k, lo, hi in [
                    ("width", 16, "max_width"),
                    ("height", 16, "max_height"),
                    ("fps", 1, "max_fps"),
                ]
            ):
                raise ValueError("video_limit")
            offset = start.pop("offset_ms", 0)
            if not isinstance(offset, (float, int)) or not 0 <= offset <= claims["duration_seconds"] * 1000:
                raise ValueError("video_clock")
            # Server supplies correlation; untrusted device cannot attach another session.
            start.update(
                capture_id=str(sid),
                capture_start_unix_ms=c.data["anchor_unix_ms"],
                retention_hours=limits["media_retention_hours"],
            )
            async with connect(
                s.video_url,
                additional_headers={"Authorization": "Bearer " + s.video_token.get_secret_value()},
                proxy=None,
                compression=None,
                max_size=65536,
                open_timeout=5,
                close_timeout=2,
            ) as upstream:
                await upstream.send(json.dumps(start))
                ready = json.loads(await asyncio.wait_for(upstream.recv(), 5))
                if ready.get("type") != "ready":
                    raise ValueError()
                entry = {"id": str(UUID(ready["recording_id"])), "status": "pending", "start_ms": offset}
                c.data["video"].append(entry)
                await c.save()
                await ws.send_json(ready)
                # Bounded application acknowledgment; independent audio connection stays responsive.
                count = 0
                while True:
                    message = await asyncio.wait_for(ws.receive(), 5)
                    if message.get("bytes") is not None:
                        c.guard()
                        data = message["bytes"]
                        if not 20 < len(data) <= min(524288, ready["max_frame_bytes"]) + 20:
                            raise ValueError()
                        magic, sequence, timestamp = struct.unpack("!4sQQ", data[:20])
                        if (
                            magic != b"VPF1"
                            or sequence != count
                            or timestamp > claims["duration_seconds"] * 1_000_000
                            or count >= limits["max_fps"] * claims["duration_seconds"]
                        ):
                            raise ValueError()
                        count += 1
                        await asyncio.wait_for(upstream.send(data), 5)
                        event = json.loads(await asyncio.wait_for(upstream.recv(), 5))
                        if event.get("type") != "accepted" or event.get("sequence") != sequence:
                            raise ValueError()
                        await asyncio.wait_for(ws.send_json(event), 5)
                    elif message.get("text") == '{"type":"stop"}':
                        await upstream.send(message["text"])
                        receipt = json.loads(await asyncio.wait_for(upstream.recv(), 10))
                        if receipt.get("type") != "complete" or receipt.get("recording_id") != entry["id"]:
                            raise ValueError()
                        entry.update(status=receipt["recording"]["status"], receipt=receipt["recording"])
                        if entry["status"] != "saved":
                            c.data["recording_status"] = "incomplete"
                        elif c.data["recording_status"] != "incomplete":
                            c.data["recording_status"] = "saved"
                        await c.save()
                        await ws.send_json(receipt)
                        return
                    else:
                        raise ValueError()
        except Exception:
            if owns:
                if entry:
                    entry["status"] = "incomplete"
                c.data["recording_status"] = "incomplete"
                try:
                    await c.save()
                except Exception:
                    pass
            try:
                await ws.close(1008)
            except Exception:
                pass
        finally:
            if owns:
                c.video_active = False

    @app.post("/sessions/{sid}/prepare-replay")
    async def prepare(sid: UUID, request: Request):
        data = await document(request, sid, {"read", "control"})
        c = app.state.coordinator
        if c.data and c.data["status"] in {"warming", "active"}:
            raise HTTPException(409, "finish_active_session_before_bulk_export")
        if data.get("replay_frames") is not None:
            return data
        result = await c.store.call("prepare", json.loads(json.dumps(data)), s.video_store, s.video_client_id)
        if c.data and c.data["id"] == str(sid):
            c.data = result
        return result

    @app.get("/sessions/{sid}/frames/{index}.jpg")
    async def frame(sid: UUID, index: int, request: Request):
        data = await document(request, sid, {"read", "control"})
        frames = data.get("replay_frames", [])
        if not 0 <= index < len(frames):
            raise HTTPException(404, "frame_not_found")
        content = await app.state.coordinator.store.call("read", sid, f"frame-{index:06d}.jpg")
        return Response(content, media_type="image/jpeg")

    @app.get("/sessions/{sid}/video/{rid}")
    async def video_manifest(sid: UUID, rid: UUID, request: Request):
        data = await document(request, sid, {"read", "control"})
        return await app.state.coordinator.store.call(
            "video", data, s.video_store, s.video_client_id, str(rid)
        )

    @app.get("/sessions/{sid}/video/{rid}/{index}.mkv")
    async def segment(sid: UUID, rid: UUID, index: int, request: Request):
        data = await document(request, sid, {"read", "control"})
        content = await app.state.coordinator.store.call(
            "video", data, s.video_store, s.video_client_id, str(rid), index
        )
        return Response(
            content,
            media_type="video/x-matroska",
            headers={"Content-Disposition": f'attachment; filename="{rid}-{index}.mkv"'},
        )

    return app
