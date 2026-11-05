# Local and cloud speech and patient models

The PMS published processing profile is authoritative. Audio transcription and
the conversation LLM are independent selections. Local Whisper/Qwen remain
supported, including automatic Whisper GPU selection in the combined launcher.
Video still receives and records independently; this feature adds no video model.

## Choose and switch configured online models

In Human-test, open **Models → Cloud**, select the speech and patient-response
connections, then **Check, save & activate models**. Each choice shows its connection
name, provider and actual model/deployment. Use **Custom** for one local and one
online service. Cloud models are configured PMS connections, not downloadable
weights or an unrestricted list of every model advertised by a provider. Provision
one connection per desired deployment/model with its own protocol/capability options.
After provisioning through the APIs below, **Refresh models** discovers the choices.

Activation checks the current operator gates and provider access, checks that the
connection revisions still match the displayed choices, publishes the profile and
applies it to the next question. Online-to-online switching needs no restart.
Changing operator environment gates/endpoint allowlists requires a PMS restart.
Human-test retains its active selection if checks fail, resets conversation history
after a successful switch and blocks repeat saves after an uncertain publication
until settings are refreshed. It sends no audio or completion during access checks;
Azure API access does not prove that the selected deployment can perform inference.

| Capability | Configured online choices | Where selection is used |
|---|---|---|
| Interactive microphone transcription | Azure OpenAI Whisper or GPT Realtime Whisper deployment | Human-test Models and PMS interactive speech API |
| Patient response | OpenAI, Azure OpenAI deployment, OpenAI-compatible Chat Completions endpoint | Human-test Models; JSON and streaming results |
| Job-based transcription | AWS Transcribe, Azure Speech | PMS processing profile `audio_input` and device jobs; not the desktop conversation loop |
| Video analysis | AWS Rekognition, Azure Video Indexer | PMS processing profile `video` and explicit `video.labels` jobs |
| Speech synthesis | AWS Polly, Azure Speech | PMS processing profile `audio_output` and explicit `audio.synthesize` jobs |
| Video recording / desktop spoken answers | Local video receiver / local Piper | No cloud model is selected by the speech/LLM dropdowns |

Direct OpenAI speech transcription, conversational realtime audio and vision LLMs are not adapters
in this release. Do not substitute their IDs into the Whisper connection. Video
remains receive/record/save in this demo; choosing online speech or an online LLM
does not upload video, enable detection, or replace the local spoken-answer voice.

The [Azure Realtime Whisper adapter and live checks](simulations/azure-realtime-whisper/README.md)
verify `gpt-realtime-whisper` with the existing resource key. It is a separate
selectable speech connection using a transcription session over WebSocket. The
desktop still submits completed recordings; live microphone captions and
persistent sessions across questions are not part of this integration.

All following paths are under `/api/v1/organizations/{organization_id}`:

1. Create each LLM using `POST /llm/connections`; set its `provider`, approved
   `base_url`, model/deployment, encrypted `api_key` and `model_options`. Check
   `GET /llm/connections/{id}/status`. Update via revision-checked `PUT`.
2. Create speech/video/output services using `POST /connections`. Store credentials
   only in the request's encrypted credential fields. Check each required operation
   using `POST /connections/{id}/validate` with `sample: false`.
3. Speech/LLM selections use `POST /model-profiles`. The desktop supplies
   `activate: true`, `expected_llm_revision`, `expected_speech_revision` when cloud
   speech is chosen, and the selected profile's `expected_revision_id`. The server
   locks/checks connection revisions, rechecks activation gates, validates the
   profile and atomically publishes with its audit record. Configuration-only API
   callers retain the existing `activate: false` default.
4. Platform video/output and job-based transcription use `POST /profiles` or
   `PATCH /profiles/{id}` with their section settings and corresponding
   `draft_*_connection_id`, then `POST /profiles/{id}/publish` with the current
   revision. Assign the profile to the intended device or organization. Device
   configuration returns its new desired revision; existing runs retain their
   original snapshots. Changing speech/LLM choices preserves these media sections.

