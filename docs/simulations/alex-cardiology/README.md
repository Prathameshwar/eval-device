# Repeatable live audio interview

Run Alex's **Cardiology / Chest discomfort interview** with the 25 questions in
[questions.json](questions.json). This is a live integration/regression test, not
an isolated unit test: it uses your saved online ASR and LLM connections and
consumes their normal capacity. The runner continues to the next question after
an error, preserving evidence for all 25 questions.

From the repository root:

```powershell
.\docs\simulations\alex-cardiology\run.bat
```

For a shorter gap, or to disable patient answer playback:

```powershell
.\docs\simulations\alex-cardiology\run.bat --gap-seconds 0.5
.\docs\simulations\alex-cardiology\run.bat --gap-seconds 0.5 --mute
```

The batch entry point also works when this laptop disables PowerShell scripts.
`run.ps1` is an optional wrapper on machines that allow scripts.

The default is one second after the previous turn and playback finish. There is
one active question at a time. The desktop window opens automatically and runs
the whole interview. Leave the window open; closing it stops that run. Do not
change patient or model settings from another window during the run.

## What it exercises

- Existing demo launcher, PostgreSQL and PMS, using the published cloud profile.
- Production patient setup, microphone-button flow, paced PCM input, live cloud
  speech recognition, conversation history, live response model and streaming.
- Existing busy retries, request recovery by read-only status lookup, displayed
  errors, and actual local patient speech playback unless `-Mute` is supplied.
- Expected case facts, transcript comparison and conservative content checks.

Installed Piper creates the spoken questions. The production WAV reader feeds
that audio where microphone frames normally enter. This does **not** test the
physical microphone, room noise, VAD, accents or overlapping speech. Neither
the transcript nor the patient answer is mocked.

The runner selects and saves the fictional chest-discomfort case in English
through the normal API. That selection remains saved afterward. Model settings,
retry rules and quotas remain unchanged. Existing compatible services are reused;
only services started by this runner are stopped on exit. A new run asks the
questions anew; it never silently resumes/replays an interrupted provider request.

## Results

[First live baseline and failure analysis](findings-2026-09-20.md).

Every run creates `results/YYYY-MM-DD_HH-MM-SS_microseconds/` beside this README.
The launcher prints the absolute folder path. Generated results are excluded
from version control by this folder's `.gitignore`.

| Artifact | Contents |
|---|---|
| `report.md` | Readable per-question results, expected facts and errors |
| `results.csv` | Spreadsheet-ready questions, transcripts, answers and timings |
| `results.json`, `summary.json` | Detailed events, request IDs, stored provider outcomes and checks |
| `events.jsonl` | Incremental evidence, including retries, saved during the run |
| `inputs/q01.wav` … `q25.wav` | Exact synthetic speech used as input |
| `suite.json`, `questions.json` | Frozen check definitions and generated audio inventory |
| `case-snapshot.json` | Actual saved database case used by the run |
| `before-database.json`, `after-database.json` | Daily quota counters and status/error counts |
| `qNN.png`, `completed.png` | Application-only screenshots, when screenshot support is installed |
| `driver-error.json` | Safe harness diagnostics if the run cannot finish |

Only fictional interview content and allowlisted diagnostics are saved. Provider
credentials and tokens are not included. Speech recordings also follow the
application's normal PMS retention policy.

Exit status is `0` when all answers pass the checks, `2` when the run completes
with errors or answers needing review, and `1` for an incomplete/failed harness.
The automatic checks flag missing expected facts and transcription differences;
they are not a complete semantic or clinical correctness judgment. Read the
full answers alongside the scenario facts before deciding on fixes.

Rebuild a report from saved evidence without making cloud calls:

```powershell
.\human-test\.venv\Scripts\python.exe .\docs\simulations\alex-cardiology\review_results.py .\docs\simulations\alex-cardiology\results\<run-folder>
```

The existing demo environments, installed English Piper voices, cloud credentials
and a published cloud/cloud profile must already be configured. Follow
[the launcher guide](../../../start/README.md) for setup. The runner uses normal
authentication and does not increase limits or change provider credentials.

## Offline unit checks for the result reviewer

These tests do not call any service:

```powershell
.\human-test\.venv\Scripts\python.exe .\docs\simulations\alex-cardiology\test_review_results.py
```

They verify matching facts, incorrect identity, unavailable answers and transcript
comparison. The full 25-question run remains a separate live regression test.

## Organization quota follow-up

Online LLM defaults are now 5,000 accepted requests and 5,000,000 combined input/output
tokens per organization per UTC day. Local turns are exempt. New snapshots include
`charged_or_reserved_total_tokens`, and failed admissions retain their API error
code even when the desktop displays a human-readable message. The original baseline
results remain unchanged. See the [implementation and remaining fix plan](fix-plan-2026-09-20.md).

Run all nine offline reviewer/HTTP-observer/deadline checks with the installed desktop environment:

```powershell
.\human-test\.venv\Scripts\python.exe -m unittest discover -s docs/simulations/alex-cardiology -p "test_*.py"
```

The HTTP-observer test uses a mock transport and opens no GUI or cloud connection.

## Speech retry rounds

Cloud speech now retains each input for up to ten rounds of five retries, with a
three-second pause between rounds and the existing 1–5 second waits within each
round. This allows 51 submissions total, stopping on success, cancellation or an
error that cannot safely be retried. The response model still allows five retries.
The runner derives its per-question deadline from these settings and the request
timeout, so an allowed later round is not cut short. Exhausting speech retries
adds 177 seconds of scheduled waits plus request time; the gap between questions
still starts only after the previous turn and playback finish.

Run the mocked retry regression suite without using cloud capacity:

```powershell
.\human-test\.venv\Scripts\python.exe -m pytest -q human-test/tests/test_busy_retry.py --junitxml=.test_artifacts/speech-retry-rounds/retry-tests.xml
```

It covers later-round recovery, all-round exhaustion, retained audio, cancellation
between rounds and stopping on quotas or unknown outcomes. These checks do not
establish whether the live provider has recovered from throttling.

Check the actual desktop retry panel using mocked services and synthetic audio:

```powershell
.\human-test\.venv\Scripts\python.exe human-test/tests/busy_window_smoke.py --output .test_artifacts/speech-retry-rounds/ui
```

This opens a transparent test window, uses real retry delays, and saves only that
window's screenshots plus `ui-result.json`. It checks the centered clock panel at
1080×800 and 1180×860, countdown updates, recovery, exhaustion, cancellation, and
microphone/speaker interlocks. No cloud, physical microphone or camera is used.
The live runner also records structured `retry_status` events for each wait,
pause between rounds and request in progress.
