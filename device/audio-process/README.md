# Local device audio API

This standalone FastAPI service runs on the connected **Windows laptop**. The Raspberry Pi sends microphone audio over Wi-Fi. The laptop transcribes it with a selected local Whisper, Nemotron or Vosk model, returns transcript events on the same WebSocket, and saves audio/text locally through a bounded background writer. Console text output remains configurable.

There is **no PMS API, database, enrollment, or cloud-service connection** in this package. The future text receiver is optional and disabled by default. Raspberry Pi audio/video capture and speaker/display output remain separate hardware adapters; this package implements audio reception, transcription and local recording.

## Run on the laptop

Python 3.12 or 3.13 and uv are required. Run these commands from this directory:

```powershell
uv sync --frozen
uv run audio-api init-local
uv run audio-api download-model --model large-v3
uv run audio-api serve
```

`init-local` creates a git-ignored `.env` with a random token for `pi-1`. Before writing credentials, it restricts the file to the running Windows account and SYSTEM, or mode 0600 on POSIX. Run setup and serving under the same account. It does not print credentials or overwrite an existing file; failed permission setup writes no credentials. The download is an explicit installation step. Serving loads only local files from `.models/large-v3` and fails startup when the model, configuration or tokenizer is missing, preventing an implicit tokenizer download.

The selected model is **loaded and warmed once per service process**. A single dedicated inference worker reuses it across every stream. For Whisper, the bundled Silero speech filter is also loaded/warmed at startup. Readiness follows successful initialization. Run one process, with no reload or extra Uvicorn workers: extra processes would each allocate another model. Changing models requires restarting the service.

The default is `large-v3`, CPU INT8, four inference threads, beam size one. Optional NVIDIA GPU execution is described below. Configurable multilingual choices are `tiny`, `base`, `small`, `medium`, `large-v3`, and `large-v3-turbo`. Set `AUDIO_MODEL_NAME` in `.env` and download that model before restarting. `AUDIO_MODEL_PATH` accepts a locally converted CTranslate2 model directory. The additional `nemotron-3.5-asr-streaming-0.6b` option uses the resident sherpa-onnx CPU adapter described below.

The standard download uses Hugging Face. If a managed network denies that host, use an approved publisher distribution and local conversion, or provision a previously downloaded CTranslate2 directory. Keep certificate verification enabled.

Whisper's `auto` selection is limited to the service's supported English/Hindi languages. If initial detection selects another language (for example, Urdu for a short Hindi question), the adapter uses the highest-probability supported language before decoding text. Explicit English/Hindi selections stay fixed, and the task remains transcription. Recognition quality still depends on the model and audio; see the [local speech and response review](../../docs/local-speech-response-final-review.md).

## Optional NVIDIA GPU for Whisper

For the standalone service, `AUDIO_GPU_ENABLED=false` preserves explicit CPU INT8 execution. The combined Human-test launcher automatically probes CUDA and writes this flag to match the selected GPU/CPU, so it no longer forces CPU. The probe is available as `.venv/Scripts/python.exe -m device_audio.gpu`; it reports safe device metadata without loading model weights. To enable the NVIDIA GPU for any supported Whisper model on Windows x64, install the optional project-local runtime libraries:

```powershell
uv sync --frozen --extra cuda
```

Set the following in your existing private `.env` and restart the service:

```dotenv
AUDIO_MODEL_NAME=large-v3
AUDIO_MODEL_PATH=.models/large-v3
AUDIO_GPU_ENABLED=true
AUDIO_GPU_DEVICE_INDEX=0
```

Start with `uv run --extra cuda audio-api serve`. Keep `--extra cuda` on future `uv sync`/`uv run` commands for this GPU environment so the optional runtime dependencies remain installed. Set the flag back to `false` and restart to use CPU again; the same downloaded model directory works in both modes. Model weights remain loaded once per service process.

GPU mode uses CUDA `int8_float16` (INT8 weights with FP16 computation for non-quantized operations), one inference worker and the configured beam size. The CPU still handles receiving, voice detection, recording and other service work. Intel integrated graphics are not used by this CUDA adapter. `AUDIO_GPU_DEVICE_INDEX` selects an NVIDIA CUDA device (default 0). Authenticated status and ready/transcript events expose the execution device and compute type. Startup verifies the selected GPU and its compute support, checks the native model's actual device/precision, and warms inference before readiness.

An unavailable GPU, missing CUDA libraries, unsupported precision or insufficient memory fails startup; there is no silent CPU fallback. Windows CUDA DLL discovery uses the installed NVIDIA wheels within this Python environment and modifies only this process's DLL search path. It does not install or replace system drivers. Operator-provisioned CUDA/cuDNN libraries on PATH are also supported. The optional wheels are scoped to Windows x64; other CUDA installations need platform-appropriate vendor libraries and were not tested here.

