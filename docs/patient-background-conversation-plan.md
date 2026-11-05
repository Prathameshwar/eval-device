# Patient background and flexible conversation plan

Status: implemented in the workspace, 2026-10-06; final measurements tracked in
[TODO](patient-background-todo.md) and review evidence. Hosted deployment and live
provider integration remain deferred.

Revision: local-first design for a 2,048-token context and short reply latency.
This supersedes the earlier per-turn structured answer/fact-update proposal.

Implementation details supersede the target allocations below: compiler version
34, English language pack 1.1.0, schema versions 4/5 with unchanged runtime wrapper
version 2, one generation, 128-token default output and a 128-token safety margin.
Native qualification replaced free personal/clinical paraphrasing in new English
sessions with a compact fact-ID response. The runtime validates IDs against the
selected view and frozen sources, then speaks stored wording, with a 600-character
speech bound. Clear knowledge, greeting and unresolved-reference questions use
shorter prompts. Clear everyday subjects select relevant background areas;
explicit medical subjects discard unrelated life/general history. Presentation
facts alone serve clear intake questions. All permitted facts remain in the
immutable snapshot; nothing is silently shortened to fit an oversized question.
Older snapshots and other languages retain their previous response contract.
There is no optional biography deletion or approximate UI claim of native model
readiness. The actual execution host performs the native tokenizer check.

Snapshots preserve deterministic approved details across request recovery and
history trimming. Desktop/device copies are private recovery evidence; neither
client automatically resumes an interview after process restart. Compiler and
pack versions pin new contexts without changing the existing policy wire name.

## Outcome

Add a Patient background tab to scenario authoring. Authors describe food and
drink, sleep and activity, work and home life, personality and interests, and
additional background. There are no dedicated yesterday/today form fields.
Authors select which everyday areas may be elaborated during a fictional
interview. Clinical facts remain authoritative.

The patient should answer ordinary questions directly, give supported partial
answers, clarify unclear questions and acknowledge missing personal facts.
Everyday details supplied by the conversation's compact background must remain
consistent after older dialogue is trimmed or a request is recovered. The fast
path does not permit unrestricted new autobiographical facts on every turn.

## Local-first implementation constraints

- One model generation per question, with thinking disabled on the
  currently supported local model configuration. No LLM router, summarizer,
  memory extractor, repair generation, embedding service or second model.
- Prepare a compact session background once using authored content and bounded,
  reviewer-approved variation rules. New English personal/clinical turns select
  a bounded JSON array of frozen source IDs; the host validates it and speaks
  stored wording. General questions generate short spoken text directly.
- Keep the patient model resident and reuse existing HTTP connections. Make no
  unsolicited runtime/model/context configuration change.
- Start with a configurable 128-token reply ceiling, one or two sentences, and
  the current 128-token safety margin. Measure completion/truncation behavior in
  each supported language before finalizing this setting; increasing it must
  reduce another optional budget, not overrun the context.
- Default to the latest two complete dialogue pairs. Restore more history only
  where actual token budget and measurements justify it. Background consistency
  must not depend on keeping all prior dialogue.

Starting allocation for a 2,048-token model (targets, not measured token counts):

| Component | Tokens |
| --- | ---: |
| Patient role and response rules, including language instructions | 160 |
| Compact required clinical facts and patient identity | 800 |
| Stable session background | 160 |
| Recent complete dialogue pairs | 320 |
| Current question | 128 |
| Chat template and message delimiters | 64 |
| Reserved spoken output | 128 |
| Safety margin | 128 |
| Remaining headroom | 160 |
| Total | 2,048 |

The native tokenizer measures the entire rendered prompt, including its actual
chat template. These allocations share spare capacity; the question is not
silently truncated to 128 tokens. A longer question first reduces old history
and optional background. If the question plus required clinical facts still
cannot fit, report the capacity limit before generation. Never silently drop
medicines, allergies, symptoms, explicit negatives or case-critical timelines.

## 1. Authoring and contracts

- Add an optional, bounded background section in a new scenario contract version;
  retain support for current version 4 scenarios and their existing behavior.
- Store localized background text separately from clinical history. Define stable
  category identifiers and an explicit author-controlled set of permitted
  elaboration categories. A text entry alone does not enable elaboration.
- Existing scenarios have elaboration disabled. New drafts present the option
  clearly; publication requires reviewer approval of the selected behavior.
- Add the tab inside the existing Clinical details step. Include its content and
  policy in copy/import/export, preview, review, immutable publication, practice
  snapshots and device runtime payloads. Published scenarios remain read-only.
- Treat blank background as unspecified. Preserve explicit negative facts. A
  clinical field overrides background and generated details.
- Include background in translation hashes and review stamps. Changing it
  invalidates affected approvals through the existing publication workflow.
- Reject unsupported categories, excessive text, invalid localized values and
  instruction-like metadata. Free text remains data, never trusted instructions.
