"""One bounded background writer. Queue admission never waits for disk."""

import threading
import time
from collections import deque
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any

from .config import Settings
from .privacy import StorageError
from .store import Store


@dataclass
class Work:
    kind: str
    args: tuple[Any, ...]
    weight: int
    future: Future[Any]


class Recorder:
    def __init__(self, settings: Settings):
        self.settings, self.store = settings, Store(settings)
        self.condition = threading.Condition()
        self.queue: deque[Work] = deque()
        self.queued_bytes, self.queued_items = 0, 0
        self.stopping, self.ready = False, False
        self.started: Future[Any] = Future()
        self.receipts: dict[str, dict[str, Any]] = {}
        self.pending: set[str] = set()
        self.finishing: set[str] = set()
        self.thread = threading.Thread(target=self.run, name="video-writer", daemon=True)
        self.thread.start()

    def publish(self) -> None:
        with self.condition:
            self.receipts = {identity: data.copy() for identity, data in self.store.records.items()}

    def status(self, identity: str, owner: str) -> dict[str, Any] | None:
        with self.condition:
            data = self.receipts.get(identity)
            return data.copy() if data and data["client_id"] == owner else None

    def submit(self, kind: str, *args: Any, weight: int = 0) -> Future[Any]:
        with self.condition:
            # End commands have a bounded reserved slot per active session. They must
            # follow already admitted frames even when the byte queue is full.
            limit = self.settings.queue_items + (self.settings.max_sessions if kind == "finish" else 0)
            if (
                self.stopping
                or not self.ready
                or self.queued_items >= limit
                or self.queued_bytes + weight > self.settings.queue_bytes
            ):
                raise StorageError("recording_backpressure")
            identity = args[0]
            if kind == "start":
                if len(self.pending) >= self.settings.max_sessions or identity in self.pending:
                    raise StorageError("session_limit")
                self.pending.add(identity)
            elif identity not in self.pending or identity in self.finishing:
                raise StorageError("recording_closed")
            if kind == "finish":
                self.finishing.add(identity)
            work = Work(kind, args, weight, Future())
            self.queue.append(work)
            self.queued_bytes += weight
            self.queued_items += 1
            self.condition.notify()
            return work.future

    def execute(self, work: Work) -> None:
        result, error = None, None
        identity = work.args[0]
        try:
            result = getattr(self.store, work.kind)(*work.args)
        except Exception as exc:
            reason = str(exc) if isinstance(exc, StorageError) else "disk_error"
            self.store.fail(identity, reason)
            if work.kind == "finish":
                data = self.store.records.get(identity)
                if data:
                    data.update(status="incomplete", finalized=False, reason=reason)
                self.store.active.pop(identity, None)
            if work.kind == "start":
                self.store.active.pop(identity, None)
            error = StorageError(reason)
        finally:
            self.publish()
            with self.condition:
                self.queued_bytes -= work.weight
                self.queued_items -= 1
                if work.kind == "finish" or (work.kind == "start" and error):
                    self.pending.discard(identity)
                    self.finishing.discard(identity)
        if not work.future.cancelled():
            if error:
                work.future.set_exception(error)
            else:
                work.future.set_result(result.copy() if isinstance(result, dict) else result)

    def maintenance(self) -> None:
        for identity, session in list(self.store.active.items()):
            if session.frames and time.monotonic() - session.buffered_at >= self.settings.segment_seconds:
                try:
                    self.store.flush(identity)
                except Exception:
                    self.store.fail(identity, "disk_error")
        self.publish()

    def run(self) -> None:
        try:
            self.store.initialize()
            self.publish()
            self.ready = True
            self.started.set_result(None)
            last_cleanup = time.monotonic()
            while True:
                with self.condition:
                    if not self.queue and not self.stopping:
                        self.condition.wait(timeout=min(self.settings.segment_seconds, 1))
                    if self.queue:
                        work = self.queue.popleft()
                    elif self.stopping:
                        break
                    else:
                        work = None
                if work:
                    self.execute(work)
                self.maintenance()
                if time.monotonic() - last_cleanup >= 60:
                    try:
                        self.store.prune()
                    except Exception:
                        pass  # Admission still enforces quotas and reports its failure.
                    self.publish()
                    last_cleanup = time.monotonic()
            for identity, session in list(self.store.active.items()):
                self.queued_items += 1
                self.execute(
                    Work("finish", (identity, "shutdown", session.data["received_frames"]), 0, Future())
                )
        except Exception:
            if not self.started.done():
                self.started.set_exception(StorageError("storage_unavailable"))
        finally:
            self.ready = False
            self.store.close()

    def stop(self) -> None:
        with self.condition:
            self.stopping = True
            self.condition.notify_all()
        self.thread.join(timeout=self.settings.disk_wait_seconds)
