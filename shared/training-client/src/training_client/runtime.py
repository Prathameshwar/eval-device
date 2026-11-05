"""Application-independent conversation lifecycle and physical playback coordination.

Call asynchronous operations on one event loop. Observers receive notifications;
they never have to consume an event to make playback or persistence happen.
"""

import asyncio
import threading
import time
from contextlib import suppress
from uuid import uuid4

from .audio_client import connection
from .controller import Controller
from .listening import Listener, Utterance
from .performance import TurnTiming
from .pms_client import ClientError
from .recording import CameraRecording
from .sessions import SessionSupervisor
from .speech import Speaker

SPEECH_STALL_LIMIT_MS = 5000


class Runtime:
    def __init__(
        self,
        settings,
        observe=None,
        *,
        controller=None,
        speaker=None,
        listener_factory=None,
        camera=None,
        clock=time.monotonic,
    ):
        self.settings = settings
        self.observe = observe or (lambda *_: None)
        self.observer_failures = 0
        self.inference = getattr(controller, "inference", None) or connection(settings)
        self.speaker = speaker or Speaker(
            enabled=settings.speaker_output,
            inference=self.inference,
            emit=self.emit,
        )
        self.speaker.prefer(settings.voice)
        self.controller = controller
        if controller is not None:
            controller.emit = self.emit
        self.listener_factory, self.clock = listener_factory or Listener, clock
        self.send_now = threading.Event()
        self.work = None
        self.capture_quality = None
        self.playback_progress = self.playback_stalled_at = None
        self.operation = None
        self.closing = self.finishing = False
        self.retrying = False
        self.camera = camera or CameraRecording(can_start=lambda: not self.closing and not self.finishing)
        self.sessions = None

    async def initialize(self):
        if self.closing:
            raise ClientError("This client has been closed")
        if self.controller is None:
            self.controller = Controller(self.settings, self.emit, inference=self.inference)
        if self.sessions is None:
            self.sessions = SessionSupervisor(self)
            self.sessions.start()
        return self.controller

    async def prepare(self):
        await self.initialize()
        self._claim()
        try:
            if self.sessions and self.sessions.assigned():
                raise ClientError("Complete the assigned session before reloading practice")
            return await self._prepare()
        finally:
            self.operation = None

    async def _prepare(self):
        await self._stop_media()
        if self.settings.use_pms_models:
            self.controller.use_models(await self.controller.pms.model_config())
        await self.controller.refresh_local_models()
        options = await self.controller.pms.scenario_options()
        return (
            {
                "categories": [],
                "patients": [],
                "cases": [],
                "scenarios": options["items"],
                "default": options.get("default"),
            },
            options.get("selection"),
        )

    async def save_selection(self, payload, *, scenario=True):
        self._claim()
        try:
            if self.sessions and self.sessions.blocks_setup():
                raise ClientError("Use the assigned session before changing practice setup")
            await self._stop_media()
            pms = self.controller.pms
            selected = await (
                pms.save_scenario_selection(payload) if scenario else pms.save_selection(payload)
            )
            self.controller.use_selection(selected)
            if getattr(self.controller, "sync", None):
                await pms.ensure_conversation()
            return selected
        finally:
            self.operation = None

    async def _stop_media(self):
        self.speaker.stop()
        await self.camera.close()

    async def reload_models(self):
        self._claim()
        try:
            if self.sessions and self.sessions.assigned():
                raise ClientError("Complete the assigned session before changing models")
            await self._stop_media()
            route = await self.controller.pms.model_config()
            await self.controller.refresh_local_models()
            self.controller.use_models(route)
            return route
        finally:
            self.operation = None

    async def reset_conversation(self):
        self._claim()
        try:
            if self.sessions and self.sessions.assigned():
                raise ClientError("Complete the assigned session before starting another conversation")
            await self._stop_media()
            self.controller.reset()
            if getattr(self.controller, "sync", None):
                await self.controller.pms.ensure_conversation()
        finally:
            self.operation = None

    def notify(self, kind, value):
        try:
            self.observe(kind, value)
        except Exception:
            # A missing/busy frontend must never disable safety or output actions.
            # Keep only a count, never potentially sensitive observer exceptions.
            self.observer_failures += 1

    def emit(self, kind, value):
        if kind == "retrying":
            self.retrying = bool(value)
            if self.retrying:
                self.speaker.stop()
        if kind in {"speak", "prepare_speech"}:
            generation = getattr(self.controller, "_conversation_generation", 0)
            if (
                self.closing
                or self.finishing
                or self.retrying
                or value.get("generation", generation) != generation
            ):
                return
            sync = getattr(self.controller, "sync", None)
            progress = self.speaker.progress
            accepted = self.speaker.speak(
                value["text"],
                value["language"],
                value.get("gender", "male"),
                **({"gate": value["gate"]} if value.get("gate") else {}),
                **({"performance": value["performance"]} if value.get("performance") else {}),
                **({"archive": (sync, value["archive_id"])} if sync and value.get("archive_id") else {}),
            )
            if accepted:
                self.notify("speech_started", {**value, "progress": progress})
            return
        self.notify(kind, value)

    def capture_allowed(self):
        if not getattr(self.speaker, "playing", self.speaker.speaking):
            self.playback_progress = self.playback_stalled_at = None
            return True
        now, progress = self.clock(), self.speaker.progress
        if progress != self.playback_progress:
            self.playback_progress, self.playback_stalled_at = progress, now
            return False
        if self.playback_stalled_at is None:
            self.playback_stalled_at = now
            return False
        return (now - self.playback_stalled_at) * 1000 >= SPEECH_STALL_LIMIT_MS

    def _claim(self):
        if (
            self.closing
            or self.finishing
            or self.operation is not None
            or (self.sessions is not None and (self.sessions.starting or self.sessions.remote_busy))
        ):
            raise ClientError("A client operation is already active or stopping")
        self.operation = asyncio.current_task()

    async def text_turn(self, text):
        if self.closing or self.finishing:
            raise ClientError("Practice is stopping")
        if self.work is not None:
            self.enqueue_text(text)
            return None
        self._claim()
        try:
            self.speaker.stop()
            return await self.controller.text_turn(text)
        except BaseException:
            self.speaker.stop()
            raise
        finally:
            self.operation = None

    def enqueue_text(self, text):
        if self.closing or self.finishing or self.work is None:
            raise ClientError("The microphone session is no longer accepting questions")
        text = text.strip()
        if not text or len(text) > 8000:
            raise ClientError("Enter a question of 1 to 8,000 characters")
        try:
            self.work.put_nowait(text)
        except asyncio.QueueFull:
            raise ClientError("Questions are still being processed; ask again in a moment") from None
        self.speaker.stop()

    async def listen(self):
        self._claim()
        self.speaker.stop()
        self.send_now.clear()
        self.playback_progress = self.playback_stalled_at = None
        try:
            await self._listen()
        finally:
            self.speaker.stop()
            self.operation = None

    async def _listen(self):
        self.emit("state", "Preparing voice and model…")
        await self.controller.preflight()
        if hasattr(self.speaker, "warm"):
            ready = self.speaker.warm(
                self.settings.language, getattr(self.controller, "voice_gender", "male")
            )
            if ready is not None:
                async with asyncio.timeout(30):
                    while not ready.is_set():
                        await asyncio.sleep(0.02)
        sync = getattr(self.controller, "sync", None)
        if sync:
            await self.controller.pms.ensure_conversation("speech")
        listener = self.listener_factory(
            self.settings,
            self.emit,
            open_gate=self.capture_allowed,
            send_now=self.send_now,
        )
        self.work = listener.ready
        archive_id = sync.current if sync else None
        stream_id = str(uuid4())
        if sync:
            sync.busy(True)
            sync.audio_start(archive_id, stream_id)
            listener.on_audio = lambda frame: sync.audio(archive_id, stream_id, frame)
        reader = asyncio.create_task(listener.run())
        try:
            while True:
                item = await listener.ready.get()
                if item is None:
                    raise listener.failure or ClientError("Microphone stopped unexpectedly")
                self.emit("queued", listener.ready.qsize())
                try:
                    timing = item.performance if isinstance(item, Utterance) else TurnTiming("text")
                    timing.mark("worker")
                    self.controller.performance = timing
                    await self.controller.preflight()
                    timing.mark("preflight")
                    if isinstance(item, Utterance):
                        self.capture_quality = item.quality
                        self.emit("capture", item.quality)
                        try:
                            await self.controller.turn(
                                item.frames(), **({"record_audio": False} if sync else {})
                            )
                        finally:
                            if item.quality.blocks:
                                self.emit("capture_quality", item.quality.concerns())
                    else:
                        await self.controller.text_turn(item)
                except ClientError as error:
                    if error.retry_exhausted:
                        raise
                    self.emit("turn_failed", str(error))
                finally:
                    self.controller.performance = None
        finally:
            self.work = None
            reader.cancel()
            await asyncio.gather(reader, return_exceptions=True)
            if sync:
                if listener.lost or listener.failure:
                    sync.submit("incomplete", archive_id)
                sync.audio_end(archive_id, stream_id)
                sync.busy(False)

    def pause(self):
        self.speaker.stop()
        if self.operation is not None:
            self.operation.cancel()

    async def stop_work(self):
        self.finishing = True
        task = self.operation
        self.pause()
        if task is not None and task is not asyncio.current_task():
            await asyncio.gather(task, return_exceptions=True)
        if self.camera is not None:
            await self.camera.close()

    async def close(self):
        self.closing = True
        try:
            await self.stop_work()
        finally:
            try:
                if self.sessions is not None:
                    with suppress(Exception):
                        await asyncio.wait_for(self.sessions.close(), 3)
            finally:
                try:
                    await asyncio.to_thread(self.speaker.close)
                finally:
                    if self.controller is not None:
                        await self.controller.close()
