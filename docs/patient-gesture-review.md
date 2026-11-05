# Occasional patient speech gestures

## Independent occasional blinking — 2026-09-24

Blinking now uses elapsed time independently of speech. A visible patient briefly
closes its eyes for about 160 ms after each random 5–9-second pause. This replaces
the former speech-only, frame-based blink schedule. Ready, Listening, processing,
retry and speaking states all allow blinking. Leaving the patient screen or hiding
the widget/window resets it; returning starts a fresh pause. Lip timing and
speech/head/hand and quiet leg gesture scheduling remain unchanged.

The existing 30 ms UI poll advances the small blink state machine. Only closing
and reopening the eyes request a redraw; waiting does not redraw or advance lip
frames. No extra Tk timer, background thread, model call or audio processing is
added. The existing eye shapes and head transform are reused.

- Targeted gesture, speech, native workflow and continuous-listening tests:
  **82 passed, 4 skipped**. Skips are opt-in real voice checks.
- Deterministic tests cover random delay bounds, brief closure, resampling,
  hiding/reopening and delayed polls without replaying missed blink cycles.
  Native checks verify unchanged non-eye geometry while silent, no redraws in
  waiting/closed-hold intervals, no idle lip motion or extra timers, and continued
  lip animation while speaking. Head-tilt tests also exercise closed eyes.
- A native 638×425 check drove 2,001 production blink updates over **60 simulated
  seconds**. It produced **16 redraws**, with 1,985 polls needing no redraw.
  Median draw-plus-paint time was 13.01 ms; all updates and painting together took
  219.93 ms wall time and 218.75 ms UI-thread CPU time. No Tk timers were created
  and the lip frame remained zero. This is a local simulated-clock check, not
  a loaded inference/audio or Raspberry Pi performance result. Reproduction:
  `.test_artifacts/eye-blink-20260924/benchmark.py` and `performance.json`.
- First review checked separation from speech and state transitions, visibility
  gating and callback reuse. Second review checked redraw counts, mouth isolation,
  head-feature transforms, cleanup and documentation. Targeted Ruff lint/format
  and mypy for the changed source files passed.

Restart an open Human-test window to load the update. Earlier sections below
record prior behavior and measurements; their speech-only blink timing is historical.

## Slight head movement during speech — 2026-09-24

Accepted patient audio now independently arms one possible head tilt. The chance
is 40% per eligible reply, compared with the unchanged 25% hand/finger chance.
Each controller skips its next reply after starting a gesture. Head movement
uses the existing 0.6–1.3-second playback delay, 1.6-second smooth return and
audio freshness gate. Short answers may finish before a tilt starts. It cannot
start from text alone, a voice preview or queued synthesis, and stops on playback
completion, a stall, mute, retry, cancellation or navigation.

The head tilts about 3.4 degrees left or right around its base. Ears, hair, eyes,
eyebrows, nose and mouth follow one rotation; the neck, seated body and labels
remain fixed. Small oval features use smooth ellipse polygons because Tk oval
items cannot rotate. Blink and lip cadence stays unchanged. Both speech gesture
controllers share the existing callbacks and animation timer; quiet leg timing
remains 15–30 seconds. No extra model calls, timers or threads are added.

- Targeted gesture, speech and patient workflow suite: **55 passed, 4 skipped**.
  The skips are opt-in real voice tests. Coverage includes the 40% boundary,
  one decision per reply, cooldown, short answers, synthesis waiting, audio
  stalls and explicit stops. Native checks cover both tilt directions, bounded
  displacement, head-only geometry, blinking, simultaneous hand/head movement,
  exact return to rest, rearming and cleanup of both controllers.
- First review checked playback gating, preserving both controllers' updates
  without short-circuiting, and rotating all features together. Native previews
  of neutral, left/right tilt and blink were visually inspected at 340×460 and
  638×425. Captures are in
  `.test_artifacts/gesture-visibility-20260924/speaking-head/`.
- Rendering at 638×425 after 25 warm-ups and 100 measured redraws per pose had
  median draw-plus-paint times of 9.88 ms neutral, 9.92/8.54 ms for left/right
  tilt and 7.28 ms blinking. Corresponding p95 times were 11.95, 14.11, 14.06
  and 10.92 ms, below the 60 ms animation interval. Item counts remain 111 with
  eyes open and 107 during blinking. These are local drawing measurements,
  not loaded speech/model latency results.
