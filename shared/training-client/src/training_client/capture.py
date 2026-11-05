"""Microphone capture with an adaptive speech gate and per-turn input quality.

Frames are yielded byte-for-byte as the device produced them. Nothing here filters, gains or
resamples the signal, so recording integrity and the server's own segmentation are unchanged.
What this module owns is *endpointing* (when a question has finished) and *reporting* (whether
the audio was good enough to trust the transcript).
"""

import asyncio
import math
import queue
import threading
import time
import wave
from array import array

from .pms_client import ClientError

BLOCK_SAMPLES = 800
BLOCK_MS = BLOCK_SAMPLES * 1000 // 16000  # 50 ms at 16 kHz mono.
QUEUE_BLOCKS = 40  # Two seconds of slack before the event loop is considered stalled.
FULL_SCALE = 32768
CLIPPED_AT = 32000  # Near full scale; the driver has already lost the waveform shape here.
SILENT_RMS = 1.0  # Below this a 16-bit capture is digital silence, not a quiet room.
QUIET_BLOCKS_TO_RESET = 2  # A single dipped block mid-word must not disarm the endpointer.
FLOOR_DECAY = 0.95  # Slow tracking, so a lull inside speech cannot pull the gate down.
MIN_DBFS = -120.0


def _now():
    """Capture's own clock seam, so tests can advance time without touching asyncio's."""
    return time.monotonic()


def microphones():
    import sounddevice as sd

    return [(i, d["name"]) for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0]


def _default_input_index():
    """Which device PortAudio would pick for us. Best effort: it is only used to name the
    microphone in the quality report, never to choose one."""
    import sounddevice as sd

    try:
        index = sd.default.device[0]
    except Exception:
        return None
    return index if isinstance(index, int) and index >= 0 else None


def dbfs(rms):
    return MIN_DBFS if rms <= 0 else max(MIN_DBFS, round(20 * math.log10(rms / FULL_SCALE), 1))


def block_levels(frame):
    """Return (rms, peak, clipped sample count) in one pass, without numpy."""
    samples = array("h", frame)
    if not samples:
        return 0.0, 0, 0
    total = peak = clipped = 0
    for sample in samples:
        total += sample * sample
        magnitude = -sample if sample < 0 else sample
        if magnitude > peak:
            peak = magnitude
        if magnitude >= CLIPPED_AT:
            clipped += 1
    return math.sqrt(total / len(samples)), peak, clipped


def resolve_device(settings):
    """Prefer the saved device *name*: sounddevice indices reorder across reboots and USB
    re-enumeration, so a stored index can silently open a different microphone."""
    wanted = (settings.microphone_name or "").strip()
    try:
        available = microphones()
    except Exception:
        # Enumeration is best effort; the stream open below reports the real failure. The name is
        # left unknown rather than echoing what was asked for, which nothing has confirmed.
        return settings.microphone, None, "Could not enumerate microphones"
    names = dict(available)
    if wanted:
        for index, name in available:
            if name == wanted:
                return index, name, None
        for index, name in available:
            if wanted.lower() in name.lower():
                return index, name, None
        if settings.microphone is not None and settings.microphone in names:
            return (
                settings.microphone,
                names[settings.microphone],
                f"Saved microphone {wanted!r} is not connected; using {names[settings.microphone]!r}",
            )
        return (
            None,
            names.get(_default_input_index()),
            f"Saved microphone {wanted!r} is not connected; using the system default",
        )
    if settings.microphone is not None and settings.microphone not in names:
        return (
            None,
            names.get(_default_input_index()),
            f"Microphone index {settings.microphone} is no longer an input device",
        )
    if settings.microphone is None:
        # Report which device the default resolves to, so a report always names what was heard.
        return None, names.get(_default_input_index()), None
    return settings.microphone, names.get(settings.microphone), None


