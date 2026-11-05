# Phase 6 - Multiple model types and providers

Date: 2026-09-22. Status: implemented as the phase-6 catalog, binding, connection, and profile management contract; new native adapters and live provider checks remain deferred.

This expands phase 6 of the [API management plan](pms-api-management-plan.md). The target is an API that manages multiple model types, providers, deployments, and tenant configurations with consistent permissions and lifecycle rules. One tenant may register several choices for each operation and publish different profiles for different devices or use cases.

## 1. Separate the concepts

| Concept | Meaning | Scope and examples |
|---|---|---|
| Provider | The service/hosting authority selected for execution. | Platform catalog: existing OpenAI, Azure, AWS, and self-hosted/local representations; additional providers can be described without claiming an adapter exists. |
| Adapter | Reviewed application code implementing a particular protocol, service, operation, authentication mode, and result contract. | Release-owned registry. An OpenAI-compatible protocol is not itself a vendor or proof that every OpenAI feature is supported. |
| Model/service definition | What performs an operation: family/version, supported input/output, capability and parameter contracts. | Platform-owned public metadata. Includes service-managed engines where a provider does not expose a selectable model version. Optional publisher metadata is separate from hosting provider. |
| Tenant connection | An organization's authorized provider account/resource, endpoint, region, authentication configuration, and encrypted credentials. | Tenant-private. Reuse existing provider and LLM connection storage and redaction rules. |
| Model binding/deployment | A selectable model/service exposed through one authorized connection and adapter, with its provider model ID or deployment name and configuration revision. | Tenant-owned. Local bindings also declare who executes the model; registering a local name does not prove installation. |
| Profile revision | A published choice of compatible bindings and validated settings for application operations. | Tenant-owned and immutable. An organization/device selects a profile; old runs retain their original snapshots. |

There is no assumption that one model serves every operation, one provider serves every tenant, or a model has exactly one deployment. A model can have multiple input/output capabilities and multiple valid hosting choices. Azure deployment labels, provider model identifiers, local aliases, model publisher, and model version must not be conflated.

These are logical boundaries, not a requirement to introduce six new tables. Existing LLM connections already combine connection and model-binding data. Preserve their IDs and request shapes, projecting them into the new management contract before considering any physical split. Never copy credentials into parallel connection stores.

## 2. Model and operation coverage

| Model/service category | Input -> output | Phase 6 management scope | Execution boundary |
|---|---|---|---|
| Text/conversation LLM | Text -> text | Multiple families, versions, providers, context/output limits, instruction/streaming options, supported reasoning settings. | Preserve current LLM paths; model-specific protocol and capability validation is required. |
| Speech recognition / ASR | Audio -> transcript | Multiple local/cloud models or services, languages, audio formats, duration limits, batch/interactive/streaming modes. | Reuse the implemented speech/job adapters; do not equate a streaming provider protocol with an implemented continuous microphone client. |
| Speech synthesis / TTS | Text -> audio | Voice, locale, format, text limits, sample rate and applicable engine options. | Reuse implemented synthesis adapters. Local companion voices are not automatically PMS synthesis bindings. |
| Video analysis / detection | Video or frames -> labels/events | Service/model identity, clip/frame limits, supported output schema, synchronous/asynchronous mode. | Preserve supported video-analysis jobs and local result contracts; recording video alone is not model analysis. |
| Multimodal / image understanding / OCR | Text/image/document -> structured/text result | First-class modality and operation metadata, parameter validation, availability status. | Catalog/configuration support only until an operation-specific API, adapter, input/media policy, and tests are implemented. |
| Embeddings | Text/image -> vectors | Input kind, dimensions, vector type, normalization/version metadata, batch limits. | No new embedding inference or vector database in this phase. |
| Reranking | Query + candidate items -> ranked scores | Item/count limits, score/output schema and model/version metadata. | No new reranking execution in this phase. |
| Image/video generation | Prompt/reference media -> generated media | Input/output formats, bounded dimensions/duration, job mode, usage unit, lifecycle metadata. | No generation dispatch until dedicated submission/reconciliation, media, quota, and adapter contracts exist. |

The first executable management release covers existing LLM, ASR, TTS, and video operations. Other categories can be represented and queried as catalog entries, with `adapter_not_implemented` or `operation_not_supported` availability. They must not appear as runnable choices in an existing profile slot.

Avoid a single exclusive `model_type` as the complete capability description: use model categories plus explicit supported operations and input/output modalities. A multimodal model may support more than one operation, but each operation needs its own validated contract.

## 3. Provider coverage and honest support reporting

