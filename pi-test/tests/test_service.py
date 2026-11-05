import asyncio
import io
import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from training_client.runtime import Runtime

from pi_test.config import Settings
from pi_test.control import Control, send
from pi_test.hardware import camera as camera_module
from pi_test.hardware.audio import output_device
from pi_test.hardware.camera import JpegParser
from pi_test.service import Service


def host(tmp_path):
    settings = Settings(app_root=tmp_path, control_dir=tmp_path / "control", speaker_output=False)
    scenarios = [
        {"id": str(uuid4()), "title": title, "languages": ["en"], "vitals": {"pulse_bpm": pulse}}
        for title, pulse in (("Chest discomfort", 88), ("Wheezing", 96))
    ]
    pms = SimpleNamespace(
        conversation=None,
        model_route=None,
        close_conversation=AsyncMock(),
        scenario_options=AsyncMock(
            return_value={
                "items": scenarios,
                "selection": None,
                "default": {"scenario_id": scenarios[0]["id"]},
            }
        ),
    )
    pms.save_scenario_selection = AsyncMock(side_effect=lambda body: body)
    controller = SimpleNamespace(
        inference=None,
        pms=pms,
        sync=None,
        busy=False,
        _conversation_generation=1,
        use_models=Mock(),
        refresh_local_models=AsyncMock(),
        use_selection=Mock(),
        reset=Mock(),
        close=AsyncMock(),
        text_turn=AsyncMock(),
    )
    speaker = SimpleNamespace(
        prefer=Mock(), stop=Mock(), close=Mock(), speak=Mock(), speaking=False, progress=0
    )

    def factory(settings, observe):
        client = Runtime(settings, observe, controller=controller, speaker=speaker)
        client.settings.use_pms_models = False
        return client

    service = Service(settings, runtime_factory=factory)
    service.ready = True
    return service, scenarios


async def test_two_scenarios_use_shared_runtime_without_gui_or_automatic_capture(tmp_path):
    service, scenarios = host(tmp_path)
    assert not service.active and not service.runtime.camera.busy
    try:
        for row in scenarios:
            response = await service.dispatch({"command": "begin", "scenario": row["id"]})
            assert response == {"accepted": "begin"}
            await service.job
            assert service.active and service.state == "paused"
            for text in ("What brought you here?", "When did it begin?"):
                await service.dispatch({"command": "text", "text": text})
                await service.job
            await service.dispatch({"command": "pause"})
            assert not service.runtime.finishing
            await service.dispatch({"command": "finish"})
            assert not service.active and service.state == "idle"
        assert service.runtime.controller.text_turn.await_count == 4
        assert "tkinter" not in sys.modules
        assert not service.runtime.camera.busy
    finally:
        await service.runtime.close()


async def test_pause_cancels_one_submission_and_allows_explicit_resume(tmp_path):
    service, scenarios = host(tmp_path)
    await service.begin(scenarios[0]["id"])
    started = asyncio.Event()

    async def blocked(text):
        started.set()
        await asyncio.Event().wait()

    service.runtime.controller.text_turn.side_effect = blocked
    await service.dispatch({"command": "text", "text": "question"})
    await started.wait()
    with pytest.raises(ValueError):
        await service.dispatch({"command": "text", "text": "duplicate"})
    await service.pause()
    assert service.job.cancelled()
    assert not service.runtime.finishing
    assert service.runtime.controller.text_turn.await_count == 1
    await service.runtime.close()


async def test_control_auth_bounds_and_redaction(tmp_path):
    async def dispatch(request):
        if request.get("command") == "fail":
            raise ValueError("secret signed URL and transcript must not escape")
        return {"state": "idle"}

    server = Control(tmp_path / "control", dispatch)
    await server.start()
    try:
        assert (await send(server.directory, {"command": "status"}))["result"]["state"] == "idle"
        failed = await send(server.directory, {"command": "fail"})
        assert failed == {"ok": False, "error": "ValueError"}
        with pytest.raises(ValueError):
            await Control(server.directory, dispatch).start()
        if sys.platform == "win32":
            data = json.loads(server.path.read_text())
            reader, writer = await asyncio.open_connection("127.0.0.1", data["port"])
            writer.write(b'{"command":"status","token":"wrong"}\n')
            await writer.drain()
            assert not json.loads(await reader.readline())["ok"]
            writer.close()
            await writer.wait_closed()
    finally:
        await server.close()


def test_camera_chunks_and_limits_and_speaker_identity():
    parser = JpegParser()
    assert parser.feed(b"\xff") == []
    assert parser.feed(b"\xd8abc\xff\xd9") == [b"\xff\xd8abc\xff\xd9"]
    with pytest.raises(Exception, match="limit"):
        parser.feed(b"x" * 1100001)
    devices = [{"name": "USB", "max_output_channels": 2}]
    assert output_device("USB", devices) == 0
    with pytest.raises(ValueError):
        output_device("USB", devices * 2)
    with pytest.raises(ValueError):
        output_device("missing", devices)


def test_csi_child_is_bound_to_recorder_worker_on_linux(monkeypatch):
    monkeypatch.setattr(camera_module, "sys", SimpleNamespace(platform="linux"))
    options = {}

    class Process:
        stdout = io.BytesIO()

        def poll(self):
            return 0

    def popen(_command, **kwargs):
        options.update(kwargs)
        return Process()

    capture = camera_module.CsiCamera(popen=popen)
    capture.release()
    assert options["preexec_fn"].func is camera_module._parent_death_signal


async def test_disk_pressure_blocks_capture_and_text_before_submission(tmp_path, monkeypatch):
    service, _ = host(tmp_path)
    service.active = True
    monkeypatch.setattr("pi_test.service.shutil.disk_usage", lambda _: SimpleNamespace(free=0))
    with pytest.raises(ValueError, match="reserve"):
        await service.dispatch({"command": "text", "text": "question"})
    service.runtime.controller.text_turn.assert_not_called()
    await service.runtime.close()


async def test_status_and_shutdown_remain_available_during_a_slow_mutation(tmp_path):
    service, _ = host(tmp_path)
    async with service.command_lock:
        async with asyncio.timeout(1):
            assert (await service.dispatch({"command": "status"}))["ready"]
            await service.dispatch({"command": "shutdown"})
    assert service.stop.is_set()
    await service.runtime.close()


async def test_pause_preserves_assigned_finish_barrier(tmp_path):
    service, _ = host(tmp_path)
    service.runtime.sessions = SimpleNamespace(finishing=True, close=AsyncMock())
    await service.pause()
    assert service.runtime.finishing
    await service.runtime.close()


async def test_unenrolled_daemon_boots_without_capture_and_closes_socket(tmp_path):
    service = Service(Settings(app_root=tmp_path / "state", control_dir=tmp_path / "control"))
    running = asyncio.create_task(service.run())
    try:
        async with asyncio.timeout(10):
            while service.control.server is None:
                if running.done():
                    await running
                await asyncio.sleep(0.01)
            while service.state == "starting":
                await asyncio.sleep(0.01)
        response = await send(service.settings.control_dir, {"command": "status"})
        assert response["ok"] and not response["result"]["ready"]
        assert not response["result"]["active"] and not response["result"]["camera_active"]
        assert response["result"]["state"] == "unavailable"
        await send(service.settings.control_dir, {"command": "shutdown"})
        async with asyncio.timeout(10):
            await running
        assert not service.control.path.exists()
        assert "tkinter" not in sys.modules
    finally:
        service.stop.set()
        await asyncio.gather(running, return_exceptions=True)
