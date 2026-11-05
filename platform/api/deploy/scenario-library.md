# Patient Scenario Library API

The current schema head is `0045_session_archives`. Apply migrations and
runtime grants before starting the API. Authoring accepts version-4 clinical
content only: presentation, symptoms, history and eight vitals. Q&A, Instructor
content and disclosure fields are removed from saved cases and historical
snapshots. See [cleanup and deployment](../../../docs/scenario-simplification.md).

All paths below use `/api/v1/organizations/{organization_id}/training`. Supply a
valid platform-issued or configured OIDC bearer token. Responses use
`Cache-Control: no-store`. Use fictional training content, not real patient data.

## Current scenario and Practice workflow

1. A clinical author creates or copies a version-4 draft, assigning an active
   tenant specialty. The editor contains Patient and specialty, Clinical details,
   and Review & submit. Incomplete drafts can be saved.
2. The author submits the current revision with
   `POST /scenario-drafts/{id}/submit` and `expected_revision`.
3. A different tenant clinical reviewer records language review with
   `POST /scenario-drafts/{id}/localizations/{language}/review`, the current
   revision and approval statement. Every save/review returns a new revision;
   callers must use it for subsequent actions. Content changes invalidate review.
4. The reviewer publishes the submitted, reviewed snapshot using `/publish`.
   Publication revalidates the current revision and records the authenticated
   reviewer, snapshot and audit atomically.
5. Users select a published version in web Practice. The scenario-selection and
   tenant-default endpoints are documented in [Practice storage](../../db/patient-practice.md).

Drafts use `workflow_version=2`: submit, independent language review, then
publish. Migration 0041 converts existing documents, clears stale submissions,
and closes historical conversation contexts after removing their compiled
prompts. Clinical facts and transcripts remain; removed authoring sections do not.

## System-provisioned tenant starters

New tenants receive two active immutable version-4 published starters from their
fictional chest-discomfort and wheeze cases, plus a shared Practice suggestion.
They have `publication_source=system_starter` and `starter_case_id`, with no named
clinical reviewer or approval statement. Their timestamp records system
publication. Editable case drafts, specialties and patient profiles start inactive
for local review; they have a separate lifecycle from published snapshots.
Retirement preserves drafts and history. Choose another Practice default before
retiring the current default. Migration 0041 also converts older starter snapshots to version 4.

## Permissions and lifecycle

| Identity/capability | Access |
|---|---|
| Organization-wide `org.clinical.author` | Create/copy/edit/archive/restore, validate, preview and submit drafts. Tenant administrators receive this capability by role. |
| Organization-wide `org.clinical.review` | Independent language review, publication and retirement. Review cannot be recorded by the content author. |
| Organization-wide processing and results access | Own published Practice selection and conversation admission. |
| Platform administrator without tenant membership | No tenant clinical access. |
| Enrolled device | No authoring access; scoped configuration and session endpoints remain separate. |

Inactive identity, membership, organization or assigned department blocks access.
Maintenance mode allows authorized reads/validation and pauses mutations.
Clinical review remains a tenant responsibility; software validation does not
certify the clinical accuracy of authored content.

## Endpoints

| Method and suffix | Request | Success |
|---|---|---|
| POST `/scenario-drafts` | `request_key`, `code`, optional `document`, matching `schema_version` and tenant `specialty_id`; alternatively `source_scenario_id` or `source_case_id` | 201 `{draft,replayed:false}`; equivalent retry 200 with current draft |
| GET `/scenario-drafts` | Optional `q`, `code`, `specialty`, `archived`, `limit`, `cursor` | `{items,next_cursor}`; summaries exclude document |
| GET `/scenario-drafts/{id}` | None | Current draft document and revision |
| PUT `/scenario-drafts/{id}` | `expected_revision`, complete replacement `document`, optional tenant `specialty_id` | Updated draft and new revision |
| PATCH `/scenario-drafts/{id}` | `expected_revision`, `is_archived` | Updated draft and new revision |
| POST `/scenario-drafts/{id}/validate` | `expected_revision` | `draft_id`, `revision`, `publishable`, `errors`, `warnings`, `preview` |
| POST `/scenario-drafts/{id}/publish` | `request_key`, `expected_revision`, `approval` | 201 `{scenario,replayed:false}`; equivalent retry 200 with original version |
| GET `/scenarios` | `schema_version=4` (default) or `all`; `limit`, `cursor`, `q`; author-only `code`, `specialty`, `status` | `{items,next_cursor}` |
| GET `/scenarios/{id}` | None | Author detail or safe summary according to current membership |
| POST `/scenarios/{id}/retire` | None | `{id,is_active:false}`; repeats create no extra audit event |