class CaptureQuality:
    """Per-turn microphone health. Populated by `microphone`, read by the caller afterwards, so a
    weak transcript can be attributed to the input rather than to the model."""

    def __init__(self):
        self.device_index = None
        self.device_name = None
        self.warning = None
        self.blocks = 0
        self.voiced_blocks = 0
        self.dropped_blocks = 0
        self.status_blocks = 0
        self.status_flags = None
        self.peak = 0
        self.clipped_samples = 0
        self.noise_floor = 0.0
        self.threshold = 0.0
        self.speech_rms = 0.0
        self.ended = None
        self.calibrated = False

    @property
    def samples(self):
        return self.blocks * BLOCK_SAMPLES

    def snapshot(self):
        speech_db, floor_db = dbfs(self.speech_rms), dbfs(self.noise_floor)
        return {
            "device_index": self.device_index,
            "device_name": self.device_name,
            "warning": self.warning,
            "audio_ms": self.blocks * BLOCK_MS,
            "peak_dbfs": dbfs(self.peak),
            "clipped_percent": round(100 * self.clipped_samples / self.samples, 3) if self.blocks else 0.0,
            "noise_floor_dbfs": floor_db,
            "speech_dbfs": speech_db,
            # Speech level against the tracked floor: the single best predictor of word error rate.
            "snr_db": round(speech_db - floor_db, 1) if self.speech_rms > 0 else None,
            "voiced_ratio": round(self.voiced_blocks / self.blocks, 3) if self.blocks else 0.0,
            "threshold": round(self.threshold, 1),
            "dropped_blocks": self.dropped_blocks,
            "status_blocks": self.status_blocks,
            "status_flags": self.status_flags,
            "ended": self.ended,
            "calibrated": self.calibrated,
        }

    def concerns(self):
        """Plain-language reasons to distrust this turn's audio, worst first."""
        report = self.snapshot()
        reasons = []
        if self.warning:
            reasons.append(self.warning)
        if self.dropped_blocks or self.status_blocks:
            lost = (self.dropped_blocks + self.status_blocks) * BLOCK_MS
            reasons.append(f"about {lost} ms of audio was lost before transcription")
        if report["clipped_percent"] > 0.1:
            reasons.append(f"{report['clipped_percent']}% of samples clipped; reduce the input gain")
        if self.noise_floor >= SILENT_RMS and report["snr_db"] is not None and report["snr_db"] < 15:
            reasons.append(f"only {report['snr_db']} dB above the room noise; move closer or reduce noise")
        if self.blocks and self.noise_floor < SILENT_RMS and not self.voiced_blocks:
            reasons.append("the microphone returned digital silence; check that it is unmuted")
        if report["voiced_ratio"] > 0.95 and self.blocks > 4:
            reasons.append("every block counted as speech; the room may be too noisy to detect an endpoint")
        return reasons


