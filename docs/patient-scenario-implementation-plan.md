# Patient Scenario Library: implementation plan

Date: 2026-09-18. Status: staged implementation. The database-only portion is tracked in [TODO](pms-api-todo.md) and [storage documentation](../platform/db/scenario-library.md); The database, platform authoring API and shared clinical contracts are complete under the revised API-only scope; UI and version-2 runtime phases remain pending.

This plan narrows the [feature baseline](patient-scenario-library.md) to a usable patient interview workflow. Extend the [existing pilot](patient-interview-pilot.md), [platform API](../platform/api/README.md), and [training companion](../device/training/README.md). Keep one Pi/manikin, one paired laptop, and one active interview per device as the delivery target.

Current API increment: [API-only implementation plan](patient-scenario-api-plan.md), including shared clinical contracts, authoring/publication endpoints, version-1 compatibility, and two reviews.

## Release outcome

An authorized instructor can create a fictional patient case, enter history and initial vitals, define approved Hindi/English answers, review and approve a version, load it onto the paired manikin, conduct an interview, and review recordings and manual feedback. The next session can use a different patient without carrying over the previous patient's context.

The release is for patient interviewing and history-taking. Vitals remain fixed during each session. Their configuration and display are software features; physical heating, palpable pulses, breathing motion, and examination hardware are not included. New natural response generation remains deferred: retain the existing model-assisted selection of approved answers.

## Existing foundation and gaps

Source inspection for this plan found:

| Existing foundation to reuse | Gap this plan addresses |
|---|---|
| Shared version-1 scenario contract with bilingual persona, greeting, clarification, answer topics, and rubric | Typed patient identity, symptoms, history, initial vitals, explicit disclosure rules, and learner-safe labels |
| Platform scenario creation/listing/approval/retirement and immutable version storage | Editable authoring drafts, protected detail views, practical search/filtering, and authoring UI |
| Session authorization, device binding, scenario hash, leases, quotas, stop, and manual feedback | Clear prepare/ready/start behavior and visible version/capability checks |
| Resident ASR/dialogue services, local TTS, Pi agent, and coordinator | Consume the extended scenario without changing approved facts or mixing patients |
| Separate audio/video APIs, private recordings, transcript review, and offline frame extraction | Display the assigned patient snapshot and response source alongside existing evidence |
| Minimal instructor page in the laptop companion | Forms and lifecycle controls; do not build a separate administration application for this increment |

Important storage constraint: current scenario documents are immutable even before approval. Do not make them mutable for an editor. Use a small separate draft store, then create immutable scenario versions through the existing publication/approval rules. Keep patient information inside the bounded scenario document; do not introduce a separate patient database or tables for every symptom/vital.

## Delivery boundaries

- Initial content: two small fictional adult interview fixtures, one cardiac complaint and one renal follow-up. They demonstrate reuse and remain development-only until educator approval. No large clinical catalog.
- Languages: approved English and Hindi content. Mixed-language input is a measured acceptance case; spoken output uses the selected session language. No automatic translation in this release.
- Library ownership remains organization-level under existing permissions. Device/session/media access continues to respect department scope. Do not add cross-organization sharing or a separate department library workflow.
- Server owns authoring, approval, versions, and authorization. Laptop owns local execution and review. Pi owns capture and playback. Existing media services remain standalone.
- Use the existing instructor UI and identity flow. A new identity provider deployment, full administration portal, and general device-fleet UI are separate work.
- Cloud architecture remains Pi -> platform API -> provider. Cloud conversation implementation, hosted deployment, and live provider verification remain outside this increment. Never silently fall back to cloud.

## Phase 1: structured scenario contract and compatibility

**Outcome:** one bounded definition of the patient that the API, editor, and runtime understand.

Work:

- Introduce an explicit new document schema version, distinct from the clinical scenario revision number. Continue reading version-1 documents and preserving their original hashes; never silently rewrite approved content.
- Define identity (fictional name, age, relevant sex information, occupation, height/weight, language), complaint/symptoms, history, medications/allergies, initial vitals, patient-known facts, approved answers, and instructor-only notes/objectives/rubric.
- Keep fields optional unless required for the particular case. Distinguish unknown, absent, and deliberately withheld information. Never fill missing clinical facts from the disease name.
- Use one canonical unit per measurement for the first editor: Celsius, kg, cm, beats/minute, mmHg, breaths/minute, and percent. Include pain scale and pulse description when relevant. Avoid unit-conversion UI initially.
- Reject invalid types, impossible encodings, non-finite values, excessive payloads, and invalid references. Do not reject clinically abnormal values merely because they are outside a normal range; clinical appropriateness belongs in educator review.
- Define an instructor title and a learner-safe label so catalog/session summaries do not reveal a concealed diagnosis. For legacy cases without such a label, use a neutral learner-facing description without rewriting the approved document/hash.
- Define only simple disclosure policies: volunteered in the approved greeting, answered when asked, unknown to the patient, or instructor-only. No conditional dialogue graph.
- Keep executable answer modes limited to fixed approved text and a small allowlisted field substitution where needed. Future generation is explicitly unsupported, not an enabled flag with no implementation.