The current Nemotron adapter remains CPU-only: combining its model name with `AUDIO_GPU_ENABLED=true` is rejected at configuration validation. Leave the flag false for Nemotron. For GPU model measurements and limits, see [Whisper Large-v3 GPU validation](../../docs/whisper-gpu-validation.md).

Runtime requirements and quantized GPU usage are documented by [faster-whisper](https://github.com/SYSTRAN/faster-whisper#gpu) and [CTranslate2](https://opennmt.net/CTranslate2/quantization.html). GPU availability alone does not guarantee that every model/settings combination fits the card; measure the selected configuration.

## Select Nemotron for incremental CPU recognition

The multilingual **Nemotron 3.5 ASR Streaming 0.6B, 560 ms INT8** model is supported alongside every existing Whisper choice. From `device/audio-process`:

```powershell
uv sync --frozen
uv run audio-api download-model --model nemotron-3.5-asr-streaming-0.6b
```

Set these values in the existing private `.env`, keeping your client credentials:

```dotenv
AUDIO_MODEL_NAME=nemotron-3.5-asr-streaming-0.6b
AUDIO_MODEL_PATH=.models/nemotron-3.5-asr-streaming-0.6b
AUDIO_CPU_THREADS=4
AUDIO_STREAMING_QUEUE_MS=5000
```

Then restart with `uv run audio-api serve`. No `AUDIO_ENGINE` setting is required: the model name selects the adapter. `AUDIO_MODEL_PATH` can also be omitted, in which case the name determines its `.models` directory. Clear any stale path override when switching models. Existing operational `.env` files and Whisper defaults are preserved. To switch back, select a downloaded Whisper name and its matching path, then restart.

The installer downloads only the pinned sherpa-onnx multilingual archive, verifies its published SHA-256 and size, copies four allowlisted regular model files, writes a per-file manifest and publishes the complete directory. It retries network GET failures up to three times and refuses an existing destination. Serving never downloads or silently falls back. Use the same account for installation and serving. The package locks sherpa-onnx and a compatible ONNX runtime; on Windows it explicitly loads the environment's ONNX DLL to avoid an older system DLL. No system DLLs are modified.

One recognizer is loaded and warmed at startup. Each connection has its own decoder/cache state, created on the existing serialized native worker. Incoming PCM is passed incrementally in 150 ms blocks; the exported model operates internally at 560 ms cadence. All received samples reach the streaming recognizer, including silence. Recognition state resets at the existing silence/max-duration endpoints or explicit flush, bounding memory. There is no replay of preceding audio. `AUDIO_PRE_ROLL_MS` and `AUDIO_BEAM_SIZE` apply only to Whisper; Nemotron uses greedy decoding. The 560 ms model cadence is not a guaranteed response latency.

The wire protocol and final `transcript`/`delivery`/`complete` events remain compatible; intermediate recognition results are not published, recorded or posted. Hindi/English/auto selection stays in the start message. Nemotron reports `engine=sherpa-onnx`; for `auto`, the `language` field remains `auto` because sherpa strips its language tags. Segments describe the full bounded utterance interval, not word alignment. `inference_ms` sums native work across that utterance, `queue_ms` is its largest block wait, and real-time factor divides summed work by the utterance duration. Synthetic end padding is excluded from input duration and recordings.

`AUDIO_STREAMING_QUEUE_MS` defaults to 5000 and allows 500-30000. Capacity is `ceil(value / 150)` blocks, about five seconds at default with ordinary full blocks; shorter endpoint/control blocks can fill it sooner. Overflow fails explicitly with `audio_backlog`. `AUDIO_CHUNK_QUEUE_SIZE` still controls Whisper. Authentication, session/input limits, inference deadlines, recording privacy, callback rules and failure reporting apply to both engines. No automatic model/cloud fallback is added.

See [Nemotron validation and review](../../docs/nemotron-integration.md) for measured latency, exact transcripts and limitations. Model information: [NVIDIA model card](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b) (OpenMDW-1.1 model license), [sherpa-onnx export](https://k2-fsa.github.io/sherpa/onnx/nemo/nemotron-streaming.html). Accuracy on natural clinical Hindi/English/Hinglish remains an acceptance task.

## Optional Vosk CPU streaming

Vosk is an optional dependency and uses separate English/Hindi models. This adapter has passed mocked API/regression checks; real recognition, model-archive installation and accuracy/latency validation are **pending** because the managed network blocked the model downloads. Do not use this status as measured performance evidence. See [Vosk validation status](../../docs/vosk-validation.md).

```powershell
uv sync --frozen --extra vosk
uv run --extra vosk audio-api download-model --model vosk-model-small-en-us-0.15 --vosk-source huggingface
uv run --extra vosk audio-api download-model --model vosk-model-small-hi-0.22 --vosk-source huggingface
```

`--vosk-source huggingface` selects the pinned public Rhasspy mirror. Omit the option for the original Vosk host. Both paths check the publisher's archive size and MD5 before extracting only allowlisted regular files; a local SHA-256/per-file manifest is recorded. MD5 is the publisher's available checksum, not a signature. There are up to three retries for transient GET failures; permission failures and checksum mismatches fail immediately. Existing directories are never overwritten. No download happens during serving and no Hugging Face credentials are sent by this installer.

Select **one** model and matching path in your private `.env`, then restart:

```dotenv
AUDIO_MODEL_NAME=vosk-model-small-en-us-0.15
AUDIO_MODEL_PATH=.models/vosk-model-small-en-us-0.15
AUDIO_GPU_ENABLED=false
```

Start with `uv run --extra vosk audio-api serve`. If preserving the installed Whisper GPU dependencies in the same environment, use **both** `--extra vosk --extra cuda` on `uv sync`/`uv run`. Selecting an extra only installs dependencies; `AUDIO_MODEL_NAME` selects the engine. CPU-only Vosk installations require no CUDA packages.

For English, send `{"type":"start","language":"en"}`. To recognize Hindi, select `vosk-model-small-hi-0.22`, use its matching path and send `language=hi`. Model switching requires restart. These are monolingual models: `auto` and the other language are rejected with `unsupported_language` before recording or audio acceptance. Authenticated status/ready expose `supported_languages`. Automatic bilingual detection/Hinglish support is not claimed.

One resident model is warmed at startup, with separate native recognizers per session/utterance on the serialized worker. Audio is decoded incrementally in the existing 150 ms blocks. Vosk's earlier internal endpoints are accumulated through the service endpoint/flush so completed phrases are not lost. Only final transcripts are delivered/recorded. Existing authentication, timeouts, bounded queues, recording and callback rules apply. Segments represent the bounded utterance, not word alignment.

`engine=vosk`, `device=cpu`, `compute_type=model_default`; status reports `cpu_threads=null` because Vosk Python exposes no corresponding per-recognizer thread option. `AUDIO_CPU_THREADS`, `AUDIO_BEAM_SIZE` and pre-roll do not configure this adapter. Queue/utterance/silence settings still apply.

Vosk's standard Windows wheel has no working CUDA decoder. `AUDIO_GPU_ENABLED=true` is rejected explicitly for Vosk; installing the Whisper `cuda` extra does not change that. Its separate CUDA build/batch API is not implemented by this adapter. See the [official build instructions](https://alphacephei.com/vosk/install). Existing Whisper CPU/GPU and Nemotron options are preserved.

## Connect a Pi over Wi-Fi

1. Configure `AUDIO_TLS_CERT` and `AUDIO_TLS_KEY` with a certificate/key for the laptop address. The Pi must trust the issuing CA and verify the hostname/IP.
2. Set `AUDIO_HOST=0.0.0.0` in the laptop's `.env`. Non-loopback binding requires TLS. Restrict the Windows firewall port to the intended local clients.
3. Provision the Pi's distinct local token from `AUDIO_CLIENT_TOKENS`. Send it in an `Authorization: Bearer ...` header. Platform device credentials are unrelated and must not be reused here.
4. Connect to `wss://<laptop-address>:8765/v1/audio/stream`.

Use `ws://127.0.0.1:8765/v1/audio/stream` for testing on the laptop itself. Plain remote WebSockets are rejected. Browser-origin requests and tokens in URLs are unsupported.

A paced WAV sender is included; it requires only Python and `websockets>=15,<18` on the sender, not the inference dependencies. Configure `AUDIO_CLIENT_TOKEN` in that process's environment without putting it in command history. Then run:

```powershell
uv run python scripts/stream_wav.py --audio sample.wav --language auto
```

For a Pi or another machine, use its Python environment and add `--url wss://<laptop-address>:8765/v1/audio/stream --ca-file <trusted-ca.pem>`. The sample must be mono, 16 kHz, signed PCM16 WAV. The sender removes the WAV header and streams raw PCM. Live microphone capture/resampling on the Pi is a later adapter. The sender bounds connection/start/send/close waits with `--io-timeout` (five seconds), and waits at most `--completion-timeout` (310 seconds) after finish for a matching completion event. A normal connection close without that event is a failure. It prints the initial session receipt immediately, cancels sibling tasks on failure, and never automatically replays audio. Increase the completion deadline when increasing the server drain limit.

## Streaming protocol, version 1

Authenticate the WebSocket handshake, then send this text frame:

```json
{"type":"start","version":1,"format":"pcm_s16le","sample_rate":16000,"channels":1,"language":"auto"}
```

An optional UUID `stream_id` identifies the caller's stream. It is correlation metadata, not a platform run ID or an idempotency key. Language is `auto`, `hi`, or `en`; transcription preserves speech rather than requesting translation. Mixed Hindi/English accuracy must be evaluated with representative recordings.

Wait for a `ready` event before sending audio. Send binary frames of **raw signed 16-bit little-endian, 16 kHz mono PCM**. A 100 ms frame contains 3,200 bytes. Each frame must be nonempty, sample-aligned, and no larger than the advertised `max_frame_bytes` (16,000 by default). Containers, compressed audio and arbitrary sample rates are not accepted.

- `{"type":"flush"}` closes the current speech chunk and keeps capture open.
- `{"type":"finish"}` ends capture and drains accepted chunks and delivery notifications.
- `transcript` events contain `text`, language, sequence, server-generated event/session IDs, client/stream IDs, UTC creation time, model/engine, absolute audio offsets, segments, inference/queue milliseconds and real-time factor.
- `chunk_skipped` means the recognizer returned no speech.
- `delivery` reports console and optional HTTP delivery for an event.
- `complete` contains counts and total input duration; the server then closes normally.
- `error` gives a stable code such as `audio_backlog`, `audio_limit`, `invalid_start`, `invalid_control`, or `inference_timeout`.

Read events while sending audio. Transcripts are final for each speech chunk, not continuously revised partial words. Speech ends after 600 ms of silence or at the configured eight-second limit; hard cuts can split a word and currently have no overlap/context reconciliation.

Unauthenticated or excess concurrent connections are rejected during the handshake. One client token may have one active stream; the service permits two streams by default, sharing one serialized model worker.

## Console output and future text receiver

`AUDIO_CONSOLE_OUTPUT=true` prints each recognized text on the laptop console as requested. This intentionally exposes transcript text to whoever can view or collect that console. Set it to `false` to suppress console text; stream output and configured recording remain available. Routine service logs contain no transcripts, credentials or callback URLs; audio/transcript recording is described below.

Leave `AUDIO_CALLBACK_URL` unset for now. Later, configuring a fixed operator-selected URL enables a JSON POST for each nonempty transcript:

```dotenv
AUDIO_CALLBACK_URL=https://your-selected-receiver.example/transcripts
AUDIO_CALLBACK_TOKEN=<receiver-token-if-required>
```

The body is the same `transcript` event returned to the Pi, including `text`. The server-generated `event_id` is sent as `Idempotency-Key`; the receiver should use it for deduplication. Audio clients cannot choose a destination. Non-loopback receivers require HTTPS; redirects and environment proxy inheritance are disabled.

Console/HTTP delivery uses a separate bounded queue so a slow receiver does not block inference. Delivery status is `not_configured`, `delivered`, `rejected`, `unknown`, `queue_full`, or `not_sent`. Console status reports `printed`, `disabled`, `failed`, or `unknown`. Queue overflow is reported. Console output has its own serial daemon worker and uses the callback timeout as a separate print deadline. A stalled print reports `unknown`, retires console output until restart, and allows HTTP delivery to continue; that print may finish later and is never replayed. Safe pre-submission connection retries are bounded as described below; uncertain submissions are never automatically replayed and there is no durable callback outbox.

Ordering is represented by sequence and audio offsets; concurrent delivery workers can complete HTTP requests out of order. A disconnected stream cancels pending inference requests, but an already queued/submitted delivery may still complete. Reconnecting does not resume a prior stream and resending audio can duplicate text.

## Local audio and transcript recordings

Recording is enabled by default. The laptop stores accepted input audio, including silence, and final transcript events in a private local directory:

```text
.recordings/<server-session-id>/
  audio.wav          # original accepted PCM in a mono 16 kHz PCM16 WAV
  transcript.jsonl   # UTF-8 transcript events, including Hindi, timing and model
  session.json       # recording status, ownership, counts and failure reason
```

The server generates the directory ID; clients cannot supply paths or change storage settings. A successful recording preserves the entire accepted input, not just speech selected for inference. Transcripts retain their audio offsets and sequence numbers. Empty/silent sessions can have an empty transcript file. These recordings stay on the laptop.

Audio reception and transcript delivery only submit references to a bounded queue. One separate disk thread handles WAV writing, JSON encoding, flushing, retention and finalization; the model stays loaded and reused. The stream does not wait for disk writes. Background work still consumes some resources, so zero added latency is not guaranteed.

Both `ready` and `complete` include a `recording` object. Its `id` is the server session ID. A `complete` event completes transcription and can report recording `pending`; it does **not** promise that files are already saved. Poll `GET /v1/recordings/<id>` with the same local client token until `finalized=true`, then inspect `saved` or `incomplete`, the component completion flags and its reason. Active recordings report `recording`; configuration can report `disabled`. Other clients and unknown/expired IDs receive 404. This endpoint returns metadata only, without audio, text, local paths or credentials. There is no media download/list endpoint.

The defaults are configurable in `.env`:

| Setting | Default | Purpose |
|---|---|---|
| `AUDIO_RECORDING_ENABLED` | `true` | Enable local recording |
| `AUDIO_RECORDING_DIR` | `.recordings` | Dedicated directory, relative to the service working directory |
| `AUDIO_RECORDING_MAX_BYTES` | `1000000000` | 1 GB total accounting cap, including reserved metadata overhead |
| `AUDIO_RECORDING_RETENTION_HOURS` | `168` | Seven days from session creation |
| `AUDIO_RECORDING_MAX_SESSIONS` | `1000` | Stored session count limit |
| `AUDIO_RECORDING_QUEUE_BYTES` / `AUDIO_RECORDING_QUEUE_ITEMS` | `2097152` / `256` | Queued work bounded by bytes and event count; bytes include in-flight work and conservative text allowance |
| `AUDIO_RECORDING_PENDING_SESSIONS` | `8` | Maximum sessions awaiting recording completion |
| `AUDIO_RECORDING_MIN_FREE_BYTES` | `67108864` | Keep at least 64 MiB free on the volume |
| `AUDIO_RECORDING_FLUSH_SECONDS` | `1` | Periodically flush buffers and update WAV length |
| `AUDIO_RECORDING_CLEANUP_SECONDS` | `60` | Expiry cleanup interval while the service runs |
| `AUDIO_RECORDING_STARTUP_SECONDS` / `AUDIO_RECORDING_SHUTDOWN_SECONDS` | `5` / `5` | Storage startup deadline; separate shutdown bounds for queue drain and disk-thread exit |

Oldest finished sessions are removed when expired or needed to admit new data within the size/count limits; active recordings are protected. Retention also runs at startup. It does not run while the service is stopped. Space accounting reserves 16 KiB per session for metadata and atomic updates; buffered data and partial failed writes remain charged. Raw audio is about 32 KB/second, or 19.2 MB for the existing ten-minute stream maximum, before metadata.

If the queue fills, recording stops accepting further data for the affected component, preserves its already queued prefix, and reports `incomplete` with `recording_queue_full`. The other component can continue within the same bounds. Disk, quota or permission failures also mark the session incomplete; transcription continues. Safe disk retries and component fallbacks are described below. Abrupt disconnects retain available data with `stream_interrupted`. An unavailable recording directory leaves ASR ready but reports recording unavailability in `ready` and authenticated `GET /v1/status`.

The initial on-disk manifest is incomplete. Final `saved` status is written only after file completion, flush and filesystem sync. A crash can lose buffered data; restart repairs an unfinished WAV header, discards a partial final JSONL line, and keeps the recording incomplete. Counts recovered after interruption describe persisted data; exact pre-crash receive counts are not recoverable. Size mismatches in previously saved files are also marked incomplete. Restart removes empty initial session directories or a bounded partial initial manifest only when no media was created; unexpected orphan media is preserved and storage initialization is refused. A permanently stalled OS write has bounded shutdown waits and may leave unfinished data for restart recovery.

Use a dedicated local folder. The service refuses unmarked nonempty directories, redirected paths, hard-linked files, unexpected contents and a second writer using the same store. Windows directory permissions are restricted to the running account and SYSTEM; POSIX directories use mode 0700. Files are local plaintext protected by filesystem permissions, not encrypted by this package. The recording directory and private settings are excluded from source control and built packages. These local client permissions are separate from future PMS tenant/device authorization.

### Retries and fallback behavior

Retries are bounded and apply only where the operation can be repeated safely. They run in the disk/delivery workers; audio reception and inference do not wait for their backoff.

| Failure | Recovery |
|---|---|
| Transient local file creation, write, synchronization or atomic-manifest error | Up to three attempts per operation, with roughly 50 ms then 100 ms backoff and 20% jitter |
| Partial audio/text write | Repeat the bytes at the same file offset; complete short writes, charge storage once and stop that file after exhaustion |
| Permission denial, full disk, quota limit, unsafe path or invalid input | Fail explicitly; these are not repaired by repeating the same operation |
| Audio writing/admission fails after the session files open | Preserve its accepted prefix and continue saving transcript events if their file and the existing limits allow |
| Transcript writing/admission fails | Continue audio recording if its file remains usable |
| Both files/storage initialization fail | Keep returning transcript events and configured console output; report recording failure |
| Callback connection or connection-pool failure before POST submission | Up to three attempts using the same event ID/body; roughly 200 ms then 400 ms backoff with 20% jitter, within the existing five-second total callback deadline |
| Callback read/write timeout, uncertain submission, response-cleanup error or HTTP rejection | Report the outcome without automatic replay; the future receiver's reconciliation/idempotency contract must resolve uncertain delivery |

`AUDIO_RECORDING_RETRY_ATTEMPTS` and `AUDIO_RECORDING_RETRY_DELAY_SECONDS` configure disk retry count/base delay. `AUDIO_CALLBACK_RETRY_ATTEMPTS` and `AUDIO_CALLBACK_RETRY_DELAY_SECONDS` configure callback retries. Attempt counts include the initial attempt; setting them to one disables retries. Existing queue, byte, session, quota, startup and shutdown limits still apply. Normal successful operations incur no retry sleep. The OS itself can still stall a disk call; the existing bounded shutdown waits remain relevant.

Recording receipts expose `fallback` (`none`, `transcript_only`, `audio_only`, or `stream_only`), `audio_complete`, `transcript_complete`, and `finalized`. During processing, `fallback` describes the remaining storage path, not a durability promise. Poll until `finalized=true` before evaluating the component completion flags. Overall `status` stays `incomplete` whenever part of the accepted session was lost, even if its transcript was fully saved. Component completion means all accepted data for that component was finalized; a disconnected stream still has an incomplete overall session. An `incomplete` receipt with `finalized=false` can still be draining fallback data. Old interrupted data cannot be reconstructed by retrying.

Queue overflow stops new admissions only for the affected component, while its already queued prefix drains. Other-component data can be admitted when capacity becomes available; there is no extra unbounded fallback queue or automatic catch-up after a gap. Transcript-only storage shares the same private directory and quotas. If there is insufficient space even for text, its status also becomes incomplete.

Authenticated `GET /v1/status` exposes recording retry/exhaustion counters and callback retry counts. Each `delivery` event includes its HTTP attempt count. Console output occurs once per event, before callback retries. Callback failure does not redirect text to an unconfigured destination; the stream and independently configured local recording remain available.

Whole store initialization is not blindly repeated after an uncertain startup, and permission/ownership errors require correction followed by service restart. Retention already runs on its bounded periodic schedule. Expensive model inference is not automatically repeated or switched to another model/cloud provider; the selected model stays loaded and processing failures remain explicit. The callback is still disabled until an endpoint is configured.

## Voice activity detection

Segmentation uses one of two detectors. `AUDIO_VAD_ENGINE=silero` is the default: the neural Silero v6 detector, whose 1.2 MB ONNX weights already ship inside the installed `faster-whisper`, so nothing is downloaded. `AUDIO_VAD_ENGINE=webrtc` selects the previous energy detector and `AUDIO_VAD_AGGRESSIVENESS` still applies to it. `AUDIO_VAD_THRESHOLD` (default 0.5) is the Silero speech probability; raise it in a noisy room, lower it for quiet speakers. `AUDIO_VAD_MODEL_PATH` optionally overrides the weights and is rejected at configuration validation if the file is absent or the engine is not `silero`. Neither engine falls back to the other: a configured engine that cannot start is a startup failure.

The detector chooses utterance boundaries only; it never alters a sample, and framing stays at 30 ms, so `AUDIO_PRE_ROLL_MS`, `AUDIO_SILENCE_MS` and `AUDIO_MIN_SPEECH_MS` keep their existing meaning. The default changed because the energy detector scores every frame as speech below roughly 10 dB SNR, so `AUDIO_SILENCE_MS` never elapses and questions end at `AUDIO_MAX_CHUNK_SECONDS` instead of at the speaker's pause. Measured segmentation, cost, onset lag and the limits of that measurement are in [the VAD engine comparison](../../docs/vad-engine-comparison.md); it used synthesised speech and synthetic noise, not a room recording.

## Performance and limits

The receiver, CPU inference worker, delivery workers and recording disk writer run independently. Native inference stays serialized even when a client disconnects or its request times out. This avoids starting another CPU-heavy inference while a cancelled native call is still running.

For Whisper, the default per-stream queue holds two speech chunks; the shared inference queue holds at most the configured session count. Incoming overload fails explicitly with `audio_backlog` instead of accumulating unlimited latency. Speech and silence both count toward the ten-minute input cap. Sessions have a fifteen-minute capture deadline, a thirty-second idle timeout, and at most 1,024 controls. Python cancellation cannot safely terminate native inference. Startup/model warmup is bounded by `AUDIO_MODEL_LOAD_TIMEOUT_SECONDS` (180 seconds). Shutdown stops new admissions and waits at most `AUDIO_INFERENCE_SHUTDOWN_SECONDS` (five seconds) for inference, then retires that runtime and resolves unfinished callers with `service_stopped`. A native call may remain in its daemon thread until it returns or the process exits; the retired runtime cannot start another model. The CLI also bounds Uvicorn connection shutdown separately, while disk and delivery workers retain their own shutdown deadlines. These limits are not a guarantee of total process shutdown time.

The inference/queue timeout now starts when a speech chunk enters the stream queue. Expired queued chunks are rejected before inference. A native call that exceeds the same configured execution limit retires its worker, fails readiness and exposes `failure=native_inference_timeout` in authenticated status; it never starts a replacement model alongside the blocked call. Restart the process after resolving the cause.

Other defaults include a 180-second inference/queue timeout, 300-second finish-drain timeout, five-second send/opening/closing-handshake timeout, and eight queued console/HTTP events with two delivery workers. [Settings](src/device_audio/config.py) defines every bound; [.env.example](.env.example) lists the common controls. Hard chunk limits round up by at most one 30 ms detector frame.

RAM capacity alone does not establish real-time performance. Benchmark the selected model on the intended laptop with representative Hindi, English and mixed speech, including noise and continuous speech. CPU thread count, beam size, chunk size and model choice affect the tradeoff. The service does not silently substitute a smaller model or send audio to cloud processing.

For a local 0-30 second PCM16 WAV:

```powershell
uv run audio-api benchmark --audio sample.wav --language hi --output benchmark.json
```

This separate benchmark command loads one model for its own process and reports startup/warmup time and inference real-time factor (inference seconds / audio seconds). A factor below one indicates faster-than-audio processing for that clip, excluding capture/silence, network and queue delay. The serving process exposes per-chunk queue/inference timing and authenticated aggregate metrics at `GET /v1/status`. `GET /health/ready` also requires the local token; `GET /health/live` returns minimal public liveness.

## Verified local model setup (2026-09-17)

This checkout already has a private `.env` and the converted `large-v3` model. From this directory, start it with `uv run audio-api serve`. The verification servers were stopped after testing.

The managed network denied Hugging Face. The official [OpenAI Whisper checkpoint source](https://github.com/openai/whisper/blob/main/whisper/__init__.py) supplied the original Azure-hosted `large-v3` checkpoint instead. Its SHA-256 matched `e5b1a55b89c1367dacf97e3e19bfd829a01529dbfdeefa8caeb59b3f1b81dadb`. A separate conversion environment used the official Transformers weight mapping, OpenAI tokenizer assets and CTranslate2 conversion code. The converted INT8 weights are about 1.55 GB in `.models/large-v3`, with local tokenizer/configuration files and a checksum manifest. The verified source checkpoint is retained in `.models/original`; temporary range-download files were removed.

Real loopback streaming with this model produced the expected synthetic English transcript and console text in two streams per trial, with **one model load per service process**:

| CPU threads | Load + warmup | Stream completion, two trials | Peak process working set |
|---|---|---|---|
| 4 (default) | 15.77 s | 39.17 s / 39.41 s | 3.23 GB |
| 8 | 15.37 s | 39.78 s / 35.71 s | 3.23 GB |

Each input was 8.55 seconds, split into three speech chunks. Completion is measured from the start of streaming after readiness. These are illustrative local checks on Windows / Intel Core Ultra 7 165H / **64 GB installed RAM**, not controlled performance benchmarks or verification on the intended 16 GB machine. `large-v3` is working but is **not real-time with these settings**. Short chunks repeatedly pay the Whisper encoder cost. Keep the model selectable and evaluate turbo/smaller models or utterance batching for a lower-latency profile; do not infer speed or Hindi/mixed-speech accuracy from this English sample.

Ignored local evidence is in `.test_artifacts/device-audio` at the repository root. The recorded raw queue timings preceded the later per-stream queue-metric fix; stream completion, inference timing, text, model reuse and memory measurements are unaffected. The current API includes both per-stream and shared-worker waiting in `queue_ms`.

### Recording latency comparison

These measurements preceded the retry/fallback update. That update was checked with fault-injection and transport tests; this native timing comparison has not been rerun.

A follow-up used the same installed model, four CPU threads and one model load across four paced loopback streams, with recording off/on/on/off. Console output was disabled in both modes. Each input was the same 8.55-second synthetic English clip; recording completion was checked separately after the transcription timer.

| Recording | Stream completion, two trials | Mean |
|---|---|---|
| Off | 51.50 s / 51.52 s | 51.51 s |
| On | 53.58 s / 51.22 s | 52.40 s |

The observed mean difference was 0.89 seconds (1.7%). Two trials per mode cannot separate recording overhead from scheduling/thermal variation or guarantee zero latency impact. All four transcripts matched; both stored WAVs matched the original PCM byte-for-byte, and every saved transcript matched its stream event. Each stream reported recording `pending` before its separate status reached `saved`. The model loaded once (21.36-second startup/warmup). A deterministic blocked-disk regression also confirms transcript, completion and health/status responses do not wait for storage.

These trials used the same 64 GB Windows host described above; the model remains far slower than real time in this configuration. They do not verify the 16 GB target, Hindi/mixed-language recognition or Pi/Wi-Fi behavior. Script and timing report: `.test_artifacts/device-audio-recording` at the repository root. Two synthetic sample sessions were retained in the ignored private `.recordings` directory. The verification server was stopped.

## Verification and scope

```powershell
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src/device_audio
uv lock --check
uv build
```

Tests use deterministic speech detection and fake recognizers to check protocol errors, model reuse, Hindi text preservation, cancellation, concurrency, queue limits, callbacks and real loopback HTTP/WebSocket transport. Recording tests cover exact audio/Unicode text, blocked-disk responsiveness, queue and quota limits, partial writes, client scope, retention, disconnects, restart recovery, startup/shutdown timeouts, directory ownership, Windows permissions and unsafe paths. Retry regressions inject short/partial disk writes, transient/permanent failures, atomic-replacement uncertainty and callback failures before/after submission; they assert bounded attempts, no duplicate data, fallback completeness, restart behavior and deadlines. Final-review regressions also cover stalled model loading/inference/console output, private credential creation, abandoned initial manifests, and missing or invalid sender completion. No test automatically downloads weights or calls a cloud provider.

This is a single trusted local installation with operator-managed tokens. It does not enforce PMS tenant membership, device lifecycle, profile revisions or offline authorization; platform integration must supply those controls before tenant operation. That integration, Pi hardware, Wi-Fi/TLS deployment and Hindi/English quality benchmarks remain separate verification work.

See the [service plan](../../docs/platform-service-plan.md#71-how-the-raspberry-pi-will-work), [TODO](../../docs/pms-api-todo.md#pi-inputoutput-and-laptop-transcription-follow-up), and [review evidence](../../docs/pms-api-reviews.md).


## Local transport decision

This service already streams binary audio over TCP through WebSocket; Wi-Fi uses WSS
with TLS. The reference sender transmits PCM while receiving transcripts concurrently.
Keep its connection separate from video, and retain bounded buffers and application
save receipts. A raw TCP listener is not currently justified. See the [transport
assessment](../../docs/local-media-transport.md) for protocol overhead, reliability
boundaries and the measured video-sender improvement. No audio runtime, inference or
recording behavior changed in that transport follow-up.

## Deep latency review (2026-09-19)

See the [audio review and native measurements](../../docs/audio-latency-review.md) for findings, fixes, timing definitions and remaining acceptance work. Fresh synthetic loopback tests on the available 64 GB CPU host measured roughly 2.1-5.3 seconds after input for small, versus 12.2-35.7 seconds for large-v3. These are not target-16GB, human accuracy or Pi/Wi-Fi results. The selected model and private settings remain unchanged.

The [medium/turbo CPU comparison](../../docs/whisper-model-comparison.md) adds actual human Hindi/English quality scores and paced API timings for small, medium, large-v3-turbo and large-v3. Both new models were provisioned in this workspace; weights remain local ignored assets. The report includes selection settings, transcript examples and the remaining live-conversation acceptance limits.


## Optional Whisper Medical (English)

Run `setup-medical.bat` for an isolated conversion environment and verified download/conversion of `Crystalcareai/Whisper-Medicalv1`. Select `AUDIO_MODEL_NAME=whisper-medical-v1` and remove stale `AUDIO_MODEL_PATH` overrides (or use `.models/whisper-medical-v1`). Start streams with `language=en`; Hindi/auto are rejected. CPU/GPU remains controlled by `AUDIO_GPU_ENABLED`. Runtime reuses the existing resident faster-whisper worker; no Torch/Transformers dependency is added to serving.

`audio-api download-model --model whisper-medical-v1` also supports this selection if the optional converter dependencies are installed in that environment; the batch script preserves the lean serving environment. Repeat installs verify/reuse the completed conversion. The checkpoint revision is fixed and source/converted hashes are checked.

**Current machine: downloads are blocked; native medical inference/latency/accuracy is unverified.** See [medical setup and validation](../../docs/medical-models.md). Existing multilingual models remain available for Hindi and mixed speech.
