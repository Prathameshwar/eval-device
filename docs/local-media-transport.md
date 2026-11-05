# Local audio/video transport decision

Decision: 2026-09-18. Keep two independent authenticated WebSocket connections over TLS
between the Pi and laptop: audio on 8765, video on 8766. Do not add a raw TCP listener
without evidence that WebSocket framing or compatibility is the actual bottleneck.

## Why this already provides TCP

WebSocket uses an established TCP connection after its opening handshake; it does not
make a new HTTP request for every media frame. WSS adds TLS. Audio and JPEG media already
use binary messages, avoiding base64 expansion. The frame header for a single masked
client message is eight bytes at a 3,200-byte audio payload, or fourteen bytes at a
100 KiB video payload: about 0.25% and 0.014% respectively. These calculations exclude
handshake, acknowledgments, TLS and network headers, and are not CPU benchmarks.
See [RFC 6455](https://www.rfc-editor.org/rfc/rfc6455#section-5.2).

TCP provides ordered delivery and retransmission of lost data while a connection can
recover. Both WebSocket and a custom raw TCP protocol inherit these properties and
the resulting wait behind missing bytes. A raw TCP socket does not add disk durability,
application acknowledgments, reconnect/resume semantics, authentication or encryption.
See [RFC 9293](https://www.rfc-editor.org/rfc/rfc9293#section-2.2).

The existing clients/server libraries also support Ping/Pong keepalive. This detects
unresponsive peers but does not resume interrupted recordings. Current video sender
settings explicitly retain 20-second ping/timeout values, in addition to shorter
application receipt deadlines. See [websockets keepalive](https://websockets.readthedocs.io/en/stable/topics/keepalive.html).

| Option | Decision for this project |
|---|---|
| Separate audio/video WSS connections | Keep: existing TCP reliability, TLS, bounded queues and independent service behavior |
| Custom framed TCP with TLS | Defer: would require another authenticated protocol, parser, limits and test surface; no demonstrated need |
| A single socket combining both media types | Defer: queued large video messages would share the same ordered stream as audio |
| Resumable uploads after Wi-Fi outages | Future application feature: requires bounded Pi-side storage and idempotent server commit/resume semantics, independently of transport |
| Another video codec/transport | Measure camera bitrate, CPU and congestion first; JPEG is the current accepted format |

Separate connections do not provide bandwidth reservation or eliminate contention on
the same network, CPU or disk. Keep video capture rate and bitrate within measured
capacity so it does not overwhelm audio. Wired Ethernet can also be evaluated on the
same protocol; changing the physical link does not require a custom TCP API.

## Implemented improvement

The video reference sender previously waited for an `accepted` reply after every frame.
That couples its send rate to receipt delay: a roughly 150 ms round trip cannot sustain
15 fps with one frame outstanding, even if the receiver and link have enough capacity.

The sender now has separate send/receive tasks and a **four-frame window** by default:

- Pace frames using their original capture timestamps; keep at most four unacknowledged
  frames, configurable from 1 to 16. Retain only receipt metadata for outstanding frames,
  plus the currently sent/read-ahead frame and bounded transport buffers.
- Validate every acknowledgment's sequence and timestamp. An acknowledgment means
  accepted/pending, not saved. Require the matching recording ID and frame count in a
  finalized saved receipt; preserve pending receipts for status polling.
- Bound startup replies, sends and the oldest missing acknowledgment. Defaults are
  five seconds for acknowledgments/sends, fifteen seconds for completion, and two
  seconds of maximum capture lag. Stop explicitly if stale frames accumulate rather
  than silently dropping them or replaying a large backlog.
- Cancel the other tasks on failure and close the connection. Do not automatically
  replay media, reconnect into a new recording or fall back to plaintext/cloud.
- Connect directly to the selected laptop, ignoring environment proxy settings, matching
  the audio sender's existing behavior. Continue validating TLS certificates.

The audio sender already sends PCM concurrently with receiving transcripts; this
per-video-frame acknowledgment bottleneck does not exist there. Audio inference and
storage behavior were not changed. Whisper CPU inference remains a separate latency
cost; a socket change does not accelerate its model computations.

Example from `device/video-process`:

```powershell
uv run python scripts/stream_file.py --input path\to\segment.mkv --max-in-flight 4 --ack-timeout 5 --completion-timeout 15 --max-lag 2
```

This is still receive-and-record only. No live video detection, pixel decoding,
re-encoding or frame extraction was added. Server APIs and stored recording formats
remain compatible with the original one-frame sender.

## Controlled local comparison

Actual Uvicorn/WebSocket recording and local disk, 18 synthetic 1280×720 JPEG frames
at 15 fps, each 191,363 bytes. Two runs per configuration, ordered 1/4/4/1. The ideal
first-to-last capture span was 1.133 seconds. Delay was injected into receipt delivery
while preserving order, not into a real Wi-Fi link.

| Added receipt delay | One-frame window, mean completion | Four-frame window, mean completion |
|---|---:|---:|
| 0 ms | 1.196 s | 1.211 s |
| 150 ms | 3.055 s | 1.343 s |

All eight recordings saved 18 frames with exact original compressed bytes. The delayed
case completed about 56% sooner; the no-delay case showed no meaningful improvement in
this small sample. The comparison demonstrates removing the per-frame waiting limit,
not a universal speedup, a WebSocket-versus-raw-TCP benchmark, or a disk-latency guarantee.
Scripts and raw results are retained in ignored `.test_artifacts/device-video-transport`.

Pi hardware, actual Wi-Fi loss/jitter, TLS deployment, concurrent audio/video traffic
and the target 16 GB laptop remain unverified. Neither current service offers durable
resume across reconnects. After an interruption, inspect the owner-authenticated
recording receipt and start another session explicitly. A future offline spool/resume
design must preserve bounded storage, ownership and idempotency before enabling replay.
