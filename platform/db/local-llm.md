# LLM storage

Forward migration `0009_local_llm` follows `0008_scenario_drafts`. It adds two tables and 32 fields. Forward migration `0010_llm_providers` then adds four connection fields (18 tables, 329 fields at that revision). Subsequent migrations add [scenario categories](scenario-categories.md) and [fictional patient identities](patient-identities.md); current head `0012_patient_identities` has 20 domain tables and 356 fields. Frozen SQL baseline and prior migrations remain unchanged. Apply the updated API grant bundle after upgrading. The API readiness check requires the current head. The existing scenario-library verifier accepts the reviewed heads from 0008 through 0012.

## llm_connections (18 fields)

| Fields | Storage/meaning |
| --- | --- |
| id, organization_id, created_by | UUID identity, tenant and creating human |
| name | 1-100 characters; unique per organization |
| base_url, model | Canonical API destination (maximum 512 characters) and explicit model alias |
| provider | local_llama_cpp / openai / openai_compatible; migrated rows remain local |
| token_parameter | max_tokens / max_completion_tokens; OpenAI requires the latter |
| stream_usage | Request usage in SSE; mandatory for local/OpenAI, optional for compatible |
| instruction_role | system / developer; existing local protocol requires system |
| system_prompt | Administrator-controlled instructions, 1-4,000 characters |
| max_tokens | 16-512 for local; 16-4096 for OpenAI/compatible; reservation includes reasoning when using max_completion_tokens |
| encrypted_credentials, credential_key_id | AES-GCM encrypted credential envelope and external key identifier |
| revision, is_active | Revision increases exactly once per edit/reencryption; active lifecycle |
| created_at, updated_at | Server timestamps |

A trigger locks the tenant and enforces ten connections per organization. API transactions use READ COMMITTED. Tenant/identity fields cannot be changed. Credentials use the existing vault with tenant/connection-bound authenticated data. Master keys are outside PostgreSQL. No role except the API runtime and trusted schema owner needs credentials.

## llm_requests (18 fields)

| Fields | Storage/meaning |
| --- | --- |
| id, organization_id, department_id, user_id | Immutable request identity and recorded authorization scope |
| connection_id, connection_revision | Tenant-bound connection snapshot |
| request_key, fingerprint | Unique per-tenant UUID and keyed request fingerprint; no stored prompt |
| target_key | Canonical provider-endpoint digest used for shared capacity |
| status | running / succeeded / failed / cancelled / unknown |
| reserved_tokens | Maximum output budget charged at admission, 16-4096 |
| lease_token, lease_expires_at | Worker ownership and bounded expiry |
| created_at, completed_at, expires_at | Admission/finalization timestamps and at most 24-hour cache expiry |
| result, error_code | Success-only JSON <=64 KiB; sanitized terminal error code |

Composite foreign keys enforce connection and department tenant boundaries. A unique partial index permits only one running request per endpoint. Request key uniqueness, immutable reservation fields, running-to-terminal-only transitions and expired-terminal-only deletion are enforced in PostgreSQL. API admission takes endpoint and organization locks before counting UTC daily reservations and writing request plus audit atomically. Final response is returned only after atomic finalization/audit. No database transaction stays open for inference.

An API recovery loop marks expired running leases unknown. This releases capacity without retrying an uncertain submission. The retention worker deletes expired terminal rows, up to 100 per pass. Logical reads expire immediately at the recorded deadline; physical cleanup requires the retention worker. Audit records use the existing policy-controlled retention and contain no raw prompts or credentials.

## Runtime roles and verification

- API: SELECT/INSERT/UPDATE on both tables; no DELETE.
- Processing worker: no access to either table.
- Retention: SELECT/DELETE on requests only; delete guard rejects live/nonexpired rows.
- PUBLIC: no table or guard-function access.

The database upgrade integration test verifies preservation of existing users, organizations, subscription settings, approved cases, training sessions, old local credentials/settings and running LLM request records, then compares every mapped field with PostgreSQL. LLM integration tests exercise real runtime grants, tenant/department boundaries, encryption, atomic request admission, concurrent duplicate/busy handling, connection count races, expired-lease recovery and retention. Tests must target a dedicated disposable PostgreSQL server. See the [API contract](../api/deploy/local-llm.md) and [validation evidence](../../human-test/validation.md).
