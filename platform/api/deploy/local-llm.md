# LLM through PMS

Requires the [current schema head](../README.md), the updated runtime grants and the normal human OIDC/organization setup. Provider storage was introduced in `0010_llm_providers`. The default adapter is the authenticated resident llama.cpp server, initially installed Qwen3 4B on the machine that asks for the turn — typically the laptop running Human-test. A `local_llama_cpp` connection is **declaration-only**: it stores the model selection and its encrypted key, and PMS never dials it. The caller executes that turn and reports its metadata to `/local-turns`; see [local execution boundary](../../../docs/local-execution-boundary.md). OpenAI and allowlisted OpenAI-compatible providers are also supported; see [provider and token configuration](llm-providers.md). External calls are disabled by default.

## Deployment

Set `PMS_LLM_ENABLED=true` and `PMS_LLM_ALLOWED_PORTS=[8787]`; for a local connection that allowlist only decides which loopback port may be *published* to the caller, since this service never connects to it. The limits below apply to platform-executed calls. Default overall timeout is 120 seconds, with 5,000 accepted requests and 5,000,000 combined input/output tokens per UTC day per organization for online LLMs. All organization users and devices share the allowance. Local execution has no daily request/token quota. Online admission reserves conservative prompt/output capacity, then settles successful complete provider usage; uncertain usage retains the reservation. See [accounting details](llm-providers.md). Cloud concurrency defaults to four active requests per destination across API processes and organizations. Busy requests fail admission with 429; there is no inference queue or automatic retry.

Apply `pms-admin migrate` with the owner connection, then `deploy/grant-runtime-access.sql` using the database owner. Do not give runtime roles ownership. Run the API and `pms-worker --retention`; the processing worker does not need LLM credentials or requests. API startup owns a pooled async client and an abandoned-request recovery loop; model weights stay in the existing native server. Start that server on the caller's laptop with the local-models launcher; it does not need to be reachable from the PMS host. Keep the database credential-encryption keys outside PostgreSQL.

## Connection and request contracts

All routes below start with `/api/v1/organizations/{organization_id}/llm`. Send the existing human bearer token. Platform-admin status alone never grants tenant access. Device credentials are not accepted here.

| Method/path | Contract |
| --- | --- |
| POST `/connections` | Organization connection-management permission; `name`, secret `api_key`, optional `base_url`, `model`, `system_prompt`, `max_tokens`; returns redacted connection, 201 |
| PUT `/connections/{id}` | Full replacement of configurable fields, required `name` and `expected_revision`; optional replacement key; `is_active`; stale revision returns 409 |
| GET `/connections` | Execution permission; active connection shortlist without key or system prompt |
| GET `/connections/{id}/status` | Execution permission; checks provider authentication and exact model alias. A local connection returns `declared` with `inference_verified: false`, because this service cannot reach the caller's machine |
| POST `/completions` | Execution permission, permitted department, unique request key, bounded conversation, `language`, `stream`. A local connection is refused with 409 `llm_local_execution_required` and no request row |
| POST `/local-turns` | Execution permission; metadata only for a turn the caller executed on its own local model — counts, timings, routing outcome, route/connection/practice identity, idempotent on `turn_key`. No prompt, transcript or answer field exists; rows are append-only |
| GET `/local-turns` | Result-read permission; own turns, or the organization's within the actor's department scope |
| GET `/requests/{request_key}` | Result-read permission plus request owner or organization administrator; original department/lifecycle applies |

Create a connection with the private key from `local-models/.state/api-key.txt`, supplied in a private HTTPS/loopback request body. Never paste credentials into a command line, URL, source file or log. The demo provisions only its own isolated database automatically; existing PMS deployments require an authorized operator. No endpoint accepts a provider URL from the completion caller. For local_llama_cpp, permitted endpoints are exactly `http://127.0.0.1:<allowlisted-port>`. Remote/compatible API base URLs require the provider configuration described in the linked guide. Userinfo, query strings, fragments, redirects and environment proxies are rejected.

Example completion body (replace the two sample UUIDs with your values):

