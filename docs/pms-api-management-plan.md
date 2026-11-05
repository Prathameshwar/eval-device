# PMS API consolidated implementation plan

Date: 2026-09-22. Status: phases 1-7 implemented and locally reviewed; disposable PostgreSQL, live-provider, hosted, and hardware verification remain explicitly deferred.

This is the primary plan for all seven phases. It consolidates the earlier phase breakdown and the expanded [model/provider design](pms-api-model-management-plan.md). The model/provider document remains a technical supplement; scope, sequence, dependencies, and completion gates are collected here.

## 1. Scope and confirmed direction

Deliver a complete management API for users, authentication/passwords, tenants, departments, devices, multiple model types/providers, connections, and processing profiles, with consistent pagination, filtering, sorting, and search.

Work includes FastAPI/Python services, SQLAlchemy mappings, PostgreSQL migrations and runtime grants, OpenAPI schemas/examples, local automated tests, and operational documentation. Keep the current single-backend/PostgreSQL architecture. UI work, companion application changes, model installation, new inference workloads/native-provider adapters, physical Pi verification, hosted deployment, and live cloud/email verification remain separate work unless specifically brought into scope.

Follow the [API guide](../platform/api/README.md), [database guide](../platform/db/README.md), [architecture](pms-api-architecture.md), and [service plan](platform-service-plan.md). Earlier OIDC-only assumptions are extended by the confirmed local-account requirement; current OIDC identities and device clients remain supported.

| Area | Consolidated decision |
|---|---|
| Local accounts | PMS owns login, first-password setup, password change/recovery/reset, email verification, and local sessions. |
| External accounts | OIDC provider owns login and passwords; PMS validates trusted tokens and applies its own current authorization. |
| Password storage | Salted Argon2id hashes. Passwords are never stored as recoverable encrypted values. Provider credentials remain encrypted because adapters must use their original value. |
| Account identity | Explicit local/OIDC identity representation; no automatic same-email merging or fabricated external subjects. |
| Tenant naming | Product “tenant” maps to existing `organization` routes/tables. |
| Management deletion | Documented archive/soft-delete preserving references/history; device removal follows retirement. Deactivation and archive are distinct operations. |
| Pagination | Cursor-based lists, default 50 and maximum 100; optional filtered totals. Direct page-number jumps and unbounded exports are outside this contract. |
| Models | Many types, providers, and configured deployments per tenant; independent selections in published profiles. A catalog entry does not imply an executable adapter. |
| Compatibility | Extend current endpoints and defaults; version any unavoidable breaking contract. Never overwrite released migrations or immutable profile/run snapshots. |
| Verification | Local HTTP/PostgreSQL tests and mocked external services. Report live/hardware/deployment verification separately. |

## 2. Execution order and phase gates

Execute phases 1 through 7 sequentially. Phase 1 supplies shared contracts/schema foundations; phase 2 supplies local authentication; phase 3 supplies complete user/onboarding operations; phases 4-6 complete domain management; phase 7 validates the combined system.

| Phase | Objective | Depends on | Completion output |
|---|---|---|---|
| 1 | API conventions, identity/lifecycle schema, shared list queries | Existing API/schema inventory | Tested foundations, endpoint/permission matrix, migration strategy |
| 2 | Local login/password/session APIs alongside OIDC | 1 | Tested local security flows and unchanged external/device behavior |
| 3 | Global users and organization memberships | 1-2 | Complete onboarding, administration, archive, and scoped directories |
| 4 | Organizations and departments | 1-3 | Tenant lifecycle, administrator coverage, subscription/assignment integrity |
| 5 | Devices | 1-4 | Complete device administration, enrollment/lifecycle and configuration compatibility |
| 6 | Model types/providers, tenant configurations, profiles | 1-5 | Multi-provider management, capability validation, preserved execution contracts |
| 7 | Integrated review and handover | 1-6 | Verified upgrades, end-to-end evidence, final documentation and limitations |

Every phase includes implementation, meaningful unit/integration tests, inspection for authorization/integrity/compatibility, fixes, and a recorded completion result. Final testing does not replace phase-level checks. Each phase should be a reviewable change set; record remaining limitations instead of marking incomplete work done.

