# LLM providers and token handling

PMS supports `local_llama_cpp`, `openai`, `azure_openai`, and `openai_compatible` through Chat Completions, and Anthropic through its Messages API, with both JSON and SSE responses. The existing Qwen demo stays local. Provider storage was added in `0010_llm_providers`, with Azure/capabilities in `0015_cloud_models` and platform-owned configurations in `0034_platform_model_connections`; apply the [current head](../README.md) and runtime grants before starting this API. Existing local ciphertext, settings, revisions and request records are preserved. The [Platform model setup](../../../docs/platform-models.md) describes the current UI; the [cloud configuration guide](../../../docs/cloud-models.md) covers Azure authentication and capability options.

## Configure a provider

Enable `PMS_LLM_ENABLED=true`. Platform Admin configures and tests new models on `/models`. The older tenant connection API, `POST /api/v1/organizations/{organization_id}/llm/connections`, remains restricted to Platform Admin for existing profiles. Supply any secret in a private request body from a protected configuration source. Never place it in a URL, shell argument, committed file, desktop setting or log. Completion callers provide a connection ID.

| Setting | Local Qwen | OpenAI | Compatible server |
| --- | --- | --- | --- |
| `provider` | `local_llama_cpp` (default) | `openai` | `openai_compatible` |
| `base_url` | `http://127.0.0.1:8787`, root only; declared for the caller, never dialled by PMS | `https://api.openai.com/v1` (fixed/default) | Explicit full API base, e.g. `https://gateway.example/v1` |
| `model` | `qwen3-4b-local` default | Explicit model available to your account | Explicit server model alias |
| `max_tokens` | Default 192; 16-512 | Default 1024; 16-4096 | Default 1024; 16-4096 |
| `token_parameter` | `max_tokens` | `max_completion_tokens` | `max_tokens` default; configurable `max_completion_tokens` |
| `stream_usage` | true | true | true default; set false if unsupported |
| `instruction_role` | `system` | `system` default; `developer` when required by selected model | `system` default; `developer` if supported |
| Additional parameters | temperature 0, seed 42, Qwen thinking off | `store=false` | No local Qwen extensions |

`name`, private `api_key`, and optional administrator `system_prompt` complete the connection. Provider keys accept 1-4096 printable ASCII characters with no spaces/control characters, including long project keys. A local compatible server without its own authentication can use a non-secret placeholder key, but PMS authentication and endpoint restrictions still apply. Select a **text Chat Completions model**; model capabilities and entitlement remain provider-specific. Azure uses `api-key` authentication and its approved `/openai/v1` API base. This adapter does not implement Responses-only models, tools, images, realtime audio, or arbitrary custom headers.

For OpenAI, the default `PMS_LLM_ALLOWED_BASE_URLS` is `["https://api.openai.com/v1"]`. Set `PMS_EXTERNAL_CALLS_ENABLED=true` to allow dispatch and status checks. The same deployment flag also governs existing external adapters. Leaving it false permits storing a connection but prevents all new remote calls. Existing completed PMS results can still be read without a remote call.

For a compatible endpoint, include its exact API base in the operator-owned allowlist, for example:

```dotenv
PMS_LLM_ENABLED=true
PMS_EXTERNAL_CALLS_ENABLED=true
PMS_LLM_ALLOWED_BASE_URLS=["https://api.openai.com/v1","https://gateway.example/v1"]
```

These example settings contain no credentials. Restart PMS after changing deployment configuration. Remote destinations require HTTPS and public addresses. Every new socket resolves and validates all DNS answers, then connects to a validated IP while preserving the original hostname for certificate verification, SNI and pooling. Private/link-local/multicast addresses, mixed public/private DNS answers, userinfo, query strings, fragments, encoded/dot paths, redirects and environment proxies are rejected. Private LAN gateways are outside this implementation; expose an explicitly approved public TLS endpoint.

A compatible base URL may not be loopback, private or plain HTTP, even if the allowlist contains it: a platform-executed call only ever leaves for a public destination. A model that runs on the machine asking for the turn is configured as `local_llama_cpp` instead, and that turn is executed by the caller rather than by PMS — see [local execution boundary](../../../docs/local-execution-boundary.md). Local Qwen uses the port allowlist alone (`PMS_LLM_ALLOWED_PORTS=[8787]`), keeps its original root URL, and needs no external-calls flag because no call leaves this service. A compatible base already contains its API path: PMS appends `/chat/completions`, not another `/v1`. Compatible servers must expose `GET <base>/models` with the selected alias for desktop preflight; OpenAI preflight checks `GET /v1/models/{model}`.

`PUT /connections/{id}` is a full replacement, including provider/model/protocol options and `expected_revision`. Preserve all desired fields. Leaving `api_key` out retains the encrypted key only when the provider and normalized base URL are unchanged. A destination/provider change requires a newly supplied key. Updates and credential-master-key rotation increment the revision and revoke in-flight use of the old connection settings.

## Tokens, limits and failures

