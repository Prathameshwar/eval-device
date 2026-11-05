# Human voice test

Human-test is the desktop frontend for the shared
[`training-client`](../shared/training-client/README.md) package. Pairing, model
calls, listening/playback, assigned-session ownership, history and media archives
live there. This folder owns Tk views, desktop connection/configuration defaults
and launchers. Existing `HUMAN_` settings and private `.local/` paths are retained.
The same core powers the headless [Pi-test service](../pi-test/README.md), including
remote GPU transport. Physical Pi qualification remains outstanding. See the
[extraction checklist](../docs/shared-client-todo.md) and
[current end-to-end review](../docs/client-e2e-review-20261011.md).

For a copy-and-run Windows package without installing Python on the destination,
see [portable Human-test](../docs/human-test-portable.md). Extract the complete
folder and launch `Human-test.exe`; enroll each computer independently. Install and
start assigned local models separately in **Manage Local Models**.
Portable builds compile key conversation, model, speech and sync modules with
Cython by default and omit their Python source. This raises inspection cost;
it does not make embedded code or prompt strings unrecoverable.

Patient background is authored and reviewed in the platform's scenario editor.
Version 5 cases carry optional everyday facts and approved choices; a choice is
fixed for each conversation. Local replies use one generation with a default
128-token cap and two recent dialogue pairs. Exact native token counting checks
capacity before generation. New English version 4/5 sessions select approved fact
IDs in that same call and speak the stored wording; clear general questions use
a shorter knowledge prompt. Missing personal details remain unknown. Clinical
facts stay in the immutable snapshot. See [background
authoring and verification](../docs/simulations/patient-background/README.md).

Current Practice workflow: use this desktop app to choose a published scenario,
language and initial observations, then save your private setup before starting
the conversation. The web platform provides scenario authoring and publication;
it has no Practice page. The app uses the retained authenticated Practice APIs
and database records. No browser selection is required.


Speak on this laptop and converse with the patient configured in the central platform. The registered device assignment chooses local or cloud models: local inference runs on this laptop, and cloud inference goes through the platform API. Conversation language follows the patient setup and installed language packs.

## Run now on this laptop

1. In the platform Devices page, create the device, assign its models, and issue an enrollment token.
2. Run [start/start-human-test.bat](../start/start-human-test.bat). The connection screen defaults to `https://eval.centralindia.cloudapp.azure.com`; change the address if using another platform.
3. Enter the **device unique ID** (or registration UUID) and **enrollment token**, then click **Connect & start**. No user login, tenant UUID or environment-file editing is required.
4. Watch connection, enrollment and model startup progress, then click **Open Practice**. Choose a published scenario and language, review observations and save. Start the microphone explicitly, or type a question.

### Device connection and central inference

Use the gear icon for enrollment and connection settings. Clearing saved provisioning
removes this desktop's connection, keeps recordings/history, and does not change
central model services or the platform registration.

For a local assignment, open [Manage Local Models](../local-models/README.md), download
and verify its assets, provision the matching LLM/recognition service, and start it.
Provision/start synthesis as well for speaker output. Then start Human-test. A missing,
stopped or mismatched assigned service produces an actionable connection error.
Human-test never downloads models, provisions runtimes, selects GPU settings, starts,
stops or cleans up inference services. Closing either desktop leaves central inference
running. Cloud assignments continue through the platform API.

Later launches reconnect automatically. Enrollment tokens expire after 15 minutes and are used once; the app saves only the resulting device credential in the private `.local/platform-connection/connection.json` file. A model startup failure keeps the enrollment so **Retry connection** can continue without another token. Revoked credentials require **Change connection** and a new enrollment token. Use `start/start-human-test.bat --connect` to force the pairing form. Transfers require pairing with the new registration; previous conversations stay with their original tenant/device registration.

