import asyncio
import logging
import time
from dataclasses import dataclass
from functools import partial
from typing import Callable

import httpx

from .audio import AudioChunk
from .config import Settings
from .delivery import CallbackDispatcher
from .engine import Engine, Recognition, create_engine
from .native import SerialWorker
from .recording import Recorder

logger = logging.getLogger("device_audio")


class ServiceError(Exception):
    def __init__(self, code: str, close_code: int = 1013):
        self.code = code
        self.close_code = close_code
        super().__init__(code)


@dataclass
class Work:
    chunk: AudioChunk
    language: str
    queued_at: float
    future: asyncio.Future["Outcome"]
    engine: Engine | None = None


@dataclass(frozen=True)
class Outcome:
    result: Recognition
    inference_seconds: float
    queue_seconds: float


class Runtime:
    def __init__(
        self,
        settings: Settings,
        engine_factory: Callable[[Settings], Engine] = create_engine,
        callback_transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.settings = settings
        self.engine_factory = engine_factory
        self.native: SerialWorker | None = None
        self.stopping = False
        self.failure: str | None = None
        self.engine: Engine | None = None
        self.worker: asyncio.Task[None] | None = None
        self.jobs: asyncio.Queue[Work | None] = asyncio.Queue(settings.max_sessions)
        self.callbacks = CallbackDispatcher(settings, callback_transport)
        self.recorder = Recorder(settings)
        self.active_clients: set[str] = set()
        self.processed_chunks = 0
        self.processed_audio_seconds = 0.0
        self.inference_seconds = 0.0
        self.model_load_seconds = 0.0

    async def start(self) -> None:
        if self.stopping or self.native is not None:
            raise RuntimeError("runtime cannot be restarted")
        started = time.perf_counter()
        self.native = SerialWorker("speech-inference")
        try:
            self.engine = await asyncio.wait_for(
                self.native.call(partial(self.engine_factory, self.settings)),
                self.settings.model_load_timeout_seconds,
            )
            self.model_load_seconds = time.perf_counter() - started
            await self.recorder.start()
            self.callbacks.start()
            self.worker = asyncio.create_task(self._worker(), name="speech-inference")
            logger.info("model_ready model=%s engine=%s", self.settings.model_name, self.settings.engine_name)
        except BaseException:
            self.stopping = True
            self.native.stop()
            self.engine = None
            try:
                await self.recorder.stop()
            finally:
                await self.callbacks.stop()
            raise

    @property
    def ready(self) -> bool:
        return (
            not self.stopping
            and self.failure is None
            and self.engine is not None
            and self.worker is not None
            and not self.worker.done()
        )

    def acquire(self, client_id: str) -> None:
        if not self.ready:
            raise ServiceError("not_ready")
        if client_id in self.active_clients:
            raise ServiceError("client_already_streaming")
        if len(self.active_clients) >= self.settings.max_sessions:
            raise ServiceError("session_capacity")
        self.active_clients.add(client_id)

    async def transcribe(
        self,
        chunk: AudioChunk,
        language: str,
        queued_at: float | None = None,
        *,
        engine: Engine | None = None,
    ) -> Outcome:
        if not self.ready:
            raise ServiceError("not_ready")
        admitted_at = time.perf_counter() if queued_at is None else queued_at
        remaining = self.settings.inference_timeout_seconds - (time.perf_counter() - admitted_at)
        if remaining <= 0:
            raise ServiceError("inference_timeout")
        future: asyncio.Future[Outcome] = asyncio.get_running_loop().create_future()
        try:
            self.jobs.put_nowait(Work(chunk, language, admitted_at, future, engine))
        except asyncio.QueueFull:
            raise ServiceError("inference_capacity") from None
        try:
            async with asyncio.timeout(remaining):
                return await future
        except TimeoutError:
            raise ServiceError("inference_timeout") from None
        finally:
            # Cancelling this future never releases the native inference worker early.
            if not future.done():
                future.cancel()

    async def _worker(self) -> None:
        assert self.engine is not None and self.native is not None
        while True:
            work = await self.jobs.get()
            if work is None:
                self.jobs.task_done()
                return
            try:
                if work.future.cancelled():
                    continue
                started = time.perf_counter()
                try:
                    result = await asyncio.wait_for(
                        self.native.call(
                            partial((work.engine or self.engine).transcribe, work.chunk, work.language)
                        ),
                        self.settings.inference_timeout_seconds,
                    )
                except TimeoutError:
                    # Cancellation cannot stop a native call. Retire this worker and
                    # fail readiness; never run another model beside the stuck one.
                    self.failure = "native_inference_timeout"
                    self.native.stop()
                    if not work.future.done():
                        work.future.set_exception(ServiceError("inference_timeout"))
                    while not self.jobs.empty():
                        pending = self.jobs.get_nowait()
                        if pending is not None and not pending.future.done():
                            pending.future.set_exception(ServiceError("not_ready"))
                        self.jobs.task_done()
                    return
                elapsed = time.perf_counter() - started
                self.processed_chunks += int(result.final)
                self.processed_audio_seconds += work.chunk.duration_seconds
                self.inference_seconds += elapsed
                if len(result.text) > self.settings.max_text_chars:
                    raise ValueError("result limit")
                if not work.future.done():
                    work.future.set_result(Outcome(result, elapsed, started - work.queued_at))
            except asyncio.CancelledError:
                if not work.future.done():
                    work.future.set_exception(ServiceError("service_stopped"))
                raise
            except Exception:
                logger.warning("inference_failed")
                if not work.future.done():
                    work.future.set_exception(ServiceError("inference_failed", 1011))
            finally:
                self.jobs.task_done()
                del work

    async def stop(self) -> None:
        self.stopping = True
        try:
            if self.worker is not None:
                try:
                    async with asyncio.timeout(self.settings.inference_shutdown_seconds):
                        await self.jobs.put(None)
                        await asyncio.shield(self.worker)
                except TimeoutError:
                    pass
                finally:
                    if not self.worker.done():
                        self.worker.cancel()
                    await asyncio.gather(self.worker, return_exceptions=True)
                    while not self.jobs.empty():
                        work = self.jobs.get_nowait()
                        if work is not None and not work.future.done():
                            work.future.set_exception(ServiceError("service_stopped"))
                        self.jobs.task_done()
        finally:
            if self.native:
                self.native.stop()
            self.engine = None
            try:
                await self.recorder.stop()
            finally:
                await self.callbacks.stop()
