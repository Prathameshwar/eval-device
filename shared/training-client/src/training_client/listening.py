"""One microphone stream for a whole interview, cut into utterances.

Capture used to share a lifecycle with transcription, answering and playback: the device was
opened for each question and closed again while that question was processed, so anything said
in between was never heard. Here the stream is opened once when listening starts, the
endpointer hands finished utterances to a worker that owns no device, and idle silence costs
nothing - no request, no reopening, and a bounded amount of memory.

Frames are still yielded byte-for-byte as the device produced them. What this module adds is a
pre-roll, so the beginning of a question survives the moment before the gate arms, and a
per-utterance duration limit, because the listening session itself now has no end.
"""

import asyncio
import queue
import time
from collections import deque

from .capture import (
    BLOCK_MS,
    CaptureQuality,
    _Gate,
    block_levels,
)
from .devices import Microphone
from .performance import TurnTiming
from .pms_client import ClientError

# Speech reliably starts before an energy gate can prove it. Half a second of audio is held
# behind the gate so the first syllable is transcribed rather than guessed at.
PREROLL_MS = 500
PREROLL_BLOCKS = max(1, PREROLL_MS // BLOCK_MS)
# Questions captured but not yet processed. Two lets a learner ask the next question while the
# previous one is still being transcribed; a third is refused out loud, never dropped silently.
PENDING_UTTERANCES = 2
# Sustained quiet, not one dipped block, is what breaks a run of speech.
QUIET_BLOCKS_TO_RESET = 2
LIMIT_MESSAGE = "Question reached duration limit; speak a shorter question"


class Utterance:
    """One learner question: a live stream of blocks, bounded by its own duration limit.

    The listener fills this whether or not anyone is reading it yet, so capture never waits for
    transcription. `frames()` is consumed once, by the processing worker.
    """

    def __init__(self, settings, quality, preroll=()):
        self.quality = quality
        self.limit = max(1, int(settings.max_question_seconds * 1000 // BLOCK_MS))
        self.blocks = 0
        self.ended = None
        self.lost_at_start = 0
        self._frames: asyncio.Queue = asyncio.Queue()
        self.performance = TurnTiming()
        self.performance.mark("speech_end")
        for frame, levels in preroll:
            self.add(frame, levels)

    @property
    def full(self):
        return self.blocks >= self.limit

    def add(self, frame, levels):
        """Route one measured block into this question. False once it may not grow."""
        if self.ended is not None or self.full:
            return False
        rms, peak, clipped = levels
        self.quality.blocks += 1
        self.quality.peak = max(self.quality.peak, peak)
        self.quality.clipped_samples += clipped
        self.quality.speech_rms = max(self.quality.speech_rms, rms)
        self._frames.put_nowait(frame)
        self.blocks += 1
        return True

    def close(self, reason):
        if self.ended is None:
            self.performance.mark("endpoint")
            self.ended = reason
            self.quality.ended = reason
            self._frames.put_nowait(None)

    async def frames(self):
        """Yield blocks as capture produces them, then stop at the endpoint.

        A refusal is raised after the audio rather than before it, so the reason is reported
        once the whole question is known. Nothing partial is submitted either way: both
        transcription clients consume this iterator to completion before they send anything.
        """
        while True:
            frame = await self._frames.get()
            if frame is None:
                break
            yield frame
        if self.ended == "limit":
            raise ClientError(LIMIT_MESSAGE)
        if self.ended == "device_error":
            raise ClientError("Microphone stopped during this question; incomplete audio was not submitted")
        if self.ended == "playback_interrupted":
            raise ClientError(
                "Patient playback interrupted this question; incomplete audio was not submitted"
            )
        if self.ended == "lost_audio":
            lost = (self.quality.dropped_blocks + self.quality.status_blocks) * BLOCK_MS
            raise ClientError(f"Microphone lost about {lost} ms of audio; this question was not submitted")


class Listener:
    """Owns the input device for a whole listening session and emits utterances.

    `run()` is a task, not an async generator: it has to keep filling the current utterance
    while the worker awaits that same utterance's frames, which a generator suspended by its
    own consumer could not do.
    """

    def __init__(self, settings, emit, *, open_gate=None, send_now=None, source_factory=Microphone):
        self.settings, self.emit = settings, emit
        self.source_factory = source_factory
        self.on_audio = None
        # Closed while the patient is speaking: an open device must not hear the answer back.
        self.open_gate = open_gate or (lambda: True)
        self.send_now = send_now
        self.ready: asyncio.Queue = asyncio.Queue(maxsize=PENDING_UTTERANCES)
        self.failure = None
        self.stream = CaptureQuality()
        # Attributes rather than locals so a test can assert that idle listening stays bounded
        # and that nothing is being captured between questions.
        self.preroll: deque = deque(maxlen=PREROLL_BLOCKS)
        self.active = None

    @property
    def lost(self):
        return self.stream.dropped_blocks + self.stream.status_blocks

    def _begin(self, preroll):
        """A new question, carrying the room measurements the session has already learned."""
        quality = CaptureQuality()
        quality.device_index = self.stream.device_index
        quality.device_name = self.stream.device_name
        quality.warning = self.stream.warning
        quality.noise_floor = self.stream.noise_floor
        quality.threshold = self.stream.threshold
        quality.calibrated = self.stream.calibrated
        utterance = Utterance(self.settings, quality, preroll)
        utterance.lost_at_start = self.lost
        return utterance

    def _finish(self, utterance, reason):
        """Close one question, crediting only the audio lost while it was being captured."""
        utterance.quality.noise_floor = self.stream.noise_floor
        utterance.quality.threshold = self.stream.threshold
        utterance.quality.calibrated = self.stream.calibrated
        lost = self.lost - utterance.lost_at_start
        if lost:
            utterance.quality.dropped_blocks = self.stream.dropped_blocks
            utterance.quality.status_blocks = self.stream.status_blocks
            utterance.quality.status_flags = self.stream.status_flags
        utterance.close(reason)

    async def run(self):
        """Hold the device open, arm on speech, hand each finished question to the worker."""
        try:
            gate = _Gate(self.settings)
            preroll, run, quiet = self.preroll, 0, 0
            muted = False
            rejected = False
            with self.source_factory(self.settings, self.stream) as frames:
                self.emit("mic", "Listening")
                while True:
                    if self.send_now is not None and self.send_now.is_set():
                        # Consumed here, once. Leaving it set would end the *next* question the
                        # moment it armed, and a press with nothing being captured is simply
                        # spent rather than held against a later one.
                        self.send_now.clear()
                        if self.active is not None:
                            self._finish(self.active, "operator")
                            self.active, run, quiet = None, 0, 0
                    speaking = not self.open_gate()
                    if speaking != muted:
                        muted = speaking
                        if speaking:
                            # Anything in flight ends here, and the pre-roll is dropped so the
                            # answer's tail cannot arm the gate on the way out.
                            if self.active is not None:
                                self._finish(self.active, "playback_interrupted")
                                self.active = None
                            preroll.clear()
                            run = quiet = 0
                            self.emit("mic", "Paused while the patient speaks")
                        else:
                            self.emit("mic", "Listening")
                    try:
                        frame = frames.get_nowait()
                    except queue.Empty:
                        await asyncio.sleep(0.01)
                        continue
                    if speaking:
                        continue
                    if self.on_audio:
                        self.on_audio(frame)
                    levels = block_levels(frame)
                    speech = gate.update(levels[0])
                    self.stream.blocks += 1
                    self.stream.noise_floor, self.stream.threshold = gate.floor, gate.threshold
                    self.stream.calibrated = gate.calibrated
                    if speech:
                        self.stream.voiced_blocks += 1
                        run += 1
                        quiet = 0
                    else:
                        quiet += 1
                        if quiet >= QUIET_BLOCKS_TO_RESET:
                            run = 0
                    if rejected:
                        # Once a sentence was refused, never reinterpret its tail as
                        # another question when the worker happens to free a slot.
                        if quiet * BLOCK_MS >= self.settings.silence_ms:
                            rejected = False
                            preroll.clear()
                            run = quiet = 0
                        continue
                    if self.active is None:
                        preroll.append((frame, levels))
                        if run < self.settings.min_voiced_blocks:
                            continue
                        candidate = self._begin(list(preroll))
                        try:
                            self.ready.put_nowait(candidate)
                        except asyncio.QueueFull:
                            # Visible, not silent: finite buffering cannot hold unlimited
                            # speech while the services are slow.
                            self.emit("mic", "Listening — busy, that question was not kept")
                            preroll.clear()
                            run = 0
                            rejected = True
                            continue
                        self.active = candidate
                        preroll.clear()
                        self.emit("mic", "Hearing you")
                        continue
                    if speech:
                        self.active.quality.voiced_blocks += 1
                        self.active.performance.mark("speech_end", at=time.perf_counter(), replace=True)
                    if not self.active.add(frame, levels):
                        self._finish(self.active, "limit")
                        self.active, run, quiet = None, 0, 0
                        rejected = True
                        self.emit("mic", "Listening")
                        continue
                    if self.lost - self.active.lost_at_start > self.settings.max_lost_blocks:
                        self._finish(self.active, "lost_audio")
                        self.active, run, quiet = None, 0, 0
                        rejected = True
                        self.emit("mic", "Listening")
                        continue
                    if quiet * BLOCK_MS >= self.settings.silence_ms:
                        self._finish(self.active, "endpoint")
                        self.active, run, quiet = None, 0, 0
                        self.emit("mic", "Listening")
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 - handed to the worker, never swallowed
            self.failure = error
            # Wake both a consumer of live frames and a worker awaiting its next question.
            # Pending questions are abandoned when the input device fails; a full queue must
            # never hide the failure sentinel and strand the worker after it drains.
            if self.active is not None:
                self._finish(self.active, "device_error")
                self.active = None
            while not self.ready.empty():
                self.ready.get_nowait()
            self.ready.put_nowait(None)
            raise
