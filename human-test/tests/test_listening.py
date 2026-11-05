"""One held-open microphone, cut into questions.

No real device is opened: `sounddevice` is replaced by a stream whose callback the test drives
directly, so every assertion is about the listener's own logic. Silence, speech onset, the
endpoint, queue saturation and device failure are all exercised without waiting on audio.
"""

import asyncio
from array import array
from uuid import uuid4

import pytest
import sounddevice as sd
from training_client.capture import BLOCK_MS, BLOCK_SAMPLES
from training_client.listening import PENDING_UTTERANCES, PREROLL_BLOCKS, Listener
from training_client.pms_client import ClientError

from human_test.config import Settings

QUIET = 20
LOUD = 4000


def settings(**kw):
    return Settings(
        _env_file=None,
        pms_token="fixture",
        audio_token="fixture",
        organization_id=uuid4(),
        connection_id=uuid4(),
        **kw,
    )


def block(level):
    """One block of a constant magnitude, whose RMS is exactly that magnitude."""
    return array("h", [level] * BLOCK_SAMPLES).tobytes()


class Device:
    """A scripted input stream. The test decides when audio arrives, block by block."""

    def __init__(self, monkeypatch):
        self.opens = 0
        self.closes = 0
        self.callback = None
        device = self

        class Stream:
            def __init__(self, **kw):
                self.callback = kw["callback"]

            def __enter__(self):
                device.opens += 1
                device.callback = self.callback
                return self

            def __exit__(self, *args):
                device.closes += 1

        monkeypatch.setattr(sd, "check_input_settings", lambda **kw: None)
        monkeypatch.setattr(sd, "RawInputStream", Stream)
        monkeypatch.setattr(sd, "query_devices", lambda: [{"name": "Fixture Mic", "max_input_channels": 1}])
        monkeypatch.setattr("training_client.capture._default_input_index", lambda: 0)

    async def feed(self, level, count=1, batch=24):
        """Deliver blocks and let the listener consume them.

        Batches stay under the reader's queue so nothing is dropped as overrun, and each batch
        yields long enough for the listener's idle sleep to come back round.
        """
        for start in range(0, count, batch):
            for _ in range(min(batch, count - start)):
                frame = block(level)
                self.callback(frame, BLOCK_SAMPLES, None, False)
            await settle()


async def settle(rounds=4):
    """Let the listener task run until it is waiting for audio again."""
    for _ in range(rounds):
        await asyncio.sleep(0.02)


async def started(listener, device):
    task = asyncio.create_task(listener.run())
    for _ in range(50):
        if device.callback is not None:
            break
        await asyncio.sleep(0.01)
    assert device.callback is not None, "the stream was never opened"
    return task


async def stopped(task):
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


async def collect(utterance):
    return [frame async for frame in utterance.frames()]


async def test_playback_refuses_an_unfinished_question(monkeypatch):
    device = Device(monkeypatch)
    muted = [False]
    listener = Listener(settings(), lambda *_: None, open_gate=lambda: not muted[0])
    task = await started(listener, device)
    try:
        await device.feed(QUIET, count=8)
        await device.feed(LOUD, count=10)
        question = listener.ready.get_nowait()
        assert question.ended is None
        muted[0] = True
        await device.feed(LOUD, count=4)
        with pytest.raises(ClientError, match="incomplete audio was not submitted"):
            await collect(question)
        assert question.ended == "playback_interrupted"
    finally:
        await stopped(task)


async def test_overload_discards_the_entire_sentence_before_rearming(monkeypatch):
    device = Device(monkeypatch)
    listener = Listener(settings(), lambda *_: None)
    task = await started(listener, device)
    try:
        await device.feed(QUIET, count=8)
        for _ in range(PENDING_UTTERANCES):
            listener.ready.put_nowait(object())
        await device.feed(LOUD, count=8)
        for _ in range(PENDING_UTTERANCES):
            listener.ready.get_nowait()
        await device.feed(LOUD, count=15)
        await device.feed(QUIET, count=20)
        assert listener.ready.empty()
        await device.feed(LOUD, count=10)
        await device.feed(QUIET, count=20)
        question = listener.ready.get_nowait()
        assert await collect(question)
        assert question.ended == "endpoint"
    finally:
        await stopped(task)


