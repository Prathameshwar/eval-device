import asyncio
import copy
import time
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from training_contracts import fingerprint
from training_contracts.clinical_cases import ClinicalRuntime, parse_runtime

from .engines import EngineError
from .media import wav


class Coordinator:
    def __init__(self, settings, store, dialogue, speech, transcriber):
        self.settings, self.store = settings, store
        self.dialogue, self.speech, self.transcriber = dialogue, speech, transcriber
        self.data: dict[str, Any] = {}
        self.case = None
        self.claims: dict[str, Any] = {}
        self.deadline = 0.0
        self.lock = asyncio.Lock()
        self.turn_lock = asyncio.Lock()
        self.tasks: set[asyncio.Task[Any]] = set()
        self.video_active = False

    def spawn(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        task.add_done_callback(lambda t: None if t.cancelled() else t.exception())
        return task

    def guard(self):
        if (
            not self.data
            or self.data["status"] not in {"warming", "active"}
            or not self.claims
            or time.time() >= self.claims["exp"]
            or time.monotonic() >= self.deadline
        ):
            raise HTTPException(409, "session_not_active")

    def same(self, claims):
        if (
            not self.data
            or claims["session_id"] != self.data["id"]
            or claims["scenario_hash"] != self.data["scenario_hash"]
        ):
            raise HTTPException(404, "session_not_found")

    async def save(self, files=None):
        await self.store.call("save", copy.deepcopy(self.data), files)

    async def start(self, claims, document, anchor, simulated=False):
        async with self.lock:
            scenario = parse_runtime(document)
            if fingerprint(scenario.model_dump(mode="json")) != claims["scenario_hash"]:
                raise HTTPException(409, "scenario_hash_mismatch")
            if self.data and self.data["id"] == claims["session_id"]:
                self.same(claims)
                self.guard()
                self.renew(claims)
                return self.data
            if (
                self.turn_lock.locked()
                or self.tasks
                or self.video_active
                or (self.data and self.data["status"] in {"warming", "active"})
            ):
                raise HTTPException(409, "laptop_busy")
            # A persisted session never resumes/replays after a process restart.
            try:
                existing = await self.store.call("read", claims["session_id"])
            except Exception:
                existing = None
            if existing is not None:
                raise HTTPException(409, "session_cannot_resume")
            snapshot = None
            if isinstance(scenario, ClinicalRuntime) and hasattr(self.dialogue, "prepare"):
                try:
                    snapshot = self.dialogue.prepare(scenario, claims["language"], claims["session_id"])
                except ValueError:
                    # Reject unavailable/unreviewed translations before admitting a session.
                    raise HTTPException(422, "scenario_language_unavailable") from None
            self.case, self.claims = scenario, claims
            self.deadline = time.monotonic() + min(
                claims["duration_seconds"], claims["session_deadline"] - time.time()
            )
            self.data = {
                "id": claims["session_id"],
                "organization_id": claims["organization_id"],
                "device_id": claims["device_id"],
                "scenario_id": claims["scenario_id"],
                "scenario_hash": claims["scenario_hash"],
                "language": claims["language"],
                "simulated": simulated,
                "status": "warming",
                "reason": "none",
                "anchor_unix_ms": anchor,
                "created_at": time.time(),
                "expires_at": time.time() + 3600 * claims["limits"]["media_retention_hours"],
                "turns": [],
                "video": [],
                "tts_characters": 0,
                "recording_status": "pending",
                "result_event_id": str(uuid4()),
                "sync_status": "pending",
            }
            if snapshot is not None:
                self.data["conversation_snapshot"] = snapshot
            try:
                await self.save()
            except Exception:
                self.data.update(status="failed", reason="storage_failed", recording_status="incomplete")
                raise
            self.spawn(self.warm())
            return self.data

    def renew(self, claims):
        self.same(claims)
        # Late leases cannot resurrect a stopped/expired session.
        self.guard()
        if claims["iat"] >= self.claims["iat"]:
            self.claims = claims

    async def warm(self):
        assert self.case is not None
        try:
            async with self.turn_lock:
                await self.transcriber.check()
                if isinstance(self.case, ClinicalRuntime):
                    await self.dialogue.reply(self.case, "Hello", [], self.data["language"])
                else:
                    await self.dialogue.select(self.case, "Hello", [])
                self.guard()
                text = getattr(self.case.greeting, self.data["language"])
                sound = await self.speech.synthesize(text, self.data["language"])
                self.guard()
                tid = str(uuid4())
                self.data["turns"].append(
                    {
                        "id": tid,
                        "kind": "greeting",
                        "start_ms": 0,
                        "text": "",
                        "answer": text,
                        "topic": "greeting",
                        "playback": "ready",
                        "fallback": False,
                    }
                )
                self.data["tts_characters"] += len(text)
                self.data["status"] = "active"
                await self.save({tid + "-patient.wav": sound})
        except asyncio.CancelledError:
            raise
        except Exception:
            await self.finish("failed", "processing_failed")

    async def turn(self, claims, tid, start_ms, chunks):
        assert self.case is not None
        self.same(claims)
        self.guard()
        if self.turn_lock.locked() or self.data["status"] != "active":
            raise HTTPException(409, "turn_busy")
        if any(t["id"] == tid for t in self.data["turns"]):
            raise HTTPException(409, "turn_already_submitted_do_not_replay")
        if any(t["playback"] in {"ready", "claimed", "playing"} for t in self.data["turns"]):
            raise HTTPException(409, "playback_pending")
        if (
            len(self.data["turns"]) >= self.claims["limits"]["max_turns"]
            or not 0 <= start_ms <= self.claims["duration_seconds"] * 1000
        ):
            raise HTTPException(409, "session_limit")
        async with self.turn_lock:
            row = {
                "id": tid,
                "kind": "interview",
                "start_ms": start_ms,
                "text": "",
                "answer": "",
                "topic": "clarify",
                "playback": "processing",
                "fallback": False,
            }
            self.data["turns"].append(row)
            # Persist admission before accepting non-idempotent microphone input.
            try:
                await self.save()
            except BaseException:
                row["playback"] = "failed"
                await self.finish("failed", "storage_failed")
                raise
            pcm = bytearray()
            began = time.monotonic()
            input_finished_at = None
            budget = asyncio.timeout(
                self.claims["limits"]["max_audio_turn_seconds"] + self.settings.response_seconds
            )

            async def timed_chunks():
                nonlocal input_finished_at
                async for chunk in chunks:
                    yield chunk
                input_finished_at = time.monotonic()
                # Once capture ends, ASR, selection, TTS and persistence share one
                # response deadline rather than receiving separate full budgets.
                budget.reschedule(asyncio.get_running_loop().time() + self.settings.response_seconds)

            try:
                async with budget:
                    self.guard()
                    text, recording, receipt = await self.transcriber.transcribe(
                        timed_chunks(), self.data["language"], self.guard, pcm
                    )
                    self.guard()
                    if input_finished_at is None:
                        raise ValueError("input_not_finished")
                    if len(pcm) > 32000 * self.claims["limits"]["max_audio_turn_seconds"]:
                        raise ValueError("audio_limit")
                    recognized_at = time.monotonic()
                    row.update(
                        text=text,
                        audio_recording=recording,
                        audio_receipt=receipt,
                        input_duration_ms=len(pcm) / 32,
                    )
                    topic = "clarify"
                    answer = getattr(self.case.clarification, self.data["language"])
                    try:
                        if text and isinstance(self.case, ClinicalRuntime):
                            answer = await self.dialogue.reply(
                                self.case, text, self.data["turns"][:-1], self.data["language"]
                            )
                            topic = "clinical"
                        elif text:
                            topic = await self.dialogue.select(self.case, text, self.data["turns"][:-1])
                            if topic != "clarify":
                                answer = getattr(
                                    next(t.answer for t in self.case.topics if t.id == topic),
                                    self.data["language"],
                                )
                    except EngineError:
                        row["fallback"] = True
                    self.guard()
                    selected_at = time.monotonic()
                    row.update(topic=topic, answer=answer)
                    if self.data["tts_characters"] + len(row["answer"]) > self.claims["tts_budget"]:
                        raise ValueError("tts_budget")
                    self.data["tts_characters"] += len(row["answer"])
                    sound = await self.speech.synthesize(row["answer"], self.data["language"])
                    self.guard()
                    synthesized_at = time.monotonic()
                    row.update(
                        playback="ready",
                        input_receive_seconds=round(input_finished_at - began, 3),
                        asr_after_input_seconds=round(recognized_at - input_finished_at, 3),
                        dialogue_seconds=round(selected_at - recognized_at, 3),
                        tts_seconds=round(synthesized_at - selected_at, 3),
                        processing_seconds=round(synthesized_at - input_finished_at, 3),
                    )
                    await self.save({tid + "-learner.wav": wav(pcm), tid + "-patient.wav": sound})
                    self.guard()
                    # These two measurements become durable on the next state save.
                    row["response_save_seconds"] = round(time.monotonic() - synthesized_at, 3)
                    row["response_ready_seconds"] = round(time.monotonic() - input_finished_at, 3)
                    return row
            except BaseException:
                row["playback"] = "failed"
                try:
                    await self.save({tid + "-learner.wav": wav(pcm)})
                except Exception:
                    self.data["recording_status"] = "incomplete"
                await self.finish("failed", "processing_failed")
                raise

    async def playback(self, claims, tid, event, offset):
        self.same(claims)
        self.guard()
        async with self.lock:
            row = next((t for t in self.data["turns"] if t["id"] == tid), None)
            if row is None:
                raise HTTPException(404, "turn_not_found")
            transitions = {
                "claim": ("ready", "claimed"),
                "started": ("claimed", "playing"),
                "finished": ("playing", "played"),
                "failed": ("playing", "failed"),
            }
            previous, target = transitions[event]
            if row["playback"] != previous:
                # Playback claims are deliberately not retried after uncertain delivery.
                raise HTTPException(409, "playback_state_conflict")
            if not 0 <= offset <= self.claims["duration_seconds"] * 1000 or offset < row.get(
                "started_ms", row["start_ms"]
            ):
                raise HTTPException(400, "invalid_capture_clock")
            row["playback"] = target
            row[event + "_ms"] = offset
            await self.save()
            return row

    async def finish(self, status="cancelled", reason="operator_stop"):
        if self.data and self.data["status"] in {"warming", "active"}:
            self.data.update(status=status, reason=reason)
            if not self.data["video"]:
                self.data["recording_status"] = "incomplete"
            for row in self.data["turns"]:
                if row["playback"] in {"claimed", "playing", "ready", "processing"}:
                    row["playback"] = "unknown" if row["playback"] in {"claimed", "playing"} else "suppressed"
            try:
                await self.save()
            except Exception:
                self.data["recording_status"] = "incomplete"

    async def watch(self):
        cleanup_at = time.monotonic() + 60
        while True:
            await asyncio.sleep(0.2)
            if time.monotonic() >= cleanup_at:
                cleanup_at = time.monotonic() + 60
                try:
                    await self.store.call("cleanup")
                except Exception:
                    await self.finish("failed", "storage_failed")
            if self.data and self.data["status"] in {"warming", "active"}:
                try:
                    self.guard()
                except HTTPException:
                    await self.finish(
                        "completed" if time.monotonic() >= self.deadline else "failed",
                        "none" if time.monotonic() >= self.deadline else "authorization_expired",
                    )

    async def close(self):
        await self.finish("failed", "connection_lost")
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.dialogue.close()
