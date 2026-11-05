# Patient Scenario Library: revised API implementation plan

Revision 2 | 2026-09-18 | Status: feature implementation, both reviews and audit verification follow-ups A-01/A-02 complete. Closure: 2026-09-19, 110 platform tests passed with no skips; see the audit report.

This revision replaces the previous phase order. It moves safe reads and the unsupported-runtime check before publication, fixes the request/retry contracts, and defines deliverables and completion gates for each phase. It uses the completed [migration 0008 database storage](../platform/db/scenario-library.md) and the existing [platform API](../platform/api/README.md). The wider [product plan](patient-scenario-implementation-plan.md) still governs subsequent UI and runtime work.

The [planned-versus-implemented audit](patient-scenario-api-audit.md) identified two verification gaps after initial delivery. Both are now closed by dedicated tests: overlapping retirement/lease/control requests and the complete kidney API lifecycle. The audit preserves the original observations and records their closure.

## Outcome and boundaries

Deliver the platform API and shared contracts for this workflow:

**Create or copy draft -> edit -> validate and preview -> approve and publish -> retrieve versions -> retire.**

The first implementation supports structured fictional patient identity, complaints, history, initial vitals, approved Hindi/English answers, disclosure rules, and instructor assessment content. Initial vital signs remain fixed per case version. Do not add generated clinical answers, automatic translation, dynamic physiology, or physical manikin effects.

Reuse the existing database, user roles, session authorization, audit infrastructure, and media services. No new database migration is expected. If a confirmed implementation gap requires one, add a reviewed forward migration; never modify migration 0008 or earlier history.

UI screens, laptop proxy expansion, Pi/laptop version-2 execution, the prepare/ready/start protocol, hardware verification, and live cloud services remain separate increments. API completion means authoring and managing version-2 cases; it does not mean the current version-1 manikin runtime can execute them. Existing version-1 interviews must remain usable.

## Decisions fixed for implementation

| Concern | Decision |
|---|---|
| Permissions | Organization administrators with existing `org.profiles.manage` author, preview, approve, and retire. No new educator role. |
| Other users | Operators retain scoped session control. Read-only users and trainees receive only permitted safe summaries/results. Trainees retain own-session restrictions. |
| Tenant boundaries | Every route checks authenticated identity, active membership/organization and applicable department. Platform administrators without tenant membership receive no implicit content access. |
| Library ownership | Organization-wide; no department-level draft sharing or per-case ACL system. |
| Draft storage | One draft per organization/code; 100 drafts including archived drafts. Existing 100 published-version capacity remains separate. |
| Content saves | Full replacement through PUT with positive `expected_revision`; no deep partial merge or silent overwrite. |
| Copying | Copy an immutable same-organization source version into an unapproved draft. Keep its document schema version; automatic conversion is deferred. |
| Schema changes | New blank cases default to schema version 2. Code and schema version cannot change through the edit API; create a separate draft for a different case/schema. |
| Publication | One operation validates, records educator approval, creates an immutable version, and writes audit in one transaction. |
| Runtime support | Supported execution versions remain `{1}` for this increment; version-2 admission/delivery is explicitly rejected. A device capability advertisement alone cannot enable it. |
| Scope of previews | Author-only, deterministic, and read-only. No LLM/TTS/provider calls. |
| Evidence | Tests in each phase, integrated verification, then two final reviews with fixes. |

## Phase API-1: shared contracts, permissions, and response boundaries

**Purpose:** make the data and access rules explicit before adding authoring operations.

### Implementation

1. Add separate version-2 draft and publishable-case models to the shared contract package. Preserve the current version-1 `Scenario` symbol, validation, serialization, and fingerprints used by the laptop; introduce explicit version-aware helpers for the platform.
2. Define the following version-2 groups without introducing a clinical ontology or general rules engine:

| Group | Content | Publication requirement |
|---|---|---|
| Catalog | Code, instructor title, learner-safe label, optional specialty | Stable code and both labels required |
| Patient | Fictional name, age, optional relevant sex/occupation, height/weight | Basic identity required; optional attributes may remain unspecified |
| Presentation | Main complaint, authored symptoms, onset/duration/severity when relevant | A clear presenting complaint required |
| History | Past conditions, operations, medications, allergies, family/social history | Medication/allergy knowledge must be explicit; unknown is valid, omission must not imply none |
| Initial vitals | Temperature, heart rate, pulse, blood pressure, respiration, SpO2, optional pain | Individual measurements optional; supplied values must be valid; absent means not configured |
| Dialogue | Greeting, clarification/unknown response, topics, approved bilingual answers, disclosure | English/Hindi spoken text and valid topic references required |
| Instructor | Objectives, notes, concealed diagnosis, manual rubric | Objectives and a usable rubric required; content remains private |

3. Keep values distinct from disclosure. A patient may know a fact but reveal it only when asked. Unknown/absent facts must not be populated automatically from a disease label.
4. Use canonical units: Celsius, kg, cm, beats/minute, mmHg, breaths/minute, percent, and an explicit pain scale. Validate types, finite numbers, technical bounds, unique IDs, references, and list/text sizes. Normal clinical ranges are not hard rejection limits; educator review decides clinical appropriateness.
5. Support approved fixed answers and small explicit allowlisted scalar fact substitutions only. No arbitrary JSON paths, expressions, code, external content retrieval, or freely generated answer mode. References must resolve to patient-accessible facts and render in the selected language.
6. Draft validation allows missing sections/translations, but rejects malformed supplied values and unknown fields. Publication validation requires completeness. Missing and invalid are different states.
7. Use the existing 48,000-byte canonical document budget, a bounded authoring request body (128 KiB maximum), and explicit handling of the database's 65,536-byte JSONB representation limit. Oversize requests/documents must fail without echoing input.
8. Normalize on save. Publication copies the exact saved JSON; validation must not silently add defaults or translate it after the author previews it.
9. Implement explicit draft, private published-case, safe summary, validation, and mutation response models. Do not expose ORM rows directly. Keep credentials, original request fingerprints, hidden answers, and sensitive input out of logs/errors/audit details.
10. Reuse authentication/access helpers. Authoring and publication require active organization-wide profile-management permission. Active state and authorization must be rechecked after lock waits. Maintenance mode permits authorized reads/validation while pausing authoring/publication mutations under the existing maintenance convention.

**Verification:** contract tests for incomplete versus publishable cases, Unicode, units/types, duplicate and private references, unsupported modes, strict positive revisions (reject null/bool), bounds, response projections, and unchanged version-1 serialization.

**Completion gate:** one partial draft and one complete bilingual fixture validate at the appropriate level; all unauthorized/private projections fail safely; existing version-1 contracts remain unchanged.

## Phase API-2: safe scenario reads and execution compatibility

**Depends on:** API-1. Implement this before enabling version-2 publication.

### Implementation

- Extend GET `/scenarios` and add GET `/scenarios/{scenario_id}`. Authors can read full approved/unapproved/retired case records in their organization. Other permitted readers receive only active approved safe views; unpublished/private detail is not exposed.
- Safe summaries contain an opaque scenario ID, label/title safe for the learner, published version, available languages, and execution support. Internal case codes, specialty tags, diagnoses, approval notes, and other private metadata are not assumed safe. Preserve authorized instructor detail via separate role-appropriate projections.
- Apply search/filter predicates only to fields the caller can see. Author filters may include internal code/title/specialty/status. Non-author search uses safe labels only; reject private-field filters rather than letting result counts reveal hidden content.
- Keep the existing `items` response envelope. Add `next_cursor` and bounded paging. For new draft lists, default limit 50/max 100; keep the legacy no-query scenario list's limit of 100 and schema-version-1 behavior. New library clients explicitly request `schema_version=all` or `2`.
- Order paged lists by immutable `created_at DESC, id DESC`; encode both in the cursor. Bind cursor validation to the organization/filter scope. This is live pagination, not a frozen snapshot; no offset paging or total-count service is required.
- Use a neutral learner label for old cases where no explicitly safe label exists, without changing stored content or hashes. Do not leak a diagnostic code alongside a neutral title.
- Add server checks for supported document versions before new session reservations and before device lease/control delivery. Return `scenario_runtime_unsupported` for version 2. `execution_supported` in a listing is explanatory metadata, not permission to bypass the check.
- Preserve legacy version-1 create/approve, feedback/rubric parsing, signed grants, expiry, and results. Keep legacy create/approve version-1-only so they cannot bypass the new publication workflow.
- Keep HTTP responses private/no-store. Do not expand the laptop proxy or change device capability/runtime code in this API phase.