- Second review checked the final independent cooldowns, unchanged hand/leg
  settings, cancellation paths, rendered anatomy and documentation. Targeted
  Ruff lint/format and mypy checks passed; no outstanding findings.

Playback was simulated for tests. No live audio, cloud, model or hardware
verification was performed. Restart Human-test to load this update.

## Quiet seated leg movement — 2026-09-24

The conversation screen now includes a separate quiet leg gesture. After a
random 15–30 seconds in Ready or Listening, one randomly selected lower leg and
foot swing outward by up to about 10.3 degrees, then return over 1.6 seconds.
The next random pause starts when the movement finishes. Speaking, reply
animation, processing, retries, navigation and explicit animation resets cancel
the movement and countdown. Returning to a quiet eligible state starts a fresh
pause. The existing hand/finger speech probability and cooldown are unchanged.

The existing 30 ms UI poll updates this timer-free state, drawing at most every
60 ms during movement and once on each transition. Quiet waits do not redraw.
The same knee transform applies to the selected trouser leg, hem, crease and
shoe; thighs, hips, the other leg, hands and face remain fixed. No model calls,
audio processing, threads, canvas shapes or Tk timers are added.

Verification and two reviews:

- Targeted gesture, speech and patient workflow tests: **47 passed, 4 skipped**.
  Skips are opt-in real voice checks. Deterministic tests exercise 15-, 22.5-
  and 30-second pauses, fresh random pauses after movement, both sides, smooth
  return, speaking interruption, a fresh wait after interruption and no burst
  of movements following delayed polling. Window tests verify eligibility.
- Native canvas tests verify six changed shapes, only coordinates below the
  selected knee moving, visible displacement, fixed face cadence, no extra
  timers, exact return to rest and cancellation by text/audio speech.
- Both peak leg poses were visually inspected at 340×460 and 638×425. Saved
  captures are in `.test_artifacts/gesture-visibility-20260924/seated-leg/`.
  A local 100-redraw measurement after 25 warm-ups retained 111 canvas items;
  median wall time including paint was 11.47 ms at rest, 12.99 ms for the left
  leg and 9.48 ms for the right. This run overlapped tests, so timings are only
  a local rendering check, not a comparison or loaded audio/model benchmark.
- First review found that the finger transform also ran for the new leg
  gesture. It now explicitly requires a finger gesture; native isolation tests
  pass. Second review checked the final 15–30-second scheduling, speech and
  navigation gating, cancellation, geometry and documentation. Targeted Ruff
  lint/format and mypy for the three changed source files passed.

Checks used simulated playback and offline drawing, without live audio, models,
cloud or hardware. Restart Human-test to load the change.

## Visibility update — 2026-09-24

Wrist rotation now reaches about 25.8 degrees (previously 5.7 degrees).
The finger gesture curls all four fingers progressively, with up to ten drawing
units of fingertip flex instead of three units on only the index finger.
Knuckles and palm remain fixed during finger movement; wrist movement rotates
the existing hand around the same attachment point.

Gesture frequency and scheduling are unchanged: one 25% chance per eligible
spoken reply, the next reply always still after a started gesture, a 0.6–1.3
second delay and a 1.6-second motion. Audio progress still gates movement and
all existing cancellation/stall behavior remains in place. `gestures.py` has no
changes in this update. The existing animation timer redraws every 60 ms;
mouth and blink frames advance every second tick, preserving their 120 ms
cadence. This changes drawing smoothness, not how often gestures occur.

Verification:

- Targeted gesture, speech and patient workflow suite: **35 passed, 4 skipped**.
  Skips are opt-in real voice tests. Playback was simulated; no model, audio
  device, cloud or hardware verification was performed for this update.
- Native canvas checks verify both sides, visible displacement, unchanged face
  and opposite hand, one timer, preserved face cadence and immediate reset on
  completion/cancellation. Finger motion affects four polygons and four creases;
  wrist motion still affects the same 14 existing shapes.
- Native rest/peak captures at 340×460 and 638×425 were visually inspected.
  Hands remain attached and finger curls remain within the existing drawing.
  Local captures and the script are in
  `.test_artifacts/gesture-visibility-20260924/`.
- At 638×425, 100 measured redraws per pose after 25 warm-ups gave median
  draw-plus-paint times of **7.58 ms at rest, 7.77 ms for wrist and 7.02 ms for
  fingers**; corresponding p95 times were 11.00, 11.28 and 9.92 ms. Each pose
  retains 111 canvas items. These Windows measurements are below the 60 ms
  timer interval; they are not a loaded inference/audio benchmark. More redraws
  do increase rendering work while speaking.
