# Online Nemotron default ? 2026-09-20

## Configuration

The requested endpoint is `https://api.24-144-74-153.sslip.io/v1`, model
`nemotron-3-super-120b`, PMS provider `openai_compatible`. Non-secret settings
are in `start/cloud-models.json`. The optional operator section persists explicit
external-call enablement and the custom bootstrap preset, while environment
variables and command-line presets keep precedence. Existing published profiles
remain authoritative. Local speech plus the online LLM appears as Custom.

The one-time setup used a masked Windows dialog and the authenticated PMS
connection/profile APIs. The key stays in process memory until PMS encrypts it
in PostgreSQL; it is never written into the JSON config, command line, report,
or desktop configuration. Publication uses expected connection/profile revisions
and preserves existing speech, video, output, language and capture settings.

## HTTPS and review

Unauthenticated GET to the model catalog returned HTTP 401 through the existing
PMS DNS-pinned transport with certificate and hostname verification enabled.
An ordinary HTTPX client using only its bundled certificate store rejected the
chain, while Windows system trust and the existing PMS transport succeeded.
Inspection confirmed httpcore already loads system and bundled public trust roots;
no transport change or TLS bypass was needed. A regression test protects that
trust-store behavior and verifies certificate/hostname checks remain required.

Operator JSON rejects secret/unknown fields, non-boolean enablement, and invalid
processing modes. External calls remain disabled when no explicit configuration
is present. An explicit environment disable overrides a saved enablement. Existing
profile selection still wins over the bootstrap preset. No schema or grant changes.

## Verification

- Full API suite before the additional TLS regression: 154 passed, 129 skipped.
  Database-dependent tests were skipped without a disposable test DSN; the demo
  database was not used for destructive pytest fixtures.
- Full launcher regression suite: 98 passed. Focused final configuration suite: 32 passed,
  including additional environment/command-line/bootstrap precedence cases.
- Provider suite including the new TLS regression: 60 passed.
- API lint, format and mypy checks passed; affected launcher lint and format passed.
- Live authenticated catalog, JSON and SSE checks passed with TLS verification
  enabled. The single-word synthetic prompt completed in 0.58 s (JSON) and 0.53 s
  (SSE). PMS published and re-read default profile version 8 with the online LLM,
  preserving local `nemotron-3.5-asr-streaming-0.6b` speech and other profile fields.
  The key was stored through the existing encrypted-credential API. Redacted
  evidence: `.test_artifacts/nemotron-online/result.json`.

A fresh combined-launcher startup reloaded the encrypted connection and selected
online Nemotron automatically, with the saved local speech model, video receiver
and retention worker ready. Patient identity and complaint turns succeeded using
the saved `auto` language and normal PMS context/authorization, ending with
`finish_reason=stop` in 0.72 s and 4.02 s respectively. Redacted evidence:
`.test_artifacts/nemotron-online/verify-result.json`. An initial probe specifying
English instead of the saved `auto` language was correctly rejected before
inference; the corrected probe preserved the saved setup. No failed or unknown
external submission was automatically replayed.

Final review checked saved-route persistence, expected-revision publication,
unchanged speech/media settings, TLS/SSRF protection, encrypted credentials and
owned-service cleanup. All services started for verification were stopped.
Reopen Human-test normally to use the saved online default. The Models dialog
shows Custom because speech remains local and the response model is online.

No microphone, voice-quality, hardware or clinical-quality verification is claimed.