**Verification:** every role/projection; hidden title/code/filter inference; cursor bounds/scope; retired/unapproved visibility; legacy listing and feedback; unchanged version-1 sessions; rejected version-2 admission without quota reservation or grant delivery.

**Completion gate:** safe reads work and the old runtime is protected before any new-format case can be published.

## Phase API-3: draft creation, copying, saving, and lifecycle

**Depends on:** API-1 and API-2.

### Endpoints

| Endpoint | Request and behavior |
|---|---|
| POST `/scenario-drafts` | `request_key`, target `code`, and either optional `schema_version`/`document` for a new draft or `source_scenario_id` for a copy; reject mixed create/copy inputs |
| GET `/scenario-drafts` | Author-only bounded summaries with search/archive filters; no full answer bank in list rows |
| GET `/scenario-drafts/{id}` | Author-only current document, revision, source, archive state, and permitted editing metadata |
| PUT `/scenario-drafts/{id}` | `expected_revision` plus complete replacement `document`; document code/version must match the saved draft |
| PATCH `/scenario-drafts/{id}` | `expected_revision` plus `is_archived`; cannot include document edits |

### Transaction behavior

- Create a minimal typed envelope when no initial document is supplied; do not fabricate patient facts. For copying, load the exact authorized immutable source, preserve schema/answer content, replace the target code, and record the source link. Existing target drafts cause a clear conflict.
- Compute the creation fingerprint from normalized original request semantics and authenticated author/organization. On retry, reconcile the same request key against that immutable fingerprint; return the existing draft with its current revision without resetting later edits.
- Check replay before enforcing a fresh-create capacity limit. A valid replay at full capacity still returns its existing result after current authorization is checked.
- Require compare-and-set on every PUT/PATCH. Set the expected revision; the database increments it. Return 409 on stale versions, including a retry of an already-applied save, rather than replaying the mutation.
- Archive and restore are separate revisioned changes. Archived drafts remain counted, cannot be edited/published, and have no DELETE endpoint.
- Derive actor fields on the server. Commit successful mutation plus a redacted audit event together. Denied/stale operations do not create success audits.
- After an unknown save/archive response, clients fetch current state and reconcile. No automatic overwrite or unbounded retry.

**Verification:** create/copy/reopen/save/restore flows; create replay after subsequent edits; conflicting keys/codes; two concurrent editors; archive rules; quota boundary; forbidden identity/source/schema changes; out-of-scope/inactive identities; audit rollback.

**Completion gate:** authors can safely maintain incomplete cases with no lost updates or duplicate drafts.

## Phase API-4: complete-case validation and patient preview

**Depends on:** API-3.

Endpoint: POST `/scenario-drafts/{id}/validate` with `expected_revision`.

### Implementation

- Read one saved revision and report the same revision in the response. Reject a stale requested revision. This operation does not lock the case against future edits, reserve capacity, approve it, or write an audit mutation.
- Return `publishable`, structured errors (`path`, `code`, safe message), review warnings, and a patient preview. Represent invalid or missing preview sections explicitly instead of inventing answers.
- Preview greeting, permitted topics/fact references, approved answers, and clarification behavior in English/Hindi. Resolve only supported deterministic references. Keep instructor notes, assessment keys, and concealed facts excluded.
- Keep preview author-only even though its projected content is patient-facing. It is an authoring aid, not a learner endpoint.
- Publishable means technically complete, not clinically verified. Warn about missing optional vitals where useful; never auto-approve content or promise detection of every free-text contradiction.
- Validation success becomes stale if the draft changes. Publication reruns validation and permission checks; do not introduce a signed preview token or a validation-cache subsystem.

**Verification:** missing translations, unknown facts, forbidden answer references, invalid units, incomplete preview, correct revision reporting, no writes/provider calls, and revalidation after a subsequent save.

