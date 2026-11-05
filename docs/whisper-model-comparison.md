# Whisper medium and turbo: practical CPU comparison

Completed 2026-09-19. All four model runs and recording-integrity checks completed successfully.

## Practical decision

**Prefer `large-v3-turbo` over `medium` for the next Hindi/English quality trial.** On this fixed human set, English quality was tied, while turbo produced fewer Hindi word and character errors. Medium's API median was 11.21 seconds versus turbo's 13.01 seconds; that speed saving does not make either suitable for prompt patient replies in the measured CPU configuration.

- **Turbo:** the more useful quality/speed compromise of the two newly downloaded models; keep it available for quality trials and recorded-session transcription.
- **Medium:** faster here, but less accurate in Hindi; there is no compelling reason from this sample to make it the preferred bilingual profile.
- **Small:** fastest, but its Hindi errors are too substantial to recommend it as the accepted bilingual profile based on this sample. It remains a speed baseline.
- **Large-v3:** best human Hindi scores here, with substantially more inference time; suitable for further offline quality evaluation.

This is a provisional selection from a small controlled-input comparison. No tested setting establishes both accurate Hindi interview recognition and prompt full patient responses. Natural learner questions, medication names, negation, real Hinglish, quiet speech/noise/echo and simultaneous camera recording still need acceptance on the actual Pi and 16 GB laptop. CPU-thread/beam/VAD tuning was not swept in this run.

## Scope and method

