# Standalone local video recording API

The Pi captures video; this laptop service receives and saves it, independently of
[audio-process](../audio-process/README.md), on port **8766**. There is **no detection,
inference, live frame extraction, image decoding or video re-encoding** in the receiver.
The background writer copies compressed JPEG packets into playable MJPEG Matroska
(`.mkv`) segments. No model needs downloading or loading.

The service has separate local credentials and storage. It makes no PMS, database,
audio-service or cloud calls. Cloud mode remains Pi → platform API → provider.
Platform enrollment, tenant permissions, configuration binding and Pi capture/display
adapters remain separate work. A local token is not a platform device identity.

## Run on the Windows laptop

Use Python 3.12 or 3.13. From this directory:

```powershell
uv sync
uv run video-api init-local
uv run video-api serve
```

`init-local` creates a random `pi-1` token in private `.env`, without printing it or
overwriting existing settings. Serving makes no external calls or downloads. Package
installation downloads dependencies, including PyAV/FFmpeg. `.env.example` lists every
supported `VIDEO_*` setting.

For Wi-Fi, configure `VIDEO_TLS_CERT` and `VIDEO_TLS_KEY` with a certificate trusted by
the Pi, then set `VIDEO_HOST=0.0.0.0`. Connect to
`wss://<laptop-hostname>:8766/v1/video/stream`. Restrict the laptop firewall to intended
local clients. Do not disable certificate verification. Plain HTTP/WebSocket is allowed
only from loopback; reverse-proxy forwarding headers are not trusted.

`VIDEO_CLIENT_TOKENS` is a JSON object mapping client IDs to distinct secrets with at
least 32 ASCII characters. Restart to change tokens. Clients can read only their own
recording receipts. Query strings, browser Origins and cookie authentication are
unsupported. The supplied CLI suppresses request URL logs; tokens and video are not logged.

## API and wire format

| Endpoint | Behavior |
|---|---|
| `GET /health/live` | Minimal public liveness |
| `GET /health/ready` | Authenticated writer readiness; 503 when storage failed to initialize |
| `WS /v1/video/stream` | Authenticated bounded receive-and-record session |
| `GET /v1/recordings/{recording_id}` | Owner-authenticated receipt; 404 for another owner |

Supply `Authorization: Bearer <client-token>` in the handshake. No media browsing,
download, deletion or live extraction endpoint is exposed.

The first message is JSON, limited to 2 KiB:

```json
{"type":"start","version":1,"format":"jpeg","width":1280,"height":720,"fps":10,"capture_id":"e812ef54-1018-4ea7-a2b2-e87d0b32b858","capture_start_unix_ms":1789680000000}
```

`capture_id` and `capture_start_unix_ms` are optional correlation metadata. They do not
authorize access, synchronize clocks, resume sessions or deduplicate recordings. A Pi
adapter can assign the same UUID to audio's `stream_id` and video's `capture_id`; neither
service currently joins them. The server returns `type=ready`, a new `recording_id`, and
`status=pending` after committing the initial manifest. Use that server ID for status.

Each following binary message contains one baseline JPEG:

| Offset | Value |
|---|---|
| 0–3 | ASCII `VPF1` |
| 4–11 | Unsigned 64-bit sequence, network byte order; 0, 1, 2, … |
| 12–19 | Unsigned 64-bit capture timestamp in microseconds, network byte order |
| 20 onward | Complete baseline 8-bit grayscale or three-component JPEG |

The first timestamp is zero; later timestamps strictly increase. JPEG headers must
match declared dimensions. Framing checks reject progressive, multi-scan and concatenated
JPEGs without decoding pixels. They do not certify entropy-coded image content: `saved`
means the accepted compressed bytes were stored, not that every pixel was decoded.

Send at capture speed. Frame-rate limits include 10% interval jitter tolerance, a
one-second receive burst allowance, and at most two seconds of capture-time lead.
Capture duration and wall-clock session limits both apply. Every admitted frame receives:

```json
{"type":"accepted","sequence":0,"timestamp_us":0,"status":"pending"}
```

**Accepted does not mean durably saved.** Finish with `{"type":"stop"}`. The server
drains admitted work and returns `type=complete` with the recording receipt. A bounded
wait may leave it pending; poll the owner-authenticated status endpoint. Only
`status=saved` together with `finalized=true` confirms successful recording completion.
`saved_frames` counts committed segment frames; `received_frames` records the admitted
session count at finalization.

Disconnects, timeouts, overload, invalid input and storage failures produce `incomplete`
recordings. A finalized incomplete recording can contain playable segments. A failed
final manifest write remains `incomplete` with `finalized=false`; restart reconciles it.
If a connection fails before its ID is received, the local operator must inspect the
private store; there is no public listing or resume facility.

## Storage, limits and recovery

```text
.recordings/
  .store.json
  .writer.lock
  <server-generated UUID>/
    session.json
    segment-000000.mkv
    segment-000000.json
    segment-000001.mkv
    segment-000001.json
```

Segments are independently playable. Sidecars retain source microsecond timestamps,
sequences, lengths and SHA-256 hashes. Container timestamps start at zero per segment
and may round to milliseconds; sidecars preserve exact capture timing. Recordings have
no microphone audio track. Automatic audio/video alignment or combining is not implemented.