Verification: meaningful contract tests for units, missing/unknown fields, duplicate references, bounds, private/public projections, and version-1 compatibility. Clinical review must still check contradictions in free text; validation cannot certify medical correctness.

**Exit:** a complete sample can be validated, patient/instructor views are defined, and old approved scenarios remain readable without changed fingerprints.

## Phase 2: drafts, version publication, and library API

Depends on phase 1.

**Outcome:** reliable authoring storage without weakening existing immutable cases or tenant boundaries.

Work:

- Add one bounded organization-scoped draft store through a forward Alembic migration. Store draft document, source revision when applicable, creator/editor, timestamps, and an optimistic concurrency version.
- Support create/save/read draft, copy an existing scenario into a draft, and publish an educator-approved immutable version. Reject stale edits rather than overwriting another instructor's work.
- Reuse existing scenario code/revision, approval statement, retirement, and idempotency behavior. Publication must lock/recheck the draft revision, allocate the case revision safely, and commit the version, approval, and audit together. An uncertain publication response must be reconciled using the same request identifier.
- Keep existing scenario/session records unchanged. Preserve existing approval routes for older clients while enforcing equivalent validation for the new document version.
- Add protected instructor detail reads and bounded list/search filters for title/code, specialty, and status. Expose learner-safe summaries only to learner-facing reads. Do not send hidden fields and rely on the browser to conceal them.
- Enforce draft and published-version quotas server-side, including concurrent requests. Respect the current published-version cap; saving a draft must not consume a new published version each time. No automatic deletion of history to free capacity.
- Update models, schemas, runtime grants, readiness, and database documentation together. Keep organization-level library permissions and department-scoped session restrictions consistent with the pilot.

Verification: dedicated disposable PostgreSQL upgrade tests preserving old scenarios and sessions; authorization, stale-save, simultaneous publication, quota, idempotency, and atomic-audit tests. Exercise least-privilege runtime roles and old API compatibility.

**Exit:** an authorized instructor can save, reopen, revise, approve, and retire cases through the API; unauthorized reads/writes and conflicting publications fail safely.

## Phase 3: practical authoring and library screens

Depends on phase 2.

**Outcome:** an instructor can build a case without editing JSON.

Work:

- Extend the existing companion instructor page with a library list and editor. Keep the platform API as the persistent source of truth.
- Provide simple form sections: identity; complaint/history; initial vitals; approved answers/disclosure; learning objectives/manual rubric. Display field errors next to the relevant input.
- Add search/filter, create, copy, save draft, reopen, preview, approve version, and retire actions. Copying is enough for templates in this release.
- Show save conflicts and unsaved changes clearly. Use explicit save first; no collaborative editor or autosave engine. Credentials remain in memory and are never stored with drafts.
- Provide patient-view versus instructor-view preview. Show missing required translations and unresolved facts before approval. Require an actual educator name/approval statement; do not automatically approve sample content.
- Extend the existing same-origin proxy only with explicit necessary routes, methods, and validated query parameters. Preserve organization binding and bounded request/response sizes.

Verification: browser workflow tests for save/reopen, copy, validation, concurrent-save conflict, preview, approval, retirement, safe text rendering, and authorization errors. Include Hindi Unicode. Test real controls, not just page load.

**Exit:** a permitted instructor can create and approve a complete sample through the UI, and an approved version cannot be edited in place.

## Phase 4: approved answers bound to the patient case

Depends on phases 1-2; use the editor from phase 3 for workflow verification.

**Outcome:** the existing conversation engine can run the structured case consistently.

Work:

