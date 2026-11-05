# Human voice test through PMS and local Qwen

Current architecture (2026-10-09): model downloads, native runtimes and inference lifecycle now belong entirely to `local-models/`. Human-test is a read-only inference consumer. The original phases below are historical; their model startup, local engine ownership and WebSocket ASR requirements are superseded by [the central client migration](../docs/local-model-client-migration.md).

Status: implemented, with verification and two review passes recorded in [validation.md](validation.md), 2026-09-19. The desktop test screen belongs in repository-root `human-test/`; its batch entry point is `start/start-human-test.bat`. The reusable LLM client, authorization and response APIs belong in `platform/api`.

## First usable outcome

Launch one Windows batch file. After configuration and service readiness checks, a small desktop window begins listening to the laptop microphone. It displays the recognized question and the LLM answer. Streaming mode displays answer text as it arrives; non-streaming mode displays the completed answer. Subsequent questions reuse the resident ASR and Qwen processes.

```text
Laptop microphone
  -> human-test capture client
  -> existing audio service (local WebSocket)
  -> finalized transcript back to human-test
  -> authenticated PMS LLM API
  -> reusable asynchronous PMS LLM client
  -> resident local Qwen3 4B service
  -> PMS JSON or SSE response
  -> answer in the human-test window
```

For this pilot, PMS runs on the same laptop as the local LLM. A remotely hosted PMS cannot reach the laptop through its own 127.0.0.1; a future remote topology requires a separately designed authenticated transport. The audio service remains standalone. `human-test` coordinates the two API calls; it does not call Qwen directly.

## Practical decisions

- Use a small Tkinter desktop window, Python microphone capture and a background asyncio worker. This keeps Hindi text, streamed answers and microphone status readable without introducing another web application. Tk availability is checked during setup; dependencies remain declared and installation repeatable.
- Initial model is the installed Qwen3 4B Q4_K_M through llama.cpp at the configured local endpoint, currently port 8787, alias `qwen3-4b-local`.
- Use configurable CPU ASR and GPU Qwen because the laptop has about 4 GB VRAM. The selected defaults are Whisper large-v3 on CPU and Qwen3 4B on GPU (updated 2026-09-19); retain installed alternatives as operator-selected options. Preserve unrelated service settings. Earlier small-model latency measurements remain historical and do not describe the new default's performance.
- One spoken turn and one generation are active at a time. Pause microphone admission during final transcription/generation; resume after completion. Provide Pause/Resume, Send now, Cancel answer, Reset conversation and Exit.
- The first implementation answers general test questions. Educator-approved patient context, scenario grounding, spoken replies, camera capture/video display and automatic assessment are later integration work.
- Use existing PMS human authentication, organization/department access rules and PostgreSQL. Configure a permitted account for this test; do not add an unauthenticated development shortcut. A laptop used as this human test client does not need an invented Pi enrollment or device credential.

## Phase 1 - PMS contract, configuration and minimal persistence

1. Define typed LLM request/result/event contracts independently of the screen. Include request key, connection selection, permitted scope, bounded user/assistant messages, language, streaming flag and permitted generation settings. PMS owns system instructions and clamps generation limits.
2. Add focused LLM connection configuration for an active organization: provider kind `local_llama_cpp`, configured endpoint, model alias, limits and encrypted credentials. Reuse PMS encryption, key rotation, redaction and audit patterns. Import the local model API key through a private operator path; keep its value out of the UI, command arguments and logs.
3. Add a forward Alembic migration for minimal LLM connection/request records. Existing provider integrations are specialized for audio/video AWS/Azure processing; keep their dispatch behavior intact. New records cover connection versions and request identity, scope, fingerprint, lifecycle, concurrency reservation/lease, timing, usage and bounded completed result retention. Do not create a general conversation-management subsystem.
4. Enforce organization/department permissions, active membership/connection/parent lifecycle, maintenance policy and capacity during admission. Human execute/read/manage permissions reuse the corresponding PMS permission patterns. Cross-organization references and platform-admin-only tenant access must fail.
5. Make request admission, quota reservation and its audit event atomic. Uniqueness and concurrency limits must work across API processes. Requests use short database transactions; no database transaction stays open while tokens stream.
6. Keep prompt/history persistence off by default. A bounded final-result cache supports safe status lookup and duplicate completion retrieval, with explicit retention and tenant access controls. Audit only operational metadata. Update retention, runtime grants, readiness, models and documentation together.
7. Restrict local-provider endpoints to explicitly configured loopback destinations. Clients submit a connection ID rather than arbitrary URLs. Local connections bypass environment proxies and reject redirects. Cloud providers and cloud fallback remain disabled in this increment.

