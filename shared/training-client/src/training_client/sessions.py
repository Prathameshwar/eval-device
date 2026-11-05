"""Assigned-session ownership, leases and shutdown without frontend timers."""

import asyncio
import time
from datetime import UTC, datetime
from uuid import uuid4

from .pms_client import ClientError

BASE = "/api/v1/device/session-queue"


class SessionSupervisor:
    def __init__(self, runtime, *, clock=time.monotonic):
        self.runtime = runtime
        self.clock = clock
        self.runtime_id = str(uuid4())
        self.active = self.next = None
        self.starting = self.finishing = self.remote_busy = False
        self.last_ok = 0.0
        self.deadline = None
        self.task = self.poll_task = None
        self.closed = False
        self.finish_outcome = "completed"
        self._finish_lock = asyncio.Lock()
        self._generation = 0
        self._begin_task = None
        self._claim_id = None

    @property
    def controller(self):
        return self.runtime.controller

    def assigned(self):
        return self.active is not None or self.starting or self.finishing

    def standalone_active(self):
        return not self.active and bool(self.controller.pms.conversation)

    def blocks_setup(self):
        return self.assigned() or self.remote_busy or (self.next is not None and not self.standalone_active())

    async def call(self, path, body):
        return await self.controller.pms.json("POST", BASE + path, json=body)

    def start(self):
        if self.task is None and self.runtime.settings.device_id:
            self.task = asyncio.create_task(self.run())

    def remaining(self):
        return max(0, int(self.deadline - self.clock())) if self.deadline is not None else 0

    def expired(self):
        return bool(self.active) and (
            self.clock() - self.last_ok >= 20 or (self.deadline is not None and self.clock() >= self.deadline)
        )

    async def poll(self):
        return await self.call(
            "/poll",
            {
                "runtime_id": self.runtime_id,
                "session_id": self.active["id"] if self.active else None,
                "runtime_state": "assigned"
                if self.active
                else "standalone"
                if self.standalone_active()
                else "idle",
            },
        )

    async def receive(self, data):
        self.last_ok = self.clock()
        remote = data.get("active")
        self.remote_busy = bool(remote and (not self.active or remote["id"] != self.active["id"]))
        if self.active:
            if not remote or remote["id"] != self.active["id"] or remote["status"] != "active":
                await self.finish()
        else:
            self.next = None if remote else data.get("next")
        self.runtime.emit("queue_snapshot", data)

    async def run(self):
        next_poll = 0.0
        try:
            while not self.closed:
                if self.expired() and not self.finishing:
                    outcome = (
                        "completed"
                        if self.deadline is not None and self.clock() >= self.deadline
                        else "failed"
                    )
                    try:
                        await self.finish(outcome)
                    except Exception:
                        pass  # Work is already stopped; retry only the idempotent finish.
                elif self.finishing:
                    try:
                        await self.finish(self.finish_outcome)
                    except Exception:
                        await asyncio.sleep(2)
                if self.poll_task and self.poll_task.done():
                    task, self.poll_task = self.poll_task, None
                    try:
                        if not task.cancelled():
                            await self.receive(task.result())
                    except Exception:
                        self.runtime.emit("queue_unavailable", None)
                if (
                    self.poll_task is None
                    and not self.finishing
                    and (not self.starting or self.active)
                    and self.clock() >= next_poll
                ):
                    self.poll_task = asyncio.create_task(self.poll())
                    next_poll = self.clock() + 2
                # Lease enforcement proceeds even while an HTTP request is stalled.
                await asyncio.sleep(0.25)
        finally:
            if self.poll_task:
                poll, self.poll_task = self.poll_task, None
                poll.cancel()
                await asyncio.gather(poll, return_exceptions=True)

    def activate(self, result):
        self.active, self.next = result, None
        self.last_ok = self.clock()
        expires = datetime.fromisoformat(result["expires_at"].replace("Z", "+00:00"))
        started = datetime.fromisoformat(result["started_at"].replace("Z", "+00:00"))
        stamp = datetime.now(UTC)
        remaining = min(
            (expires - stamp).total_seconds(), result["duration_seconds"] - (stamp - started).total_seconds()
        )
        self.deadline = self.last_ok + max(0, remaining)

    async def begin(self):
        if (
            self.closed
            or self.runtime.closing
            or self.runtime.finishing
            or self.remote_busy
            or getattr(self.runtime, "operation", None) is not None
            or self.assigned()
            or self.standalone_active()
            or not self.next
        ):
            raise ClientError("No assigned session is ready to begin")
        assignment = self.next.copy()
        if assignment["language"] not in self.runtime.settings.language_choices:
            raise ClientError(
                "The assigned language is unavailable on this device. Update its language setup."
            )
        self.starting = True
        self._begin_task = asyncio.current_task()
        self._claim_id = assignment["id"]
        generation = self._generation
        pms = self.controller.pms
        try:
            if self.poll_task:
                poll, self.poll_task = self.poll_task, None
                poll.cancel()
                await asyncio.gather(poll, return_exceptions=True)
            options = await pms.scenario_options()
            result = await self.call(f"/{assignment['id']}/begin", {"runtime_id": self.runtime_id})
            if generation != self._generation or result["id"] != assignment["id"]:
                raise ClientError("Assigned session changed while preparing practice")
            self.activate(result)
            if result["language"] not in self.runtime.settings.language_choices:
                raise ClientError(
                    "The assigned language is unavailable on this device. Update its language setup."
                )
            case = next((row for row in options["items"] if row["id"] == result["scenario_id"]), None)
            if not case:
                options = await pms.scenario_options()
                case = next((row for row in options["items"] if row["id"] == result["scenario_id"]), None)
            if not case:
                raise ClientError("The assigned case is unavailable. Ask the instructor to update the queue.")
            selection = options.get("selection")
            saved = await pms.save_scenario_selection(
                {
                    "expected_revision": selection["revision"] if selection else 0,
                    "scenario_id": result["scenario_id"],
                    "language": result["language"],
                    "vitals": case["vitals"],
                }
            )
            if generation != self._generation:
                raise asyncio.CancelledError()
            self.controller.use_selection(saved)
            pms.assigned_session_id = assignment["id"]
            await pms.ensure_conversation()
            if generation != self._generation or self.finishing or self.closed or self.expired():
                raise ClientError("Assigned session ended while preparing practice")
            self.runtime.emit(
                "catalog",
                (
                    {
                        "categories": [],
                        "patients": [],
                        "cases": [],
                        "scenarios": options["items"],
                        "default": options.get("default"),
                    },
                    saved,
                ),
            )
            self.runtime.emit("queue_begun", (result, saved))
            return result, saved
        except BaseException:
            try:
                if generation == self._generation:
                    await self.finish("failed")
            except Exception:
                pass  # Keep the exact pending claim for idempotent finish retry.
            finally:
                self.runtime.emit("queue_start_failed", None)
            raise
        finally:
            self.starting = False
            self._begin_task = None

    async def finish(self, outcome="completed"):
        generation = self._generation
        already_finishing = self.finishing
        async with self._finish_lock:
            if generation != self._generation or (already_finishing and not self.finishing):
                return  # Another finisher already handled this generation.
            if not self.finishing:
                self.finish_outcome = outcome
                self._generation += 1
            self.finishing = True
            self.runtime.finishing = True
            self.runtime.emit("queue_stopping", None)
            try:
                if self._begin_task is not None and self._begin_task is not asyncio.current_task():
                    self._begin_task.cancel()
                    await asyncio.gather(self._begin_task, return_exceptions=True)
                await self.runtime.stop_work()
                pms = self.controller.pms
                identity = self.active["id"] if self.active else self._claim_id
                if identity:
                    await self.call(
                        f"/{identity}/finish",
                        {
                            "runtime_id": self.runtime_id,
                            "outcome": self.finish_outcome,
                        },
                    )
                if pms.conversation:
                    await pms.close_conversation(pms.conversation["context"]["conversation_id"])
                    pms.conversation = None
                pms.assigned_session_id = None
                self.controller.reset()
                self.active = self.next = self.deadline = None
                self._claim_id = None
                self.finishing = self.runtime.finishing = False
                self.runtime.emit("queue_finished", None)
            except Exception:
                self.runtime.emit("queue_finish_failed", self.finish_outcome)
                raise

    async def close(self):
        self.closed = True
        if self.task and self.task is not asyncio.current_task():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None
        if self.active or self._claim_id:
            await self.finish("cancelled")
