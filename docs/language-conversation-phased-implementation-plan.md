# Conversation languages: detailed phased implementation plan

Date: 2026-09-24. Status: planned; this revision does not resume runtime implementation.

Architecture: [Pluggable conversation languages](language-conversation-architecture-plan.md).
This document expands that architecture into ordered work packages and exit gates.
Existing single-call changes are unfinished inputs to this work, not completed phases.

## Delivery scope

Deliver one extensible conversation engine and a qualified English experience across
typed input, local recognition, generation, speech output, and history. Support the
platform/cloud execution contract with mocked provider verification. Qualify Hindi
and later languages in separate deliveries using the same extension points.

Fixed decisions: explicit language, no Auto in patient conversations, one normal
answer-generation call, case facts retained, general questions allowed, unknown
personal facts not invented, and no silent change of language/provider. Language
packs do not contain provider credentials or tenant data.

The installation is in development. Use a coordinated implementation and forward
schema changes; there is no production rollout or backup prerequisite. Preserve
useful case/history data and unrelated workspace changes. Do not rewrite existing
migrations or the frozen SQL baseline.

## Phase order

| Phase | Main output | Depends on | Exit gate |
| --- | --- | --- | --- |
| 0 | Baseline, inventory, evaluation contracts | Existing workspace | Relevant changes and known failures accounted for |
| 1 | Language-pack and shared type contracts | 0 | English and synthetic second pack pass contract tests |
| 2 | Generic localized case data | 1 | Conversion preserves facts; missing/stale content fails clearly |
| 3 | Conversation lifecycle and persistence | 1, 2 | Scope, immutability, idempotency, races, retention verified |
| 4 | Shared one-call conversation engine | 1, 2, 3 | Grounding, prompt fitting, failure behavior and call counts verified |
| 5 | Desktop/platform integration and capability UI | 3, 4 | Both hosts use the same context and compiler |
| 6 | English recognition and speech output | 5 | Explicit-language speech, reset/cancellation and pronunciation verified |
| 7 | English quality and latency qualification | 4, 5, 6 | Live and held-out acceptance targets met or failures explicitly unresolved |
| 8 | Final review, fixes, development activation and documentation | 7 | Final checks and installation smoke pass; evidence recorded |
| 9 | Hindi and each later language | English accepted | New pack/content/model/speech qualification passes |

Implementation proceeds in this order. Each phase includes its own relevant tests
and review; testing is not postponed until phase 7. Phase 9 is outside the initial
English delivery. A phase remains open if its gate fails.

## Phase 0 - Account for current work and establish the baseline

### Work

1. Inventory existing patient-conversation edits, unfinished migration/tests, older
   routing helpers, language branches, and unrelated model UI changes. Retain useful
   work; replace or remove obsolete execution code only after consumer inspection.
2. Trace every consumer of case contracts: authoring, publication, practice setup,
   device training, local inference, platform inference, and historical rendering.
3. Record installed model/version, quantization, context size, GPU/CPU settings,
   recognizer, selected voice, and current configuration hashes. Never include keys.
4. Establish the current targeted test status. Record pre-existing failures
   separately; do not declare them resolved because an old assertion was removed.
5. Define fictional English evaluation fixtures with expected meaning and forbidden
   claims. Cover the retained negation, unknown-headache, irrelevant-family-history,
   greeting, abbreviation, and clinical-term failures without committing private logs.
6. Split tuning and held-out question families before further prompt tuning. Define
   answer-quality and timing report fields before measuring the replacement.

### Files and deliverables

- Inspect `shared/training-contracts`, `human-test`, `platform/api`, and the local
  audio receiver; account for pending `0023_patient_conversation` work without
  assuming it is applied or complete.
- Extend `local-models/qualification/evaluate_patient_conversation.py`; inventory the older
  benchmark scripts and native-local tests so they are updated or deliberately retired.
- Record the baseline and unfinished items in TODO/review evidence. Keep raw local
  artifacts in the ignored test-artifact directory.

