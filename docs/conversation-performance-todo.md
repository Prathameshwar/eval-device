# Conversation performance implementation

Target: warm speech-end to first audible answer median <=3 s, p95 <=5 s.
Software output submission and estimated device latency are distinguished from
physical audible onset. Complete playback and cold preparation are separate.
Quality, permissions and durable result/media recovery remain mandatory.

- [x] Phase 1: privacy-safe turn/stage timings and reproducible pipeline benchmark.
- [x] Phase 2: use actual ASR device for GPU allocation; warm speech before listening;
  retain current profile and conversation access checks, avoid repeated local probes.
- [x] Phase 3: prioritize bounded durable result commits; overlap synthesis with saving;
  prevent playback if a required result commit fails.
- [x] Phase 4: bounded synthesis/playback overlap, cancellation, low-latency fallback,
  bounded memory PCM reuse and first-output/playback timings.
- [x] Phase 5: endpoint/ASR measurement and safe tuning; retain conservative capture
  defaults unless recognition evidence supports a change.
- [x] Phase 6: assess further model/streaming work against grounding and save-before-
playback requirements; retain one generation and the 2,048-token budget.
- [x] Phase 7: execute native combined qualification, sustained and failure checks,
  full affected checks and two final reviews with fixes. Speed/accuracy gates
  below remain open; implementation completion does not mean qualification passed.

No hosted rollout, paid cloud inference or Raspberry Pi verification. No automatic
publication of this implementation. Evidence must identify unavailable physical
microphone/loopback measurements and unsuccessful latency gates explicitly.

Qualification gates remain separate from implementation completion:

- [ ] Meet warm median <=3 s / p95 <=5 s on the complete deployed configuration.
  The Large-v3/18-layer and small-Whisper/33-layer component runs both missed it;
  measurements and actual sample counts are preserved in the evidence.
- [ ] Resolve the small-Whisper recognition failure on the synthetic rain question
  before recommending it as a faster replacement for the selected recognizer.
- [ ] Qualify real microphone/endpoint accuracy, natural pauses and room noise.
- [ ] Verify digital/acoustic onset; listed Stereo Mix currently cannot be opened.
- [ ] Qualify camera load and actual PMS access-check/GUI scheduling overhead.

Phase 6 assessment keeps complete validation and correct generation accounting.
It does not silently add unsafe ID streaming, speculative speech or fake model
usage. See the two review passes in the evidence document for fixes and limits.

## Cross-scenario qualification requested 2026-10-06

- [x] Prepare nine fictional starter matrices, ten spoken questions each, covering
  case facts, missing personal details, mixed questions and general knowledge.
- [x] Run all nine local ASR/model/durable-save/speaker pipelines with fresh history.
  Baseline: 90 attempted; repeat all nine after the confirmed routing/prompt fixes.
- [ ] Review every transcript and answer, timings, journal integrity and call budgets.
- [ ] Fix confirmed findings, add relevant regressions and repeat affected scenarios.
- [ ] Complete two final reviews and report actual pass/fail gates and limitations.
