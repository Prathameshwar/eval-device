# Consolidated correctness review — 2026-09-19

This pass reinspected the recent online/offline changes and their test evidence.
It found and fixed remaining desktop audio-readiness failure cases. Existing
application data, model configuration and parallel work were preserved.

## Findings and fixes

| Finding | Fix | Verification |
|---|---|---|
| A null language list raised an internal exception; strings/dictionaries could be accepted as capabilities | Require a JSON list of strings and return a clear client error | Null, string, dictionary and mixed-type list regressions |
| Non-boolean readiness values such as `"false"` were accepted | Require boolean `true` before model/device/language checks | Four readiness-value regressions |
| Status-body reads were unbounded and the HTTP timeout only limited inactivity | Stream at most 128 KiB within a five-second total deadline | Oversized response and continuously trickling response regressions; cancellation closes the response |
| Malformed JSON or transport failures could expose internal exception details | Return concise readiness errors without upstream details | Malformed JSON/encoding, timeout and connection-failure regressions |

Twelve newly written regression cases failed before the fix, reproducing these
issues. Eighteen new tests now cover the fixes plus valid chunked responses,
authentication, response cleanup, no credential forwarding on redirects and no
automatic replay. The already reviewed stream-handshake validation remains in
place before microphone frames are consumed.

The second inspection checked the final code and package contents. No further
confirmed issue was found in the reviewed PMS authorization/profile-publication
changes, provider authentication/token handling, launcher controls or model-reuse
logic.

## Verification

| Check | Current result |
|---|---|
| Targeted audio/client/cloud regressions | 52 passed |
| Full desktop suite, including native English voice synthesis | 67 passed, no skips (24.89 s) |
| Launcher suite | 68 passed (11.83 s) |
| PMS LLM client/provider contract suite | 80 passed, no skips (2.11 s); provider traffic mocked |
| Desktop/API Ruff and format | Passed |
| API mypy | Passed for 55 source files |
| Desktop wheel and source archive | Built; packaged audio client matches final source; private runtime files excluded |
| API source and existing migrations | Hash comparison confirms unchanged since the preceding full API/database verification |

Private evidence: `.test_artifacts/final-correctness-review`.

The preceding [offline review](offline-models-final-review.md) retains the full
PostgreSQL result (263 passed, three opt-in skips), the three separately passing
native integration tests, 30 real ASR streams and actual CPU/GPU Qwen results.
Those expensive inference/database runs were not repeated for this client-only
fix; the affected desktop, launcher and provider checks above were rerun. No
application/model server or database was started or modified in this follow-up.

The prior limits remain: cloud calls were tested with mocks rather than live
accounts; optional QwenMedic/Whisper Medical/Vosk assets are incomplete; Hindi
voice output is text-only; natural clinical Hindi/Hinglish accuracy, physical
microphone/speaker behavior, Pi hardware and sustained-load acceptance remain
unverified. See the [online audit](online-enablement-final-review.md) for its
provider-specific evidence.