class _Gate:
    """Adaptive speech gate. `energy_threshold` is the floor, never the whole answer: a quiet room
    behaves exactly as the configured value, and a noisy one raises the bar instead of arming the
    endpointer on room noise forever."""

    def __init__(self, settings):
        self.minimum = float(settings.energy_threshold)
        self.ceiling = float(settings.energy_ceiling)
        self.multiplier = settings.noise_multiplier
        self.needed = max(1, settings.calibration_ms // BLOCK_MS)
        self.samples = []
        self.floor = 0.0
        self.threshold = self.minimum

    @property
    def calibrated(self):
        return len(self.samples) >= self.needed

    def update(self, rms):
        """Feed one block; return whether it counts as speech."""
        if not self.calibrated:
            self.samples.append(rms)
            if self.calibrated:
                # The quietest calibration block, not the mean: robust if the learner starts
                # speaking immediately and the window contains speech.
                self.floor = min(self.samples)
                self._recompute()
            return rms >= self.threshold
        speech = rms >= self.threshold
        if not speech:
            self.floor = self.floor * FLOOR_DECAY + rms * (1 - FLOOR_DECAY)
            self._recompute()
        return speech

    def _recompute(self):
        self.threshold = min(max(self.minimum, self.floor * self.multiplier), self.ceiling)


def _reader(settings, quality):
    """Bridge the PortAudio callback thread to asyncio, dropping the oldest block under pressure
    rather than discarding the learner's whole question."""
    frames = queue.Queue(maxsize=QUEUE_BLOCKS)
    lock = threading.Lock()
    budget = settings.max_lost_blocks

    def callback(data, count, timing, status):
        if status:
            with lock:
                quality.status_blocks += 1
                quality.status_flags = str(status)
        try:
            frames.put_nowait(bytes(data))
        except queue.Full:
            # Keep the most recent audio: the end of a question carries the endpoint.
            try:
                frames.get_nowait()
            except queue.Empty:
                pass
            with lock:
                quality.dropped_blocks += 1
            try:
                frames.put_nowait(bytes(data))
            except queue.Full:
                pass

    def check():
        with lock:
            lost = quality.dropped_blocks + quality.status_blocks
        if lost > budget:
            # Recorded before raising, so a snapshot taken afterwards says why the turn stopped.
            quality.ended = "lost_audio"
            raise ClientError(
                f"Microphone lost about {lost * BLOCK_MS} ms of audio; this question was not submitted"
            )

    return frames, callback, check


async def microphone(settings, send_now, quality=None):
    """Capture exactly one question, opening and closing the device around it.

    The desktop no longer uses this: an interview holds one stream open through
    `listening.Listener`, because closing the device between questions is what lost the speech
    that arrived in between. This remains the single-question helper for probes and benchmarks,
    and it is where the endpointer semantics the listener reuses are pinned by tests.
    """
    import sounddevice as sd

    quality = quality if quality is not None else CaptureQuality()
    index, name, warning = resolve_device(settings)
    quality.device_index, quality.device_name, quality.warning = index, name, warning
    sd.check_input_settings(device=index, channels=1, dtype="int16", samplerate=16000)
    frames, callback, check = _reader(settings, quality)

    gate = _Gate(settings)
    began = _now()
    run = quiet = 0
    armed = False
    with sd.RawInputStream(
        device=index,
        samplerate=16000,
        channels=1,
        dtype="int16",
        blocksize=BLOCK_SAMPLES,
        callback=callback,
    ):
        while True:
            check()
            elapsed = _now() - began
            if send_now.is_set():
                quality.ended = "operator"
                return
            if armed and quiet * BLOCK_MS >= settings.silence_ms:
                quality.ended = "endpoint"
                return
            if not armed and elapsed >= settings.no_speech_seconds:
                quality.ended = "no_speech"
                return
            if elapsed >= settings.max_question_seconds:
                quality.ended = "limit"
                raise ClientError("Question reached duration limit; speak a shorter question")
            try:
                frame = frames.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.01)
                continue
            rms, peak, clipped = block_levels(frame)
            speech = gate.update(rms)
            quality.blocks += 1
            quality.peak = max(quality.peak, peak)
            quality.clipped_samples += clipped
            quality.noise_floor, quality.threshold = gate.floor, gate.threshold
            quality.calibrated = gate.calibrated
            if speech:
                quality.voiced_blocks += 1
                quality.speech_rms = max(quality.speech_rms, rms)
                run += 1
                quiet = 0
            else:
                quiet += 1
                # Only sustained quiet breaks a run, so one dipped block mid-word cannot
                # prevent arming; isolated clicks and coughs still never arm it.
                if quiet >= QUIET_BLOCKS_TO_RESET:
                    run = 0
            if run >= settings.min_voiced_blocks:
                armed = True
            yield frame


async def probe_microphone(settings, seconds=1.0):
    """Open the configured microphone briefly and report what it hears. Intended for startup and
    for device selection, so a muted, missing or reordered microphone fails before a session."""
    import sounddevice as sd

    quality = CaptureQuality()
    index, name, warning = resolve_device(settings)
    quality.device_index, quality.device_name, quality.warning = index, name, warning
    try:
        sd.check_input_settings(device=index, channels=1, dtype="int16", samplerate=16000)
    except Exception as error:
        raise ClientError(f"Microphone unavailable: {error}") from error
    frames, callback, check = _reader(settings, quality)
    gate = _Gate(settings)
    began = _now()
    with sd.RawInputStream(
        device=index,
        samplerate=16000,
        channels=1,
        dtype="int16",
        blocksize=BLOCK_SAMPLES,
        callback=callback,
    ):
        while _now() - began < seconds:
            try:
                frame = frames.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.01)
                continue
            rms, peak, clipped = block_levels(frame)
            if gate.update(rms):
                quality.voiced_blocks += 1
                quality.speech_rms = max(quality.speech_rms, rms)
            quality.blocks += 1
            quality.peak = max(quality.peak, peak)
            quality.clipped_samples += clipped
            quality.noise_floor, quality.threshold = gate.floor, gate.threshold
            quality.calibrated = gate.calibrated
    quality.ended = "probe"
    if not quality.blocks:
        raise ClientError("Microphone delivered no audio; check that the device is connected")
    check()
    return quality


async def wav_frames(path, paced=True):
    with wave.open(str(path), "rb") as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, 16000):
            raise ClientError("Fixture must be mono 16 kHz PCM16 WAV")
        began = time.monotonic()
        sent = 0
        while frame := source.readframes(BLOCK_SAMPLES):
            if paced:
                await asyncio.sleep(max(0, began + sent / 32000 - time.monotonic()))
            yield frame
            sent += len(frame)
        if paced:
            await asyncio.sleep(max(0, began + sent / 32000 - time.monotonic()))
