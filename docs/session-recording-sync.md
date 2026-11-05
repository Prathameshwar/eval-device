# Session history and recording sync

Human-test automatically archives enrolled-device practice for both local and cloud models. A server-issued conversation ID joins the trainee assignment (when present), immutable practice snapshot (including selected vitals), model/configuration context, language, conversation turns, microphone WAV segments, played patient audio and enabled camera video. Standalone practice is explicitly unassigned. Sync never calls a model or restarts practice.

The Sessions page has one **Session history** list for assigned and standalone practice, with completion, recording sync and saved/expected items shown separately. One **View session** displays the conversation, private recordings and explicit status refresh. Completion is separate from synchronization: a completed or expired practice can still have pending uploads. “Fully synced” requires every item in an immutable final manifest to have all checksum-verified parts acknowledged. Capture interruption is shown as missing data, never as complete capture. Device-reported transcripts remain distinguishable from authoritative model/assessment results.

## Foreground performance

- Capture and playback submit existing immutable PCM frames to a nonblocking queue. No HTTP, hashing, encoding, filesystem operations or waits run on that intake path.
- Intake is capped at 256 commands and 8 MiB. A dedicated lower-priority disk thread writes approximately five-second PCM WAV segments and a SQLite WAL journal. A separate lower-priority uploader handles HTTP.
- Uploads pause throughout continuous microphone listening, model requests, playback and camera recording. An already-started HTTP request may finish; subsequent chunks wait. Text and microphone processing retain their own connections.
- One uploader per destination/device namespace sends at most one 256 KiB chunk at a time, with a default 512 KiB/s rate limit. File hashing is incremental, pauseable and limited to 8 MiB/s. Upload retry backoff grows to 60 seconds. Text items have priority over media.
- Downloads stream through the authenticated web route; the browser and web server do not buffer the entire recording. The session list fetches 25 rows and summary counts, without eagerly fetching media or transcript contents.

These bounds reduce contention, but do not promise zero overhead on every disk, CPU or network. Synthetic slow-network tests measure capture enqueue latency; real microphone, Raspberry Pi and hosted-cloud validation remain separate rollout checks.

## Durability and recovery

The private local journal is namespaced by API destination, organization and device. Stable item UUIDs, SHA-256 per chunk and immutable metadata allow retry after a lost acknowledgement without duplicates. Only acknowledged cache files are removed. Original camera files remain under the existing camera storage policy. Camera encoding is reused; sync performs no extra video transcoding.

Microphone listening saves the unmuted input independently of transcription, including queued or failed questions. Played output is captured from the actual playback path. Muted microphone periods and a disabled camera are not recordings. Microphone input loss, local queue saturation, disk/quota failure and interrupted processes are explicitly incomplete. Power loss can still lose queued or unflushed data; a damaged or interrupted session must not be represented as complete capture.

Complete & Close and Previous return control without waiting for network uploads. Final manifests wait for active audio/video writers, with a bounded timeout that marks unfinished capture incomplete. A hidden helper can continue uploading after GUI exit; its device credential is passed through an anonymous stdin pipe, never command arguments or a journal. The helper uses file locks to avoid duplicate writers/uploaders. It exits after draining or after seven days. Reopening Human-test resumes pending work after a computer restart; uploading while the computer is off is impossible. Removing the app/journal before acknowledgement loses the remaining local copy.

Storage is bounded: 5 GiB for pending local media and retained conversation snapshots by default, 20,000 pending items across sessions, 4,000 items per session, 5,000 retained journal sessions, and a 64 MiB disk-free reserve. Snapshot capacity is reserved before file writes and reused on retry; older journals are upgraded and accounted for on startup. Camera recovery includes those snapshot bytes; camera storage also has its existing separate quota/free-space checks. Acknowledged journal receipts and snapshots older than 30 days are pruned on startup. Unsynced files are retained on errors and capacity exhaustion stops new archival with a visible warning while practice continues. It does not silently evict recordings to make room.

## Expiry, authorization and deployment