**Completion gate:** authors can inspect exactly what the simulated patient may disclose and understand all technical publication blockers.

## Phase API-5: approved publication, replay handling, and retirement

**Depends on:** API-2 compatibility checks and API-4 validation.

Endpoints: POST `/scenario-drafts/{id}/publish`; reuse POST `/scenarios/{scenario_id}/retire`.

Publication request:

```json
{
  "request_key": "<uuid>",
  "expected_revision": 3,
  "approval": {
    "educator_name": "<reviewer display name>",
    "statement": "<substantive review statement>"
  }
}
```

### Transaction sequence

1. Authenticate and authorize; lock organization then draft; recheck current authorization/lifecycle after waits.
2. Reconcile the publication request key before considering the current draft revision or available capacity. Matching retries return the original version even if the draft was subsequently edited; they never reactivate a retired version.
3. Match replays against persisted source draft ID/revision, authenticated approver, and normalized approval fields. A different body/actor cannot reuse the same key, and a legacy scenario key cannot masquerade as a draft publication.
4. For a new publication, verify expected revision, unarchived state, full contract completeness, explicit educator statement, and capacity. A passed preview does not bypass these checks.
5. Allocate the next immutable case version under the organization lock. Copy the exact saved document; compute its canonical fingerprint and store approval/provenance.
6. Write the redacted publication audit and commit atomically. A failure rolls back the version and audit together.

The database permits only one publication per draft revision. A second request key for the same revision returns a conflict with the existing version ID only when the caller is authorized to read it. Repeated identical content under a later draft revision remains an explicit new reviewed version, not an automatic duplicate merge.

Retirement updates the selected immutable version's lifecycle only, preserves history, and maintains existing lease-renewal rejection. Repeated retirement returns its existing state without duplicate success audit. It cannot rewrite session history or remove media.

**Verification:** simultaneous publication, key replay after edit/archive/retirement, altered approval fields/actor, full quota, stale revision, duplicate revision under another key, exact document/hash copying, audit rollback, and retirement/lease races.

**Completion gate:** every approved version has a stable source and authenticated approval record, with no duplicate or partially committed publication.

## Phase API-6: integrated verification and API handover materials

**Depends on:** API-1 through API-5. Add focused tests during earlier phases, not only here.

### End-to-end cases

1. Create -> save incomplete draft -> validate errors -> finish content -> validate/preview -> publish -> fetch safe/private views -> edit next revision -> publish -> retire.
2. Copy a version-1 case and retain version-1 compatibility; create a version-2 case and verify it is manageable but blocked from the old runtime.
3. Execute the workflow with English/Hindi Unicode and two fictional development cases. Do not mark fixtures clinically approved automatically.
4. Exercise tenant/role/department boundaries, inactive membership/organization, device tokens, platform-admin isolation, private metadata in searches, and error/log redaction.
5. Exercise concurrent editors/publications, quota races, lost responses, rollback, archive/retirement, and existing signed-session/feedback paths.

### Checks and deliverables

- Real API calls through the test client and isolated PostgreSQL, including migrations and least-privilege roles; cloud calls mocked and not required by these endpoints.
- Required platform pytest, Ruff lint/format, and mypy checks; shared-contract and existing training regression tests because the shared package is imported by the laptop.
- Lock/build/package checks and documentation examples that use fake credentials and fictional content. No new UI is necessary to verify the API.
- OpenAPI request/response models, stable error codes, permission matrix, replay guidance, and reproducible workflow examples in the API README.
- Record actual passes/skips; do not reuse the database-only delivery's 55-test result as evidence for new endpoints. Actual hardware and latency remain outside this acceptance.

**Completion gate:** the whole authoring API and its failure cases pass with clear setup and client examples.

## Phase API-7: first final review and fixes

Review route permissions and lifecycle, schema/private response boundaries, hidden-field search inference, expected-revision handling, original-create and publication idempotency, lock order, quotas, audit atomicity, exact snapshot/hash preservation, backward compatibility, and unsupported-runtime admission. Inspect implementation and tests; a green test run alone is not the review.

