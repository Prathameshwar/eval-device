# Local patient interview pilot

Version 5 clinical cases include reviewed patient background and optional approved
everyday choices. The coordinator prepares a private snapshot once with the signed
session identity, saves it before warmup, and keeps it through history trimming.
The local clinical path uses one 128-token completion, two recent pairs and exact
native chat-template counting at a 2,048-token cap. Oversized context fails before
generation. New English version 4/5 sessions select frozen fact IDs in that same
call; spoken personal/clinical replies contain stored source wording. General
questions and greetings use lean prompts. Old snapshots keep their reply format.
Existing persisted sessions cannot automatically resume after restart.
See [background authoring and checks](../../docs/simulations/patient-background/README.md).

One Raspberry Pi captures microphone/camera input and plays patient speech. A Wi-Fi connected laptop runs the existing audio/video APIs and this coordinator. The platform authorizes sessions and keeps scenario versions, receipts and manual instructor feedback. Hindi and English are supported by configuration. Video is recorded without detection or live analysis.

This is a development pilot, not clinical or hardware acceptance. The supplied fictional case must be reviewed and approved by an authorized educator before learner use. The implementation does not provide diagnosis, treatment advice or automatic assessment.

## Packages and processes

- `shared/training-contracts`: shared validated scenario/session contracts, private filesystem helpers.
- `platform/api`: migration `0007_training_pilot`, training routes and signed 30-second grants.
- `device/audio-process`: resident multilingual Whisper, loopback port 8765.
- `device/video-process`: compressed JPEG recording in Matroska, loopback port 8766.
- `device/training`: coordinator/instructor page on 8767; resident local llama.cpp service on 8780; `training-agent` on the Pi.

Media services remain independent of PMS. Only the coordinator's fixed instructor-control proxy and the Pi agent contact the platform. A device credential never reaches the laptop. Local grants are pinned to the platform public key, one organization and one device. Existing platform administrator status does not grant tenant media access.

## Install and configure

From this directory, run `uv sync --extra replay` on the laptop. On the Pi use `uv sync --extra hardware`; install the OS PortAudio library and Raspberry Pi `rpicam-apps` as appropriate for that OS. Run `uv run training-agent --check` after configuring its environment. This checks device formats/executable availability, not real camera capture or audible playback.