### Exit gate

A reproducible test/evaluation entry point exists, expected behavior is explicit,
and the implementation file list excludes unrelated work. Earlier token/latency
experiments remain labelled preliminary, rather than being reused as final evidence.

## Phase 1 - Build language-pack contracts and registry

### Work

1. Add `LanguageTag`, `LanguagePack`, `PackRef`, `LocalizedText`,
   `ConversationContext`, `CapabilityResult`, and the small renderer/adapter protocols.
2. Implement a trusted bundled pack registry with immutable version/content hashes.
   Validate duplicate IDs, required resources, contract version, size bounds, and
   unknown pack references at startup. Package resources must work in installed wheels.
3. Implement the English pack: natural first-person speech, concise responses,
   terminology, unknown/clarification/boundary examples, script/direction, and
   pronunciation resources. General behavioral and disclosure rules stay in the engine.
4. Separate conversation language (`en`) from the selected speech locale (initially
   an available English locale such as `en-IN`). Register exact variants; reject
   unsupported tags rather than guessing from prefixes.
5. Implement the pure capability resolver. Inputs are the pack, case localization,
   model qualification, requested text/voice mode, and available speech resources.
   Output is readiness per operation and stable unavailable reasons.
6. Keep provider/model settings outside packs. No request-controlled imports, file
   paths, arbitrary templates, or executable plugin loading.

### Files and deliverables

Add `languages/contracts.py`, `registry.py`, `capabilities.py`, and `packs/en/`
under `shared/training-contracts/src/training_contracts/`. Add shared contract tests
and a test-only second pack. Declare the context interface here; persistence is phase 3.

### Exit gate

The same public interface loads English and the test pack without editing the core.
Malformed/unknown packs fail clearly. Tests cover region/script variants, missing
resources, operation-specific readiness, and conservative normalization that keeps
negatives, measurements, names, and the original transcript intact.

## Phase 2 - Make case content language-extensible

### Work

1. Introduce the version-3 authoring contract with one source language and bounded
   language-to-text maps. Preserve the existing structured clinical schema and its
   explicit unknown/none/present distinctions.
2. Give translatable history entries stable IDs. Reuse existing symptom/topic IDs
   and fixed fact paths. Preserve values, units, disclosure levels, and instructor data.
3. Store localization revision, canonical source hash, and review status per language.
   Hash source facts deterministically without including the hash field itself.
   Reordering keyed entries must not create new identities or lose translations.
4. Define source-edit invalidation. A changed fact or disclosure policy makes the
   affected localization unready until revalidated; a translation cannot self-approve
   through a posted `reviewed` flag. Reuse the existing authorized review workflow.
5. Convert current bilingual case documents deterministically. Preserve Hindi text
   but qualify English first. Supply a read adapter for historical formats and a
   tested adapter for any existing device runtime format still in use.
6. Replace patient-setup `_en`/`_hi` display fields with generic localized values in
   identity/category/case metadata. Keep one numerical/clinical source of truth.
7. Set consistent language-count, text, total-document, and selected-snapshot limits
   across Python contracts, request bounds, PostgreSQL, and quota calculations. Test
   six-to-eight-language documents; compile only the selected language into a prompt.
8. Build the disclosure-safe projection before localization. Fail unavailable case
   translations explicitly; never silently omit a fact or substitute another language.

### Files and deliverables

Update shared `scenarios.py`, contract readers/publishers, API scenario schemas and
practice setup, relevant identity/category serializers, database models, seed data,
and authoring controls that consume the changed fields. Add forward migrations,
grant/readiness updates, and matching database documentation.

Keep this within existing JSONB case storage; do not add a table per language or a
translation service. Choose new migration IDs from the actual chain at implementation
time. All reusable conversions must be deterministic and tested.

### Exit gate

Fresh installation and upgrades pass on disposable PostgreSQL. All nine seeded cases
retain their factual meaning and disclosures. Tests reject forged review status,
unknown tags, stale/missing translations, duplicate IDs, and oversized maps. Hidden
facts stay out of model projections in every tested language.

