import asyncio
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from local_model_client import Connection, configure

from training_client.config import Settings
from training_client.pms_client import ClientError
from training_client.recording import CameraRecording
from training_client.runtime import Runtime
from training_client.speech import ManagerPlayback
from training_client.video import Options, VideoError


def runtime(tmp_path, observe=None):
    speaker = SimpleNamespace(
        prefer=Mock(),
        speak=Mock(return_value=True),
        stop=Mock(),
        close=Mock(),
        progress=0,
        speaking=False,
        warm=Mock(return_value=None),
    )
    controller = SimpleNamespace(
        inference=None,
        _conversation_generation=1,
        sync=None,
        text_turn=AsyncMock(),
        close=AsyncMock(),
    )
    return Runtime(Settings(app_root=tmp_path), observe, controller=controller, speaker=speaker)


def test_playback_does_not_require_an_observer_or_ui_drain(tmp_path):
    client = runtime(tmp_path)
    client.emit("speak", {"text": "Reply", "language": "en", "generation": 1})
    client.speaker.speak.assert_called_once_with("Reply", "en", "male")
    client.emit("speak", {"text": "Stale", "language": "en", "generation": 0})
    assert client.speaker.speak.call_count == 1
    client.finishing = True
    client.emit("speak", {"text": "Late", "language": "en"})
    assert client.speaker.speak.call_count == 1


def test_failed_observer_cannot_prevent_playback_or_retry_stop(tmp_path):
    client = runtime(tmp_path, Mock(side_effect=RuntimeError("observer unavailable")))
    client.emit("speak", {"text": "Reply", "language": "en"})
    client.emit("retrying", True)
    client.emit("speak", {"text": "Blocked", "language": "en"})
    assert client.speaker.speak.call_count == 1
    client.speaker.stop.assert_called_once()
    assert client.observer_failures == 2


async def test_one_operation_and_shutdown_cancel_inference_without_replaying(tmp_path):
    client = runtime(tmp_path)
    entered = asyncio.Event()

    async def answer(text):
        entered.set()
        await asyncio.Event().wait()

    client.controller.text_turn = AsyncMock(side_effect=answer)
    active = asyncio.create_task(client.text_turn("Question"))
    await entered.wait()
    with pytest.raises(ClientError, match="already active"):
        await client.text_turn("Another")
    await client.close()
    assert active.cancelled()
    assert client.operation is None
    client.controller.text_turn.assert_awaited_once_with("Question")
    client.controller.close.assert_awaited_once()


async def test_new_text_stops_previous_playback_before_submission(tmp_path):
    client = runtime(tmp_path)
    order = []
    client.speaker.stop.side_effect = lambda: order.append("stop")
    client.controller.text_turn.side_effect = lambda text: order.append("submit")
    await client.text_turn("Question")
    assert order == ["stop", "submit"]


async def test_queued_text_stops_previous_playback_without_an_observer(tmp_path):
    client = runtime(tmp_path)
    client.work = asyncio.Queue(maxsize=1)
    await client.text_turn("Question")
    assert client.work.get_nowait() == "Question"
    client.speaker.stop.assert_called_once()


async def test_closed_runtime_cannot_restart_platform_polling(tmp_path):
    client = runtime(tmp_path)
    await client.close()
    with pytest.raises(ClientError):
        await client.initialize()
    assert client.sessions is None
    with pytest.raises(VideoError, match="stopping"):
        client.camera.start(Options(tmp_path))


@pytest.mark.parametrize("action", ["reload_models", "reset_conversation"])
async def test_configuration_actions_cannot_change_an_assigned_session(tmp_path, action):
    client = runtime(tmp_path)
    client.sessions = SimpleNamespace(starting=False, remote_busy=False, assigned=lambda: True)
    with pytest.raises(ClientError, match="Complete the assigned session"):
        await getattr(client, action)()
    assert client.operation is None


@pytest.mark.parametrize("action", ["reload_models", "reset_conversation", "save_selection", "prepare"])
async def test_context_changes_finish_media_before_resetting_archive(tmp_path, action):
    client = runtime(tmp_path)
    order = []
    client.speaker.stop.side_effect = lambda: order.append("playback_stopped")
    client.camera.close = AsyncMock(side_effect=lambda: order.append("camera_finished"))
    client.controller.pms = SimpleNamespace(
        model_config=AsyncMock(return_value={"version": 2}),
        save_scenario_selection=AsyncMock(return_value={"id": "case"}),
        scenario_options=AsyncMock(return_value={"items": []}),
    )
    client.settings.use_pms_models = True
    client.controller.refresh_local_models = AsyncMock()
    client.controller.use_models = Mock(side_effect=lambda _: order.append("context_changed"))
    client.controller.use_selection = Mock(side_effect=lambda _: order.append("context_changed"))
    client.controller.reset = Mock(side_effect=lambda: order.append("context_changed"))
    await getattr(client, action)(*([{}] if action == "save_selection" else []))
    assert order == ["playback_stopped", "camera_finished", "context_changed"]


