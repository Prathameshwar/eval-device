import asyncio
import json
import math
import time
from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import UUID, uuid4

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .audio import SAMPLE_RATE, AudioChunk, Segmenter, VoiceDetector
from .delivery import Delivery
from .engine import Engine, StreamingEngine
from .recording import Recording
from .runtime import Runtime, ServiceError
from .streaming import BLOCK_MS, StreamingSegmenter


class StartMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    type: Literal["start"]
    version: Literal[1] = 1
    format: Literal["pcm_s16le"] = "pcm_s16le"
    sample_rate: Literal[16000] = 16000
    channels: Literal[1] = 1
    language: Literal["auto", "hi", "en"] = "auto"
    stream_id: UUID = Field(default_factory=uuid4)


class Session:
    def __init__(
        self,
        websocket: WebSocket,
        runtime: Runtime,
        client_id: str,
        detector: VoiceDetector | None = None,
    ):
        self.websocket = websocket
        self.runtime = runtime
        self.settings = runtime.settings
        self.client_id = client_id
        self.session_id = str(uuid4())
        self.segmenter: Segmenter | StreamingSegmenter
        self.session_engine: Engine | None = None
        queue_size = self.settings.chunk_queue_size
        if self.settings.streaming:
            self.segmenter = StreamingSegmenter(self.settings, detector)
            self.session_engine = cast(StreamingEngine, runtime.engine).new_session()
            queue_size = math.ceil(self.settings.streaming_queue_ms / BLOCK_MS)
        else:
            self.segmenter = Segmenter(self.settings, detector)
        self.chunks: asyncio.Queue[tuple[AudioChunk, float] | None] = asyncio.Queue(queue_size)
        self.send_lock = asyncio.Lock()
        self.notifications: set[asyncio.Task[None]] = set()
        self.notification_error: BaseException | None = None
        self.start: StartMessage | None = None
        self.processed = 0
        self.transcripts = 0
        self.delivery_failures = 0
        self.recording: Recording | None = None

    async def send(self, payload: dict[str, Any]) -> None:
        try:
            async with asyncio.timeout(self.settings.send_timeout_seconds):
                async with self.send_lock:
                    await self.websocket.send_json(payload)
        except TimeoutError:
            raise ServiceError("slow_consumer") from None

    async def run(self) -> None:
        try:
            message = await asyncio.wait_for(self.websocket.receive(), self.settings.idle_timeout_seconds)
            if message["type"] == "websocket.disconnect":
                raise WebSocketDisconnect(message.get("code", 1000))
            text = message.get("text")
            if not isinstance(text, str) or len(text) > 1024:
                raise ServiceError("start_required", 1008)
            self.start = StartMessage.model_validate_json(text)
        except (ValidationError, ValueError):
            raise ServiceError("invalid_start", 1008) from None
        except TimeoutError:
            raise ServiceError("idle_timeout", 1008) from None
        if self.start.language not in self.settings.supported_languages:
            raise ServiceError("unsupported_language", 1008)
        self.recording = self.runtime.recorder.begin(
            self.session_id, self.client_id, str(self.start.stream_id), self.start.language
        )
        await self.send(
            {
                "type": "ready",
                "version": 1,
                "session_id": self.session_id,
                "stream_id": str(self.start.stream_id),
                "model": self.settings.model_name,
                "engine": self.settings.engine_name,
                "supported_languages": self.settings.supported_languages,
                "device": self.settings.inference_device,
                "compute_type": self.settings.compute_type,
                "sample_rate": SAMPLE_RATE,
                "format": "pcm_s16le",
                "channels": 1,
                "max_frame_bytes": self.settings.max_frame_bytes,
                "max_audio_seconds": self.settings.max_audio_seconds,
                "callback_configured": self.settings.callback_url is not None,
                "console_output": self.settings.console_output,
                "recording": self.recording.snapshot(),
            }
        )
        reader = asyncio.create_task(self._receive(), name="audio-receive")
        consumer = asyncio.create_task(self._consume(), name="audio-consume")
        try:
            done, _ = await asyncio.wait({reader, consumer}, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
            if not reader.done():
                raise ServiceError("processing_stopped", 1011)
            try:
                async with asyncio.timeout(self.settings.drain_timeout_seconds):
                    await consumer
            except TimeoutError:
                raise ServiceError("drain_timeout") from None
        finally:
            reader.cancel()
            consumer.cancel()
            await asyncio.gather(reader, consumer, return_exceptions=True)
            for task in list(self.notifications):
                task.cancel()
            await asyncio.gather(*self.notifications, return_exceptions=True)

    def _enqueue(self, chunks: list[AudioChunk]) -> None:
        for chunk in chunks:
            try:
                self.chunks.put_nowait((chunk, time.perf_counter()))
            except asyncio.QueueFull:
                raise ServiceError("audio_backlog") from None

    async def _receive(self) -> None:
        deadline = time.monotonic() + self.settings.max_session_seconds
        controls = 0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ServiceError("session_limit", 1008)
            try:
                message = await asyncio.wait_for(
                    self.websocket.receive(), min(remaining, self.settings.idle_timeout_seconds)
                )
            except TimeoutError:
                raise ServiceError("idle_or_session_timeout", 1008) from None
            if message["type"] == "websocket.disconnect":
                raise WebSocketDisconnect(message.get("code", 1000))
            pcm = message.get("bytes")
            if pcm is not None:
                if not pcm or len(pcm) > self.settings.max_frame_bytes or len(pcm) % 2:
                    raise ServiceError("invalid_audio_frame", 1009)
                samples = self.segmenter.total_samples + len(pcm) // 2
                if samples > self.settings.max_audio_seconds * SAMPLE_RATE:
                    raise ServiceError("audio_limit", 1008)
                if self.recording:
                    self.runtime.recorder.audio(self.recording, pcm)
                self._enqueue(self.segmenter.feed(pcm))
                continue
            text = message.get("text")
            if not isinstance(text, str) or len(text) > 1024:
                raise ServiceError("invalid_control", 1008)
            controls += 1
            if controls > 1024:
                raise ServiceError("control_limit", 1008)
            try:
                control = json.loads(text)
            except ValueError:
                raise ServiceError("invalid_control", 1008) from None
            if control not in ({"type": "flush"}, {"type": "finish"}):
                raise ServiceError("invalid_control", 1008)
            self._enqueue(self.segmenter.flush())
            if control["type"] == "finish":
                # Sentinel waits for capacity, unlike incoming audio which fails fast on overload.
                await self.chunks.put(None)
                return

    def _watch_done(self, task: asyncio.Task[None]) -> None:
        self.notifications.discard(task)
        if not task.cancelled():
            error = task.exception()
            if error is not None:
                self.notification_error = error

    async def _notify_delivery(self, event: dict[str, Any], future: asyncio.Future[Delivery]) -> None:
        result = await asyncio.shield(future)
        if result.status not in {"delivered", "not_configured"} or result.console_status in {
            "failed",
            "unknown",
        }:
            self.delivery_failures += 1
        await self.send(
            {
                "type": "delivery",
                "event_id": event["event_id"],
                "sequence": event["sequence"],
                "status": result.status,
                "http_status": result.http_status,
                "console_status": result.console_status,
                "attempts": result.attempts,
            }
        )

    async def _consume(self) -> None:
        assert self.start is not None
        inference_seconds = queue_seconds = 0.0
        while True:
            queued = await self.chunks.get()
            if queued is None:
                break
            chunk, queued_at = queued
            if self.notification_error:
                raise self.notification_error
            outcome = await self.runtime.transcribe(
                chunk,
                self.start.language,
                queued_at,
                engine=self.session_engine,
            )
            inference_seconds += outcome.inference_seconds
            queue_seconds = max(queue_seconds, outcome.queue_seconds)
            if not outcome.result.final:
                continue
            elapsed, waited = inference_seconds, queue_seconds
            inference_seconds = queue_seconds = 0.0
            start_sample = outcome.result.start_sample
            if start_sample is None:
                start_sample = chunk.start_sample
            duration = (chunk.end_sample - start_sample) / SAMPLE_RATE
            self.processed += 1
            if not outcome.result.text.strip():
                await self.send({"type": "chunk_skipped", "sequence": self.processed, "reason": "no_speech"})
                continue
            self.transcripts += 1
            event = {
                "type": "transcript",
                "version": 1,
                "event_id": str(uuid4()),
                "session_id": self.session_id,
                "stream_id": str(self.start.stream_id),
                "sequence": self.processed,
                "client_id": self.client_id,
                "created_at": datetime.now(UTC).isoformat(),
                "text": outcome.result.text,
                "language": outcome.result.language,
                "requested_language": self.start.language,
                "engine": self.settings.engine_name,
                "device": self.settings.inference_device,
                "compute_type": self.settings.compute_type,
                "model": self.settings.model_name,
                "audio_start_seconds": start_sample / SAMPLE_RATE,
                "audio_end_seconds": chunk.end_sample / SAMPLE_RATE,
                "segments": outcome.result.segments,
                "inference_ms": round(elapsed * 1000, 2),
                "queue_ms": round(waited * 1000, 2),
                "real_time_factor": round(elapsed / max(duration, 1 / SAMPLE_RATE), 4),
            }
            if self.recording:
                self.runtime.recorder.transcript(self.recording, event)
            future = self.runtime.callbacks.submit(event)
            await self.send(event)
            task = asyncio.create_task(self._notify_delivery(event, future), name="delivery-notification")
            self.notifications.add(task)
            task.add_done_callback(self._watch_done)
        if self.notifications:
            await asyncio.gather(*list(self.notifications))
        if self.notification_error:
            raise self.notification_error
        recording_status = self.runtime.recorder.finish(self.recording) if self.recording else None
        await self.send(
            {
                "type": "complete",
                "session_id": self.session_id,
                "audio_seconds": self.segmenter.total_samples / SAMPLE_RATE,
                "chunks_processed": self.processed,
                "transcripts": self.transcripts,
                "delivery_failures": self.delivery_failures,
                "recording": recording_status,
            }
        )
