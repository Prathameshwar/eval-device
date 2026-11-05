"""Independent bounded media connections; no reconnect/resume after a partial utterance."""

import asyncio
import json
import struct
import time

import httpx

from .connection import ConnectionError

HEADER = struct.Struct("!IQ")


async def transmit(connection, kind, metadata, frames):
    from websockets.asyncio.client import connect

    path = "/v1/stream/" + kind
    raw, body = connection.request_body("GET", path, metadata)
    try:
        async with asyncio.timeout(connection.timeout):
            async with httpx.AsyncClient(
                trust_env=False,
                follow_redirects=False,
                timeout=10,
                verify=connection.verify,
                transport=connection.async_transport,
            ) as client:
                headers = await connection.async_grant(client, body)
            connection.note(body["request_id"], "unknown")
            async with connect(
                connection.root.replace("https://", "wss://", 1) + path,
                ssl=connection.verify,
                additional_headers=headers,
                proxy=None,
                open_timeout=10,
                close_timeout=2,
                max_size=65536,
                max_queue=4,
            ) as socket:
                await socket.send(raw.decode())
                ready = json.loads(await socket.recv())
                if ready != {"type": "ready", "request_id": body["request_id"], "window": 1}:
                    raise ValueError()
                sequence, total, last_stamp = 0, 0, -1
                async for frame in frames:
                    total += len(frame)
                    if (
                        not frame
                        or len(frame) > (3200 if kind == "audio" else 1000000)
                        or total > (960000 if kind == "audio" else 32000000)
                        or sequence >= (600 if kind == "audio" else 900)
                    ):
                        raise ValueError()
                    # Some supported hosts have a coarse monotonic clock. Sequence
                    # timestamps must remain strictly increasing even within one tick.
                    last_stamp = max(last_stamp + 1, time.perf_counter_ns() // 1000)
                    await socket.send(HEADER.pack(sequence, last_stamp) + frame)
                    async with asyncio.timeout(5):
                        ack = json.loads(await socket.recv())
                    if ack != {"type": "ack", "sequence": sequence}:
                        raise ValueError()
                    sequence += 1
                await socket.send('{"type":"end"}')
                value = json.loads(await socket.recv())
                if value.get("type") != "done" or not isinstance(value.get("result"), dict):
                    raise ValueError()
                connection.note(body["request_id"], "completed")
                return value["result"]
    except asyncio.CancelledError:
        raise
    except Exception:
        raise ConnectionError("Media stream ended; partial capture was not replayed") from None
    finally:
        await frames.aclose()


async def audio(connection, pcm, model, language):
    if not pcm or len(pcm) % 2 or len(pcm) > 960000:
        raise ConnectionError("Invalid utterance", "input", 422)

    async def chunks():
        for offset in range(0, len(pcm), 3200):
            yield pcm[offset : offset + 3200]

    return await transmit(connection, "audio", {"model": model, "language": language}, chunks())


async def audio_frames(connection, frames, model, language, *, max_seconds=30):
    """Transmit while capturing. Only a clean iterator end permits ASR submission."""
    from .audio import validate_transcript

    async def bounded():
        total = 0
        try:
            async for frame in frames:
                if not isinstance(frame, bytes) or not frame or len(frame) % 2:
                    raise ConnectionError("Invalid audio frame", "input", 422)
                total += len(frame)
                if total > min(30, max_seconds) * 32000:
                    raise ConnectionError("Utterance exceeds its duration limit", "input", 422)
                for start in range(0, len(frame), 3200):
                    yield frame[start : start + 3200]
        finally:
            await frames.aclose()

    result = await transmit(connection, "audio", {"model": model, "language": language}, bounded())
    return validate_transcript(result, language)
