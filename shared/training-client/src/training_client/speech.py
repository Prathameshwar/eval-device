"""Physical speaker playback using synthesis from Manage Local Models."""

import queue
import threading
import time
from collections import OrderedDict
from contextlib import suppress
from uuid import uuid4

MAX_CHARACTERS = 2000
# Playback is handed to the device in small slices so stopping stays responsive.
SLICE_BYTES = 4096
PCM_CACHE_BYTES = 2 * 1024 * 1024
PCM_CACHE_ENTRIES = 32


def voice_gender(value):
    return "female" if isinstance(value, str) and value.strip().lower() == "female" else "male"


def patient_gender(selection):
    document = selection.get("document") if isinstance(selection, dict) else None
    patient = document.get("patient") if isinstance(document, dict) else None
    return voice_gender(patient.get("sex") if isinstance(patient, dict) else None)


def catalogue():
    from local_model_client import catalogue as central_catalogue

    return central_catalogue()


def selected_voice(language, gender="male", preferred=None, *, voices=None):
    voices = [v for v in (catalogue() if voices is None else voices) if v["language"] == language]
    if preferred:
        chosen = next((v for v in voices if v["key"] == preferred), None)
        if chosen:
            return chosen["key"], chosen
    for wanted in dict.fromkeys((voice_gender(gender), "male")):
        for default in (True, False):
            chosen = next(
                (v for v in voices if v["gender"] == wanted and (v["default"] or not default)), None
            )
            if chosen:
                return chosen["key"], chosen
    return None


def available(language, gender="male", preferred=None, *, voices=None):
    chosen = selected_voice(language, gender, preferred, voices=voices)
    return chosen[1] if chosen else None


def missing_languages():
    return [language for language in ("en", "hi") if not available(language)]


class Unavailable(Exception):
    """No installed voice for this language."""


class Speaker:
    """Serialized speech for one window. Each new answer replaces the previous one."""

    def __init__(self, enabled=True, engine=None, emit=None, *, inference=None):
        self.enabled = enabled
        self.last_error = None
        self._engine = engine or ManagerPlayback(inference)
        self.catalogue = inference.catalogue if inference is not None else catalogue
        self._requests: queue.Queue = queue.Queue(maxsize=4)
        self._worker = None
        self._generation = 0
        self._active = threading.Event()
        self._playing = threading.Event()
        self._lock = threading.Lock()
        self._closing = False
        self._preferred: dict[str, str] = {}
        self._progress = 0
        self.emit = emit

    def prefer(self, key):
        """Choose one installed voice for its own language; None restores the defaults."""
        chosen = {entry["key"]: entry for entry in self.catalogue()}.get(key or "")
        if chosen:
            self._preferred[chosen["language"]] = key
        elif key is None:
            self._preferred.clear()
        return chosen

    def preference(self, language):
        return self._preferred.get(language)

    def _note_progress(self):
        """Counts audio actually handed to the device, so waiters can tell playing from stuck."""
        self._progress += 1

    @property
    def progress(self):
        return self._progress

    def warm(self, language, gender="male"):
        """Load a voice ahead of the first answer so speech is not delayed by model load."""
        preferred = self.preference(language)
        if self.enabled and available(language, gender, preferred, voices=self.catalogue()):
            with self._lock:
                generation = self._generation
            ready = threading.Event()
            self._submit(("warm", (language, voice_gender(gender), preferred, ready), generation))
            return ready
        return None

    def speak(self, text, language, gender="male", archive=None, gate=None, performance=None):
        """Queue one answer, replacing any current speech. False when nothing will be spoken."""
        text = (text or "").strip()
        if not self.enabled or not text:
            return False
        gender = voice_gender(gender)
        preferred = self.preference(language)
        if not available(language, gender, preferred, voices=self.catalogue()):
            self.last_error = f"No installed {language} voice; the answer is shown as text only"
            return False
        with self._lock:
            self._generation += 1
            self._discard_pending()
            generation = self._generation
        self._active.set()
        if performance:
            performance.mark("speech_queued")
        self._submit(
            (
                "speak",
                (text[:MAX_CHARACTERS], language, gender, preferred, archive, gate, performance),
                generation,
            )
        )
        return True

    def stop(self):
        """Abandon queued and playing speech immediately."""
        with self._lock:
            self._generation += 1
            self._discard_pending()
        self._engine.interrupt()
        self._active.clear()
        self._playing.clear()

    @property
    def speaking(self):
        return self._active.is_set()

    @property
    def playing(self):
        """Only actual output preparation/playback mutes the learner microphone."""
        return self._playing.is_set()

    def close(self):
        self._closing = True
        self.stop()
        if self._worker is not None:
            with suppress(queue.Full):
                self._requests.put_nowait(("close", None, 0))
            self._worker.join(timeout=3)
            if not self._worker.is_alive():
                self._worker = None
        else:
            self._engine.close()

    def _submit(self, request):
        with self._lock:
            if self._closing:
                self._active.clear()
                if request[0] == "warm":
                    request[1][-1].set()
                return
            if request[2] != self._generation:
                if request[0] == "warm":
                    request[1][-1].set()
                return
            if request[0] == "warm" and self._active.is_set():
                request[1][-1].set()
                return
            # Navigation may change several times during one native model load.
            # Keep only the latest request; never drop an answer behind old warmups.
            self._discard_pending()
            self._requests.put_nowait(request)
            if self._worker is None:
                self._worker = threading.Thread(target=self._run, name="human-test-speech", daemon=True)
                self._worker.start()

    def _discard_pending(self):
        while True:
            try:
                request = self._requests.get_nowait()
                if request[0] == "warm":
                    request[1][-1].set()
            except queue.Empty:
                return

    def _current(self, generation):
        with self._lock:
            return generation == self._generation

    def _run(self):
        while True:
            kind, payload, generation = self._requests.get()
            if kind == "close":
                # PortAudio and cached native resources are owned by this worker.
                # A slow native call must not race main-thread resource disposal.
                self._engine.close()
                return
            try:
                if not self._current(generation):
                    continue
                if kind == "warm":
                    language, gender, preferred, ready = payload
                    try:
                        warm = getattr(self._engine, "warm", self._engine.load)
                        warm(language, gender, preferred)
                    except Exception as error:
                        self.last_error = str(error) or type(error).__name__
                    finally:
                        ready.set()
                    continue
                text, language, gender, preferred, archive, gate, performance = payload
                if not self._current(generation):
                    continue
                stream = str(uuid4())
                sync, sid = archive if archive else (None, None)
                if sync:
                    sync.busy(True)
                    sync.audio_start(sid, stream)
                try:
                    self._engine.play(
                        text,
                        language,
                        lambda current=generation: self._current(current),
                        gender=gender,
                        preferred=preferred,
                        on_progress=self._note_progress,
                        **(
                            {"on_start": self._playing.set}
                            if isinstance(self._engine, ManagerPlayback)
                            else {}
                        ),
                        **({"gate": gate} if gate else {}),
                        **({"performance": performance, "on_timing": self._timing} if performance else {}),
                        **(
                            {
                                "on_audio": lambda pcm, rate, sync=sync, sid=sid, stream=stream: sync.audio(
                                    sid, stream, pcm, rate, "patient_audio"
                                )
                            }
                            if sync
                            else {}
                        ),
                    )
                finally:
                    if sync:
                        sync.audio_end(sid, stream)
                        sync.busy(False)
            except Exception as error:  # Speech must never break the interview.
                self.last_error = str(error) or type(error).__name__
            finally:
                if kind == "speak":
                    self._playing.clear()
                if kind == "speak" and self._current(generation):
                    self._active.clear()

    def _timing(self, performance):
        if self.emit:
            try:
                self.emit("performance", performance.snapshot())
            except Exception:
                pass  # Diagnostics cannot interrupt playback.


