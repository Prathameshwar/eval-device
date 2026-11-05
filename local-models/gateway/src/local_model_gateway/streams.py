"""Bounded independent WSS streams. ASR starts only after an explicit complete utterance."""

import asyncio
import json
import struct
import time

from local_model_client.audio import encode
from starlette.websockets import WebSocketDisconnect

from .security import Rejected

HEADER = struct.Struct("!IQ")  # sequence, monotonic timestamp in microseconds


class Frames:
    def __init__(self, kind):
        if kind not in {"audio", "video"}:
            raise Rejected("input", 422)
        self.kind = kind
        self.sequence = 0
        self.last_stamp = -1
        self.total = 0
        self.pcm = bytearray()

    def accept(self, raw):
        if not isinstance(raw, bytes) or len(raw) < HEADER.size:
            raise Rejected("input", 422)
        sequence, stamp = HEADER.unpack(raw[: HEADER.size])
        payload = raw[HEADER.size :]
        if sequence != self.sequence or stamp <= self.last_stamp:
            raise Rejected("sequence", 409)
        if self.kind == "audio":
            if not 0 < len(payload) <= 3200 or len(payload) % 2:
                raise Rejected("input", 422)
            maximum = 960000
        else:
            if (
                not 4 <= len(payload) <= 1000000
                or not payload.startswith(b"\xff\xd8")
                or not payload.endswith(b"\xff\xd9")
            ):
                raise Rejected("input", 422)
            maximum = 32000000
        if self.total + len(payload) > maximum or self.sequence >= (600 if self.kind == "audio" else 900):
            raise Rejected("input", 413)
        self.total += len(payload)
        self.last_stamp = stamp
        self.sequence += 1
        if self.kind == "audio":
            self.pcm.extend(payload)
        return sequence, payload


async def receive(socket, kind, grants, receipts, slots, forward, validate_payload):
    acquired = False
    claims = None
    try:
        if socket.url.scheme != "wss" or socket.headers.get("origin") or socket.headers.get("cookie"):
            raise Rejected()
        if slots.locked():
            raise Rejected("capacity", 429)
        await slots.acquire()
        acquired = True
        await socket.accept()
        async with asyncio.timeout(5):
            raw = await socket.receive_text()
        if len(raw.encode()) > 4096:
            raise Rejected("input", 413)
        claims = grants.verify(
            socket.headers.get("authorization", ""), "GET", "/v1/stream/" + kind, raw.encode()
        )
        payload = json.loads(raw)
        validate_payload(claims, payload)
        frames = Frames(kind)
        analysis = None
        if kind == "video" and claims.get("video_operation") == "video.motion":
            from .video import Motion

            analysis = Motion()
        receipts.claim(claims)
        await socket.send_json({"type": "ready", "request_id": claims["jti"], "window": 1})
        first_stamp = None
        async with asyncio.timeout(min(35, claims["deadline"] - time.time())):
            while True:
                async with asyncio.timeout(5):
                    message = await socket.receive()
                if message["type"] == "websocket.disconnect":
                    return
                if message.get("text") is not None:
                    if message["text"] != '{"type":"end"}' or not frames.total:
                        raise Rejected("input", 422)
                    break
                sequence, frame = frames.accept(message.get("bytes"))
                if kind == "audio" and frames.total > 32000 * claims.get("max_audio_seconds", 0):
                    raise Rejected("input", 413)
                if kind == "video":
                    first_stamp = frames.last_stamp if first_stamp is None else first_stamp
                    seconds = claims.get("max_video_seconds", 30)
                    if frames.sequence > seconds * 5 or frames.last_stamp - first_stamp > seconds * 1000000:
                        raise Rejected("input", 413)
                    if analysis:
                        await asyncio.to_thread(analysis.accept, frame)
                await socket.send_json({"type": "ack", "sequence": sequence})
        if kind == "audio":
            result = await forward(
                claims,
                "POST",
                "/v1/infer/asr",
                {
                    "model": payload["model"],
                    "language": payload["language"],
                    "wav_base64": encode(bytes(frames.pcm)),
                },
            )
        elif analysis:
            result = analysis.result()
        else:
            result = {"frames": frames.sequence, "bytes": frames.total, "inference": "unsupported"}
        receipts.finish(claims["jti"], "completed")
        await socket.send_json({"type": "done", "result": result})
    except asyncio.CancelledError:
        raise
    except Exception:
        # Keep an uncertain receipt; never expose upstream exception messages to service logs.
        pass
    finally:
        if acquired:
            slots.release()
        try:
            await socket.close(code=1000 if claims else 1008)
        except (RuntimeError, WebSocketDisconnect):
            pass
