# Patient voice selection audit

Implemented 2026-09-19. PMS already includes patient `sex` in the saved practice
selection's `document.patient`. Human-test uses that authoritative snapshot for
voice selection. No identity, clinical context, prompt, database or API contract
change was needed; Alex's existing male identity now selects a male voice.

| Requirement | Implementation | Verification |
|---|---|---|
| Match the saved patient | Male selects Alan; female selects existing Lessac | Controller, setup and playback event tests |
| Default to male | Missing, unspecified, intersex and other unsupported values choose male for speech only | Normalization and missing-document regressions |
| Handle absent voices | Missing/empty female files fall back to same-language male; no supported voice leaves visible text and a status note | Missing-file and language-boundary tests |
| Preserve responsiveness | Background warmup, reuse across replies and a two-instance cache | Cache identity/eviction tests and real native synthesis |
| Preserve interview behavior | Existing stop, microphone gate, speaker toggle and answer recovery remain intact | Full desktop suite; recovered answers remain silent |
| Install reproducibly | Pinned HTTPS archives and SHA-256 verification; male files also have individual hashes | Installed-file verification and corrupted-file regression |

## Reviews and fixes

First review identified that the single existing English voice ignored PMS sex.
Selection now travels from the successful saved setup through the controller's
answer event to Piper. Warmup uses the same choice. Unsupported identity values
affect the voice preference only, and a busy conversation cannot switch identity.

The review also found a Windows installer handle leak: a failed HTTP connection
could leave the temporary file open before cleanup. The file descriptor is now
owned before opening the connection. A regression exercises five failed attempts,
backoff and temporary-file cleanup. Same-size corruption is rejected during
verification of the new pinned male model.

The second review checked default/fallback behavior, cache bounds, language
isolation, setup propagation and recovered-answer silence. Native checks loaded
both installed voices, produced non-silent PCM and confirmed that repeat loads
reuse the resident object. Output speech remains local even when speech recognition
or the LLM uses an online connection. Existing provider credentials and routing
are untouched.

## Verification

Desktop checks run from `human-test`:

- `HUMAN_TEST_SPEECH=1 uv run pytest -q --tb=short tests`: 114 passed, no skips.
- Ruff lint and format checks, mypy and offline wheel/sdist build passed.
- `uv run python scripts/install_voices.py --verify`: both voices installed.

Separate CPU synthesis samples used the fictional sentence “My name is Alex.
The discomfort began yesterday.” These are observed timings, not a controlled
benchmark; other local checks were running concurrently.

| Installed voice | Initial load | Synthesis | Generated audio |
|---|---:|---:|---:|
| Alan, male English | 3.314 s | 1.295 s | 3.696 s |
| Lessac, female English | 5.230 s | 0.913 s | 3.040 s |

Artifacts: `.test_artifacts/patient-voice/synthesis.json`, `english-male.wav` and
`english-female.wav`. No physical speaker audition, clinical pronunciation rating,
live cloud inference or Raspberry Pi test was performed in this change. API and
database tests were not rerun for this desktop-only change.

## Operation and limits

Restart an existing Human-test window once to load the updated Python code. After
that, saving a different patient setup applies its voice without restarting the
window or API/model services. Startup warmup may take a few seconds; subsequent
answers reuse the loaded voice. The newly installed male voice uses British
English; the preserved female voice uses US English.

The later [Hindi installation](hindi-voice-review.md) adds Rohan and Priyamvada;
the earlier text-only limitation is resolved. Fallback never plays Hindi using
English pronunciation. A native synthesis/device error retains the
text answer and reports failure; speech does not block the interview indefinitely.

Voice assets come from the pinned [Piper release](https://github.com/rhasspy/piper/releases/tag/v0.0.2).
The male model card references the [upstream Alan dataset](https://github.com/MycroftAI/mimic3-voices/tree/master/voices/en_UK/apope_low).
The lock file preserves upstream license references rather than asserting a
blanket dataset license. No patient audio or credentials were sent for downloads.