`GET /model-options` separates interactive `speech`/`llm` choices from
`platform_services`, includes connection revisions and operator availability, and
never returns credentials or provider endpoints. `GET /model-config` includes the
selected `platform_media` sections for visibility; these do not activate desktop
media processing. All endpoints retain organization/role/lifecycle authorization.

Verification and limitations: [online switching audit](online-model-switching-review.md).

## Configuration and startup

The central API owns all application data, provider credentials and operator policy. Apply the current migration/grants following [API setup](../platform/api/README.md). Start `start/start-platform.bat` before `start/start-human-test.bat`, or connect Human-test to an already running API with `HUMAN_PMS_URL`.

Set the authenticated `HUMAN_PMS_TOKEN`, tenant `HUMAN_ORGANIZATION_ID`, and optionally `HUMAN_PROCESSING_PROFILE_ID` in `human-test/.env`. The selected published profile determines which local engines run. The launcher never creates an API, database, tenant, administrator or replacement profile. `--processing-mode` is accepted only for compatibility and ignored; `PMS_PROCESSING_MODE` belongs to the backend. `--check` checks configured access/readiness without inference and stops owned companions.

An existing launcher is reused only after verifying its API, tenant, login/department and current profile/revision/configuration hash. Renewed credentials require a new desktop session. Close that window or reload Models when these differ. See [client/API boundary](human-test-api-boundary.md).

The following `PMS_*` settings belong to the **central API environment**, never a Human-test environment:

| Setting | Default / meaning |
|---|---|
| `PMS_EXTERNAL_CALLS_ENABLED` | `false`; operator gate for every cloud dispatch |
| `PMS_PROCESSING_MODE` | `local`; backend processing default |
| `PMS_LLM_ENABLED` | Enable API LLM connections/calls on the backend |
| `PMS_SPEECH_ENABLED` | `false`; enable interactive cloud speech on the backend |
| `PMS_LLM_ALLOWED_BASE_URLS` | Exact approved HTTPS API bases; shared by cloud speech and LLM |
| `PMS_LLM_CLOUD_CONCURRENCY` | 4 active cloud LLM calls per API endpoint; a local model is executed by the caller and takes no slot |
| `PMS_PATIENT_REMOTE_CONTEXT_TOKENS` | Legacy fallback; prefer per-connection `model_options.context_tokens` |
| `PMS_SPEECH_MAX_SECONDS` | 30; server/operator maximum, tightened by published/tenant policy |
| `PMS_SPEECH_DAILY_SECONDS` | 3600; additionally bounded by shared tenant daily audio policy |
| `PMS_SPEECH_CONCURRENCY` | 2; additionally bounded by shared organization job policy |
| `PMS_SPEECH_RECORDING_MAX_BYTES` | 100 MB per organization, including pending cleanup |
| `PMS_SPEECH_RETENTION_DAYS` | 7; tightened by tenant/platform/profile media retention |
| `HUMAN_USE_PMS_MODELS` | `true` in the combined launcher; standalone legacy clients remain compatible |

The launcher checks the running central API first, resolves its published profile, then starts only the required local engines. Cloud-only speech/response needs no local ASR/LLM weights or CUDA environment. The optional video receiver still needs its environment. Supervision restarts only owned local companions; API outages are reported without starting a private replacement. Backend credentials are removed from child environments, and local engines also receive no desktop token.

## Cloud connection provisioning

Use the existing authorized PMS connection APIs to provision encrypted keys.
Azure must also be enabled in **platform settings** for Azure speech and LLMs; the operator
cloud environment gate alone does not override that platform policy. Bootstrap
a platform administrator through the documented deployment command if this is a
fresh installation. Organization administrators manage their own connections.

Create and rotate credentials through the platform web UI or authenticated central API connection endpoints. Publish the profile there, assigning it as the tenant default or selecting its UUID in Human-test. Provider keys are encrypted in the platform database and never returned to the desktop. The API's operator must explicitly enable external calls and the relevant providers.

