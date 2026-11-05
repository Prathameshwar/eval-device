# Models and device configuration

Models are configured once, then selected directly on a device. The web flow has no processing profile, separate provider connection, publish, binding, or connection-test step. This document supersedes the earlier model workspace design.

## Models page

Use **Add LLM**, **Add audio**, or **Add video**. Audio offers speech recognition or speech output. Choose Local or Cloud, give the model a name, and enter only the fields needed by that model type and provider. Existing models have Edit and Delete actions. Search, type, location, and status filters are available; rows show type, Local/Cloud, inactive status, and tenant scope when applicable.

Local models need a name and a supported model selection. They do not need an endpoint or credentials. Adding a local model does not download or install it. Speech models have optional language/voice preferences. Cloud models contain their own provider settings and encrypted credentials. Blank credential fields on edit retain the saved secret; endpoint or authentication changes require appropriate fresh credentials. Type, provider, and location are fixed when editing; create a separate model to change them.

| Type | Local options | Cloud providers/services |
| --- | --- | --- |
| Conversation LLM | Qwen3 4B, Qwen3 1.7B, Qwen3.5 4B, QwenMedic v1 aliases | OpenAI, Azure OpenAI, Anthropic, OpenAI compatible |
| Speech recognition | Whisper tiny/base/small/medium/large-v3/large-v3-turbo and Whisper Medical v1 aliases | Azure OpenAI Whisper, Azure Speech, Amazon Transcribe |
| Speech output | eSpeak NG | Azure Speech, Amazon Polly |
| Video analysis | OpenCV motion | Amazon Rekognition, Azure Video Indexer |

The video options analyze video or motion; they do not generate videos. Cloud LLM model IDs/deployments are entered for the configured provider. Fresh deployment seeds exactly three active Models page entries: **Whisper large-v3**, **qwen3.5-4b-local**, and **eSpeak NG**. Other supported options in the table remain available through Add model. Local availability is determined separately for each device; these database defaults do not download, install, load or assign device runtimes.

Migration **0039_default_local_models** archives the earlier unused starter entries with atomic audit records. Existing administrator edits, tenant models, models with recorded usage and device assignments are preserved. Archived or disabled defaults stay that way; repeated initialization/deployment does not duplicate or restore them. Existing deployments can therefore retain additional configured models. The migration preserves historical catalog/configuration records and does not change runtime grants.

Saving does not call a cloud provider and does not certify provider availability. LLM endpoints remain subject to the API endpoint allowlist and external-call policy. Media provider enablement, quotas, permissions, and runtime checks remain enforced. No provider key is returned to the browser or device.

## Devices page

Open a device's action menu and choose **Configure model**. The popup remains on `/devices` and contains:

1. One **Local / Cloud** switch for the device.
2. Four optional selections: Conversation, Speech recognition, Speech output, and Video analysis.
3. **Save** and Cancel. Choose **None** for unused capabilities.

Options list active, configured models matching the selected mode, type and tenant scope. Models can be assigned before device enrollment or runtime installation, including on manikins; a missing or stale inventory report does not hide them or block saving. Cloud models become selectable as soon as they are configured and active. Inactive models cannot be selected and archived models are omitted. An empty dropdown means no active model of that type/mode is configured for the device's tenant.

Assignment does not certify execution readiness. Install and run local models on the device or its connected laptop before use; cloud execution still requires enabled providers, credentials and runtime policy checks. The launcher reports installed aliases through `POST /api/v1/device/local-models` using its device credential, independently of assignment. The API does not inspect laptop files or install models.

Inventory reporting and platform inventory inspection support manikin and laptop registrations. Human-test reports the models installed on its host for the device it enrolled as; the device type does not restrict reporting. Reports still require an active enrolled device credential matching the submitted device ID, and only supported model aliases are accepted.

Save updates all four selections atomically. Device and model versions reject stale edits. Failed saves retain the draft; an uncertain network result requires reload before retry. Cancel protects unsaved edits. Device registration itself no longer asks for model/profile configuration.

Migrated mixed Local/Cloud configurations retain their exact settings. The popup asks the operator to choose Local or Cloud before changing such a configuration. Disabled/retired devices and inactive tenants/departments cannot receive new selections.

## API and storage

In the platform device list, devices with no selected model show **Configure Model** immediately after **View**, a subtle gray row, and **Model required**. Saving a selection refreshes the list. Existing management permissions and inactive/retired device restrictions still apply. Platform device summaries expose only a `models_configured` boolean for this indicator; a saved mode with all four model selections cleared is still unconfigured.

- `GET/POST /api/v1/platform/runtime-models`: list or create typed models.
- `PUT/DELETE /api/v1/platform/runtime-models/{id}`: edit with `expected_revision`, or archive an unused model. Delete uses the revision query parameter.
- `GET/PUT /api/v1/platform/devices/{id}/models`: eligible choices/current selection, or an atomic save with `expected_version` and selected `model_revisions`.

Only Platform Admin manages models and device assignments. Model management requires platform settings management permission; device configuration requires platform organization management permission. A platform administrator does not thereby gain tenant execution or media access. New models are shared platform configurations; migrated tenant models remain restricted to their original tenant. Runtime requests still require the caller's authorized, active device/tenant context. A shared cloud model cannot be called directly without its assigned device route.

`runtime_models` owns type, execution location, provider settings, defaults, encrypted credentials, revision and lifecycle. `device_model_selections` owns four model IDs, execution mode, version and its immutable execution snapshot reference. Model edits refresh affected device snapshots atomically while retaining previous snapshots and capture/policy limits. Selected models cannot be deleted while assigned to a non-retired device.

Migration **0037_direct_device_models** consolidates existing configurations and flattens effective device assignments, including tenant defaults. It preserves credential encryption context and exact initial execution settings. It drops the physical `platform_model_connections` and `media_model_configs` tables after migration and replaces them with read-only compatibility views. Migration **0038_retire_model_setup** removes the old device and organization profile assignment columns after preserving their provenance. Legacy connection/profile management APIs and tenant model pickers are removed. Original configuration records remain immutable for historical foreign keys; triggers and runtime grants block edits. Immutable execution revisions retain internal wire identifiers for runtime compatibility. Legacy web URLs redirect to Models. The desktop only loads assigned models; it cannot change or publish them.

Apply migration head and reapply `platform/api/deploy/grant-runtime-access.sql` before starting this API/worker/web version. Only the API role manages the new records. Workers can read media models and update last-use metadata, but cannot read LLM model credentials; retention has no model-credential access. The migration is forward-only; use a backup for rollback. Source changes do not migrate an application database automatically.

## Runtime compatibility and verification

Device configuration, LLM requests, patient conversations, interactive speech, local turns, and media workers resolve the canonical models. Older clients still receive immutable revision IDs through existing wire field names. Interactive desktop recording supports local Whisper and Azure OpenAI Whisper; other ASR services run through the media processing API. A device without speech recognition can still use typed conversation input.

See [the implementation checklist](direct-models-todo.md) and [reconciliation and review evidence](direct-models-review.md). Verification uses disposable PostgreSQL, mocked provider calls, and a local authenticated browser. Live cloud integration, application database rollout, hosted deployment, and hardware verification are separate work.