## 3. Rules shared by all phases

- Resolve identity, current role, organization/department scope, record lifecycle, and applicable quota before every read/mutation. Platform administrator privileges do not imply tenant connection, processing, result, or media access.
- Use explicit request/response schemas and parameterized SQL. Keep credentials, hashes, tokens, signed URLs, and sensitive media out of directory responses, errors, and logs.
- Write business mutations and their audit records atomically. External email/provider calls run outside database locks, with bounded delivery/submission state.
- Preserve last-administrator guards, database lock ordering, concurrent subscription limits, idempotency, worker leases, and uncertain-submission handling.
- Use expected revisions for concurrent management edits. Keep existing `expected_version`/`expected_revision` contracts; phase 1 defines compatible behavior for endpoints that currently lack them.
- Define archive dependencies, restoration privileges, and effective access explicitly. Restoring a record does not revive old sessions, resume queued work, or bypass quotas.
- Retain operation-specific usage units and conservative unknown-usage handling. This increment does not add billing, currency conversion, automatic provider fallback, or blind inference retries.

<a id="phase-1"></a>
## Phase 1 - Contracts, database foundation, and consistent lists

### Deliverables

**1.1 Inventory and contract matrix.** Capture current routes, OpenAPI schemas, role grants, migration head, runtime grants, and supported client requests. Mark each resource's create/list/detail/update/deactivate/archive/restore operation as existing, extended, or new. Include HTTP method/CORS support for DELETE, authentication rate-limit categories, safe errors, and request redaction.

**1.2 Identity and lifecycle design.** Add an explicit local/OIDC account representation. Existing `users.identity_issuer` and `identity_subject` are non-null today; the forward migration must allow their absence only for local identities and retain valid external pairs and uniqueness. Preserve user IDs, memberships, administrator assignments, and history. Global email is not currently unique: enforce unique normalized local login identifiers without breaking existing external accounts or merging them.

Design separate local credentials, local session/refresh state, and setup/reset/verification records. Add archive metadata and optimistic revisions only where existing fields are insufficient. Include lifecycle changes in database guards, not only API handlers.

**1.3 Shared list implementation.** Build small model-specific query helpers with explicit search/filter/sort allowlists. Integrate one directory as the reference implementation; later phases apply the same helpers to their resources.

| Input/output | Contract |
|---|---|
| `limit` | Integer 1-100, default 50 |
| `cursor` | Bounded continuation token; new format is expiring, integrity-protected, and bound to route, query, sort, and effective scope |
| `q` | Proposed maximum 128 characters; case-insensitive substring search over documented permitted fields; wildcard characters escaped |
| `sort_by`, `sort_order` | Allowlisted field and `asc`/`desc`; ID tie-breaker and defined null ordering |
| Typed filters | Resource-specific roles, status, dates, departments, providers, etc.; invalid values fail validation |
| `include_total=true` | Optional exact count with the same permission/search/filter predicates; bound and measure query cost |
| Response | Existing `items`, `next_cursor`, plus `has_more`; `total` only when requested |

Preserve legacy default ordering and UUID cursor semantics for the legacy query contract. Reject mixing a legacy cursor with incompatible new sorts/filters. Reauthorize each page. Read count/page consistently within a request; separate requests remain a live view rather than a frozen snapshot.

**1.4 Mutation contracts.** Specify creation/invitation idempotency where retries could duplicate actions; same key/different body is a conflict. Preserve established status codes and define safe new errors for stale versions, unsupported capabilities, invalid filters, and dependency conflicts. Do not return privileged dependency details to unauthorized callers. Define PATCH omission versus explicit null behavior.

**1.5 Migration and query validation.** Use forward Alembic migrations, matching mappings/schemas/runtime grants/readiness changes, and representative indexes justified by query plans. Recheck current head before naming migrations; `0019_patient_turn_recovery` is the planning baseline, not a reserved next migration number.

### Acceptance

