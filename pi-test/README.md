# Pi-test

A headless Raspberry Pi host for the existing `training-client` package. The Pi
captures microphone/camera input, plays audio and keeps bounded private upload
queues. Local model execution means **a separate GPU machine** running
`local-models` behind its TLS inference gateway. The Pi installs no model weights.

The service starts idle. Starting a practice session and starting microphone or
camera capture are separate explicit commands. There is no desktop, browser UI,
display server or inbound network control port on the Pi.

## Layout and ownership

| Component | Responsibility |
| --- | --- |
| `pi_test` | Service lifecycle, local control socket, diagnostics, Pi hardware |
| `training-client` | Conversations, routing, assigned sessions, microphone endpointing, playback, durable archives |
| `local-model-client` | Bounded HTTPS/WSS transport and private request-status journal |
| `local-models/gateway` | TLS ingress, platform grant verification, replay protection and admission |
| Platform API | Existing enrollment, models, published scenarios, leases, cloud processing; new inference grants |

See [architecture](docs/architecture.md), [phase tracking](docs/todo.md),
[operations](docs/operations.md) and [compatibility/evidence](docs/compatibility.md).
The subsequent implementation phases and reviews are tracked in
[completion plan](docs/completion-todo.md) and [completion evidence](docs/completion-review.md).
See the [final Pi-specific review](docs/final-review.md) for the latest fixes and bundle.

## Develop without a Pi

Use Python 3.12 or 3.13. From `pi-test`:

```text
uv sync --group dev
uv run pytest -q
uv run pi-test --help
```

Copy `deployment/config.example.toml` to a development file and set absolute
`app_root` and `control_dir` paths. Use forward slashes in TOML Windows paths.
The Windows fallback is an authenticated loopback socket with a private descriptor;
Linux uses a Unix socket restricted to the service account.

```text
pi-test --config development.toml doctor
pi-test --config development.toml enroll --device DEVICE-UNIQUE-ID
pi-test --config development.toml serve
```

Enrollment reads the token with a hidden prompt. Never place tokens in command
arguments or source-controlled TOML. Restart the service after enrollment or config
changes. Run control commands as the same OS account, in another terminal.

## Raspberry Pi installation

Target Raspberry Pi OS Lite Trixie **64-bit**, with OS Python 3.13. Install OS
packages `python3-venv` and `libportaudio2`; CSI additionally needs `rpicam-apps-lite`.
Audio devices must work through ALSA without a desktop session. Choose exact device
names with `pi-test audio-devices`.

On a build machine with `uv` and `pip`, create an ARM64 wheelhouse:

```text
python pi-test/deployment/build_wheelhouse.py --output .test_artifacts/pi-release --python-version 313
```

Copy the deployment scripts and complete wheelhouse to the Pi, then run:

```sh
sudo sh install.sh 0.2.0 /path/to/wheelhouse
sudo -u pi-test /opt/pi-test/current/bin/pi-test enroll --device DEVICE-UNIQUE-ID
sudo systemctl restart pi-test
sudo -u pi-test /opt/pi-test/current/bin/pi-test status
```

Edit `/etc/pi-test/config.toml` before enrollment. Grant the service account access
to audio/video/render devices; the installer creates those group memberships.
Do not install a replacement Python interpreter for the CSI stack.

Installation is offline, wheel-only and hash-checked. Each release gets a separate
venv. `rollback.sh VERSION` switches executables while preserving identity and
queued archives. `uninstall.sh` unregisters the service and preserves private data.

## Inference setup

For cloud models, assign supported models through the existing platform workflow.
ASR/LLM use the shared platform routes; cloud speech output uses device processing
runs. Cloud credentials stay encrypted on the platform.

For a GPU machine, configure the [inference gateway](../local-models/gateway/README.md).
The platform device's audited `details.inference` value and the Pi configuration
must agree on the HTTPS origin and host UUID. The platform training Ed25519 signing
key must be configured. The GPU gateway pins its public key out of band.

The existing tenant-scoped device PATCH accepts this additional validated field:

```json
{
  "expected_etag": "CURRENT_MANAGEMENT_ETAG",
  "details": {
    "inference": {
      "host_id": "00000000-0000-4000-8000-000000000001",
      "origin": "https://gpu.example.lan:8791",
      "tts_voices": ["en_US-lessac-medium"],
      "video_transport": false
    }
  }
}
```

Use actual installed voice keys from the manager. Model selection remains platform
controlled. The binding authorizes a host and local voice keys; it never contains a
manager key, provider key or TLS private key. Clear it with `"inference": null`.
No database migration or UI modification is needed.

## Practice commands

```sh
pi-test scenarios
pi-test config-check
pi-test probe
pi-test begin --scenario PUBLISHED-SCENARIO-UUID
printf '%s' 'What brought you here?' | pi-test text
pi-test listen
pi-test send-now
pi-test pause
pi-test resume
pi-test camera-start
pi-test camera-process
pi-test result
pi-test camera-stop
pi-test finish
```

An assigned session takes priority; use `begin` without a scenario for that case.
Published scenarios need baseline vitals and the configured language. Commands
that submit long work return an acceptance acknowledgement; inspect `status` for
completion/errors. `pause` stops microphone, playback, camera and video transport;
`finish` also closes the conversation. Platform remote-stop and lease expiry use
the same shared session supervisor as Human-test.

`stream_audio=true` sends microphone frames while an utterance is being captured.
Whisper finalizes only after a clean end marker; partial transcripts are not supported.
Loss, timeout or cancellation aborts that utterance without replay. Audio at 44.1/48 kHz
is normalized to mono PCM16 at 16 kHz. Named inputs must match exactly and uniquely.

`camera-process` uses the platform's assigned video task: `video.motion` with
`opencv_motion` executes on the remote gateway; `video.labels` uses the platform's
AWS Rekognition or Azure Video Indexer processing path. No model runs on the Pi.
Clips are bounded to 30 seconds, 5 fps and the platform's tighter policy. Cloud clips
contain video only; the full session recording keeps its independent private archive.
Motion observations describe visual changes and never change patient scenario facts.
Listening and camera processing can run concurrently. `camera-stream` remains a
transport diagnostic and returns `inference: unsupported` without reserving a processing run.

`result` returns the last command result through the private control channel for up
to five minutes. `processing-requests` lists durable metadata; `processing-status
--run-id ID` reads an owned run without submitting it again. Operational status and
logs exclude result text. Use `reload` while idle to refresh platform configuration;
restart the service to apply TOML or enrolled credential changes. `listen_on_begin`
can start listening after an explicit successful `begin`; boot always stays idle.

There is no automatic inference retry after an uncertain response. Use
`inference-requests` to list recent request IDs and `inference-status --request-id ID`
to query the gateway's owner-scoped receipt. Receipts contain status only, not the
answer. Restart never resumes capture or replays a question.

The [end-to-end client review](../docs/client-e2e-review-20261011.md) records the
latest fixes, actual verification and current ARM64 bundle. While a session finish
awaits platform confirmation, new capture and inference remain blocked; `pause`
does not clear that barrier. Retry `finish` after connectivity returns.
