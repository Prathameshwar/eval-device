from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest

from training_client.config import Settings
from training_client.media import media_url
from training_client.pms_client import ClientError, PMSClient
from training_client.processing import VideoProcessing
from training_client.speech import ManagerPlayback


async def test_video_processing_accepts_real_http_202_without_replaying(tmp_path, monkeypatch):
    identity, revision = str(uuid4()), str(uuid4())
    created = []

    def platform(request):
        if request.url.path.endswith("/config"):
            return httpx.Response(
                200,
                json={
                    "settings": {
                        "video": {
                            "enabled": True,
                            "execution_mode": "local",
                            "engine": "opencv_motion",
                            "operation": "video.motion",
                        }
                    },
                    "profile_revision_id": revision,
                    "configuration_hash": "a" * 64,
                    "policy": {"capture_limits": {"max_video_seconds": 30, "max_upload_bytes": 8000000}},
                },
            )
        if request.url.path.endswith("/runs"):
            created.append(request)
            return httpx.Response(202, json={"run": {"id": identity, "status": "awaiting_device"}})
        if request.url.path.endswith("/result"):
            return httpx.Response(
                200, json={"id": identity, "status": "succeeded", "result": {"motion_detected": True}}
            )
        assert request.url.path.endswith("/heartbeat")
        return httpx.Response(200, json={})

    async def capabilities(*_):
        return {"media": {"video_operations": ["video.motion"]}}

    async def transmit(connection, kind, metadata, frames):
        assert metadata["processing_run_id"] == identity
        assert len([value async for value in frames]) == 2
        return {"motion_detected": True}

    async def frames():
        yield b"fixture"
        yield b"fixture"

    settings = Settings(
        app_root=tmp_path, pms_url="https://platform.test", pms_token="dev_fixture", organization_id=uuid4()
    )
    pms = PMSClient(settings)
    await pms.http.aclose()
    pms.http = httpx.AsyncClient(base_url=settings.pms_url, transport=httpx.MockTransport(platform))
    monkeypatch.setattr("local_model_client.streams.transmit", transmit)
    try:
        processor = VideoProcessing(settings, pms, SimpleNamespace(remote=True, async_request=capabilities))
        assert (await processor.execute(frames(), 1))["status"] == "succeeded"
        assert len(created) == 1
        # All other API operations continue requiring their declared status.
        with pytest.raises(ClientError):
            await pms.json("POST", "/api/v1/device/runs")
    finally:
        await pms.close()


@pytest.mark.parametrize(
    "address,origin",
    [
        ("https://user:secret@storage.test/media", "https://platform.test"),
        ("http://127.0.0.1:9000/media", "http://127.0.0.1:8000"),
        ("http://127.0.0.1/media", "https://127.0.0.1"),
        ("https://storage.test:invalid/media", "https://platform.test"),
        ("https://storage.test/\nmedia", "https://platform.test"),
    ],
)
def test_media_addresses_reject_embedded_credentials_and_wrong_origins(address, origin):
    with pytest.raises(ClientError, match="address"):
        media_url(address, origin)


def test_reselected_output_device_reopens_cached_stream(monkeypatch):
    import sounddevice

    opened = []

    def output(**kwargs):
        stream = Mock()
        opened.append((kwargs["device"], stream))
        return stream

    monkeypatch.setattr(sounddevice, "RawOutputStream", output)
    engine = ManagerPlayback()
    engine.output_device = 1
    engine._output(22050)
    engine.output_device = 2
    engine._output(22050)
    assert [index for index, _ in opened] == [1, 2]
    opened[0][1].close.assert_called_once()
    opened[1][1].close()