Tests cover malformed inputs/cursors, tampering, expired cursors, duplicate/null sort values, first/last/empty pages, filter changes, scoped totals, SQL-injection-shaped input, stale writes, idempotent retries, and audit rollback. Upgrade representative existing records without identity/ownership loss. Local authentication remains inactive until phase 2 is ready.

<a id="phase-2"></a>
## Phase 2 - Local authentication and password management

### Endpoints

All paths below are proposed under `/api/v1`; keep existing `POST /identity/sync` and `GET/PATCH /me`.

| Operation | Purpose |
|---|---|
| `POST /auth/login` | Verify local email/password, account setup/verification, and active state; issue a local session and credentials |
| `POST /auth/refresh` | Atomically rotate refresh credentials; detect reuse and revoke the affected family |
| `POST /auth/logout` | Revoke the current local session |
| `POST /auth/logout-all` | Revoke all local sessions for the authenticated account |
| `POST /auth/password/setup` | Establish the first password using a one-time setup token |
| `POST /auth/password/change` | Require a local authenticated account and current password; replace the hash and revoke existing local sessions |
| `POST /auth/password/forgot` | Initiate local recovery using a generic response that does not reveal account existence or authentication method |
| `POST /auth/password/reset` | Consume a valid reset token, replace the hash, revoke local sessions, and require a fresh login |
| Email verification/change actions | Initiate and confirm purpose-bound local email verification/change; exact paths/schemas finalized in phase 1 |
| `GET /me` additions | Report account capabilities, including whether PMS password management is available |

### Work packages

**2.1 Credentials and bootstrap.** Use a maintained Argon2id implementation with per-password random salts, stored algorithm/work parameters, bounded input, measured hashing cost, and rehash on successful login when needed. Adopt a documented length/blocklist policy without silent truncation or arbitrary password transformations. Add a trusted one-time local administrator bootstrap path; no public administrator signup, shared default password, or password in command-line arguments. Preserve OIDC bootstrap.

**2.2 Sessions.** Use short-lived local access tokens with explicit PMS issuer/audience/key/algorithm rules and server-owned session identity. Check current session/account validity on protected requests. Hash refresh credentials at rest, rotate atomically, retain bounded replay-detection state, and clean up expired records. Keep signing keys outside PostgreSQL and separate from device/media secrets.

Finalize transport in phase 1 while retaining bearer compatibility. Any cookie-based variant requires Secure/HttpOnly settings, CSRF/origin checks, and explicit CORS behavior; frontend storage is outside this API task.

**2.3 Account actions.** Setup, verification, reset, invitation, and email-change tokens have separate purposes, expiry, attempt bounds, and atomic consumption. Store opaque action tokens as hashes. Successful recovery never activates a suspended user, grants a role, or creates membership. Local login/recovery email changes take effect only after appropriate verification and invalidate superseded action tokens.

**2.4 Delivery and abuse prevention.** Deliver account email from a bounded durable outbox after commit, with protected short-lived payloads and delivery leases. Accepted recovery is not a delivery guarantee. Public APIs never return recovery tokens. Use shared PostgreSQL-backed authentication rate limits and bounded hashing concurrency across API processes; the current per-process limiter alone is insufficient for local login. Keep unknown-account handling comparable and avoid attacker-triggered permanent lockout.

**2.5 Multiple identity types.** External users keep provider-managed passwords. Local, external, and device credentials use distinct verification paths; a failed verification must not fall back to a weaker verifier. No automatic same-email linking. External-only accounts cannot obtain local credentials through setup/recovery. Invitation acceptance must bind the intended identity or method where email alone would be ambiguous.

### Database and operational output

Local credentials; sessions/refresh families; purpose-bound action tokens; bounded email outbox/shared counters; explicit secret redaction and least-privilege grants. A narrowly scoped delivery role/process may read protected outbox payloads; ordinary processing workers do not read password hashes. Local auth defaults disabled until migrations, keys, delivery configuration, and readiness checks satisfy its contract. OIDC-only deployments continue to work.

Use fixture-created users to test phase 2 before phase 3 adds full user creation endpoints. Document key rotation, session revocation/cleanup, delivery failures, and operator recovery.

### Acceptance

