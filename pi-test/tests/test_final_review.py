import asyncio
import io
from unittest.mock import AsyncMock

import pytest
from test_service import host

from pi_test import __main__ as cli
from pi_test.control import Control, send


async def test_control_shutdown_cancels_pending_command_promptly(tmp_path):
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    async def dispatch(_request):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    control = Control(tmp_path / "control", dispatch)
    await control.start()
    request = asyncio.create_task(send(control.directory, {"command": "slow"}))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        await asyncio.wait_for(control.close(), 1)
        assert cancelled.is_set() and not control.clients
        assert not control.path.exists()
    finally:
        request.cancel()
        await asyncio.gather(request, return_exceptions=True)
        await control.close()


async def test_shutdown_refuses_queued_and_new_work(tmp_path):
    service, _ = host(tmp_path)
    service.active = True
    try:
        async with service.command_lock:
            queued = asyncio.create_task(service.dispatch({"command": "text", "text": "queued"}))
            await asyncio.sleep(0)
            await service.dispatch({"command": "shutdown"})
            status = await service.dispatch({"command": "status"})
            assert status["state"] == "stopping" and not status["ready"]
        with pytest.raises(ValueError, match="stopping"):
            await queued
        for command in ("begin", "text", "listen", "camera-start", "reload"):
            with pytest.raises(ValueError, match="stopping"):
                await service.dispatch({"command": command})
        service.runtime.controller.text_turn.assert_not_called()
    finally:
        await service.runtime.close()


async def test_control_accepts_complete_unicode_question_without_escaping_expansion(tmp_path):
    captured = []

    async def dispatch(request):
        captured.append(request["text"])
        return {"accepted": True}

    control = Control(tmp_path / "control", dispatch)
    await control.start()
    question = "\U0001f642" * 8000
    try:
        response = await send(control.directory, {"command": "text", "text": question})
        assert response["ok"] and captured == [question]
    finally:
        await control.close()


def test_cli_rejects_oversized_input_before_trimming_or_submitting(tmp_path, monkeypatch):
    service, _ = host(tmp_path)
    monkeypatch.setattr(cli, "load", lambda *_args, **_kwargs: service.settings)
    submit = AsyncMock()
    monkeypatch.setattr(cli, "send", submit)
    monkeypatch.setattr("sys.argv", ["pi-test", "text"])
    monkeypatch.setattr("sys.stdin", io.StringIO("q" * 8000 + " \ncritical continuation"))
    with pytest.raises(SystemExit) as exit_status:
        cli.main()
    assert exit_status.value.code == 1
    submit.assert_not_called()


@pytest.mark.parametrize("ending", ["", "\n", "\r\n"])
def test_cli_preserves_full_limit_question_with_optional_terminal_newline(tmp_path, monkeypatch, ending):
    service, _ = host(tmp_path)
    monkeypatch.setattr(cli, "load", lambda *_args, **_kwargs: service.settings)
    submit = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(cli, "send", submit)
    monkeypatch.setattr("sys.argv", ["pi-test", "text"])
    monkeypatch.setattr("sys.stdin", io.StringIO("q" * 8000 + ending))
    cli.main()
    assert submit.await_args.args[1]["text"] == "q" * 8000