Human-test no longer reads `start/cloud-models.json` or `PMS_BOOTSTRAP_LLM_API_KEY` / `PMS_BOOTSTRAP_SPEECH_API_KEY`. Existing private files are left untouched; they have no effect on startup. For mixed operation, publish a profile combining local speech with a cloud LLM, or cloud speech with a local LLM.

TLS certificate and hostname verification remain required. The LLM transport trusts
both its bundled public roots and the operating system certificate store, including
operator-managed Windows trust roots. Public HTTPS destinations are validated and
DNS-pinned. The current transport intentionally does not support HTTP proxies or
Azure Private Link addresses; those require separately reviewed network policy.


### Azure Whisper with a dated API version

Speech connections can optionally set `api_version`, for example `2024-06-01`.
Keep `endpoint` as the allowlisted resource base `https://RESOURCE.openai.azure.com/openai/v1`
and `deployment` as the deployment name. PMS then sends the multipart WAV to
`/openai/deployments/DEPLOYMENT/audio/transcriptions?api-version=2024-06-01`.
Omit `api_version` to retain the existing v1 route. The version must be a bounded
`YYYY-MM-DD` or `YYYY-MM-DD-preview` string; Azure decides which versions are
supported. There is no automatic route fallback. The provider adapter never
replays a POST; the desktop may make a new bounded attempt after an explicit busy
rejection, as described below.