- Show a compact-runtime preview and a small-context readiness result. Rich
  authoring text is not permission to send an unlimited biography to the model.
  Flag oversized required cases for author editing or a larger supported model;
  do not hide clinical facts to make a token target pass.
- Everyday variation rules must be explicit, narrow and reviewable. Prefer
  choices supplied by the author; any system-provided choices require approval
  and localization. Do not infer structured facts from arbitrary prose with an
  unreliable keyword heuristic or an extra model call.

Primary surfaces: shared clinical/scenario contracts, localized-case helpers,
API scenario schemas/runtime compilation, UI patient-catalog types,
ScenarioLibrary editor and publication previews.

## 2. Prompt policy

- Update the shared conversation prompt and every supported language pack together;
  remove conflicting instructions that always require the exact uncertainty phrase.
- Separate authored clinical facts, authored background and previously established
  session details into clearly delimited prompt sections.
- Allow elaboration only inside author-enabled everyday categories, constrained
  by the supplied background. Prefer broad answers over unnecessary exactness.
- Explicitly forbid inventing clinical symptoms, diagnoses, medication use,
  allergies, investigations, relevant exposures or illness timelines. Do not infer
  an absence from missing information or normal vitals.
- Answer the supported part of mixed questions and express uncertainty only for
  the unsupported part. Use clarification for unclear questions and general
  knowledge for impersonal questions while retaining the patient role.
- A trainee cannot enable elaboration or rewrite the case through dialogue.
- Bump policy/compiler and language-pack versions. New conversations pin the new
  versions; existing contexts follow the established stale-version behavior and
  require a fresh conversation when necessary.
- Replace duplicated prohibitions and long examples with a single compact rule
  set. Preserve their meaning and verify it through tests; do not concatenate the
  new policy to all the old text. Spend context on patient facts rather than
  repeating the same uncertainty instruction.
- Compile only the selected language. Order stable rules and clinical/background
  facts before changing dialogue to allow prefix reuse where the local server
  supports it. Cache benefits are measured, not assumed from the config name.

Background food details that could establish an allergy, poisoning or symptom
trigger must be authored clinical events. Category allowlisting and prompt
instructions reduce risk but do not prove semantic correctness of an LLM reply.

## 3. Stable background without per-turn fact extraction

- Use shared deterministic code to compile a small session background on the
  existing conversation-start path. Authored facts always win. Permitted choices
  may vary with a conversation seed, but remain stable for that conversation.
- For example, an author-approved ordinary meal pattern can produce one simple
  recent-meal detail. This does not introduce yesterday/today form fields and
  does not authorize inventing illness triggers, allergies or special diets.
- Store its seed/compiler version, provenance and bounded resolved values in the
  existing scoped conversation snapshot. Send it through the existing local
  startup response; no new per-question network request is needed.
- Cache the same valid snapshot durably on the desktop for supported recovery.
  Cache scope includes conversation, tenant, scenario revision, language and model
  context. Expired/replaced contexts cannot be resumed or shared across users.
- Reuse these values on every turn. The model can vary wording and answer general
  questions, but cannot establish additional unsupported precise life events.
  For missing incidental details, prefer a supported general answer; for example,
  "Usually home-cooked food" rather than an invented exact restaurant or time.
- Retain existing plain-text completion validation and result persistence. Keep
  disk writes off the UI thread, model submissions idempotent and audit operations
  atomic. Do not add a memory write or extraction job on every turn.
- Preserve the stable background across history trimming and request recovery.
  Invalid/failed/cancelled generations neither change it nor trigger a repair call.

This deliberately limits free-form improvisation to keep a small model fast and
consistent. Some specific personal questions still cannot be answered without
authored or approved session facts. Plain-text validation cannot prove semantic
correctness; test actual model behavior before claiming factual consistency.

## 3a. Token budgeting and caches

The current fitter in `patient_turn.py` obtains `/props`, applies the chat template
and tokenizes the prompt; it can repeat rendering/tokenization while dropping
old pairs. The current conversation engine reserves up to 256 output tokens and
uses a 128-token margin; local history configuration allows 12 messages.

- Cache immutable compiled text by case snapshot hash, policy/compiler version,
  selected language and session-background identity. Use bounded in-memory caches.
- Cache `/props` and model capabilities for a short bounded lifetime, keyed by
  endpoint, model/config revision and template identity. Invalidate on detected
  service/config changes, restart, mismatch or context-related failure. Recheck
  conservatively when server identity cannot be verified. Never blindly retry an
  uncertain submitted generation because a cache became stale.
- Reuse an exact rendered-prompt token count only for an identical prompt and
  tokenizer/template identity. Separately cached fragment counts can guide initial
  history selection but cannot replace final exact counting: token boundaries
  and template overhead are not reliably additive.
