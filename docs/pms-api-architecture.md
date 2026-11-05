# PMS API architecture and delivery phases

Implementation lives in `platform/api`. PostgreSQL 17 remains the source of truth. This is one FastAPI service and separately launched processing/retention workers, sharing SQLAlchemy mappings and reviewed Alembic migrations. The Raspberry Pi runs the audio/video hardware agent. The local direction uses the standalone laptop receiver in `device/audio-process` for OSS speech transcription; its platform integration remains future work, and cloud mode uses Pi-to-platform API requests without a laptop relay. A laptop may still use the device HTTP contract as a development substitute.

## Confirmed decisions

- Provider credentials are encrypted in PostgreSQL using AES-256-GCM. Key IDs accompany ciphertext; independently managed encryption keys stay outside the database. No provider credential is returned to a device or normal API response.
- Live OIDC, AWS, Azure and hosted deployment verification are deferred by the user. External provider calls default to disabled. Local PostgreSQL tests and mocked provider contract tests remain part of delivery.
- Devices optionally select a preferred language. The platform catalog starts with English (`en`, speech locale `en-IN`) and Hindi (`hi`, `hi-IN`). An unset or inactive preference resolves to English. A profile's explicit speech language overrides the device preference. Platform administrators can add language choices and deactivate them; English remains active and selected codes cannot be removed.
- No additional language table, separate queue database, custom-role editor, child/guardian records, billing system, or streaming endpoint is introduced in the PMS API. The separate [local audio receiver](../device/audio-process/README.md) runs independently, with no PMS/server connection.

## Confirmed device execution direction

