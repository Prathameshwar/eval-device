"""Camera recording and archive completion independent of any preview consumer."""

import asyncio
import threading
import time
from collections import deque
from contextlib import suppress
from dataclasses import replace

from .video import Recorder, VideoError


class CameraRecording:
    def __init__(self, *, recorder=None, can_start=None):
        self.recorder = recorder or Recorder()
        self.can_start = can_start or (lambda: True)
        self._lock = threading.RLock()
        self._events = deque(maxlen=128)
        self._preview = None
        self._thread = None
        self._archive = None

    @property
    def busy(self):
        with self._lock:
            return self.recorder.busy or bool(self._thread and self._thread.is_alive())

    def start(self, options, *, sync=None):
        with self._lock:
            if not self.can_start():
                raise VideoError("Practice is stopping; camera capture cannot start")
            if self.busy:
                raise VideoError("Camera is already recording or finishing")
            if sync and not sync.current:
                raise VideoError("Practice is preparing. Start recording when the session is ready.")
            archive = (sync, sync.current) if sync else None
            if archive:
                options = replace(options, archive_id=archive[1], archive_namespace=sync.root.name)
            self._events.clear()
            self._preview = None
            self._archive = archive
            try:
                if archive:
                    archive[0].video_start(archive[1])
                self.recorder.start(options)
                self._thread = threading.Thread(target=self._monitor, name="camera-archive", daemon=True)
                self._thread.start()
            except Exception:
                with suppress(Exception):
                    self.recorder.abort()
                with suppress(Exception):
                    self._finish_archive(True)
                self._thread = None
                raise VideoError("Could not start camera recording") from None

    def _finish_archive(self, incomplete):
        if self._archive:
            sync, identity = self._archive
            self._archive = None
            sync.video_end(identity, incomplete)

    def _monitor(self):
        try:
            while True:
                with self._lock:
                    events, preview = self.recorder.poll()
                    for kind, value in events:
                        if kind == "segment" and self._archive:
                            self._archive[0].video_file(self._archive[1], value)
                        elif kind in {"finished", "interrupted"}:
                            self._finish_archive(kind == "interrupted" or bool(value.get("error")))
                        self._events.append((kind, value))
                    if preview is not None:
                        self._preview = preview
                    if not self.recorder.busy:
                        break
                time.sleep(0.05)
        except Exception:
            with self._lock:
                with suppress(Exception):
                    self.recorder.abort()
                self._events.append(("interrupted", None))
                if not self.recorder.busy:
                    self._events.append(("idle", None))
        finally:
            with self._lock:
                try:
                    self._finish_archive(True)
                except Exception:
                    self._events.append(("interrupted", None))

    def poll(self):
        """Drain bounded preview notifications; recording never depends on this call."""
        with self._lock:
            events, preview = list(self._events), self._preview
            self._events.clear()
            self._preview = None
            return events, preview

    def stop(self):
        with self._lock:
            self.recorder.stop()

    async def close(self):
        self.stop()
        thread = self._thread
        if thread:
            await asyncio.to_thread(thread.join, 8)
            if thread.is_alive():
                raise VideoError("Camera is still finishing its recording")
        if self.recorder.busy:
            await asyncio.to_thread(self.recorder.abort)
