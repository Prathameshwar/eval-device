"""Nonblocking recording admission and bounded background disk work."""

import asyncio
import logging
import queue
import threading
import time
from collections import OrderedDict
from concurrent.futures import Future
from dataclasses import dataclass, field
from functools import partial
from typing import Any, Callable

from .config import Settings
from .recording_store import FORMAT, RecordingStore, StorageError

logger = logging.getLogger("device_audio")


class DiskThread:
    """One daemon I/O thread. A stuck OS write cannot hold up API shutdown indefinitely."""

    def __init__(self, store: RecordingStore):
        self.store = store
        self.jobs: queue.Queue[tuple[Callable[[], Any], Future[Any]]] = queue.Queue(1)
        self.stopping = threading.Event()
        self.closed = threading.Event()
        self.thread = threading.Thread(target=self._run, name="audio-recording-disk", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        try:
            while not (self.stopping.is_set() and self.jobs.empty()):
                try:
                    function, future = self.jobs.get(timeout=0.05)
                except queue.Empty:
                    continue
                if future.set_running_or_notify_cancel():
                    try:
                        future.set_result(function())
                    except BaseException as exc:
                        future.set_exception(exc)
                self.jobs.task_done()
        finally:
            try:
                self.store.shutdown()
            except Exception:
                logger.warning("recording_shutdown_failed")
            finally:
                self.closed.set()

    async def call(self, function: Callable[[], Any]) -> Any:
        future: Future[Any] = Future()
        self.jobs.put_nowait((function, future))
        return await asyncio.wrap_future(future)

    def stop(self) -> None:
        self.stopping.set()


@dataclass
class Recording:
    data: dict[str, Any]
    pending: int = 0
    opened: bool = False
    ended: bool = False
    finalized: bool = False
    failed_components: set[str] = field(default_factory=set)
    stopped_components: set[str] = field(default_factory=set)

    def fail(self, reason: str) -> None:
        self.data.update(status="incomplete", reason=self.data.get("reason") or reason)

    def stop_component(self, component: str, reason: str, broken: bool = False) -> None:
        parts = {"audio", "transcript"} if component == "begin" else {component}
        self.stopped_components.update(parts)
        if broken:
            self.failed_components.update(parts)
        self.fail(reason)
        self.data["fallback"] = (
            "stream_only"
            if len(self.stopped_components) == 2
            else "transcript_only"
            if "audio" in self.stopped_components
            else "audio_only"
        )

    def snapshot(self) -> dict[str, Any]:
        return {**self.data, "finalized": self.finalized}


@dataclass
class Command:
    kind: str
    recording: Recording
    payload: Any
    weight: int


class Recorder:
    def __init__(
        self, settings: Settings, store_factory: Callable[[Settings], RecordingStore] = RecordingStore
    ):
        self.settings = settings
        self.store_factory = store_factory
        self.disk: DiskThread | None = None
        self.worker: asyncio.Task[None] | None = None
        self.queue: asyncio.Queue[Command] = asyncio.Queue(settings.recording_queue_items)
        self.wake = asyncio.Event()
        self.records: OrderedDict[str, Recording] = OrderedDict()
        self.pending_bytes = 0
        self.available = False
        self.stopping = False
        self.failure: str | None = None
        self.stored_bytes = 0

    async def start(self) -> None:
        if not self.settings.recording_enabled:
            return
        self.disk = DiskThread(self.store_factory(self.settings))
        try:
            restored = await asyncio.wait_for(
                self.disk.call(self.disk.store.initialize), self.settings.recording_startup_seconds
            )
            for data in restored:
                self.records[data["id"]] = Recording(data, opened=True, ended=True, finalized=True)
            self.available = True
            self.stored_bytes = self.disk.store.used
            self.worker = asyncio.create_task(self._work(), name="audio-recording")
        except Exception:
            self.failure = "storage_unavailable"
            logger.warning("recording_unavailable")
            self.disk.stop()

    def begin(self, session_id: str, client_id: str, stream_id: str, language: str) -> Recording:
        record = Recording(
            {
                "format": FORMAT,
                "id": session_id,
                "client_id": client_id,
                "stream_id": stream_id,
                "created_at": time.time(),
                "language": language,
                "model": self.settings.model_name,
                "sample_rate": 16000,
                "channels": 1,
                "format_audio": "pcm_s16le",
                "status": "recording",
                "reason": None,
                "fallback": "none",
                "audio_complete": False,
                "transcript_complete": False,
                "received_audio_bytes": 0,
                "received_transcripts": 0,
                "audio_bytes": 0,
                "transcripts": 0,
                "transcript_bytes": 0,
            }
        )
        if not self.settings.recording_enabled:
            record.data["status"] = "disabled"
            record.finalized = True
            return record
        if not self.available or self.stopping:
            record.stop_component("begin", "storage_unavailable")
            record.finalized = True
        elif (
            sum(not item.finalized for item in self.records.values())
            >= self.settings.recording_pending_sessions
        ):
            record.stop_component("begin", "recording_capacity")
            record.finalized = True
        else:
            if not self._put(Command("begin", record, record.snapshot(), 4096)):
                record.finalized = True
        self.records[session_id] = record
        self._trim_cache()
        return record

    def _trim_cache(self) -> None:
        maximum = self.settings.recording_max_sessions + self.settings.recording_pending_sessions
        for key, record in list(self.records.items()):
            if len(self.records) <= maximum:
                break
            if record.finalized:
                del self.records[key]

    def _put(self, command: Command) -> bool:
        record = command.recording
        if record.data["status"] == "disabled" or command.kind in record.stopped_components:
            return False
        if self.pending_bytes + command.weight > self.settings.recording_queue_bytes:
            record.stop_component(command.kind, "recording_queue_full")
            return False
        try:
            self.queue.put_nowait(command)
        except asyncio.QueueFull:
            record.stop_component(command.kind, "recording_queue_full")
            return False
        record.pending += 1
        self.pending_bytes += command.weight
        self.wake.set()
        return True

    def audio(self, record: Recording, pcm: bytes) -> None:
        record.data["received_audio_bytes"] += len(pcm)
        if not record.ended:
            self._put(Command("audio", record, pcm, len(pcm)))

    def transcript(self, record: Recording, event: dict[str, Any]) -> None:
        record.data["received_transcripts"] += 1
        if not record.ended:
            weight = self.settings.max_text_chars * 12 + 65536
            self._put(Command("transcript", record, event, weight))

    def finish(self, record: Recording, reason: str | None = None) -> dict[str, Any]:
        if not record.ended:
            record.ended = True
            if record.data["status"] != "disabled":
                if reason:
                    record.fail(reason)
                elif record.data["status"] == "recording":
                    record.data["status"] = "pending"
            self.wake.set()
        return record.snapshot()

    def lookup(self, session_id: str, client_id: str) -> dict[str, Any] | None:
        record = self.records.get(session_id)
        if record is None or record.data["client_id"] != client_id:
            return None
        if (
            record.finalized
            and record.data["created_at"] + self.settings.recording_retention_hours * 3600 < time.time()
        ):
            return None
        return record.snapshot()

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.settings.recording_enabled,
            "available": self.available,
            "failure": self.failure,
            "queued_bytes": self.pending_bytes,
            "queued_events": self.queue.qsize(),
            "stored_bytes_reserved": self.stored_bytes,
            "retry_count": self.disk.store.retry.retries if self.disk else 0,
            "retry_exhausted": self.disk.store.retry.exhausted if self.disk else 0,
            "pending_sessions": sum(not item.finalized for item in self.records.values()),
        }

    async def _finalize(self) -> None:
        assert self.disk is not None
        for record in list(self.records.values()):
            if record.finalized or not record.ended or record.pending:
                continue
            try:
                if record.opened:
                    receipt = record.snapshot()
                    receipt["audio_complete"] = "audio" not in record.stopped_components
                    receipt["transcript_complete"] = "transcript" not in record.stopped_components
                    if receipt["status"] == "pending":
                        receipt["status"] = "saved"
                    result = await self.disk.call(partial(self.disk.store.finish, record.data["id"], receipt))
                    record.data.update(result)
            except Exception:
                record.stop_component("begin", "write_failed", broken=True)
                logger.warning("recording_finalize_failed")
            record.finalized = True

    async def _work(self) -> None:
        assert self.disk is not None
        flushed_at = time.monotonic()
        cleaned_at = time.monotonic()
        try:
            while True:
                self.wake.clear()
                for _ in range(64):  # Yield regularly even when audio arrives faster than wall time.
                    try:
                        command = self.queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    record = command.recording
                    try:
                        # On overload keep an already accepted prefix; never append after a gap.
                        if command.kind == "begin":
                            await self.disk.call(partial(self.disk.store.begin, command.payload))
                            record.opened = True
                        elif command.kind not in record.failed_components and record.opened:
                            if command.kind == "audio":
                                await self.disk.call(
                                    partial(self.disk.store.audio, record.data["id"], command.payload)
                                )
                                record.data["audio_bytes"] += len(command.payload)
                            else:
                                await self.disk.call(
                                    partial(self.disk.store.transcript, record.data["id"], command.payload)
                                )
                                record.data["transcripts"] += 1
                    except Exception as exc:
                        record.stop_component(
                            command.kind,
                            str(exc) if isinstance(exc, StorageError) else "write_failed",
                            broken=True,
                        )
                        logger.warning("recording_write_failed")
                    finally:
                        self.pending_bytes -= command.weight
                        record.pending -= 1
                        self.queue.task_done()
                await self._finalize()
                now = time.monotonic()
                if now - flushed_at >= self.settings.recording_flush_seconds:
                    errors = await self.disk.call(self.disk.store.flush)
                    for key, components in errors.items():
                        if key in self.records:
                            for component, reason in components.items():
                                self.records[key].stop_component(component, reason, broken=True)
                    flushed_at = now
                if now - cleaned_at >= self.settings.recording_cleanup_seconds:
                    try:
                        removed = await self.disk.call(self.disk.store.prune)
                        for key in removed:
                            if key in self.records and self.records[key].finalized:
                                del self.records[key]
                    except Exception:
                        self.failure = "cleanup_failed"
                    cleaned_at = now
                self.stored_bytes = self.disk.store.used
                for key, item in list(self.records.items()):
                    if item.finalized and item.opened and key not in self.disk.store.records:
                        del self.records[key]
                if self.stopping and self.queue.empty() and all(r.finalized for r in self.records.values()):
                    return
                if not self.queue.empty():
                    await asyncio.sleep(0)
                    continue
                try:
                    await asyncio.wait_for(self.wake.wait(), self.settings.recording_flush_seconds)
                except TimeoutError:
                    pass
        except asyncio.CancelledError:
            raise
        except Exception:
            self.available = False
            self.failure = "writer_failed"
            for record in self.records.values():
                if not record.finalized:
                    record.stop_component("begin", "writer_failed", broken=True)
            logger.warning("recording_worker_failed")

    async def stop(self) -> None:
        self.stopping = True
        self.wake.set()
        for record in self.records.values():
            if not record.ended:
                self.finish(record, "service_stopped")
        if self.worker:
            try:
                await asyncio.wait_for(asyncio.shield(self.worker), self.settings.recording_shutdown_seconds)
            except TimeoutError:
                self.worker.cancel()
                await asyncio.gather(self.worker, return_exceptions=True)
                for record in self.records.values():
                    if not record.finalized:
                        record.fail("shutdown_timeout")
        if self.disk:
            self.disk.stop()
            deadline = time.monotonic() + self.settings.recording_shutdown_seconds
            while not self.disk.closed.is_set() and time.monotonic() < deadline:
                await asyncio.sleep(0.01)
        self.available = False
