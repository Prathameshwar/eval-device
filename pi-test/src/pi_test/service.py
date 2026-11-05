"""A single event loop owns capture, conversation work and upload lifetime."""

import asyncio
import json
import os
import shutil
import signal
import socket
import time
from contextlib import suppress
from functools import partial
from uuid import UUID

from training_client.recording import CameraRecording
from training_client.runtime import Runtime
from training_client.video import Options, Recorder

from .config import private_dir
from .control import Control
from .diagnostics import hardware, inspect


def notify(message):
    address = os.environ.get("NOTIFY_SOCKET")
    if address and os.name != "nt":
        if address.startswith("@"):
            address = "\0" + address[1:]
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
            with suppress(OSError):
                client.sendto(message.encode(), address)


class Service:
    def __init__(self, settings, *, runtime_factory=Runtime):
        self.settings = settings
        self.runtime = runtime_factory(settings, self.observe)
        if settings.camera_backend in {"csi", "usb"}:
            from .hardware.camera import CsiCamera, UsbCamera

            self.runtime.camera = CameraRecording(
                recorder=Recorder(
                    partial(
                        CsiCamera if settings.camera_backend == "csi" else UsbCamera,
                        width=settings.camera_width,
                        height=settings.camera_height,
                        fps=settings.camera_fps,
                        **({"device": settings.camera_device} if settings.camera_backend == "usb" else {}),
                    )
                ),
                can_start=lambda: not self.runtime.closing and not self.runtime.finishing,
            )
        if getattr(self.runtime.inference, "remote", False):
            self.runtime.inference.stream_audio = settings.stream_audio
        if runtime_factory is Runtime:
            from training_client.cloud_speech import RoutedPlayback
            from training_client.speech import Speaker

            from .hardware.audio import output_device

            class Playback(RoutedPlayback):
                def _output(inner, rate):
                    inner.output_device = output_device(settings.speaker_device_name)
                    return super()._output(rate)

            engine = Playback(
                settings,
                lambda: self.runtime.controller.pms.model_route if self.runtime.controller else None,
                self.runtime.inference,
            )
            self.runtime.speaker = Speaker(
                enabled=settings.speaker_output,
                engine=engine,
                inference=self.runtime.inference,
                emit=self.runtime.emit,
            )
            self.runtime.speaker.prefer(settings.voice)
        self.control = Control(settings.control_dir, self.dispatch)
        self.stop = asyncio.Event()
        self.state = "starting"
        self.job = None
        self.job_name = None
        self.job_error = None
        self.ready = False
        self.active = False
        self.finish_pending = False
        self.event_counts = {}
        self.last_contact = 0.0
        self.catalog = None
        self.started = time.monotonic()
        self.command_lock = asyncio.Lock()
        self.video_stream = None
        self.video_job = None
        self.processing = None
        self.result = None
        self.result_until = 0.0
        self.readiness = {
            "platform": "unknown",
            "binding": "unknown",
            "models": "unknown",
            "gateway": "unused",
        }
        self.hardware_status = {"microphone": "unknown", "speaker": "unknown", "camera": "unknown"}

    def observe(self, kind, value):
        if kind in {"queue_stopping", "queue_finished"}:
            self.state = "paused" if kind == "queue_stopping" else "idle"
            if kind == "queue_finished":
                self.active = False
            for task in (self.video_job, self.video_stream):
                if task and not task.done():
                    task.cancel()
            self.result, self.result_until = None, 0.0
        # Count only known event names; never persist transcript, answers or HTTP details.
        if kind in {"transcript", "done", "error", "queue_unavailable", "history_status", "sync_status"}:
            self.event_counts[kind] = self.event_counts.get(kind, 0) + 1

    def status(self):
        return {
            "state": "stopping" if self.stop.is_set() else self.state,
            "ready": self.ready and not self.stop.is_set(),
            "active": self.active,
            "finishing": self.runtime.finishing,
            "job": self.job_name if self.job and not self.job.done() else None,
            "video_processing": bool(self.video_job and not self.video_job.done()),
            "last_error": self.job_error,
            "uptime_seconds": int(time.monotonic() - self.started),
            "events": dict(self.event_counts),
            "camera_active": self.runtime.camera.busy,
            "inference_request": getattr(self.runtime.inference, "last_request", None),
            "readiness": dict(self.readiness),
            "hardware": dict(self.hardware_status),
            "processing_request": self.processing.last if self.processing else None,
            "result_available": self.result is not None and time.monotonic() < self.result_until,
        }

    def launch(self, name, operation, *, video=False):
        existing = self.video_job if video else self.job
        if existing and not existing.done():
            raise ValueError("Another operation is active")
        if not video:
            self.job_name = name
        self.job_error = None
        self.result, self.result_until = None, 0.0

        async def run():
            try:
                value = await operation()
                if value is not None:
                    self.result = (
                        value
                        if len(json.dumps(value, default=str).encode()) <= 24000
                        else {"available_on_platform": True}
                    )
                    self.result_until = time.monotonic() + 300
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self.job_error = type(error).__name__
                if not video:
                    self.state = "paused" if self.active else "idle"

        task = asyncio.create_task(run(), name="pi-" + name)
        if video:
            self.video_job = task
        else:
            self.job = task
        return {"accepted": name}

    async def stop_video(self):
        tasks = [task for task in (self.video_stream, self.video_job) if task and not task.done()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def pause(self):
        self.runtime.pause()
        if self.job and not self.job.done():
            self.job.cancel()
            await asyncio.gather(self.job, return_exceptions=True)
        await self.stop_video()
        await self.runtime.stop_work()
        # Both standalone and assigned finishes retain the barrier until acknowledged.
        self.runtime.finishing = self.finish_pending or bool(
            self.runtime.sessions and self.runtime.sessions.finishing
        )
        self.state = "paused" if self.active else "idle"

    async def finish(self):
        await self.pause()
        if self.runtime.sessions and self.runtime.sessions.assigned():
            await self.runtime.sessions.finish()
        else:
            self.finish_pending = self.runtime.finishing = True
            pms = self.runtime.controller.pms
            if pms.conversation:
                await pms.close_conversation(pms.conversation["context"]["conversation_id"])
                pms.conversation = None
            self.runtime.controller.reset()
            self.finish_pending = self.runtime.finishing = False
        self.active = False
        self.state = "idle"
        self.result, self.result_until = None, 0.0

    async def begin(self, scenario=None):
        if self.active:
            raise ValueError("Finish the current session first")
        if not self.ready:
            raise ValueError("Device is not ready")
        self.check_storage()
        if self.runtime.sessions and self.runtime.sessions.next:
            if scenario:
                raise ValueError("An assigned session takes priority")
            await self.runtime.sessions.begin()
        else:
            catalog, selection = await self.runtime.prepare()
            self.catalog = catalog
            default = catalog.get("default") or {}
            identity = str(UUID(scenario)) if scenario else default.get("scenario_id")
            # The platform supplies all clinical data. The device chooses only a published ID.
            row = next((item for item in catalog["scenarios"] if item["id"] == identity), None)
            if row is None:
                raise ValueError("Choose a published scenario")
            if self.settings.language not in row.get("languages", [self.settings.language]):
                raise ValueError("The scenario does not support the configured language")
            if not row.get("vitals"):
                raise ValueError("Publish baseline vitals for unattended practice")
            await self.runtime.save_selection(
                {
                    "scenario_id": row["id"],
                    "expected_revision": selection["revision"] if selection else 0,
                    "language": self.settings.language,
                    "vitals": row["vitals"],
                }
            )
        self.active = True
        self.state = "paused"
        self.configure_output()

    def check_storage(self):
        if shutil.disk_usage(self.settings.app_root).free < self.settings.min_free_mb * 1024 * 1024:
            raise ValueError("Storage is below the capture reserve")

    async def dispatch(self, request):
        if request.get("command") in {"status", "doctor", "shutdown"}:
            return await self._dispatch(request)
        async with self.command_lock:
            return await self._dispatch(request)

    async def _dispatch(self, request):
        if set(request) - {"command", "scenario", "text", "request_id", "run_id"}:
            raise ValueError("Unknown fields")
        command = request.get("command")
        if (self.stop.is_set() or self.runtime.closing) and command not in {"status", "doctor", "shutdown"}:
            raise ValueError("Service is stopping")
        if (
            command
            in {"begin", "text", "listen", "resume", "camera-start", "camera-stream", "camera-process"}
            and self.runtime.finishing
        ):
            raise ValueError("Session is stopping; wait for platform confirmation")
        if command == "status":
            return self.status()
        if command == "doctor":
            return inspect(self.settings)
        if command == "probe":
            self.hardware_status = await asyncio.to_thread(hardware, self.settings)
            return self.hardware_status
        if command == "result":
            if time.monotonic() >= self.result_until:
                self.result = None
            return self.result
        if command == "processing-requests":
            from training_client.cloud_speech import Journal

            return await asyncio.to_thread(
                lambda: [
                    {"kind": kind, **row}
                    for directory, kind in (("processing", "video"), ("synthesis", "audio_output"))
                    for row in Journal(self.settings.app_root / directory).recent()
                ]
            )
        if command == "processing-status":
            return await self.video_processor().status(request["run_id"])
        if command == "send-now":
            if not self.job or self.job.done() or self.job_name != "listen":
                raise ValueError("Listening is not active")
            self.runtime.send_now.set()
            return {"accepted": "send-now"}
        if command == "reload":
            if self.active or (self.job and not self.job.done()):
                raise ValueError("Finish the session before reloading")
            self.ready = False
            self.catalog, _ = await self.runtime.prepare()
            await self.verify_binding()
            self.ready = True
            return self.status()
        if command == "inference-requests":
            journal = getattr(self.runtime.inference, "journal", None)
            return journal.recent() if journal else []
        if command == "inference-status":
            identity = str(UUID(request["request_id"]))
            return await self.runtime.inference.async_request(
                "POST", "/v1/requests/status", {"request_id": identity}
            )
        if command == "scenarios":
            if not self.ready:
                raise ValueError("Device is not ready")
            options = await self.runtime.controller.pms.scenario_options()
            return [
                {"id": row["id"], "name": row.get("name", row.get("title", ""))} for row in options["items"]
            ]
        if command == "pause":
            await self.pause()
            return self.status()
        if command == "finish":
            await self.finish()
            return self.status()
        if command == "shutdown":
            self.stop.set()
            return {"stopping": True}
        if command == "begin":

            async def start():
                await self.begin(request.get("scenario"))
                if self.settings.listen_on_begin:
                    self.job_name = "listen"
                    await self.listen()

            return self.launch("begin", start)
        if command == "camera-process":
            if not self.active or not self.ready or not self.runtime.camera.busy:
                raise ValueError("Start recording in an active session first")
            if self.video_stream and not self.video_stream.done():
                raise ValueError("Video stream is already active")
            self.check_storage()

            async def process():
                from .hardware.streaming import frames

                await self.runtime.controller.pms.ensure_conversation()
                return await self.video_processor().execute(
                    frames(self.runtime.camera, self.settings.processing_video_seconds),
                    self.settings.processing_video_seconds,
                )

            return self.launch("camera-process", process, video=True)
        if command == "camera-stream":
            if not self.active or not self.ready or not self.runtime.camera.busy:
                raise ValueError("Start recording in an active session first")
            if not getattr(self.runtime.inference, "remote", False):
                raise ValueError("Configure a remote inference gateway")
            if self.video_stream and not self.video_stream.done():
                raise ValueError("Video stream is active")
            if self.video_job and not self.video_job.done():
                raise ValueError("Video processing is active")
            from .hardware.streaming import video

            self.video_stream = asyncio.create_task(video(self.runtime.camera, self.runtime.inference))
            self.video_stream.add_done_callback(self.stream_finished)
            return {"accepted": "camera-stream"}
        if command in {"listen", "resume", "text", "camera-start"}:
            if not self.active or not self.ready:
                raise ValueError("Begin a session first")
            self.check_storage()
            if command in {"listen", "resume"}:
                return self.launch("listen", self.listen)
            if command == "text":
                text = request.get("text")
                if not isinstance(text, str) or not text.strip() or len(text) > 8000:
                    raise ValueError("Invalid question")
                return self.launch("text", lambda: self.runtime.text_turn(text))
            if self.settings.camera_backend == "none":
                raise ValueError("Camera is disabled")
            await self.runtime.controller.pms.ensure_conversation()
            self.runtime.camera.start(
                Options.from_settings(self.settings, self.settings.camera_index),
                sync=self.runtime.controller.sync,
            )
            return {"camera": "started"}
        if command == "camera-stop":
            await self.stop_video()
            await self.runtime.camera.close()
            return {"camera": "stopped"}
        raise ValueError("Unknown command")

    async def listen(self):
        self.state = "listening"
        try:
            await self.runtime.listen()
        finally:
            self.state = "paused" if self.active else "idle"

    def video_processor(self):
        from training_client.processing import VideoProcessing

        if not self.runtime.controller:
            raise ValueError("Device is not initialized")
        if self.processing is None:
            self.processing = VideoProcessing(
                self.settings, self.runtime.controller.pms, self.runtime.inference
            )
        return self.processing

    async def verify_binding(self):
        if not getattr(self.runtime.inference, "remote", False):
            self.readiness["binding"] = "cloud_only"
            route = self.runtime.controller.pms.model_route or {}
            if route.get("llm", {}).get("mode") == "local" or (
                route.get("audio", {}).get("enabled") and route["audio"].get("mode") == "local"
            ):
                self.readiness["binding"] = "remote_host_required"
                raise ValueError("Local routes require a remote host on Pi")
            return
        from training_contracts.inference import Binding

        binding = Binding.model_validate(
            await self.runtime.controller.pms.json("GET", "/api/v1/device/inference")
        )
        if (
            str(binding.host_id) != self.runtime.inference.host_id
            or binding.origin != self.runtime.inference.root
        ):
            self.readiness["binding"] = "mismatch"
            raise ValueError("Platform and device inference bindings differ")
        self.readiness["binding"] = "verified"

    async def reconcile(self):
        from training_client.telemetry import heartbeat

        await self.runtime.initialize()
        pms = self.runtime.controller.pms
        self.readiness["platform"] = "checking"
        await pms.json("GET", "/api/v1/device/identity")
        self.readiness["platform"] = "reachable"
        if self.active and pms.conversation:
            await pms.ensure_conversation()
        prepared = not self.active and not self.ready
        if prepared:
            await self.runtime.prepare()
        elif self.active and self.settings.use_pms_models:
            latest = await pms.model_config(self.settings.processing_profile_id)
            if latest["configuration_hash"] != (pms.model_route or {}).get("configuration_hash"):
                self.readiness["models"] = "configuration_changed"
                raise ValueError("Finish and reload the changed configuration")
        await self.verify_binding()
        route = pms.model_route or {}
        self.configure_output()
        self.readiness["models"] = "cloud" if route.get("llm", {}).get("mode") == "cloud" else "configured"
        if getattr(self.runtime.inference, "remote", False):
            from local_model_client import ConnectionError

            info = self.settings.local_models_capabilities if prepared else {}
            if not prepared:
                try:
                    info = await self.runtime.inference.async_request("GET", "/v1/capabilities")
                    self.runtime.inference.remember(info)
                except ConnectionError:
                    self.runtime.inference.clear_capabilities()
            self.readiness["gateway"] = "reachable" if info else "unavailable"
            llm = route.get("llm", {})
            if llm.get("mode") == "local":
                service = info.get("services", {}).get("llm", {})
                model = next(
                    (row for row in info.get("models", []) if row["id"] == service.get("model_id")), {}
                )
                if not service.get("ready") or llm.get("model") not in {model.get("id"), model.get("alias")}:
                    self.readiness["models"] = "unavailable"
                    raise ValueError("Assigned language model is unavailable")
                self.readiness["models"] = "ready"
        await pms.json("POST", "/api/v1/device/heartbeat", json=heartbeat())

    def configure_output(self):
        route = self.runtime.controller.pms.model_route or {}
        output = route.get("platform_media", {}).get("audio_output", {}).get("settings", {})
        self.runtime.speaker.enabled = self.settings.speaker_output and bool(output.get("enabled"))
        # Capabilities may arrive after construction (or after GPU reconnection).
        self.runtime.speaker.prefer(self.settings.voice)

    def stream_finished(self, task):
        if not task.cancelled() and task.exception() is not None:
            self.job_error = "video_stream_failed"

    async def supervise(self):
        next_check = 0.0
        while not self.stop.is_set():
            notify("WATCHDOG=1")  # This loop must progress; network readiness is a separate state.
            if time.monotonic() >= next_check and not (self.job and not self.job.done() and not self.active):
                next_check = time.monotonic() + self.settings.readiness_seconds
                try:
                    async with asyncio.timeout(10):
                        await self.reconcile()
                    self.ready = True
                    if not self.active:
                        self.state = "idle"
                    self.last_contact = time.monotonic()
                except Exception:
                    self.ready = False
                    if self.readiness["platform"] in {"unknown", "checking"}:
                        self.readiness["platform"] = "unavailable"
                    if self.active:
                        await self.pause()
                    else:
                        self.state = "unavailable"
            if self.active:
                try:
                    self.check_storage()
                except ValueError:
                    await self.pause()
                    self.job_error = "storage_reserve"
            if self.result is not None and time.monotonic() >= self.result_until:
                self.result = None
            try:
                await asyncio.wait_for(self.stop.wait(), 2)
            except TimeoutError:
                pass

    async def run(self):
        private_dir(self.settings.app_root)
        from training_client.session_sync import FileLock

        ownership = FileLock(self.settings.app_root / "service.lock")
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with suppress(NotImplementedError):
                loop.add_signal_handler(sig, self.stop.set)
        try:
            await self.control.start()
            notify("READY=1\nSTATUS=Idle; capture requires an explicit command")
            await self.supervise()
        finally:
            self.stop.set()
            self.state = "stopping"
            notify("STOPPING=1")
            try:
                # Stop admission and cancel pending commands before closing their dependencies.
                await self.control.close()
            finally:
                try:
                    await self.pause()
                finally:
                    try:
                        await self.runtime.close()
                    finally:
                        ownership.close()
