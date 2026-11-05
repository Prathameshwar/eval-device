# Patient background implementation review — 2026-10-06

Implemented the local-first plan in the workspace. No application database,
hosted deployment, live cloud provider, commit or GitHub publication was changed.
Earlier result/recording sync fixes were preserved.

## Delivered phases

1. Schema version 5 adds five bounded localized background areas, explicit
   author-approved choices and deterministic selection by conversation identity.
   Version 4 remains supported. Background text, choice permissions and choices
   participate in language review hashes; edits cannot reuse approval silently.
2. Forward migration `0046_patient_background` validates all five document-storage
   surfaces without rewriting existing cases. API grants/readiness, draft save,
   review, publication, copy, practice and runtime projections support both versions.
   Refreshing a clinical-only source preserves background authored in a version 5
   draft; refreshing from a version 5 source permits the compatible upgrade.
3. The scenario editor has a Patient background tab, localized choice editing and
   review previews. Published cases remain read-only. A conversation compiles its
   selected language and background once into an immutable private snapshot.
4. Local inference uses one plain-text generation, default 128 output tokens,
   two recent dialogue pairs and exact native template/tokenizer fitting with a
   128-token margin. Required clinical facts and the question are never truncated.
   Bounded, model-scoped metadata/token caches expire after 30 seconds and clear on
   native errors. Failed/uncertain generations are not automatically resubmitted.
5. Desktop sync saves the fixed context/snapshot on its background writer before
   the completed turn's durable receipt. Snapshot queue rejection can retry;
   mutable session status is excluded; conflicting snapshots and unsafe links
   are rejected. File flush/publication and retention follow the existing journal.
   The device coordinator prepares and saves its session snapshot before warmup
   and uses the same native fitter. Restart recovery does not automatically resume
   a GUI/device interview or bypass current authorization.
6. Starter restoration tooling exports two unreviewed drafts from the frozen
   source, including Alex's explicit yesterday-meal fact. It does not overwrite
   tenant content or publish/approve anything. A 20-question background matrix and
   11 additional clinical/general probes accompany a reproducible local benchmark.

## Verification

| Check | Actual result |
| --- | --- |
| Full desktop suite | 532 passed, 6 optional native/runtime checks skipped |
| Full API suite without test DSN | 441 passed, 388 database-dependent checks skipped |
| Isolated background/schema/desktop checks | 15 passed |
| Refreshed case-to-device workflow, versions 4/5 | 2 passed after updating the new version-5 expectation |
| Earlier isolated background/clinical/archive/desktop run | 27 passed; 7 obsolete history-fixture setup errors |
| Final affected API/shared prompt checks | 60 passed, 5 database-dependent skips |
| Final background permission-hash regression | 10 passed, 2 database-dependent skips |
| Final desktop sync/cache regressions | 24 passed; final snapshot-path check rerun: 5 passed |
| Full device suite | 34 passed; final clinical runtime rerun: 12 passed |
| UI background/scenario component regressions | 8 passed |
| UI TypeScript and production build | Passed; existing TenantProvisionWizard CSS warning |
| API/desktop Ruff, formatting and mypy | Passed |
| Shared contract Ruff/formatting | Passed |
| Device Ruff/mypy and changed-file formatting | Passed |

Database tests used only the dedicated disposable PostgreSQL server on loopback
port 55447. The upgrade test compared existing version 4 documents and revisions
before/after 0046, accepted version 5, rejected malformed/oversized background and
checked PUBLIC execution was revoked. Workflow tests exercised independent review,
tenant denial, copying, idempotent lost-start-response recovery, model reassignment
and local/cloud client compatibility without submitting cloud inference. The
disposable server was stopped after testing.

Seven older optional-history fixtures still POST a removed connection endpoint and
fail with 404 before business assertions. The device whole-tree formatting check
also finds the pre-existing `tests/test_coordinator.py`; it was preserved. These
are broader-suite limitations, not passing verification.

## Actual native model evidence

The installed Qwen3.5-4B ran on its existing CUDA runtime with 16 GPU layers,
2,048 context tokens and thinking disabled. The benchmark started its own server
on port 17887 and stopped it afterward. Both policies received the same authored
background and a 128-token output allowance; no PMS/cloud calls occurred.

Final reduced-prompt run, counterbalanced baseline/compact/compact/baseline:

| Measurement | Baseline policy | Final compact policy |
| --- | ---: | ---: |
| Warm samples | 18 | 18 |
| Average prompt tokens | 1,241.1 | 831.1 |
| Complete-answer median | 2,751.2 ms | 1,952.7 ms |
| Complete-answer p95 | 6,311.9 ms | 5,091.6 ms |
| Average native fitting time | 35.3 ms | 43.3 ms |

Prompt size fell 33%; median answer time fell 29%; p95 fell 19%. This final
sample meets the proposed no-more-than-10% p95 regression target. Fitting was about
8 ms slower in this sample; it remained small relative to inference. All measured
turns used one generation. Earlier prompt revisions had inconsistent tail latency,
including a quiet 36-sample comparison with p95 8,057 ms baseline versus 10,363 ms
compact. These results prompted further rule reduction; the final smaller sample
is useful evidence, not a guarantee for other loads, models or hardware.

The final 31-probe pass answered the supplied meal/sleep/work facts, general Paris
question and supported sleep portion of a mixed question. Unrecorded prior medicine,
ringing ears, antibiotics, travel and pets remained uncertain. The approved meal
choice remained rice/vegetables in three real replies before/after history removal.
Clinical facts and numbers were retained in the tested identity/onset/rest probes.

Limits remain model-specific: unsupported background still produces uncertainty;
ambiguous questions may get an uncertainty reply instead of an explicit clarification
question. A plain-text guard does not prove semantic grounding for all questions.
No Hindi semantic certification, full near-limit/native history stress, microphone/
playback latency, power-loss guarantee, Raspberry Pi verification or live cloud
qualification is claimed. Wider qualification remains in TODO.

Final artifacts are under `.test_artifacts/patient-background-reduced-final/`:
`native-results-final.json`, `native-quality.json` and `native-variation.json`.
The earlier 36-sample evidence is under `patient-background-quiet-final/`.
The benchmark and authoring instructions are in
[the simulation guide](simulations/patient-background/README.md).

## Rollout

Apply migration 0046 and the matching runtime grants before upgrading API/UI/
companions. Existing cases remain version 4 unless authored or explicitly restored
and reviewed as version 5. Publish the approved replacement and select it in Practice
to enable its background; the feature does not retroactively invent missing facts.
The existing startup/migration tooling provides the forward upgrade path. Hosted
rollout and additional model/hardware qualification remain separate work.