Fix confirmed findings, add meaningful regression tests, and rerun affected checks. Record findings and fixes in [review evidence](pms-api-reviews.md).

**Completion gate:** confirmed blocking findings are fixed and remaining limitations are explicit.

## Phase API-8: second final review and delivery

Perform a fresh pass over the final implementation, including fixes, migrations if any, packaging, OpenAPI/README examples, old-client behavior, and TODO status. Verify that future UI/runtime features are not described as delivered. Do not call this an independent review unless a different reviewer performs it.

Finish final checks appropriate to actual changes. Deliver verification evidence, updated runbooks, and the remaining UI/runtime integration list. Stop at the API boundary; separate UI or device work requires the user's next instruction.

**Completion gate:** API/shared contracts are complete and locally verified, with both reviews documented and no outstanding blocking API defects.

## HTTP and client contracts

All endpoint paths above have prefix `/api/v1/organizations/{organization_id}/training`.

| Operation | Success contract |
|---|---|
| New draft creation | 201, `{draft, replayed: false}` |
| Equivalent create retry | 200, `{draft, replayed: true}`; draft contains current revision, not a fabricated original snapshot |
| GET/PUT/PATCH draft | 200, explicit draft response; PUT/PATCH return new revision |
| Validation | 200 with `draft_id`, `revision`, `publishable`, errors/warnings, and available preview; stale expected revision is 409 |
| New publication | 201, `{scenario, replayed: false}` |
| Equivalent publication retry | 200, `{scenario, replayed: true}`; original immutable version and current lifecycle |
| Lists | 200, `{items, next_cursor}`; existing `items` structure retained |
| Detail / retirement | 200, authorized explicit response; repeated retirement makes no new mutation |

Legacy version-1 endpoints retain their existing success/replay status conventions. New endpoint conventions above do not silently rewrite old clients.

Use the existing error envelope: 401 missing/invalid authentication; 403 denied role or private filter; 404 missing/out-of-scope resource; 409 revision/state/idempotency/unsupported-runtime conflict; 413 raw request too large; 422 invalid supplied content; existing 429 convention for capacity/rate limits; 503 for relevant maintenance/unavailable service conditions. Return stable codes and safe field locations without raw clinical text, SQL detail, tokens, or other-tenant identifiers.

## Implementation map and checkpoints

- Shared contracts: extend `shared/training-contracts/src/training_contracts` while preserving existing imports; use focused modules only when they improve clarity.
- API: extend training routes and use a focused scenario service/schema module where needed. Keep transaction logic out of response serializers. Do not refactor unrelated management/provider/media code.
- Tests: add authoring API and contract regressions; retain the reviewed database tests.
- Documentation: API README, this plan, [TODO](pms-api-todo.md), and review evidence.

| Checkpoint | Observable result |
|---|---|
| After API-2 | Safe catalog reads and version-2 execution rejection are in place |
| After API-3 | Drafts can be created, copied, reopened, edited, archived, and restored |
| After API-5 | The full authoring/validation/publication API workflow works |
| After API-8 | Tests and both reviews are complete; UI/runtime integration can be planned next |

## Completion checklist

- [x] API-1: compatible contracts, permissions, and safe response models.
- [x] API-2: safe reads, pagination/filtering, and early execution compatibility checks.
- [x] API-3: draft create/copy/read/save/archive/restore with revision and audit rules.
- [x] API-4: complete-case validation and deterministic patient preview.
- [x] API-5: atomic approved publication, replay/conflicts, and retirement.
- [x] API-6: full workflow/security/fault checks, packages, and client examples.
- [x] API-7: first review, confirmed fixes, and regression tests.
- [x] API-8: fresh final review, delivery documentation, and evidence.

## Verified API delivery (2026-09-18)

The implementation uses the existing migration 0008 without changing database history. Final platform suite: 105 passed, no skips; existing companion: 12 passed. Lint, formatting, mypy and consumer dependency locks passed. Both review passes reproduced and fixed their findings; detailed evidence is in [reviews](pms-api-reviews.md). See the [API runbook and client examples](../platform/api/deploy/scenario-library.md). Version-2 authoring/publication is complete; version-2 execution, UI, live cloud and hardware verification remain outside this delivery.
