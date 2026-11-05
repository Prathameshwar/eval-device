# Human-test result and recording sync review - 2026-10-06

This records the initial review before implementation. Its reproduced findings
and measurements are historical; see the follow-up for the current fix status.

**Follow-up:** the user subsequently authorized fixes. The implementation described
in [recording sync](session-recording-sync.md#durability-and-retry-corrections---2026-10-06)
addresses the four confirmed runtime findings. The text below preserves the original
review evidence. Current validation and remaining rollout limits are recorded in
`pms-api-reviews.md` under the 2026-10-06 implementation entry. Hardware/power-loss
guarantees and tenant retention limits remain explicit constraints.

## Current flow

The platform creates an archive with the conversation. The desktop queues turn
JSON, microphone PCM, played patient PCM and completed camera segments without
disk or HTTP work on the capture thread. A disk thread creates approximately
five-second WAV segments and a SQLite WAL journal with synchronous=FULL.
Finalized local audio and turn files are flushed before becoming uploadable.
Camera originals remain in the recording directory.

A separate uploader hashes 256 KiB chunks, reserves stable item IDs, reads the
server's received-chunk list and sends missing chunks. Lost acknowledgements are
recoverable because metadata and chunk hashes are immutable. Acknowledged local
audio/turn files are deleted; camera originals remain. A final manifest names all
expected items. Upload/hash rates are bounded; uploading normally pauses during
listening, inference, playback and camera capture. A detached helper attempts to
drain pending data after desktop exit.

## Confirmed open findings

1. **High: server local-storage acknowledgement precedes explicit durable flush.**
   `platform/api/src/pms_api/integrations/storage.py:64` writes/renames a temporary
   file without fsync. `modules/session_archives.py:326` then commits the received
   chunk. `human-test/src/human_test/session_sync.py:730` deletes acknowledged local
   audio/turn files. The storage probe observed zero fsync calls. The server has
   not established power-loss durability before acknowledgement, and the desktop
   may already have removed its backup. Actual power loss was not simulated. This
   finding concerns LocalStorage, not verified cloud object storage. Fix: durable
   publication before acknowledgement, including platform-appropriate rename/
   directory durability, on server/background I/O paths.

2. **High: detached retry can stop during ordinary shutdown.**
   `session_sync.py:623` waits only 0.1 seconds for the uploader. The helper starts
   after three seconds (`:785`), while an HTTP call may hold the uploader lock for
   its eight-second timeout. In drain mode lock contention returns immediately
   (`:582`). The helper exits and the old uploader subsequently stops. A probe
   matching the three-second startup delay left pending data and no live uploader.
   Fix: bounded ownership handoff/retry without prolonging foreground shutdown.

3. **High: one rejected item starves later items and sessions.**
   `session_sync.py:664` always selects the first eligible item. Most HTTP errors,
   including 404/409 and archive quota 429, leave it eligible and apply one global
   backoff (`:753`). A per-session quota cannot be resolved by repeating that item,
   while another session can still accept data. The probe made three attempts at
   the first quota-rejected turn and none at the later valid turn. Fix: persisted
   per-item retry deadlines/attempts, fair selection and separate classification of
   permanent, capacity and credential failures. Preserve local data and server
   authorization/retention restrictions.

4. **High: a transient journal error can permanently stop persistence.**
   Some SQLite writes/commits are outside the command exception handler
   (`session_sync.py:519`, `:552`). Failure ends the disk thread (`:555`) without
   clearing disk_ok or supervising restart. submit() continues accepting data.
   Holding a competing SQLite transaction beyond the two-second timeout killed
   the writer; after releasing the transaction, another turn was accepted but
   never persisted. Fix: rollback, bounded retry and worker supervision, accurate
   health and explicit failure when data cannot be persisted. This is fault
   injection; ordinary-operation frequency has not been measured. Uploader-level
   SQLite errors also terminate that worker without supervision.

## Design and reporting gaps

- **Recovery deadline:** default media retention is 24 hours
  (`modules/schemas.py:44`) from conversation creation
  (`session_archives.py:110`), while upload_until is at most seven days. New media
  reservations/chunks reject expired media. A day offline can therefore exhaust
  recording recovery even while the archive upload window remains open. Agree
  on offline recovery and retention semantics without silently extending tenant
  retention or bypassing expired access.
- **Status conflation:** `session_archives.py:189` returns incomplete whenever
  capture was interrupted, even with captured files still pending or uploads
  expired. The uploader acknowledges that manifest immediately (`:743`), although
  item uploads continue. The web pending-upload explanation is absent for incomplete
  sessions. Capture completeness and transfer completion should be separate fields.
- **Memory loss window:** intake is bounded but memory-only until the disk worker
  writes it; audio is explicitly flushed at segment finalization. Abrupt exit/power
  loss can lose queued results and the latest audio tail. Recovery repairs saved
  partials and marks interrupted sessions, but cannot reconstruct unwritten bytes.
  Define the permitted loss window and distinguish queued, locally durable and
  server acknowledged states.
- **Performance limits:** thread separation and throttling protect responsiveness,
  but disk/fsync and background work still consume resources. No final pause check
  exists immediately before metadata reservation (`session_sync.py:704`); a probe
  reproduced starting that request after foreground busy became true. Real-device
  audio-loss, inference-latency and disk-contention checks remain necessary.

## Evidence and limits

- Existing sync suite: **8 passed**, covering lost acknowledgements, busy pause,
  restart, chunk resume and detached-loopback helper operation.
- Slow mocked HTTP capture enqueue: p99 **0.037 ms**, maximum **0.069 ms**, 100 frames.
  This measures enqueue cost, not whole-device performance or inference overhead.
- Review probes: **4 passed**, reproducing starvation, shutdown handoff, dead writer
  and the metadata pause-check interleaving. Source:
  `.test_artifacts/session-sync-review-20261006/test_review.py`.
- LocalStorage probe: zero fsync calls on a synthetic recording write. Source:
  `.test_artifacts/session-sync-review-20261006/storage_probe.py`.
- API archive integration tests: **4 skipped** because no dedicated disposable
  PMS_TEST_ADMIN_DSN was configured. No application database was used.
- No live cloud, hardware, power-loss experiment, runtime fix, hosted change,
  commit or publication. The normal resume protocol passed the exercised cases;
  unattended durable retry cannot yet be confirmed for the failure cases above.