Local setup/login/change/reset/logout journeys pass. Tests cover wrong passwords, inactive/archive state, wrong issuers/keys/algorithms, expired tokens, refresh replay/concurrency, concurrent reset versus login/refresh, wrong-purpose action tokens, external/local email collisions, invitation binding, email failures, rate limits, and redaction. Existing OIDC/device tests pass. External provider/email calls are mocked.

<a id="phase-3"></a>
## Phase 3 - Users and organization memberships

### Global user administration

Extend `GET /platform/users` and `PATCH /platform/users/{user}`; add `POST /platform/users`, `GET/DELETE /platform/users/{user}`, and a controlled restore action. DELETE means archive.

- Create local accounts pending secure setup/verification. Prefer a one-time setup invitation; never return a stored password.
- Read permitted profile/status details, update fields according to ownership, activate/deactivate, archive, and restore with current safeguards.
- Preserve platform-role assignment controls and the last active platform administrator.
- Keep external identity email/verification provider-managed. Local email changes use phase 2 verification.
- Preserve `/me` self-service fields and account capabilities. Do not expose hashes, reset/session tokens, unnecessary provider identifiers, or unrelated memberships.

### Organization membership administration

Reuse invitation create/resend/accept and member update routes; complete member detail, invitation cancellation, membership removal/deactivation, and reactivation. Organization administrators can initiate scoped local/external onboarding without receiving global account-edit permissions or a global account-existence lookup.

Return purpose-built member summaries with permitted display name/email, role, department, invitation and active state. Removing one membership does not disable other memberships or delete the global user. Enforce invitation expiry/single use/identity binding and concurrent user-seat accounting.

### Lists and lifecycle

Apply the phase 1 contract to global users and member summaries. Support appropriate name/email search, method/status/role/department/invitation filters, and allowed creation/login/activity/joined-time sorts.

Global archive blocks both local authentication and external synchronization, revokes local sessions/actions, and preserves history. Restore never revives old sessions or bypasses administrator coverage, subscription limits, or identity verification. Last-org-admin changes require a valid atomic replacement or permitted tenant suspension.

### Acceptance

Local create/setup/login and external sync/invite journeys reach correct memberships. Tests prove org admins cannot edit global identities, pending users cannot bypass activation, duplicate requests are safe, archived users cannot reappear through sync, and concurrent last-admin/seat mutations preserve database guarantees.

<a id="phase-4"></a>
## Phase 4 - Organizations and departments

### Deliverables

**4.1 Organization directory and onboarding.** Preserve `GET/POST /organizations`, `GET/PATCH /organizations/{org}`, platform directory/update, administrator assignment, and subscription routes. Add missing platform create/detail/archive/recovery operations with directory-only responses where no tenant membership exists.

Self-service creation follows registration policy and verified identity. Platform creation can nominate/invite the intended first org admin without silently enrolling the acting platform admin as a tenant member. An organization without its required accepted active administrator remains inactive.

**4.2 Settings and subscriptions.** Manage permitted name/contact fields, policies, plan assignment, usage/capacity summaries, and default profiles. Keep policy limits and profile references server-validated. Plan reductions, reactivation, and invitation/device allocation must retain concurrent subscription guarantees.

**4.3 Departments.** Complete existing create/list/update with detail, archive, and controlled restoration. Resolve active user/device assignments before archive; reject unresolved dependencies with authorized details. Never silently move records or rewrite historical department snapshots.

**4.4 Lifecycle and lists.** Add organization/department search, typed filters, sort, pagination, and scoped totals. Platform suspension requires platform recovery. Organization archive preserves child records, audit, media retention obligations, and history. Restoration does not resume old work or silently reactivate children.

### Acceptance

Test first-admin onboarding, registration modes, directory-versus-tenant permissions, department dependencies, default-profile validation, plan changes/limits, and suspension/archive/recovery. Concurrent updates cannot orphan administrators, over-allocate capacity, or cross tenant boundaries.

<a id="phase-5"></a>
## Phase 5 - Device administration

### Deliverables

**5.1 Directory.** Extend existing create/list/detail/update operations with explicit response schemas, revision checks, standardized lists, and assignment validation for department, profile, language, location, and contacts. Ordinary updates cannot transfer devices between tenants.

