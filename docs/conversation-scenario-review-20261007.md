# Cross-scenario local conversation review

Requested: at least ten Q&As per scenario, fix findings and rerun. All nine
fictional starter scenarios have a ten-question matrix. Evidence remains private
under `.test_artifacts/scenario-20261006-small-b1/` (baseline) and
`.test_artifacts/scenario-20261007-final/` (final rerun). Qualification is in
progress; final answer review, checks and conclusions are recorded below when
complete.

## Setup and interpretation

Qwen3.5-4B uses a 2,048-token context, 128 output tokens and 128 safety tokens,
with two recent dialogue pairs and exactly one generation per answer. The runner
fits each actual prompt through the native tokenizer. Input is fictional Piper
speech sent in real time with an 800 ms simulated quiet interval. Output is real
Piper speaker playback, released only after a required durable result commit;
patient audio is saved in the local private journal. Each case starts a fresh
owned local ASR/LLM service and frozen conversation.

Warm first-audio timing excludes the first request per case and includes the
quiet interval, ASR completion, prompt fitting, generation, required saving and
speaker readiness. This is output submission plus reported device latency, not
a measured physical acoustic onset. Cold voice/model loading and the first turn
are reported separately. No physical microphone, camera/PMS/GUI load, cloud
provider, Raspberry Pi or hosted deployment is qualified by these runs.

## Baseline findings

Small Whisper CUDA / beam 1 with 33 actual Qwen GPU layers attempted **90**
spoken Q&As: **86 accepted, four protocol errors**. Manual review found **72/90**
acceptable answers. The per-case warm medians were 1.77–2.14 s and p95 values
2.35–3.21 s; speed did not establish quality.

- Combined identity/intake questions were narrowed to identity only. Four cases
  failed validation; the missing chief complaint was visible in the selected view.
- A chest-tightness follow-up shed clinical evidence and produced general advice.
- Whole-question past-treatment filtering discarded other known clinical parts.
- Cough/fever remedies could be offered for sleeping-pill use; sleep facts with
  clinical words could be removed from a mixed sleep/treatment question.
- Seven of nine synthetic rain questions became "ring". The two correctly
  recognized rain questions still produced a false air-pressure explanation.

## Confirmed fixes and comparisons

Compiler **35** retains the one-generation fact-selection contract. Intake
phrases keep the full grounded view, clinical follow-ups include the case's own
clinical vocabulary, and explicitly requested background areas remain eligible
without overriding clinical facts. Explicit joined past-treatment questions
scope each part independently; requested sleeping-pill/antibiotic types need
explicit source support. Current medicines still cannot prove past use.

The general prompt is shorter and asks for the core explanation without
speculative secondary causes. A longer intermediate anti-speculation prompt
did not fix rain; shorter prompt comparisons did. No question-specific answer
lookup, speculative playback, extra generation or relaxed source validation was
introduced. Existing snapshots keep their frozen general prompt.

New regressions first reproduced **11 failures / seven passes**. After the fixes,
the focused shared/API suite passed **162 tests**, with **two database-dependent
skips**. Database tests did not use the application database.

Small-model beam sizes 1/3/5 repeated the same errors on four saved clips.
Medium Whisper corrected both rain clips and the "when" clip; one trigger clip
remained "treaters". Large-v3-turbo and the installed CPU recognizer each retained
other errors. These replay timings are not live pipeline qualification. A
same-source linear/bandlimited resampling A/B recognized all four diagnostic
clips in both versions, so resampling alone does not establish a cure. The final
harness uses bandlimited resampling to avoid introducing interpolation artifacts.

The combined candidate is medium Whisper CUDA / beam 1 with **26 actual Qwen
GPU layers**. One resident observation was **3,235/4,094 MiB** GPU memory. It is
not a deployed profile change or a memory guarantee under other workloads.

## Final rerun

The VM deployment request interrupted the final native batch after three complete
cases: chest discomfort (warm median/p95 **2.90/3.45 s**), palpitations
(**2.69/3.52 s**) and blood pressure (**2.92/4.74 s**). Each completed ten answers
with zero protocol errors and passed its warm latency gate. Chest journal
integrity was `ok`; all ten turn files and twelve audio segments were ready,
matched committed sizes, and the patient WAVs were valid. The session was sealed,
complete and unacknowledged, as expected for an offline mocked upload transport.

The other six final cases, the separate 25-question stress matrix, remaining
answer/journal review and two final qualification reviews remain open. No faster
recognizer/profile recommendation or universal five-second guarantee follows
from these partial results. Deployment checks are recorded separately in
[VM verification](vm-update-20261007.md).
