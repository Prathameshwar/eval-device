import asyncio
import queue
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from test_service import host
from training_client.devices import NormalizedFrames, input_device, input_rate
from training_client.pms_client import ClientError
from training_client.telemetry import heartbeat

from pi_test.config import Settings


@pytest.mark.parametrize("rate", [16000, 44100, 48000])
def test_native_audio_becomes_bounded_16khz_blocks_and_disconnect_fails(rate):
    source = queue.Queue()
    stream = SimpleNamespace(active=True)
    clock = [1.0]
    normalized = NormalizedFrames(source, stream, rate, clock=lambda: clock[0])
    for _ in range(20):
        source.put(bytes(rate // 10))
    blocks = []
    while True:
        try:
            blocks.append(normalized.get_nowait())
        except queue.Empty:
            break
    assert 19 <= len(blocks) <= 20
    assert all(block == bytes(1600) for block in blocks)
    clock[0] += 4
    with pytest.raises(ClientError, match="stalled"):
        normalized.get_nowait()
    clock[0] = 1.0
    stream.active = False
    with pytest.raises(ClientError, match="disconnected"):
        normalized.get_nowait()


def test_named_microphone_is_exact_and_never_falls_back(tmp_path):
    settings = Settings(app_root=tmp_path, control_dir=tmp_path / "control", microphone_name="USB mic")
    devices = [{"name": "USB mic", "max_input_channels": 1}, {"name": "Webcam", "max_input_channels": 1}]
    assert input_device(settings, devices, 1)[0] == 0
    for inventory in (devices[1:], devices + devices[:1]):
        with pytest.raises(ClientError, match="missing or ambiguous"):
            input_device(settings, inventory, 0)


async def test_audio_and_video_jobs_are_independent_and_pause_cancels_both(tmp_path):
    service, scenarios = host(tmp_path)
    await service.begin(scenarios[0]["id"])
    audio, video = asyncio.Event(), asyncio.Event()

    async def wait(event):
        event.set()
        await asyncio.Event().wait()

    service.launch("listen", lambda: wait(audio))
    service.launch("camera-process", lambda: wait(video), video=True)
    await asyncio.gather(audio.wait(), video.wait())
    assert service.status()["job"] == "listen" and service.status()["video_processing"]
    await service.dispatch({"command": "send-now"})
    assert service.runtime.send_now.is_set()
    with pytest.raises(ValueError):
        service.launch("duplicate", lambda: wait(video), video=True)
    await service.pause()
    assert service.job.cancelled() and service.video_job.cancelled()
    assert service.state == "paused" and not service.runtime.finishing
    await service.runtime.close()


async def test_results_are_private_expire_and_are_cleared_by_new_work(tmp_path):
    service, _ = host(tmp_path)
    service.launch("text", AsyncMock(return_value={"answer": "private result"}))
    await service.job
    assert "private result" not in str(service.status())
    assert (await service.dispatch({"command": "result"}))["answer"] == "private result"
    service.result_until = 0
    assert await service.dispatch({"command": "result"}) is None
    service.launch("text", AsyncMock(side_effect=ValueError("private error")))
    await service.job
    assert await service.dispatch({"command": "result"}) is None
    assert service.status()["last_error"] == "ValueError"
    await service.runtime.close()


async def test_session_completion_and_camera_stop_cancel_video(tmp_path):
    service, _ = host(tmp_path)
    for command in ("camera-stop", "remote-finish"):
        service.launch("camera-process", asyncio.Event().wait, video=True)
        await asyncio.sleep(0)
        if command == "remote-finish":
            service.observe("queue_finished", {})
            await asyncio.gather(service.video_job, return_exceptions=True)
        else:
            await service.dispatch({"command": command})
        assert service.video_job.cancelled()
    await service.runtime.close()


async def test_begin_can_listen_only_after_explicit_command(tmp_path):
    service, scenarios = host(tmp_path)
    service.settings.listen_on_begin = True
    started = asyncio.Event()

    async def listen():
        assert service.active
        started.set()
        await asyncio.Event().wait()

    service.runtime.listen = listen
    assert not service.active
    await service.dispatch({"command": "begin", "scenario": scenarios[0]["id"]})
    await started.wait()
    assert service.status()["job"] == "listen"
    await service.pause()
    await service.runtime.close()


async def test_binding_mismatch_and_disabled_audio_route(tmp_path):
    service, _ = host(tmp_path)
    service.runtime.controller.pms.model_route = {
        "llm": {"mode": "cloud"},
        "audio": {"enabled": False, "mode": "local"},
    }
    await service.verify_binding()
    assert service.readiness["binding"] == "cloud_only"
    service.runtime.inference = SimpleNamespace(remote=True, host_id=str(uuid4()), root="https://gpu.test")
    service.runtime.controller.pms.json = AsyncMock(
        return_value={"host_id": str(uuid4()), "origin": "https://gpu.test"}
    )
    with pytest.raises(ValueError, match="differ"):
        await service.verify_binding()
    assert service.readiness["binding"] == "mismatch"
    await service.runtime.close()


def test_heartbeat_uses_one_boot_for_concurrent_media():
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(4) as pool:
        bodies = list(pool.map(lambda _: heartbeat(), range(100)))
    assert len({body["boot_id"] for body in bodies}) == 1
    assert len({body["sequence_number"] for body in bodies}) == 100


async def test_outage_recovery_never_resumes_capture(tmp_path, monkeypatch):
    service, scenarios = host(tmp_path)
    await service.begin(scenarios[0]["id"])
    clock = [100.0]
    monkeypatch.setattr("pi_test.service.time.monotonic", lambda: clock[0])
    attempts = []

    async def reconcile():
        attempts.append(True)
        if len(attempts) == 1:
            raise ConnectionError()
        service.stop.set()

    class Stop:
        stopped = False

        def is_set(self):
            return self.stopped

        def set(self):
            self.stopped = True

        async def wait(self):
            clock[0] += 20
            if not self.stopped:
                raise TimeoutError()

    service.stop = Stop()
    service.reconcile = reconcile
    service.runtime.listen = AsyncMock()
    await service.supervise()
    assert len(attempts) == 2 and service.ready
    assert service.active and service.state == "paused"
    assert not service.runtime.camera.busy
    service.runtime.listen.assert_not_called()
    await service.runtime.close()


async def test_cloud_text_remains_available_when_optional_gpu_is_down(tmp_path):
    from local_model_client import ConnectionError

    service, _ = host(tmp_path)
    service.runtime.initialize = AsyncMock()
    service.runtime.controller.pms.model_route = {"llm": {"mode": "cloud"}}
    identity = str(uuid4())
    service.runtime.controller.pms.json = AsyncMock(
        return_value={"host_id": identity, "origin": "https://gpu.test"}
    )
    service.runtime.inference = SimpleNamespace(
        remote=True,
        host_id=identity,
        root="https://gpu.test",
        clear_capabilities=lambda: None,
        async_request=AsyncMock(side_effect=ConnectionError("offline")),
    )
    await service.reconcile()
    assert service.readiness["gateway"] == "unavailable" and service.readiness["models"] == "cloud"
    service.runtime.controller.pms.model_route = {"llm": {"mode": "local", "model": "assigned"}}
    with pytest.raises(ValueError, match="unavailable"):
        await service.reconcile()
    await service.runtime.close()


def test_probe_and_capture_agree_on_native_audio_rate(tmp_path):
    class Unsupported(Exception):
        pass

    checked = []

    def check(**args):
        checked.append(args["samplerate"])
        if args["samplerate"] == 16000:
            raise Unsupported()

    sd = SimpleNamespace(
        PortAudioError=Unsupported,
        check_input_settings=check,
        query_devices=lambda *_: {"default_samplerate": 48000},
    )
    settings = Settings(app_root=tmp_path, control_dir=tmp_path / "control")
    assert input_rate(settings, 0, sd) == 48000
    assert checked == [16000, 48000]
    settings.microphone_native_rate = 16000
    with pytest.raises(Unsupported):
        input_rate(settings, 0, sd)


async def test_camera_loss_does_not_complete_a_partial_clip():
    from pi_test.hardware.streaming import frames

    camera = SimpleNamespace(busy=False)
    with pytest.raises(ValueError, match="stopped"):
        await anext(frames(camera, 10))


async def test_processing_journals_survive_service_restart(tmp_path):
    from training_client.cloud_speech import Journal

    Journal(tmp_path / "processing").write("video-key", "unknown")
    Journal(tmp_path / "synthesis").write("voice-key", "submitted", "run")
    service, _ = host(tmp_path)
    rows = await service.dispatch({"command": "processing-requests"})
    assert {row["kind"] for row in rows} == {"video", "audio_output"}
    assert {row["request_key"] for row in rows} == {"video-key", "voice-key"}
    await service.runtime.close()


async def test_assigned_stop_cancels_video_before_platform_ack_and_blocks_new_work(tmp_path):
    from training_client.sessions import SessionSupervisor

    service, _ = host(tmp_path)
    service.active = True
    started = asyncio.Event()

    async def processing():
        started.set()
        await asyncio.Event().wait()

    service.launch("camera-process", processing, video=True)
    await started.wait()
    service.runtime.sessions = SessionSupervisor(service.runtime)
    service.runtime.sessions.active = {"id": "fixture-assignment"}
    service.runtime.controller.pms.json = AsyncMock(side_effect=ConnectionError("offline"))
    with pytest.raises(ConnectionError):
        await service.runtime.sessions.finish()
    await asyncio.gather(service.video_job, return_exceptions=True)
    assert service.video_job.cancelled()
    assert service.status()["finishing"] and service.active
    for command in ("begin", "text", "listen", "resume", "camera-start", "camera-process", "camera-stream"):
        with pytest.raises(ValueError, match="stopping"):
            await service.dispatch({"command": command})
    service.runtime.controller.pms.json.side_effect = None
    await service.runtime.sessions.finish()
    assert not service.active and not service.runtime.finishing
    await service.runtime.close()


async def test_standalone_finish_failure_keeps_barrier_until_acknowledged(tmp_path):
    service, _ = host(tmp_path)
    service.active = True
    pms = service.runtime.controller.pms
    pms.conversation = {"context": {"conversation_id": str(uuid4())}}
    pms.close_conversation.side_effect = ConnectionError("unknown close outcome")
    with pytest.raises(ConnectionError):
        await service.dispatch({"command": "finish"})
    await service.dispatch({"command": "pause"})
    assert service.status()["finishing"] and service.active
    for command in ("text", "resume", "camera-start", "camera-process"):
        with pytest.raises(ValueError, match="stopping"):
            await service.dispatch({"command": command})
    service.runtime.controller.reset.assert_not_called()
    pms.close_conversation.side_effect = None
    await service.dispatch({"command": "finish"})
    assert not service.status()["finishing"] and not service.active
    assert pms.conversation is None
    await service.runtime.close()


def test_configured_voice_is_applied_when_gpu_metadata_arrives(tmp_path):
    from pi_test.service import Service

    service = Service(Settings(app_root=tmp_path, control_dir=tmp_path / "control", voice="en_alt"))
    service.runtime.controller = SimpleNamespace(pms=SimpleNamespace(model_route={}))
    assert service.runtime.speaker.preference("en") is None
    service.runtime.inference.remember(
        {
            "version": 1,
            "revision": 1,
            "models": [
                {
                    "id": "voice",
                    "name": "Fixture",
                    "capability": "tts",
                    "key": "en_alt",
                    "language": "en",
                    "gender": "male",
                    "default": True,
                }
            ],
            "services": {"tts": {"model_id": "voice", "ready": True, "state": "Ready"}},
        }
    )
    service.configure_output()
    assert service.runtime.speaker.preference("en") == "en_alt"
    service.runtime.speaker.close()