**5.2 Distinct statuses.** Expose active state, enrollment/retirement state, credential status, server-derived connectivity, registration/enrollment/last-seen/activity times, desired configuration, and acknowledged revision/hash separately. An active device may be offline; an inactive device may still report basic health.

**5.3 Enrollment and retirement.** Preserve single-use enrollment, credential issuance/revocation, and retirement. If a DELETE route is added, it is a documented alias of retirement with the same permission/lifecycle semantics. No ordinary PATCH can revive retired credentials. Any recovery/re-enrollment path must remain explicit and satisfy current lifecycle rules.

**5.4 Configuration and existing operations.** Preserve restricted inactive-device config/heartbeat behavior, subscription seat accounting, current processing admission, and historical department attribution. Revocation/retirement blocks new work; later recovery must not replay old audio or uncertain submissions.

### List coverage

Search permitted device names/locations/identifiers. Filter by department, type, profile, active state, enrollment state, and online/offline status. Sort by name, registration, or last seen with explicit null behavior. Connectivity is evaluated from server time and may change between pages.

### Acceptance

HTTP tests cover concurrent enrollment, token reuse, stale/revoked/retired credentials, unauthorized assignment, department/profile/language validity, quotas, retirement retries, inactive exceptions, and configuration acknowledgment compatibility. No hardware execution is required to complete API verification.

<a id="phase-6"></a>
## Phase 6 - Multiple model types, providers, and configurations

Phase 6 manages multiple choices per tenant/operation and independently selected providers in a profile. It builds on existing execution paths and distinguishes catalog metadata, configuration, adapter availability, access validation, and actual execution evidence.

### Domain boundaries

| Concept | Responsibility |
|---|---|
| Provider | Hosting/service authority; separate from model publisher |
| Adapter | Reviewed code for a particular protocol/service/operation/auth mode |
| Model/service definition | Family/version where known, categories, operations, modalities, typed capabilities and parameter contract |
| Tenant connection | Tenant endpoint/resource/region/authentication plus encrypted credentials |
| Configured binding/deployment | A model exposed through one authorized connection/adapter, with deployment/model ID, settings and revision |
| Published profile | Immutable selections/settings for enabled operations, assigned to an organization/device |

A model may have several modalities/operations and several deployments. A provider may supply several model types. Azure deployment labels, provider model identifiers, local aliases, publisher and version are distinct fields.

These logical boundaries do not require duplicate credential stores or six new tables. Preserve existing LLM/provider connection IDs and APIs; project their configuration into a unified management view and add a separate association only where necessary.

### Model-type coverage

| Category | Input -> output | This phase's execution commitment |
|---|---|---|
| Text/conversation LLM | Text -> text | Manage and preserve existing supported text paths and model-specific options |
| ASR/transcription | Audio -> transcript | Manage existing local/cloud speech and job paths with their actual mode limits |
| TTS/synthesis | Text -> audio | Manage implemented synthesis services, languages, voices, and output settings |
| Video analysis/detection | Video/frames -> labels/events | Manage existing supported analysis jobs and local result contracts |
| Multimodal/vision/OCR | Text/image/document -> interpretation | Catalog/capability representation; new execution requires an operation-specific adapter/API |
| Embeddings | Text/image -> vectors | Catalog/configuration representation; no new embedding engine/vector database |
| Reranking | Query/candidates -> scores/order | Catalog/configuration representation; no new ranking execution |
| Image/video generation | Prompt/reference -> generated media | Catalog/configuration representation; dispatch awaits dedicated adapter/media/quota/reconciliation work |

Future categories remain non-executable when their adapter or API operation is missing. Existing profile slots are extended only through versioned changes once an operation is implemented.

### Provider coverage

Preserve the code's current direct OpenAI text, Azure OpenAI text, approved OpenAI-compatible text endpoints, local LLM, Azure interactive speech, AWS media services, Azure Speech, Azure Video Indexer, and explicit local processing contracts.

