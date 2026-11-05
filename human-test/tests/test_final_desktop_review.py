"""Cancellation, dialog lifetime and uncertain conversation-start regressions."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from test_cloud_models import route, settings
from test_device_models_readonly import attach_runtime
from test_speech import FakeWindow
from training_client.controller import Controller
from training_client.pms_client import ClientError

from human_test.model_dialog import ModelDialog


async def test_cancelled_model_reload_can_be_retried():
    dialog = object.__new__(ModelDialog)
    dialog.closed = False
    dialog.owner = SimpleNamespace(
        controller=SimpleNamespace(
            pms=SimpleNamespace(model_config=AsyncMock(side_effect=asyncio.CancelledError)),
            use_models=Mock(),
        ),
        emit=Mock(),
    )
    dialog.window = SimpleNamespace(winfo_exists=lambda: True)
    attach_runtime(dialog.owner)
    dialog.refresh = SimpleNamespace(configure=Mock())
    dialog.summary = SimpleNamespace(set=Mock())
    with pytest.raises(asyncio.CancelledError):
        await dialog.load()
    assert not dialog.handle(dialog.owner.emit.call_args.args[1])
    dialog.refresh.configure.assert_called_once_with(state="normal")
    assert "cancelled" in dialog.summary.set.call_args.args[0]
    dialog.owner.controller.use_models.assert_not_called()


def test_applied_reload_updates_setup_even_after_its_dialog_closed():
    window = FakeWindow(
        model_dialog=None,
        camera_view=SimpleNamespace(poll=Mock(), stop=Mock(), recording=False),
        talk_frame=SimpleNamespace(pack_forget=Mock()),
        setup_frame=SimpleNamespace(pack=Mock()),
        step=SimpleNamespace(set=Mock()),
        catalog_data={"scenarios": []},
        saved={"revision": 3},
        apply_catalog=Mock(),
    )
    window.emit("model_dialog", (SimpleNamespace(closed=True), "loaded", route()))
    window.drain()
    assert window.page == "setup"
    window.apply_catalog.assert_called_once_with(window.catalog_data, window.saved)
    window.camera_view.stop.assert_called_once()
    assert window.speaker.stops == 1


@pytest.mark.parametrize("cancel", [False, True])
async def test_readiness_ends_all_probes_before_returning(monkeypatch, cancel):
    controller = Controller(settings(), lambda *args: None)
    selected = route()
    controller.use_models(selected)
    started, stopped = asyncio.Event(), asyncio.Event()

    async def speech():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    async def llm():
        await started.wait()
        if cancel:
            await asyncio.Event().wait()
        raise ClientError("Credentials rejected", code="llm_credentials_rejected")

    monkeypatch.setattr(controller.pms, "model_config", AsyncMock(return_value=selected))
    monkeypatch.setattr(controller.pms, "speech_status", speech)
    monkeypatch.setattr(controller.pms, "preflight", llm)
    task = asyncio.create_task(controller.preflight())
    try:
        await asyncio.wait_for(started.wait(), 1)
        if cancel:
            task.cancel()
        with pytest.raises(asyncio.CancelledError if cancel else ClientError):
            await asyncio.wait_for(task, 1)
        assert stopped.is_set()
        assert not controller._preflight_at
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await controller.close()


async def test_invalid_local_settings_do_not_create_speech_probe_coroutines(monkeypatch):
    controller = Controller(settings(), lambda *args: None)
    selected = route(llm="local")
    selected["llm"]["execution"] = "caller"
    controller.use_models(selected)
    speech = Mock()
    monkeypatch.setattr(controller.pms, "model_config", AsyncMock(return_value=selected))
    monkeypatch.setattr(controller.pms, "speech_status", speech)
    monkeypatch.setattr(controller, "local_model", Mock(side_effect=ClientError("Local key missing")))
    try:
        with pytest.raises(ClientError, match="Local key missing"):
            await controller.preflight()
        speech.assert_not_called()
    finally:
        await controller.close()


async def test_uncertain_context_start_reuses_exact_payload_until_reset(monkeypatch):
    controller = Controller(settings(), lambda *args: None)
    controller.use_models(route())
    controller.use_selection(
        {"id": "fixture", "revision": 1, "language": "en", "document": {"patient": {"name": "Alex"}}}
    )
    attempts = []

    async def timeout(method, path, **kwargs):
        attempts.append(dict(kwargs["json"]))
        raise httpx.ReadTimeout("Uncertain context creation")

    monkeypatch.setattr(controller.pms, "json", timeout)
    try:
        with pytest.raises(httpx.ReadTimeout):
            await controller.pms.ensure_conversation("speech")
        controller.settings.speaker_output = False
        with pytest.raises(httpx.ReadTimeout):
            await controller.pms.ensure_conversation("text")
        assert attempts[0] == attempts[1]
        controller.reset()
        with pytest.raises(httpx.ReadTimeout):
            await controller.pms.ensure_conversation("text")
        assert attempts[2]["request_key"] != attempts[0]["request_key"]
        assert attempts[2]["input_mode"] == attempts[2]["output_mode"] == "text"
    finally:
        await controller.close()


def test_prepared_desktop_opens_without_launching_another_launcher(monkeypatch):
    import subprocess

    from human_test import app

    monkeypatch.setenv("HUMAN_DESKTOP_PREPARED", "true")
    root = SimpleNamespace(mainloop=Mock())
    monkeypatch.setattr(app.tk, "Tk", lambda: root)
    window = Mock(return_value=SimpleNamespace(reopen_provisioning=False))
    monkeypatch.setattr(app, "Window", window)
    redirect = Mock(side_effect=AssertionError("A prepared child must not launch recursively"))
    monkeypatch.setattr(subprocess, "call", redirect)
    app.main()
    window.assert_called_once()
    root.mainloop.assert_called_once()
    redirect.assert_not_called()
