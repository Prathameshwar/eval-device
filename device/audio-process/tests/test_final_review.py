import asyncio
import os
import subprocess
import sys
import threading
import time
from uuid import uuid4

import httpx
import pytest
from conftest import SPEECH, FakeEngine

from device_audio.audio import AudioChunk
from device_audio.cli import init_local
from device_audio.delivery import CallbackDispatcher
from device_audio.recording_store import RecordingStore, StorageError
from device_audio.runtime import Runtime, ServiceError


async def test_stalled_native_inference_retires_runtime_and_bounds_stop(settings):
    entered, release = threading.Event(), threading.Event()

    class Blocked(FakeEngine):
        def transcribe(self, chunk, language):
            entered.set()
            release.wait(5)
            return super().transcribe(chunk, language)

    settings.inference_shutdown_seconds = 0.1
    runtime = Runtime(settings, lambda _: Blocked())
    await runtime.start()
    chunk = AudioChunk(SPEECH * 6, 0, 2880)
    first = asyncio.create_task(runtime.transcribe(chunk, "hi"))
    assert await asyncio.to_thread(entered.wait, 1)
    second = asyncio.create_task(runtime.transcribe(chunk, "en"))
    await asyncio.sleep(0)
    try:
        before = time.monotonic()
        await asyncio.wait_for(runtime.stop(), 1)
        assert time.monotonic() - before < 0.7 and not runtime.ready
        assert runtime.native.thread.daemon and runtime.native.thread.is_alive()
        for task in (first, second):
            with pytest.raises(ServiceError, match="service_stopped"):
                await task
        with pytest.raises(ServiceError, match="not_ready"):
            await runtime.transcribe(chunk, "hi")
        with pytest.raises(RuntimeError, match="restarted"):
            await runtime.start()
    finally:
        release.set()
        await asyncio.to_thread(runtime.native.closed.wait, 1)


async def test_model_load_deadline_cleans_up_without_waiting_for_native_loader(settings):
    entered, release = threading.Event(), threading.Event()

    def factory(_):
        entered.set()
        release.wait(5)
        return FakeEngine()

    settings.model_load_timeout_seconds = 0.05
    runtime = Runtime(settings, factory)
    try:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(runtime.start(), 0.8)
        assert entered.is_set() and not runtime.ready and runtime.native.thread.daemon
    finally:
        release.set()
        await asyncio.to_thread(runtime.native.closed.wait, 1)


async def test_blocked_console_does_not_block_callback_or_shutdown(settings, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls, posts = [], []

    def blocked_print(*args, **kwargs):
        calls.append(1)
        entered.set()
        release.wait(5)

    async def callback(request):
        posts.append(1)
        return httpx.Response(204)

    monkeypatch.setattr("builtins.print", blocked_print)
    settings.console_output = True
    settings.callback_timeout_seconds = 0.05
    from pydantic import SecretStr

    settings.callback_url = SecretStr("http://127.0.0.1:1234/receiver")
    dispatcher = CallbackDispatcher(settings, httpx.MockTransport(callback))
    dispatcher.start()
    try:
        first = await asyncio.wait_for(dispatcher.submit({"event_id": "one", "text": "one"}), 1)
        second = await asyncio.wait_for(dispatcher.submit({"event_id": "two", "text": "two"}), 1)
        assert first.console_status == "unknown" and first.status == "delivered"
        assert second.console_status == "failed" and second.status == "delivered"
        assert len(calls) == 1 and len(posts) == 2
        await asyncio.wait_for(dispatcher.stop(), 0.5)
    finally:
        release.set()
        await asyncio.to_thread(dispatcher.console.closed.wait, 1)


def test_private_env_created_before_secret_write_and_never_overwritten(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from device_audio import cli

    original = cli.private_directory
    observed = []

    def check_before_write(path):
        assert path.stat().st_size == 0
        observed.append(True)
        original(path)

    monkeypatch.setattr(cli, "private_directory", check_before_write)
    init_local()
    original_data = (tmp_path / ".env").read_bytes()
    with pytest.raises(FileExistsError):
        init_local()
    assert observed == [True] and (tmp_path / ".env").read_bytes() == original_data
    if sys.platform == "win32":
        command = "$p=Get-Acl -LiteralPath $env:AUDIO_ACL_FILE; $p.Access | ForEach-Object { $_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value }"
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            check=True,
            capture_output=True,
            text=True,
            env=os.environ | {"AUDIO_ACL_FILE": str(tmp_path / ".env")},
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        sids = result.stdout.split()
        assert len(sids) == 2 and "S-1-5-18" in sids
    else:
        assert (tmp_path / ".env").stat().st_mode & 0o777 == 0o600


def test_failed_permission_setup_does_not_write_credentials(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def reject(path):
        raise OSError("permissions")

    monkeypatch.setattr("device_audio.cli.private_directory", reject)
    with pytest.raises(OSError):
        init_local()
    assert (tmp_path / ".env").read_bytes() == b""


def test_audio_recovery_handles_empty_initial_sessions_but_preserves_unrecognized_media(settings, tmp_path):
    settings.recording_dir = tmp_path / "recordings"
    settings.recording_min_free_bytes = 0
    store = RecordingStore(settings)
    store.initialize()
    store.shutdown()
    for temporary in (False, True):
        directory = settings.recording_dir / str(uuid4())
        directory.mkdir()
        if temporary:
            (directory / "session.json.tmp").write_bytes(b'{"incomplete":')
    store = RecordingStore(settings)
    store.initialize()
    assert store.records == {}
    store.shutdown()
    directory = settings.recording_dir / str(uuid4())
    directory.mkdir()
    (directory / "audio.wav").write_bytes(b"preserve")
    store = RecordingStore(settings)
    try:
        with pytest.raises(StorageError):
            store.initialize()
        assert (directory / "audio.wav").read_bytes() == b"preserve"
    finally:
        store.shutdown()


@pytest.mark.parametrize(
    "blocked_event, invalid_start",
    [
        ("websocket.accept", False),
        ("websocket.close", False),
        ("websocket.close", True),
    ],
)
async def test_audio_handshake_deadlines_release_client_slot(settings, blocked_event, invalid_start):
    from conftest import TOKEN, Detector
    from starlette.websockets import WebSocket

    from device_audio.app import create_app

    settings.send_timeout_seconds = 0.05
    app = create_app(settings, lambda _: FakeEngine(), detector_factory=Detector)
    route = next(route.endpoint for route in app.routes if route.path == "/v1/audio/stream")
    incoming = asyncio.Queue()
    for message in (
        {"type": "websocket.connect"},
        {"type": "websocket.receive", "text": '{"type":"bad"}' if invalid_start else '{"type":"start"}'},
        {"type": "websocket.receive", "text": '{"type":"finish"}'},
    ):
        incoming.put_nowait(message)

    async def send(message):
        if message["type"] == blocked_event:
            await asyncio.Event().wait()

    scope = dict(
        type="websocket",
        scheme="ws",
        path="/v1/audio/stream",
        query_string=b"",
        client=("127.0.0.1", 1234),
        server=("127.0.0.1", 8765),
        headers=[(b"authorization", ("Bearer " + TOKEN).encode())],
    )
    async with app.router.lifespan_context(app):
        await asyncio.wait_for(route(WebSocket(scope, incoming.get, send)), 0.8)
        assert not app.state.runtime.active_clients
