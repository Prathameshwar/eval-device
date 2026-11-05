import asyncio
import json
import time

import pytest

from device_video.protocol import HEADER, Frame
from device_video.sender import Limits, send_frames


class Peer:
    """A receiver that accepts promptly but delays each receipt independently."""

    def __init__(self, delay=0.04, window=4, ack_change=None, receipt_change=None):
        self.delay, self.window = delay, window
        self.ack_change, self.receipt_change = ack_change, receipt_change
        self.events = asyncio.Queue()
        self.tasks = []
        self.sent = []
        self.outstanding, self.peak = 0, 0
        self.stopped = False
        self.cancelled = False

    async def later_ack(self, sequence, timestamp):
        await asyncio.sleep(self.delay)
        # TCP preserves order even when multiple delayed timers wake together.
        if sequence:
            await self.tasks[sequence - 1]
        event = dict(type="accepted", sequence=sequence, timestamp_us=timestamp, status="pending")
        if self.ack_change:
            event = self.ack_change(event)
        if event is not None:
            await self.events.put(json.dumps(event))

    async def later_complete(self):
        await asyncio.gather(*self.tasks)
        event = dict(
            type="complete",
            recording_id="recording-1",
            recording=dict(status="saved", finalized=True, saved_frames=len(self.sent)),
        )
        if self.receipt_change:
            event = self.receipt_change(event)
        if event is not None:
            await self.events.put(json.dumps(event))

    async def send(self, message):
        if isinstance(message, bytes):
            _, sequence, timestamp = HEADER.unpack_from(message)
            self.sent.append(sequence)
            self.outstanding += 1
            self.peak = max(self.peak, self.outstanding)
            assert self.outstanding <= self.window
            self.tasks.append(asyncio.create_task(self.later_ack(sequence, timestamp)))
        else:
            assert json.loads(message) == {"type": "stop"}
            self.stopped = True
            asyncio.create_task(self.later_complete())

    async def recv(self):
        try:
            event = await self.events.get()
            if json.loads(event).get("type") == "accepted":
                self.outstanding -= 1
            return event
        except asyncio.CancelledError:
            self.cancelled = True
            raise

    async def cleanup(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)


def sample_frames(count=8, gap_us=1000):
    return [Frame(i, i * gap_us, b"fixture") for i in range(count)]


def error_codes(group):
    return [str(exc) for exc in group.exceptions]


@pytest.mark.asyncio
async def test_window_keeps_sending_while_receipts_delayed_and_stays_bounded():
    peer = Peer()
    result = await send_frames(peer, sample_frames(), "recording-1", 100)
    assert result["recording"]["status"] == "saved"
    assert peer.peak == 4 and peer.sent == list(range(8)) and peer.stopped


@pytest.mark.asyncio
async def test_window_one_remains_compatible_with_serial_sender():
    peer = Peer(window=1)
    await send_frames(peer, sample_frames(4), "recording-1", 100, Limits(max_in_flight=1))
    assert peer.peak == 1 and peer.sent == list(range(4))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        lambda e: e | {"sequence": e["sequence"] + 1},
        lambda e: e | {"timestamp_us": -1},
        lambda e: e | {"sequence": True},
        lambda e: e | {"status": "saved"},
        lambda e: {"type": "error", "code": "disk_error"},
    ],
)
async def test_wrong_receipts_stop_without_replay(change):
    peer = Peer(ack_change=change)
    try:
        with pytest.raises(ExceptionGroup):
            await send_frames(peer, sample_frames(20), "recording-1", 100)
        assert len(peer.sent) == 4 and len(set(peer.sent)) == 4 and not peer.stopped
    finally:
        await peer.cleanup()


@pytest.mark.asyncio
async def test_missing_ack_expires_and_cancels_receive():
    peer = Peer(ack_change=lambda e: None)
    try:
        with pytest.raises(ExceptionGroup) as caught:
            await send_frames(peer, sample_frames(20), "recording-1", 100, Limits(ack_seconds=0.05))
        assert "ack_timeout" in error_codes(caught.value)
        assert peer.cancelled and len(peer.sent) == 4
    finally:
        await peer.cleanup()