Direct POST `/scenarios` is removed. Create a draft and use submit, language review and publication.

Draft lists default to 50 rows; published lists retain 100. Maximum is 100. Cursors are tied to organization, caller and filters; reuse with identical filters. Ordering is immutable creation time then ID descending. Live pagination is not a frozen snapshot. No query preserves legacy version-1 catalog selection. New clients request `schema_version=all` explicitly.

Non-authors see only an opaque ID, learner-safe title, published version, schema version, languages, approval/active status and execution support. Internal codes, specialties, clinical details and approval statements remain private. Legacy cases receive the neutral title `Patient interview` in safe views. Private search/filter fields are rejected for non-authors, including filters that might reveal information only through matching results.

## Legacy version-2 document

`document.version` is the schema version (2), `draft.revision` is the optimistic editing revision, and `scenario.version` is the immutable published case version. They are different counters. Code and schema cannot change during editing. Copying a version-1 case preserves its schema; there is no automatic conversion.

The [cough](../scripts/scenario-examples/cough_draft.json) and [kidney-history](../scripts/scenario-examples/kidney_draft.json) files are fictional development examples, without approval. They demonstrate JSON structure and Hindi/English content, not clinically validated scenarios.

| Group | Fields and rules |
|---|---|
| Catalog | `code`, `title`, `learner_label`, optional `specialty` |
| `patient` | `name`, integer `age_years`; optional `sex`, bilingual `occupation`, `height_cm`, `weight_kg` |
| `presentation` | Bilingual `chief_complaint`; optional `onset`, `duration`, `severity`; `symptoms` with unique `id`, bilingual `description`, `disclosure` |
| `history` | Optional `past_conditions`, `surgeries`, `medications`, `allergies`, `family`, `social`. Each has `knowledge` (`unknown`, `none`, `present`), bilingual `entries`, `disclosure`. Only present history has entries. |
| `vitals` | Optional `temperature_c`, `heart_rate_bpm`, `pulse_bpm`, `systolic_mmhg`, `diastolic_mmhg`, `respirations_per_minute`, `spo2_percent`, `pain_0_10` |
| `dialogue` | Bilingual `greeting`, `clarification`; topics with unique `id`, `intent`, bounded `examples`, bilingual `answer`, `disclosure` |
| `instructor` | `objectives`, optional `notes`, optional concealed `diagnosis`, manual `rubric` (`id`, `description`) |
| `fact_disclosure` | Explicit scalar-reference policy: `volunteered`, `on_question`, or `never` |

Bilingual fields have `en` and `hi`. Drafts may omit sections/translations; supplied malformed values and unknown fields are rejected. Publication requires both labels, patient name/age, chief complaint, explicit medication/allergy knowledge, bilingual spoken content, topics, objectives and a rubric. Optional vitals stay unconfigured when omitted. Numeric technical bounds allow intentionally abnormal simulation values; they do not certify medical appropriateness. Vitals remain static configuration, not device measurements or hardware control commands.

Answers are fixed authored text with optional `{patient.name}`, `{patient.age_years}`, `{patient.height_cm}`, `{patient.weight_kg}`, or the numeric vital paths above. Escaped `{{`/`}}` are literal braces. These explicit names are the entire substitution language: no arbitrary paths, expressions, format specifications, conversions, URLs or external retrieval. Referenced facts must be explicitly permitted in `fact_disclosure`; omitted policy means `never`. Greeting/clarification can reference only volunteered facts. Concealed topics and instructor sections are excluded from preview. Free text still needs educator review.

Canonical document limit is 48,000 UTF-8 bytes; PostgreSQL independently limits its JSONB text to 65,536 bytes. Authoring request bodies are capped at 128 KiB or the configured global limit if smaller. Both draft and published-version capacities are 100 per organization, separately counted. Archived drafts and retired published versions still count. No destructive delete endpoint is provided.

## Legacy version-2 example from PowerShell