async def test_archive_observes_input_without_waiting_for_transcription_and_respects_mute(monkeypatch):
    device = Device(monkeypatch)
    muted = False
    listener = Listener(settings(), lambda *args: None, open_gate=lambda: not muted)
    captured = []
    listener.on_audio = captured.append
    task = await started(listener, device)
    try:
        await device.feed(QUIET, count=8)
        await device.feed(LOUD, count=6)
        assert captured and not listener.ready.empty()
        before = len(captured)
        muted = True
        await device.feed(LOUD, count=5)
        assert len(captured) == before
    finally:
        await stopped(task)


async def test_device_failure_ends_active_frames_and_wakes_a_full_queue(monkeypatch):
    device = Device(monkeypatch)
    fail = False

    def available():
        if fail:
            raise ClientError("Microphone disconnected")
        return True

    listener = Listener(settings(), lambda *a: None, open_gate=available)
    task = await started(listener, device)
    try:
        await device.feed(QUIET, count=8)
        await device.feed(LOUD, count=6)
        active = listener.ready.get_nowait()
        for _ in range(PENDING_UTTERANCES):
            listener.ready.put_nowait("queued text")
        fail = True
        await settle()
        assert task.done()
        with pytest.raises(ClientError, match="Microphone disconnected"):
            await task
        with pytest.raises(ClientError, match="Microphone stopped"):
            await asyncio.wait_for(collect(active), 0.3)
        assert listener.ready.get_nowait() is None
        assert listener.ready.empty()
    finally:
        await stopped(task)


# --- Idle listening ------------------------------------------------------------------------