The catalog/interface can accommodate additional providers such as Anthropic, Google/Gemini, AWS Bedrock, and other self-hosted runtimes. Their native adapters are follow-on execution work, not implied by registering metadata. “OpenAI-compatible” describes a protocol and does not prove all capabilities.

Show independent status for catalog lifecycle, adapter availability, configuration validity, current-revision access checks, sample execution evidence, and effective availability/reason codes. A successful model listing or credential check is not proof that a deployment can run every operation.

### Parameter and capability validation

Use bounded, reviewed adapter schemas and expose parameter descriptions as read-only metadata:

- LLM: context/output allowances, permitted instruction role, supported temperature/reasoning/streaming/structured-output options.
- ASR: language, encoding, channels, sample rate, duration/byte limits and supported timestamps/diarization/modes.
- TTS: voice-language compatibility, format/sample rate, text length and supported voice options.
- Vision/video: input formats, image/frame counts, dimensions, clip duration/frame rate and output/job contract.
- Future embeddings/reranking: dimensions, batch/input limits, vector/score conventions without enabling missing execution.

Reject unsupported parameters rather than silently ignoring them. Effective capabilities are constrained by the installed adapter, model/deployment, and application operation. Apply platform/tenant/profile/binding limits in their proper units. Validate on configuration changes, publication, activation, and dispatch.

Never allow catalog data to upload executable validators, arbitrary headers, or endpoint templates. Preserve destination/network protections and local-execution boundaries. A remote API server's loopback is not a user's laptop.

### Profiles and mixed-provider use

Keep existing `audio_input`, `conversation`, `audio_output`, and `video` sections and old clients. An illustrative profile can use Azure transcription, a local or direct OpenAI conversation model, AWS Polly synthesis, and Azure Video Indexer analysis. Each caller/device still needs the relevant operation support.

Support drafts, validation, immutable publication, assignment, revision history, and rollback by publishing a new revision. Store definition/schema versions and effective settings in snapshots. Changes affect subsequent work; in-flight work keeps its recorded configuration.

Catalog retirement blocks new selection without rewriting history. Connection/provider disablement blocks applicable dispatch. Unsafe archive reports authorized dependencies and fails instead of deleting referenced configurations. Credential/configuration changes invalidate relevant evidence. No automatic provider fallback, load balancing, or uncertain-request replay is introduced.

### API and list surface

- Provider/catalog reads: proposed `GET /providers`, `GET /providers/{provider}/capabilities`, `GET /models`, and `GET /models/{id}`.
- Platform model administration: proposed `GET/POST /platform/models` and `GET/PATCH/DELETE /platform/models/{id}`; DELETE retires.
- Tenant configured-model reads: proposed `GET /organizations/{org}/model-bindings` and detail with unambiguous typed/opaque references.
- Reuse existing LLM/provider connection write/status/validation services; complete missing detail/archive/admin-list operations. Preserve active-only selection clients through a separate management contract where needed.
- Extend existing profile, revision, model-options, and effective model-config APIs compatibly.

All management lists use phase 1 helpers. Filter by provider, category, operation, modality, execution mode/owner, lifecycle, adapter availability, and validation state. Search permitted name/model/deployment/description fields. No credential search, endpoint leakage to ordinary selection views, or cross-tenant totals.

### Eight delivery steps

| Step | Deliverable | Exit evidence |
|---|---|---|
| 6.1 | Existing engine/provider inventory, category/operation matrix, capability/status contracts | Every current path mapped; unsupported execution explicit |
| 6.2 | Minimal provider/model catalog and lifecycle, typed parameter descriptions, scoped views | Permissions, model identity/capability validation, retirement tests |
| 6.3 | Tenant connections/bindings and multiple deployments, consistent configured-model reads | Secret redaction, tenant isolation, revision and compatibility tests |
| 6.4 | Per-operation configuration/access validation and small adapter interface around existing code | Invalid options/protocols/destinations and stale checks rejected |
| 6.5 | Mixed-provider profile selections, publication/assignment/revisions/rollback | Immutable history, concurrency, independent capability checks |
| 6.6 | Shared queries, availability reasons, dependencies, existing usage summaries | Scoped totals, bounded lists, typed usage, no secret exposure |
| 6.7 | Forward migration/backfill and explicit legacy mapping | IDs, ciphertext, profiles, model aliases, and effective config preserved |
| 6.8 | Mocked provider/operation matrix, failure/concurrency cases, docs and final review | Required checks pass; live checks and missing adapters stated separately |

