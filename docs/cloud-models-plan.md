# Local and cloud model implementation

Scope: Azure OpenAI Whisper, Azure/OpenAI chat models, PMS-authoritative selection,
Human-test and conditional startup. Preserve local models and concurrent work.
Cloud calls are mocked until live credentials and paid-call authorization are supplied.

## Phases

1. Configuration contracts: reuse published processing profiles; independent speech
   and LLM connections; revision-pinned questions; operator cloud gate.
2. Forward migration, provider capabilities, context budgets and complete two-call
   token reservations/accounting. Preserve existing records and encrypted keys.
3. Azure v1/direct OpenAI chat, provider-specific parameters, readiness, bounded
   cloud concurrency, errors, and strict authored patient-answer option.
4. Bounded authenticated interactive Azure Whisper transcription, idempotency,
   private recordings, retention and stage timing.
5. PMS-driven Human-test selection, route-dependent credentials and readiness,
   visible provider/model/status, configuration changes between questions.
6. Conditional launcher with five recoverable startup attempts, local GPU reuse,
   environment examples and operational documentation.
7. Review one: security, migration, correctness, quotas, regressions; fix findings
   and rerun affected checks.
8. Review two: end-to-end combinations, failure/cancellation, latency and final
   consistency; fix findings and record actual evidence and limitations.

## Configuration contract

`PMS_EXTERNAL_CALLS_ENABLED` remains an operator permission gate. The proposed
`PMS_PROCESSING_MODE` is a bootstrap preset (`local`, `cloud`, `custom`), not an
override of an already published profile. Audio input and conversation LLM bind
separately. Profile and connection revisions are checked before dispatch and
before publishing results. Provider secrets never enter effective configuration.

The cloud speech API accepts one completed bounded WAV utterance. Local speech
keeps the existing standalone WebSocket receiver. Neither path implicitly falls
back to a different provider. Video receive/record behavior stays independent.

## Parallel-work handling

Inspect current content before each patch; preserve existing migrations and
unrelated edits. Add isolated modules where practical, use contextual patches,
and record source snapshots/hashes in `.test_artifacts/cloud-models` for review.
Never reset the workspace or stop services owned by another session.

## Verification

Use a dedicated disposable PostgreSQL server for destructive integration tests,
mock provider traffic, and keep native local, mocked cloud and live cloud evidence
distinct. Run API pytest, Ruff, formatting and mypy; relevant Human-test and
launcher checks. Record the two review passes and final audit separately.
