"""Adapters for the existing independent audio and video services."""

import asyncio
import io
import json
import wave

import httpx
from websockets.asyncio.client import connect


def wav(pcm):
    out = io.BytesIO()
    with wave.open(out, "wb") as f:
        f.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        f.writeframes(pcm)
    return out.getvalue()


class Transcriber:
    def __init__(self, settings):
        self.settings = settings

    async def check(self):
        url = self.settings.audio_url.replace("ws://", "http://").split("/v1/")[0] + "/v1/status"
        async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=5) as client:
            response = await client.get(
                url, headers={"Authorization": "Bearer " + self.settings.audio_token.get_secret_value()}
            )
            response.raise_for_status()
            state = response.json()
            if (
                not state.get("ready")
                or state.get("console_output")
                or state.get("callback_configured")
                or state.get("recording", {}).get("enabled")
            ):
                raise ValueError("training_requires_ready_private_audio_profile")

    async def transcribe(self, chunks, language, guard, collected):
        s = self.settings
        async with connect(
            s.audio_url,
            additional_headers={"Authorization": "Bearer " + s.audio_token.get_secret_value()},
            proxy=None,
            compression=None,
            max_size=65536,
            open_timeout=5,
            close_timeout=2,
        ) as ws:
            await ws.send(json.dumps({"type": "start", "language": language}))
            ready = json.loads(await asyncio.wait_for(ws.recv(), 5))
            if ready.get("type") != "ready" or not 2 <= ready.get("max_frame_bytes", 0) <= 32000:
                raise ValueError("audio_not_ready")
            text = []
            complete = None
            finished = False

            async def produce():
                nonlocal finished
                carry = b""
                async for chunk in chunks:
                    guard()
                    collected.extend(chunk)
                    if len(collected) > 960000:
                        raise ValueError("audio_limit")
                    merged = carry + chunk
                    even = len(merged) - len(merged) % 2
                    chunk, carry = merged[:even], merged[even:]
                    for i in range(0, len(chunk), ready["max_frame_bytes"]):
                        await asyncio.wait_for(ws.send(chunk[i : i + ready["max_frame_bytes"]]), 5)
                if carry:
                    raise ValueError("incomplete_pcm_sample")
                finished = True
                await ws.send('{"type":"finish"}')

            async def consume():
                nonlocal complete
                async for raw in ws:
                    guard()
                    event = json.loads(raw)
                    if event.get("type") == "transcript":
                        text.append(event["text"])
                        if sum(map(len, text)) > 4000:
                            raise ValueError("transcript_limit")
                    elif event.get("type") == "error":
                        raise ValueError("transcription_failed")
                    elif event.get("type") == "complete":
                        if not finished or event.get("session_id") != ready["session_id"]:
                            raise ValueError("invalid_audio_receipt")
                        complete = event
                        return
                raise ValueError("missing_audio_receipt")

            async with asyncio.TaskGroup() as group:
                group.create_task(produce())
                group.create_task(consume())
            if not complete:
                raise ValueError("missing_audio_receipt")
            return " ".join(text).strip(), ready["session_id"], complete.get("recording", {})