The user requested actual downloads and tests of multilingual `medium` and `large-v3-turbo`, including transcription quality. Both were downloaded from official OpenAI checkpoint URLs, verified against the SHA-256 values published in the [Whisper source](https://raw.githubusercontent.com/openai/whisper/main/whisper/__init__.py), and converted locally to CTranslate2 INT8 using the same conversion approach as the existing small/large-v3 installations. Tokenizer ID/round-trip checks include Hindi and English. Converted-file hashes were independently checked against their manifests. The standard Hugging Face download route failed in this environment; TLS verification was preserved when using the official checkpoint source.

Model assets live under ignored `device/audio-process/.models/{medium,large-v3-turbo}`. INT8 asset sizes, excluding the tiny checksum manifests: medium 774,216,227 bytes; turbo 819,109,063 bytes. Original checkpoint hashes:

- medium: `345ae4da62f9b3d59415adc60127b97c714f32e89e936602e85993674d08dcb1`
- large-v3-turbo: `aff26ae408abcba5fbf8813c21e62b0941638c5f6eebfb145be0c9839262a19a`

Benchmark host: Windows 11, Intel Core Ultra 7 165H, 16 cores/22 logical processors, approximately **64 GB installed RAM**. This is not the proposed 16 GB laptop acceptance test. Runtime: Python 3.12.9, faster-whisper 1.2.1, CTranslate2 4.8.2, ONNX Runtime 1.30.0. Four inference threads, CPU INT8, beam 1, one model resident at a time in separate sequential processes. Order: small, turbo, medium, large-v3. No GPU, remote inference or runtime weight downloads. Ordinary laptop background activity and thermals were not controlled, so small timing differences cannot establish a reliable ranking.

Each process constructs and warms the existing `FasterWhisperEngine` once, transcribes the same 23 clips, then reuses that engine through four real loopback WebSocket API streams. These stream checks use paced 20 ms PCM frames, actual API segmentation/queues and background recording enabled; console/callback delivery is disabled. The whole-clip accuracy pass uses the current engine and its Silero filter directly, without the API's front-end segmentation. These are distinct measurement paths.

## Fixed input set and scoring

Inputs were selected before viewing model outputs. All are 16 kHz mono PCM16; every inference verifies its PCM checksum. Total input duration: 96.56 seconds.

| Group | Clips | Audio duration | Purpose |
|---|---:|---:|---|
| Human English | 6 | 33.66 s | Paired transcription quality |
| Human Hindi | 6 | 33.06 s | Paired transcription quality |
| Synthetic interview English | 4 | 9.55 s | Onset, duration, negation and medication probes |
| Synthetic interview Hindi | 4 | 11.03 s | Same topic probes |
| Synthetic mixed language | 2 | 8.27 s | Exploratory automatic-language stress cases |
| Digital silence | 1 | 1.00 s | Empty-output check |

Human audio comes from Google's [FLEURS](https://huggingface.co/datasets/google/fleurs), [CC BY 4.0](https://huggingface.co/datasets/google/fleurs/blob/main/README.md). For each language, use the first six development-set utterances encountered in the official archive prefix with duration 2-8 seconds. Preserve the complete utterance, source filename and original reference transcript. These are public general-domain read sentences, not clinical interviews, and this selection is not the official FLEURS benchmark. The local corpus manifest contains exact source paths and references. The six English recordings contain five unique reference sentences: the satellite sentence occurs in two distinct recordings. Both were retained to preserve the preselected input set; content diversity is therefore especially limited.

Synthetic audio uses local eSpeak NG. Mixed clips concatenate Hindi and English synthetic voices and are **not natural Hinglish**. Synthetic failures can reflect pronunciation/voice artifacts as well as recognition weaknesses. Monolingual clips supply the known language (`en`/`hi`); mixed clips use `auto`. This does not measure automatic language detection on the human set.

Scoring applies NFC/case folding, replaces punctuation with spaces, preserves Devanagari combining marks, and computes word/character edit distance. Corpus WER/CER is total errors divided by total reference words/characters, rather than an average of sentence percentages. Lower is better; neither is a semantic or clinical accuracy percentage. No digit/spelled-number aliases or transliteration normalization is applied. Literal target probes are reported separately and manually reviewed for meaning.

## Results

### Human-speech quality and actual API response time

WER = word error rate; CER = character error rate. Lower is better. Each language has six human clips: English 84 reference words/349 characters; Hindi 75 words/266 characters. Timing uses four paced API streams per model, with recording enabled.

| Model | English WER / CER | Hindi WER / CER | Input EOF to API complete: median (range) |
|---|---:|---:|---:|
| small | 5.95% / 0.86% | 52.00% / 24.06% | 2.70 s (2.20-4.89 s) |
| medium | 4.76% / 0.57% | 38.67% / 15.04% | 11.21 s (7.72-12.42 s) |
| large-v3-turbo | 4.76% / 0.57% | 29.33% / 9.02% | 13.01 s (12.04-14.04 s) |
| large-v3 | 4.76% / 0.57% | 21.33% / 6.39% | 21.67 s (20.14-25.76 s) |

The Hindi word-edit counts are small 39/75, medium 29/75, turbo 22/75 and large-v3 16/75. This is a small paired sample, not a population accuracy estimate. English differences are tiny and partly formatting-related; this set does not support a strong English quality ranking.

### Per-stream latency

Each column is the same recording across models. All measured streams produced one transcript chunk. Times are seconds after input EOF.

| Model | Human English | Human Hindi | Synthetic English negation | Synthetic Hindi negation |
|---|---:|---:|---:|---:|
| small | 2.265 | 3.131 | 2.201 | 4.888 |
| medium | 7.720 | 12.417 | 10.758 | 11.662 |
| large-v3-turbo | 12.040 | 14.035 | 13.637 | 12.389 |
| large-v3 | 20.136 | 25.760 | 20.585 | 22.748 |

### Startup, direct-engine throughput and process memory

RTF below 1 would mean processing faster than audio duration. The direct-engine figures cover the 22 speech clips, excluding silence; they are not API response times. Model initialization/warmup occurs once and is excluded from all per-request timing. Memory is for the ASR process alone, in decimal GB: peak resident working set and final private committed memory are different measurements. Neither includes the OS, dialogue model, video service or browser, and these values are not a target-16GB acceptance result.

| Model | Load + warmup | Median whole-clip inference | Total inference / audio duration (RTF) | Peak working set | Final private commit |
|---|---:|---:|---:|---:|---:|
| small | 4.65 s | 4.22 s | 1.037 | 0.61 GB | 3.23 GB |
| medium | 13.22 s | 11.05 s | 2.819 | 1.64 GB | 5.33 GB |
| large-v3-turbo | 17.63 s | 15.11 s | 3.740 | 1.73 GB | 4.18 GB |
| large-v3 | 20.68 s | 22.20 s | 5.197 | 3.22 GB | 7.59 GB |

### Synthetic probes and observed failures

These are secondary stress cases using robotic speech. A passed literal-target probe only means all preselected words/patterns appeared, not that the full statement or clinical meaning was correct. A failed probe can also reflect spelling variation. The main recommendation uses the human recordings.

| Model | Synthetic English WER | English clips passing all target probes | Synthetic Hindi WER | Hindi clips passing all target probes |
|---|---:|---:|---:|---:|
| small | 11.54% | 3/4 | 80.77% | 0/4 |
| medium | 15.38% | 2/4 | 92.31% | 0/4 |
| large-v3-turbo | 15.38% | 2/4 | 84.62% | 0/4 |
| large-v3 | 3.85% | 3/4 | 57.69% | 0/4 |

Selected examples below are taken directly from the paired outputs; the full local [transcript review](../.test_artifacts/whisper-model-comparison/transcript-review.md) preserves every case, including failures.

**Human Hindi example (FLEURS dev)**

Reference: दो घंटों में सरकारी इमारतों के पास दो बम विस्फोट हुए.

| Model | Transcript |
|---|---|
| small | तो गन्तो में सरकारी मार्तो की पास दो बम विस्फोट हुए. |
| medium | वो गणटो में सरकारी इमारतो के पास दो बम विस्फोट हुए। |
| large-v3-turbo | दो घंटों में सरकारी इमारतों के पास दो बम विस्फोट हुए। |
| large-v3 | दो घंटों में सरकारी इमार्तों के पास दो बम विस्फोट हुए |

**Synthetic English example (eSpeak)**

Reference: I have had a fever for three days.

| Model | Transcript |
|---|---|
| small | I have had a fever for three days. |
| medium | I have had a femur for three days. |
| large-v3-turbo | I have had a femur for three days. |
| large-v3 | I have had a Femur for three days. |

**Synthetic English example (eSpeak)**

Reference: I take metformin twice a day.

| Model | Transcript |
|---|---|
| small | I take Met for me twice a day. |
| medium | I take met for mint twice a day. |
| large-v3-turbo | I take meth for mint twice a day. |
| large-v3 | I take metformin twice a day. |

Artificial mixed-language clips passing all literal targets: small: 0/2; medium: 0/2; large-v3-turbo: 0/2; large-v3: 0/2. Because these are concatenated synthetic voices and scoring is script-sensitive, they do not establish a natural Hinglish ranking. Outputs are retained in the paired transcript review.

Models returning empty text for digital silence: small, medium, large-v3-turbo, large-v3. That single case is not a noise/echo hallucination guarantee.


### Interpretation of the measurements

API response latency starts at the sender's input EOF and ends at the API `complete` event. Startup is excluded; background recording finalization is checked separately. This is a single-stream loopback measurement, not microphone/acoustic end-of-speech latency. Pi capture, Wi-Fi/TLS deployment, dialogue generation, reply TTS and speaker playback are not included. There is one pass per clip and four API streams per model: no p95, sustained-load or concurrency claim is supported.

One observed API quality difference is important regardless of model choice. On the first English recording (3.30 s), the API submitted the 0.33-2.64 s window to recognition. Small and medium included the final phrase in their whole-clip outputs but omitted it in their streamed outputs; turbo and large-v3 retained it through the same API window. The original saved WAV matches the complete input exactly. This is recognition sensitivity to the API input window, not recording loss, and does not prove the final words were physically removed. Whole-clip accuracy should not be assumed to match every streamed result. Existing VAD settings were preserved across models; real microphone utterance boundaries still need acceptance.

Word-error scores include formatting effects: the reference "WiFi door bell" and recognized "Wi-Fi doorbell" count as word edits. Character error rate removes spaces and helps distinguish this from changes to content. Drug names, negation and symptom substitutions are inspected directly as well; fluent output alone is insufficient for a patient interview.


## Availability and switching models

Both new models are ready in this workspace. When running from `device/audio-process`, the existing service settings can select either:

| `AUDIO_MODEL_NAME` | `AUDIO_MODEL_PATH` |
|---|---|
| `large-v3-turbo` | `.models/large-v3-turbo` |
| `medium` | `.models/medium` |

An explicit model path takes precedence, so keep the name and path aligned. Model selection takes effect after a service restart; the model is loaded and warmed once before serving streams, not for each call. This benchmark did not switch the operational service profile. Assets are local ignored files, not distributed with the repository.

## Verification and final review

- Four sequential model processes completed successfully: **92 whole-clip recognition checks and 16 paced loopback API streams**. Every API recording finalized as saved.
- The verifier compared every saved WAV's PCM bytes with the input and every saved transcript with the API-delivered text: **16/16 exact audio/text matches**.
- Corpus hashes, all per-case scores, Unicode normalization, edit-distance edge cases and reference self-scores were checked. Result hashes are preserved in `verification.json`. Both new converted-model manifests matched their file hashes; official source checkpoints matched the published hashes.
- First review checked selection before outputs, reference provenance, Hindi combining marks, weighted scoring, one resident model, fixed CPU settings and timing boundaries. A benchmark hardening change explicitly disables callbacks even if future shells define callback environment variables; this hardening is confined to benchmark code.
- Final review checked all raw paired transcripts, numerical aggregates, synthetic versus human evidence, recording integrity, the recognition sensitivity to the API input window and the recommendation's scope. All measurement servers exited with their model processes. This is review by the same implementation agent, not an independent reviewer.
- Eight benchmark scripts passed syntax checks. Application/platform/database suites were not rerun because this task changed model assets, benchmark scripts and documentation, not production code or schema. No live cloud, Pi hardware, Wi-Fi, target-16GB, end-to-end audible response, sustained-load or simultaneous-video verification is claimed.

## Reproduction and evidence

Local scripts and results: `.test_artifacts/whisper-model-comparison/`.

- `download_models.py`: official downloads, bounded range retries, full source hashes.
- `prepare_human.py`, `prepare_corpus.py`, `corpus.json`: fixed inputs, references, source attribution and PCM hashes.
- `compare.py`, `run_comparison.py`: resident-engine and actual paced API measurements.
- `{model}-4threads.json`, `{model}-progress.txt`: per-clip text, scores, timings and stream receipts.
- `summarize.py`, `summary.json`, `transcript-review.md`: weighted metrics and paired output review.
- `verify_results.py`, `verification.json`: result/scorer consistency, exact saved PCM and delivered/saved transcript equality.
- `runtime-versions.json`: runtime versions.

Model conversion scripts are `.test_artifacts/convert_medium_checkpoint.py` and `.test_artifacts/convert_large_v3_turbo_checkpoint.py`; each output directory has `conversion-manifest.json`. No operational environment file, selected service model, platform/database code or video processing behavior was changed.
