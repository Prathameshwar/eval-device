import os
import queue
import signal
import stat
import subprocess
import sys
import threading
from functools import partial
from pathlib import Path

from training_client.video import VideoError
from training_contracts.media import jpeg_dimensions


class JpegParser:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, chunk):
        self.buffer.extend(chunk)
        if len(self.buffer) > 1100000:
            raise VideoError("Camera frame exceeded its limit")
        frames = []
        while True:
            start = self.buffer.find(b"\xff\xd8")
            end = self.buffer.find(b"\xff\xd9", max(0, start) + 2)
            if start < 0 or end < 0:
                break
            frames.append(bytes(self.buffer[start : end + 2]))
            del self.buffer[: end + 2]
        return frames


class UsbCamera:
    """Resolve a configured stable Linux device link each time capture starts."""

    def __init__(self, index=0, *, device=None, width=640, height=480, fps=10):
        import cv2

        target = index
        if device:
            resolved = Path(device).resolve(strict=True)
            if (
                os.name == "nt"
                or not resolved.is_relative_to("/dev")
                or not stat.S_ISCHR(resolved.stat().st_mode)
            ):
                raise VideoError("Configured camera is not a Linux video device")
            target = str(resolved)
        self.camera = cv2.VideoCapture(target, cv2.CAP_V4L2 if os.name != "nt" else cv2.CAP_ANY)
        if not self.camera.isOpened():
            self.camera.release()
            raise VideoError("Configured USB camera is unavailable")
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.camera.set(cv2.CAP_PROP_FPS, fps)
        self.camera.set(cv2.CAP_PROP_BUFFERSIZE, 2)

    def read(self):
        return self.camera.read()

    def release(self):
        self.camera.release()


def _parent_death_signal(parent_pid):
    """Release the CSI device if the recorder worker has to be killed."""
    import ctypes

    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0 or os.getppid() != parent_pid:
        os._exit(127)


class CsiCamera:
    """rpicam MJPEG adapter matching shared Recorder's OpenCV capture contract."""

    def __init__(self, index=0, *, width=640, height=480, fps=10, popen=subprocess.Popen):
        self.frames = queue.Queue(maxsize=2)
        self.stopped = threading.Event()
        child_options = (
            {"preexec_fn": partial(_parent_death_signal, os.getpid())} if sys.platform == "linux" else {}
        )
        self.process = popen(
            [
                "rpicam-vid",
                "--camera",
                str(index),
                "--codec",
                "mjpeg",
                "--width",
                str(width),
                "--height",
                str(height),
                "--framerate",
                str(fps),
                "--quality",
                "70",
                "--nopreview",
                "--timeout",
                "0",
                "--output",
                "-",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
            **child_options,
        )
        self.thread = threading.Thread(target=self._read, name="rpicam-reader", daemon=True)
        self.thread.start()

    def _read(self):
        parser = JpegParser()
        try:
            while not self.stopped.is_set():
                chunk = self.process.stdout.read(65536)
                if not chunk:
                    break
                for frame in parser.feed(chunk):
                    if self.frames.full():
                        try:
                            self.frames.get_nowait()
                        except queue.Empty:
                            pass
                    self.frames.put_nowait(frame)
        except (OSError, VideoError, queue.Full):
            pass
        finally:
            self.stopped.set()

    def read(self):
        import cv2
        import numpy

        try:
            raw = self.frames.get(timeout=4)
        except queue.Empty:
            return False, None
        try:
            jpeg_dimensions(raw, max_width=1920, max_height=1080)
        except ValueError:
            return False, None
        pixels = cv2.imdecode(numpy.frombuffer(raw, dtype=numpy.uint8), cv2.IMREAD_COLOR)
        if pixels is None or pixels.shape[0] > 1080 or pixels.shape[1] > 1920:
            return False, None
        return True, pixels

    def release(self):
        self.stopped.set()
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        self.process.stdout.close()
        self.thread.join(timeout=2)
