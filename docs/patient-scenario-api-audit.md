# Patient Scenario Library: planned versus implemented audit

Current status (2026-09-19): A-01/A-02 are closed; see the closure section at the end. The initial audit findings and package verification below remain a historical record.
Date: 2026-09-18. Baseline: [revised API plan, revision 2](patient-scenario-api-plan.md).

## Conclusion

The planned platform API feature set is implemented: draft creation/copying/editing, validation and patient preview, approved immutable publication, safe/private reads and retirement. Existing version-1 sessions remain supported; version-2 execution is deliberately blocked.

The audit found **two planned verification items without complete test evidence**: concurrent retirement versus lease renewal, and the complete authoring API workflow using the kidney example. These are coverage gaps, not confirmed functional defects. The earlier statement that all eight phases were complete needs this qualification: feature delivery and both reviews are complete, but full verification against every planned test item is still open.

This is a repository/evidence audit by the implementation agent. It is not an independent security assessment, clinical validation or hardware acceptance.

## Method and evidence

- Compared the revision-2 plan with the shared contracts, route/request/response implementations, runtime guards, tests, runbook, TODO and recorded review findings.
- Read the final test output: **105 platform tests passed, zero skips**, with two existing test-library deprecation warnings. This includes earlier database tests; it is not 105 additional scenario-library tests.
- The prior companion verification records **12 passing tests**. Lint/format, mypy, dependency-lock and build outcomes are recorded in the [review evidence](pms-api-reviews.md).
- Rechecked all four distribution hashes against the recorded package manifest and made 111 Python source comparisons across the wheel/source distributions and current workspace. All matched. Comparisons include duplicate files across distribution formats; this is not a count of 111 unique source files.
- No runtime tests were rerun for this audit. No application code, database, provider configuration or device configuration was changed.

Detailed prior artifacts: `.test_artifacts/patient-scenario-api/final-tests.txt`, `package-verification.json`, and the review before/after logs. The audit does not infer live deployment or measured latency from these local results.

## Phase-by-phase comparison

| Phase | Planned | Implemented evidence | Audit status |
|---|---|---|---|
| API-1 | Structured version-2 drafts/publishable cases, Hindi/English content, units, disclosure, limits, permissions and explicit projections; preserve version 1 | Shared `ScenarioDraftV2`/`PublishedScenarioV2`, publication validation, bounded typed groups, scalar-reference allowlist, strict revisions, author access and explicit response models | Implemented; relevant contract/security tests present |
| API-2 | Safe list/detail, private-field filtering, pagination, legacy behavior and early runtime compatibility gates | Role-dependent summaries/details, neutral legacy learner label, query-bound cursors, version-1 default listing; rejection before version-2 session admission and control/device grants | Implemented; relevant API/session tests present |
| API-3 | Create/copy/read/save/archive/restore drafts with revisions, request keys, quota and atomic audit | Five draft CRUD/lifecycle routes, server-derived actors, original-request fingerprint, compare-and-set writes, archive rules and serialized capacity | Implemented; lifecycle, replay, concurrency, quota and rollback tests present |
| API-4 | Read-only revision-specific publication validation and deterministic bilingual patient preview | `/validate` returns revision, publishability, safe issues/warnings and available preview; publication revalidates; no provider/model call in this path | Implemented; incomplete content, disclosure and translation checks present |
| API-5 | Atomic approval/publication, exact immutable snapshot, idempotency, retirement and retirement/lease race verification | Organization/draft locks, approval/provenance/hash, one version per draft revision, equivalent retries, quota and atomic audit; idempotent retirement | Features implemented; concurrent retirement/lease test evidence missing (A-01) |
| API-6 | Complete workflows, both fictional bilingual cases, security/fault/concurrency checks, OpenAPI/client examples and package checks | Full cough-example API lifecycle, version-1 copy/session compatibility, contract checks for cough and kidney examples, real PostgreSQL tests, documentation and checked packages | Substantially verified; kidney full API lifecycle evidence missing (A-02) |
| API-7 | First implementation review, fixes and regressions | Three input-handling findings reproduced and fixed; six regression cases plus contract checks passed | Review completed |
| API-8 | Fresh final review, fixes, final checks and accurate handover | Unsupported-format rubric/feedback handling fixed; final full suite and package verification recorded | Review completed; final acceptance remains qualified by A-01/A-02 |

Implementation references: [shared clinical contracts](../shared/training-contracts/src/training_contracts/scenarios.py), [library routes](../platform/api/src/pms_api/modules/scenarios.py), [request/response models](../platform/api/src/pms_api/modules/scenario_schemas.py), [session/legacy routes](../platform/api/src/pms_api/modules/training.py), [request bounds/error handling](../platform/api/src/pms_api/main.py).

## Functional coverage

| Requirement | Current behavior |
|---|---|
| Patient configuration | Fictional identity, complaint/symptoms, history, medications/allergies, optional static vitals and instructor assessment content |
| Language | Authored English/Hindi text; missing translations can be saved in a draft and block publication where required |
| Disclosure | Explicit volunteered/on-question/never policies; bounded scalar substitutions; no automatic clinical fact generation |
| Draft editing | Full-document PUT with expected revision; stale edits conflict; code/schema cannot change through editing |
| Versioning | Published content remains immutable and retains source draft/revision, authenticated approver and content fingerprint |
| Retries | Equivalent create returns current draft; equivalent publish returns original version; uncertain edits require GET/reconciliation |
| Authorization | Existing organization administrators author; other permitted users receive safe summaries; platform-admin/device identities have no implicit authoring access |
| Privacy | Private fields excluded from learner views and private filter/search behavior; unknown input names/invalid keys redacted in validation errors |
| Capacity | 100 drafts including archived drafts; separate 100 published-version limit including retired versions; concurrent quota tests present |
| Limits | 48,000-byte canonical document budget, independent PostgreSQL JSONB bound, 128 KiB authoring body cap or smaller global limit |
| Audit integrity | Business mutations and their redacted audit events commit or roll back together |
| Compatibility | Existing version-1 runtime contract retained; version-2 execution explicitly rejected rather than advertised as usable |
| Database delivery | Reuses migration `0008_scenario_drafts`; no new migration introduced by this API increment |

