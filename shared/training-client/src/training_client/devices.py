"""Optional physical audio adapter. Importing the runtime never opens a device."""

import queue
import time

from .pms_client import ClientError


def input_device(settings, devices, default=None):
    """Strict unattended identity; a disconnected named input must never select another."""
    inputs = [(index, row) for index, row in enumerate(devices) if row["max_input_channels"] >= 1]
    if settings.microphone_name:
        matches = [(index, row) for index, row in inputs if row["name"] == settings.microphone_name]
    else:
        index = settings.microphone if settings.microphone is not None else default
        matches = [(i, row) for i, row in inputs if i == index]
    if len(matches) != 1:
        raise ClientError("Configured microphone is missing or ambiguous", code="microphone_unavailable")
    index, row = matches[0]
    return index, row["name"], None


class NormalizedFrames:
    """Bounded PCM normalization and a liveness check for a stopped PortAudio stream."""

    def __init__(self, source, stream, rate, *, clock=time.monotonic):
        self.source, self.stream, self.rate, self.clock = source, stream, rate, clock
        self.last = clock()
        self.buffer = bytearray()
        self.resampler = None
        if rate != 16000:
            import av

            self.resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)

    def get_nowait(self):
        while len(self.buffer) < 1600:
            try:
                raw = self.source.get_nowait()
            except queue.Empty:
                if not self.stream.active or self.clock() - self.last > 3:
                    raise ClientError(
                        "Microphone disconnected or stalled", code="microphone_unavailable"
                    ) from None
                raise
            self.last = self.clock()
            if self.resampler:
                import av

                frame = av.AudioFrame(format="s16", layout="mono", samples=len(raw) // 2)
                frame.sample_rate = self.rate
                frame.planes[0].update(raw)
                for output in self.resampler.resample(frame):
                    self.buffer.extend(bytes(output.planes[0])[: output.samples * 2])
            else:
                self.buffer.extend(raw)
            if len(self.buffer) > 16000:
                raise ClientError(
                    "Microphone normalization exceeded its buffer", code="microphone_unavailable"
                )
        result = bytes(self.buffer[:1600])
        del self.buffer[:1600]
        return result


def input_rate(settings, index, sd):
    rate = settings.microphone_native_rate or 16000
    try:
        sd.check_input_settings(device=index, channels=1, dtype="int16", samplerate=rate)
    except sd.PortAudioError:
        if not settings.microphone_strict or settings.microphone_native_rate:
            raise
        rate = int(sd.query_devices(index, "input")["default_samplerate"])
        if rate not in {16000, 44100, 48000}:
            raise ClientError("Unsupported microphone sample rate", code="microphone_unavailable") from None
        sd.check_input_settings(device=index, channels=1, dtype="int16", samplerate=rate)
    return rate


class Microphone:
    """Context-managed bounded queue of 50 ms, mono 16 kHz PCM16 blocks.

    Alternative sources use this same frame contract and update CaptureQuality
    loss counters. Endpointing and utterance queues remain in Listener.
    """

    def __init__(self, settings, quality):
        self.settings, self.quality = settings, quality
        self.stream = None

    def __enter__(self):
        import sounddevice as sd

        from .capture import BLOCK_SAMPLES, _reader, resolve_device

        if self.settings.microphone_strict:
            index, name, warning = input_device(self.settings, sd.query_devices(), sd.default.device[0])
        else:
            index, name, warning = resolve_device(self.settings)
        self.quality.device_index, self.quality.device_name, self.quality.warning = index, name, warning
        rate = input_rate(self.settings, index, sd)
        frames, callback, self.check = _reader(self.settings, self.quality)
        self.stream = sd.RawInputStream(
            device=index,
            samplerate=rate,
            channels=1,
            dtype="int16",
            blocksize=rate // 20 if rate != 16000 else BLOCK_SAMPLES,
            callback=callback,
        )
        try:
            self.stream.__enter__()
        except BaseException:
            self.stream.close()
            raise
        return (
            NormalizedFrames(frames, self.stream, rate)
            if self.settings.microphone_strict or rate != 16000
            else frames
        )

    def __exit__(self, *args):
        return self.stream.__exit__(*args)
