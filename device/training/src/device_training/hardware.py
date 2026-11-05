"""Pi hardware adapters. Never activated by fixture-mode tests."""

import asyncio
import io
import threading
import time
import wave
from collections import deque


class MicrophoneBuffer:
    """Bound bytes and scheduled wakeups even if the asyncio loop stalls."""

    def __init__(self, loop, capacity=20):
        self.loop = loop
        self.capacity = capacity
        self.frames: deque[bytes] = deque()
        self.lock = threading.Lock()
        self.available = asyncio.Event()
        self.failed = False
        self.closed = False
        self.notification_pending = False

    def push(self, data, status=False):
        with self.lock:
            if self.closed:
                return
            if status or len(self.frames) >= self.capacity:
                self.failed = True
            elif not self.failed:
                self.frames.append(bytes(data))
            if not self.notification_pending:
                self.notification_pending = True
                self.loop.call_soon_threadsafe(self._notify)

    def _notify(self):
        with self.lock:
            self.notification_pending = False
        self.available.set()

    async def receive(self):
        while True:
            with self.lock:
                if self.failed:
                    raise RuntimeError("microphone_overflow")
                if self.frames:
                    return self.frames.popleft()
                self.available.clear()
            await asyncio.wait_for(self.available.wait(), 1)

    def close(self):
        with self.lock:
            self.closed = True
            self.frames.clear()


async def microphone(seconds, guard, device=None):
    import numpy as np
    import sounddevice as sd

    frames = MicrophoneBuffer(asyncio.get_running_loop())

    def callback(data, count, timing, status):
        frames.push(data, bool(status))

    voiced = 0
    quiet = 0
    started = time.monotonic()
    try:
        with sd.RawInputStream(
            device=device, samplerate=16000, channels=1, dtype="int16", blocksize=320, callback=callback
        ):
            while time.monotonic() - started < seconds:
                guard()
                data = await frames.receive()
                energy = float(np.sqrt(np.mean(np.frombuffer(data, dtype="<i2").astype(np.float32) ** 2)))
                voiced += int(energy > 400)
                quiet = 0 if energy > 400 else quiet + 1
                yield data
                if (voiced >= 9 and quiet >= 30) or (voiced < 9 and time.monotonic() - started > 5):
                    return
    finally:
        frames.close()


async def speaker(sound, guard, started, device=None):
    import sounddevice as sd

    loop = asyncio.get_running_loop()
    complete = asyncio.Event()
    failed = False
    with wave.open(io.BytesIO(sound), "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getnframes() > wav.getframerate() * 60:
            raise ValueError("invalid_speech")
        rate, pcm = wav.getframerate(), wav.readframes(wav.getnframes())
    position = 0

    def callback(output, count, timing, status):
        nonlocal position, failed
        failed = failed or bool(status)
        block = pcm[position : position + count * 2]
        output[:] = block + bytes(count * 2 - len(block))
        position += len(block)
        if len(block) < count * 2:
            raise sd.CallbackStop()

    def done():
        loop.call_soon_threadsafe(complete.set)

    with sd.RawOutputStream(
        device=device,
        samplerate=rate,
        channels=1,
        dtype="int16",
        blocksize=512,
        callback=callback,
        finished_callback=done,
    ):
        await started()
        async with asyncio.timeout(65):
            while not complete.is_set():
                guard()
                await asyncio.sleep(0.05)
    if failed:
        raise RuntimeError("speaker_underflow")


async def camera(width, height, fps, stop, executable="rpicam-vid"):
    process = await asyncio.create_subprocess_exec(
        executable,
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
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    assert process.stdout is not None
    buffer = bytearray()
    try:
        while not stop.is_set():
            data = await asyncio.wait_for(process.stdout.read(65536), 5)
            if not data:
                raise RuntimeError("camera_disconnected")
            buffer.extend(data)
            if len(buffer) > 1048576:
                raise RuntimeError("camera_frame_limit")
            while (end := buffer.find(b"\xff\xd9")) >= 0:
                frame = bytes(buffer[: end + 2])
                del buffer[: end + 2]
                if not frame.startswith(b"\xff\xd8"):
                    raise RuntimeError("invalid_camera_stream")
                yield frame, time.monotonic()
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()
