# Azure Whisper default - 2026-09-20

Human-test now saves **Cloud** mode: Azure Whisper deployment
`whisper-audio-to-text` on resource `aiforce-openai` for speech, plus the existing
`nemotron-3-super-120b` connection for responses. The operator chose transcription
to preserve English/Hindi. The actual speech operation is:

```text
https://aiforce-openai.openai.azure.com/openai/deployments/whisper-audio-to-text/audio/transcriptions?api-version=2024-06-01
```

`start/cloud-models.json` holds only non-secret configuration: the canonical Azure
resource base, deployment, explicit API version and cloud bootstrap preset. The
published PMS default profile remains authoritative. A fresh launch reloaded both
encrypted credentials and selected cloud audio without starting local ASR or LLM
engines. Video recording and local speaker output retain their existing behavior.

## Compatibility fixes

The resource accepted authentication, but its model catalog exceeded the old
64 KiB bound. Only Azure catalog GETs now allow up to 1 MiB. Completion responses
and audio transcripts keep their prior bounds; malformed/oversized payloads still
fail. Boundary tests cover exactly 1 MiB, one byte above it and unchanged limits
for other providers and Azure completions.

The v1 audio route returned HTTP 404. Speech connections now accept optional
`api_version` in the existing settings JSON. An explicit dated version uses the
fixed deployment transcription route; omission preserves existing v1 behavior.
The supplied `2024-06-01` version passed real deployment inference. Version strings
are bounded date/preview forms, deployment names retain strict validation, and
queries are encoded by HTTPX. There is no automatic route fallback or POST replay.
The existing exact resource allowlist, public DNS pinning, TLS/hostname verification,
timeouts and response limits still apply to this fixed operation.

Live readiness then exposed an expired ORM identity read after transaction rollback.
Speech status now snapshots identity before rollback and reloads the user/device
after provider access checks. It still rechecks token expiry, current identity,
credential revocation and current route permissions/configuration before success.

The [Azure transcription quickstart](https://learn.microsoft.com/en-us/azure/foundry/openai/whisper-quickstart)
describes the deployment path. The [audio API reference](https://learn.microsoft.com/en-us/azure/foundry/openai/reference-preview-latest)
distinguishes original-language transcription from English translation.

## Configuration security

The key was entered once in a masked Windows dialog and stored through the
normal authenticated PMS credential API. It remains encrypted in PostgreSQL,
with the master key outside the database. No key enters the Human-test client, command
line, cloud JSON or reports. Later checks reused that encrypted connection.
The API-version update preserved the ciphertext and advanced its revision.

Azure was initially disabled in this isolated demo. The reviewed first-admin
bootstrap verified the locally signed demo identity and created its first platform
administrator with an audit record. A revision-checked platform API call then
enabled Azure. Existing tenant membership still authorizes connection/media access;
platform administrator status does not bypass those checks. Other provider flags,
limits, saved patient language and profile media sections were preserved. Only the
local human-test demo was configured. No schema, migration or grant changes.

## Verification

- Live authenticated catalog and explicit-version deployment sample: passed.
- Synthetic English speech through PMS: succeeded in 0.97 s.
- Synthetic Hindi speech through PMS with auto detection: succeeded in 1.09 s;
  its transcript retained Devanagari. Both private recordings reached saved state.
- English transcription -> Nemotron -> saved patient answer: succeeded.
- Published default profile version 10: Azure audio and the unchanged Nemotron
  connection, both cloud; saved patient language stays auto.
- Fresh combined startup: passed. PMS, private PostgreSQL, video receiver and
  retention worker started; no local audio/LLM engine started. Desktop configuration
  selected cloud audio. All check-owned services stopped afterward.
- Full API run: 172 passed, 134 database-dependent cases skipped without a test DSN.
- Separate disposable PostgreSQL provider/cloud suite: 102 passed, two new test
  fixtures needed corrections to respect last-admin and device-credential constraints.
  After correcting those fixtures, all four affected readiness cases passed in
  another disposable cluster, including user/device revocation during the cloud check.
- Full launcher suite: 102 passed. API lint/format/mypy and affected launcher
  lint/format passed.

Database tests used fresh loopback-only PostgreSQL clusters with verified data
paths; `PMS_TEST_ADMIN_DSN` was set only inside their test processes. They never
ran destructive pytest fixtures against the human-test demo. Cloud calls in these
automated tests were mocked; the live checks above used only fixed synthesized
questions, not microphone recordings. No clinical accuracy, real microphone,
voice-quality or Raspberry Pi verification is claimed.

Final review confirmed the fixed transcription path, preserved v1 compatibility,
bounded catalog reads, encrypted credential reuse and fresh authorization after
readiness checks. No unresolved findings remain within this change's scope.

Redacted evidence: `.test_artifacts/azure-whisper-online/result.json`,
`verify-result.json`, `db-tests.txt` and `db-tests-rerun.txt`.
