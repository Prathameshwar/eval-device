# Online model switching review — 2026-09-19

This review covers code readiness and runtime selection using configured PMS
connections. It does not provision accounts, enable cloud calls or claim live
provider inference. Tests use fictional cases, mocked cloud calls and a dedicated
disposable PostgreSQL cluster. Existing application databases and provider secrets
were not changed. No migration is required.

## Capability audit

| Capability | What can be selected | Current execution surface | Verification boundary |
|---|---|---|---|
| Interactive speech input | Azure OpenAI Whisper deployment | Human-test Models → Cloud/Custom; PMS interactive speech API | Mocked transcription and access checks; actual deployment/quality not verified |
| Patient LLM | OpenAI, Azure OpenAI, OpenAI-compatible text Chat Completions | Human-test Models → Cloud/Custom; PMS JSON/SSE | Provider switching, token/capability contracts and profile revision checks tested |
| Job-based transcription | AWS Transcribe, Azure Speech | Separate PMS profiles and device runs | Existing provider contracts; kept out of incompatible interactive dropdown |
| Video analysis | AWS Rekognition, Azure Video Indexer | PMS `video` profile section and explicit device jobs | AWS/Azure profile switching, connection validation/bindings and device configuration tested with mocks |
| Speech output | AWS Polly, Azure Speech | PMS `audio_output` section and explicit device jobs | Both provider selections and preservation across patient-model changes tested |
| Video receiver | Receive, record and save | Local video API | No model; selecting a cloud speech/LLM connection does not enable analysis/upload |
| Desktop spoken answer | Installed local Piper voice | Human-test speaker | Cloud synthesis is not wired into this playback path |

Direct OpenAI transcription, Responses-only models, vision chat and realtime
audio are not supported adapters. Cloud selection lists configured organization
connections, rather than unverified model names obtained from a public catalog.
Each desired model/deployment should have a connection with its own capability
settings. The current machine has no online selection enabled by this work.

## Findings and resulting behavior

| Finding | Change / evidence |
|---|---|
| Connection names obscured the actual model/deployment | Dropdowns include provider and model/deployment; empty selections explain provisioning; refresh discovers configured choices |
| Saving could apply an unavailable cloud selection before preflight | Desktop checks current deployment gates and LLM/speech access before publishing; speech validation explicitly sends `sample: false` |
| A connection could change after it was displayed/checked | Catalog exposes revisions; desktop checks displayed and returned revisions; publication locks/rechecks both connections and active flags; post-publication mismatches are not applied |
| Operator gates could change between access check and save | `activate: true` rechecks endpoint allowlists, external-call, speech/LLM and maintenance gates at publication; existing configuration-only API saves remain compatible |
| A failed existing-profile selection could affect the active route | Check LLM, speech and the final configuration hash before applying; reset history only after successful selection |
| A lost publication response invited another save | Unknown outcome disables repeated saves until refresh; no automatic POST replay; cancellation reports possible completion |
| Provider settings were not distinguished from desktop video behavior | API separately returns `platform_services` and selected `platform_media`; Models explains recording-only video and separate platform jobs |
| Speech/LLM changes must retain video/output settings | Database tests publish AWS then Azure video/output bindings, apply speech/LLM choices and verify device configuration retains the correct sections and connection IDs |
| Same-host compatible models were incorrectly treated as external calls | Server exposes `requires_external`; desktop and launcher use it; launcher preserves explicit compatible-server port allowlists |
| An inactive current connection could prevent Models from loading alternatives | Load permitted choices even when the previous profile cannot be resolved; retain the active desktop route and allow a replacement to be configured |
| Malformed route data could partially overwrite desktop state | Validate IDs, mode, model and duration before mutating any active settings; regression tests retain the complete prior selection |
| The older LLM guide said Azure authentication was unsupported | Corrected guide to match the existing Azure adapter and current migration head |

Access checks do not upload patient media or generate completions. Azure's current
check verifies authenticated API access; it does not prove deployment entitlement,
model parameter compatibility or successful inference. Those remain live acceptance
checks once credentials and permitted endpoints are configured.

## Reviews and verification

The first review checked authorization, tenant filtering, credential redaction,
provider gates, connection/profile concurrency, failed publication and unknown
outcomes. Fixes include optimistic connection fences and preserving the active
desktop route until checks succeed. An initial media test incorrectly used a
single-profile GET not offered by the API; it now reads the existing profile list.

The second review checked GUI/background-thread boundaries, cancellation,
post-publication revision changes, Custom mode, loopback-compatible startup,
model-specific parameters and preservation of the existing local switch flow.
UI clearing is dispatched through the main-thread event queue. Cancelled or
uncertain saves cannot be automatically replayed. The desktop smoke exercises
empty cloud choices, deployment labels, successful activation, failed checks,
unknown saves and refresh recovery.

Both review passes are complete, with confirmed findings fixed and affected checks
rerun. Final verification:

| Check | Result |
|---|---|
| Full PMS API suite, dedicated PostgreSQL 17 | 270 passed, 3 skipped in 641.66 seconds; all database tests ran |
| Skipped API tests | Two opt-in native Qwen tests and one opt-in local audio → PMS → Qwen test; no resident-model test was claimed as a cloud check |
| Full Human-test suite | 94 passed in 25.16 seconds, with the installed-voice check enabled; no skips |
| Launcher suite | 87 passed in 7.22 seconds using the API environment; no skips |
| API/client Ruff and format | Passed |
| API/client mypy | Passed (55 API and 12 desktop source files) |
| API/client wheel and source distributions | Built offline; packaged switching code matches source and private runtime paths are excluded |
| Real Tk Models smoke | Passed: local behavior, empty online lists, provider/deployment labels, successful/failed online activation, uncertain saves, unavailable-profile recovery and permissions |
| Live cloud inference / Raspberry Pi | Not run |

Total: **451 passed, 3 explicit opt-in native checks skipped**. Two existing
test-client deprecation warnings remain. An initial launcher check used the desktop
environment, which lacks launcher dependencies; rerunning with its required API
environment passed. No package installation was needed for these changes.

## Operational boundaries

- Restart PMS/Human-test once to load this code. Switching already configured
  online connections then needs no restart. Changing operator environment gates or
  allowlists requires restarting PMS.
- Cloud connections remain administrator-managed and encrypted in PostgreSQL;
  the desktop has no provider key fields. Existing revision, audit, quota and
  idempotency behavior remains in effect.
- Custom local components must already be running and match their selected model.
  Switching to cloud does not forcibly terminate resident local services; use the
  local activation flow to replace launcher-owned models.
- Platform media jobs are separate from Human-test recording/Piper. This change
  adds no continuous cloud video stream or automatic analysis.
- Live cloud inference, account quotas, clinical/Hindi quality, network latency
  and Raspberry Pi hardware remain unverified.

Private verification artifacts: `.test_artifacts/online-switch-review/`.
Configuration instructions: [cloud models](cloud-models.md).