Run from `platform/api` against a disposable development organization. Obtain an authorized token through the configured identity provider and keep it out of logs and source control. Replace the placeholders. Publishing must follow an educator's review; the supplied JSON files have no clinical approval.

```powershell
$base = 'http://127.0.0.1:8000/api/v1/organizations/<organization-id>/training'
$headers = @{ Authorization = 'Bearer <access-token>' }
$document = Get-Content -Raw -Encoding UTF8 scripts/scenario-examples/cough_draft.json | ConvertFrom-Json
$create = @{ request_key = [guid]::NewGuid().ToString(); code = $document.code; document = $document }
$reply = Invoke-RestMethod -Method Post -Uri "$base/scenario-drafts" -Headers $headers -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes(($create | ConvertTo-Json -Depth 30)))
$draft = $reply.draft
$path = "$base/scenario-drafts/$($draft.id)"

# GET returns the latest saved revision before editing.
$draft = Invoke-RestMethod -Uri $path -Headers $headers
$draft.document.patient.age_years = 36
$save = @{ expected_revision = $draft.revision; document = $draft.document }
$draft = Invoke-RestMethod -Method Put -Uri $path -Headers $headers -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes(($save | ConvertTo-Json -Depth 30)))
$check = @{ expected_revision = $draft.revision } | ConvertTo-Json
$validation = Invoke-RestMethod -Method Post -Uri "$path/validate" -Headers $headers -ContentType 'application/json' -Body $check
# Inspect validation.errors, validation.warnings and validation.preview locally.

# Only after review: use a separately authenticated tenant clinical reviewer token.
$reviewerHeaders = @{ Authorization = 'Bearer <reviewer-access-token>' }
$publish = @{
    request_key = [guid]::NewGuid().ToString()
    expected_revision = $draft.revision
    approval = @{ educator_name = '<reviewer name>'; statement = '<actual educator review statement>' }
}
$published = Invoke-RestMethod -Method Post -Uri "$path/publish" -Headers $reviewerHeaders -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes(($publish | ConvertTo-Json -Depth 10)))
$catalog = Invoke-RestMethod -Uri "$base/scenarios?schema_version=all" -Headers $headers
```

The authenticated reviewer is recorded as approver; a supplied display name cannot impersonate another account. Validation is read-only, makes no provider calls and does not reserve a revision or approve clinical content. Publish revalidates under the organization/draft locks and atomically stores approval, the exact saved snapshot and its audit event.

## Errors and retries

Errors use `{error:{code,message,request_id,details}}`. Raw input, SQL details and tokens are excluded. Validation issues expose safe field paths and codes.

- 401 authentication; 403 role/private-filter denial; 404 missing or out-of-tenant resource.
- 409 `draft_revision_conflict`, `draft_identity_conflict`, `draft_code_conflict`, `draft_archived`, `draft_revision_published`, `idempotency_conflict`, lifecycle conflict or `scenario_runtime_unsupported`.
- 413 raw body limit; 422 malformed supplied fields, `scenario_incomplete`, invalid cursor or document budget.
- 429 `draft_capacity`, `scenario_capacity` or rate limit; 503 maintenance/database unavailable.

After an uncertain create response, retry the same request key and original request. It returns the existing draft's current state and never resets later edits. A changed request or author conflicts. After an uncertain publication, retry its same key, draft revision and approval; it returns the original version even after later edits/archive/retirement, without reactivation. A different key for an already published draft revision conflicts and includes the authorized existing version ID.

After an uncertain PUT/PATCH, GET and reconcile the latest document/revision. Do not automatically overwrite with a newly read revision. A retry using the old revision returns 409. Retrying a valid creation/publication at capacity still reconciles the existing result. There are no automatic cloud submissions or provider fallbacks in this workflow.

Version-2 admission is rejected before session reservations and before device/control grants. `execution_supported` is descriptive only and does not override server checks. Version-1 training sessions remain supported; published version-4 scenarios support the current conversation/Practice runtime.

## Verification

Run the platform checks in the API README against a dedicated disposable PostgreSQL server. `test_scenario_library.py` covers workflow/security/transaction behavior; `test_scenario_contracts.py` covers clinical document mechanics. Existing database and training tests remain required. Test counts and the two implementation reviews are recorded in [review evidence](../../../docs/pms-api-reviews.md). Local checks do not verify live cloud services, clinical accuracy or Raspberry Pi hardware.
