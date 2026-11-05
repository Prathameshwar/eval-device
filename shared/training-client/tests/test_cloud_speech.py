import io
import json
import threading
import wave
from uuid import uuid4

import httpx
import pytest

from training_client.cloud_speech import PlatformVoice, RoutedPlayback
from training_client.config import Settings


def wav():
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(22050)
        stream.writeframes(bytes(4410))
    return output.getvalue()


@pytest.mark.parametrize("storage_host", ["storage.test", "platform.test"])
def test_cloud_output_uses_processing_and_does_not_send_device_key_to_storage(tmp_path, storage_host):
    settings = Settings(
        app_root=tmp_path, pms_url="https://platform.test", pms_token="dev_secret", organization_id=uuid4()
    )
    run_id, revision = str(uuid4()), str(uuid4())
    submissions = []

    def handle(request):
        if request.url.path == "/private":
            assert "authorization" not in request.headers
            assert "cookie" not in request.headers
            return httpx.Response(200, content=wav())
        assert request.headers["authorization"] == "Bearer dev_secret"
        path = request.url.path
        if path.endswith("/device/config"):
            result = {
                "settings": {"audio_output": {"execution_mode": "cloud", "enabled": True}},
                "profile_revision_id": revision,
                "configuration_hash": "a" * 64,
            }
        elif path.endswith("/heartbeat"):
            result = {}
        elif path.endswith("/device/runs"):
            submissions.append(json.loads(request.content))
            result = {"run": {"id": run_id, "status": "succeeded"}}
        elif path.endswith("/media"):
            result = {"items": [{"role": "output", "index": 0}]}
        else:
            assert path.endswith("/access")
            result = {"url": f"https://{storage_host}/private?signature=secret"}
        return httpx.Response(
            202 if path.endswith("/device/runs") else 200,
            json=result,
            headers={"Set-Cookie": "platform_session=private; Path=/; Secure"},
        )

    voice = PlatformVoice(settings, threading.Event(), transport=httpx.MockTransport(handle))
    assert sum(len(chunk.audio_int16_bytes) for chunk in voice.synthesize("Hello")) == 4410
    assert len(submissions) == 1 and submissions[0]["playback"] is False
    assert submissions[0]["profile_revision_id"] == revision


def test_cloud_warmup_does_not_require_local_gpu(tmp_path):
    settings = Settings(app_root=tmp_path)
    route = {"platform_media": {"audio_output": {"settings": {"enabled": True, "execution_mode": "cloud"}}}}
    playback = RoutedPlayback(settings, lambda: route)
    assert isinstance(playback.warm("en"), PlatformVoice)


def test_cancelled_output_never_submits(tmp_path):
    settings = Settings(app_root=tmp_path)
    stop = threading.Event()
    stop.set()
    voice = PlatformVoice(
        settings, stop, transport=httpx.MockTransport(lambda _: pytest.fail("Submitted after stop"))
    )
    with pytest.raises(Exception, match="stopped"):
        list(voice.synthesize("Hello"))


def test_full_synthesis_journal_can_finish_existing_work(tmp_path):
    import sqlite3
    import time

    from training_client.cloud_speech import Journal

    journal = Journal(tmp_path / "synthesis")
    with sqlite3.connect(journal.path) as db:
        db.executemany(
            "INSERT INTO requests VALUES (?, NULL, 'unknown', ?)",
            [(str(index), time.time()) for index in range(1000)],
        )
    journal.write("0", "completed", "run")
    with pytest.raises(Exception, match="full"):
        journal.write("new", "unknown")


def test_cloud_metadata_read_obeys_cancellation_before_submission(tmp_path):
    settings = Settings(app_root=tmp_path)
    stop = threading.Event()

    class SlowResponse(httpx.SyncByteStream):
        def __iter__(self):
            yield b'{"settings":'
            stop.set()
            yield b"{} }"

    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, stream=SlowResponse())

    voice = PlatformVoice(settings, stop, transport=httpx.MockTransport(handle))
    with pytest.raises(Exception, match="Invalid platform response"):
        list(voice.synthesize("Hello"))
    assert len(calls) == 1 and calls[0].method == "GET"