- Keep the resident topic-selection model and existing ASR/TTS interfaces. Do not load models for each question or introduce another LLM call to compose answers.
- Build the model's topic catalog only from patient-accessible answer topics. Keep hidden diagnoses, assessment keys, and instructor notes out of dialogue requests.
- Render fixed answers or explicit allowlisted fact references deterministically. Never evaluate arbitrary templates/code or infer missing clinical values. Patient-reported information and measured vitals remain distinct.
- An unknown question selects an approved clarification/unknown response. Questions requesting hidden instructions or assessment answers must not expose instructor content. Record selected topic, answer source, clarification use, and latency in private session evidence.
- Reject unsupported schema/answer modes before recording starts. Maintain version-1 runtime behavior while adding the new schema.
- Clear all dialogue/follow-up state between sessions. Static initial vitals and approved history cannot be mutated by model output.

Verification: text-input tests covering English/Hindi topics, follow-up questions, unknowns, contradictory learner suggestions, instruction attacks, restricted fields, and switching between two cases. Test the actual topic selector separately from deterministic doubles; do not imply perfect classification from constrained output.

**Exit:** every spoken response originates from an approved answer or permitted fact rendering; unsupported questions do not invent a clinical response, and patient A's facts cannot appear in patient B's session.

## Phase 5: load, readiness, and explicit session start

Depends on phase 4.

**Outcome:** the instructor knows which patient is loaded and starts capture only when the system is ready.

Work:

- Present the paired manikin identity, selected approved revision, learner, language, and initial patient card. Keep the existing one-device pairing rather than adding fleet scheduling.
- Implement a bounded prepare/readiness step and an explicit Start action. Readiness covers the scenario hash/schema, microphone/camera/speaker availability, configured services, warmed model, selected language, storage allowance, and current authorization.
- Preserve the platform's authorized/active/terminal lifecycle: preparation occurs before active capture; mark active only through a valid start transition for the new workflow. Preparation status is not proof of capture or playback. Document old-client behavior and reject incompatible clients instead of silently bypassing readiness.
- Keep preparation subject to expiring authorization and existing quotas. Distinguish preparation timeout from interview duration, and do not let readiness extend a lease or revive a stopped session.
- Make preparation acknowledgments specific to the session, device, scenario version/hash, and runtime capability version. Recheck at Start so stale readiness cannot activate an edited, retired, revoked, or mismatched case.
- Disable new assignment while the device has an authorized/active session. Start, stop, and duplicate requests must preserve existing concurrency and idempotency guarantees.
- Show a specific actionable failure when readiness fails. No microphone recording during a speaker/setup check and no unannounced clinical fallback. Physical pulse/heat requirements remain unsupported.

Verification: failed warmup, missing camera, full storage, stale readiness, mismatched hash, expired/revoked authorization, duplicate Start, simultaneous assignments, and stop while preparing. Use hardware doubles locally and record what still requires the Pi.

**Exit:** only the confirmed case can start, capture begins after authorized Start, and a failed preparation leaves no apparently active interview or pending speech replay.

## Phase 6: conduct and debrief the interview

Depends on phase 5.

**Outcome:** the instructor can complete and assess the session using the same case that was loaded.

Work:

- Show session identity, scenario revision, language, readiness/active status, recording status, and a clearly labeled simulated vital-sign card for the instructor. Do not infer physical measurements or show an invented ECG waveform.
- Reuse Finish and Stop. Starting again creates a new session; no durable resume or ambiguous replay. Defer pause/resume until its effect on recording, authorization, and turn state is separately designed.
- Keep vitals fixed during the interview. To change the patient, prepare a new approved revision for a later session. Defer live state overrides, deterioration, and treatment effects.
- Reuse audio/video/transcript review, actual playback acknowledgments, bulk frame extraction, and manual rubric feedback. Add the pinned patient snapshot, response source, and clear missing/incomplete-media indicators.
- Keep instructor notes/rubric permissions separate from permitted learner feedback and recordings. Preserve retention limits; a case snapshot does not grant permanent media access.

Verification: complete a session, view the matching case revision and available media, save manual feedback with conflict handling, and check learner versus instructor access. Confirm expired/missing recordings are clearly reported and no live video analysis is introduced.

**Exit:** create -> approve -> load -> interview -> finish -> review -> feedback works as one workflow, including clear failure states.

## Phase 7: integrated validation and performance evidence

Depends on phase 6. Add focused tests in every preceding phase; this phase verifies the combined workflow.

**Outcome:** documented evidence of what works, what fails, and what remains external.

