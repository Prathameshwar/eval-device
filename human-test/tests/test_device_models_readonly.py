"""The desktop consumes device assignments and cannot publish configuration."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from test_cloud_models import settings
from training_client.pms_client import ClientError
from training_client.runtime import Runtime

from human_test.model_dialog import ModelDialog


def attach_runtime(owner):
    if not hasattr(owner.controller, "refresh_local_models"):
        owner.controller.refresh_local_models = AsyncMock()
    owner.runtime = Runtime(settings(), controller=owner.controller)
    return owner.runtime


async def test_reload_reads_and_applies_only_the_assigned_models():
    route = {"mode": "cloud", "llm": {"model": "assigned-model"}, "audio": {"enabled": False}}
    reader, apply, emit = AsyncMock(return_value=route), Mock(), Mock()
    dialog = object.__new__(ModelDialog)
    dialog.closed = False
    dialog.owner = SimpleNamespace(
        controller=SimpleNamespace(pms=SimpleNamespace(model_config=reader), use_models=apply), emit=emit
    )
    dialog.window = SimpleNamespace(winfo_exists=lambda: True)
    attach_runtime(dialog.owner)
    dialog.summary = SimpleNamespace(set=Mock())
    dialog.refresh = SimpleNamespace(configure=Mock())
    await dialog.load()
    reader.assert_awaited_once_with()
    emit.assert_called_once_with("model_dialog", (dialog, "loaded", route))
    apply.assert_called_once_with(route)
    dialog.handle((dialog, "loaded", route))
    apply.assert_called_once_with(route)
    assert "Speech recognition: None" in dialog.summary.set.call_args.args[0]


async def test_failed_or_closed_reload_never_applies_a_stale_assignment():
    dialog = object.__new__(ModelDialog)
    dialog.closed = False
    apply, emit = Mock(), Mock()
    reader = AsyncMock(side_effect=ClientError("Device is inactive"))
    dialog.owner = SimpleNamespace(
        controller=SimpleNamespace(pms=SimpleNamespace(model_config=reader), use_models=apply), emit=emit
    )
    dialog.window = SimpleNamespace(winfo_exists=lambda: True)
    attach_runtime(dialog.owner)
    dialog.summary = SimpleNamespace(set=Mock())
    dialog.refresh = SimpleNamespace(configure=Mock())
    with pytest.raises(ClientError):
        await dialog.load()
    assert not dialog.handle(emit.call_args.args[1])
    assert "Unable to reload" in dialog.summary.set.call_args.args[0]
    apply.assert_not_called()
    reader.side_effect = None
    reader.return_value = {"llm": {"model": "new"}}
    dialog.closed = True
    await dialog.load()
    apply.assert_not_called()
    assert not dialog.handle((object(), "loaded", reader.return_value))


async def test_reload_closes_previous_conversation_on_the_worker_loop(monkeypatch):
    import asyncio

    from test_cloud_models import route, settings
    from training_client.controller import Controller

    controller = Controller(settings(), lambda *args: None)
    selected = route()
    controller.use_models(selected)
    controller.pms.conversation = {"context": {"conversation_id": "previous"}}
    close = AsyncMock()
    monkeypatch.setattr(controller.pms, "close_conversation", close)
    monkeypatch.setattr(controller.pms, "model_config", AsyncMock(return_value=selected))
    dialog = object.__new__(ModelDialog)
    dialog.closed = False
    dialog.owner = SimpleNamespace(controller=controller, emit=Mock())
    attach_runtime(dialog.owner)
    try:
        await dialog.load()
        await asyncio.gather(*controller._closing_tasks)
        close.assert_awaited_once_with("previous")
        assert controller.pms.conversation is None
    finally:
        await controller.close()


async def test_open_models_dialog_cannot_reload_after_an_assignment_begins():
    dialog = object.__new__(ModelDialog)
    dialog.closed = False
    dialog.owner = SimpleNamespace(
        controller=SimpleNamespace(pms=SimpleNamespace(model_config=AsyncMock()), use_models=Mock()),
        emit=Mock(),
    )
    core = attach_runtime(dialog.owner)
    core.sessions = SimpleNamespace(starting=False, remote_busy=False, assigned=lambda: True)
    with pytest.raises(ClientError, match="Complete the assigned session"):
        await dialog.load()
    dialog.owner.controller.pms.model_config.assert_not_awaited()
    dialog.owner.controller.use_models.assert_not_called()


async def test_closing_models_dialog_cancels_pending_reload():
    import asyncio

    entered = asyncio.Event()

    async def read():
        entered.set()
        await asyncio.Event().wait()

    dialog = object.__new__(ModelDialog)
    dialog.closed = False
    dialog.window = SimpleNamespace(destroy=Mock())
    dialog.owner = SimpleNamespace(
        controller=SimpleNamespace(pms=SimpleNamespace(model_config=read), use_models=Mock()),
        emit=Mock(),
        loop=asyncio.get_running_loop(),
    )
    core = attach_runtime(dialog.owner)
    pending = asyncio.create_task(dialog.load())
    await entered.wait()
    dialog.close()
    await asyncio.gather(pending, return_exceptions=True)
    assert pending.cancelled() and core.operation is None
    dialog.owner.controller.use_models.assert_not_called()
