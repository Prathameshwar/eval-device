# Cross-scenario spoken qualification

Each of the nine starter scenarios has ten fictional questions and explicit
review expectations. They exercise combined identity/intake, clinical facts and
follow-ups, exact-day background, partially known treatment questions, missing
personal details, arithmetic, a general explanation and an unsupported claim.
These are test inputs, not a runtime question/answer lookup table.

The runner restores and reviews the selected starter in memory, freezes its
background once and uses a fresh dialogue per scenario. No saved platform
scenario or device profile is changed. It starts owned authenticated loopback
services and records private local evidence; it does not call cloud providers.

From the repository root, for example:

```powershell
.\human-test\.venv\Scripts\python.exe local-models/qualification/benchmark_conversation_pipeline.py --output .test_artifacts/my-chest-run --scenario alex_chest_discomfort --matrix docs/simulations/conversation-scenarios/alex_chest_discomfort.json --asr medium --rounds 1 --realtime --playback
```

Use a new output directory for every run. Inspect every transcript and accepted
answer against the expectation and frozen fixture. The latency gate alone
does not establish answer quality. Synthetic Piper input is resampled with a
bandlimited converter; the quiet interval is simulated. Speaker submission plus
reported device latency estimates first audio, not measured acoustic onset.

The ten-question matrices include two general questions; the existing
`../patient-background/qualification-questions.json` is a separate 25-question
background/general stress matrix. Both should be assessed before recommending
a recognizer/allocation profile. See the [cross-scenario evidence](../../conversation-scenario-review-20261007.md)
for measured results, fixes and remaining gates.