Endpoint contract and reproducible examples: [API runbook](../platform/api/deploy/scenario-library.md). The examples are development fixtures, not clinically approved cases.

## Open audit items

### A-01: retirement versus lease renewal concurrency evidence

**Priority:** medium verification follow-up. **Implementation defect:** not established by this audit.

API-5 explicitly planned retirement/lease race verification. Current tests exercise retirement, repeat retirement without extra success audit, and lease/control rejection after retirement. The test in `test_training_scope_and_revocation` retires first and requests the lease afterward; it does not overlap the two requests. Other concurrent tests cover editing, publication, quota and session admission.

**Closure:** add an isolated PostgreSQL test that coordinates concurrent retirement and lease/control requests. Assert the permitted outcomes under the documented short-lease semantics, rejection of subsequent renewals after retirement, and unchanged session/scenario history. Record the result and any resulting fix; sequential rejection alone does not close this item.

Evidence: [existing training tests](../platform/api/tests/test_training.py), [library lifecycle/concurrency tests](../platform/api/tests/test_scenario_library.py).

### A-02: kidney-example full API lifecycle evidence

**Priority:** low verification follow-up. **Implementation defect:** not established by this audit.

API-6 planned workflow execution with two fictional Hindi/English development cases. Both example files are packaged, and the contract test iterates over cough and kidney for normalization, validation and preview. API workflow helpers currently use the default cough example; a complete kidney-specific API workflow is not present.

**Closure:** exercise kidney draft creation, an edit, revision-specific validation/preview, publication, private/safe retrieval and retirement through the authenticated API on isolated PostgreSQL. Verify bilingual history survives the saved/published snapshot and private instructor content stays excluded from safe views.

Evidence: [contract tests](../platform/api/tests/test_scenario_contracts.py), [fixture loader](../platform/api/tests/scenario_samples.py), [API workflow tests](../platform/api/tests/test_scenario_library.py), [kidney example](../platform/api/scripts/scenario-examples/kidney_draft.json).

## Findings already fixed during implementation

| Finding | Resolution | Recorded verification |
|---|---|---|
| Non-string cursor IDs caused server errors | Validate cursor field types before parsing | Regression cases in final passing suite |
| Unknown field names/invalid dictionary keys could echo input | Redact those error locations and bound error details | Regression cases in final passing suite |
| Null characters reached PostgreSQL as storage failures | Reject unsupported document/approval text before SQL | Regression cases in final passing suite |
| Legacy rubric/feedback parsers assumed version-1 layout | Reject unsupported document versions before parsing | Imported version-2 session regression and version-1 tests pass |

These four findings were handled in the two recorded reviews. A-01/A-02 are additional audit coverage observations and must not be reported as fixes already completed.

## Broader product boundary

| Area | Status relative to this delivery |
|---|---|
| Database, shared contracts and platform authoring APIs | Delivered, subject to the verification follow-ups above |
| Instructor library/editor UI | Deferred in the revised API scope |
| Loading/executing version-2 cases on the laptop/manikin | Deferred; deliberately blocked by current platform gates |
| New prepare/ready/start protocol and extended session views | Deferred to later product phases |
| Generated clinical answers, automatic translation and dynamic physiology | Deferred |
| Physical temperature/pulse/breathing effects | Deferred hardware work |
| Live cloud/deployment integration | Not performed in this increment |
| Pi/Wi-Fi/microphone/camera/speaker, CPU latency and Hindi/English speech benchmarks | Not verified by this API delivery |
| Clinical educator acceptance | Still required; software validation does not establish clinical correctness |

Existing version-1 pilot and standalone audio/video services were not re-audited comprehensively here. Companion regression results establish only the tested compatibility paths. API-level completion must not be described as completion of the entire patient-manikin product.

## Audit disposition

Keep the implemented feature checklist, with A-01 and A-02 explicitly open in [TODO](pms-api-todo.md). Close these focused verification items before claiming complete coverage of every acceptance check in the revised API plan. The next functional product work remains UI and version-2 runtime integration, governed by the [broader implementation plan](patient-scenario-implementation-plan.md).


## Audit follow-up closure (2026-09-19)

A-01 and A-02 are closed by `platform/api/tests/test_scenario_audit_followup.py` and the full isolated PostgreSQL run: **110 passed, no skips** (`.test_artifacts/patient-scenario-api/audit-closure-tests.txt`). The earlier sections preserve the original audit observations.

- **A-01:** four coordinated overlapping request tests cover device lease and human control grant validation on both sides of retirement. Requests validated before retirement may finish issuing their existing bounded grant (at most 30 seconds); retirement does not retract an already validated in-flight grant. Requests validated after retirement and all subsequent renewals/control requests are rejected. Scenario content and session history remain intact. This verifies the existing short-lease contract, not instantaneous cancellation of issued grants.
- **A-02:** the kidney example completed authenticated create, edit, revision-specific validation/preview, publication, author and trainee retrieval, and retirement. Its Hindi/English history survives normalization/publication; private content stays excluded from the trainee projection. An initial test assertion was corrected to allow documented default-field normalization; no production defect was found.

These follow-ups add verification only. No platform production code, database migration, UI or version-2 runtime changed. API acceptance coverage is closed within the revised scope; broader product and hardware acceptance remains pending.