The following baseline was checked in repository source, not inferred from external provider catalogs:

| Current integration area | Existing representation to preserve |
|---|---|
| Direct OpenAI text | `openai` LLM connection and current text-completion adapter. |
| Azure text | `azure_openai` LLM connection with an explicit deployment label. |
| Compatible text endpoints | `openai_compatible`, restricted to approved destinations and explicit protocol options. |
| Local text | `local_llama_cpp` legacy representation and caller-local execution rules; do not interpret API-server loopback as a remote laptop. |
| Azure interactive speech | `azure_openai_whisper`, with the existing bounded transcription paths including the configured realtime-transcription variant. |
| AWS media services | `aws_processing`, with per-operation Transcribe, Polly, and Rekognition paths. |
| Azure media services | `azure_speech` and `azure_video_indexer`, with their current service/authentication restrictions. |
| Local processing | Explicit local profile engines and caller/device result contracts; installed companion software remains a separate operational boundary. |

Provider catalog design must accommodate additional providers such as Anthropic, Google, AWS Bedrock, and other self-hosted runtimes. Those are extension targets, not newly implemented integrations. Native provider protocols require their own adapter; an arbitrary base URL cannot make an unsupported protocol work. New native adapters and new inference operations are separately sized work after the phase 6 management foundation, unless explicitly added to implementation scope.

Expose separate facts rather than a single misleading `supported` flag:

- Catalog state: active, deprecated, retired.
- Adapter implementation: available or unavailable for the requested operation/protocol.
- Tenant configuration: missing, configured, or invalid.
- Access validation: not checked, passed, failed, or stale, bound to connection/binding revisions.
- Sample execution evidence: not run, passed, failed, or unknown, with scope/time and redacted error category.
- Effective availability: selectable/executable plus reason codes after current policy, tenant permissions, connection state, and runtime gates are checked.

An access check does not prove inference, a provider model list does not prove deployment access, and a successful text request does not prove image/audio/tool support.

## 4. Definition and binding fields

Model/service definitions should expose stable ID, display name, description, publisher/family/version where known, categories, operations, input/output modalities, and lifecycle/version fields. Provider-managed services may have no immutable model release ID; record that honestly rather than inventing one.

Operation capabilities include only applicable values: streaming/job modes, structured output/tool-call support, languages, context/output bounds, audio formats/duration, image size/count, frame/clip limits, embedding dimensions, and usage units. Record evidence/source and schema version for capability metadata. Marketing claims or administrator-entered booleans cannot enable a capability that the installed adapter does not implement.

Bindings add tenant connection ID, adapter/protocol, model-definition ID/version or preserved legacy identity, provider deployment/model identifier, region/resource selection, execution owner, supported parameter overrides, version, active/archive state, and validation evidence. Several bindings may reference the same model with different regions, resources, providers, or limits.

Credentials remain only on the owning tenant connection, encrypted with external key material. Non-secret metadata must not smuggle keys into URLs, headers, model options, or arbitrary JSON. Endpoint validation, DNS/address protections, and current local-runtime restrictions remain mandatory; private-network access requires an explicitly reviewed policy.

## 5. Parameter contracts and capability checks

Use common fields where semantics match, with bounded adapter-specific options for real differences. Define schemas in reviewed code and expose read-only parameter descriptions through the API. Do not let administrators upload executable validators, endpoint templates, arbitrary headers, or unrestricted schemas that override adapter safety limits.

| Operation | Parameters to validate |
|---|---|
| Conversation | Context/output allowance, permitted instruction role, temperature/top-p where supported, reasoning choices, stop conditions, structured output/streaming support. |
| ASR | Language/auto-detection, encoding, channels, sample rate, duration/byte limits, timestamps/diarization only if implemented. |
| TTS | Voice-language compatibility, output format/sample rate, character limits, speed/style only where the adapter supports them. |
| Vision/video | Accepted input formats, image/frame counts, resolution, clip duration/frame rate, result schema, job mode. |
| Embeddings/reranking | Dimensions, input/batch length, result shape, normalization/score conventions; remain non-executable until an adapter exists. |

Validate compatibility at definition/binding creation, update, profile publication, activation, and dispatch. Existing run/profile snapshots must not change when catalog metadata is edited. Store the definition/schema version and effective validated settings in new published revisions.

Effective capabilities are the intersection of installed adapter support, model/deployment capabilities, and the allowed application operation. Limits use the applicable platform, tenant, profile, and binding restrictions; do not pretend unlike units can be compared numerically. Unrecognized parameters fail validation rather than being silently ignored. Incompatible options return safe, actionable errors before external submission.

