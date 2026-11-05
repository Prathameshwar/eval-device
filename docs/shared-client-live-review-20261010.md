# Shared client: local desktop integration, 2026-10-10

Started Manage Local Models, the local platform API, then Human-test using the
existing enrolled local test device and published fictional scenarios. No API
implementation, schema, model assignment or database migration was changed.

The installed services are Qwen 3.5 4B on CUDA (20 offloaded layers), Whisper
large-v3 on CUDA, and Piper English male on CPU. API readiness and the normal
Human-test saved-device startup checks passed. Existing weights were reused.

## Scenarios and findings

Each scenario exercises three typed questions, one synthesized spoken question
through the real continuous Listener and Whisper, and one typed question queued
while listening. Actual Qwen inference and Piper speaker output remain enabled.
Only the input-device source is replaced with paced 50 ms PCM blocks; inference,
endpointing, playback, persistence and API calls are real.

| Scenario | Observed answers |
| --- | --- |
| Chest discomfort interview | Chest tightness when walking uphill; schoolteacher living with family; onset two days ago; Paris for the general-knowledge question |
| Wheeze interview | Wheezing and tight breathing; dust trigger and temporary reliever-inhaler benefit; same published patient background; onset two days ago; Paris |

The scenarios use separate conversations. Each has five completed turns. The API
returned ten new completed history records; both archives reported complete
capture and fully synchronized items, including microphone and patient audio.
Stopping listening released the source and cleared the shared runtime operation.
Completing each practice returned the desktop to setup. Runtime observer failures
and application errors were zero. Closing the desktop left all three services Ready.

The live window revealed a misleading Human-test message: pausing an idle
microphone after a completed answer displayed "Cancelled. Ask the question again."
Human-test now reports normal listening completion for an idle pause, while an
interrupted question or typed operation retains the cancellation warning. The busy
state is sampled on the worker loop before cancellation unwinds it. Three new
regression cases cover idle listening, an active question and a typed operation.
This fix is confined to the desktop adapter; the common runtime and API need no
further change for these runs.

Two initial automation passes stopped after the first scenario because of the
window-capture helper, not an application failure. The driver now captures the
explicit window handle and does not abort functional checks for optional capture
errors. A complete run then verified both scenarios and exposed the pause-message
issue during visual inspection.

## Verification and limits

- Affected Human-test listening, speech, patient-workflow and lifecycle tests:
  **64 passed**. Ruff lint/format passed; mypy passed for 13 desktop modules.
- Authenticated archive reads verified uploads. Anonymous inference metadata
  access returned 401; inference credentials were rejected for management with 403.
- Physical microphone probing returned digital silence. Actual spoken microphone
  quality remains unverified; the ASR checks used synthesized input.
- No cloud calls, camera recording, Raspberry Pi hardware, LAN transport, hosted
  deployment, destructive database integration tests or portable rebuild were run.

Ignored evidence and driver files are under
`.test_artifacts/shared-client-live-20261010/`. They are not published. Existing
pairing credentials remain in protected local storage and are absent from this
report. The application database was used only through normal application APIs.

The post-fix repetition passed all ten exchanges again, including assertions that
both idle pauses show "Listening stopped" without a cancellation banner. The chest
archive received all 16 expected items and the wheeze archive all 14; both were
complete, synchronized and marked completed. The desktop error log was empty.
Human-test was reopened through the normal saved-device launcher; Local Models,
the API and the desktop remain running. Completion is tracked in
[shared-client-todo.md](shared-client-todo.md).
