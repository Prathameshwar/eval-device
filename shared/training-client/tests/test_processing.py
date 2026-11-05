import asyncio
import io
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import av
import httpx
import pytest

from training_client.config import Settings
from training_client.processing import BoundedBuffer, VideoProcessing, encode_clip, media_url


def jpeg(color=0):
    import cv2
    import numpy as np

    return cv2.imencode(".jpg", np.full((150, 200, 3), color, np.uint8))[1].tobytes()


async def frames():
    yield jpeg()
    yield jpeg(255)


async def test_encoded_clip_is_bounded_video_without_audio():
    clip, duration = await encode_clip(frames(), seconds=1, maximum=100000)
    with av.open(io.BytesIO(clip)) as decoded:
        assert len(decoded.streams.video) == 1 and not decoded.streams.audio
        assert sum(1 for _ in decoded.decode(video=0)) == 2
    assert duration == 0.4
    with pytest.raises(av.error.FFmpegError):  # PyAV wraps the bounded sink's exception.
        await encode_clip(frames(), seconds=1, maximum=100)
    output = BoundedBuffer(3)
    with pytest.raises(Exception, match="budget"):
        output.write(b"1234")


@pytest.mark.parametrize(
    "address",
    ["http://storage.test/media", "https://user:secret@storage.test/media", "http://127.0.0.1:9001/media"],
)
def test_private_upload_url_rejects_unsafe_addresses(address):
    with pytest.raises(Exception, match="address"):
        media_url(address, "http://127.0.0.1:8000")


def processor(tmp_path, mode="local"):
    identity = str(uuid4())
    config = {
        "settings": {
            "video": {
                "enabled": True,
                "execution_mode": mode,
                "clip_seconds": 10,
                "operation": "video.motion" if mode == "local" else "video.labels",
                "engine": "opencv_motion" if mode == "local" else "aws_rekognition",
            }
        },
        "profile_revision_id": str(uuid4()),
        "configuration_hash": "a" * 64,
        "policy": {"capture_limits": {"max_video_seconds": 30, "max_upload_bytes": 8000000}},
    }
    calls = []

    async def call(method, path, **kwargs):
        calls.append((method, path, kwargs))
        if path.endswith("/config"):
            return config
        if path.endswith("/heartbeat"):
            return {}
        if path.endswith("/runs"):
            return {
                "run": {"id": identity, "status": "awaiting_device" if mode == "local" else "awaiting_upload"}
            }
        if path.endswith("/access"):
            return {"url": "https://storage.test/clip?secret=hidden"}
        if path.endswith("/cancel"):
            return {"id": identity, "status": "cancelled"}
        return {"id": identity, "status": "succeeded", "result": {"observation": "fixture"}}

    pms = SimpleNamespace(json=AsyncMock(side_effect=call))
    inference = SimpleNamespace(
        remote=True, async_request=AsyncMock(return_value={"media": {"video_operations": ["video.motion"]}})
    )
    settings = Settings(app_root=tmp_path, pms_url="https://platform.test", pms_token="dev_secret")
    return VideoProcessing(settings, pms, inference), calls, identity


async def test_local_processing_reserves_run_then_sends_frames_once(tmp_path, monkeypatch):
    client, calls, identity = processor(tmp_path)

    async def transmit(connection, kind, metadata, source):
        assert kind == "video" and metadata["processing_run_id"] == identity
        assert calls[-1][1].endswith("/runs")
        assert len([frame async for frame in source]) == 2
        return {"motion_detected": True}

    mock = AsyncMock(side_effect=transmit)
    monkeypatch.setattr("local_model_client.streams.transmit", mock)
    assert (await client.execute(frames(), 1))["status"] == "succeeded"
    assert mock.await_count == 1
    assert client.journal.recent()[0]["state"] == "succeeded"
    assert calls[-1][1].endswith("/result")


async def test_cloud_video_upload_does_not_leak_device_credentials(tmp_path):
    client, calls, _ = processor(tmp_path, "cloud")
    uploads = []

    def storage(request):
        assert "authorization" not in request.headers
        assert request.headers["content-type"] == "video/mp4"
        assert request.method == "PUT"
        uploads.append(request.content)
        return httpx.Response(204)

    client.transport = httpx.MockTransport(storage)
    assert (await client.execute(frames(), 1))["status"] == "succeeded"
    assert len(uploads) == 1
    assert calls[-1][1].endswith("/upload-complete")
    assert "secret" not in str(client.journal.recent())


async def test_uncertain_creation_is_journaled_and_never_replayed(tmp_path):
    client, calls, _ = processor(tmp_path)
    original = client.pms.json.side_effect

    async def timeout(method, path, **kwargs):
        if path.endswith("/runs"):
            calls.append((method, path, kwargs))
            raise TimeoutError()
        return await original(method, path, **kwargs)

    client.pms.json.side_effect = timeout
    with pytest.raises(TimeoutError):
        await client.execute(frames(), 1)
    assert client.journal.recent()[0]["state"] == "unknown"
    assert sum(path.endswith("/runs") for _, path, _ in calls) == 1


async def test_cancelled_processing_cancels_reserved_run(tmp_path, monkeypatch):
    client, calls, _ = processor(tmp_path)
    started = asyncio.Event()

    async def transmit(*args):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("local_model_client.streams.transmit", transmit)
    task = asyncio.create_task(client.execute(frames(), 1))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert calls[-1][1].endswith("/cancel")
    assert client.journal.recent()[0]["state"] == "cancelled"