| Limit | Default |
|---|---|
| Active/pending sessions | 2 across all clients |
| Resolution and rate | Up to 1280×720 at 15 fps |
| JPEG bytes | 512 KiB per frame, plus 20-byte header |
| Session / idle timeout | 600 seconds / 15 seconds |
| Writer queue | 8 MiB and 128 items, including in-flight work |
| Segment buffer | At most 2 MiB compressed bytes per session; flush about every 2 seconds |
| Store | 1,000,000,000 bytes / 1,000 sessions / seven days |
| Minimum free disk | 64 MiB plus pending reservations |
| Startup / drain / shutdown wait | 5 seconds each |
| Safe transient I/O attempts | 3 total, 50/100 ms backoff with jitter |

One background writer handles packaging, files and retention. Frame admission does not
wait for disk. Initial metadata creation and final save confirmation wait within their
deadlines. Opening/closing-handshake waits use the send deadline, and stream capacity is released even if the final reply is cancelled. Transport, writer and per-session buffers are separately bounded. Storage
accounting reserves container/metadata overhead; usable video capacity is conservatively
below the configured cap.

Oldest finished sessions are evicted for age/count/bytes; active sessions are protected.
Cleanup runs on startup, admission and periodically while idle. Use a dedicated local
directory. Unknown contents, symbolic links, Windows reparse points and hard-linked media
are rejected. A lifetime store lock excludes another writer or extractor. Windows ACLs
grant access only to the current user and SYSTEM; POSIX directories use 0700. These are
filesystem access controls, not encryption at rest or isolation from the same OS user.

Files are written to bounded temporary paths, flushed and atomically renamed. Retries
rewrite immutable content at the same path and check uncertain successful renames.
Disk-full and permission errors are not blindly retried. Queue overload drains accepted
work; quota rejection first flushes already reserved frames. A failed segment preserves
previously committed segments and marks the recording incomplete. The service stops
accepting unrecordable input; no cloud or arbitrary-directory fallback exists.

A crash can lose frames acknowledged as pending. Recovery checks manifests, segment
pairs, lengths and counts. Unfinalized sessions remain incomplete; partial artifacts
stay within normal quotas. Abandoned initial empty sessions are removed safely. Full
hashes are checked during offline extraction, not API startup. Bounded shutdown does
not forcibly cancel stuck OS writes; the daemon writer retains the lock until it exits
or the process terminates.

## Offline frame extraction

Stop the video API, then run:

```powershell
uv run video-api extract-frames --recording-id <UUID> --output C:\Pratham\poc-device\.test_artifacts\frames-001 --every 10 --max-frames 1000 --max-bytes 268435456
```

This separate batch command accepts completed saved recordings, verifies segment hashes,
and copies original JPEG packets into a new private directory without re-encoding.
Filenames contain sequence and source timestamp. `--every 10` selects every tenth source
frame; `--every 1` selects all. It holds the store lock, preventing overlap with recording
or retention. Output must be a new directory outside the recording store.

`extraction.json` reports `complete`, `limited` when capped, or `incomplete` after failure.
Extracted files have byte/frame bounds but are outside recording retention; the operator
manages their lifecycle. There is no scheduled extraction job, bulk analysis, detection
or platform callback.

## Development sender and checks

The included sender streams an existing local MJPEG Matroska file at capture speed:

```powershell
uv run python scripts/stream_file.py --input path\to\segment-000000.mkv
```

The sender keeps up to four frames awaiting acknowledgment while reading replies
concurrently. Configure `--max-in-flight` (1-16), `--ack-timeout` (default 5 seconds),
`--completion-timeout` (15 seconds), and `--max-lag` (2 seconds). It validates every
sequence/timestamp, fails on missing or invalid receipts, and stops excessive lag
without silent frame drops. An incomplete final receipt is an error; a pending receipt
still requires status polling. Startup/send/close waits are bounded, and environment
proxies are ignored for this direct laptop connection. [Transport decision and measured
comparison](../../docs/local-media-transport.md).

For Wi-Fi, supply `--url wss://<laptop-hostname>:8766/v1/video/stream` and optionally
`--ca-file path\to\trusted-ca.pem`. It reads its client's token from `.env`. It never
automatically replays failed streams: query the receipt, then start a new recording
explicitly. Duplicate sequences are rejected within a session; a new session creates
a separate recording.

```powershell
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src/device_video
uv lock --check
uv build
```

Tests use actual generated JPEGs, PyAV containers, filesystem operations and loopback
HTTP/WebSocket transport. Fault injection covers ambiguous renames, disk failures,
quotas, saturation, recovery, cancellation and shutdown. See
[review evidence](../../docs/pms-api-reviews.md) for final verification.

This v1 protocol requires timestamped JPEGs. Raw H.264/MP4, RTSP and WebRTC need future
adapters. MJPEG can consume more bandwidth than inter-frame codecs; avoiding laptop
re-encoding does not eliminate transport or disk work. Pi capture, Wi-Fi/TLS deployment,
real camera throughput, 16 GB performance and concurrent Whisper/video latency remain
unverified. Separate processes still share CPU, memory, disk and network.

Upstream references: [PyAV containers](https://pyav.org/docs/stable/api/container.html)
and [packets](https://pyav.org/docs/stable/api/packet.html). Installed dependency behavior
is covered by the package's native-container tests.
