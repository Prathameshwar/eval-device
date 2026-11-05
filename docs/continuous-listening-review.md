# Continuous listening and truthful status — 2026-09-21

The microphone used to share a lifecycle with transcription, answering and playback: it was
opened for each question and closed again while that question was processed. Speech that
arrived in between was not heard at all, and the patient's status badge said "Ready" while the
machine was working. This is what changed, and what is still deliberately not changed.

## What was actually losing speech

Two separate gaps, and the smaller one was the more visible.

**Between questions, while idle.** Capture gave up after `no_speech_seconds` (5 s), reported
"No speech detected", and the app reopened the device 400 ms later. So the device cycled about
every 5.4 s and was deaf for the reopen plus however long the driver took to start the stream.
A question begun in that window lost its opening syllables.

**Around each question, while it was processed.** This was much larger. In cloud mode
`cloud_audio.transcribe` buffers the whole utterance and calls `frames.aclose()` *before* the
network request, so the device was already closed for transcription, answering and playback:
measured on this stack, about 0.6-1.2 s of transcription, 1.9 s of routing, 1.4 s of speaking,
and then the length of the spoken answer.

**And the status was wrong.** `Manikin.set_status` mapped three states and sent every other
message to "Ready" through `.get(state, "Ready")`. "Transcribing…", a failed turn and a
microphone warning all displayed as Ready, while the status line directly above showed the
accurate text. Two surfaces contradicting each other.

## What changed

**The badge is a phase, not an echo of the status line** (`manikin.phase_for`). Progress phases
have their own labels - Listening, Transcribing, Preparing reply, Question queued, Waiting for
model - and work reads as amber rather than grey. Anything that is prose leaves the badge
alone, so an informational message can no longer relabel a working patient as idle.

**One stream for the whole interview** (`listening.Listener`). The device is opened when
listening starts and released when it stops. Idle silence produces no question, makes no
request and reopens nothing. A 500 ms pre-roll is held behind the gate, so the audio captured
*before* the endpointer could prove speech had begun leads the question instead of being
discarded. The duration limit became per question, because the session itself now has no end.

**Capture is separated from processing.** `Listener.run()` is a task, not a generator: it keeps
filling the current question while the worker is awaiting that same question's frames. One
worker consumes them in order, owns no device, and builds the conversation history
sequentially. Typed questions join the same queue, so a spoken and a typed question can never
overtake one another.

**Two status surfaces.** The microphone surface says whether input is being heard - Listening,
Hearing you, Paused while the patient speaks, Microphone off. The processing surface says what
is happening to a question already captured. Queue depth is reported on both.

**A failed question no longer ends the session.** A failure the services report is shown as
`turn_failed` and the device stays open. An operator pause, an exhausted service, a lost device
and an unexpected error each still end the session, because none of them is a failure the loop
can honestly keep listening through. The 400 ms and 3 s reopen timers are gone; there is
nothing left to fire after a manual stop.

**Per-question loss accounting.** The single-question path failed the whole capture on driver
overrun, which for a held-open stream would end the interview. Loss is now measured per
question against the same `max_lost_blocks` budget.

**Status updates can no longer kill a session.** `emit` raised on a full display queue, which
was correct for a question's own updates and wrong for a microphone or queue-depth refresh -
a burst of them would have torn down listening. Those two kinds are dropped instead, and
`turn_failed` displaces a stale event so a failure is always reported.

## What did not change, deliberately

**The patient's own answer is still kept out of the microphone.** The device stays open during
playback, so instead of closing it the listener discards audio and clears its pre-roll while
speech is reaching the device. Playback *progress* decides, not elapsed time, so a long answer
is never cut into, and a device that stops progressing releases the microphone after
`SPEECH_STALL_LIMIT_MS` rather than stranding input. Both guarantees are the ones the old
reopen path had; only the mechanism moved.

The consequence is honest and worth stating plainly: **speech during playback is still not
captured.** Continuous listening removes the idle gap and the processing gap, not the playback
gap. Real interruption needs tested echo cancellation or a verified headset mode, because an
open microphone during playback will otherwise hear the patient and answer itself. That is the
next piece of work, not this one.

**Nothing partial is ever submitted.** A question that reaches its duration limit or loses
audio raises after its frames, so both transcription clients have consumed the whole question
before they send anything, and a truncated question is never passed off as complete.

**Audio is still byte-for-byte what the device produced.** The listener adds endpointing and a
pre-roll; it filters, gains and resamples nothing.

## Verification

296 desktop tests and 135 launcher tests pass. Eleven new tests in `tests/test_listening.py`
drive a scripted device with no real audio:

- two minutes of silence: one opening, no question, pre-roll bounded to its 500 ms, and the
  device released only when the session ends
- speech 15 s after the old 5 s cutoff is still captured
- the audio before the gate arms leads the question, and a single click never becomes one
- configured silence ends a question and the next one follows with no reopening
- a question past its duration limit is refused rather than truncated, and listening survives
- the operator's send-now closes a question immediately
- audio arriving while the patient speaks never becomes a question, and capture resumes the
  moment playback ends
- questions queue while one is processed, and saturation is reported rather than silent
- a device failure reaches the worker instead of being awaited forever
- driver overrun is charged to the question it happened in, not to the session

`tests/test_continuous_listening.py` covers the session: ordering across spoken and typed
questions, a failure that leaves the session listening, a manual stop leaving nothing pending,
and a display backlog that cannot kill the session. The playback guarantees moved to
`tests/test_speech.py::test_capture_is_muted_while_the_patient_speaks_and_a_stall_releases_it`.

## Limitations and follow-ups

- No real microphone, and no live cloud or hosted run: every test scripts the device.
- Latency was not re-measured end to end after this change; the gaps removed are structural,
  not timed.
- `capture.microphone` is now used only by tests and benchmarks. It duplicates about thirty
  lines of endpoint loop with the listener while sharing the gate, reader and level code.
  Eighteen of the thirty tests in `test_capture_quality.py` pin it, so it was kept rather than
  rewritten in this pass; the duplication should be retired.
- `no_speech_seconds` therefore no longer paces an interview. It bounds only that
  single-question helper, and its documentation says so.
- Speech during playback is still lost. See above: it needs echo cancellation, not a timer.
- `test_video.py::test_recording_dates_unique_names_private_playable_and_preview` compares a
  recording's name against `datetime.now()` captured earlier in the test, so it fails whenever
  the minute rolls over mid-run. Pre-existing and unrelated.
