# Patient background: two review passes, 2026-10-06

Review scope: the current uncommitted background implementation, its local
conversation paths and result/snapshot durability. Existing sync work is preserved.

## Pass 1: lifecycle and conversation compatibility

- Fixed session admission before prompt preparation: a stale or unavailable
  translation previously left the device coordinator in `warming` without a
  warmup task or durable record. Preparation now precedes state mutation; an
  unavailable translation returns 422. Regression checks repeated rejection and
  successful start after correction.
- Fixed the two-pair history window: unfinished/failed playback previously
  consumed slots before filtering. It now selects the last two completed pairs
  in order, excluding answers the learner never heard.
- Inspected background editing, localization hashes, version-4 compatibility,
  immutable choice compilation and the forward migration. No additional
  confirmed defect found in those paths during this pass.

Verification: clinical-runtime suite 14 passed; device Ruff and mypy (11 source
files) passed. Initial broader run: 35 passed and one new-test failure caused by
using an unavailable Hindi language pack; corrected the fixture to English and
reran the affected suite successfully.

## Pass 2: storage bounds and retries

- Fixed missing snapshot quota accounting. Retained snapshots and pending media
  now share the configured byte limit. The local journal adds an incremental
  `context_size` column without replacing old records; startup accounts for old
  final/partial snapshots. New writes reserve capacity durably before creating
  partial files; retries reuse that reservation. Camera recovery includes the
  same retained snapshot bytes and preserves originals when capacity is exhausted.
- Fixed an activation race: a disk failure could clear `current` before the caller
  assigned it again, suppressing a later begin retry. Activation now records the
  identity before admission and preserves the worker's failure reset.
- Regression coverage includes immediate disk failure, retained acknowledged
  snapshot quotas, retry after capacity change, replacement failure and reservation
  reuse, old-journal upgrade and restart, and camera recovery under a shared quota.

No new generation calls or foreground filesystem work were added. Quota queries
run on the disk worker; startup reconciliation is bounded by the retained-session
limit. This is an architectural check, not a new hardware latency measurement.

Final verification:

| Check | Result |
| --- | --- |
| Desktop full suite | 537 passed, 6 skipped, 211.56 seconds |
| Final desktop background/sync rerun | 28 passed, 46.51 seconds |
| Device full suite | 36 passed |
| API full suite | 442 passed, 388 database-dependent skips |
| API background/desktop compatibility | 10 passed, 6 database-dependent skips |
| Desktop/device/API Ruff | Passed |
| Changed desktop/device formatting; full API formatting | Passed |
| Desktop/device/API mypy | Passed: 29 / 11 / 85 source files |
| Git whitespace check | Passed with repository CRLF setting |

The full desktop run started before the last startup/quota adjustment and camera
regression were added; the final 28-test rerun verifies those final changes.
Desktop skips include opt-in native-model and installed-voice checks. No disposable PostgreSQL DSN
was configured in this follow-up; database checks were explicitly skipped, not
presented as passing. Prior isolated PostgreSQL evidence is recorded separately
in the original implementation review. API/device suites reported dependency
deprecation warnings without failures. The pre-existing device whole-tree
formatting limitation remains; changed device files pass formatting.

The compact model prompt and generation defaults were unchanged by these fixes.
Prior native measurements remain evidence for that prompt, not a benchmark of
these storage corrections. No live cloud, hosted deployment, or Raspberry Pi
hardware checks were performed. No additional confirmed findings remain from
these two passes; broader model semantics and rollout limits remain as recorded
in the implementation TODO.