## Phase 3 - Implement isolated conversation lifecycle

### Work

1. Add a scoped `patient_conversations` record with the permitted selected-language
   case snapshot, language/pack/localization versions, practice revision, policy/compiler
   version, model/speech profile references, configuration hash, owner, scope, and expiry.
2. Keep immutable context separate from explicitly mutable runtime state: lifecycle,
   turn sequence, in-flight claim, and bounded recent accepted dialogue. For cloud
   execution, the server owns accepted history; it does not trust posted assistant replies.
   For local execution, the desktop owns runtime history and reports it as client-reported.
3. Add start/read/close operations under patient practice. Start takes the selection
   revision, explicit language, requested input/output modes, and an idempotency key.
   The server resolves all hashes, scope, and executable bindings itself.
4. Validate capability readiness before creating the conversation. Atomically store
   its context and audit event. Reject stale setup, wrong owner, disabled case,
   missing permission, or incompatible model/voice configuration.
5. Serialize cloud turns for one conversation using a bounded claim/lease and sequence.
   Never hold a database transaction open during inference. Commit accepted history,
   usage, and final turn state only under the valid claim; cancellation fences late results.
6. Preserve exact retry fingerprints. A repeated key with the same body returns the
   same result; changed content conflicts. An unknown external submission outcome is
   not automatically resubmitted. Known incurred usage is still accounted for if the
   answer is subsequently cancelled or discarded.
7. Close/recreate the conversation on explicit language, case, or incompatible profile
   change. Existing snapshots remain fixed after ordinary template edits; lifecycle
   revocation still blocks access. Pack updates apply to new conversations.
8. Enforce session count/storage bounds, expiration, tenant/department scope, runtime
   grants, and retention order. Optional archives must not keep expired contexts alive
   indefinitely or prevent cleanup through conflicting foreign keys.

### Proposed API contract

Names below are planned additions, not claims about existing routes:

| Operation | Proposed route suffix under `/organizations/{org}/patient-practice` | Purpose |
| --- | --- | --- |
| GET | `/capabilities` | Readiness for case revision, profile and requested modes |
| POST | `/conversations` | Validate selection and create fixed context idempotently |
| GET | `/conversations/{id}` | Read the caller's permitted context and lifecycle |
| POST | `/conversations/{id}/close` | Close/cancel the scoped conversation idempotently |

Existing completion and reporting operations reference `conversation_id`; they cannot
override its language, case, or pack. Stable error codes distinguish unavailable
language, stale translation/setup, context overflow, closed conversation, and a busy turn.

### Files and deliverables

Add the conversation service/contracts beside `modules/patient_practice.py`; update
`llm_schemas.py`, local event schemas, model mappings, migrations, grants, quota and
retention code, and configuration hashing.

### Exit gate

Isolated database tests cover another owner/tenant, department restrictions, access
revocation, stale start races, duplicate starts/turns, concurrent turns, late completion,
immutable context, expiration, and retention. Local outbox records can arrive out of
order and are deduplicated by stable identity; they do not invoke inference or authorize it.

## Phase 4 - Implement the shared one-call engine

### Work

1. Refactor the in-progress `patient_conversation.py` into case projection, prompt,
   context, and engine modules. Both hosts inject the selected pack and provider adapter.
2. Assemble the prompt in this order: shared behavior, selected pack guidance,
   complete permitted localized case, recent complete pairs, current question.
   Treat all authored content/history as data; user text cannot replace system rules.
3. Define factual precedence: explicit case facts govern personal claims; dialogue
   resolves follow-ups; general knowledge answers general questions but never fills
   missing patient facts. An earlier incorrect answer does not become case evidence.
4. Let the model answer factual questions, general questions, clarifications, and
   boundaries directly. Do not restore a question router, authored-answer selector,
   per-turn translator, or mandatory reviewer.
