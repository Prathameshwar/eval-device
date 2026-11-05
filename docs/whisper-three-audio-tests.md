# Three audio tests per Whisper model

Completed 2026-09-19.

[Open the offline report with three audio players](../.test_artifacts/whisper-three-tests/index.html)

Fresh sequential runs through the current audio API: small, medium, large-v3-turbo, then large-v3. Windows / Core Ultra 7 165H / approximately 64 GB RAM; CPU INT8, four threads, beam 1. Each model was loaded and warmed once for all three tests, with background audio/text recording enabled. The selected clips repeat the first human English and Hindi examples and the mixed_pain synthetic example from the previous comparison; this is a demonstration, not a new held-out benchmark.

After input means the delay from the end of paced audio upload to the API complete event. Total includes audio streaming plus that delay. Model startup and recording-finalization polling are excluded. No Pi, Wi-Fi, dialogue model, reply TTS or speaker playback is measured. This is one run per clip/model on the available 64 GB host, not target-16GB acceptance.

Word error rate (WER) is reference word edits divided by reference word count; lower is better. Case and punctuation are normalized, but spelling, word splits and transliteration count as errors. It is not a semantic accuracy percentage. Read the quality notes and listen to the source audio, especially for the artificial mixed-language clip.

## Test 1: English - human recording

[Listen to input audio](../.test_artifacts/whisper-three-tests/audio/test-1.wav) (3.30 seconds; language setting: `en`).

Reference: He built a WiFi door bell, he said.

| Model | After input | Total | Exact returned transcript | Word edits / reference words (WER) | Quality review |
|---|---:|---:|---|---:|---|
| small | 2.39 s | 5.68 s | He built a wifi doorbell. | 4/8 (50.0%) | Partial: omitted 'he said'; word-joining also differs. |
| medium | 7.49 s | 10.78 s | He built a Wi-Fi doorbell. | 5/8 (62.5%) | Partial: omitted 'he said'; hyphenation and word-joining also differ. |
| large-v3-turbo | 14.34 s | 17.65 s | He built a Wi-Fi doorbell, he said. | 3/8 (37.5%) | Complete meaning; only hyphenation and word-joining differences. |
| large-v3 | 16.63 s | 19.92 s | He built a Wi-Fi doorbell, he said. | 3/8 (37.5%) | Complete meaning; only hyphenation and word-joining differences. |

Public FLEURS development-set recording.

## Test 2: Hindi - human recording

[Listen to input audio](../.test_artifacts/whisper-three-tests/audio/test-2.wav) (5.58 seconds; language setting: `hi`).

Reference: हालांकि तीन लोग घर के अन्दर थे फिर भी जब कार टकराई तब किसी को भी चोट नहीं आई।

| Model | After input | Total | Exact returned transcript | Word edits / reference words (WER) | Quality review |
|---|---:|---:|---|---:|---|
| small | 4.23 s | 9.81 s | आलाकी तीन लोग गरके अंदरते फिर भी जब कार तक्राई तब किसी को भी चोट नहीं आई. | 6/19 (31.6%) | Main event and no-injury meaning retained; several spelling and word-boundary errors. |
| medium | 15.83 s | 21.41 s | हालाकि तीन लों घर के अंदर थे फिर भी जब कार तक्राई तक किसी को भी जोट नहीं आई | 6/19 (31.6%) | Main gist retained, with errors in the words for people, collision and injury. |
| large-v3-turbo | 12.49 s | 18.06 s | हाला कि तीन लोग घर के अंदर ते फिर भी जब कार टकराई तब किसी को भी चोट नहीं आए | 5/19 (26.3%) | Main meaning retained; some spelling and grammatical agreement errors remain. |
| large-v3 | 21.57 s | 27.14 s | हाला कि तीन लोग घर के अंदर थे फिर भी जब कार टकराई तब किसी को भी चोट नहीं आई | 3/19 (15.8%) | Closest wording in this test; meaning preserved, with an initial-word split/spelling difference and one spelling variant. |

Public FLEURS development-set recording.

## Test 3: Mixed Hindi/English - synthetic stress case

[Listen to input audio](../.test_artifacts/whisper-three-tests/audio/test-3.wav) (3.96 seconds; language setting: `auto`).

Reference: मुझे chest pain तीन दिन से है।

| Model | After input | Total | Exact returned transcript | Word edits / reference words (WER) | Quality review |
|---|---:|---:|---|---:|---|
| small | 6.54 s | 10.49 s | Mugia! Kestai! Din din se heia! | 7/7 (100.0%) | Poor: does not reliably recover chest pain or three days. |
| medium | 15.98 s | 19.93 s | (empty) | 7/7 (100.0%) | Failed this clip: no text returned; the API correctly reported a skipped empty recognition. |
| large-v3-turbo | 23.00 s | 26.97 s | Mugia. Chest pie. Din vince heia. | 6/7 (85.7%) | Poor: chest pain became 'Chest pie'; the duration was not recovered reliably. |
| large-v3 | 37.80 s | 41.77 s | Moogia. Cast Pie. Dean Vincey Heia. | 7/7 (100.0%) | Poor: garbled wording; chest pain and three days were not recovered reliably. |

Synthetic voices joined together; this is not natural Hinglish or clinical acceptance evidence.

## Startup and verification

Startup is paid once per model process, not per request.

| Model | Load + warmup |
|---|---:|
| small | 5.45 s |
| medium | 11.63 s |
| large-v3-turbo | 15.70 s |
| large-v3 | 17.13 s |

All 12 saved WAVs match the input PCM exactly; all saved transcripts match the delivered text. All model processes and measurement servers exited. Per-case scores were recomputed during final review. Production code/settings were not changed; platform/database suites were not rerun for this benchmark-only task.

An initial Medium attempt exposed a benchmark assertion that incorrectly required one transcript per processed chunk. The API correctly skipped an empty recognition result. The checker now verifies the count of delivered transcripts, and Medium's full three-test run was repeated. The initial attempt's log/partial results and recordings were retained; the tables contain only the completed final runs.

Human recordings and references: Google FLEURS, CC BY 4.0. Audio was converted to mono 16 kHz PCM16 without trimming. The mixed clip uses local eSpeak NG voices; all audio is public/synthetic, not private patient data. [Source and license](https://huggingface.co/datasets/google/fleurs).

Local evidence: `.test_artifacts/whisper-three-tests/{cases.json,quality-notes.json,small.json,medium.json,large-v3-turbo.json,large-v3.json,verification.json}`; scripts `run.py` and `report.py`.
