import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from training_client.pms_client import ClientError
from training_client.sessions import SessionSupervisor


def supervisor():
    stamp = datetime.now(UTC)
    row = {
        "id": "assigned",
        "scenario_id": "case",
        "language": "en",
        "duration_seconds": 300,
        "started_at": stamp.isoformat(),
        "expires_at": (stamp + timedelta(minutes=5)).isoformat(),
    }
    pms = SimpleNamespace(
        conversation=None,
        assigned_session_id=None,
        scenario_options=AsyncMock(return_value={"items": [{"id": "case", "vitals": {}}]}),
        save_scenario_selection=AsyncMock(return_value={"id": "selection"}),
        ensure_conversation=AsyncMock(),
        json=AsyncMock(return_value=row),
    )
    client = SimpleNamespace(
        settings=SimpleNamespace(device_id="device", language_choices=("en",)),
        controller=SimpleNamespace(pms=pms, use_selection=Mock(), reset=Mock()),
        closing=False,
        finishing=False,
        stop_work=AsyncMock(),
        emit=Mock(),
    )
    core = SessionSupervisor(client)
    core.next = row
    return core, client, pms


async def test_stopping_during_setup_cannot_publish_a_late_session():
    core, client, pms = supervisor()
    entered = asyncio.Event()

    async def ensure():
        entered.set()
        await asyncio.Event().wait()

    pms.ensure_conversation = AsyncMock(side_effect=ensure)
    begin = asyncio.create_task(core.begin())
    await entered.wait()
    await core.finish("failed")
    assert begin.cancelled()
    assert not core.starting and core.active is None
    assert pms.assigned_session_id is None
    assert not any(call.args[0] == "queue_begun" for call in client.emit.call_args_list)
    assert [call.args[1].split("/")[-1] for call in pms.json.call_args_list] == ["begin", "finish"]


async def test_unknown_begin_retains_exact_claim_until_finish_is_acknowledged():
    core, client, pms = supervisor()
    pms.json.side_effect = OSError("offline")
    with pytest.raises(OSError):
        await core.begin()
    assert core.finishing and client.finishing
    assert core._claim_id == "assigned"
    pms.json.side_effect = None
    await core.finish("completed")
    assert not core.finishing and core._claim_id is None
    paths = [call.args[1] for call in pms.json.call_args_list]
    assert paths == [
        "/api/v1/device/session-queue/assigned/begin",
        "/api/v1/device/session-queue/assigned/finish",
        "/api/v1/device/session-queue/assigned/finish",
    ]
    assert pms.json.call_args.kwargs["json"]["outcome"] == "failed"


async def test_concurrent_finishes_do_not_reset_or_acknowledge_twice():
    core, client, pms = supervisor()
    core.activate(core.next)
    entered, release = asyncio.Event(), asyncio.Event()

    async def stop():
        entered.set()
        await release.wait()

    client.stop_work = AsyncMock(side_effect=stop)
    first = asyncio.create_task(core.finish())
    await entered.wait()
    second = asyncio.create_task(core.finish())
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(first, second)
    client.controller.reset.assert_called_once()
    assert pms.json.await_count == 1


async def test_foreign_runtime_is_observed_without_adopting_or_finishing_it():
    core, client, pms = supervisor()
    await core.receive({"active": core.next, "next": None})
    assert core.remote_busy and core.active is None and core.next is None
    client.stop_work.assert_not_awaited()
    pms.json.assert_not_awaited()


async def test_begin_refuses_a_competing_runtime_operation():
    core, client, pms = supervisor()
    client.operation = asyncio.current_task()
    with pytest.raises(ClientError):
        await core.begin()
    pms.scenario_options.assert_not_awaited()
    pms.json.assert_not_awaited()


async def test_cancelled_poll_does_not_kill_lease_supervision():
    core, client, pms = supervisor()
    poll = asyncio.create_task(asyncio.sleep(10))
    poll.cancel()
    await asyncio.gather(poll, return_exceptions=True)
    core.poll_task = poll
    core.starting = True
    runner = asyncio.create_task(core.run())
    try:
        await asyncio.sleep(0.01)
        assert not runner.done(), "Cancelling a poll must not cancel the session supervisor"
    finally:
        runner.cancel()
        await asyncio.gather(runner, return_exceptions=True)