5. Use the actual model/tokenizer/chat template for prompt fitting. Drop only oldest
   completed pairs. If required case facts plus question and reserves do not fit,
   reject before generation with a capacity error. Never silently truncate case facts.
6. Start English with at most six recent pairs and a 256-token output allowance;
   actual context capacity takes precedence. Short natural answers need not use the cap.
7. Validate finish status and output shape. Reject empty, truncated, internal-analysis,
   malformed, or error payloads without a second model call. Do not use a clinical
   keyword blacklist or claim a format check proves factual correctness.
8. Return accepted text, provenance, actual calls, usage, timings, and history-pruning
   counts. Keep spoken rendering separate from displayed factual text where necessary.

### Files and deliverables

Add the `conversation/` modules to the shared package. Adapt API prompt budgeting and
quota accounting and local execution to their interfaces. Retain old routing helpers
only where historical evaluation/compatibility genuinely consumes them.

### Exit gate

Tests prove one call for each successful answer category, zero for preflight rejection,
and no retry after generation failure. Test exact-fit/overflow budgets, complete-pair
pruning, omitted hidden facts, malformed roles, prompt injection, explicit negatives,
unknown personal facts, and selected-pack inclusion. Local/cloud prompt parity uses
the same model/template assumptions and mock provider contract.

## Phase 5 - Wire desktop, platform, capabilities and history

### Work

1. Make the desktop language selector consume computed capabilities. Show English as
   the initial explicit supported conversation choice; remove Auto from this flow.
   Do not globally delete the catalog's retained Hindi data or unrelated media features.
2. Start the conversation from saved setup and keep the resulting context as the only
   authority for language, case, model profile, voice selection, and version provenance.
3. Wire local and platform generation to the shared engine. Preserve local model
   ownership and platform-only cloud credentials. Never route to cloud as a silent fallback.
4. Replace duplicated language branches in config/startup with registry/capability
   resolution. Validate actual installed local resources, not just a catalog entry.
5. Bind accepted history to the conversation. Include context/version references in
   metrics, optional archive records, outbox fingerprints, and history views.
6. Add a desktop generation counter for reset, stop, and profile/language changes.
   Late recognition, model, or speech work from an old counter is discarded.
7. Make archive/metrics failures nonblocking to an otherwise valid local answer.
   Retry archival independently; never retry inference or playback as a side effect.
8. Clarify local authorization lifecycle. Online execution rechecks current scope;
   any existing permitted offline mode stays bounded by its issued authorization and
   expiry. Immediate revocation cannot be guaranteed while disconnected, and adding
   languages must not expand that permission window. Do not add a new offline system.

### Files and deliverables

Update desktop `app.py`, `config.py`, `controller.py`, `local_turn.py`, history/outbox,
`scripts/model_startup.py`, and model capability startup metadata. Update API practice,
completion, configuration/model routing, local metrics/history, and affected setup UI.
Preserve the unrelated model-management UI changes already present in the workspace.

### Exit gate

End-to-end tests cover new/resumed/closed conversations, language/profile resets,
permission/config changes, history separation, missing resources, cancellation,
outbox restart/replay, and service unavailability. Both hosts report matching context
provenance. Optional archive failure does not create another generation.

## Phase 6 - Complete English recognition and speech output

### Work

1. Pass explicit English speech locale to recognition. Detected-language metadata
   stays diagnostic and cannot mutate the interview language.
2. Select a qualified available English voice using the pinned profile. Validate
   voice/locale compatibility before microphone capture; offer deliberate text-only
   operation when voice output is unavailable.
3. Apply conservative English pronunciation resources for numbers, units, common
   abbreviations, and medical terms. Preserve names and factual values. Treat voice
   persona preference separately from language compatibility.
4. Buffer a short accepted complete answer before playback. Clear queued audio on
   cancel/reset; an answer from a closed conversation cannot start speaking later.
5. Instrument end-of-speech detection, final transcript, generation start/first token/
   accepted answer, synthesis start, and actual first playback separately.