The [service plan, section 7.1](platform-service-plan.md#71-how-the-raspberry-pi-will-work) defines the Pi/laptop split confirmed on 2026-09-17:

- **Pi hardware:** microphone/camera input and speaker/video-display output in both modes. Video/display output remains to be implemented and does not imply an existing video-generation or video-playback API.
- **Local speech-to-text:** Pi audio goes over local Wi-Fi to a Windows laptop with 16 GB RAM. The laptop runs a configurable installed OSS model on CPU and returns transcript text to the Pi. Whisper `large-v3` INT8 is a candidate, with `large-v3-turbo` and smaller multilingual models available for evaluation; selection depends on measured Hindi/English accuracy and processing delay, including mixed speech. The standalone receiver defaults to configurable `large-v3` CPU INT8; this does not enable an engine in PMS.
- **Cloud processing:** the Pi calls the platform API directly; the platform worker calls the configured provider and makes authorized results/media available to the Pi. The laptop is unnecessary in this path. Provider credentials remain encrypted server-side; API-issued media access preserves the existing upload/download workflow.
- **Identity and policy:** the companion serves the Pi's logical device; the Pi remains responsible for platform authentication, scoped run/result reporting and output acknowledgment. A separate authenticated/encrypted local session must preserve device/configuration binding, lifecycle restrictions, bounded buffers, retention and offline expiry. Do not copy the Pi's platform bearer credential to the laptop or silently fall back to cloud when local processing is unavailable.

The standalone receiver accepts bounded PCM16 streams, loads/warms one model at startup, prints text to console and returns transcript events. Private background recording saves input WAV and UTF-8 transcript events with a 1 GB/1,000-session cap and seven-day retention. An independent bounded writer reports incomplete recordings on overload/storage failure; transcription does not wait for disk. Safe transient I/O uses bounded retries at fixed file offsets; failed audio can fall back to transcript-only storage within the same limits. Recording status is scoped to the authenticated local client and distinguishes finalization and per-component completeness. Callback retries are limited to failures before submission. Its optional callback is unset; no PMS endpoint is selected or invoked. Local client tokens belong to one trusted installation and do not implement PMS tenant/lifecycle authorization. Add the platform bridge, model registry and validated configuration/capability extensions before advertising platform-integrated local transcription. The current API has no local transcription engine or video-display operation. Keep audio/video runs independent and preserve current quotas, tenant boundaries, idempotency and worker fencing. Video analysis and speech synthesis remain independently configured; this decision assigns speech transcription to the laptop without relocating every processor.

## Phase plan and implementation contract

| Phase | Deliverable | Acceptance evidence |
|---|---|---|
| 1 | `pms_api` package, modules, dependency lock, architecture and TODO | Importable package; documented boundaries and decisions |
| 2 | Settings, lifespan, structured logs, request IDs, safe errors, health and metrics | Validated deployment configuration; database/version readiness; no request bodies or raw provider errors in logs |
| 3 | Twelve ORM models, frozen SQL baseline, encrypted-credential and language migrations | Fresh PostgreSQL installation and structural comparison before adopting an existing SQL database |
| 4 | OIDC/JWKS authentication, hashed device credentials and six default roles | Issuer/audience/signature/expiry checks; tenant/department isolation; no implicit tenant access for platform administrators |
| 5 | Strict request models, bounded lists, explicit commits and normalized errors | Invalid input rejected without echoing credentials; deferred constraints evaluated before successful responses |
| 6 | Platform users, organizations, settings, administrator assignment and audit | Last-administrator safeguards, optimistic settings version, platform suspension boundary |
| 7 | Organization and department management, memberships and invitations | Verified-email acceptance, expiring hashed tokens, role/scope enforcement and atomic audit |
| 8 | Device registration, enrollment/revocation, preferred language, heartbeat, telemetry and activity | Single-use enrollment, inactive-device restrictions, deduplicated historical samples and events |
| 9 | AWS/Azure connections, encrypted credentials, operation checks, immutable profile revisions | Rotation invalidates validation; publishing checks bindings; effective configuration hashes propagate policy/language changes |
| 10 | Durable processing requests, idempotency, quotas, bounded uploads, result/media access and playback | No double reservation on retry; media inspection and content hash; expiring scoped media access |
| 11 | Worker leases, provider adapters, reconciliation and retention | Worker fencing; cancellation cannot be undone; unknown submissions do not blindly repeat; cleanup precedes deletion |
| 12 | Local commands, Dockerfile, CI, operations and device probe | Runnable local service/worker commands, reproducible tests, package/migration artifacts and operational handover |

After implementation, perform two distinct reviews. Record findings, fixes and regression verification in `pms-api-reviews.md`; maintain `pms-api-todo.md` throughout.

## Request and data boundaries

Routers parse inputs and call small module functions. `security/access.py` establishes human/device identity and organization/department scope. Every tenant lookup uses the requested organization and, when applicable, the membership's department. Runs, telemetry and activities preserve their historical department snapshot. Platform permissions and organization permissions are separate.

The six fixed roles are `platform_admin`, `org_admin`, `org_user`, `org_read_only`, `org_trainee`, and the device-only `org_device`. A normal human without a platform role may create an organization when registration policy allows it. The creator receives an organization-admin membership. A trainee can read scoped device summaries, basic status, results and media, without configuration, processing or administration privileges.

Administrative changes take the platform singleton lock first where required by the SQL guard design. API services commit before returning success so deferred last-administrator checks are visible to the caller. No cloud API runs while holding a database row lock. Processing admission serializes organization quota reservations. Workers claim with `FOR UPDATE SKIP LOCKED`, use expiring random lease tokens and recheck the token on every write.

JSONB stores small versioned settings, health, normalized results and media manifests. Large media stays in private local development storage, S3 or Azure Blob storage. The application database stores object identifiers and expiration/cleanup state.

## Patient practice turn: routing then speaking (2026-09-19, recovery added 2026-09-21)

A practice completion spends **up to three bounded model calls** inside one request, lease and idempotency key, because a single call cannot both hold the whole topic index and produce natural speech inside the 2,048-token local window.

1. **Routing.** `modules/patient_context.py` builds `id|intent` lines for every disclosable topic and asks for exactly `{"kind":"...","topics":["id"]}`. `kind` is one of `topic`, `backchannel`, `command`, `boundary` or `unknown`. Topic answers are deliberately **not** in this prompt; carrying only the index keeps 32 topics near 3,050 bytes, measured previously at roughly 4.1 bytes per token. Any malformed object, unknown kind, duplicate, over-long list or concealed topic id fails closed to `unknown` with `routing_status: "invalid"`.
2. **Speaking.** Only when routing selected topics, a second prompt carries the persona facts the author permitted, the selected topics' authored answers and the authored `presentation`/`history` wording for those topics alone. The model rephrases; it is told to add no fact, number, medicine or advice. Instructor objectives, notes, rubric, diagnosis, `never` disclosures and unrouted sections never enter either prompt.

`backchannel`, `command` and `boundary` are answered from authored `dialogue` text with **no further call**, so filler, instructions and abuse stay in character instead of returning the clarification line for everything. `command_ack` acknowledges without asserting that the body moved: manikin physical capability is not modelled yet.

**Repair.** A `routing_status: "invalid"` outcome is retried exactly once. Eight different causes collapse into that one status — prose around the object, a code fence, a hallucinated or duplicate id, more than three ids, an invalid kind, a missing or extra key, and an object truncated because the allowance ran out — and most are formatting slips rather than the case failing to hold the answer. The retry drops the conversation to the message being answered, appends `REPAIR_RULE` after the topic index, and is allowed `repair_budget` — double the routing allowance, floored at it and capped by the spoken one — so a truncated attempt gets room (150 tokens local, 1,024 remote) without a third configured number and without reserving a spoken answer's worth of tokens to emit about fifteen. The unusable reply is never fed back. A second failure keeps the authored clarification, and a routed decision is never retried. `routing_attempts` and `routing_repaired_from` report what happened.

**Deflection.** `unknown` (including a twice-invalid outcome) answers from authored `dialogue.clarification` by default. Setting `model_options.patient_deflection_mode` to `generated` instead spends the spoken call on an in-character "I did not follow" that names up to `DEFLECTION_SUBJECTS` (8) topic *intents*. That prompt carries no authored answer, no persona fact and no instructor content, so it cannot disclose a case fact however the model replies; the spoken guard is unchanged, and a rejected reply falls back to the authored line with the call still counted. It is off by default because it is a provider call spent on a turn with no fact to speak.

The spoken call is **buffered, not streamed through**: generated wording is released only after a guard confirms it introduces no number absent from the supplied facts (Latin or Devanagari digits), stays within 900 characters and did not stop on `length`. A rejected or truncated answer falls back to the literal authored text, recorded as `answer_source: "scripted_case"` rather than `"patient_voice"`. Every prompt is fitted independently by `fit_patient_prompt` and reported under `context.routing` and `context.voice`. Admission reserves every completion the turn may make — routing, one repair, and the spoken call when either generated wording or a generated deflection is configured — against the daily output-token quota, within the column's 16,384 ceiling.

Remote providers keep their configured allowance for routing so reasoning models are not starved (measured deliberation reached 420 tokens for a 15-token reply), and `patient_voice_tokens_remote` is unset by default for the same reason. The local server is clamped to `patient_routing_tokens_local` (75) and `patient_voice_tokens_local` (256); both are published on the route so the laptop and the platform stay one substitutable unit. The spoken cap is not merely the 900-character guard converted to tokens: Devanagari costs several tokens per character, and an answer that stops on `length` is discarded, so too tight a cap reads as a stiff patient rather than as a failure. `scripts/audit_patient_index.py` reports every prompt against the window that binds it, and lists topics that are absent from the index because they are concealed or missing a translation — those can never be routed, and the result is otherwise indistinguishable from a model failure.

Generated wording is a bounded rephrasing of authored text, not clinical generation: the patient still cannot volunteer a fact nobody wrote.

## Media, providers and language

Profile section audio duration and video duration/dimensions/frame-rate limits tighten effective capture policy. Run admission, default quota reservations and actual upload inspection use these limits. Current organization/platform caps also clamp the configuration returned to devices; published revisions and existing run snapshots stay immutable.

Audio input and video are separate bounded runs. Video-only clips must omit microphone audio; submitting audio separately enables independent permissions, costs and retention. Audio output is a separate synthesis/playback operation. Device playback acknowledgment records delivery separately from successful synthesis.

| Capability | AWS adapter | Azure adapter | Local device contract |
|---|---|---|---|
| Speech transcription | Transcribe batch job with deterministic job name and S3 staging | Speech fast transcription REST | Planned laptop OSS model returns text through Pi; no local transcription engine currently advertised |
| Video labels | Rekognition asynchronous label detection with deterministic client token | Video Indexer private video upload/index/delete | OpenCV motion events |
| Speech output | Polly synthesis; PCM can be wrapped as WAV | Speech text-to-speech REST | eSpeak NG synthesis and device player |
| Audio activity | — | — | Local audio activity events |

English/Hindi output chooses compatible default voices. Additional catalog languages need a compatible configured voice and engine support. The catalog defines selection, not a promise that every provider supports every language. Official references: [Polly voices](https://docs.aws.amazon.com/polly/latest/dg/available-voices.html), [Azure speech languages](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support), [Rekognition idempotency](https://docs.aws.amazon.com/rekognition/latest/dg/api-video.html).

Connection access validation checks identity/service discovery and staging access where applicable. Its `test_kind=access` explicitly differs from an end-to-end sample. Run a bounded ordinary processing request after publishing to test actual operation permissions, language/voice support, results and cleanup. No connection-wide success implies that another operation has been validated.

AWS processing clients disable automatic transport retries. The worker records submission intent before billable requests. Lost synchronous responses become `unknown`; asynchronous jobs are reconciled by provider identifier/idempotency key. Unknown Rekognition submissions require operator reconciliation: calling start to discover the job could create new work. An authorized organization administrator can record a provider-verified resolution; this never automatically resubmits lost synchronous work.

## Database evolution

`0019_patient_turn_recovery` widens the recorded local-turn call count to three, adds `patient_deflection` to the authored outcomes a caller-executed turn may report, and raises the reserved-output ceiling to 16,384 so a turn can reserve routing, its repair and the spoken call. No column is added and no existing record changes meaning.

`0001_baseline` installs the reviewed SQL unchanged. `0002_credentials` adds ciphertext/key ID and invalidates connection validation on credential rotation. `0003_languages` adds the language catalog and optional device preference. `0004_runtime_guards` versions connection activation and revokes PUBLIC execution on the language trigger function. `0005_subscriptions` adds Standard/Advanced plans, mandatory organization assignments and serialized membership/device capacity guards. `0006_confirmed_plan_limits` applies the confirmed 200-user/1-device and 500-user/3-device defaults without removing records or overriding customized capacity pairs. There are now thirteen domain tables and 241 columns. The two role-catalog views are not domain tables.

Do not use ORM `create_all` or blind Alembic stamping. The SQL baseline owns constraints, triggers, indexes and role views; ORM metadata maps application columns. Before adopting an existing database, compare columns/defaults, constraints, indexes, functions, triggers, views and security metadata with the packaged baseline signature. Later migrations are explicit reviewed SQL, including data migration when needed.

Speech request contracts follow the [Azure text-to-speech REST reference](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-text-to-speech) and [fast-transcription reference](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/fast-transcription-create). Entra Speech connections require a resource endpoint and resource ID.

New processing requires an enrolled device with an unrevoked credential, including requests initiated by a human. Revocation cancels pending work; re-enrollment restores eligibility. Device-authenticated requests must match any organization identifier in the URL. Polling prioritizes actionable work/playback over completed history. Predictable synthesis validation happens before submission intent, and automatic expiry/cancellation writes an operational activity event atomically.

Device work polling includes cloud capture requests in `awaiting_upload`, prioritized alongside actionable local work and playback before completed history. Devices request authorized upload access, capture bounded media and finalize it before worker dispatch.

Subscription catalog administration uses platform settings permissions; organization plan assignments use platform organization-management permissions. Organization creation requires an active plan ID. Pricing, confirmed defaults, seat-counting rules, migration backfill and endpoints are detailed in [the subscription contract](../platform/db/subscriptions.md).


## Standalone local video recording follow-up

The confirmed local companion in [device/video-process](../device/video-process/README.md) receives and saves video only, independently from audio transcription and PMS. It exposes an authenticated bounded JPEG-over-WebSocket stream on port 8766 and owner-scoped recording receipts. Background writes create private playable MJPEG Matroska segments. No live detection, decoding, re-encoding or image extraction runs in this service. An offline command can extract original JPEGs from completed recordings while the API is stopped. Existing platform video-label/provider contracts above are separate capabilities and do not enable analysis in this companion. Platform run/configuration binding, Pi capture/display adapters and Wi-Fi/hardware verification remain future work.
