"""Bounded device video processing using existing platform run/accounting contracts."""

import asyncio
import io
import json
from contextlib import suppress
from uuid import UUID, uuid4

import httpx
from training_contracts.media import jpeg_dimensions

from .cloud_speech import Journal
from .media import media_url
from .pms_client import ClientError
from .telemetry import heartbeat


def result_view(value):
    result = value.get("result")
    if len(json.dumps(result).encode()) > 24000:
        result = {"available_on_platform": True}
    return {"run_id": value["id"], "status": value["status"], "result": result}


class BoundedBuffer(io.BytesIO):
    def __init__(self, maximum):
        super().__init__()
        self.maximum = maximum

    def write(self, data):
        if self.tell() + len(data) > self.maximum:
            raise ClientError("Video clip exceeded its upload budget", code="video_size")
        return super().write(data)


async def encode_clip(frames, *, seconds, maximum):
    """Encode video only; source owns capture and its separate full-quality archive."""
    import av

    output = BoundedBuffer(maximum)
    count = 0
    with av.open(output, mode="w", format="mp4") as container:
        stream = container.add_stream("libx264", rate=5)
        stream.width, stream.height, stream.pix_fmt = 200, 150, "yuv420p"
        stream.options = {"preset": "ultrafast", "crf": "28"}
        try:
            async for jpeg in frames:
                count += 1
                if count > seconds * 5 or len(jpeg) > 1000000:
                    raise ClientError("Video clip exceeded its capture budget", code="video_size")
                jpeg_dimensions(jpeg)
                with av.open(io.BytesIO(jpeg), format="mjpeg") as image:
                    frame = next(image.decode(video=0))
                frame = frame.reformat(width=200, height=150, format="yuv420p")
                frame.pts = None
                for packet in stream.encode(frame):
                    container.mux(packet)
            for packet in stream.encode():
                container.mux(packet)
        finally:
            await frames.aclose()
    if count < 2:
        raise ClientError("Not enough camera frames", code="camera_unavailable")
    return output.getvalue(), count / 5


class VideoProcessing:
    def __init__(self, settings, pms, inference, *, transport=None):
        self.settings, self.pms, self.inference = settings, pms, inference
        self.transport = transport
        self.last = None
        self.journal = Journal(settings.app_root / "processing")

    async def note(self, key, state, run=None):
        await asyncio.to_thread(self.journal.write, key, state, run)
        self.last = {"request_key": key, "run_id": run, "state": state}

    async def prepare(self):
        config = await self.pms.json("GET", "/api/v1/device/config")
        section = config["settings"]["video"]
        mode = section.get("execution_mode", section.get("mode"))
        if not section.get("enabled") or (mode, section.get("operation"), section.get("engine")) not in {
            ("local", "video.motion", "opencv_motion"),
            ("cloud", "video.labels", "aws_rekognition"),
            ("cloud", "video.labels", "azure_video_indexer"),
        }:
            raise ClientError("No supported video operation is assigned", code="video_unsupported")
        if mode == "local" and not getattr(self.inference, "remote", False):
            raise ClientError("Video processing requires a remote host", code="inference_not_configured")
        capabilities = None
        if mode == "local":
            available = await self.inference.async_request("GET", "/v1/capabilities")
            if "video.motion" not in available.get("media", {}).get("video_operations", []):
                raise ClientError("Remote host has no motion processor", code="video_unsupported")
            capabilities = {"engines": ["opencv_motion"]}
        await self.pms.json(
            "POST", "/api/v1/device/heartbeat", json=heartbeat(config, capabilities=capabilities)
        )
        return config, section, mode

    async def execute(self, frames, seconds):
        self.last = None
        try:
            async with asyncio.timeout(180):
                return await self._execute(frames, seconds)
        except BaseException:
            if self.last and self.last["run_id"] and self.last["state"] == "submitted":
                with suppress(Exception):
                    async with asyncio.timeout(3):
                        observed = await self.pms.json(
                            "POST", f"/api/v1/device/runs/{self.last['run_id']}/cancel", json={}
                        )
                        await self.note(self.last["request_key"], observed["status"], self.last["run_id"])
            raise
        finally:
            await frames.aclose()

    async def _execute(self, frames, seconds):
        config, section, mode = await self.prepare()
        policy = config["policy"]["capture_limits"]
        seconds = min(seconds, 30, policy["max_video_seconds"], section.get("clip_seconds") or 30)
        source = frames

        async def bounded():
            count = 0
            try:
                async for frame in source:
                    yield frame
                    count += 1
                    if count >= seconds * 5:
                        break
            finally:
                await source.aclose()

        frames = bounded()
        clip = None
        if mode == "cloud":
            clip, seconds = await encode_clip(
                frames, seconds=seconds, maximum=min(8000000, policy["max_upload_bytes"])
            )
        key = str(uuid4())
        body = {
            "request_key": key,
            "operation": section["operation"],
            "profile_revision_id": config["profile_revision_id"],
            "duration_seconds": seconds,
        }
        if clip is not None:
            body["media_format"] = "mp4"
        await self.note(key, "unknown")
        response = await self.pms.json("POST", "/api/v1/device/runs", json=body, expected=202)
        run = response["run"]
        identity = str(UUID(run["id"]))
        await self.note(key, "submitted", identity)
        if mode == "local":
            from local_model_client.streams import transmit

            result = await transmit(
                self.inference,
                "video",
                {
                    "format": "jpeg",
                    "model": "opencv_motion",
                    "processing_run_id": identity,
                    "max_seconds": seconds,
                },
                frames,
            )
            run = await self.pms.json(
                "POST",
                f"/api/v1/device/runs/{identity}/result",
                json={"status": "succeeded", "result": result},
            )
        else:
            access = await self.pms.json(
                "POST", f"/api/v1/device/runs/{identity}/media/0/access", params={"method": "PUT"}
            )
            address = media_url(access["url"], self.settings.pms_url)
            # Separate client: device authentication must never be sent to object storage.
            async with httpx.AsyncClient(
                transport=self.transport, trust_env=False, follow_redirects=False, timeout=30
            ) as http:
                async with http.stream(
                    "PUT", address, content=clip, headers={"Content-Type": "video/mp4"}
                ) as uploaded:
                    if uploaded.status_code not in {200, 201, 204}:
                        raise ClientError("Video upload did not complete", code="upload_unknown")
            run = await self.pms.json("POST", f"/api/v1/device/runs/{identity}/upload-complete", json={})
            while run["status"] not in {"succeeded", "failed", "cancelled", "expired", "unknown"}:
                await asyncio.sleep(0.5)
                run = await self.pms.json("GET", f"/api/v1/device/runs/{identity}")
        await self.note(key, run["status"], identity)
        return result_view(run)

    async def status(self, identity):
        identity = str(UUID(identity))
        value = await self.pms.json("GET", f"/api/v1/device/runs/{identity}")
        # Status inspection never starts/retries processing or playback.
        return result_view(value)
