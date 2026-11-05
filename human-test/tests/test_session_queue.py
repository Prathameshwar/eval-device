"""Desktop handoff, attribution, expiry and capture stopping without real hardware."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from training_client.sessions import SessionSupervisor

from human_test.app import Window
from human_test.session_queue import SessionQueue


def queue():
    value = SessionQueue.__new__(SessionQueue)
    value.preview_id = None
    value.label, value.frame, value.begin_button = Mock(), Mock(), Mock()
    value.window = SimpleNamespace(
        page="setup",
        closing=False,
        running=False,
        settings=SimpleNamespace(device_id="device", language_choices=("en",)),
        controller=SimpleNamespace(pms=SimpleNamespace(json=AsyncMock(), conversation=None), reset=Mock()),
        catalog_data={},
        body=Mock(),
        practice_identity=Mock(),
        save_button=Mock(),
        root=Mock(),
        pause=Mock(),
        speaker=Mock(),
        camera_view=Mock(),
        emit=Mock(),
        back=Mock(),
        active=None,
    )
    w = value.window
    w.runtime = SimpleNamespace(
        settings=w.settings,
        controller=w.controller,
        closing=False,
        finishing=False,
        emit=w.emit,
        stop_work=AsyncMock(),
    )
    w.runtime.sessions = SessionSupervisor(w.runtime)
    w.runtime.sessions.runtime_id = "instance"
    return value


async def receive(value, data):
    await value.core.receive(data)
    value.received(data)


def assignment():
    stamp = datetime.now(UTC)
    return {
        "id": "session",
        "learner_name": "Trainee A",
        "scenario_title": "Case A",
        "scenario_id": "case",
        "language": "en",
        "duration_seconds": 300,
        "status": "active",
        "started_at": stamp.isoformat(),
        "expires_at": (stamp + timedelta(seconds=8)).isoformat(),
    }


@pytest.mark.parametrize("confirmed", [False, True])
def test_complete_button_requires_yes_without_stopping_on_no(monkeypatch, confirmed):
    value = queue()
    window = value.window
    window.page = "talk"
    window.session_queue = value
    value.finish = Mock()
    dialog = Mock(return_value=confirmed)
    monkeypatch.setattr("human_test.app.messagebox.askyesno", dialog)
    Window.confirm_complete(window)
    dialog.assert_called_once_with(
        "Complete & Close",
        "Complete this practice session and return to Practice setup?",
        parent=window.root,
        default="no",
    )
    assert value.finish.call_count == int(confirmed)
    window.pause.assert_not_called()
    window.camera_view.stop.assert_not_called()


def test_complete_confirmation_does_not_finish_again_after_remote_stop(monkeypatch):
    value = queue()
    window = value.window
    window.page = "talk"
    window.session_queue = value
    value.finish = Mock()

    def confirm(*args, **kwargs):
        window.page = "setup"
        return True

    monkeypatch.setattr("human_test.app.messagebox.askyesno", confirm)
    Window.confirm_complete(window)
    value.finish.assert_not_called()


async def test_waiting_assignment_does_not_replace_standalone_practice():
    value = queue()
    value.window.page = "talk"
    await receive(value, {"active": None, "next": assignment(), "paused": False})
    assert value.active is None
    assert "Finish this practice" in value.label.configure.call_args.kwargs["text"]
    value.begin_button.pack.assert_not_called()
    value.window.controller.pms.json.assert_not_called()


async def test_previous_does_not_abandon_an_existing_standalone_conversation():
    value = queue()
    value.window.controller.pms.conversation = {"context": {"conversation_id": "standalone"}}
    await receive(value, {"active": None, "next": assignment(), "paused": False})
    assert value.standalone_active()
    assert not value.blocks_setup()
    value.window.save_button.configure.assert_called_with(text="Return to current practice")
    value.begin()
    value.window.controller.pms.json.assert_not_called()


async def test_ready_session_preselects_assigned_case_without_starting_or_saving():
    value = queue()
    value.window.catalog_data = {"scenarios": [{"id": "case"}]}
    value.window.saved = {"revision": 7}
    value.window.apply_catalog = Mock()
    value.window.lock_options = Mock()
    value.window.state = Mock()
    await receive(value, {"active": None, "next": assignment(), "paused": False})
    catalog, saved = value.window.apply_catalog.call_args.args
    assert catalog["default"] == {"scenario_id": "case", "language": "en"}
    assert saved is None
    assert value.window.saved == {"revision": 7}
    value.window.controller.pms.json.assert_not_called()
    value.window.save_button.configure.assert_called_with(text="Begin assigned session")


def test_begin_deadline_is_capped_at_original_expiry():
    value = queue()
    value.core.clock = lambda: 100
    row = assignment()
    value.core.activate(row)
    value.begun(row, {"id": "saved"})
    assert 100 < value.core.deadline <= 108
    assert value.active["learner_name"] == "Trainee A"
    value.window.emit.assert_called_once_with("saved", {"id": "saved"})


async def test_web_end_stops_capture_before_acknowledging():
    value = queue()
    value.core.active = assignment()
    order = []
    value.window.runtime.stop_work = AsyncMock(side_effect=lambda: order.append("stopped"))
    value.window.controller.pms.json = AsyncMock(side_effect=lambda *a, **k: order.append("acknowledged"))
    await value.core.receive({"active": {**assignment(), "status": "stopping"}})
    assert order == ["stopped", "acknowledged"]
    assert value.active is None


async def test_another_runtime_is_not_adopted_or_ended():
    value = queue()
    await receive(value, {"active": assignment(), "next": None})
    assert value.blocks_setup()
    assert value.active is None
    value.window.pause.assert_not_called()


async def test_connection_loss_stops_assigned_capture():
    import asyncio

    value = queue()
    value.core.active = assignment()
    value.core.last_ok = 100
    value.core.deadline = 400
    value.core.clock = lambda: 121
    value.core.poll_task = asyncio.create_task(asyncio.Event().wait())
    task = asyncio.create_task(value.core.run())
    try:
        for _ in range(50):
            if value.window.runtime.stop_work.await_count:
                break
            await asyncio.sleep(0.01)
        value.window.runtime.stop_work.assert_awaited_once()
        assert value.window.controller.pms.json.call_args.kwargs["json"]["outcome"] == "failed"
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_finish_keeps_assignment_until_server_acknowledges():
    value = queue()
    value.core.active = assignment()
    value.window.controller.pms.json = AsyncMock(side_effect=RuntimeError("offline"))
    with pytest.raises(RuntimeError):
        await value.core.finish("completed")
    assert value.active is not None and value.finishing
    value.window.controller.reset.assert_not_called()
    value.window.emit.assert_called_with("queue_finish_failed", "completed")


async def test_begin_binds_assignment_before_creating_conversation():
    value = queue()
    value.core.next = assignment()
    calls = []
    pms = value.window.controller.pms
    pms.scenario_options = AsyncMock(
        return_value={"items": [{"id": "case", "vitals": {}}], "selection": None}
    )
    pms.save_scenario_selection = AsyncMock(return_value={"id": "saved"})

    async def request(method, path, **kwargs):
        calls.append(path)
        return assignment()

    pms.json = request

    async def ensure():
        assert pms.assigned_session_id == "session"
        assert calls == ["/api/v1/device/session-queue/session/begin"]

    pms.ensure_conversation = ensure
    value.window.controller.use_selection = Mock()
    tasks = []
    value.window.submit = lambda coro, completion: tasks.append(coro)
    value.begin()
    await tasks.pop()
    assert value.window.emit.call_args.args[0] == "queue_begun"
    assert pms.assigned_session_id == "session"


async def test_all_scenario_pages_are_available_to_assigned_sessions(monkeypatch):
    from test_flow import settings
    from training_client.pms_client import PMSClient

    client = PMSClient(settings())
    request = AsyncMock(
        side_effect=[
            {"items": [{"id": "first"}], "next_cursor": "cursor"},
            {"items": [{"id": "last"}], "next_cursor": None},
        ]
    )
    monkeypatch.setattr(client, "json", request)
    try:
        assert [row["id"] for row in (await client.scenario_options())["items"]] == ["first", "last"]
    finally:
        await client.close()


def test_unsupported_assigned_language_never_falls_back_or_starts():
    value = queue()
    value.core.next = {**assignment(), "language": "hi"}
    value.preview = Mock()
    value.begin()
    value.preview.assert_called_once()
    value.window.controller.pms.json.assert_not_called()
    assert not value.starting


async def test_unavailable_preview_is_cleared_when_assignment_is_removed():
    value = queue()
    w = value.window
    w.catalog_data = {"scenarios": [{"id": "case"}]}
    w.saved = {"revision": 7}
    for name in ("clear_case", "case_choice", "language", "lock_options", "state", "apply_catalog"):
        setattr(w, name, Mock())
    await receive(value, {"active": None, "next": {**assignment(), "language": "hi"}})
    w.apply_catalog.assert_not_called()
    w.language.set.assert_called_with("HI")
    w.save_button.configure.assert_called_with(text="Assigned language unavailable", state="disabled")
    await receive(value, {"active": None, "next": None})
    w.apply_catalog.assert_called_once_with(w.catalog_data, w.saved)
    assert value.preview_id is None


async def test_begin_uses_claimed_assignment_after_an_instructor_edits_the_waiting_session():
    value = queue()
    value.core.next = assignment()
    pms = value.window.controller.pms
    claimed = {**assignment(), "scenario_id": "changed-case", "duration_seconds": 60}
    pms.json = AsyncMock(return_value=claimed)
    pms.scenario_options = AsyncMock(
        side_effect=[
            {"items": [{"id": "case", "vitals": {}}], "selection": None},
            {"items": [{"id": "changed-case", "vitals": {"spo2_percent": 95}}], "selection": {"revision": 4}},
        ]
    )
    pms.save_scenario_selection = AsyncMock(return_value={"id": "saved"})
    pms.ensure_conversation = AsyncMock()
    value.window.controller.use_selection = Mock()
    tasks = []
    value.window.submit = lambda coro, completion: tasks.append(coro)
    value.begin()
    await tasks.pop()
    pms.save_scenario_selection.assert_awaited_once_with(
        {
            "scenario_id": "changed-case",
            "language": "en",
            "expected_revision": 4,
            "vitals": {"spo2_percent": 95},
        }
    )
    assert value.window.emit.call_args.args == ("queue_begun", (claimed, {"id": "saved"}))


@pytest.mark.parametrize(
    "event", ["queue_begun", "queue_start_failed", "queue_finished", "queue_finish_failed"]
)
def test_queue_lifecycle_events_survive_a_full_display_queue(event):
    from queue import Queue

    from human_test.app import Window

    window = SimpleNamespace(events=Queue(maxsize=2))
    window.events.put(("state", "Old status"))
    window.events.put(("state", "Old status"))
    Window.emit(window, event, "assignment")
    assert list(window.events.queue)[-1] == (event, "assignment")


def test_committed_setup_and_final_answer_survive_display_backlog():
    from queue import Queue

    from training_client.runtime import Runtime

    from human_test.app import Window

    window = SimpleNamespace(events=Queue(maxsize=3))
    window.events.put(("queue_stopping", None))
    window.events.put(("state", "stale"))
    window.events.put(("answer_delta", "partial"))
    Window.emit(window, "saved", {"revision": 2})
    assert ("queue_stopping", None) in list(window.events.queue)
    assert ("saved", {"revision": 2}) in list(window.events.queue)

    runtime = object.__new__(Runtime)
    runtime.observe = lambda kind, value: Window.emit(window, kind, value)
    runtime.observer_failures = 0
    runtime.notify("answer", "complete answer")
    assert ("answer", "complete answer") in list(window.events.queue)
    assert runtime.observer_failures == 0

    window.events = Queue(maxsize=2)
    window.events.put(("saved", {"revision": 2}))
    window.events.put(("queue_stopping", None))
    Window.emit(window, "answer", "complete answer")
    assert list(window.events.queue) == [
        ("saved", {"revision": 2}),
        ("queue_stopping", None),
        ("answer", "complete answer"),
    ]
