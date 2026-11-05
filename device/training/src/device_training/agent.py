import argparse
import asyncio
import json
import ssl
import struct
import time
import wave
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from websockets.asyncio.client import connect

from .auth import Grants
from .config import endpoint
from .hardware import camera, microphone, speaker


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PI_", env_file=".env.agent", extra="ignore", hide_input_in_errors=True
    )
    platform_url: str
    laptop_url: str
    credential: SecretStr
    public_key_file: Path
    organization_id: UUID
    device_id: UUID
    ca_file: Path | None = None
    input_device: str | None = None
    output_device: str | None = None
    camera_executable: str = "rpicam-vid"

    @model_validator(mode="after")
    def validate_urls(self):
        self.platform_url = endpoint(self.platform_url, {"https", "http"})
        self.laptop_url = endpoint(self.laptop_url, {"https", "http"})
        return self


class Agent:
    def __init__(self, settings, fixture_audio=None, fixture_jpeg=None):
        self.s = settings
        self.grants = Grants(settings)
        self.fixture_audio, self.fixture_jpeg = fixture_audio, fixture_jpeg
        self.token = ""
        self.claims: dict[str, Any] = {}
        self.stop = asyncio.Event()
        self.anchor = 0.0
        self.context = ssl.create_default_context(cafile=str(settings.ca_file) if settings.ca_file else None)
        self.client = httpx.AsyncClient(
            verify=self.context,
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(60, connect=5, write=5, pool=5),
        )
        self.last_state = None

    def guard(self):
        if (
            self.stop.is_set()
            or not self.claims
            or time.time() >= self.claims["exp"]
            or time.monotonic() - self.anchor >= self.claims["duration_seconds"]
        ):
            raise RuntimeError("authorization_ended")

    def offset(self):
        return (time.monotonic() - self.anchor) * 1000

    async def request(self, method, path, *, platform=False, retry=False, **kwargs):
        token = self.s.credential.get_secret_value() if platform else self.token
        url = (self.s.platform_url + "/api/v1" if platform else self.s.laptop_url) + path
        for attempt in range(3 if retry else 1):
            try:
                async with self.client.stream(
                    method,
                    url,
                    headers={"Authorization": "Bearer " + token, **kwargs.pop("headers", {})},
                    **kwargs,
                ) as response:
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > 4_000_000:
                            raise ValueError("response_limit")
                    response.raise_for_status()
                    return (
                        bytes(body)
                        if response.headers.get("content-type", "").startswith("audio/")
                        else json.loads(body)
                    )
            except (httpx.TransportError, httpx.HTTPStatusError) as error:
                if (
                    not retry
                    or attempt == 2
                    or (isinstance(error, httpx.HTTPStatusError) and error.response.status_code < 500)
                ):
                    raise RuntimeError("request_failed_or_outcome_unknown") from None
                await asyncio.sleep(0.2 * 2**attempt)
        raise RuntimeError("request_failed")

    async def renew(self, sid):
        while not self.stop.is_set():
            await asyncio.sleep(8)
            try:
                lease = await self.request(
                    "POST", f"/device/training/sessions/{sid}/lease", platform=True, retry=True
                )
                claims = self.grants.verify("Bearer " + lease["grant"], {"device"}, sid)
                self.token, self.claims = lease["grant"], claims
                await self.request("POST", f"/sessions/{sid}/lease", retry=True)
            except Exception:
                self.stop.set()
                return

    async def capture(self):
        if self.fixture_audio:
            with wave.open(str(self.fixture_audio), "rb") as source:
                if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, 16000):
                    raise ValueError("fixture_must_be_16khz_mono_pcm16")
                while block := source.readframes(320):
                    self.guard()
                    yield block
                    await asyncio.sleep(0.02)
        else:
            source = microphone(
                self.claims["limits"]["max_audio_turn_seconds"], self.guard, self.s.input_device
            )
            try:
                async for block in source:
                    yield block
            finally:
                await source.aclose()

    async def play(self, sid, row):
        tid = row["id"]

        async def ack(event):
            return await self.request(
                "POST",
                f"/sessions/{sid}/turns/{tid}/playback",
                json={"event": event, "offset_ms": self.offset()},
            )

        await ack("claim")
        sound = await self.request("GET", f"/sessions/{sid}/turns/{tid}/patient.wav")
        self.guard()
        if self.fixture_audio:
            # Fixture mode records simulation explicitly; never claims physical playback.
            await ack("started")
            await asyncio.sleep(0.05)
        else:
            await speaker(sound, self.guard, lambda: ack("started"), self.s.output_device)
        await ack("finished")

    async def video(self, sid):
        limits = self.claims["limits"]
        width, height, fps = (
            min(640, limits["max_width"]),
            min(480, limits["max_height"]),
            min(10, limits["max_fps"]),
        )

        async def frames():
            if self.fixture_jpeg:
                jpeg = self.fixture_jpeg.read_bytes()
                while not self.stop.is_set():
                    yield jpeg, time.monotonic()
                    await asyncio.sleep(1 / fps)
            else:
                async for frame in camera(width, height, fps, self.stop, self.s.camera_executable):
                    yield frame

        source = frames()
        try:
            first, base = await anext(source)
            url = (
                self.s.laptop_url.replace("https://", "wss://").replace("http://", "ws://")
                + f"/sessions/{sid}/video"
            )
            async with connect(
                url,
                ssl=self.context if url.startswith("wss:") else None,
                additional_headers={"Authorization": "Bearer " + self.token},
                proxy=None,
                compression=None,
                max_size=65536,
                open_timeout=5,
                close_timeout=2,
            ) as ws:
                start = {
                    "type": "start",
                    "version": 1,
                    "format": "jpeg",
                    "width": width,
                    "height": height,
                    "fps": fps,
                    "offset_ms": (base - self.anchor) * 1000,
                }
                await ws.send(json.dumps(start))
                ready = json.loads(await asyncio.wait_for(ws.recv(), 5))
                if ready.get("type") != "ready":
                    raise RuntimeError("video_not_ready")
                slots = asyncio.Semaphore(4)
                pending: asyncio.Queue[tuple[int, int]] = asyncio.Queue(maxsize=4)
                finished = asyncio.Event()

                async def produce():
                    index = 0
                    frame, stamp = first, base
                    while not self.stop.is_set():
                        self.guard()
                        if len(frame) > ready["max_frame_bytes"]:
                            raise RuntimeError("frame_too_large")
                        await asyncio.wait_for(slots.acquire(), 3)
                        timestamp = 0 if index == 0 else int((stamp - base) * 1e6)
                        await pending.put((index, timestamp))
                        await asyncio.wait_for(
                            ws.send(struct.pack("!4sQQ", b"VPF1", index, timestamp) + frame), 3
                        )
                        index += 1
                        try:
                            frame, stamp = await anext(source)
                        except StopAsyncIteration:
                            break
                    finished.set()
                    await ws.send('{"type":"stop"}')

                async def consume():
                    while True:
                        event = json.loads(await asyncio.wait_for(ws.recv(), 6))
                        if event.get("type") == "accepted":
                            expected = await asyncio.wait_for(pending.get(), 1)
                            if (event.get("sequence"), event.get("timestamp_us")) != expected:
                                raise RuntimeError("invalid_video_ack")
                            slots.release()
                        elif (
                            event.get("type") == "complete"
                            and finished.is_set()
                            and pending.empty()
                            and event.get("recording_id") == ready["recording_id"]
                        ):
                            return
                        else:
                            raise RuntimeError("invalid_video_receipt")

                async with asyncio.TaskGroup() as group:
                    group.create_task(produce())
                    group.create_task(consume())
        finally:
            await source.aclose()

    async def monitor(self, sid):
        while not self.stop.is_set():
            try:
                async with asyncio.timeout(2):
                    state = await self.request("GET", f"/sessions/{sid}")
                self.last_state = state
                if state["status"] not in {"warming", "active"}:
                    self.stop.set()
                    return
            except Exception:
                self.stop.set()
                return
            await asyncio.sleep(0.5)

    async def record_video(self, sid):
        try:
            await self.video(sid)
        except Exception:
            try:
                await self.request("POST", f"/sessions/{sid}/recording-failure")
            except Exception:
                pass

    async def run_session(self, row):
        sid = row["id"]
        self.stop.clear()
        self.anchor = time.monotonic()
        lease = await self.request(
            "POST", f"/device/training/sessions/{sid}/lease", platform=True, retry=True
        )
        self.token = lease["grant"]
        self.claims = self.grants.verify("Bearer " + self.token, {"device"}, sid)
        self.last_state = await self.request(
            "POST",
            f"/sessions/{sid}/start",
            json={
                "scenario": lease["scenario"],
                "anchor_unix_ms": int(time.time() * 1000),
                "simulated": bool(self.fixture_audio),
            },
        )
        renewal = asyncio.create_task(self.renew(sid))
        monitor = asyncio.create_task(self.monitor(sid))
        video = asyncio.create_task(self.record_video(sid))
        completed = False
        try:
            count = 0
            while not self.stop.is_set():
                self.guard()
                state = await self.request("GET", f"/sessions/{sid}", retry=True)
                self.last_state = state
                if state["status"] not in {"warming", "active"}:
                    break
                if state["status"] == "warming":
                    await asyncio.sleep(0.3)
                    continue
                pending = next((t for t in state["turns"] if t["playback"] == "ready"), None)
                if pending:
                    await self.play(sid, pending)
                elif count < self.claims["limits"]["max_turns"] - 1:
                    if self.fixture_audio and count:
                        completed = True
                        break
                    source = self.capture()
                    try:
                        await self.request(
                            "POST",
                            f"/sessions/{sid}/turns/{uuid4()}",
                            headers={
                                "Content-Type": "application/octet-stream",
                                "X-Capture-Offset-Ms": str(self.offset()),
                            },
                            content=source,
                        )
                    finally:
                        await source.aclose()
                    count += 1
                else:
                    completed = True
                    break
        finally:
            self.stop.set()
            renewal.cancel()
            monitor.cancel()
            await asyncio.gather(renewal, monitor, return_exceptions=True)
            try:
                await asyncio.wait_for(video, 8)
            except Exception:
                pass
            try:
                self.last_state = await self.request(
                    "POST",
                    f"/sessions/{sid}/stop",
                    json={"status": "completed" if completed else "cancelled"},
                )
            except Exception:
                pass
            state = self.last_state
            if state:
                result = {
                    "event_id": state["result_event_id"],
                    "status": state["status"]
                    if state["status"] in {"completed", "failed", "cancelled"}
                    else "failed",
                    "turns": len(state["turns"]),
                    "audio_recordings": [],
                    "video_recordings": [v["id"] for v in state["video"]],
                    "recording_status": "saved" if state["recording_status"] == "saved" else "incomplete",
                    "simulated": state["simulated"],
                    "reason": state["reason"]
                    if state["status"] in {"completed", "failed", "cancelled"}
                    else "connection_lost",
                }
                synced = "unknown"
                try:
                    await self.request(
                        "POST",
                        f"/device/training/sessions/{sid}/result",
                        platform=True,
                        retry=True,
                        json=result,
                    )
                    synced = "saved"
                except Exception:
                    pass
                try:
                    await self.request("POST", f"/sessions/{sid}/sync", json={"status": synced})
                except Exception:
                    pass

    async def run(self):
        try:
            while True:
                row = await self.request("GET", "/device/training/next", platform=True, retry=True)
                if row["session"]:
                    await self.run_session(row["session"])
                else:
                    await asyncio.sleep(2)
        finally:
            await self.client.aclose()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check configured audio devices and camera executable without recording",
    )
    parser.add_argument("--fixture-audio", type=Path)
    parser.add_argument("--fixture-jpeg", type=Path)
    args = parser.parse_args()
    if bool(args.fixture_audio) != bool(args.fixture_jpeg):
        parser.error("fixture mode needs both WAV and JPEG")
    try:
        settings = AgentSettings()
        if args.check:
            import shutil

            import sounddevice as sd

            Grants(settings)
            sd.check_input_settings(device=settings.input_device, channels=1, dtype="int16", samplerate=16000)
            sd.check_output_settings(
                device=settings.output_device, channels=1, dtype="int16", samplerate=22050
            )
            if not shutil.which(settings.camera_executable):
                raise ValueError("camera_executable_missing")
            print(
                "Configured audio formats and camera executable are available. Camera capture, Wi-Fi and audible playback still require a session test."
            )
            return
        asyncio.run(Agent(settings, args.fixture_audio, args.fixture_jpeg).run())
    except KeyboardInterrupt:
        pass
    except Exception:
        parser.exit(
            1,
            "Agent stopped; inspect session status before restarting. Credentials and media are not logged.\n",
        )