### Acceptance

One tenant can manage multiple text/speech choices plus independent synthesis/video services. Another tenant cannot inspect, validate, modify, or use them. The same model can have distinct deployments. A valid text connection cannot authorize unrelated speech/video capabilities. Unsupported categories cannot enter executable slots. Local installation remains unknown without a trusted runtime contract.

Test parameter combinations, publication races, unsafe archives, key rotation, stale evidence, provider disablement, query isolation, legacy upgrades, and uncertain submissions. Use existing usage records; unknown usage is not zero. Discovery/import, if added, is explicit, bounded, reviewed as draft data, and never auto-enables entries. External samples/access calls stay deferred here.

<a id="phase-7"></a>
## Phase 7 - Integrated verification, review, and handover

### End-to-end journeys

- Local admin/user creation -> email/password setup -> login -> profile read -> password change/recovery/reset -> session revocation/logout.
- External identity sync -> correctly targeted invitation -> membership -> scoped administration/use; passwords remain provider-owned.
- Organization creation -> first-admin acceptance -> department/member assignment -> subscription limits -> suspension/archive/recovery.
- Device registration -> enrollment -> profile assignment -> configuration read/acknowledgment -> revoke/retire.
- Multiple model/provider configurations -> operation validation -> mixed profile publication -> assignment -> effective configuration -> lifecycle changes.
- Combined search/filter/sort/pagination/counts, retries, concurrent edits, and forbidden access across all management resources.

### Verification work

Use real local HTTP routes and isolated disposable PostgreSQL databases with representative existing data. Test fresh install, upgrades from the current supported head/baselines, runtime grants, readiness, preserved identities/history, and backup/restore coverage appropriate to the schema changes. `PMS_TEST_ADMIN_DSN` must identify a dedicated disposable server; report skipped DB tests.

Exercise all roles, guessed IDs, tenant/department restrictions, inactive/archived ancestors, administrator guards, subscription races, audit rollback, idempotency, stale versions, token races, secret redaction, delivery failures, and bounded rate-limit/session cleanup. Provider/email calls remain mocked.

From `platform/api` run:

```text
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src/pms_api
uv build
```

Validate OpenAPI/examples and packaged migration artifacts. Perform an implementation review, fix confirmed findings, rerun affected checks, and review the final result again. Record measured query behavior without inventing performance targets or live certification.

### Handover output and completion

Update API/database guides, configuration examples, migration/activation/rollback boundaries, local-admin recovery, token/key rotation, session/outbox cleanup, model capability/provider extension documentation, and the [TODO](pms-api-todo.md)/[review log](pms-api-reviews.md).

Completion requires passing required local checks, preserved upgrade data, no unresolved confirmed authorization/integrity/compatibility findings, an endpoint matrix matching the agreed scope, and an explicit list of skipped/deferred verification. This task does not automatically deploy or publish implementation.

## 4. Consolidated management endpoint coverage

Paths are under `/api/v1`. “Complete” means retain existing operations and add the documented missing ones, not replace working clients.

| Resource | Target coverage |
|---|---|
| Identity/local auth | Existing sync/me plus phase 2 local login/session/password/email actions |
| Global users | Create/list/detail/update, activate/deactivate, archive, controlled restore and setup resend |
| Memberships/invitations | Scoped list/detail, invite/resend/cancel/accept, role/department update, removal/reactivation |
| Organizations | Self-service and platform onboarding, list/detail/update, first-admin assignment, suspension/archive/recovery |
| Departments | Create/list/detail/update, deactivate/archive, dependency-aware restoration |
| Subscriptions | Existing plan reads/admin updates, assignment, usage/capacity summaries and lifecycle integration |
| Devices | Create/list/detail/update, enrollment/revoke/retire, explicit status/configuration/telemetry contracts |
| Providers/model definitions | Capability/catalog reads, model definition administration and retirement, installed-provider policy controls |
| Tenant connections/bindings | Multiple LLM/media configurations, authorized detail/admin lists, updates, key rotation, validation and archive |
| Profiles/revisions | Draft create/list/detail/update, publish, assignment, revision history, rollback and dependency-aware archive |

