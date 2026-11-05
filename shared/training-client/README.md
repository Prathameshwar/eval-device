# Training client

Shared patient-practice runtime used by Human-test and the headless `pi-test`
device service. It contains no Tk dependency, model weights, inference
engine, platform server or Raspberry Pi daemon.

`training-contracts` remains the shared conversation/schema implementation.
`local-model-client` remains the inference-only transport. Platform credentials
and assigned model/case revisions continue to govern client operations. Choosing
local inference does not enable disconnected practice: current conversation and
assigned-session authorization still require the platform.

## Hosts and lifecycle

Create `Settings(app_root=...)` with an explicit writable application directory
and provisioned device identity. The core reads `TRAINING_CLIENT_` environment
variables and does not load a desktop `.env`. Human-test subclasses these settings
to retain its `HUMAN_` variables, existing application directories and optional
detached upload helper. The shared default keeps uploads in the host process.

Pairing is available through `connection.PairingClient(origin, path=...)`; the
caller supplies its private connection-file path. Use `connection_values()` to
map a validated paired identity into settings. Provider secrets remain on the
platform; GPU manager operator credentials never belong in a device client.

Call runtime operations on one asyncio event loop:

```python
from training_client.runtime import Runtime

runtime = Runtime(settings, observe=on_event)
try:
    catalog, saved = await runtime.prepare()
    # Apply an explicit operator/host selection, or begin the assigned session.
    await runtime.save_selection(selection_payload, scenario=True)
    await runtime.listen()
finally:
    await runtime.close()
```

`text_turn(text)` submits a standalone typed turn or adds it to the active
microphone queue. `enqueue_text(text)` adds to an existing queue synchronously on
that same loop. `pause()` interrupts pending playback and the active runtime
operation. `send_now.set()` requests the current utterance's explicit endpoint.
No microphone/camera opens merely because a runtime is constructed or prepared.

`reload_models()` and `reset_conversation()` use the same operation/session guards
as the other runtime actions. They stop playback and await camera finalization
before changing conversation/archive context; so do preparation and selection
changes. New typed input interrupts previous playback inside the runtime, including
when added to the listening queue. After `close()`, create a new runtime to restart;
the closed instance cannot start polling, work or camera capture again.

For assigned practice, `runtime.sessions.next` exposes the next assignment and
`await runtime.sessions.begin()` claims and prepares it. `finish(outcome)` stops
work before acknowledging completion. The supervisor owns polling, deadlines,
remote-stop handling and finish retries independently of any frontend timer.
An application must decide how the operator authorizes Begin; startup alone does
not begin a trainee session.

Events are notifications. Playback executes inside the runtime; observer failure
does not disable playback, persistence or session shutdown. The observer should
enqueue quickly and never access widgets from a runtime/audio worker thread.
`speech_started` reports an accepted playback request; it is not a command to
play the audio again. `observer_failures` counts failed notifications without
logging sensitive payloads or exception text.

Use one runtime per device identity. Its inference connection and capability
cache are instance-owned. Recreate/close the runtime when credentials or device
identity change; mutating an existing HTTP client's token is not supported.
Conversation contexts retain the validated immutable snapshots in
`training-contracts`.

## Hardware and persistence

Install the `audio` extra for the sounddevice adapter and `camera` for the
OpenCV/PyAV recorder. Neither extra is needed merely to import the core.
`Listener(source_factory=...)` accepts a context-managed source returning the
bounded queue of mono 16 kHz PCM16, 50 ms frames and updating capture-loss
metadata. Alternative sources must normalize to that contract; endpointing,
speech quality and overload handling stay in the shared listener. A runtime may
receive a listener factory and a speaker implementation for another device or
for deterministic tests. `Speaker` also accepts an injected playback engine.

When a question exceeds the duration/loss limit or the queue is full, the listener
discards the remainder until a full silence interval. It never submits the tail of
that rejected sentence as a separate question.

`runtime.camera.start(Options.from_settings(settings, index), sync=...)` starts
the optional camera recorder. Its monitor registers segments and finishes the
archive even when no consumer calls `poll()`. `poll()` only drains bounded UI
notifications and the latest preview. Shutdown awaits camera finalization before
closing archive storage.

Conversation history, local turn reporting and session media archives are
distinct stores with distinct contracts. Their identities, quotas, integrity
checks and idempotent uploads are preserved. Durable archive recovery does not
resume an interrupted conversation or replay uncertain inference/playback.
By default uploads pause during active capture. Pi-test owns these background
tasks in its service process and preserves the same archive recovery protocol.

## Transport scope and development

The original GPU connection remains loopback-only. An explicit `inference_url`
and `inference_host_id` select the shared HTTPS/WSS transport, which obtains
device-scoped platform grants for the separate GPU gateway. Management credentials
never travel to a device. Unknown inference outcomes are journaled without replay.
`cloud_speech.RoutedPlayback` adds cloud synthesis through existing platform
processing while preserving the shared playback gates and interruption behavior.
Pi-test injects that adapter; the desktop's playback configuration is preserved.

ASR uses complete bounded utterances over HTTPS or acknowledged WSS frames; it
does not provide live partial recognition. Bounded video transport supports the
gateway's `opencv_motion` processor under a platform processing-run grant. Cloud
video labels use bounded uploads and platform processing; general vision-model
inference is not implemented by the gateway.
See [Pi-test](../../pi-test/README.md) and its
[verification record](../../pi-test/docs/review.md) for the network and ARM scope.

The Windows desktop portable builder installs this package as a dependency and
protects the extracted critical modules in that distribution. The ordinary wheel
remains platform-independent Python; native hardware extras require separate
Linux/ARM verification.

Run the package's headless checks with pytest and pytest-asyncio, and run the
Human-test suite for desktop integration. The extraction checklist and actual
verification are in [TODO](../../docs/shared-client-todo.md) and
[review evidence](../../docs/shared-client-review.md).