## 6. Profiles and mixed-provider configurations

Keep existing `audio_input`, `conversation`, `audio_output`, and `video` profile sections, their connection references, and old client schemas. Add new operation slots only through a versioned profile/API change once execution exists. A tenant can create many named profiles; a published profile selects one explicit binding for each enabled operation it supports.

Illustrative device-processing configuration:

| Profile operation | Independently selected binding |
|---|---|
| Audio transcription | Tenant Azure speech binding, or a configured local Whisper choice. |
| Conversation | Tenant direct OpenAI/Azure text binding, or the caller-local LLM choice. |
| Speech synthesis | Tenant AWS Polly or Azure Speech binding. |
| Video analysis | Tenant AWS Rekognition or Azure Video Indexer binding. |

This is a configuration example, not a claim that the desktop executes every profile section. The caller/device must support each selected operation and local execution contract. A remote PMS server must never interpret `127.0.0.1` as the user's laptop.

Profiles support draft editing, validation, publication, revision listing, assignment, and rollback by a new revision. Switching takes effect for subsequent authorized work; in-flight work retains its recorded revision and submission state. No automatic provider fallback, load balancing, or replay after an uncertain request is introduced by model management.

Catalog retirement prevents new selections without rewriting old history. Connection deactivation or provider policy disablement blocks applicable new dispatch. Archive operations report authorized dependent profiles/devices and reject unsafe removal; they never cascade-delete published snapshots. Revalidation is required after relevant credential, connection, binding, or capability revision changes.

## 7. API surface and access

All paths are proposed under `/api/v1`; preserve existing connection/profile routes and versions.

| Area | Proposed administration/query surface |
|---|---|
| Provider and adapter metadata | `GET /providers`; `GET /providers/{provider}/capabilities`; platform-only provider policy updates for installed providers. |
| Model definitions | `GET /models`, `GET /models/{id}`; platform `GET/POST /platform/models`, `GET/PATCH/DELETE /platform/models/{id}` with retirement semantics. |
| Tenant configured models | `GET /organizations/{org}/model-bindings`, `GET .../model-bindings/{id}` as a unified authorized projection across existing LLM/media configurations. |
| Binding changes | Type-specific create/update/archive commands reuse existing LLM/provider connection services; add a binding write route only when a separate deployment association is needed. Never introduce two independently editable copies of the same configuration. |
| Validation | Existing connection/status routes retain behavior. New binding validation is operation-specific and reports schema/access/sample stages independently. |
| Profiles | Existing profile CRUD gaps, publish, revisions, model-options, and effective model-config contracts extended compatibly. |

Define an opaque binding ID or typed reference so IDs from different underlying connection resources cannot collide or be confused. The unified read surface is scope-filtered before pagination/counting. Existing active-only selection endpoints remain compatible; management endpoints can include inactive/retired entries for authorized administrators.

Lists support the shared `limit`, `cursor`, `q`, `sort_by`, `sort_order`, and optional scoped `total`. Filters include provider, category, operation, input/output modality, execution mode/owner, adapter availability, active/retired state, and current validation state. Search permitted display names, model IDs, deployment labels, and descriptions; never search credentials.

Platform admins manage public definitions and platform availability. Organization admins manage their connections/bindings/profiles. Non-admin users receive only the permitted selectable summaries. A platform administrator without tenant membership cannot inspect tenant model credentials or obtain tenant processing/media access.

## 8. Adapter contract and provider expansion

Inventory installed adapters and define a small common capability interface around them: supported operations/protocol versions/auth modes; configuration validation; access checking; request translation; bounded dispatch/stream/job handling; result/usage/error normalization; and cancellation/reconciliation where the provider operation supports it. Preserve existing implementations behind that interface rather than rewrite the worker or inference pipeline.

Retain provider-specific differences, including explicit unsupported capabilities, unknown usage, asynchronous job IDs, uncertain submission, and partial/failed streaming. Do not claim cancellation prevented billing unless the provider outcome confirms it. Existing worker leases, idempotency keys, tenant quotas, private media rules, and no-blind-retry behavior still apply.

A new provider/operation is enabled only after its adapter, schemas, authentication, endpoint policy, usage accounting, errors, permission checks, and mocked contract tests exist. Catalog metadata may be added earlier but remains non-executable. Discovery/import is optional, explicitly initiated by an authorized administrator, bounded, and a draft-review step; do not fetch every provider catalog automatically or auto-enable imported entries.

