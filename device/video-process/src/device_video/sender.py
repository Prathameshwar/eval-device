"""Bounded concurrent sending and receipt validation over the existing WebSocket."""

import asyncio
import json
import time
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol

from .protocol import HEADER, Frame


class Socket(Protocol):
    async def send(self, message: str | bytes) -> None: ...

    async def recv(self) -> str | bytes: ...


class TransferError(Exception):
    """An interrupted/invalid transfer; never a reason to replay automatically."""


@dataclass(frozen=True)
class Limits:
    max_in_flight: int = 4
    ack_seconds: float = 5
    completion_seconds: float = 15
    max_lag_seconds: float = 2

    def __post_init__(self) -> None:
        if type(self.max_in_flight) is not int or not 1 <= self.max_in_flight <= 16:
            raise ValueError("in-flight window must be 1-16 frames")
        for value in (self.ack_seconds, self.completion_seconds, self.max_lag_seconds):
            if not 0.01 <= value <= 60:
                raise ValueError("sender deadlines must be 0.01-60 seconds")


async def send_frames(
    socket: Socket,
    frames: Iterable[Frame],
    recording_id: str,
    max_frame_bytes: int,
    limits: Limits | None = None,
) -> dict[str, Any]:
    """Send paced frames while receiving receipts independently.

    At most max_in_flight frames await acknowledgment, plus one iterator lookahead.
    Acknowledgments release window slots, not retained JPEG buffers. Only the server's
    final receipt can claim durable storage. Failures cancel sibling tasks and bubble
    to the connection owner, which must close rather than resume/replay this session.
    """
    limits = limits or Limits()
    if type(max_frame_bytes) is not int or not 1 <= max_frame_bytes <= 2097152:
        raise ValueError("invalid receiver frame limit")
    window = asyncio.Semaphore(limits.max_in_flight)
    changed = asyncio.Event()
    pending: deque[tuple[int, int, float]] = deque()
    began = time.monotonic()
    sent, acknowledged, last_timestamp = 0, 0, -1
    stop_sent: float | None = None
    completion: dict[str, Any] | None = None

    async def produce() -> None:
        nonlocal sent, last_timestamp, stop_sent
        for frame in frames:
            if (
                frame.sequence != sent
                or frame.timestamp_us <= last_timestamp
                or (sent == 0 and frame.timestamp_us != 0)
                or not 0 < len(frame.jpeg) <= max_frame_bytes
            ):
                raise TransferError("invalid_source_frame")
            target = began + frame.timestamp_us / 1000000
            await asyncio.sleep(max(0, target - time.monotonic()))
            await window.acquire()
            if time.monotonic() - target > limits.max_lag_seconds:
                raise TransferError("sender_backlog")
            pending.append((frame.sequence, frame.timestamp_us, time.monotonic()))
            sent += 1
            last_timestamp = frame.timestamp_us
            changed.set()
            # The ack watchdog also bounds a blocked send (slot reserved before I/O).
            await asyncio.wait_for(
                socket.send(HEADER.pack(b"VPF1", frame.sequence, frame.timestamp_us) + frame.jpeg),
                limits.ack_seconds,
            )
        stop_sent = time.monotonic()
        changed.set()
        await asyncio.wait_for(socket.send('{"type":"stop"}'), limits.ack_seconds)

    async def consume() -> None:
        nonlocal acknowledged, completion
        while True:
            event = json.loads(await socket.recv())
            if not isinstance(event, dict):
                raise TransferError("invalid_receipt")
            kind = event.get("type")
            if kind == "accepted":
                if not pending:
                    raise TransferError("unexpected_ack")
                sequence, timestamp, _ = pending[0]
                if (
                    type(event.get("sequence")) is not int
                    or event["sequence"] != sequence
                    or type(event.get("timestamp_us")) is not int
                    or event["timestamp_us"] != timestamp
                    or event.get("status") != "pending"
                ):
                    raise TransferError("invalid_ack")
                pending.popleft()
                acknowledged += 1
                window.release()
                changed.set()
            elif kind == "complete":
                receipt = event.get("recording")
                if (
                    stop_sent is None
                    or pending
                    or acknowledged != sent
                    or event.get("recording_id") != recording_id
                    or not isinstance(receipt, dict)
                    or receipt.get("status") not in {"pending", "saved", "incomplete"}
                ):
                    raise TransferError("invalid_completion")
                if receipt["status"] == "saved" and (
                    receipt.get("finalized") is not True
                    or type(receipt.get("saved_frames")) is not int
                    or receipt["saved_frames"] != sent
                ):
                    raise TransferError("invalid_saved_receipt")
                completion = event
                changed.set()
                return
            elif kind == "error":
                raise TransferError("receiver_rejected_stream")
            else:
                raise TransferError("unexpected_receipt")

    async def watchdog() -> None:
        while completion is None:
            changed.clear()
            if pending:
                deadline, code = pending[0][2] + limits.ack_seconds, "ack_timeout"
            elif stop_sent is not None:
                deadline, code = stop_sent + limits.completion_seconds, "completion_timeout"
            else:
                # An intentional capture gap has no outstanding ack to time out.
                await changed.wait()
                continue
            try:
                await asyncio.wait_for(changed.wait(), max(0, deadline - time.monotonic()))
            except TimeoutError:
                raise TransferError(code) from None

    async with asyncio.TaskGroup() as group:
        group.create_task(produce(), name="video-send")
        group.create_task(consume(), name="video-receipts")
        group.create_task(watchdog(), name="video-deadlines")
    if completion is None:
        raise TransferError("missing_completion")
    return completion