Transcription preserves the input language. The separate `audio/translations`
route returns English and is not used by Human-test. This follows the
[Azure transcription quickstart](https://learn.microsoft.com/en-us/azure/foundry/openai/whisper-quickstart)
and [audio API reference](https://learn.microsoft.com/en-us/azure/foundry/openai/reference-preview-latest).
Azure catalog access checks permit up to 1 MiB of model metadata; completion and
transcription responses retain their existing smaller limits. Catalog access does
not prove deployment inference. Speech readiness snapshots identity before releasing
the database transaction and reloads authorization after the provider check.

## Model parameters

An Azure connection's `model` is its **deployment name**. `model_family` describes
the underlying model, not that arbitrary deployment label.

```json
{
  "model_family": "gpt_5_reasoning",
  "context_tokens": 8192,
  "reasoning_effort": "none",
  "patient_answer_mode": "authored"
}
```

For a supported GPT-5.6 deployment this is a low-latency starting configuration;
verify quality on representative cases. Reasoning profiles reject temperature
and require `max_completion_tokens`. GPT-4.1 profiles can configure temperature
and omit reasoning effort. Generic compatible connections preserve their explicit
token parameter and streaming-usage choices. Local model parameters remain under
the local server's existing configuration.

PMS continues using Chat Completions for the current text-only workflow. Responses,
tools, Entra identity/token refresh and real-time cloud audio sessions are not
required by this increment and are not implemented. Azure v1 access readiness
checks verify authenticated API access; they **do not prove deployment inference**
or generate paid sample requests. A connection validation with `sample=true` is
an explicit paid Whisper sample; routine setup uses `sample=false`.

In patient practice, PMS supplies the selected case's permitted context. A routing
call chooses topics. `authored` returns the saved bilingual answer without a second
call; `generated` retains the wording call and its length/number guard for narrative
or combined topics. A single exact attribute (name, age, sex, body size or vital
reading) uses its authored answer immediately after routing in either mode.
That guard is not a complete semantic or clinical fact validator. Existing local
connections retain generated behavior; the cloud example explicitly selects authored.
Both calls are separately budgeted, their usage is aggregated, and missing provider
usage stays unknown. Reasoning tokens are part of completion usage, not an extra
quantity to add a second time. Quotas conservatively charge reservations.

## APIs and client behavior

All organization paths below start with `/api/v1/organizations/{organization_id}`.

| Method/path | Purpose |
|---|---|
| `GET /model-options` | Permitted profile/connection choices; no provider secrets |
| `GET /model-config?profile_id=...` | Effective model routes, limits and configuration hash |
| `POST /model-profiles` | Authorized, version-checked publish of speech/LLM selections; optionally set organization default |
| `GET /speech/status?profile_id=...` | Cloud speech access check |
| `POST /speech/transcriptions` | Interactive WAV transcription |
| `GET /speech/requests/{request_key}` | Request/result/recording status; never resubmits |
| `GET /speech/requests/{request_key}/audio` | Authorized private recording download |
| Existing `/llm/connections` and `/llm/completions` | LLM configuration and JSON/SSE answers |

Speech submission uses `Content-Type: audio/wav` with mono 16 kHz PCM16 WAV as the
raw body. Query parameters: UUID `request_key`, `profile_revision_id`,
`configuration_hash`, and `language=en|hi|auto`. The server checks duration, bytes,
format, organization quotas and configuration before dispatch. The same key and
same utterance returns the existing status/result; different content gets 409.
Do not automatically generate another key after a timeout or disconnect.

Human-test obtains the active route from PMS, buffers only one bounded utterance
for cloud speech and retains local WebSocket streaming for local speech. The
Models window shows the actual provider/model, permits published-profile selection,
and allows organization administrators to publish changes. Changing selections
clears conversation history and is blocked during an active question. The local
audio token is required only for local speech. Server revision/hash checks reject
configuration changes during a turn. Short readiness caching avoids a cloud model
catalog round trip before every continuous-microphone utterance.
Model selection preserves published capture language/duration and refuses to publish
unrelated draft edits. Review and publish such drafts through the normal profile API
before saving model choices. Switching profiles recomputes the recording limit while
retaining the client's own maximum.

Cloud audio is written concurrently with transcription. The transcript response
does not wait for disk completion; `recording_status` is `pending`, `saved` or
`failed`. The transcript is retained in the authorized request record. Audio and
results expire together according to the stricter policy. Cleanup also reclaims
unknown/failed requests. No recordings or transcript text enter operational logs.
Expired recording leases are recovered after a restart without replaying cloud
requests. Daily speech allowance uses durable audit duration metadata so early
media deletion does not restore consumed quota. Filesystem permission setup runs
off the async loop; the transcription response does not await recording completion.

Devices can fetch their assigned effective route and submit cloud speech directly
to PMS using their enrolled credential. Human-test uses its staff identity.
Physical Pi capture/playback and its complete conversation client remain the
separate hardware integration; this release does not claim that verification.

## Flow and verification boundaries

```text
Microphone -> end-of-utterance detection
  local -> laptop Audio API -> resident Whisper GPU/CPU -> text
  cloud -> PMS speech API -> Azure OpenAI Whisper -> text
                                               +-> private recording (concurrent)
Text -> PMS publishes the case, persona, language and model selection
  cloud -> PMS calls the selected Azure/OpenAI LLM -> validated answer -> Human-test
  local -> Human-test calls the laptop's own model -> validated answer, spoken here
                                               +-> metadata-only PMS local-turn record
```

A local model runs on the machine that asks for the turn, so PMS is not on that
inference path. When `HUMAN_HISTORY_ENABLED=true`, the bounded local outbox separately uploads transcript/answer history to that same central API. Both paths use the shared conversation pipeline. See
[local execution boundary](local-execution-boundary.md).

Startup retries and paid inference retries are different. Unknown external
submissions are not automatically replayed and there is no implicit cross-provider
fallback. API errors distinguish invalid configuration, input limits, permissions,
capacity and unknown outcomes. The UI can recover completed results by request key.

Human-test retains one bounded utterance in memory while a stage is busy. Explicit
`speech_busy`, `llm_busy` and `concurrency_limit` rejections allow cloud speech to
retry in ten rounds of five retries. Each round waits 1, 2, 3, 4 and 5 seconds,
with an additional three-second pause between rounds: 50 retries plus one initial
submission, or 51 submissions maximum. The same WAV is retained across all rounds.
These defaults are controlled by `HUMAN_SPEECH_RETRY_ROUNDS` (1–10) and
`HUMAN_SPEECH_RETRY_ROUND_PAUSE_SECONDS` (0–60). Exhaustion adds 177 seconds of
scheduled waits, plus request time. Local/cloud response models still allow five
retries after 1, 2, 3, 4 and 5 seconds (six submissions maximum). Only
the rejected stage repeats: a completed transcription is reused when the response
model is busy. Each definite rejection
gets a new attempt key because an admitted failed request retains its failed result.
There is no retry after partial response delivery, transport interruption, timeout,
invalid configuration, authorization failure or exhausted daily quota. The microphone
closes before the first upload; its WAV and speech parameters remain unchanged for
each retry. Listening and speaking stay paused during waits and retry requests.
The window shows the speech round, retry and waiting/in-progress status, including
the pause between rounds, in a centered bordered panel with an animated clock,
live countdown and elapsed waiting time. **Cancel queued question** cancels the active turn during
requests or any wait. A successful answer is spoken once before continuous
listening resumes; exhaustion returns to **Start microphone**. A cloud catalog
busy response permits capture; submission still rechecks
authentication, the selected profile, policy and capacity. Local capture readiness
checks remain required.

Other failed turns no longer end a microphone session. A bordered warning keeps
the failure visible, and fresh capture resumes after three seconds. Unknown
submissions are not replayed; their recovery key remains available after a later
successful question. Only manual pause/cancel/close and the existing busy-retry
exhaustion policy turn listening off. A display backlog cannot discard the
terminal event and leave the interface locked. The repeatable native regression
and saved results are described in [continuous listening](simulations/continuous-listening/README.md).

Startup now distinguishes failed cloud readiness probes from invalid credentials,
configuration, policy or patient-setup access. After five temporary cloud probe
failures, it opens with a named warning rather than shutting down its services.
Each question still performs its normal access/admission checks. Diagnostics show
the failed stage and a safe error code without raw provider responses.

**Azure Whisper audio** and **Azure GPT Realtime Whisper** are separate choices in
Models. Realtime uses a bounded WebSocket transcription session through PMS after
the question is recorded; it does not yet stream microphone captions live.
Both retain the same quota, private recording and access controls. See the
[configuration and live adapter evidence](simulations/azure-realtime-whisper/README.md#selectable-app-integration-2026-09-20).

Compatible LLMs can return inconsistent optional usage breakdowns. A reasoning or
cached-token count above its parent total is omitted; valid totals and completed
text remain usable. Totals must still be bounded integers with a consistent sum;
malformed breakdown values remain errors. Missing counts are unknown, never zero.
Cached speech submissions recheck the original department's access just like GET
status/media routes, and new conversations clear both speech and response recovery keys.

Verification uses a disposable PostgreSQL server and mocked provider transports.
Real Azure/OpenAI deployment compatibility, speech quality, account quotas and
network latency require explicitly authorized live tests. Measure speech-end,
upload/ASR, routing, wording and visible-answer times separately; cloud is not
assumed faster than an already warm local GPU.

Protocol references: [Azure v1](https://learn.microsoft.com/en-us/azure/foundry/openai/api-version-lifecycle),
[Azure transcription](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/transcribe-overview),
[OpenAI GPT-4.1](https://developers.openai.com/api/docs/models/gpt-4.1),
[OpenAI GPT-5.6](https://developers.openai.com/api/docs/models/gpt-5.6-sol).

Current Azure Whisper/Nemotron verification and busy handling:
[final speech and response review](online-speech-response-final-review.md).

### Organization daily online allowance

Online LLM completion requests share organization-wide defaults of 5,000 requests and 5,000,000 combined input/output tokens per UTC day. Both calls in a generated patient answer consume tokens. Local model turns are exempt. Configure `PMS_LLM_DAILY_REQUESTS` and `PMS_LLM_DAILY_TOTAL_TOKENS`; the previous output-only setting is obsolete. See [settlement, conservative reservations and upgrade](../platform/api/deploy/llm-providers.md). Speech audio-duration limits and upstream provider throttling are separate from this LLM allowance.
