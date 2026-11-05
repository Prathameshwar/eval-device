"""Nonblocking intake, independent disk persistence and bounded background HTTP uploads."""

import asyncio
import base64
import hashlib
import json
import queue
import threading
import time
from datetime import datetime

import httpx

from .history_outbox import Outbox


def identity_hint(token):
    # This is only a local namespace hint. The server-verified identity is checked before uploads.
    part = token.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
    issuer, subject = claims["iss"], claims["sub"]
    if not isinstance(issuer, str) or not isinstance(subject, str) or not issuer or not subject:
        raise ValueError("Invalid identity")
    return issuer, subject


def merge_history(remote, pending, limit=10):
    records = {row["turn_key"]: row for row in pending if row.get("outcome") == "completed"}
    records.update({row["turn_key"]: row for row in remote if row.get("outcome") == "completed"})
    return sorted(records.values(), key=lambda row: (row["occurred_at"], row["turn_key"]), reverse=True)[
        :limit
    ]


class HistoryRecorder:
    def __init__(self, settings, emit, *, transport=None, outbox_factory=Outbox, busy=lambda: False):
        self.busy = busy
        self.settings = settings.model_copy(deep=True)
        self.emit, self.transport, self.factory = emit, transport, outbox_factory
        self.queue = queue.Queue(maxsize=settings.history_queue_records)
        self.commands = queue.Queue(maxsize=settings.history_queue_records)
        self.stopping, self.ready, self.wake = threading.Event(), threading.Event(), threading.Event()
        self.pending_bytes = 0
        self.guard = threading.Lock()
        self.status_guard = threading.Lock()
        self.failures = 0
        self.outbox = None
        self.identity = (
            ("urn:pms:device", str(settings.device_id))
            if settings.pms_token.get_secret_value().startswith("dev_") and settings.device_id
            else identity_hint(settings.pms_token.get_secret_value())
        )
        material = [
            settings.pms_url.rstrip("/"),
            str(settings.organization_id),
            str(settings.department_id),
            *self.identity,
        ]
        self.namespace = hashlib.sha256(json.dumps(material).encode()).hexdigest()
        self.base = f"/api/v1/organizations/{settings.organization_id}/llm"
        self.disk = threading.Thread(target=self._disk, name="history-disk", daemon=True)
        self.uploader = threading.Thread(target=self._upload, name="history-upload", daemon=True)
        self.disk.start()
        self.uploader.start()

    def notify(self, status, key=None):
        if status == "not_saved":
            with self.status_guard:
                self.failures += 1
        try:
            self.emit("history_status", {"status": status, "turn_key": key})
        except Exception:
            pass  # A saturated/closing UI must never fail a turn or kill the writer.

    def enqueue(self, record, metrics=None):
        # Bound without JSON serialization or filesystem access on the conversation task.
        weight = 4096 + 4 * (len(record["input_text"]) + len(record.get("response_text") or ""))
        with self.guard:
            if self.stopping.is_set() or self.pending_bytes + weight > self.settings.history_queue_bytes:
                self.notify("not_saved", record["turn_key"])
                return False
            try:
                self.queue.put_nowait((record, metrics, weight))
            except queue.Full:
                self.notify("not_saved", record["turn_key"])
                return False
            self.pending_bytes += weight
        self.notify("pending_local_save", record["turn_key"])
        return True

    def _disk(self):
        try:
            self.outbox = self.factory(
                self.settings.history_dir,
                self.namespace,
                max_records=self.settings.history_max_records,
                max_bytes=self.settings.history_max_bytes,
                max_age=self.settings.history_pending_hours * 3600,
            )
            if self.outbox.bad_count:
                self.notify("incomplete_files")
        except Exception:
            self.notify("not_saved")
        finally:
            self.ready.set()
        sweep = time.monotonic()
        try:
            while not self.stopping.is_set() or not self.queue.empty() or not self.commands.empty():
                try:
                    command, key = self.commands.get_nowait()
                except queue.Empty:
                    pass
                else:
                    try:
                        if self.outbox:
                            if command == "ack":
                                self.outbox.acknowledge(key)
                                self.notify("saved_to_pms", key)
                            else:
                                self.outbox.reject(key)
                                self.notify("upload_rejected", key)
                    except Exception:
                        self.notify("cleanup_failed" if command == "ack" else "upload_rejected", key)
                    finally:
                        self.commands.task_done()
                try:
                    record, metrics, weight = self.queue.get(timeout=0.1)
                except queue.Empty:
                    record = None
                if record is not None:
                    try:
                        if self.outbox is None:
                            raise OSError("Outbox unavailable")
                        self.outbox.put(record, metrics)
                        self.notify("saved_locally", record["turn_key"])
                        self.wake.set()
                    except Exception:
                        self.notify("not_saved", record["turn_key"])
                    finally:
                        with self.guard:
                            self.pending_bytes -= weight
                        self.queue.task_done()
                if self.outbox and time.monotonic() - sweep > 60:
                    try:
                        if self.outbox.expire():
                            self.notify("pending_expired")
                    except Exception:
                        self.notify("cleanup_failed")
                    sweep = time.monotonic()
        finally:
            if self.outbox:
                self.outbox.close()

    def _upload(self):
        self.ready.wait()
        if not self.outbox:
            return
        delay = 1
        headers = {"Authorization": "Bearer " + self.settings.pms_token.get_secret_value()}
        with httpx.Client(
            base_url=self.settings.pms_url,
            headers=headers,
            timeout=5,
            trust_env=False,
            transport=self.transport,
        ) as client:
            while not self.stopping.is_set():
                if self.busy():
                    self.stopping.wait(0.5)
                    continue
                pending = [item for item in self.outbox.snapshot() if item["state"] == "pending"]
                if not pending:
                    self.wake.wait(0.5)
                    self.wake.clear()
                    continue
                item = min(pending, key=lambda value: value["record"]["occurred_at"])
                key = item["record"]["turn_key"]
                try:
                    identity = client.get(self.base + "/local-conversation-turns/identity")
                    if identity.status_code in {401, 403}:
                        self.notify("authentication_required", key)
                        self.stopping.wait(30)
                        continue
                    identity.raise_for_status()
                    verified = identity.json()
                    if not isinstance(verified, dict):
                        raise ValueError("Invalid identity response")
                    if (verified.get("issuer"), verified.get("subject")) != self.identity:
                        raise ValueError("Identity changed")
                    if verified.get("organization_id") != str(self.settings.organization_id):
                        raise ValueError("Organization changed")
                    # Old metrics keep their original short admission window. Failure never blocks archival.
                    metrics = item.get("metrics")
                    if (
                        metrics
                        and time.time() - datetime.fromisoformat(metrics["occurred_at"]).timestamp() < 54 * 60
                    ):
                        try:
                            client.post(self.base + "/local-turns", json=metrics)
                        except httpx.HTTPError:
                            pass
                    response = client.post(self.base + "/local-conversation-turns", json=item["record"])
                    if response.status_code in {401, 403}:
                        self.notify("authentication_required", key)
                        self.stopping.wait(30)
                        continue
                    if response.status_code in {409, 410, 413, 422}:
                        self.commands.put_nowait(("reject", key))
                    else:
                        response.raise_for_status()
                        acknowledgement = response.json()
                        if not isinstance(acknowledgement, dict) or acknowledgement.get("turn_key") != key:
                            raise ValueError("Invalid acknowledgement")
                        self.commands.put_nowait(("ack", key))
                    delay = 1
                    # Wait for the disk receipt, even on a slow disk, instead of flooding PMS with duplicates.
                    while any(
                        value["record"]["turn_key"] == key and value["state"] == "pending"
                        for value in self.outbox.snapshot()
                    ):
                        if self.stopping.wait(0.05):
                            break
                except (httpx.HTTPError, ValueError, KeyError, TypeError, queue.Full):
                    self.notify("saved_locally", key)
                    self.stopping.wait(delay)
                    delay = min(60, delay * 2)

    def pending(self):
        if not self.outbox:
            return []
        return [
            {
                **item["record"],
                "save_status": {
                    "pending": "saved_locally",
                    "rejected": "upload_rejected",
                    "acknowledged": "saved_to_pms",
                }[item["state"]],
            }
            for item in self.outbox.snapshot()
        ]

    async def close(self):
        self.stopping.set()
        self.wake.set()
        # Disk flush has a bounded budget; network shutdown cannot consume it.
        await asyncio.to_thread(self.disk.join, 2)
        if self.disk.is_alive():
            self.notify("flush_incomplete")
        await asyncio.to_thread(self.uploader.join, 0.1)


class MetricsReporter:
    """Bounded, retained metadata task when text archival is disabled."""

    def __init__(self, send, emit):
        self.send, self.emit = send, emit
        self.queue = asyncio.Queue(maxsize=64)
        self.task = None

    def enqueue(self, event):
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            self.emit("history_status", {"status": "metrics_not_saved", "turn_key": event["turn_key"]})
            return
        if self.task is None:
            self.task = asyncio.create_task(self.run())

    async def run(self):
        while True:
            event = await self.queue.get()
            try:
                await self.send(event)
            except Exception:
                self.emit("state", "Answer delivered; PMS did not record this local turn's metrics")
            finally:
                self.queue.task_done()

    async def close(self):
        if self.task:
            try:
                await asyncio.wait_for(self.queue.join(), 2)
            except TimeoutError:
                pass
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