Install desktop dependencies with `setup.bat` before the first launch. It runs `uv sync --frozen --no-dev`, which also removes stale packages from the Human-test virtual environment. For development, run `uv sync --frozen` from `human-test/` to include pytest, pytest-asyncio, Ruff and mypy; ordinary batch launchers use the existing environment without installing development tools. Assigned local model files must already be installed. The platform must have migration `0043_device_practice` and an active published scenario; new tenants include starter examples. For a local platform, start `start/start-platform.bat` and enter `http://127.0.0.1:8000` in the connection screen.

The desktop lists published scenarios without requiring clinical author access. It
restores your saved selection when available; otherwise it suggests the tenant
default or the first scenario supported by your installed language packs. Selection
is saved only when you press Save. Reload from PMS refreshes availability and your
stored values without starting a conversation. You can change the scenario and
language here; there is no web Practice page. Inactive or unsupported scenarios
cannot be restored as an active choice. Private revision checks prevent overwriting
another saved change silently.

Human-test and the web UI share the platform API and database. Human-test accesses platform data only through HTTP APIs; it has no database credentials, migrations, SQL access, private API process or database retention worker. It does not generate an administrator identity or automatically create a tenant/profile. Existing `.local/demo/` data is not used or deleted. Local recording/cache/launcher state is separate under `.local/platform-client/`. The launcher connects to assigned central inference services; it owns only its desktop window. See the [API boundary and lifecycle](../docs/human-test-api-boundary.md).

The Models screen displays the device assignment and can reload it. A conversation LLM is required. Interactive speech accepts local Whisper or Azure OpenAI Whisper; with no supported speech assignment, use typed questions. Other cloud ASR assignments are device-job processors and cannot transcribe desktop interviews. Local models must be installed on this laptop before execution. With `HUMAN_DEVICE_TOKEN`, startup reports supported installed model names; configuring a model in the web platform does not install it.

Launch Human-test using `start/start-human-test.bat`. This folder retains `setup.bat` for dependency installation; desktop launch shortcuts live in `start/`. PostgreSQL setup belongs to `platform/api`, not this client.

| Service | Address |
| --- | --- |
| Platform API | `HUMAN_PMS_URL`, normally `127.0.0.1:8000` |
| Central inference manager | `127.0.0.1:8790` (configurable) |
| Microphone / speaker / camera | Physical devices owned by Human-test |

Closing Human-test releases its capture/playback and window. Central inference, platform API and database continue running. An exclusive owner lock prevents duplicate launches. [Launcher behavior and setup](../start/README.md).

## Using the window

- **Pause / Resume** controls listening; microphone input stops while a reply is generated.
- **Busy models:** cloud speech allows ten rounds of five retries for the same captured recording: 50 retries plus the initial submission (51 attempts maximum). Each round waits 1, 2, 3, 4 and 5 seconds before its retries, with an additional **three-second pause between rounds**. Local/cloud response submissions retain five retries (six attempts maximum), reusing the transcript. The microphone is closed and speaker playback is stopped throughout retry waits, round pauses and requests. The window shows the round, retry number, waiting/in-progress status and **Cancel queued question**. Successful completion speaks the answer once, then resumes continuous listening after playback; persistent busy errors return to **Start microphone** after the final retry. Cancellation stops further retries, including during the pause between rounds. Only explicit capacity rejections are retried; local speech streams, connection interruptions, partial responses, configuration errors and quotas require status recovery or operator action. Cloud speech defaults can be adjusted in `.env` with `HUMAN_SPEECH_RETRY_ROUNDS` (1â€“10) and `HUMAN_SPEECH_RETRY_ROUND_PAUSE_SECONDS` (0â€“60). Exhausting the default speech policy adds 177 seconds of scheduled waits, plus time spent making requests.
- **Send now** ends the current capture. The app waits for all finalized ASR chunks before making one PMS request.
- **Cancel answer** closes the active request. Partial text is marked incomplete and does not enter conversation history.
- **Reset** clears the conversation after the current turn has stopped. History stays in memory and supports up to six completed exchanges plus the next question, within the text budget.