```json
{
  "request_key": "45d07ed9-9e4c-4845-bf79-7ddad11346fd",
  "connection_id": "5a31a304-397f-4b65-bfe3-aa5b225fba97",
  "messages": [{"role": "user", "content": "What is 12 plus 8?"}],
  "language": "en",
  "stream": true
}
```

Messages must alternate user/assistant, beginning and ending with user; 1-13 messages, 8,000 characters each and 16,000 total. System messages and extra generation parameters are rejected. PMS adds the connection's administrator-controlled instructions and language instruction. Local maximum output defaults to 100 tokens, configurable 16-512; OpenAI/compatible defaults to 1024, configurable 16-4096. Context-window errors require a shorter question or Reset; history is not silently discarded. Only the local adapter sends temperature zero, seed 42 and the Qwen thinking-disable extension. Cloud/compatible models receive their configured standard token parameter, without those local extensions.

With `stream=false`, response is JSON with `text`, `status`, `request_key`, `cached`, `finish_reason`, optional usage, and model timings. With `stream=true`, SSE events are `metadata`, sequenced `delta`, and terminal `done` or `error`. `done` is emitted only after the answer and audit commit. Errors after response headers are terminal SSE errors; partial text remains incomplete. Headers specify no-store and no buffering. UTF-8 Hindi events can span arbitrary transport boundaries.

Patient practice buffers routing and generated wording until its existing guard
and final authorization succeed. The stages below are the shared
`training-contracts` pipeline, so a locally executed turn routes, guards and
reports identically — but its caps, timings and usage are produced on the
caller's machine and arrive as the reported `/local-turns` record, not as a
platform result. Local topic routing is capped at 75 output
tokens and generated patient answers at 100, or the connection's limit if lower.
These caps apply to existing local connections after PMS restarts; stored settings
and cloud output allowances are preserved. Single objective topics (identity/body size or
vital readings) return the selected authored answer after routing, saving the
second model call. Narrative and mixed questions retain generated wording.
`provider_calls`, `routing_ms` and `voice_ms` distinguish the stages; `voice_ms` is
null when no wording call ran. `total_ms` sums provider time, while Human-test's
Answer timing includes the full PMS round trip. For a platform-executed turn,
quotas still reserve the possible two-call output allowance before routing and
reported usage counts only executed calls. A local turn consumes no platform
quota and holds no endpoint capacity: nothing was admitted here. See the [latency audit](../../../docs/llm-latency-review.md).

Reuse the same request key only to retrieve the exact completed result; changed content/identity conflicts. Running, failed, cancelled and unknown requests are not resubmitted. A transport timeout after submission is recorded as unknown. Cancellation closes the provider response; request state indicates caller cancellation, not a guarantee about every provider instruction already executed. Leases bound crash recovery to the configured timeout plus ten seconds and a 15-second cleanup sweep. Never automatically replay an uncertain inference POST.

## Storage, permissions and operation

`llm_connections` holds encrypted credentials, model settings and a revision, limited to ten per organization. A local connection's key stays encrypted here for administration only; it is never served in a route or a status response. The laptop reads its own model server's key locally (`HUMAN_LOCAL_LLM_KEY`). `local_turns` holds the reported metadata of caller-executed turns and no text; the retention role deletes only expired rows and workers have no access. `llm_requests` holds scoped identity, HMAC request fingerprint, endpoint capacity/lease, reserved tokens, bounded final result and expiry. Atomic audit records contain operational metadata, not submitted text or secrets. Connection revocation/version changes, expired login, membership/department/lifecycle changes and maintenance are checked during active work and again before committing success.

Prompt/history persistence is off. Answer caches may still contain private information and expire within 24 hours; GET returns 410 after expiry. The retention role can delete only expired terminal rows; workers cannot read either LLM table. Key rotation via the existing `pms-admin` credential rotation operation includes LLM connections and increments their revision. The encryption AAD binds tenant and connection identity.

Limits protect this single-laptop pilot, not an internet-facing multi-model gateway. Native llama.cpp context/KV limits are still authoritative. Run the [human-test screen](../../../human-test/README.md) for microphone integration. Live cloud verification, remote laptop agents, patient-context orchestration and production login UX are deferred. Provider wire contracts are covered by mocks; they are not live cloud verification.
