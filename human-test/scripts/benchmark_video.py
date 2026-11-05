"""Synthetic video + silent resident speech benchmark; never opens camera/microphone/speaker.

Run: uv run python scripts/benchmark_video.py --output ../.test_artifacts/desktop-video
Measures a deliberately noisy 640x480 source, real encoding/disk writes, Tk preview,
and resident local English TTS. Does not measure physical capture, ASR or cloud latency.
"""

import argparse
import ctypes
import json
import statistics
import sys
import threading
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from training_client import video
from training_client.speech import ManagerPlayback

from human_test.camera_view import CameraView
from human_test.config import Settings


class SyntheticCamera:
    def __init__(self):
        self.pixels = np.random.default_rng(7).integers(0, 256, (480, 640, 3), dtype=np.uint8)
        self.index = 0

    def read(self):
        self.index += 1
        self.pixels[50:90, :, 1] = self.index % 256
        return True, self.pixels

    def release(self):
        pass


def process_stats():
    if sys.platform != "win32":
        return {}
    from ctypes import wintypes

    class Memory(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
            (name, ctypes.c_size_t)
            for name in (
                "peak",
                "working",
                "peak_paged",
                "paged",
                "peak_nonpaged",
                "nonpaged",
                "page",
                "peak_page",
            )
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.GetPriorityClass.argtypes = [wintypes.HANDLE]
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Memory), wintypes.DWORD]
    memory = Memory()
    memory.cb = ctypes.sizeof(memory)
    handle = kernel.GetCurrentProcess()
    if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(memory), memory.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return {
        "peak_working_set_mb": memory.peak / video.MIB,
        "below_normal_priority": kernel.GetPriorityClass(handle) == 0x4000,
    }


def synthetic_worker(options, stop, previews, events, heartbeat):
    wall, cpu = time.monotonic(), time.process_time()
    video.record(options, stop, previews, events, heartbeat, camera_factory=lambda _: SyntheticCamera())
    elapsed, used = time.monotonic() - wall, time.process_time() - cpu
    metrics = {
        "wall_seconds": elapsed,
        "cpu_seconds": used,
        "percent_of_one_cpu_core": used / elapsed * 100,
        **process_stats(),
    }
    (options.directory / "worker-metrics.json").write_text(json.dumps(metrics, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=50)
    args = parser.parse_args()
    from local_model_client import Connection, client_key, configure

    configure(capabilities=Connection().capabilities(), key=client_key())
    args.output.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    root.withdraw()
    view = CameraView(root, Settings(_env_file=None, video_recording_dir=args.output / "recordings"))
    view.pack()
    engine = ManagerPlayback()
    voice = engine.load("en", "male")
    text = "I get tightness in my chest when I walk uphill. Rest usually helps."
    list(voice.synthesize(text))
    executor = ThreadPoolExecutor(max_workers=1)
    ticks, timings, previews = [], {}, 0
    last_tick = time.monotonic()
    finished = threading.Event()

    def tick():
        nonlocal last_tick
        now = time.monotonic()
        ticks.append((now - last_tick) * 1000)
        last_tick = now
        if not finished.is_set():
            root.after(30, tick)

    def synthesize():
        values = []
        for _ in range(args.samples):
            started = time.monotonic()
            list(voice.synthesize(text))
            values.append(time.monotonic() - started)
        return values

    def pump():
        nonlocal previews
        before = view.photo
        root.update()
        view.poll()
        previews += int(view.photo is not None and view.photo is not before)
        time.sleep(0.003)

    root.after(30, tick)
    try:
        for phase in ("before_video", "with_video", "after_video"):
            if phase == "with_video":
                video.record = synthetic_worker
                view.checkbox.invoke()
                deadline = time.monotonic() + 15
                while view.photo is None and time.monotonic() < deadline:
                    pump()
                assert view.photo is not None, view.status.get()
            ticks.clear()
            future = executor.submit(synthesize)
            while not future.done():
                pump()
            samples = future.result()
            timings[phase] = {
                "tts_seconds": samples,
                "tts_median_seconds": statistics.median(samples),
                "tk_tick_p95_ms": sorted(ticks)[int((len(ticks) - 1) * 0.95)],
            }
            if phase == "with_video":
                view.stop()
                deadline = time.monotonic() + 10
                while view.recorder.busy and time.monotonic() < deadline:
                    pump()
                assert not view.recorder.busy and "saved" in view.status.get(), view.status.get()
        timings["worker"] = json.loads((args.output / "recordings/worker-metrics.json").read_text())
        timings["preview_updates"] = previews
        timings["source"] = "synthetic noisy 640x480 BGR; no hardware or ASR/cloud requests"
        (args.output / "benchmark.json").write_text(json.dumps(timings, indent=2))
        print(json.dumps(timings, indent=2))
    finally:
        finished.set()
        view.close()
        while view.recorder.busy:
            pump()
        executor.shutdown()
        engine.close()
        root.destroy()


if __name__ == "__main__":
    main()
