# Human-test five-retry review — 2026-09-20

The desktop now retries explicit speech/response capacity rejections five times,
waiting 1, 2, 3, 4 and 5 seconds after each rejection. This means at most six
submissions per stage and 15 seconds of backoff, plus request execution time.
This supersedes the three-retry behavior recorded in the earlier
[online speech/response review](online-speech-response-final-review.md).

## Findings and changes

The earlier implementation already retained the WAV and retried only the rejected
stage, but stopped after three retries. Its waiting message also remained on screen
while the next request was executing. A typed question could leave the previous
answer's speaker playback running.

- `pms_client.retry_busy` now has five incremental waits, explicit retry lifecycle
  events, and separate waiting/in-progress messages. Success, cancellation and
  errors all clear the retry state. Each stage has its own bounded retry budget.
- Cloud transcription explicitly closes capture before the first upload and
  freezes the WAV, language and selected profile parameters for all attempts.
  Definite rejections get new request keys because a failed admitted request can
  retain its failed result. A successful transcription is not repeated for LLM
  retries; the response stage retains the same question/history.
- The window stops existing playback for typed questions and retry entry, keeps
  question/voice inputs locked, prevents microphone reopening and speaker dispatch
  while retrying, and shows **Waiting for model** on the manikin. **Cancel queued
  question** cancels either a spoken or typed turn. A completed answer is spoken
  once, then continuous listening waits for playback to finish. Exhaustion returns
  the controls to **Start microphone**.

Only `speech_busy`, `llm_busy` and `concurrency_limit` rejections are retried.
Timeouts, uncertain submissions, partial output, authorization/configuration errors
and exhausted quotas are not replayed. Request recovery, input bounds and
credential handling remain in place. No API, schema or provider configuration
changes were required; the shared helper also governs local LLM capacity retries.

## Verification

From `human-test`:

- `uv run pytest -q`: **184 passed, 6 skipped**. Skips are four opt-in installed
  Piper voice checks and two opt-in native local-model checks.
- Focused speech/cloud/retry run: **56 passed, 4 skipped, 1 deselected**; the
  separate Tk speaker subprocess was deselected for that run and passed in the
  full suite.
- `uv run ruff check .`, `uv run ruff format --check .`, and
  `uv run mypy src/human_test`: passed. Mypy reports its existing notes about
  untyped function bodies.

The regression cases cover each busy stage and both consecutively, HTTP and SSE
busy errors, immutable captured audio, unique attempt keys, a single completed
history pair and speaker event, early recovery, exhaustion, cancellation in each
of the five waits, concurrent-question rejection, partial-output protection and
unknown outcomes including a timeout after an earlier busy rejection.

The native Windows check
`human-test\.venv\Scripts\python.exe human-test\tests\busy_window_smoke.py`
passed using the actual Window, Controller, preflight, HTTP client, async worker
and button callbacks. It uses real timer waits, generated PCM, mocked HTTP busy
responses and a speaker probe. Measured intervals between submissions:

| Stage | Retry 1 | Retry 2 | Retry 3 | Retry 4 | Retry 5 |
| --- | --- | --- | --- | --- | --- |
| Speech | 1.02 s | 2.02 s | 3.00 s | 4.02 s | 5.00 s |
| Response | 1.02 s | 2.00 s | 3.01 s | 4.00 s | 5.00 s |

The check verified one capture, capture closed before submissions, identical WAV
bytes across six speech attempts, identical messages across six response attempts,
disabled input/voice controls and no speaker playback during retries, exactly one
final answer dispatch, cancellation of a typed retry, and restored controls after
six busy rejections. Completed history survived the failed follow-up. The test
window and its worker were closed.

Final review checked cleanup on success/error/cancellation, bounded retries,
stage isolation, retention, playback/capture ordering and unknown-outcome handling.
No further confirmed implementation findings remained. These are controlled busy
response tests, not a claim of reproducing Azure/Nemotron throttling live. No real
microphone, speaker playback, camera media, live provider, database or Pi checks
were needed for this desktop-only change.
