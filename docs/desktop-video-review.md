# Desktop webcam preview and dated recordings

Date: 2026-09-20. Scope: laptop webcam capture now, with Pi-origin frames as a later integration. Both implementation reviews were performed by the same agent. No physical camera, microphone, speaker, cloud provider or database was used in this verification.

## Behavior and storage

The Conversation screen offers **Capture & show video**, a camera index (0–9), a live preview, recording status and a selectable save path. Capture is off at startup. Uncheck, New conversation, Patient setup and window close stop the worker and finalize the recording. Microphone controls remain independent. Close also disables the camera controls so a new worker cannot be started during shutdown.

The default root is `human-test/.local/video-recordings`, with `YYYY/MM/DD/HH-MM-SS_<random session>/video-0001.mkv` and a `session.json` receipt. Dates use the laptop's local time; receipts include the UTC offset. Names contain no patient identity. One-minute MJPEG Matroska segments contain video only. Only finalized, flushed files are renamed from `.mkv.part` to `.mkv`; previous complete segments survive a later failure. A receipt left in `recording` state or a remaining `.part` file indicates an unclean exit, not successful completion.

The root and each date/session folder receive an explicit private ACL. Files inherit access for the current OS user and SYSTEM on Windows. Existing link/reparse-point/hard-link paths are rejected. A process-held filesystem lock prevents simultaneous writers from bypassing the same-root quota. All existing files, including partial recordings, count toward the quota; recordings are never automatically deleted. Defaults: 5 GiB total, one hour per capture, a 512 MiB free-space threshold. The writer enforces an additional hard byte ceiling; a small reserve allows receipts and normal finalization. OS disk errors produce a visible failure, not a false saved result.

This is private local operator capture. It does not expose tenant media through PMS, send frames to cloud models, or add a remote endpoint. The existing standalone video API and Pi training flow are unchanged. Camera input is isolated behind a source adapter; a future Pi adapter must authenticate/scoped-authorize its stream and preserve compressed JPEGs when saving instead of re-encoding them. That adapter is not implemented by this desktop change.

## Performance controls and measurements

Camera opening, reads, encoding and disk writes run in a separate process with Windows below-normal priority (nice +10 on POSIX). OpenCV and the encoder each use one thread. Capture is capped at 640×480 and 10 FPS, preview at 5 FPS within 320×150 pixels. A fixed shared-memory slot replaces older preview frames instead of queueing them. Tk creates images only on its own thread. Camera/encoder dependencies load only when the worker is started; the unchecked camera creates no worker and does no capture or recording.

There is no catch-up frame queue. Under load, capture rate drops, and monotonic frame timestamps retain elapsed timing. Stop waits asynchronously for finalization; a stalled driver is terminated after five seconds after stop, or after a 15-second heartbeat gap. This bounds UI blocking without claiming that a forcibly interrupted segment is complete.

Reproduction from `human-test`:

```powershell
uv run python scripts/benchmark_video.py --samples 50 --output ../.test_artifacts/desktop-video
```

The benchmark uses deliberately noisy, generated 640×480 frames, real MJPEG encoding and disk writes, native Tk image updates, and silent resident English Piper synthesis. It performs 50 synthesis samples before, during and after recording. Raw measurements are retained under `.test_artifacts/desktop-video-sustained/` and `.test_artifacts/desktop-video-final/`. In those two runs:

| Measurement | First run | Repeat |
| --- | ---: | ---: |
| TTS median, before video | 0.281 s | 0.250 s |
| TTS median, with video | 0.266 s | 0.250 s |
| TTS median, after video | 0.297 s | 0.282 s |
| Tk 30 ms timer p95, before/with/after | 32 / 32 / 32 ms | 32 / 32 / 32 ms |
| Camera-worker peak working set | 74.5 MiB | 74.6 MiB |
| Camera-worker CPU, normalized to one core | 5.3% | 10.9% |
| Recording-worker duration | 14.0 s | 13.4 s |

Low process priority was checked natively. The first run used the slightly taller initial preview; the repeat used the final preview size. These are short samples on this laptop with ambient system load, not a soak test or a promise of zero overhead. They show no speech-synthesis median slowdown in these samples. They exclude actual webcam capture/driver cost, ASR, LLM inference, acoustic playback, Pi transport and sustained thermal/storage pressure. Zero performance degradation is not established; full conversation/hardware acceptance remains open.

After the Windows ACL fix, a final 50-sample run with the final code (`.test_artifacts/desktop-video-private/benchmark.json`) measured **0.234 / 0.234 / 0.235 s** median TTS before/with/after recording. Tk timer p95 remained **32 ms** in every phase. The recording worker used **74.4 MiB** peak working set and **11.5% of one CPU core** over 12.9 seconds, with below-normal priority verified. This run includes the additional private-folder setup. Native ACL inspection of its saved media showed only current-account and SYSTEM access.

## Review findings and verification

The first review fixed shutdown control re-entry, finalized-segment double-close handling, stale preview/backlog risk, and worker-exit event races. A shared-memory preview avoids a partially written image pipe stranding Tk when a blocked driver must be killed. Playback was verified by decoding the stored files, checking frame counts, dimensions, original color and increasing timestamps. Camera failure, duration/quota limits, hard links, simultaneous writer exclusion, finalization failure and rapid stop/restart have regression coverage.

The second review checked the full window at its minimum 1080×800 size and found the preview squeezed the existing manikin below its drawing minimum. Reducing the preview height preserves a 242-pixel manikin canvas with all camera controls inside the window. A native standalone smoke test drives generated frames through the actual window, then verifies Back and Close release the worker and leave two playable files. It makes no service calls.

Windows ACL inspection also found that `mkdir(mode=0700)` installed explicit folder grants that overrode the intended inherited ACL. Every date/session folder now receives the private ACL explicitly. A native regression enumerates ACLs on all generated date folders and media and allows only the current account SID and SYSTEM.

Final verification: **157 desktop tests passed, zero skips**, with `HUMAN_TEST_SPEECH=1` enabling all four installed English/Hindi synthesis checks. This includes 15 video regressions and native Windows ACL verification. Native window lifecycle/layout, Ruff lint/format, desktop mypy, dependency-lock validation and offline wheel/source builds passed. Platform API Ruff lint/format and mypy also passed; API business/database integration tests were not run because this is a desktop-only change. No database connection or destructive database test was attempted.

Supporting files: `human-test/tests/test_video.py`, `human-test/tests/camera_window_smoke.py`, and `human-test/scripts/benchmark_video.py`. OpenCV camera acquisition and PyAV encoding follow their [video I/O guide](https://opencv.org/reading-and-writing-videos-using-opencv/) and [frame encoding example](https://pyav.org/docs/stable/cookbook/numpy.html).