- First review checked the unchanged gesture scheduling and face cadence; a
  test cleanup issue was fixed by cancelling the callback through its owning
  widget. Second review checked final geometry, timer cleanup, render cost and
  documentation. Targeted Ruff lint and formatting checks passed.

Restart an already open Human-test window to load the update. The earlier
measurements below document the original implementation, not this update.

## Original implementation — 2026-09-20

Reviewed 2026-09-20. The seated Human-test patient occasionally moves one hand
slightly at the wrist or flexes one index finger during a spoken reply. The
existing mouth and blink animation is preserved.

## Behavior and implementation

- A reply receives one random decision after the speaker progress counter first
  advances. Eligible replies have a 25% chance; the next spoken reply after any
  started gesture is always still. Short replies can end before motion begins.
- The selected hand or finger starts after 0.6–1.3 seconds of playback. A smooth
  1.6-second motion returns to rest, with at most about 5.7 degrees of wrist
  rotation or three drawing units of fingertip flex. Only one side moves.
- No motion starts during synthesis alone, silent/recovered replies or voice
  samples. Playback completion, a progress gap over 300 ms, mute, cancellation,
  retries, patient changes and close clear movement. A stalled gesture is not
  retried within that reply. Stops return directly to rest.
- `gestures.py` holds only per-reply state. `Window.drain` supplies existing
  speaker progress; `Manikin.draw` transforms the existing hand coordinates.
  Speaker processing, model requests, dependency lists and application data are
  unchanged. No new timer, thread, network request or audio operation is added.

## Performance

Compared the saved pre-gesture drawing with the current drawing in native Tk at
638×425, using fixed mouth/eye frames and forced peak gestures. Each case warmed
for 200 redraws, then ran eight batches of 100 redraws in alternating case order.
Timing includes `draw()` and `update_idletasks()`; this is a rendering comparison,
not an end-to-end audio or inference benchmark.

| Drawing | Median wall time per frame | Median UI-thread CPU per frame | Canvas items |
|---|---:|---:|---:|
| Before gestures | 14.65 ms | 14.14 ms | 111 |
| Current, still | 13.27 ms | 11.88 ms | 111 |
| Current, hand moving | 14.63 ms | 14.06 ms | 111 |
| Current, finger moving | 12.35 ms | 10.86 ms | 111 |

No slowdown was measurable in this run. Batch times varied from approximately
9.5–18.4 ms across cases, so the lower current numbers should not be interpreted
as an optimization. All were comfortably below the unchanged 120 ms animation
interval. Earlier short runs varied substantially; the table uses the final
isolated warmed run. Native tests also verify that movement creates no additional
canvas items or animation timers. The controller uses the existing 30 ms UI poll
and performs one random selection per eligible spoken reply.

Local reproduction assets: `.test_artifacts/speech-gestures/benchmark.py`, saved
`baseline_manikin.py` and `performance.json`. Measurements apply to this Windows
laptop; no Raspberry Pi or loaded audio/model throughput result is claimed.

## Verification and final review

- Full desktop suite: **197 passed, 6 skipped**. The skips are the existing four
  opt-in voice checks and two opt-in model checks. Ruff lint/format passed for
  the desktop tree, and mypy passed for its 18 source files.
- Deterministic controller tests cover selection boundaries, one decision per
  reply, forced cooldown, both sides and gesture types, smooth return to rest,
  short replies, synthesis delays, stalls and explicit stops.
- Window tests verify that only an accepted patient audio reply arms motion,
  polling does not rearm it, silent/recovered text stays still, and mute resets it.
- A native Tk subprocess verifies that finger motion changes exactly its polygon
  and crease, hand motion stays on the selected side, and the mouth, eyes, other
  hand, frame counter and timer count stay unchanged. Stop/status transitions
  reset the pose and clean up the existing animation timer.
- Native previews passed containment checks at 1080×800, 1180×860 and 1440×900.
  Rest, wrist and finger frames were visually inspected: the wrist remains
  attached, fingers stay aligned and the patient retains focus in the OPD room.
  Captures are in `.test_artifacts/seated-manikin/speech-gestures/`.
- Final review checked speaker acceptance/progress ordering, preview isolation,
  retry/navigation cleanup and preservation of the existing face animation.
  No API, database, authorization or storage path changed.

Playback was simulated for these checks. No new live speaker, microphone,
cloud, database or Pi verification was performed. Restart an already open
Human-test window to load the update.