- **Check request** retrieves the last request's status or retained completed answer without rerunning inference. A recovered answer is displayed but is not silently appended to conversational history; use Reset for a new conversation after an interruption.
- **Speaker out** plays the patient's answer through this laptop's speakers. It is **checked by default**; clearing it stops the current sentence immediately and leaves the answer as text. Only a newly generated answer is spoken â€” a **Check request** recovery is shown silently.
- Choose microphone/language and the streaming switch while paused. **Exit** closes capture and client connections; central services keep running.

During retries, a bordered panel appears centred over the patient stage, below its
title row. It shows an animated clock, the round and retry number, a live
countdown and elapsed waiting time. Between rounds it counts down the three-second
pause; during submission it displays **Retry request in progress**. The panel
confirms that your question is retained and provides **Cancel queued question**.
It closes automatically on success, exhaustion, cancellation or another terminal
error. Restart an already-open desktop to load these changes.

### Camera preview and local recordings

In **Conversation**, open the **â‹®** menu and check **Capture & show video** (or use the same checkbox in the drawer's **Camera** section) to preview and record the laptop webcam. The preview floats in the bottom-right corner of the patient stage so it stays visible with the drawer closed, and a red **REC** pill appears in the status strip while recording. The selectable recording path and camera status sit in the drawer's Camera section. Camera **0** normally selects the built-in camera; stop capture before choosing another number (0â€“9) from the drawer spinbox or the menu's **Camera number** submenu. Cameras are never opened or probed automatically. Unchecking, **New conversation**, **Patient setup**, and closing the window stop capture and finalize the current file. Microphone pause/cancel does not stop an independently enabled camera.

The selectable path under the preview shows the current session folder. By default, recordings use this layout, based on the laptop's local date/time:

```text
human-test/.local/video-recordings/
  2026/09/20/14-30-05_a1b2c3d4e5f6/
    video-0001.mkv
    video-0002.mkv
    session.json
```

Each playable MJPEG Matroska file covers up to one minute. These files contain **video only**; microphone audio remains separate. The receipt records local time with its UTC offset, completion status and completed filenames, without patient names or conversation text. An interrupted `.mkv.part` file is not marked complete. Completed segments remain available after a later camera or disk failure.

For performance, capture/encoding runs in a separate low-priority process, with one encoding thread, at most 640Ã—480 and 10 FPS. The small preview updates at most 5 FPS and holds only the latest frame; it cannot accumulate a frame backlog. Delays reduce the captured frame rate while recorded timestamps preserve elapsed time. No video analysis or model runs. This still consumes CPU and disk bandwidth; see [measured overhead and limitations](../docs/desktop-video-review.md).

Default limits are one hour per capture, 5 GiB total in this recording folder (including old/incomplete files), and a 512 MiB free-disk reserve. Reaching a limit stops recording visibly. Existing recordings are never automatically deleted. Archive or remove old recordings when the folder fills. Local originals are private to the current OS account (and SYSTEM on Windows). Enrolled practice sessions also upload completed segments through the private PMS session archive, with durable local receipts and bounded background retries. See [result and recording sync](../docs/session-recording-sync.md) for progress, retry and retention behavior.

Set `HUMAN_VIDEO_RECORDING_DIR`, `HUMAN_CAMERA_INDEX`, `HUMAN_VIDEO_MAX_SESSION_SECONDS`, `HUMAN_VIDEO_QUOTA_MB`, or `HUMAN_VIDEO_MIN_FREE_MB` in `human-test/.env` to override these defaults. Relative folder paths are anchored to `human-test/`, independent of the batch file's working directory. Restart the desktop after editing these settings. `setup.bat` / `uv sync --frozen --no-dev` installs the locked camera dependencies.

**Pi follow-up:** camera input is separate from recording and preview. This desktop implementation uses the laptop webcam adapter. The existing Pi training agent and JPEG receiver are separate; forwarding their authenticated frames into this desktop remains follow-up work. For that integration, preserve the Pi's compressed JPEG packets when saving, and decode only sampled preview frames to avoid laptop re-encoding. No Pi camera or network verification is claimed here.

### Speaker output

Speaker playback requests bounded synthesized audio from the central **Piper** service. Voice assets, native loading, tuning and the two-voice cache belong to `local-models/`. Human-test receives PCM and plays it through its physical speaker; it has no Piper/ONNX runtime dependency.

```powershell
..\start\start-local-models.bat  # download, provision and start synthesis
```

The saved PMS patient identity already contains `sex`. For English, male patients use **Ryan (US English)** and female patients use **Lessac (US English)**. For Hindi, male patients use **Rohan** and female patients use **Priyamvada**. Missing, unspecified or unsupported values select the male voice without changing the patient identity. If the female voice files are missing, playback falls back to the installed male voice in the same language. Save the patient setup to apply the choice; no API/model-server restart is needed. Restart an already open Human-test window once after installing this code update.

Every pinned voice is a **22 kHz medium-tier** Piper model. A `low`-tier 16 kHz voice sounds noticeably mechanical; `high` tier was measured at a real-time factor above 1.0 on this CPU, which would stutter, so medium is the deliberate choice. Each voice carries optional prosody settings in `local-models/voices.lock.json` (`length_scale`, `noise_w_scale`), applied through Piper's `SynthesisConfig` to keep the pace and phrasing from sounding clipped.

**Choosing a different voice.** The conversation panel has a voice list beside the microphone, defaulting to *Default for this patient*. Selecting a named voice overrides the default **for that voice's language only**, so an English choice and a Hindi choice are kept separately and the answer language is never changed. **Hear** speaks one fixed sample so a voice can be judged by ear without asking a question; it is refused while the microphone is open so the sample cannot be recorded. The picker and Hear are disabled while a turn runs, but **Speaker out** stays available so speech can be muted mid-answer. Set `HUMAN_VOICE` to a key from `local-models/voices.lock.json` to make a choice permanent.

Alternatives installed alongside the defaults: **Alan (British English, male)** and **Jenny (British English, female)**.

The desktop checks central synthesis readiness on its background thread. The central worker caches at most two native voices. Returned WAV audio is validated and played in bounded slices after the durable result gate succeeds. **The microphone stays closed until the patient has finished speaking**, so the answer is never captured back as your next question. That wait follows audio actually reaching the sound device rather than a fixed timeout, so a long answer is never cut into; only a five-second stall releases the microphone, so a stuck device cannot strand input either. Pause, Reset, Exit or clearing the checkbox stop playback at once. Lip movement follows the real audio while speech is playing.

**Hindi speaker output is installed.** Select Hindi in the patient setup, save it and leave **Speaker out** checked. Auto mode also selects Hindi speech when the answer contains Hindi text. The installer supports the official Sherpa-ONNX distribution of Piper voices, including its nested `.tar.bz2` archives; it extracts only the model/config and verifies their pinned hashes. This keeps setup available when Hugging Face downloads are blocked. It retries transient downloads up to five times; conversation playback never downloads voices or switches pronunciation languages. Priyamvada's upstream dataset is CC BY-NC-SA 4.0 (noncommercial); Rohan's model card links IIT Madras IndicTTS dataset terms. See the [Hindi installation audit and samples](../docs/hindi-voice-review.md) for provenance, checks and limits. Synthesis checks do not assess pronunciation quality.

The displayed timing separates final ASR processing from model first-token/total time. Non-streaming cannot report a first token. Output-limit truncation is shown explicitly. Defaults: 30-second question limit, five seconds of initial silence (`HUMAN_NO_SPEECH_SECONDS`), mono 16 kHz PCM16, bounded two-second microphone queue. If the event loop stalls, the queue drops its oldest block rather than the whole question, and the window reports how much audio was lost; losing more than `HUMAN_MAX_LOST_BLOCKS` (one second by default) stops the question instead of submitting audio with a hole in it. Incomplete audio or an unsupported microphone format also stops the question. Empty, whitespace-only or punctuation-only speech recognition produces no LLM question, canned clarification, spoken reply or reply animation. The previous answer clears and an active microphone session keeps listening. These checks apply before the editable filler dictionary; short recognized words and numbers remain valid input.

A failed question keeps an active microphone session on: its warning remains visible and a new capture begins after three seconds. Unknown audio/response submissions are never replayed; **Check last request** retains the failed request reference even after a later success. Manual pause/cancel/close and the existing busy-retry exhaustion policy stop listening. See the repeatable [native recovery simulation](../docs/simulations/continuous-listening/README.md). Temporary cloud startup probes warn after five attempts and allow the app to open; authentication, configuration and policy failures remain enforced.

Cloud speech can select the original **Azure Whisper audio** or **Azure GPT Realtime Whisper** connection. Both preserve recording and PMS admission controls; Realtime currently transcribes completed recordings over WebSocket. See [configuration and live evidence](../docs/simulations/azure-realtime-whisper/README.md#selectable-app-integration-2026-09-20).

Each question is reported with the microphone it used, its speech level and its signal-to-noise ratio, plus plain-language concerns when the input is worth distrusting: clipping, a level close to the room noise, digital silence, or a room too noisy for an endpoint to be found. **Check** next to the device list â€” and choosing a device from that list â€” opens the microphone briefly and reports what it hears, so a muted, missing or reordered device fails before a session rather than during one. The speech gate calibrates against the room at the start of every question: `HUMAN_ENERGY_THRESHOLD` is its lower bound, and a noisy room raises the bar to `HUMAN_NOISE_MULTIPLIER` times the measured floor. Captured frames reach the transcriber exactly as the device produced them; nothing filters, gains or resamples them.

## Existing PMS installation

Both launcher paths open device pairing and check existing connections. Platform Admin manages model definitions and device assignments. Provider keys remain exclusively in PMS; the launcher supplies only the central inference-client credential to the desktop. Existing manually configured `.env` user sessions remain supported when no saved device pairing exists.

Enrolled devices can use published scenarios with their own private selection, conversations and history, including devices assigned to a department. They cannot administer tenants, users or models. Device/tenant/department lifecycle, assigned models and revocation are checked by the API. A paired desktop is a shared device identity: it does not identify individual learners. Legacy user sessions retain their existing organization-wide processing/results permissions and token renewal requirements.

Remote platform API calls require verified TLS. Local LLM, recognition and synthesis use the central manager on authenticated loopback. Readiness checks do not establish live cloud inference or hardware quality.

## Configuration and private data

API-token handover settings, inference-client credentials and operational state live under **`.local/platform-client/`**, protected for the launching Windows account and SYSTEM. Keep this directory private. The client uses the configured platform access token; it does not mint identities, database credentials or provider encryption keys.

To protect operator privacy, all launcher scripts and desktop window interfaces feature built-in **privacy logging masking**. Specific local IP addresses (such as loopback connection ports), hostnames, local model file names, and active GPU hardware device names are automatically masked or generalized in the console stdout logs and the desktop application's status/health indicators.

Enrolled practice sessions archive results and captured media through PMS; optional legacy history uses its own private bounded outbox. Completed-answer cache and retention workers belong to the platform. Human-test does not configure an ASR recorder. Results, transcripts and recordings remain private; see [result and recording sync](../docs/session-recording-sync.md).

The assigned platform models determine local or cloud routing. CPU/GPU selection, GPU layers, runtimes and resident model loading are configured only in [Manage Local Models](../local-models/README.md). Human-test displays readiness metadata and sends requests; it never chooses compute or restarts engines. The deprecated `--audio-device` flag is ignored.

The desktop now supports saved patient cases, grounded answers, local English/Hindi speech output and the opt-in laptop camera recording described above. Clinical assessment and Pi hardware integration remain later work. See [implementation and validation](validation.md) and the [phase plan](PLAN.md) for the earlier general question/answer foundation.


## Optional medical profile

Install and provision QwenMedic / Whisper Medical through Manage Local Models, then
assign the matching models in Platform Admin. Human-test connects to that published
assignment; compatibility demo names do not start or choose model engines. Medical
model inference remains unverified on this machine; see [medical model evidence](../docs/medical-models.md).

## PMS local/cloud models

Platform Admin creates models in **Models** and assigns them in **Devices > Configure model**. The desktop Models window is read-only and reports conversation, speech recognition, device speech output and device video assignments. **Reload assigned models** starts a fresh conversation context and returns to Practice setup. A failed reload shows an error and can be retried.

After changing a local assignment, provision and start the matching service in Manage Local Models, then reload the assigned models in Human-test. The reload refreshes central voice metadata and returns to Practice setup. It does not download models, create connections, publish profiles or expose the retired activation/cleanup control endpoint.

Interactive recognition supports local Whisper and Azure OpenAI Whisper. Disabled speech and job-only Azure Speech/AWS Transcribe do not prevent typed questions. Desktop output uses installed Piper voices; camera segments are recorded locally and enrolled practice sessions sync completed segments to PMS. Device TTS/video assignments apply to the separate device processing path. No automatic provider fallback occurs.

Cloud providers, credentials, enablement and endpoint allowlists remain centrally managed. Conversation requests preserve the device revision/hash, tenant authorization, request recovery and private history boundary. See [API boundary](../docs/human-test-api-boundary.md) and [cloud model management](../docs/cloud-model-management.md).

## Local conversation history

Conversation history is enabled by default for the desktop, enrolled launcher and new laptop configuration (`HUMAN_HISTORY_ENABLED=true`); the API defaults to `PMS_LOCAL_HISTORY_ENABLED=true`. **History** shows the latest ten completed pairs and whether they are saved locally or in PMS. Inference continues on the laptop; a private outbox uploads completed records separately. Reset clears model context but retains saved history. Existing explicit `false` settings remain opt-outs and must be changed when enabling an older installation. Queue/disk failures are visible and never delay an answer. See [storage, limits, retention and recovery](../docs/local-conversation-history.md).

### English conversation implementation

The current patient path uses an explicit English language pack, a pinned conversation context, the complete permitted case, and one model generation per answer. Auto and unqualified Hindi conversation selection are disabled. Local startup and new connections default to `qwen3.5-4b-local`; device model assignments are changed by Platform Admin in Devices > Configure model. Older routing/timing reviews above describe historical implementations.


### Inputs that do not need a reply

Edit the shared [`input-ignore.json`](../shared/training-client/src/training_client/input-ignore.json) to manage
fillers and acknowledgements by conversation language. The English list includes
`hmm`, `um`, `okay`, `got it`, `thank`, `thanks`, `thank you`, `many thanks`, and
`much appreciated`. Each entry is a literal word or phrase, not a regular expression.

The entire utterance must consist of listed entries before it is ignored. Matching
ignores letter case, whitespace, and ordinary sentence punctuation. Repetitions and
combinations such as `hmm, okay okay` and `okay, thanks` are ignored. With
`repeat_last_letter: true`, fillers such as `hmmmm` and `ummmm` are recognized;
acknowledgements still match the listed spelling. Question marks are preserved:
`okay?` passes through. So do `yes`, `no`, `hello`, `stop`, `repeat`, and meaningful
input such as `thanks, but do you have fever?`. Meaningful input is never rewritten.

For an ignored input, the desktop displays **No question to answer** and keeps an
active microphone session listening. It makes no answer-generation request, no TTS
request, no reply animation, and no conversation history/archive/usage record.
Recognition still runs for spoken input so the filter can inspect the final transcript.
The same check precedes both local and cloud answer generation; it does not change
provider prompts or the model itself.

Edits are reloaded for the next input, without restarting. Set a language's `enabled`
to `false` to disable its filter, or empty a list to stop filtering that group. Languages
without a dictionary entry pass through. A bad or missing file reports a configuration
error before generation; it does not silently disable filtering or reuse stale rules.

To use a separate file, set `HUMAN_INPUT_IGNORE_FILE` in `.env` (absolute path, or a
path relative to `human-test/`). Restart once when changing that environment setting.
Files must be UTF-8 JSON, at most 64 KiB, with version `1`, at most eight language
entries, and at most 128 phrases per list. The default JSON is included in the package.

## Web-assigned trainee sessions

The web Sessions page can queue trainees for this device. Human-test previews the next assigned case and language and waits for Begin session. Assigned settings stay fixed; Complete & Close ends the session and offers the next trainee. Web End session also stops the desktop. Every assignment expires 24 hours after it was queued, whether started or not. With no assignment, standalone practice still works without a trainee. See [device session queue](../docs/device-session-queue.md) for deployment and behavior.

## Session recording sync

Enrolled devices save session history, microphone audio, played patient audio and enabled camera recordings through a bounded background journal. Local and cloud models use the same server session identity. See [recording sync](../docs/session-recording-sync.md) for defaults, recovery, performance bounds and retention. `HUMAN_HISTORY_ENABLED` also controls the separate text-history reporting outbox; it defaults to true.

## Conversation performance

The desktop checks central synthesis readiness before opening continuous listening. Current
profile and conversation access checks remain in place; successful technical
readiness probes are reused for at most 15 seconds. The central recognition worker validates the assigned model on every accepted recording.

Result/context saves have bounded priority over media, with media fairness and
reserved queue capacity. Voice synthesis overlaps a required result commit;
playback is withheld if that commit fails or times out. The displayed answer and
sync warning remain available. Capture and remote upload remain asynchronous.

The central synthesis service returns bounded WAV audio; Human-test queues PCM ahead of physical playback. Exact repeated text
can reuse up to 2 MiB / 32 entries of in-memory PCM; no PCM cache is persisted.
Output streams are reused for the current sample rate, with low-latency startup
and a conservative fallback after unsupported latency or underruns. Cancellation
aborts stale output; successful completion drains the final word.

The timing strip reports **estimated** response-to-audio, including the output
device's reported latency. Process-local diagnostic events contain only a random
turn ID, stage durations and underrun counts. They do not contain text or media,
and are not uploaded as new platform telemetry. Real microphone/acoustic onset
is distinct from software submission and digital loopback.

Run `uv run python scripts/benchmark_conversation_pipeline.py --help` for the
isolated fictional ASR/model/journal/voice benchmark. It never accesses PMS or
cloud providers, changes saved selections, or downloads a model. By default it
uses a PCM sink; `--realtime --playback` exercises the output device. Optional
`--loopback` monitors Stereo Mix without saving captured PCM; the input must be
enabled and unrelated system audio silent. Keep evidence under `.test_artifacts`.
See [performance TODO](../docs/conversation-performance-todo.md) and
[review evidence](../docs/conversation-performance-review-20261006.md).

## Central inference connection

The shared client lives in `local-models/client/` and is an editable dependency of
this app. The default manager address is loopback port 8790. Set
`HUMAN_LOCAL_MODELS_PORT` or `HUMAN_LOCAL_MODELS_STATE_DIR` in `.env` for a separate
installation. The launcher reads its private inference-only `client-key.txt`;
operator and worker credentials are never handed to Human-test. See
[the migration and verification](../docs/local-model-client-migration.md).
