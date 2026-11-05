# Hindi patient speech output

Completed 2026-09-19. Hindi answers now use installed local Piper voices through
the existing Human-test speaker worker. Select Hindi in the saved patient setup
and leave **Speaker out** enabled. Auto language chooses Hindi when the answer
contains Devanagari. Alex's male identity selects Rohan; female selects Priyamvada.
Unknown sex defaults to male, and an unavailable female voice falls back to the
same-language male voice. No English pronunciation fallback is used for Hindi.

| Planned | Implemented | Verification |
|---|---|---|
| Install Hindi speech | Rohan male and Priyamvada female, medium quality, 22,050 Hz | Both installed and SHA-256 verified |
| Preserve English output | Existing Alan/Lessac entries and files retained | Native English and Hindi synthesis passed |
| Repeatable setup | Pinned archives plus individual model/config hashes; normal `setup.bat` installs all four voices | Repeated installer reused installed files without downloads |
| Handle downloads safely | Existing five attempts, verified TLS, bounded downloads and temporary files | Retry/cleanup regressions passed |
| Support available official packages | Nested `.tar.bz2` support alongside flat `.tar.gz` archives | Both layouts tested; unwanted members and links never extracted |
| Maintain latency and controls | Existing background warmup, two-voice resident cache and interruptible playback | Cache reuse, microphone gate, cancellation and speaker-toggle tests passed |
| Confirm usable output | Non-silent Hindi WAVs and production laptop output stream | Native synthesis and short male Hindi playback completed |

## Sources and installation

Direct Hugging Face metadata/model requests returned HTTP 403 on this machine.
Downloaded the Piper packages from the official
[Sherpa-ONNX TTS release](https://github.com/k2-fsa/sherpa-onnx/releases/tag/tts-models).
Its [Piper conversion documentation](https://k2-fsa.github.io/sherpa/onnx/tts/piper.html)
describes adding ONNX metadata; the existing Piper runtime successfully loaded
both supplied models with their bundled original configuration files. No new
synthesis engine, package dependency or cloud call is needed. TLS stayed enabled.

`human-test/voices.lock.json` pins the actual distributed archives and extracted
files. Installation extracts only the model/config, not bundled executables or
auxiliary speech data. The existing Piper installation supplies the phonemizer.

Voice-specific terms are preserved rather than inferred from the engine license:
[Rohan's model card](https://huggingface.co/rhasspy/piper-voices/blob/b75a4d669179940fa44b21a03b2bf0ee3b621817/hi/hi_IN/rohan/medium/MODEL_CARD)
links the IIT Madras IndicTTS dataset terms;
[Priyamvada's model card](https://huggingface.co/rhasspy/piper-voices/blob/main/hi/hi_IN/priyamvada/medium/MODEL_CARD)
lists CC BY-NC-SA 4.0 for the dataset, including its noncommercial restriction.
This installation does not establish commercial distribution rights.

## Native evidence

Synthetic text: “मेरा नाम एलेक्स है। मुझे कल से खाँसी हो रही है।”

| Hindi voice | Initial load | Synthesis | Audio duration |
|---|---:|---:|---:|
| Rohan, male | 2.128 s | 0.526 s | 4.354 s |
| Priyamvada, female | 1.998 s | 0.251 s | 3.982 s |

These are sample observations on the laptop, not controlled full-interview latency
measurements. Repeated loads reused the same resident object. A separate short
male Hindi sentence completed through `PiperEngine.play` and the real default
sounddevice output stream. This confirms the output path, not a human listening
or clinical-pronunciation assessment. Sample files and measured results:
`.test_artifacts/hindi-voice/hindi-male.wav`, `hindi-female.wav`, `verification.json`.

## Reviews and checks

First review found that the installer accepted only flat gzip archives. Added
compression auto-detection, an explicit archive prefix and member size/hash checks
before replacing any destination file. Regression checks cover both archive
layouts, ignored traversal members, rejected symlinks, corruption and cleanup.

Second review checked actual voice selection, saved Hindi/automatic language
behavior, cache reuse, restart requirements and existing English playback. No
runtime/controller change was needed. The manifest is read on selection, so an
already running current Human-test app discovers the new voices; re-save the
patient setup to warm Hindi ahead of the first reply. PMS/Qwen/Whisper need no
restart for this voice installation.

- `HUMAN_TEST_SPEECH=1 uv run pytest -q --tb=short tests`: **120 passed**, no skips.
- Ruff lint/format and mypy for Human-test: passed.
- Offline wheel/source build: passed.
- Installer verification: all four voices installed; repeated install reused them.
- No application database, API, LLM output limits or provider credentials changed.
- API/database suites and live cloud/Pi hardware were not exercised for this
  desktop-only installation; no end-to-end spoken clinical interview was claimed.