async def test_cancelled_model_reload_does_not_apply_or_leave_runtime_busy(tmp_path):
    client = runtime(tmp_path)
    entered = asyncio.Event()

    async def read():
        entered.set()
        await asyncio.Event().wait()

    client.controller.pms = SimpleNamespace(model_config=read)
    client.controller.use_models = Mock()
    task = asyncio.create_task(client.reload_models())
    await entered.wait()
    client.pause()
    await asyncio.gather(task, return_exceptions=True)
    assert task.cancelled() and client.operation is None
    client.controller.use_models.assert_not_called()


@pytest.mark.parametrize("starting,remote_busy", [(True, False), (False, True)])
async def test_session_setup_or_foreign_owner_blocks_new_turns(tmp_path, starting, remote_busy):
    client = runtime(tmp_path)
    client.sessions = SimpleNamespace(starting=starting, remote_busy=remote_busy)
    with pytest.raises(ClientError, match="already active"):
        await client.text_turn("Question")
    client.controller.text_turn.assert_not_awaited()


def test_explicit_configuration_is_independent_of_working_directory_and_desktop_env(tmp_path, monkeypatch):
    monkeypatch.setenv("HUMAN_PMS_URL", "http://127.0.0.1:12345")
    monkeypatch.chdir(tmp_path.parent)
    settings = Settings(app_root=tmp_path)
    assert settings.session_sync_dir == tmp_path / ".local/session-sync"
    assert settings.history_dir == tmp_path / ".local/conversation-outbox"
    assert settings.input_ignore_file.is_file()
    assert not settings.session_sync_background
    assert settings.pms_url != "http://127.0.0.1:12345"


def test_connections_and_playback_do_not_follow_another_clients_configuration():
    first = Connection(port=18790, key="fixture-a", inherit_defaults=False)
    playback = ManagerPlayback(first)
    configure(port=28790, key="fixture-b")
    try:
        voice = playback.voice("voice", {"language": "en", "gender": "male"})
        assert voice.connection is first
        assert voice.connection.root == "http://127.0.0.1:18790"
        second = Connection(inherit_defaults=False)
        assert second.port == 8790 and second.key is None
    finally:
        configure()


async def test_camera_archives_segments_and_finishes_without_preview_polling(tmp_path):
    stopped = []

    class Recorder:
        busy = False

        def start(self, options):
            self.busy = True
            assert options.archive_id == "session"

        def stop(self):
            stopped.append(True)

        def poll(self):
            self.busy = False
            return [("segment", "segment.mkv"), ("finished", {"error": None})], None

    archive = SimpleNamespace(
        current="session", root=tmp_path, video_start=Mock(), video_file=Mock(), video_end=Mock()
    )
    camera = CameraRecording(recorder=Recorder())
    camera.start(Options(tmp_path), sync=archive)
    await camera.close()
    archive.video_start.assert_called_once_with("session")
    archive.video_file.assert_called_once_with("session", "segment.mkv")
    archive.video_end.assert_called_once_with("session", False)
    assert not camera.busy


def test_core_imports_without_frontend_or_native_hardware_libraries():
    script = """
import importlib.abc
import sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, *args):
        if name.split('.')[0] in {'tkinter', 'human_test', 'sounddevice', 'cv2', 'av'}:
            raise ImportError('forbidden dependency: ' + name)
sys.meta_path.insert(0, Block())
import training_client.runtime
import training_client.sessions
import training_client.connection
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr


async def test_camera_monitor_failure_stops_worker_and_marks_archive_incomplete(tmp_path):
    class Recorder:
        busy = False

        def start(self, options):
            self.busy = True

        def stop(self):
            pass

        def poll(self):
            raise RuntimeError("private driver details")

        def abort(self):
            self.busy = False

    archive = SimpleNamespace(
        current="session", root=tmp_path, video_start=Mock(), video_file=Mock(), video_end=Mock()
    )
    camera = CameraRecording(recorder=Recorder())
    camera.start(Options(tmp_path), sync=archive)
    await camera.close()
    archive.video_end.assert_called_once_with("session", True)
    assert not camera.busy
    assert ("interrupted", None) in camera.poll()[0]


async def test_camera_shutdown_error_still_closes_speaker_and_platform_client(tmp_path):
    client = runtime(tmp_path)
    client.camera = SimpleNamespace(close=AsyncMock(side_effect=RuntimeError("camera failed")))
    with pytest.raises(RuntimeError, match="camera failed"):
        await client.close()
    client.speaker.close.assert_called_once()
    client.controller.close.assert_awaited_once()