class ManagerPlayback:
    """Bounded remote synthesis playback through sounddevice."""

    def __init__(self, inference=None, output_device=None):
        from local_model_client import Connection

        self.connection = inference or Connection()
        self.output_device = output_device
        self.catalogue = inference.catalogue if inference is not None else catalogue
        self._interrupt = threading.Event()
        self._pcm = OrderedDict()
        self._pcm_bytes = 0
        self._producer = None
        self._stream = None
        self._stream_rate = None
        self._stream_device = None
        self._stream_latency = None
        self._high_latency = False

    def load(self, language, gender="male", preferred=None):
        chosen = selected_voice(language, gender, preferred, voices=self.catalogue())
        if not chosen:
            raise Unavailable(f"No installed {language} voice")
        return self.voice(*chosen)

    def voice(self, key, spec):
        from local_model_client.audio import RemoteVoice

        return RemoteVoice(self.connection, key, spec["language"], spec["gender"])

    def interrupt(self):
        self._interrupt.set()

    def warm(self, language, gender="male", preferred=None):
        self.connection.require("tts")
        return self.load(language, gender, preferred)

    def _output(self, rate):
        import sounddevice

        if self._stream is not None and (
            self._stream_rate != rate or self._stream_device != self.output_device
        ):
            self._stream.close()
            self._stream = None
        if self._stream is None:
            try:
                self._stream = sounddevice.RawOutputStream(
                    device=self.output_device,
                    samplerate=rate,
                    channels=1,
                    dtype="int16",
                    blocksize=1024,
                    latency="high" if self._high_latency else "low",
                )
            except Exception:
                if self._high_latency:
                    raise
                self._high_latency = True
                self._stream = sounddevice.RawOutputStream(
                    device=self.output_device,
                    samplerate=rate,
                    channels=1,
                    dtype="int16",
                    blocksize=1024,
                    latency="high",
                )
            self._stream_rate = rate
            self._stream_device = self.output_device
            self._stream_latency = "high" if self._high_latency else "low"
        try:
            self._stream.start()
        except Exception:
            with suppress(Exception):
                self._stream.close()
            self._stream = None
            if self._high_latency:
                raise
            self._high_latency = True
            return self._output(rate)
        return self._stream

    def _chunks(self, voice, key, text, tuning, cancelled):
        identity = (key, text, repr(tuning))
        cached = self._pcm.get(identity)
        if cached is not None:
            self._pcm.move_to_end(identity)
            voice.config.sample_rate = cached[0]
            yield from cached[1]
            return
        chunks, size = [], 0
        for chunk in voice.synthesize(text, tuning):
            if cancelled.is_set():
                return
            audio = chunk.audio_int16_bytes
            if not audio:
                continue
            if len(audio) % 2 or len(audio) > 16 * 1024 * 1024:
                raise Unavailable("Invalid synthesized audio")
            size += len(audio)
            if size <= PCM_CACHE_BYTES:
                chunks.append(audio)
            else:
                chunks.clear()
            yield audio
        if chunks and size <= PCM_CACHE_BYTES and not cancelled.is_set():
            while self._pcm and (
                self._pcm_bytes + size > PCM_CACHE_BYTES or len(self._pcm) >= PCM_CACHE_ENTRIES
            ):
                _, removed = self._pcm.popitem(last=False)
                self._pcm_bytes -= sum(map(len, removed[1]))
            self._pcm[identity] = (voice.config.sample_rate, tuple(chunks))
            self._pcm_bytes += size

    def play(
        self,
        text,
        language,
        still_current,
        gender="male",
        preferred=None,
        on_progress=None,
        on_audio=None,
        gate=None,
        performance=None,
        on_timing=None,
        on_start=None,
    ):
        chosen = selected_voice(language, gender, preferred, voices=self.catalogue())
        if not chosen:
            raise Unavailable(f"No installed {language} voice")
        key, paths = chosen
        if self._producer is not None and self._producer.is_alive():
            self._producer.join(timeout=3)
            if self._producer.is_alive():
                raise Unavailable("Previous speech synthesis is still stopping")
        voice = self.voice(key, paths)
        tuning = None
        self._interrupt.clear()
        pending = queue.Queue(maxsize=8)  # <=256 KiB of PCM ahead of playback.
        cancelled = threading.Event()

        def current():
            return not cancelled.is_set() and not self._interrupt.is_set() and still_current()

        def offer(value):
            while current():
                try:
                    pending.put(value, timeout=0.02)
                    return
                except queue.Full:
                    pass

        def produce():
            try:
                for audio in self._chunks(voice, key, text, tuning, cancelled):
                    if not current():
                        break
                    for offset in range(0, len(audio), 32768):
                        offer(audio[offset : offset + 32768])
                offer(None)
            except Exception as error:
                offer(error)

        self._producer = threading.Thread(target=produce, name="patient-synthesis", daemon=True)
        self._producer.start()
        stream = None
        complete = False
        output_reported = False
        try:
            while current():
                try:
                    audio = pending.get(timeout=0.02)
                except queue.Empty:
                    continue
                if isinstance(audio, Exception):
                    raise audio
                if audio is None:
                    complete = True
                    break
                if performance:
                    performance.mark("pcm")
                if stream is None:
                    if gate and not gate.wait(current):
                        return
                    if not current():
                        return
                    if on_start:
                        on_start()
                    stream = self._output(voice.config.sample_rate)
                    latency = getattr(stream, "latency", None)
                    if performance and isinstance(latency, (int, float)):
                        performance.output_latency_ms = round(latency * 1000, 2)
                for start in range(0, len(audio), SLICE_BYTES):
                    if not current():
                        return
                    submitted_at = time.perf_counter()
                    underrun = stream.write(audio[start : start + SLICE_BYTES])
                    if performance:
                        # A failed write is not an audio submission. Retain its
                        # start time after successful acceptance by the device.
                        performance.mark("output", at=submitted_at)
                    if underrun:
                        self._high_latency = True
                        if performance:
                            performance.underruns += 1
                    if on_audio:
                        on_audio(audio[start : start + SLICE_BYTES], voice.config.sample_rate)
                    if on_progress:
                        on_progress()
                    if performance and on_timing and not output_reported:
                        on_timing(performance)
                        output_reported = True
        finally:
            cancelled.set()
            if stream is not None:
                drained = False
                try:
                    if complete and current_without_cancel(self._interrupt, still_current):
                        stream.stop()
                        drained = True
                    else:
                        stream.abort()
                except Exception:
                    with suppress(Exception):
                        stream.abort()
                if performance:
                    performance.playback_status = "completed" if drained else "interrupted"
                    performance.mark("playback_end")
                    if on_timing:
                        on_timing(performance)
                if (self._high_latency and self._stream_latency == "low") or not drained:
                    with suppress(Exception):
                        stream.close()
                    self._stream = None
            self._producer.join(timeout=3)

    def close(self):
        self.interrupt()
        if self._producer is not None:
            self._producer.join(timeout=3)
        if self._stream is not None:
            with suppress(Exception):
                self._stream.close()
            self._stream = None
        self._pcm.clear()
        self._pcm_bytes = 0


def current_without_cancel(interrupted, still_current):
    return not interrupted.is_set() and still_current()