async def test_two_minutes_of_silence_opens_the_device_once_and_produces_no_question(monkeypatch):
    """Idle silence used to close and reopen the device every five seconds, losing the moment
    in between. It must now cost one opening, no question, and a bounded amount of memory."""
    device = Device(monkeypatch)
    listener = Listener(settings(), lambda *a: None)
    task = await started(listener, device)
    try:
        await device.feed(QUIET, count=2 * 60 * 1000 // BLOCK_MS)
        assert device.opens == 1 and device.closes == 0
        assert listener.ready.empty(), "silence must never become a question"
        assert listener.active is None
        # The only audio retained while idle is the pre-roll, whatever the silence's length.
        assert len(listener.preroll) == PREROLL_BLOCKS
        assert listener.stream.blocks == 2 * 60 * 1000 // BLOCK_MS
    finally:
        await stopped(task)
    assert device.closes == 1, "the device is released when the session ends"


async def test_speech_long_after_the_old_no_speech_cutoff_is_still_captured(monkeypatch):
    """Capture used to give up after `no_speech_seconds`; a slow question was simply not heard."""
    device = Device(monkeypatch)
    quiet = settings(no_speech_seconds=5.0)
    listener = Listener(quiet, lambda *a: None)
    task = await started(listener, device)
    try:
        # Three times the old cutoff, then a question.
        await device.feed(QUIET, count=15 * 1000 // BLOCK_MS)
        assert listener.ready.empty()
        await device.feed(LOUD, count=6)
        assert not listener.ready.empty(), "speech after a long pause must still be captured"
    finally:
        await stopped(task)


# --- Speech onset --------------------------------------------------------------------------


async def test_the_audio_before_the_gate_arms_is_kept(monkeypatch):
    """The gate needs several voiced blocks to arm. Without a pre-roll the first syllable of
    every question was thrown away, which is what made quiet starts transcribe badly."""
    device = Device(monkeypatch)
    listener = Listener(settings(min_voiced_blocks=3), lambda *a: None)
    task = await started(listener, device)
    try:
        await device.feed(QUIET, count=PREROLL_BLOCKS)
        await device.feed(LOUD, count=3)
        utterance = listener.ready.get_nowait()
        # The question opens with audio captured before it was known to be a question.
        assert utterance.blocks == PREROLL_BLOCKS
        listener.send_now = None
        await device.feed(QUIET, count=settings().silence_ms // BLOCK_MS + 1)
        frames = await collect(utterance)
        assert frames[0] == block(QUIET), "the pre-roll must lead the question"
        assert block(LOUD) in frames, "the voiced onset must be in the same question"
        assert utterance.ended == "endpoint"
    finally:
        await stopped(task)


async def test_a_single_click_never_becomes_a_question(monkeypatch):
    device = Device(monkeypatch)
    listener = Listener(settings(min_voiced_blocks=3), lambda *a: None)
    task = await started(listener, device)
    try:
        await device.feed(QUIET, count=8)
        await device.feed(LOUD, count=1)
        await device.feed(QUIET, count=8)
        assert listener.ready.empty() and listener.active is None
    finally:
        await stopped(task)


# --- Endpoint and limits -------------------------------------------------------------------


async def test_configured_silence_ends_the_question_and_listening_continues(monkeypatch):
    device = Device(monkeypatch)
    config = settings(silence_ms=600)
    listener = Listener(config, lambda *a: None)
    task = await started(listener, device)
    try:
        # Calibration must see the room, not the question: the gate takes its floor from
        # the first blocks it hears, exactly as it does in a real interview.
        await device.feed(QUIET, count=8)
        await device.feed(LOUD, count=6)
        utterance = listener.ready.get_nowait()
        await device.feed(QUIET, count=config.silence_ms // BLOCK_MS + 1)
        assert utterance.ended == "endpoint" and listener.active is None
        # The device was never closed, so the next question needs no reopening.
        assert device.closes == 0
        await device.feed(LOUD, count=6)
        assert not listener.ready.empty(), "a second question follows with no reopening"
    finally:
        await stopped(task)


async def test_a_question_past_the_duration_limit_is_refused_not_truncated(monkeypatch):
    """The limit is per question now that the session has no end. A refusal must still be a
    refusal: a partial question is never handed on as if it were complete."""
    device = Device(monkeypatch)
    config = settings(max_question_seconds=3, no_speech_seconds=2.0)
    listener = Listener(config, lambda *a: None)
    task = await started(listener, device)
    try:
        # Calibration must see the room, not the question: the gate takes its floor from
        # the first blocks it hears, exactly as it does in a real interview.
        await device.feed(QUIET, count=8)
        await device.feed(LOUD, count=3 * 1000 // BLOCK_MS + 20)
        utterance = listener.ready.get_nowait()
        assert utterance.ended == "limit"
        with pytest.raises(ClientError, match="duration limit"):
            await collect(utterance)
        # Keep listening, but never submit the remaining fragment as a fresh question.
        assert device.closes == 0 and listener.active is None and listener.ready.empty()
        await device.feed(QUIET, count=config.silence_ms // BLOCK_MS + 1)
        await device.feed(LOUD, count=6)
        assert listener.ready.get_nowait().ended is None
    finally:
        await stopped(task)


async def test_send_now_closes_the_question_immediately(monkeypatch):
    import threading

    device = Device(monkeypatch)
    send_now = threading.Event()
    listener = Listener(settings(), lambda *a: None, send_now=send_now)
    task = await started(listener, device)
    try:
        await device.feed(QUIET, count=8)
        await device.feed(LOUD, count=6)
        utterance = listener.ready.get_nowait()
        assert utterance.ended is None
        send_now.set()
        await settle()
        assert utterance.ended == "operator"
        assert await collect(utterance) != []
        # The press is spent, not held: the next question must not end the instant it arms.
        assert not send_now.is_set()
        await device.feed(LOUD, count=6)
        following = listener.ready.get_nowait()
        assert following.ended is None, "a spent send-now must not truncate the next question"
    finally:
        await stopped(task)


# --- Playback, queueing and failure --------------------------------------------------------


async def test_the_patients_own_answer_is_never_captured_back(monkeypatch):
    """The device stays open during playback, so the answer is kept out by muting instead."""
    device = Device(monkeypatch)
    speaking = [True]
    reported = []
    listener = Listener(
        settings(), lambda kind, value: reported.append(value), open_gate=lambda: not speaking[0]
    )
    task = await started(listener, device)
    try:
        # Loud audio while the patient speaks is the answer itself: it must not become a question.
        await device.feed(LOUD, count=40)
        assert listener.ready.empty() and listener.active is None
        assert "Paused while the patient speaks" in reported
        speaking[0] = False
        await device.feed(LOUD, count=6)
        assert not listener.ready.empty(), "capture resumes the moment playback ends"
    finally:
        await stopped(task)


async def test_questions_queue_while_one_is_processed_and_saturation_is_reported(monkeypatch):
    """Capture continues through transcription, but finite buffering has to be visible."""
    device = Device(monkeypatch)
    reported = []
    config = settings(silence_ms=600)
    listener = Listener(config, lambda kind, value: reported.append(value))
    task = await started(listener, device)
    try:
        # Calibration must see the room, not the question: the gate takes its floor from
        # the first blocks it hears, exactly as it does in a real interview.
        await device.feed(QUIET, count=8)
        for _ in range(PENDING_UTTERANCES):
            await device.feed(LOUD, count=6)
            await device.feed(QUIET, count=config.silence_ms // BLOCK_MS + 1)
        assert listener.ready.qsize() == PENDING_UTTERANCES
        # Nothing is consuming them, so the next question cannot be retained.
        await device.feed(LOUD, count=6)
        assert listener.ready.qsize() == PENDING_UTTERANCES
        assert any("not kept" in note for note in reported), "saturation must be reported, not silent"
        assert listener.active is None
    finally:
        await stopped(task)


async def test_a_device_failure_reaches_the_worker_instead_of_being_awaited(monkeypatch):
    device = Device(monkeypatch)
    monkeypatch.setattr(
        sd, "check_input_settings", lambda **kw: (_ for _ in ()).throw(RuntimeError("no device"))
    )
    listener = Listener(settings(), lambda *a: None)
    task = asyncio.create_task(listener.run())
    await settle()
    # The worker is woken with a sentinel rather than left waiting on a queue forever.
    assert listener.ready.get_nowait() is None
    assert isinstance(listener.failure, RuntimeError)
    await asyncio.gather(task, return_exceptions=True)
    assert device.opens == 0


async def test_audio_lost_to_an_overrun_is_charged_to_the_question_it_happened_in(monkeypatch):
    """A glitch must cost one question, not the session.

    The single-question path failed the whole capture on overrun, which for a held-open stream
    would end the interview. Loss is therefore measured per question, against the same
    `max_lost_blocks` budget.
    """
    device = Device(monkeypatch)
    config = settings(max_lost_blocks=0)
    listener = Listener(config, lambda *a: None)
    task = await started(listener, device)
    try:
        await device.feed(QUIET, count=8)
        await device.feed(LOUD, count=6)
        utterance = listener.ready.get_nowait()
        # An overrun reported by the driver while this question is being captured.
        listener.stream.status_blocks += 1
        await device.feed(LOUD, count=2)
        assert utterance.ended == "lost_audio"
        with pytest.raises(ClientError, match="lost about"):
            await collect(utterance)
        await device.feed(LOUD, count=10)
        assert listener.active is None and listener.ready.empty()
        # The stream is still open, and a later question is unaffected by the earlier loss.
        assert device.closes == 0
        await device.feed(QUIET, count=config.silence_ms // BLOCK_MS + 1)
        await device.feed(LOUD, count=6)
        following = listener.ready.get_nowait()
        assert following.ended is None and following.lost_at_start == listener.lost
    finally:
        await stopped(task)