Live access checks or samples contact external services and remain deferred in this planning increment. An API can describe and mock-test these operations without running them now. Future sample execution must be explicit, bounded, scoped, idempotent, and quota-accounted; unknown outcomes are inspected rather than replayed.

## 9. Usage, migration, and performance

Retain authoritative usage in the existing processing/LLM/speech records; expose compatible administrative summaries without creating a second billing ledger. Usage units remain typed: input/output tokens, audio/video seconds, synthesized characters, requests, and future operation-specific units. Unknown usage is not zero. No automatic currency conversion or invented pricing/cost estimates are introduced.

Implement forward migrations for the minimal provider/model metadata and binding associations that are actually needed. Preserve current `LLMConnection`/`ProviderConnection` IDs, encrypted secrets, revision behavior, published profile snapshots, and model aliases. Map existing provider literals through explicit compatibility mappings; update their SQL constraints, API schemas, policy checks, and tests together. Backfill only unambiguous model identities and retain unresolved legacy entries with clear status.

Index tenant/provider/operation/lifecycle queries based on representative query plans. Keep catalog imports, list counts, option payloads, validation requests, and logs bounded. Model metadata and secrets must not be copied into every heartbeat or inference request.

## 10. Phase 6 delivery steps

| Step | Deliverable | Exit evidence |
|---|---|---|
| 6.1 Inventory and contracts | Model categories/operations, provider/adapter matrix, capability/status schemas, current-client contracts. | Every currently represented provider/engine mapped; unsupported operations remain explicit. |
| 6.2 Catalog and lifecycle | Minimal provider/model metadata, CRUD/retirement, parameter descriptions, public versus administrative views. | Permissions, duplicate identities, modality/operation validation, and lifecycle tests. |
| 6.3 Tenant connections and bindings | Complete existing connection administration and unified configured-model reads; multiple bindings per tenant/type. | Tenant isolation, secret redaction, revision checks, same-model multiple-deployment cases, and current-client compatibility. |
| 6.4 Parameter and access validation | Typed per-operation validation; schema/access/sample evidence tied to current revisions; adapter interface around existing implementations. | Incompatible parameters, stale evidence, unauthorized endpoints, and unsupported protocols fail safely. |
| 6.5 Profiles and routing | Independent operation selections, mixed-provider profiles, immutable publication, assignment, and revision-based rollback. | Existing runs unchanged; new operations selectable only when implemented; no automatic fallback or replay. |
| 6.6 Queries and operational visibility | Shared paging/search/filter/sort, effective availability reasons, dependency views, and existing usage summaries. | Scoped totals and cross-provider queries; bounded pagination; secrets absent from discovery/status/audit. |
| 6.7 Upgrade and compatibility | Forward migration/backfill, explicit legacy mapping, preserved connection/profile APIs. | Upgrade populated databases; preserve IDs, ciphertext, profiles, and effective configuration. |
| 6.8 Integrated review | Full mocked operation/provider matrix, permission/lifecycle/concurrency checks, documentation and final review. | Required backend checks pass; live/hardware verification and unimplemented adapters are reported separately. |

## 11. Acceptance scenarios

- One organization configures multiple text choices across the existing provider paths, two speech choices, and independent synthesis/video services. Another organization cannot list, validate, modify, or use those bindings.
- The same logical model is represented by two distinct deployments with different names/regions/limits; changing one does not mutate the other or a published run snapshot.
- A mixed-provider profile validates each operation independently. A working text connection cannot authorize speech/video and does not claim tool or vision capability.
- A catalogued embedding or image-generation model with no installed adapter remains visible only as permitted metadata and cannot be published into an executable slot.
- A local choice is reported as configured with installation/execution evidence unknown unless a trusted runtime contract supplies it; PMS does not remotely install or start a model.
- Credential rotation invalidates relevant access evidence. Provider disablement, connection deactivation, and catalog retirement have their documented distinct effects.
- Invalid parameter combinations, stale revisions, same-ID resource confusion, unauthorized endpoints, cross-tenant references, and unsafe archive all fail before dispatch.
- Search/filter/sort/counts work across model categories/providers without losing tenant boundaries; secret values never appear in responses or audit.
- Existing speech/LLM/profile/device clients and populated upgrade fixtures continue to work. Timeouts and unknown provider submissions do not trigger automatic fallback or duplicate work.

Planning evidence: inspected `modules/configuration.py`, `modules/llm_schemas.py`, `modules/model_routing.py`, `integrations/llm/capabilities.py`, `integrations/llm/policy.py`, existing media/speech adapters, and the cloud-model contract documentation. This task adds documentation only; it does not claim new adapters, model execution, provider access, or live verification.