Acceptance: migration upgrades existing data safely; runtime-role, tenant, lifecycle, encrypted credential and concurrent admission tests pass against a disposable PostgreSQL instance. No frozen baseline or earlier migration is edited.

## Phase 2 - Reusable asynchronous PMS LLM client

Implement `platform/api/src/pms_api/integrations/llm/` with typed contracts and a local llama.cpp adapter:

- `complete(...)` returns a normalized complete response.
- `stream(...)` yields normalized text deltas, final metadata and controlled failure information.
- A pooled asynchronous HTTP client is created/closed with PMS lifespan. Model weights stay in the resident local server; neither PMS requests nor screen turns reload the model.
- Bound connection/pool waits, time to first response, idle reads, overall request time, request/response size and output tokens. Overall deadlines must also stop slow partial headers/events.
- Parse SSE incrementally across arbitrary network boundaries. Preserve UTF-8 Hindi characters, finish reason and usage when supplied. Missing usage remains unknown, not fabricated zero.
- Normalize unavailable model, unauthorized provider, busy/rate limit, invalid context, malformed data, timeout, truncation and cancellation errors without exposing provider payloads or credentials.
- Close upstream responses promptly on cancellation, timeout or client disconnect. Verify native cancellation/release behavior; record uncertainty if provider work cannot be confirmed stopped.
- Never blindly repeat an inference POST after ambiguous submission or partial output. Health/status GET retries may be bounded. There is no automatic device/model/cloud fallback.

Acceptance: mocked provider tests exercise complete JSON, SSE split at byte/UTF-8 boundaries, malformed and oversized events, slow streams, EOF without completion, cancellation, redirect refusal, credential redaction and no uncertain-request replay. Real local Qwen succeeds through both adapter methods.

## Phase 3 - Authenticated PMS streaming and non-streaming API

Proposed public routes:

- `POST /api/v1/organizations/{organization_id}/llm/completions`
- `GET /api/v1/organizations/{organization_id}/llm/requests/{request_key}`
- Scoped LLM connection create/update/status routes using the existing PMS management conventions.

The POST accepts `stream=false` for JSON and `stream=true` for SSE. Both modes share validation, authorization, admission, prompt construction and result finalization. Department-scoped callers must supply or resolve an allowed department; a missing scope must not widen their access.

Streaming contract:

- `metadata`: request/run identifier and selected model.
- `delta`: incremental answer text with sequence numbers.
- `done`: final finish reason, timings, usage if available and committed completion status.
- `error`: sanitized terminal failure; previously displayed text is explicitly incomplete.

Reject admission errors before streaming headers. After headers, failures use a terminal SSE event and a durable request state. Emit `done` only after successful result finalization. Configure no-store/no-buffering response behavior and test that middleware does not collect the full stream first.

A repeated request key with a changed body returns conflict. Completed duplicate requests return the retained result, with a cached-result indicator. In-progress/unknown requests return status without triggering another generation. Interrupted token streams are not automatically replayed; status recovery retrieves the final result when available. Use scoped active-request leases/recovery so a crashed API process does not leave permanent busy state, and avoid claiming an uncertain provider call was never executed.

Acceptance: authenticated text-only tests through PMS pass in JSON and streaming modes before microphone or UI integration begins. Include cross-tenant/department denial, role checks, lifecycle changes, concurrent duplicates, capacity release, disconnects and expired-result behavior.

## Phase 4 - One-screen client in human-test

Planned layout:

```text
human-test/
  PLAN.md
  README.md
  pyproject.toml
  uv.lock
  .env.example
  setup.bat
  src/human_test/
    app.py
    capture.py
    audio_client.py
    pms_client.py
    controller.py
    config.py
  tests/
```

Screen contents:

- Audio/PMS/LLM readiness indicators and explicit Listening / Transcribing / Answering / Paused / Error state.
- Microphone selection and English / Hindi / Auto language selection, validated against the selected ASR model's supported languages.
- Streaming/non-streaming switch, recognized-question pane and answer pane.
- Pause/Resume, Send now, Cancel answer, Reset conversation and Exit controls.
- Per-turn ASR finalization, first-answer and total timing.

