# Patient background implementation TODO

Scope: local-first scenario background and compact conversation support.
Plan: [implementation plan](patient-background-conversation-plan.md).
Existing result/sync fixes in this workspace are preserved.

- [x] Follow-up review 1: fix rejected device admission and completed-history selection.
- [x] Follow-up review 2: fix snapshot quota/recovery accounting and activation retry race.
- [x] Follow-up review verification: finish full suites and record final evidence.

Follow-up evidence: [two-pass review](patient-background-two-pass-review-20261006.md).
Follow-up checks: desktop full run 537 passed / 6 skipped; final affected desktop
checks 28 passed; device full run 36 passed; API full run 442 passed / 388 database
skips. Lint, changed-file formatting and types passed. Final startup/quota changes
and the added camera regression were verified by the affected desktop rerun.

Requested native local-model qualification:

- [x] Freeze 25 questions covering known facts, absent personal/clinical facts,
  ordinary general knowledge, mixed questions, greetings, ambiguity and injection.
- [x] Measure the current prompt on installed Qwen3.5-4B at exactly 2,048 tokens.
- [x] Fix confirmed native answer-quality or latency failures and rerun the matrix.
- [x] Repeat with a two-pair conversation history and inspect every answer.
- [x] Record final native speed, question/answer evidence, regressions and limits.

Final compiler-34 native qualification: four sets of 25 questions, two rounds
each, 200 completed answers and no protocol or reviewed factual failures. All
200 used one generation and fit the 2,048-token context. Full-GPU model-only
warm median 2.12 s, p95 5.00 s across 192 samples; each set met the working target.
Existing shared-GPU application settings were preserved. Earlier 16-layer runs
did not consistently meet the timing target; audio/shared-load timing remains
separate qualification work below.

Final checks: API 546 passed / 388 database skips; desktop 538 passed / 6 skips
with one sandbox Tcl/Tk failure, then 44 affected tests passed with runtime
access, including that native widget test. Device 36 passed. Final affected
API/shared checks passed 144 / 2 skips, then 136 conversation/durability checks
passed after annotation fixes; the final directory flag check passed 2 tests.
Required lint/types and formatting passed, along with explicit typing for the
10 changed shared conversation/durability modules. The additional whole-shared
type check retains 26 schema/registry issues reproduced in the committed
baseline, outside this native-answer change. Review evidence records details.

Working speed target on this laptop: warm complete-answer median <=3 seconds,
p95 <=6 seconds, one generation per question. This is a qualification target,
not a hardware-independent promise. Clinical correctness and grounded personal
answers remain required even when a fast guess would be easier.
See [native qualification evidence](patient-background-local-qualification-20261006.md).

- [x] Phase 1: versioned background contracts, localized bounded choices and tests.
- [x] Phase 1: deterministic compact session background and native context fitting.
- [x] Phase 2: forward PostgreSQL migration and compatible API/runtime projections.
- [x] Phase 2: scenario editor tab, language review and publication integration.
- [x] Phase 3: compact prompt/language policy and once-per-conversation snapshot.
- [x] Phase 3: local/cloud/device compatibility, short history and tokenizer caches.
- [x] Phase 4: starter restoration draft tooling and regression matrix.
- [x] Phase 4: isolated database lifecycle/migration/security checks.
- [x] Phase 4: full relevant suites, lint/types/UI build and final review.
- [x] Phase 4: local native inference measurements where available; report limits.

Hosted deployment, live cloud calls and Raspberry Pi verification are outside
this implementation request. Final evidence distinguishes real local model
measurements from mocks and unavailable checks.

Verification so far: full desktop 532 passed / 6 skipped, full API 441 passed /
388 skipped without a test DSN, isolated background/schema/desktop checks 15
passed, refreshed case-to-device workflow 2 passed, full device 34 passed, and
focused UI tests/types/build passed. Latest desktop sync/cache checks: 23 passed.
Final affected API/shared checks: 60 passed / 5 database skips. Background permission
hash check: 10 passed / 2 database skips. Final desktop sync/cache checks: 24 passed.
See [review evidence](patient-background-review-20261006.md) for exact runs and limits.

Final native Qwen sample: 18 warm answers per policy, 33% fewer prompt tokens,
median 2.75 s to 1.95 s and p95 6.31 s to 5.09 s. The proposed timing gate passed
in this sample; earlier larger samples varied. Approved meal choices stayed stable
through three real replies and history removal.

Broader-suite limitations: seven old optional-history database fixtures call a
removed connection endpoint. Device whole-tree formatting reports the existing
`tests/test_coordinator.py`; changed device files pass formatting.

Separate rollout/qualification work:

- [ ] Hosted rollout when requested: migrate 0046, reapply grants, update companions.
- [ ] Review/publish restored or newly authored background; do not autoapprove seeds.
- [ ] Qualify other models/languages, near-limit cases, explicit clarification quality
  and sustained playback/capture latency on target hardware.
- [ ] Qualify sustained answer tails with the shared 16-layer Whisper/TTS policy;
  the passing full-GPU text run does not qualify the combined audio pipeline.
- [ ] Separate existing shared schema/registry type debt: 26 baseline issues.
