# Human-test camera and panel layout

Date: 2026-09-20. Desktop presentation change; model configuration, inference,
credentials, database and recording policy are unchanged.

The conversation now has a full-width top control bar, a larger left patient panel
(approximately 60%) and a compact right panel (approximately 40%). The manikin,
timing/help text and rehearsal instructions stay on the left. Questions, responses,
conversation actions and camera capture stay on the right. The recording path spans
the right panel directly below the camera controls; the preview sits underneath,
with recording status beside it. Microphone, voice and typed-question inputs are
across the top.

The preview is bounded to 200×150 pixels, preserving its aspect ratio. Recorded
video retains its existing maximum 640×480 resolution and frame-rate limits.
Unchecking the camera returns vertical space to the response without resizing the
patient panel. The setup page keeps its instructions in its own left card, and a
single operational status line remains beneath the application.

## Verification

- Native Tk window checks passed at 1080×800, 1180×860 and 1440×900, including the
  Models button. Assertions cover larger-left proportions, equal panel heights,
  top-bar placement, visible full button labels, minimum readable question/answer
  sizes and containment of the manikin, instructions and camera controls.
- The final recording-path check confirms it spans the camera panel, lies below
  the checkbox/selector and above the preview at all three sizes.
- Webcam **0** was exercised in the real window. Preview appeared; stop, restart,
  Patient setup and Close released the worker. Three short recordings from the
  final physical-camera run decoded successfully within the resolution bounds.
  Temporary physical-camera clips were deleted after verification.
- Generated-frame checks separately exercise the same worker, real encoder,
  recording files, window resize and shutdown. These passed again after the final
  path placement. Screenshots use generated frames and fictional patient text;
  physical camera frames are not included in documentation.
- Full desktop suite during the review: **170 passed, six skipped** (four opt-in
  installed-voice checks and two opt-in resident-Qwen checks). After the final
  preview-size change, all **15 video tests** passed. Native layout checks passed
  after the subsequent path-only adjustment. Ruff lint/format and desktop mypy
  passed on the final files.

The initial sandboxed full-suite invocation could not read an installed Tk resource.
Repeating it with Windows GUI access passed; no dependency or application workaround
was added. Native GUI tests isolate initialization from PMS, so this review does
not claim new cloud, model-inference, database or Pi verification. Existing unrelated
local-execution changes were preserved.

Final visual inspection covered camera on/off, the minimum-size conversation and
the setup screen. The larger-left layout, path placement and lifecycle checks are
in `human-test/tests/camera_window_smoke.py`; `--physical` explicitly opts into the
webcam. Normal automated tests use generated frames. Local screenshot artifacts
are under `.test_artifacts/camera-layout`.

[Final conversation preview](images/human-test-camera-right.png).
