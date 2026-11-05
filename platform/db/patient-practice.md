# Patient practice data and API

## Current tenant contract

Current schema head: `0035_unified_scenarios`. Apply all migrations with
`pms-admin init-database`, then reapply `platform/api/deploy/grant-runtime-access.sql`.
The frozen SQL baseline cannot initialize the current application by itself.

The web **Practice** page saves a user's selection from active published version-3
scenarios. Organization-wide `org.processing.execute` and `org.results.read` are
required; clinical-author permission is not required for this workflow. Platform
administrator status alone grants no tenant clinical access.

All endpoints below are under `/api/v1/organizations/{organization_id}/patient-practice`:

| Endpoint | Purpose |
|---|---|
| `GET /scenario-options` | Available published scenarios, supported content languages, initial vitals, tenant default and the caller's own selection. |
| `GET /scenario-selection` | The caller's own published-scenario selection, or null. |
| `PUT /scenario-selection` | Save `scenario_id`, `expected_revision`, `language` and all eight bounded vital values. Saves a private snapshot and audit atomically. |
| `PUT /scenario-default` | Tenant administrator changes the shared suggestion using `scenario_id`, `language` and `expected_revision`; requires author and processing access. |

The default is a suggestion; it does not overwrite individual selections. New
tenants receive two labeled, system-provisioned version-3 published starters and
one tenant-wide Practice default. These snapshots can be selected independently
of the inactive editable case catalog. A default scenario cannot be retired until
another default is selected. Existing historical selections and conversations
remain intact during migration.

Migration 0035 adds `tenant_scenario_defaults`, tenant-bound `scenario_id` foreign
keys on `patient_practice_selections` and `patient_conversations`, and scenario
specialty/submission metadata. API access to defaults is SELECT/INSERT/UPDATE;
workers and retention have no access. Selection ownership stays unique per tenant
and user. Published snapshots remain immutable; private observation edits cannot
alter the published document. New and continuing turns recheck permissions,
tenant lifecycle, selection revision, scenario status and language readiness.

Human-test checks published Practice access at startup, restores the same user's
saved web selection, and saves observations before starting a fresh conversation.
Local inference runs on the laptop; PMS authorizes the immutable conversation
context and records bounded activity/history. Conversation execution also requires
an installed conversation language pack; content readiness alone does not install
speech or conversation models.

### Legacy tenant-case compatibility

`GET /catalog`, `GET /cases/{id}`, `GET /selection`, `PUT /selection` and
`PUT /default` remain available for existing tenant-case clients. They require
clinical author access in addition to processing access. Case selection validates
active same-tenant specialty/profile/case relationships and stores a private
snapshot. Old global-case selections are marked `legacy: true` and cannot start a
new conversation. The legacy `tenant_patient_setup_defaults` table is retained for
these clients and history. New web Practice uses `tenant_scenario_defaults`.

## Historical migration `0013_patient_practice` design

The original migration added **22 domain tables and 383 columns** at that point in the schema. The details below describe the former shared catalog and are retained for migration reference; they are not the current tenant authorization or conversation-language contract. Apply the current migrations and runtime grant bundle instead of stopping at 0013.

One fictional patient identity, **Alex**, is shared by nine bilingual version-2 case templates:

| Category | Three default cases |
|---|---|
| Cardiology | Chest discomfort; palpitations; blood-pressure follow-up |
| Nephrology | Flank pain; painful urination; kidney-condition follow-up |
| Respiratory Medicine | Wheeze; persistent dry cough; fever with productive cough |

These are synthetic staff rehearsal examples, not clinically approved learner scenarios. Each supplies complaint/onset, symptoms, six history groups, eight initial observations, 22 scripted answer topics, bilingual greeting/clarification, disclosure rules and instructor guidance. All reference the existing Alex identity. Published scenarios, device assignments and training sessions are untouched.

## Storage