1. Follow the platform API/database setup guides. Migrate to head and reapply runtime grants. Configure existing OIDC identities, organization, enrolled Pi, learner membership and department scope. The Pi must advertise `patient_interview_v1` in its enrolled capabilities. Assign a published profile with `audio_input.enabled=true`, operation `training.interview`, engine `patient_interview_v1`, execution mode `local`, and `capture.max_session_seconds` matching the intended 30-600 second session. Subscription/policy limits still apply.
2. Run `uv run training-api keys --directory ../../.local/training/keys` once, using a new empty private directory. Put `training-private.pem` on the platform via `PMS_TRAINING_KEY_FILE`; keep it outside PostgreSQL. Copy only `training-public.pem` to the laptop/Pi through a trusted channel. The laptop also keeps `model.key`. Never copy private signing/model keys to the Pi. The public verification-key API is for inspection, not automatic trust-on-first-use.
3. Copy `.env.example` to a private `.env` and fill actual IDs, paths and independently generated media tokens. Match these tokens to client ID `training` in the existing media services. Use a separate video directory `.recordings-training`. For this ASR profile set `AUDIO_MODEL_NAME=small`, `AUDIO_MODEL_PATH` to the downloaded `.models/small`, `AUDIO_CONSOLE_OUTPUT=false`, `AUDIO_RECORDING_ENABLED=false`, and leave `AUDIO_CALLBACK_URL` unset. The coordinator retains microphone WAVs/transcripts; duplicate ASR recording/logging is rejected by its preflight. This does not change the existing standalone audio service configuration. To trial Nemotron, instead select `AUDIO_MODEL_NAME=nemotron-3.5-asr-streaming-0.6b` with its matching downloaded model path and restart the audio service. Keep the same recording/console/callback restrictions. The coordinator uses the existing transcript protocol; see [selection and validation](../audio-process/README.md#select-nemotron-for-incremental-cpu-recognition).
4. Start the audio/video services using their documented commands and this dedicated configuration. Keep both listeners on loopback. In the video profile use `VIDEO_SEGMENT_SECONDS=2`, a private 1 GB quota and `VIDEO_RETENTION_HOURS=24` or less. Each training capture requests the shorter platform retention; it can never extend the service limit.
5. Start the resident dialogue service from the repository root, or adjust these paths for your working directory:

   ```powershell
   device/training/.venv/Scripts/training-api.exe model --executable .local/training/llama/llama-server.exe --model .local/training/qwen3-1.7b-q4.gguf --key-file .local/training/keys/model.key
   ```

   The launcher binds loopback, requires its private API key, disables the web UI/request logging and restricts browser origins. One model remains loaded; each request reuses it. CPU threads/context/concurrency are bounded. Stop this launcher to stop the model process.
6. From `device/training`, run `uv run training-api serve`. For Pi access use `--host 0.0.0.0 --cert <certificate> --key <private-key>` and set `TRAINING_ORIGIN` to the exact HTTPS laptop hostname/port used by both browser and Pi. The certificate must match that hostname and chain to the Pi's trusted CA. There is no TLS verification bypass, forwarded-header trust or plaintext LAN exception.
7. Copy `.env.agent.example` privately onto the Pi as `.env.agent`, fill actual platform/laptop addresses, scoped device credential and public key. Run `uv run training-agent`. Camera acquisition uses [Raspberry Pi's documented MJPEG output](https://www.raspberrypi.com/documentation/computers/camera_software.html), with bounded pipes and queues; microphone turns use basic local energy/silence gating. Tune the microphone/acoustics on actual hardware. Capture pauses during playback to reduce feedback; full duplex echo cancellation is deferred.

For a development installation on another machine, the repository and shared source package must be available at the same relative paths for `uv sync`. For wheel installs, install the `training-contracts` wheel alongside the service wheel. Model weights/runtime binaries are separate local artifacts, not bundled into Python packages.

## Scenario and instructor workflow

Create a scenario through `POST /api/v1/organizations/{org}/training/scenarios` with a UUID `request_key` and the validated scenario document. Review `src/device_training/scenarios/cough_interview_dev.json` as development content. Approval is an explicit call to `.../scenarios/{id}/approve` with `educator_name` and a substantive `statement`; the caller needs profile-management permission. There is no automatic approval script. Published versions are immutable; changes create a new version. Retiring a version prevents new sessions and lease renewal.

Open the laptop instructor page at its configured origin. For this minimal pilot, enter an access token from the existing platform identity flow; it stays only in page memory. Select an approved scenario, learner ID, language and duration. The Pi polls for its assigned session, relays a short-lived grant, and captures while authorization remains valid. Initial scenario warmup happens before microphone turns are accepted. Use Finish interview for normal completion or Stop session to cancel. If the laptop is unreachable, the platform stop prevents further lease renewal; playback/capture stop no later than local authorization expiry. Normal connected stop is polled at 0.5 seconds.

Open a session to inspect transcripts, patient answers, playback acknowledgments and recording/sync status. After capture finishes, Prepare video review extracts original JPEG packets at one frame per second in a bounded bulk operation. Reviewing an audio turn advances the matching frame using Pi monotonic offsets. This is a sampled review view; full frame-rate Matroska segments can be downloaded separately. Extraction performs no detection or re-encoding, verifies segment hashes and reads only completed captures owned by that training session. Native camera timestamp delivery/encoder offsets and speaker latency need hardware calibration.

Manual feedback uses the approved scenario's rubric, requires operator permission, and uses optimistic version checks. A trainee can only access their own permitted session results. Scenario authoring UI, OIDC login UI, automated grading, remote live viewing and durable offline session resume remain outside this pilot.

## Failure and storage behavior

- Leases are renewed every eight seconds and expire after at most 30 seconds by default. Loss of authorization suppresses pending replies. A changed profile, retired case, revoked device/user or inactive scope blocks renewal. Revocation is bounded by the issued lease, not claimed to be instantaneous.
- Each turn is admitted durably before audio processing. The Pi sends microphone PCM incrementally through the coordinator to the existing audio WebSocket. Video uses a separate WebSocket/TCP connection with four outstanding frames maximum. A second raw TCP protocol is unnecessary.
- Model failure may select only the approved clarification; ASR/TTS failure ends the session with an explicit failure. No implicit cloud fallback or invented patient facts. Output selects a scenario topic; it does not generate new clinical claims.
- Playback claim, actual device start and finish are separate events. Uncertain playback is never automatically repeated. Fixture mode is explicitly marked `simulated` in local state and platform receipts; it makes no physical playback claim.
- Raw microphone WAV, patient WAV, Unicode transcript, timing and receipts are private on the laptop. A bounded daemon writer handles disk work with quotas, atomic replacement and bounded retries only for idempotent I/O. Storage failures fail closed and remain visible. Slow storage can add delay; there is no zero-latency durability claim.
- Platform submission retries reuse the same result event and payload. Late receipts attach once without changing a cancelled/expired terminal status. Unknown submission outcomes stay visible; a stopped/restarted local session cannot resume or replay automatically.
- Local retention is at most the signed policy (24 hours maximum), with periodic cleanup while running and startup cleanup after downtime. Original video can expire or be quota-evicted before review; missing media is reported, never fabricated. Private filesystem permissions are required; full-disk encryption is an operator deployment option.

## Measured native feasibility

On the available Windows Core Ultra 7 165H / **64 GB** workstation: Qwen3 1.7B Q4 + eSpeak NG selected 10/10 expected topics across the small English/Hindi text-input set. Warm selection plus WAV generation took 1.5-1.9 seconds; initial uncached prompt took about 15 seconds. A later cold secure-service check exceeded its 30-second deadline; a warm repeat succeeded in 1.1 seconds. Complete readiness/warmup before a learner session; cold-start behavior remains an explicit acceptance limitation. llama.cpp observed peak working set was about 2.64 GB (not total laptop/ASR memory).

Actual small multilingual Whisper CPU INT8 -> Qwen -> eSpeak on four synthetic speech samples took 3.7-5.9 seconds after input, with 3/4 expected topics. One Hindi transcription failed. Those measurements exclude Pi capture/Wi-Fi, coordinator persistence and physical speaker latency. They do **not** establish a 2-3 second response target, medical interview accuracy, natural speech quality or suitability on the target 16 GB laptop. Large-v3 remains available for accuracy experiments/offline work; the interactive profile is configurable and must pass representative human Hindi/English/mixed-language testing.

Provisioned assets: official llama.cpp b11026 Windows CPU release, Qwen3 1.7B Q4 from the official Ollama model distribution, eSpeak NG 1.52.0, and official multilingual Whisper small converted to CTranslate2 INT8. Weights and runtime/license files remain under ignored local directories. See the pilot design and review evidence for exact checks and outstanding acceptance gates.

## Verification

```powershell
uv sync --all-extras
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src/device_training
uv lock --check
uv build
```

Tests use synthetic inputs and explicit ASR/dialogue/hardware doubles unless a benchmark is labeled native. The loopback integration test runs the Pi fixture through actual HTTP/WebSocket connections and the actual video recorder/private store, verifies original JPEG bytes and replay, and records a simulated platform result. PostgreSQL authorization/migration tests run separately in `platform/api` against a dedicated disposable test server. No cloud provider, hosted deployment or actual Pi is contacted by the test suite.

## Audio timing and review (2026-09-19)

The [deep audio review](../../docs/audio-latency-review.md) records fixes and fresh native measurements. Microphone buffering is bounded before event-loop handoff; partial upload failure closes capture explicitly. A brief sub-threshold noise burst no longer disables the five-second no-speech exit. Actual microphone/echo tuning remains a hardware task.

After input EOF, `TRAINING_RESPONSE_SECONDS` now covers remaining transcription, selection, speech generation and saving together. Authorization is checked again before speech generation, and failed durable turn admission ends the session before ASR. Error cleanup has its own storage bound and may add time after the response budget expires.

Turn measurements now separate `input_receive_seconds`, `asr_after_input_seconds`, `dialogue_seconds`, `tts_seconds`, `response_save_seconds` and `response_ready_seconds`. `input_duration_ms` is PCM duration. `processing_seconds` now measures actual input EOF through completed TTS, excluding saving; it no longer subtracts PCM duration from wall time. The two final save/ready fields are returned immediately and persist on the next state save, usually playback claim. These metrics exclude Pi playback/network return and are not acoustic response measurements.

For the dedicated one-patient profile, explicitly configure `AUDIO_MAX_SESSIONS=1` and an inference timeout consistent with the chosen response budget. A native ASR timeout fails readiness and requires process restart; no second model is loaded beside blocked inference. This review does not change private environment files or claim that the latency/accuracy acceptance gate is met.
