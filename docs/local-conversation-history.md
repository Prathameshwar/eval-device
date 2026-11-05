# Local conversation history

The desktop executes local inference. Optional archival records the exact accepted input and final delivered answer after execution; PMS never calls, checks, retries or recovers the local model for this feature. Authored case responses and generated/fallback responses are recorded as delivered. Full prompts and internal routing messages are not archived.

## Operation

Desktop, enrolled launcher and API settings default to enabled. New configuration templates set `HUMAN_HISTORY_ENABLED=true` and `PMS_LOCAL_HISTORY_ENABLED=true`. An existing explicit `false` remains an opt-out: change that saved setting to enable history on an older installation. Start a new launcher after changing settings. Reporting remains a bounded background operation, separate from local inference.

The web Sessions page combines assigned session history and standalone captures in
one list. Session status, recording sync and saved/expected items have separate
columns. View session shows the conversation and recordings together; when separate
text reporting saved no messages, it reads the authorized recording archive instead.
Completion alone never implies that all capture items have arrived.

The controller assigns conversation/turn UUIDs and a sequence, captures model/profile/case revisions, and enqueues terminal records without waiting for disk or HTTP. Reset starts new context and a new conversation ID. Completed, failed and cancelled turns are distinguishable. History defaults to the latest ten completed pairs; output-limit answers retain their finish reason.

A dedicated disk thread writes a private outbox independently of the upload thread. Slow PMS requests cannot hold the disk writer. Temporary files are flushed and atomically finalized; a per-directory OS lock permits one writer. Finalized records recover on restart. An acknowledgement removes the pending file; an unknown upload outcome retries the same turn key and identical payload. Inference and speaker playback are never retried by archival.

Outboxes are partitioned by PMS destination, organization, department and identity issuer/subject. JWT claims are used only as namespace hints; the uploader checks the server-authenticated identity before sending text. Credentials are not saved in records. Expired authentication requires renewed credentials for the same identity (restart this desktop with the renewed token). Local files use private OS permissions, not application-level encryption.

The History button merges local pending records with server history by turn key. Status distinguishes pending local save, saved locally, saved to PMS, rejected upload and failed save. Failed saves never cancel a delivered answer. Normal shutdown allows two seconds for local flushing and does not wait indefinitely for PMS.

## Bounds and durability

Defaults: 64 queued records and 8 MiB estimated queue bytes; 1,000 pending files or 64 MiB; pending age 24 hours. The input remains bounded to 8,000 characters and the final answer to 32,000 UTF-8 bytes. HTTP bodies are capped at 128 KiB. Server archive capacity defaults to 10,000 records or 100 MiB per organization, checked under a tenant lock. Server retention is at most seven days and is tightened by platform/organization result retention policy.

Records still only in memory can be lost on a crash. A slow or failed disk can exhaust the queue; the application reports that history was not saved and continues answering. Finalized outbox files survive process restart; no zero-loss claim is made for hardware failure. Rejected pending records remain private until their local expiry and are not retried. Incomplete/corrupt files are not presented as saved and are bounded by the same directory capacity/cleanup.

Client occurrence and completion time are retained separately from server receipt time. Uploads older than the configured window (maximum 24 hours) or more than five minutes ahead are refused. Server retention starts at server receipt, not at client time. Device reports may omit the department: the API resolves it from the authenticated device, then requires it to match the owned frozen conversation. An explicit mismatch is rejected, and a reassigned device cannot move an old conversation into a new department. User reports retain their explicit historical scope.

Metrics remain on the existing text-free /llm/local-turns contract. They share the turn key, use its existing short freshness window, and do not gate history insertion. Cloud response handling and the local model execution contract remain separate.

## API

All routes are under /api/v1/organizations/{organization_id}/llm/local-conversation-turns.

- POST the immutable terminal exchange.
- GET lists completed records by default, with limit (1-100, default 10), optional conversation_id, before cursor, completed_only and mine (default true).
- GET /{turn_key} reads one permitted unexpired record.
- GET /identity returns the server-authenticated user/identity and membership scope for the uploader.

Writes require active organization processing permission and current scope. Reads require result permission, current scope and ownership, except organization administrators may explicitly list other organization users with mine=false. Platform administration alone grants no access. Historical configuration identifiers must belong to the organization; patient setup belongs to the reporting user. Local archive data is labelled client_reported, not platform-verified inference.

Identical retries return the existing record; changed payloads under an existing key are conflicts. Uniqueness, capacity and the redacted audit event are transactional. API roles can read/insert; the retention role can delete expired records; records cannot be amended. Expired records disappear from API reads even before cleanup.

## Upgrade and verification

Apply migrations through the current head (including 0018_local_conversation_history), reapply deploy/grant-runtime-access.sql, then start the API/retention process and updated desktop. Existing migrations and metrics records are preserved. Readiness checks the new head. For the private demo, preserve its configuration and take a private database backup before upgrading.

Implementation checks and review findings are recorded in pms-api-reviews.md. Run API pytest against a dedicated disposable PostgreSQL server, plus Ruff and mypy. Desktop tests cover queue pressure, recovery, lost acknowledgements, identity mismatch, delivered-answer pairing and model execution.

The benchmark scripts/benchmark_history.py uses synthetic inference and HTTP; it reports that limitation explicitly. It compares history disabled, successful archival, unavailable PMS and a slow disk. CPU time, Python allocation peak, turn return, answer delivery and enqueue percentiles are separate. Live cloud and Raspberry Pi verification are outside this change.


The opt-in `platform/api/tests/test_native_history.py` also checks a resident local Qwen model against the real HTTP API and disposable PostgreSQL: save online, persist while PMS is offline, restart and recover without another inference call. It requires `HUMAN_TEST_NATIVE_LLM=1` and a dedicated `PMS_TEST_ADMIN_DSN`. The September 21 review includes this passing native check, private demo upgrade evidence and measured enqueue overhead; it does not claim zero CPU/memory use or lossless persistence before the background disk acknowledgement.