Queued/started assignments still expire 24 hours after creation. Archives do not reopen them. Upload admission lasts up to seven days from conversation creation, bounded by result retention; media also cannot be uploaded beyond its earlier media-retention deadline. Offline time does not extend organization retention. The archive retains upload receipts after media deletion so historical sync status remains meaningful. Expired upload windows are shown explicitly.

API storage defaults are 512 MiB per archive and 5 GiB per organization, reserved under a short organization lock before blob writes. Each item is at most 256 MiB and each chunk at most 256 KiB. Current organization/device/department access and credentials are rechecked. Instructors need scoped result/training permissions; trainees can read only their assigned archives. Platform administrator status alone never permits tenant media access. Downloads and transcript reads are audited, private and uncached. API-owned retention removes expired parts in bounded batches. Worker/maintenance database roles have no archive-table grants.

Apply migration `0045_session_archives` and the runtime grant bundle before updating Human-test and the web UI. The normal fresh-install migration path includes this revision; it needs no new signing key, provider credential or manual per-device setup. Existing API private storage adapters are reused. Old sessions without captured media cannot be reconstructed retrospectively. Deployment and real provider integration are not performed by local verification.

| Setting | Default |
|---|---:|
| `HUMAN_SESSION_SYNC_ENABLED` | `true` for enrolled-device controller |
| `HUMAN_SESSION_SYNC_BACKGROUND` | `true` |
| `HUMAN_SESSION_SYNC_DIR` | `human-test/.local/session-sync` |
| `HUMAN_SESSION_SYNC_MAX_BYTES` | `5368709120` |
| `HUMAN_SESSION_SYNC_BYTES_PER_SECOND` | `524288` |
| `PMS_SESSION_ARCHIVE_SESSION_BYTES` | `536870912` |
| `PMS_SESSION_ARCHIVE_ORG_BYTES` | `5368709120` |

`HUMAN_HISTORY_ENABLED` controls the separate local-conversation text outbox,
separate from the archive, and now defaults to true. Its uploader yields during
foreground work. The web Session history view combines assigned sessions and
standalone captures, with separate completion, sync and saved/expected item values.
View session shows conversations and recordings together, including archive turns
saved while separate text-history reporting was disabled.

## Durability and retry corrections - 2026-10-06

Completed results now wait asynchronously for a flushed local JSON file and committed
journal receipt, with a five-second wait budget. The window remains responsive;
if saving exceeds the budget it reports a pending local save rather than a durable
result. Audio in progress is flushed after each second of PCM written by the disk
worker; finalized audio, results, camera segments and receipts use durable file
publication. Memory still queued before a disk write can be lost during abrupt
process/power failure. No zero-loss or zero-overhead hardware guarantee is implied.

SQLite contention retries on background threads. An unrecoverable journal failure
disables intake and reports unavailable storage instead of accepting data into a dead
queue. The uploader reopens after worker errors. Detached helpers wait for the old
writer/uploader to release ownership; GUI shutdown keeps its bounded wait.

Each item and manifest has a persisted retry deadline and attempt count. A rejected
item no longer blocks later results, recordings or sessions. Transient failures
back off to 60 seconds; immutable conflicts, invalid/expired items and missing files
are retained for review. Authentication failures pause requests; scope denials do
not bypass authorization and can be explicitly rechecked through Retry sync.
Retry never invokes a model. Received-chunk lists and chunk acknowledgements are
validated before any local result/audio copy is deleted.

The API's local storage flushes files and publishes them durably before recording
chunk acknowledgement. An uncertain storage write leaves the database receipt
unacknowledged, so resending the same checksummed chunk is safe. Cloud storage keeps
its existing SDK write contract; no live provider verification was performed.

Capture completeness and transfer completion are separate API fields. The recording
view can show missing capture and pending uploads together. Media retention remains
the tenant's policy: by default recordings expire 24 hours after conversation
creation, while result uploads have at most seven days. The view displays both
deadlines. Expired recording uploads keep the local copy for operator review;
automatic retry never extends retention or bypasses expired access.
