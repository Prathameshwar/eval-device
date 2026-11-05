# Online enablement final review — 2026-09-19

Scope: actual local/cloud selection, operator gates, provider requests, patient
answers, client behavior and launcher configuration. This follow-up preserves
parallel work and adds no schema migration or changes to existing application data.

## Findings and fixes

| Finding | Resulting behavior | Evidence |
|---|---|---|
| Saving a model selection could publish unrelated draft changes | Reject with `profile_has_unpublished_changes`; retain the draft and published revision until its edits are deliberately published | PostgreSQL regression edits Hindi/capture settings, attempts model publication, and verifies neither draft nor revision was replaced |
| Selecting models reset published language and duration to defaults | Preserve existing capture settings and tighten the duration against operator, platform, organization and profile limits | Published Hindi and seven-second limit survive model changes; a tighter operator limit takes effect |
| Azure LLM-only profiles bypassed the provider-enable check used by speech profiles | Reject publication while Azure is disabled; recheck enablement after the remote readiness operation | Disable Azure during a delayed readiness check; verify no ready response and reject new Azure LLM-only publication |
| Several explicit operator environment controls were ignored by the launcher | Preserve LLM/speech enable flags, duration, concurrency, retention, storage, timeout and quota controls | Launcher configuration regressions and actionable disabled-provider messages |
| Client capture limits stayed permanently reduced after changing profiles | Recompute from the original client cap and newly selected server limit | Switch from a five-second profile to a longer profile and restore the client cap |
| The existing GUI animation regression could start real installed-voice playback | Disable speaker output in that text-animation test; retain the production speech implementation | Full desktop rerun after isolating the test from audio hardware |
| Medical-model language was inferred from the launch preset, not the selected model | Use the published audio selection; require English when Whisper Medical is first resolved | Launcher language and initial-client-preflight regressions |
| Bootstrap/provider keys could reach non-desktop child processes through environment inheritance | Strip those keys at the common process-launch boundary; retain required service settings | Exercise both inherited and explicit child environments |
| Azure REST resource-key authentication needed an explicit, consistent representation | Azure chat, speech and readiness use `api-key`; direct OpenAI/compatible APIs retain Bearer authentication | Transport-level assertions on both readiness and inference requests |

Azure's REST examples document resource keys using `api-key`; its OpenAI SDK
examples also support API-key credentials through the compatible client. This
change aligns the direct REST calls; it does not claim every previous Bearer-key
request would fail. [Azure v1 authentication](https://learn.microsoft.com/en-us/azure/foundry/openai/api-version-lifecycle)

The current implementation retains Azure `/openai/v1/audio/transcriptions`, which
is documented in the audio reference. Deployment availability still requires
account verification. No automatic alternate-endpoint submission was added.
[Azure transcription reference](https://learn.microsoft.com/en-us/azure/foundry/openai/reference-preview-latest#create-transcription)

GPT-4.1 tests send configured temperature without reasoning effort. Explicit
reasoning profiles omit temperature and use `max_completion_tokens`, which covers
visible output plus reasoning tokens. Both routing and wording calls contribute
to reported usage. [OpenAI Chat Completions reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)

## Verification

| Check | Result |
|---|---|
| New PostgreSQL/API review tests | 9 passed (39.41 seconds) |
| Mocked end-to-end cloud paths | Azure Whisper → PMS patient context → Azure or OpenAI answer; JSON and SSE both pass, with two-call token totals verified |
| Full API suite on disposable PostgreSQL 17 | 263 passed, 2 opt-in native-model tests skipped (669.68 seconds); all database tests ran |
| Full Human-test suite | Final rerun: 43 passed, 1 opt-in native-voice test skipped (14.37 seconds), including the updated parallel speech tests |
| Focused cloud/client regressions | 32 passed |
| Launcher tests | 68 passed (8.87 seconds), including child credential-isolation fixes |
| Static checks | API/client Ruff and format checks pass; API mypy passes for 55 sources |
| Packages and UI | API and desktop wheel/sdist builds pass; native hidden-window Models dialog smoke passes |

The prior intermittent Tk initialization errors did not recur. A later run caught
real playback affecting the older animation test; the test-isolation fix above
passed the final full desktop run. Existing application services and the application
database were not started, restarted or migrated. Only the dedicated review
PostgreSQL server was used and cleanly stopped after verification. Two upstream
test-client deprecation warnings remain;
they did not affect the API results. No existing migration was modified.
Evidence is private under `.test_artifacts/online-final-review`.

The final inspection checked the fixes, authorization and tenant boundaries,
provider credential redaction, model parameters, token totals, profile publication,
failure messages and compatibility with concurrent desktop changes. Confirmed
findings were fixed and affected checks rerun. Package inspection also confirmed
that private runtime state and environment files were excluded from the builds.

## Actual online readiness

The generated combined-launcher configuration still has
`PMS_EXTERNAL_CALLS_ENABLED=false`. No `start/cloud-models.json` exists, the checked
process environment has no bootstrap/OpenAI/Azure key variables, and neither PMS
port 8000 nor 8011 is running. Stored provider connections in a stopped application
database were not inspected, so this is not a claim that no credentials exist anywhere.

Live Azure/OpenAI inference, deployment availability, account quotas, accuracy and
network latency are therefore **not verified**. Tests use synthetic audio and mocked
provider responses; no account was charged and no real patient media was sent.
The online path is implemented and regression-tested, but this laptop remains in
its previous local configuration until the operator provisions and enables cloud use.

Follow [the configuration guide](cloud-models.md): enable the operator cloud gate,
allowlist exact provider API bases, enable Azure in platform settings, provision
encrypted organization connections and publish/select the required model profile.
An existing published profile wins over the bootstrap `--processing-mode` preset.
Readiness checks verify API access rather than paid inference. Preserve the request
key after an uncertain submission and inspect status instead of blindly replaying it.