## 5. Consolidated list field coverage

| List | Search | Main filters | Explicit sorts |
|---|---|---|---|
| Global users | Display name, permitted contact email | Method, active/archive/setup state, platform role, created range | Name/email, created, last login/activity |
| Members | Permitted name/member or invited email | Role, department, active/invitation state | Name/email, created/joined |
| Organizations | Name, authorized contact fields | Active/archive state, subscription plan, created range | Name, created/updated |
| Departments | Name, description | Active/archive state | Name, created/updated |
| Devices | Name/location/exposed identifier | Department, type, profile, active/enrollment state, connectivity | Name, registration, last seen |
| Model definitions | Name, model identifier, description | Provider/category/operation/modality, lifecycle, adapter availability | Name, provider, created/updated |
| Tenant configured models/connections | Name, permitted model/deployment identifier | Provider/type/operation, execution owner, active/archive, validation | Name/provider, created/updated |
| Profiles | Name, description | Active/archive, published/unpublished | Name, created/updated |

Only fields the caller may read can be searched, filtered, sorted, or counted. Add indexes according to actual query plans rather than creating a general unbounded search service.

## 6. Database migration groups

Names below describe proposed responsibilities; assign actual migration IDs after checking the live development head.

| Group | Representation | Required guarantees |
|---|---|---|
| Account identity | Explicit local/OIDC method and valid external issuer/subject pairs | Backfill existing users as OIDC; preserve IDs/pairs/memberships; no blanket global unique-email constraint |
| Local credentials | One-to-one local-user row, unique normalized local login, pending setup or password hash/version | Only local accounts own credentials; never serialize hashes; email/verification changes commit consistently |
| Local sessions/refresh | Session identity, expiry/revocation and hashed rotation/replay state | Immediate local revocation enforcement; bounded cleanup; signing keys external |
| Account actions | Hashed purpose-bound setup/reset/verification/email-change tokens and consumption state | Single-use atomic changes; no invitation/reset token confusion |
| Delivery/rate limits | Protected bounded outbox and expiring shared auth counters | External calls outside locks; narrow sender permissions; no new queue/database service |
| Management lifecycle | Archive metadata and revisions where missing | DB/API guards agree; history/references preserved; restoration cannot bypass invariants |
| Model metadata/bindings | Minimal definitions/provider metadata and associations or projections over existing connections | No duplicated secrets, destructive rebinding, or changed immutable snapshots |
| Query indexes/grants | Scope/filter/sort indexes and explicit API/sender/worker/retention permissions | Tested query cost and runtime permissions; credential access limited to its responsible service |

Every migration includes ORM/request/response schema changes as applicable, runtime grants, readiness expectations, upgrade tests, and documentation. Do not modify frozen SQL or released migrations.

Keep local-auth/new-record creation gated until compatible API processes are running. An older application may not understand a database containing local identities or new lifecycle states; document the supported rollback boundary and use a reviewed forward fix or restore instead of assuming application-only rollback is safe.

## 7. Completion evidence and scope boundaries

For every phase record implemented endpoints, migrations, compatibility behavior, commands/results, skipped tests, findings/fixes, and remaining limitations. Authentication and model/provider changes receive broad security/concurrency coverage because they affect shared boundaries.

Deferred work remains explicit: UI integration, physical devices/companions, live identity/email/cloud verification, hosted deployment, model downloading/hosting, new native-provider adapters and inference operations, automatic provider fallback, account linking, physical-erasure policy, payments/billing, and custom role editing.

Documentation sources for password security: [OWASP password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) and [password recovery](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html). These support the security design; they do not replace local implementation verification.

Implementation evidence is recorded in [the review log](pms-api-reviews.md#pms-management-api-phases-1-7--2026-09-22). The API, forward migration, tests, grants, and operations documentation are complete locally; external verification, deployment, hardware work, and publication are not claimed.