6. Check quiet/noisy recordings, accents represented in the test set, pauses,
   abbreviations, negation, decimals/units, silence, interrupted speech, and feedback
   from the speaker. An uncertain transcript must not be silently rewritten into facts.

### Files and deliverables

Update desktop speech/controller/capture integration, voice metadata where required,
and `device/audio-process` session/config/engine adapters that receive language.
Update platform speech request validation for patient-conversation context.

### Exit gate

Recorded-audio integration checks and local microphone/speaker trials verify English
selection, intelligible output, negative/number preservation, cancellation, queue
isolation, and readiness errors. Report unavailable hardware trials explicitly; typed
model tests and a synthesized audio file alone are not live speaker verification.

## Phase 7 - Qualify English quality and latency

### Live answer acceptance: 45 turns

Use one case in each of Cardiology, Nephrology, and Respiratory, with 15 questions
per case. Exact wording and expected facts depend on the case; never force an unknown
answer where that case explicitly supplies one.

| Slots per case | Coverage |
| --- | --- |
| 1-2 | Greeting and patient identity |
| 3-5 | Main complaint, duration follow-up, associated detail |
| 6-7 | Explicit negative and an unrecorded symptom |
| 8-9 | Medication and whether it helped, using only available evidence |
| 10-11 | Same-problem family history and another saved personal detail |
| 12 | Ambiguous abbreviation or referent requiring clarification |
| 13-14 | Generic knowledge and simple reasoning/arithmetic |
| 15 | Legitimate clinical question containing potentially sensitive terminology |

Retain conversation continuity for designated follow-ups; isolate unrelated fixtures
so earlier questions do not accidentally give away their expected answers.

### Broader acceptance

- Run at least 216 English turns across all nine seeded cases. Include held-out
  paraphrase families, boundary requests, disease names, topic switches, compound
  questions, missing facts, disclosure attempts, and long-history behavior.
- Keep a fixed held-out subset. If failures from it drive prompt edits, mark those
  fixtures as exposed and use a fresh held-out subset for the final report.
- Use deterministic assertions for counts/bounds/known values and human semantic
  review for relevance, unsupported claims, and naturalness. An LLM judge may assist
  later; it is not the only acceptance authority.
- Run every acceptance fixture once for correctness and repeat the 45 live questions
  in three controlled warm-model passes for latency/variability. Report repetitions
  separately from unique question coverage. Report cold starts separately.
- Include at least 15 recorded English inputs covering the three categories and a
  live microphone/speaker sequence. Do not mix prerecorded timings with live capture
  timings when calculating end-of-speech-to-playback latency.

### Targets and report

| Measure | Acceptance target |
| --- | --- |
| Successful answer-generation calls | Exactly one per turn |
| Critical unsupported patient facts / negative reversals / hidden disclosure | Zero in the acceptance set |
| Overall acceptable answers | At least 95%; also report per-category results |
| Naturalness | At least 95% rated 4 or 5 on the five-point rubric below |
| Warm accepted text, p95 | At most 2 seconds after typed/final-transcript submission |
| Live first audible response, p95 | At most 3.5 seconds after actual end of speech |
| Language/core isolation | All contract, scope, reset, and history tests pass |

Naturalness rubric: 1 = unusable; 2 = conspicuously awkward or repetitive;
3 = understandable but clearly stilted; 4 = natural with minor awkwardness;
5 = natural and direct. Overall acceptable also requires correct factual meaning,
relevance, selected language, appropriate disclosure/boundary behavior, and no
unsupported personal claim. Boundary responses are scored against appropriate
brevity rather than friendliness.

These are qualification targets, not guarantees for unseen questions or different
hardware/cloud providers. Include failures and incomplete turns in totals; do not
improve latency by excluding slow errors. Report success rate and failure timings
beside the latency distribution, with the percentile calculation and sample size.

For every turn record case/version, question/expected meaning for fictional fixtures,
actual answer, scores, pack/policy/compiler/model versions, full compiled-prompt hash,
input/output tokens, call count, finish status, context pruning, and available timing
stages. The prompt hash must cover all instructions, case, history, and current input,
not just a shared rules constant. Keep private prompts/audio out of general logs.