| Table | Fields and integrity |
|---|---|
| `patient_case_templates` (12) | `id`, unique `code`, `category_id`, `patient_identity_id`, `title`, `title_hi`, `document`, `revision`, `is_synthetic`, `is_active`, `created_at`, `updated_at`. Valid version-2 JSON envelope, bounded 48 KB, immutable identity, revisions advance by one. Templates are deployment-managed; runtime API has SELECT only. Nine atomic seed audit events. |
| `patient_practice_selections` (12) | `id`, `organization_id`, `user_id`, `template_id`, `category_id`, `patient_identity_id`, `template_revision`, `document`, `language`, `revision`, `created_at`, `updated_at`. One row per organization/user, template/category/identity foreign key, immutable ownership, revision guard, bounded JSON snapshot. API may select/insert/update; workers/retention/PUBLIC have no access. |
| `llm_requests` (+3) | Nullable `practice_id`, `practice_revision`, `practice_snapshot_hash`. All supplied together or absent. Organization/user/setup foreign key; normal terminal updates preserve provenance. Existing non-practice requests remain valid. |

Selection save requires an active organization-wide membership with `org.profiles.manage` and `org.processing.execute` (currently organization administrators). Platform administration alone does not qualify. Staff preview includes instructor material; the LLM projection excludes it. The database guard also verifies active accepted organization-wide membership. Case/category/identity deactivation blocks new or running practice responses.

## Endpoints

All under `/api/v1/organizations/{organization_id}/patient-practice`, using existing bearer authentication:

| Method/path | Behavior |
|---|---|
| GET `/catalog` | Active categories, identities and case summaries |
| GET `/cases/{template_id}` | Authorized staff preview of a complete case |
| GET `/selection` | Own saved selection, or `{"selection":null}` |
| PUT `/selection` | Save template/category/identity IDs, `template_revision`, `expected_revision` (0 for initial save), language (`en`, `hi`, `auto`) and all eight `vitals` values. Returns saved snapshot/revision. |

Selection and template revisions prevent lost updates. The server validates finite bounded observations, systolic ≥ diastolic, relationships, active state and scenario completeness. It copies the identity and template; the client cannot supply an arbitrary system prompt or document. Save plus audit is atomic. Numeric validation does not certify clinical consistency after manual edits.

Completion requests keep the existing LLM endpoint and add `practice_id` and `practice_revision` together. The language must match the saved selection. PMS loads patient-visible facts on every call, checks ownership/lifecycle/revision, records a snapshot hash and uses the LLM to select scripted topic IDs. Valid topics produce the stored English/Hindi text; invalid or unknown routing produces the case clarification. Provider failure remains an error. Raw routing text is withheld, including during SSE. Practice SSE emits the verified patient answer only after the model completes and successful authorization/finalization. It is not word-by-word speculative speech.

The shared patient-turn renderer shortens the exact stock clarification from migration
0014 to: "Sorry, doctor, I'm not sure. Please ask about my symptoms or medical history."
The matching Hindi stock reply is also concise. This applies to both local and cloud
turns, including existing saved setups, without a second model completion. Custom
authored wording is preserved. Stored documents, snapshot hashes, migrations and
previously cached answers are unchanged. Restart PMS and Human-test to load the update;
the patient setup does not need to be saved again.

The local budget uses authenticated `/props`, `/apply-template` and `/tokenize` on the installed server. `PMS_PATIENT_LOCAL_CONTEXT_TOKENS=2048` caps the model's reported capacity, reserves up to 128 output tokens plus 64 margin, and removes oldest complete history pairs. Mandatory patient context and the current question are never removed. An oversized mandatory prompt is rejected before request admission. `PMS_PATIENT_REMOTE_CONTEXT_TOKENS` must be explicitly set for a remote model; remote practice uses a conservative UTF-8 estimate and retains the connection's full output allowance (including provider reasoning tokens), while existing provider adapters and generic calls retain their protocols. The remote limit is global: set it no higher than the smallest context window of the remote models used by this API instance. Remote context sizes require operator verification; no live cloud validation is claimed.

The standalone `local-models/config.json.system_prompt` is **not prepended** to PMS calls. PMS's practice prompt replaces the connection prompt and is the sole authoritative instruction/context payload. New demo connections copy the short config prompt as a fallback. Provider usage counts routing tokens, not the stored answer text returned by PMS. Result retention remains 24 hours; the current staff setup persists until replaced. There is no saved conversation transcript feature in this increment.

See [implementation plan](../../docs/human-test-patient-workflow-plan.md) and [final audit](../../docs/human-test-patient-workflow-audit.md).