@pytest.mark.asyncio
async def test_duplicate_ack_rejected_even_when_next_frame_is_pending():
    peer = Peer(ack_change=lambda e: e | {"sequence": 0, "timestamp_us": 0})
    try:
        with pytest.raises(ExceptionGroup) as caught:
            await send_frames(peer, sample_frames(10), "recording-1", 100)
        assert "invalid_ack" in error_codes(caught.value)
    finally:
        await peer.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        lambda e: e | {"recording_id": "another"},
        lambda e: e | {"recording": {"status": "saved", "finalized": False, "saved_frames": 2}},
        lambda e: e | {"recording": {"status": "saved", "finalized": True, "saved_frames": 999}},
    ],
)
async def test_invalid_completion_never_claimed_success(change):
    peer = Peer(receipt_change=change)
    with pytest.raises(ExceptionGroup):
        await send_frames(peer, sample_frames(2), "recording-1", 100)


@pytest.mark.asyncio
async def test_pending_completion_is_returned_as_pending():
    peer = Peer(receipt_change=lambda e: e | {"recording": {"status": "pending", "finalized": False}})
    result = await send_frames(peer, sample_frames(2), "recording-1", 100)
    assert result["recording"] == {"status": "pending", "finalized": False}


@pytest.mark.asyncio
async def test_missing_completion_is_not_silent_success():
    peer = Peer(receipt_change=lambda e: None)
    with pytest.raises(ExceptionGroup) as caught:
        await send_frames(peer, sample_frames(2), "recording-1", 100, Limits(completion_seconds=0.06))
    assert "completion_timeout" in error_codes(caught.value)


@pytest.mark.asyncio
async def test_no_ack_timer_during_intentional_capture_gap():
    peer = Peer(delay=0.001)
    await send_frames(peer, sample_frames(2, gap_us=100000), "recording-1", 100, Limits(ack_seconds=0.04))
    assert peer.sent == [0, 1]


@pytest.mark.asyncio
async def test_stale_backlog_stops_without_burst_replay():
    peer = Peer(delay=0.06, window=1)
    with pytest.raises(ExceptionGroup) as caught:
        await send_frames(
            peer, sample_frames(10), "recording-1", 100, Limits(max_in_flight=1, max_lag_seconds=0.02)
        )
    assert "sender_backlog" in error_codes(caught.value) and peer.sent == [0]


@pytest.mark.asyncio
async def test_send_failure_cancels_receiver_immediately():
    peer = Peer()

    async def fail(message):
        await asyncio.sleep(0.01)
        raise OSError("disconnected")

    peer.send = fail
    with pytest.raises(ExceptionGroup):
        await send_frames(peer, sample_frames(), "recording-1", 100)
    assert peer.cancelled


@pytest.mark.asyncio
async def test_stalled_send_is_bounded_even_after_ack():
    peer = Peer(delay=0.001)
    original = peer.send

    async def stuck(message):
        await original(message)
        await asyncio.Event().wait()

    peer.send = stuck
    began = time.monotonic()
    with pytest.raises(ExceptionGroup):
        await send_frames(peer, sample_frames(), "recording-1", 100, Limits(ack_seconds=0.04))
    assert time.monotonic() - began < 0.5 and peer.cancelled


@pytest.mark.asyncio
async def test_receiver_closes_before_completion_is_failure():
    peer = Peer()

    async def closed():
        raise OSError("connection closed")

    peer.recv = closed
    try:
        with pytest.raises(ExceptionGroup):
            await send_frames(peer, sample_frames(), "recording-1", 100)
    finally:
        await peer.cleanup()


@pytest.mark.asyncio
async def test_source_limit_fails_before_transmission():
    peer = Peer()
    with pytest.raises(ExceptionGroup) as caught:
        await send_frames(peer, sample_frames(), "recording-1", 1)
    assert "invalid_source_frame" in error_codes(caught.value) and not peer.sent


@pytest.mark.parametrize(
    "values",
    [
        {"max_in_flight": 0},
        {"max_in_flight": 17},
        {"ack_seconds": 0},
        {"completion_seconds": float("nan")},
        {"max_lag_seconds": 100},
    ],
)
def test_invalid_sender_limits(values):
    with pytest.raises(ValueError):
        Limits(**values)