- Choose a short initial history using cached sizing; normally render/tokenize
  the final candidate once. Keep a bounded corrective fitting pass if needed.
- If the stable context is too large, remove only optional material in a defined
  order or require author/model changes. Required clinical facts stay intact.
- Do not add semantic retrieval to the default 2,048-token path. Keyword routing
  can omit essential negatives or cross-topic history; an LLM router adds latency.
- Keep server prefix caching as an optional measured optimization. A 256-MiB cache
  setting does not establish that the conversation endpoint reuses prompt tokens.
- Do not speak unchecked partial tokens. Measure model first-token time and actual
  answer/playback latency separately; a short completed reply retains validation.

## 4. Existing case content

- Inventory starter facts removed with the legacy dialogue section. Map useful
  patient facts to the new background or appropriate clinical history.
- Produce reviewable replacement drafts from original starter sources. Recover
  custom facts only from an available original export/backup; do not guess them.
- Preserve tenant edits, source lineage and existing published versions. Content
  restoration requires normal translation/review/publication; migration must not
  automatically approve restored or generated content.
- Preserve known explicit events where supplied, including Alex's historical
  yesterday-meal fact. The UI need not have a dedicated field for each event.
- Fix stale evaluation expectations where the corresponding fact is deliberately
  absent. Do not rewrite the frozen seed files or earlier migrations.

## 5. Database and compatibility

- Add forward migrations for the new document shape, bounded session background
  and matching database constraints. Keep legacy documents readable, and avoid a
  blanket rewrite of historical published content.
- Update SQLAlchemy models, request/result schemas, runtime grants and readiness
  checks together. Retain tenant/department ownership, lifecycle restrictions,
  quotas, audit atomicity, lease checks and retention/redaction behavior.
- Protect session background as private patient conversation data. Never log
  prompts, private background, credentials or generated personal details in
  operational diagnostics.
- Roll out API/shared contracts/UI/desktop/device compatibility together. Older
  companions must continue on a supported strict path or receive an explicit
  upgrade-required response; never silently enable unsupported elaboration.

## 6. Verification and acceptance

Create a versioned question matrix covering all 20 reviewed background questions,
known clinical positives and negatives, missing clinical facts, general questions,
mixed questions, ambiguity, conflicting premises and prompt-injection attempts.

Required checks:

- Authoring save/reload/copy, translations and separate-reviewer publication.
- Version 4 compatibility and migration upgrades on disposable PostgreSQL, including
  constraints, role permissions, concurrent turns, atomic writes and retention.
- Repeated everyday questions before/after history trimming, process restart and
  response recovery. Verify no cross-conversation background and no regeneration.
- Flexible mode on/off, unsupported categories, malformed output and cancellation.
- Token exhaustion, long questions and contradictions. Missing clinical facts stay
  unknown. Test English/Hindi separately; a character budget is not a token budget.
- Background preparation happens once, output remains plain text, and every
  admitted question makes one generation. Test cache invalidation and native
  template/tokenizer counting with local context set to exactly 2,048.
- Identical prompt/response contracts for local/cloud and desktop/device paths.
- Full relevant API/desktop tests, UI tests/build/types, Ruff and mypy; record
  skipped tests and unrelated fixture limitations explicitly.
- Benchmark the baseline and new path on the same installed model/hardware with
  warm and cold caches, short and near-limit questions and repeated follow-ups.
  Record prompt size, preparation time, prefill, completion tokens, first-token
  time, complete-answer/playback p50/p95 and capture/UI responsiveness.
- Initial performance acceptance target: no more than 10% regression in warm
  complete-answer p95 on the fixed question matrix, with shorter prompt/preparation
  targets where possible. Treat this as a proposed release gate, not a promised
  result; report whether it was met and any quality/latency tradeoff.
- Use local native model evaluation when its installed runtime is available and
  execution is requested. Keep cloud calls/hardware integration separate from
  mocked tests; do not present mocked timing as actual inference latency.
- Use mocked providers for implementation tests. A requested live evaluation must
  separately measure semantic quality on the actual assigned models. Passing
  mocks or structural tests is not a live-model quality claim.

Completion requires accurate supplied clinical answers, natural enabled everyday
answers, stable session details after history trimming/recovery, no unauthorized
clinical invention in the evaluation matrix and measured performance within the
agreed budget. Maintain TODO/review evidence and report remaining limitations.

## Delivery sequence

1. Benchmark current local path; prototype compact prompt and exact 2,048-token
   fitting with plain replies before committing to the full feature architecture.
2. Contracts and forward migration; background editor and publication support.
3. Shared compact prompt, once-per-conversation background and bounded caches.
4. Persistence/recovery, desktop/device compatibility, starter restoration drafts,
   semantic regression matrix and baseline/new-path performance measurements.
5. Review the concrete implementation and evidence. Hosted deployment and live
   cloud/hardware verification remain separate requested steps.
