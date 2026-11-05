# Local model selection and activation

Date: 2026-09-19. Scope: installed local models in Human-test; existing cloud paths,
PMS endpoints, schema and application data are preserved.

## Usage and implementation audit

Start the updated stack batch once. Open **Models → Local**, choose the installed
speech and response models, then **Set & activate local models**. Subsequent
switches keep the desktop open. **Refresh models** discovers new complete
installations. The current model remains resident between questions.

| Requirement | Implementation / evidence |
|---|---|
| Available model choices | Separate readonly speech/LLM dropdowns. Known model IDs only; required files, sizes and available manifests are checked. Checksums are verified during activation where manifests provide them. Native startup verifies loading. |
| Supported speech types | Whisper tiny/base/small/medium/large-v3/large-v3-turbo/medical; Nemotron; English/Hindi small Vosk. Missing/partial installations are excluded. |
| Supported LLM types | Qwen3 4B and QwenMedic, using their existing locked local installation profiles. |
| GPU memory release | Replace only affected launcher-owned services. Enumerate owned Windows job processes, stop the group, wait for process handles and empty job accounting, then verify the listener is released before loading replacements. |
| Execution settings | Existing GPU detection and shared-memory layer policy; Nemotron/Vosk stay on their CPU adapters. Language-specific choices restrict the setup language. |
| Persistence | Existing authenticated PMS connection/profile APIs. Reuse configured connections; create a missing selected local connection with encrypted credentials through PMS. Verify native services and PMS connection before profile publication. |
| Authorization and scope | Per-launch random capability on loopback only; browser Origin and unexpected Host rejected. The launcher acts only in its own isolated-demo organization and rechecks its PMS management permission. External services cannot be stopped. |
| Failure handling | One serialized switch, up to five starts for retryable failures, previous-service recovery, bounded status polling and stable request IDs. No automatic replay of an uncertain PMS publication. |
| Compatibility | Existing cloud/custom choices remain available; published local choices are staged until activation. The existing PMS local-speech route label remains `local_whisper`; the audio service chooses the actual backend from the saved model ID. No schema migration required. |

## Installed models and real checks

| Installed model | Device exercised | Result |
|---|---|---|
| Whisper small | CUDA | Switched, transcribed a prerecorded English question and obtained a patient answer through real PMS/Qwen. |
| Whisper medium | CUDA | Same full flow passed. |
| Whisper large-v3-turbo | CUDA | Same full flow passed. |
| Whisper large-v3 | CUDA | Same full flow passed after switching back from CPU Nemotron. |
| Nemotron 3.5 ASR streaming 0.6B | CPU | Service switch and full request flow passed; this clip was recognized only as “Start”, so recognition quality is limited. |
| Qwen3 4B | CPU → CUDA with 16 GPU layers | Owned LLM process replaced and readiness/inference verified. Same-selection requests retained model processes. |
| Vosk / Whisper Medical / QwenMedic | Not fully installed | Excluded from current dropdowns. Selection/adapter rules are implemented; real inference with these missing assets was not verified. |

The Whisper clip was “When did the chest pain start?” and its case-grounded answer
was “It began two days ago.” These are functional examples, not a clinical accuracy
evaluation. Model switch plus one audio-to-answer turn took roughly 19–27 seconds
in the initial run. The models were not reloaded for individual questions.

## Review findings and fixes

1. Preserve model state after a successful PMS commit even if writing the local
   convenience environment file fails; rolling back the runtime then would create
   a mismatch with PMS. Regression test passes.
2. Read back uncertain publications instead of resubmitting. Duplicate activation
   IDs return their existing status and cannot run a second switch.
3. Keep successful rollback services supervised; suspend failed recovery rather
   than closing the desktop or dereferencing a missing process. Explicit activation
   can attempt recovery again.
4. Windows job accounting alone can reach zero before process handles signal exit.
   Added process-handle waits and a real parent/child regression test.
5. Refresh stale profile revisions, stage local profile choices, maintain cloud
   choices when the local controller is unavailable, and keep language-specific
   setup defaults valid.

Final verification: **79 desktop tests**, **86 launcher tests**, and **34 local-LLM
tests** passed (199 total, plus 39 unittest subtests); Ruff lint/format, desktop
mypy and the wheel/sdist build passed. No tests in these suites were skipped.
The first native pass exercised all five installed speech models. After the
process-release fix, a second native pass used the real authenticated control
client/server to switch small → CPU Nemotron → large-v3, run a full recorded-audio
turn after each, and confirm same-selection calls retained processes. Qwen also
moved from a real CPU process to a new GPU process. All test-owned model services
and disposable PostgreSQL clusters stopped cleanly. Both review passes are complete.

Native fixtures and measurements: `.test_artifacts/local-model-switch/`.
Native tests use dedicated disposable PostgreSQL clusters, separate credentials,
private recordings and fictional cases. No existing application database was used
for destructive testing. No live cloud calls or Raspberry Pi hardware were tested.