The PMS login bearer token, audio-service token, and model-provider API key are separate credentials. Only PMS decrypts the provider key, bound by AES-GCM to tenant and connection identity. Database encryption keys remain outside PostgreSQL. Creation/update results, validation errors, audits and upstream error messages are redacted. Human token expiry is checked before dispatch, during generation and before success; the desktop obtains a replacement token through the normal identity workflow and restarts. Provider key rejection gives a controlled error; there is no automatic credential, model or cloud fallback.

The connection's `max_tokens` remains the stable PMS field. For OpenAI it is sent as `max_completion_tokens`, which covers visible output **and reasoning tokens**. A reasoning model may need a higher configured limit to produce visible text. An empty final answer, refusal or filtered response is a controlled failure and is not added to desktop history. A nonempty length-limited answer carries `finish_reason=length`, displayed as truncated. The API never silently increases the limit or resubmits a failed request. This follows the [OpenAI Chat Completions contract](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create).

Returned usage includes known `prompt_tokens`, `completion_tokens`, `total_tokens`, cached prompt tokens and reasoning completion tokens. Details are subsets, not additional charges. OpenAI's final usage-only SSE chunk with empty `choices` is consumed before `[DONE]`. Missing/interrupted usage remains unknown (`null`); PMS does not invent zero or refund capacity based on an incomplete stream. Counts are validated for type, bounds and consistency. Actual billing and model tokenization remain provider-authoritative.

Daily online capacity defaults to **5,000 accepted completion requests** (`PMS_LLM_DAILY_REQUESTS`) and **5,000,000 input + output tokens** (`PMS_LLM_DAILY_TOTAL_TOKENS`) per organization. All users, departments and devices share the organization allowance; local execution is exempt. Either online limit can reject admission. Both reset at 00:00 UTC, using the admission day. A two-call patient turn is one accepted request, but both calls consume tokens. Failed/cancelled/unknown accepted attempts count as requests; admission rejections and idempotent replays do not. The organization row lock serializes admission and settlement.

Running work reserves combined prompt/output capacity: each possible patient call reserves its fitted context bound; plain chat uses the conservative UTF-8 prompt estimate plus output maximum. Successful complete usage replaces the reservation with prompt + completion tokens. Cached/reasoning detail counts are already included. Missing/partial/invalid usage and unsuccessful outcomes retain the reservation; these estimates are not measured billing. Legacy unknown cloud usage is conservatively backfilled; old output reservations remain unchanged for historical evidence. Known legacy local requests are exempt.

Apply migration `0017_llm_total_quota` before restarting services. Replace the obsolete `PMS_LLM_DAILY_OUTPUT_TOKENS` setting with `PMS_LLM_DAILY_TOTAL_TOKENS=5000000`, and set `PMS_LLM_DAILY_REQUESTS=5000` if an existing environment overrides the default. The old output-only setting is no longer enforced. No new runtime grants are needed beyond the current grant bundle. Error codes distinguish `llm_daily_limit` (combined tokens) and `llm_daily_request_limit` (requests); neither is retryable model-busy status. Input remains bounded to 1-13 alternating user/assistant messages, 8,000 characters each, 16,000 total, plus administrator instructions. Character limits are not model token estimates; a context rejection needs a shorter question or Reset. PMS does not silently truncate history.

One generation per normalized endpoint is admitted across workers/tenants, for the platform-executed providers; a local connection is never admitted here and holds no capacity. This is a bounded pilot, not a high-throughput cloud gateway. Concurrent admission is serialized and extra work receives 429 before submission. The overall provider timeout is configurable, default 120 seconds; socket reads honor that deadline, including reasoning pauses. No POST is retried, including 429, timeout, redirect, auth failure, malformed response or unsupported options. Failed/running/cancelled/unknown request keys cannot trigger another submission. The PMS internal request UUID is sent as `X-Client-Request-Id`; it helps correlation, not provider-side idempotency. Use request-status GET to recover a completed answer.

OpenAI receives `store=false`. This does **not** establish Zero Data Retention; provider/account retention rules still apply. PMS does not persist prompt/history, but the bounded answer cache can contain private question details and expires within 24 hours. Run the retention worker. These client/server API boundaries follow the [official authentication guidance](https://developers.openai.com/api/reference/overview).

## Desktop and verification

Run `start/start-human-test.bat` and enroll or reconnect the desktop to its published device assignment. The screen never receives a cloud provider's key or URL. Local model services must already be provisioned and started in Manage Local Models; Human-test connects using the manager's inference-only client credential. Its default 180-second deadline should exceed the PMS 120-second deadline. There are no desktop launch shortcuts in `human-test/`.

Cloud contracts are verified with mocks and isolated PostgreSQL, not paid live OpenAI requests. Native Qwen JSON/SSE is checked separately. See [review evidence](../../../docs/pms-api-reviews.md) and [TODO](../../../docs/pms-api-todo.md). Enabling a real cloud connection requires operator configuration and live acceptance against the selected model; no cloud credential was downloaded, requested or embedded during this implementation.
