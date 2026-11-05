"""Shutdown must flush local work even when the central API is unavailable."""

import asyncio
from types import SimpleNamespace

import pytest
from test_flow import settings
from training_client.controller import Controller
from training_client.pms_client import ClientError


async def test_shutdown_flushes_history_and_closes_clients_while_api_close_is_stalled(monkeypatch):
    controller = Controller(settings(), lambda *args: None)
    flushed = asyncio.Event()
    cancelled = []

    async def stalled(identity):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(identity)

    async def flush():
        flushed.set()

    controller.recorder = SimpleNamespace(close=flush)
    controller.pms.conversation = {"context": {"conversation_id": "current"}}
    previous = asyncio.create_task(stalled("previous"))
    controller._closing_tasks.add(previous)
    monkeypatch.setattr(controller.pms, "close_conversation", stalled)
    task = asyncio.create_task(controller.close())
    await asyncio.wait_for(flushed.wait(), 0.5)
    await asyncio.wait_for(task, 2)
    assert set(cancelled) == {"previous", "current"}
    assert previous.done() and controller.pms.http.is_closed


async def test_shutdown_reports_local_flush_failure_and_closes_client():
    controller = Controller(settings(), lambda *args: None)

    async def failed_flush():
        raise RuntimeError("disk writer stalled")

    controller.sync = SimpleNamespace(close=failed_flush)
    with pytest.raises(RuntimeError, match="saving local state") as error:
        await controller.close()
    assert str(error.value.__cause__) == "disk writer stalled"
    assert controller.pms.http.is_closed


@pytest.mark.parametrize("reason", [None, "tool_calls", "unexpected", [], {}])
async def test_incomplete_answer_is_rejected_before_speech_or_history(reason, monkeypatch):
    controller = Controller(settings(streaming=False), lambda *args: None)

    async def response(method, path, **kwargs):
        return {
            "request_key": kwargs["json"]["request_key"],
            "status": "succeeded",
            "text": "Unverified answer",
            "finish_reason": reason,
        }

    monkeypatch.setattr(controller.pms, "json", response)
    try:
        with pytest.raises(ClientError, match="incomplete"):
            await controller.text_turn("What is your name?")
        assert controller.history == []
    finally:
        await controller.close()