- Run both sample cases through the real local HTTP/WebSocket path, then switch patients on the same device fixture. Keep fixture playback explicitly simulated.
- Verify Wi-Fi loss behavior through fault injection, service unavailability, full/slow storage, restarts, cancelled turns, late results, and uncertain submission/playback outcomes. Retry only known-safe/idempotent operations within deadlines.
- Verify migration upgrades with retained version-1 scenarios/sessions, all API/runtime permissions, quotas under concurrency, and changed UI routes. Use only a dedicated disposable PostgreSQL server.
- Build a small reviewed evaluation set, initially 20 representative questions per case in each language, plus separate unknown/follow-up/instruction-attack examples. Record raw counts, wrong-topic versus clarification outcomes, and critical clinical-fact failures. This is a pilot diagnostic set, not proof of broad clinical accuracy.
- Separate text-input selection from full human-speech evaluation. Measure ASR errors, answer selection, first audible response, cold preparation, p50/p95 response latency, RAM/CPU, and recording completion under simultaneous audio/video. Report sample counts and hardware.
- Retain the existing proposed 2-3 second response target as an unproven goal. Do not mark it achieved from averages, cached responses, synthetic speech, or a 64 GB host. Set any formal release threshold before acceptance runs and report misses without silently relaxing it.
- Actual Pi/camera/microphone/speaker, Wi-Fi/acoustics, target 16 GB laptop, and clinical educator checks remain deferred until separately requested and available. Software checks can finish with those gates explicitly open; they cannot establish readiness for learner deployment.

**Exit:** software integration checks pass after confirmed findings are fixed; performance and clinical/hardware acceptance are reported separately with no fabricated pass status.

## Phase 8: first final review and fixes

Depends on phase 7's local verification.

Review the complete change for tenant/role boundaries, hidden-content exposure, immutable versions, atomic publication/audit, stale draft/readiness conflicts, schema compatibility, lifecycle and quota enforcement, media ownership/retention, and uncertain retries/playback. Review editor errors and contradictory authoring paths as well as the API.

Fix confirmed findings, add meaningful regression coverage, and rerun affected checks. Record findings and evidence in [reviews](pms-api-reviews.md). An automated test run alone is not this review.

**Exit:** confirmed blocking defects are fixed and remaining external limitations are explicit.

## Phase 9: second final review and delivery

Depends on phase 8 and its fixes.

Perform a fresh pass over the final changes, including the fixes, migrations, grants, old-client compatibility, complete authoring/session workflow, packaging, runbook, and TODO. Verify that no deferred feature is described as implemented. Do not call this an independent reviewer unless a different reviewer actually performs it.

Run the required platform checks from `platform/api`: `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`, and `uv run mypy src/pms_api`. Include the affected shared-contract/training suites and lint/type/package checks. Regress the audio/video integrations because the session path uses both; broaden service suites if shared behavior changes or integration failures justify it. Report skipped database tests explicitly.

Deliver updated runbooks, sample-case status, API/schema documentation, test evidence, observed performance, and a checked/unchecked acceptance list. After final checks pass, repeat only for new changes or unresolved concerns.

**Exit:** the software increment is reviewable and locally verified. Learner deployment still requires the explicit hardware, language/performance, identity, and educator acceptance gates that remain open.

## Deferred features

- Freely generated clinical answers, model fine-tuning, automatic case generation, and automatic translation.
- Changing vitals during a session, autonomous deterioration, treatment/drug-response simulation, and physiology engines.
- Physical heat, pulse, breathing motion, advanced voices, and specialized examination hardware.
- Live video detection, automated grading, emotion detection, large investigation/report libraries, and waveform monitors.
- Cross-organization case sharing, marketplace/course management, fleet scheduling, and a replacement administration UI.
- Cloud conversation rollout, hosted deployment, durable offline session resume, and a second raw TCP protocol.

## Completion checklist

- [x] Phases 1-2 (revised API scope): compatible shared structured cases, safe draft/publication storage and library APIs. Runtime consumption remains Phase 4.
- [ ] Phase 3: complete instructor authoring flow without JSON editing.
- [ ] Phase 4: bounded approved-answer execution and cross-session isolation.
- [ ] Phase 5: correct-case readiness and explicit authorized Start.
- [ ] Phase 6: complete interview/review/manual-feedback workflow.
- [ ] Phase 7: local integration and measured evaluation evidence.
- [ ] Phase 8: first final review, fixes, and regressions.
- [ ] Phase 9: fresh final review and consistent delivery documentation.
- [ ] External acceptance: actual Pi/Wi-Fi/16 GB laptop, representative human speech, deployed identity workflow, and educator approval.