Microphone capture uses bounded PCM buffers and the audio service's authenticated WebSocket protocol, normally mono 16 kHz PCM16. Validate actual microphone support; any necessary resampling must be explicit and tested. Audio events are consumed concurrently with capture.

Detect the end of a question using bounded silence detection or Send now. Aggregate all finalized transcript chunks belonging to that microphone turn, including chunks split by the ASR service's duration limit. Wait for the matching complete event before one PMS submission. Deduplicate by stream/event/turn identity; do not send one LLM question per ASR chunk. Empty/silent/failed or incomplete captures do not reach PMS. Maximum question duration and buffer overflow produce a visible controlled outcome.

Keep conversation history bounded in screen memory. Only successful complete turns enter history. Reset clears it. A context-limit response asks for Reset or a shorter question; do not silently remove patient facts or system instructions. Generation text remains separate from transcription text.

Network/inference work stays off the UI thread. Closing the window stops capture, closes audio/PMS streams and cancels owned work. Existing audio-service recording remains configurable and bounded; avoid creating a second copy of the recordings by default.

Acceptance: the UI remains responsive during recording and generation, Hindi text renders correctly, manual send and silence completion each produce one answer, and cancel/reset/exit release resources.

## Phase 5 - Launch orchestration and end-to-end measurements

1. Provide setup and launch scripts inside `human-test`. Keep the existing run batches in `local-models` as requested previously.
2. Check the selected microphone, authenticated audio protocol, PMS authorization/database/LLM configuration and local model readiness before listening. Validate reused service configuration, not just whether a port is open.
3. Where launch profiles provide the required private configuration, start missing local services as hidden child processes and wait for readiness. Reuse already healthy services. Track ownership and stop only processes started by this launcher. Do not auto-migrate the application database, invent identities, replace private settings or kill an unrelated service occupying a port.
4. Run deterministic WAV fixtures through audio -> human-test orchestration -> PMS -> real Qwen -> result display for English and Hindi, in both response modes. Include consecutive questions, silence and an utterance spanning several ASR chunks.
5. Measure microphone end/silence delay, final transcript availability, PMS admission time, model time to first content token, total reply time and combined CPU/RAM/VRAM. Keep cold startup separate from warm-turn latency. Compare direct model versus PMS calls to expose avoidable proxy overhead.
6. Test busy services, unplugged/unavailable microphone, stopped ASR/model/PMS, expired authentication, slow streams, repeated submission and window closure mid-response. Preserve explicit incomplete/unknown status instead of retrying the question silently.

Acceptance: one launch command reaches the screen, the synthetic end-to-end matrix passes, and all owned processes/resources are released. Actual microphone capture and a human-spoken question are separate acceptance evidence; fixture success must not be described as a live spoken test. Record measured latency rather than promise an unmeasured response-time threshold.

## Phase 6 - Review 1, fixes and affected regression checks

Review the complete implementation for:

- Credential handling, fixed destinations, tenant/department/role/lifecycle enforcement and raw-text redaction.
- Database constraints, atomic audits, idempotency, cross-process capacity, retention and crash recovery.
- End-to-end streaming, slow-read deadlines, partial-result handling, cancellation and POST replay behavior.
- Microphone buffers, multi-chunk turn assembly, history bounds, Unicode, UI responsiveness and process ownership.
- Preservation of existing audio/video, scenario, training and standalone LLM behavior.

Fix confirmed findings. Add meaningful regressions and rerun affected checks. Maintain `docs/pms-api-todo.md` and `docs/pms-api-reviews.md` with actual results, including skipped tests.

## Phase 7 - Review 2 and completion evidence

Review the final source and execution evidence after fixes. Run the required platform suite (`uv run pytest -q`, Ruff check/format, mypy), the new human-test tests and relevant compatibility tests. Database integration tests must target a dedicated disposable PostgreSQL server; never an application database. Mock any cloud calls.

Repeat native end-to-end checks when fixes affect that path. Verify batch launch from another working directory, no per-turn model reload, and successful cleanup. Publish a planned-versus-implemented checklist, measured latency table, configuration/run instructions and remaining limitations. Identify whether reviews were performed by the same agent.

Completion requires both PMS response modes and the human-test screen to work through the requested chain. Live cloud, Pi hardware, patient-behavior acceptance, TTS and camera integration remain separate follow-up work.
