# Patient LLM latency review

2026-09-19. Scope: local Qwen inference through the existing PMS patient pipeline.
The application database, patient case records, ASR models and desktop layout were
not changed. GPU selection remains enabled; the combined launcher uses 16 of
Qwen's 37 layers on the 4 GiB RTX 500 Ada, leaving capacity for resident Whisper.
Remaining layers execute on CPU. Full GPU offload remains available for a
standalone LLM when memory permits.

## Findings and implementation

| Finding | Change | Boundary preserved |
|---|---|---|
| Routing and spoken-answer prompts alternate; the extra native prompt cache was disabled | Enable 256 MiB of reusable prompt state in system RAM | One inference slot, no disk cache, no slot-management endpoint, no prompt logging |
| Every matched topic triggered a second wording call, including names and readings | Return the complete authored answer for one exact attribute after the LLM routes it | Same patient snapshot, language, visibility filtering and final authorization |
| Narrative answers need context and controlled wording | Keep both calls for symptoms, medicines, history and combined topics | Existing prompts, history, length/number guard and authored fallback |
| Stage timing was harder to inspect | Add `voice_ms` beside `routing_ms` and actual `provider_calls` | Missing second-call timing is null, not an invented measurement |
| Tokenizer requests add comparatively little overhead | Retain exact local token budgeting and the 2,048-token limit | No context-size guess, cached authorization or dropped mandatory facts |

Exact attributes are name, age, sex, body size, temperature, heart rate, pulse,
blood pressure, breathing rate, oxygen saturation and pain score. The fast path
requires exactly one routed topic. It returns the authored patient sentence,
not raw measurement fields. The change applies to local and online patient
connections; online behavior is checked with mocks only. General LLM requests
remain unchanged.

## Measured comparison

Same installed Qwen3 4B Q4_K_M, 16 GPU layers, six CPU threads and 2,048-token
context. Four fictional dry-cough-case questions, two passes each, with a fresh
model server per configuration. These times include prompt budgeting, routing
and the accepted patient answer; they exclude startup, ASR, database/auth and TTS.
The first question includes a cold prompt cache.

| Question | Before, mean | After, mean | Reduction |
|---|---:|---:|---:|
| Name, English | 2.70 s | 1.66 s | 38% |
| Symptom onset, English | 3.83 s | 2.56 s | 33% |
| Medicines, English | 4.33 s | 3.33 s | 23% |
| Age, Hindi | 4.12 s | 1.95 s | 53% |
| All eight turns | 3.75 s | 2.38 s | 37% |

All eight questions selected the expected topics in both runs. Subsequent routing
calls reused approximately 715 of 730 prompt tokens. Native token usage includes
cached tokens as a subset of prompt tokens, not additional tokens. The rerun of
the previous path averaged approximately 3.98 s, supporting the observed benefit.
Four CPU threads did not consistently improve the result; six remains the default.

The laptop had substantial unrelated CPU activity (93% observed between runs).
It was left running. These are small, practical samples rather than an isolated
performance or clinical-accuracy study. Longer history, longer generated answers
and other GPU workloads can increase latency. Whisper was not loaded during the
timing comparison; its normal shared-GPU layer allocation was retained.

Evidence under `.test_artifacts/llm-latency/`: `baseline.json`, `baseline-recheck.json`,
`cache256.json`, `optimized4.json`, `optimized6.json`. Samples use the fictional
seed scenario only. The reusable script is
`local-models/qualification/benchmark_patient_latency.py`; it refuses to replace a
running model server and always closes its owned process. It moved out of
`platform/api/scripts/` when local execution became the caller's: it now drives
`human_test.local_turn`, the same path the desktop app takes, because the platform
no longer dials a model on this laptop (see
[local execution boundary](local-execution-boundary.md)). The measured pipeline
(prompt budgeting, routing, guarded answer) is the shared `training-contracts`
code, so the numbers above remain comparable.

## Review and verification

First review checked prompt reuse against the pinned llama.cpp release, patient
visibility and token accounting. Added bounded configuration validation, a zero
cache option and compatibility for older configuration files. Exact answers
retain the admission reservation for the possible second call; actual usage
reports only executed calls. No quota refund is guessed from missing usage.

Second review checked single-topic versus mixed/narrative behavior, Hindi output,
JSON/SSE, duplicate request recovery and cloud parameter compatibility. Updated
native, Azure and OpenAI mock tests that previously assumed every topic required
two calls, and retained two-call coverage for mixed questions. The affected checks
passed in two focused runs (11 patient/Azure and four online round-trip checks).
The existing generated wording guard checks length/numbers; it is not a complete
clinical fact validator.

Desktop: 114 passed with both native voices enabled. Launcher: 87 passed. Local
LLM: 35 passed. API lint, formatting, mypy and offline package build passed. Real PMS
JSON/SSE calls used the authenticated API and disposable PostgreSQL, with native
Qwen for English/Hindi facts, daily-life topics, backchannels, commands and unknown
questions (`native-pms.json`). The reusable benchmark script also passed all four
sample questions (`reusable-script.json`).

API verification completed in parts because the broad run was interrupted. Its
first 216 cases recorded 210 passes, five outdated two-call assertions and one
opt-in ASR integration skip. The assertions were corrected and expanded to cover
both one- and two-call behavior; all 15 affected/focused checks passed. The resumed
remaining modules passed all 87 checks, including overlap for completeness.
Comparison with collection confirms coverage of all **282 currently enabled API
cases**; the one opt-in desktop/audio/PMS round trip remains skipped. Native Qwen
JSON/SSE and patient routing were exercised. No database tests were skipped.
This was not one uninterrupted green full-suite invocation. Logs and the coverage
mapping are in `full-api.txt`, `review-regressions.txt`, `online-regressions.txt`,
`remaining-api.txt`, `current-test-cases.txt` and `verification-parts.json`.

Both review-owned Qwen instances and the dedicated PostgreSQL server were stopped.
The interrupted disposable test database was removed from that dedicated cluster;
application databases and unrelated processes were untouched.

Desktop and launcher tests require different environments; an initial combined
collection in the desktop environment failed on missing launcher dependencies and
duplicate test module names. Both suites passed when run separately in their
documented environments. No dependency changes were needed.

## Applying the change

Restart the local stack once so PMS and Qwen load the new code and cache setting.
Patient/model selection continues to work as before. No database migration or
model download is needed. In `local-models/config.local.json`, `prompt_cache_mib`
can override the 256 MiB default; accepted range is 0–1024, with 0 disabling it.
The cache uses temporary RAM and is cleared when Qwen exits. Patient history is
still supplied and authorized on every request; this is not an answer cache or
a shortcut around PMS permissions.

The runtime options and prefix-reuse behavior were checked against the
[pinned llama.cpp server documentation](https://github.com/ggml-org/llama.cpp/blob/b11046/tools/server/README.md).
No live cloud inference, Pi hardware or new microphone/speaker audition was
performed for this optimization.