### Failure loop and exit gate

Classify a failure as content, transcription, prompt, model capability, integration,
or speech output; fix its cause and rerun affected regressions. If the small model
cannot pass at the required latency, compare a better qualified local configuration
or an explicitly configured cloud model rather than silently adding repair calls.

No stage is marked passed if critical factual or isolation failures remain. Live
cloud calls, hosted deployment, and Pi verification require their own requested
scope and evidence; mocked adapter parity does not certify them.

## Phase 8 - Final review, fixes and development activation

### Work

1. Review authorization/scope, hidden facts, translation invalidation, session races,
   provider retry uncertainty, cancellation charging, retention, and resource bounds.
2. Review extensibility using the synthetic second pack and six-to-eight-language
   case documents. Verify no `if language == ...` implementation has leaked into
   shared orchestration, and that adding translations does not enlarge English prompts.
3. Run relevant shared/desktop/audio tests and the API checks below. Recheck affected
   checks after fixes and perform a final review of the resulting diff.
4. Apply the reviewed development migrations and grants to the intended local install,
   update pinned packages/settings, and run a short English conversation smoke test.
   Do not use the application database for destructive integration tests.
5. Update setup instructions, API/database field documentation, examples, TODO and
   review evidence. Document how to add a pack, approve content, qualify a model/voice,
   diagnose unavailable capabilities, and inspect measured costs/timing.
6. Summarize actual passing checks, remaining limitations, and any skipped hardware/
   cloud coverage. Keep commit/publishing work separate from plan-only changes.

Required API checks from `platform/api`:

```text
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src/pms_api
```

Set `PMS_TEST_ADMIN_DSN` only to the verified disposable PostgreSQL test server.
Database tests skipped for lack of that server cannot count as a passed schema gate.

### Exit gate

English runs through the actual local installation with explicit selection, correct
case grounding, generic responses, one-call accounting, consistent speech/history,
and recorded acceptance evidence. Documentation matches installed behavior. All
confirmed review findings are fixed or explicitly listed as unresolved blockers.

## Phase 9 - Add Hindi, then another language at a time

For each additional language:

1. Add the pack/resources and declare script, register, grammar, examples, and locales.
2. Add/review case and identity translations against the canonical source revision.
3. Qualify the chosen LLM for that pack and language, including context/token budget.
4. Bind/test recognition and synthesis if voice input/output is offered. A new
   provider needs an adapter only if existing interfaces cannot execute it.
5. Run that language's factual, generic, sensitive-clinical, boundary, follow-up,
   pronunciation, and latency suite. Use a fluent reviewer for linguistic quality.
6. Confirm isolation from English and enable only capabilities that passed.

Deliverable: a pack, reviewed content, qualified execution profiles, and measured
evidence. No new conversation engine, language-specific SQL columns, automatic
translator, or additional normal generation call should be necessary.

## Cost and completion rules across phases

- Normal successful answer: one generation; invalid preflight: zero. Recognition,
  synthesis, token counting, setup, and archival are separate operations with their
  own usage and timing, not additional answer generations.
- Only selected-language text enters the prompt. Preliminary English planning range:
  about 1,200-1,800 input tokens for short cases with bounded history; actual fitting
  and measurements govern. With a 2,048 context, 256 output reserve and 128 safety
  reserve, at most 1,664 input tokens fit. Larger prompts need fewer history pairs
  or a qualified larger context; required case facts are never trimmed away.
- A prompt/resource change invalidates relevant qualification evidence through its
  content hash. Synthetic packs prove modularity, not linguistic support for a real
  second language.
- English completion means phases 0-8 have passed. Hindi readiness, cloud live
  certification, and Pi performance are separate claims.
- This document is the requested phase plan. No runtime phase is marked completed
  by creating it, and no new implementation approval is inferred from the request
  to expand the plan.
