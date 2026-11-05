# Setup navigation and answer latency

Reviewed 2026-09-20 after the user reported that answer text appeared later after
moving between setup and conversation. The reported delay was before text, not
just before speaker playback.

## Findings and changes

| Area | Finding | Result |
|---|---|---|
| Back / Save & continue | Reuses the controller, API client, event loop and speaker. Save binds the new PMS revision and resets history. | Fifteen repeated transitions verified without timer/task accumulation or automatic microphone activation. |
| Local Qwen | Twelve fresh patient turns stayed stable across three rounds. | No progressive LLM slowdown reproduced in this isolated test; no model reload on page navigation. |
| Resident voice engine | Piper's default ONNX sessions create large CPU pools with spinning enabled. Two cached Hindi voices consumed CPU even in the sampled idle period. | Added `voice_runtime.py`: two intra-op threads, one inter-op thread, CPU provider and spinning disabled. |
| Repeated warmups | Old setup warmups could occupy the queue, and a full queue could drop a new spoken answer. | Keep the latest pending request, clear queued work on Stop/Back, and reject stale warmups. An answer takes priority over optional warmup. |
| Existing settings | Patient context, output caps and model selection are unrelated to the resource fix. | Preserved routing 75, answer 100, context 2,048, GPU policy and parallel voice-picker/prosody changes. |

The CPU contention is a credible contributor to answer delay because the combined
Qwen profile also performs work on CPU. This investigation did not capture the
user's exact slow turn or measure a complete spoken-interview before/after speedup.
It therefore does not establish that CPU contention was the only cause.

The [ONNX Runtime thread-management documentation](https://onnxruntime.ai/docs/performance/tune-performance/threading.html)
describes the default per-session physical-core thread pools and CPU cost of
spinning. The fix supplies explicit session options through Piper's normal voice
object, retaining the installed model/config and pronunciation data. Voices remain
cached; they are not reloaded for every answer.

## Measurements

Separate processes alternated the two installed Hindi voices for six cycles.
First loads were excluded from the warm synthesis means. These tests generated
synthetic audio only, with no microphone or patient recordings.

| Setting | Mean synthesis wall time | Mean CPU work per synthesis | CPU work during a 2 s idle sample |
|---|---:|---:|---:|
| Original default thread pools | 769 ms | 12,758 ms | 5.313 CPU seconds |
| Two threads, no spinning | 324 ms | 559 ms | 0.000 CPU seconds |
| Four threads, no spinning | 259 ms | 697 ms | 0.000 CPU seconds |

CPU work sums all threads, so it can exceed elapsed wall time. Chose two threads
to leave more CPU capacity for ASR/Qwen while keeping synthesis faster than audio
playback. A separate run through the final production loader also measured zero
idle CPU work; it ran alongside checks and is not used for the comparison above.
Both runs retained two voice instances; repeated cached selection took under 3 ms.

The native Qwen test used the production patient routing/wording pipeline, 16 GPU
layers, six CPU threads, a 256 MiB prompt cache and the current 75/100 output caps.
Each request had a fresh conversation, matching the history reset after setup.

| Question type | Round 1 | Round 2 | Round 3 | Model calls |
|---|---:|---:|---:|---:|
| Name, English | 2.44 s | 1.85 s | 1.82 s | 1 |
| Cough onset, English | 3.74 s | 3.49 s | 3.43 s | 2 |
| Medicines, English | 4.14 s | 3.80 s | 3.93 s | 2 |
| Age, Hindi | 2.31 s | 2.27 s | 2.39 s | 1 |

These Qwen timings include prompt budgeting, topic routing and validated patient
wording. They exclude ASR, database/authentication, UI rendering and speaker output.
All twelve selected the expected topic. The owned benchmark model server was
stopped afterward. No running application services were restarted or killed.

Narrative questions still need routing followed by wording, with the completed
answer released only after validation. Different questions can therefore have
different text latency even with unchanged navigation. History within a single
conversation also increases input work until the existing bounds trim old pairs;
a saved setup starts a new conversation.

## Review and operation

First review checked setup saving, history reset, timer/task reuse, model residency
and voice resources. Native measurement confirmed excessive voice CPU consumption;
added explicit thread settings and regression checks against real loaded sessions.

Second review checked queue replacement, stale work, cached model reuse, patient
gender/language, preferred voices and concurrent workspace edits. Added controlled
slow-load regressions proving that repeated warmups cannot displace the latest
answer and that Stop removes queued loads. Voice-picker work was being applied
in parallel; its manifest, prosody, selection methods and configuration were kept.
Speech test doubles now accept the new optional preferred-voice parameter.
The parallel playback-progress callback and stall-based microphone gate were also
preserved; their existing test doubles/expectations were brought into agreement
with that interface. Intermediate full runs caught these in-progress interface
changes; the final full run below passed after reconciliation.

Verification: `HUMAN_TEST_SPEECH=1 uv run pytest -q --tb=short tests` passed all
**122 tests**, with no skips. Ruff lint/format, mypy (13 source files) and offline
wheel/source build passed. A final import-order lint finding in the concurrently
updated installer was corrected without changing its behavior. The API/database
suite was not rerun for this desktop-only change; the opt-in native Qwen benchmark
exercised the existing patient pipeline without application database access.

Restart the Human-test window once to replace existing ONNX sessions with the
bounded thread pools. Back/Next alone keeps existing voices resident and cannot
reconfigure those sessions. No new downloads, API/database migration or cloud
calls are required.

Evidence: `.test_artifacts/navigation-latency/voices-0.json`, `voices-2.json`,
`voices-4.json`, `voices-production.json` and `patient-restarts.json`. The probes
contain only fictional sample prompts and resource/timing measurements.
