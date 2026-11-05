# Smaller Qwen installation and model-switch audit

Date: 2026-09-20. Windows laptop with NVIDIA RTX 500 Ada, 4 GiB VRAM.

Qwen3 1.7B Q8_0 is installed as an additional local option. Qwen3 4B remains
the default. Use **Models → Local → Installed response model → qwen3-1.7b →
Set & activate local models**. Restart an already running stack once to load
the updated model registry; subsequent switches keep the desktop open.

## Planned versus implemented

| Requirement | Implementation and evidence |
|---|---|
| Smaller model without replacing 4B | Separate 1.7B GGUF, manifest, setup/start batches and profile. Default configuration and 4B file remain intact. |
| Trusted, resumable installation | Official Qwen ModelScope asset, pinned revision, normal TLS, bounded ranged downloads, final SHA-256 verification. Existing pinned CPU/CUDA runtimes reused. |
| Offer installed models in Human-test | Complete 1.7B and 4B installations discovered; partial assets excluded. Tk dialog regression selects and submits the new model. |
| Actually activate the selected LLM | Existing authenticated local control and PMS publication flow uses the selected alias, then updates the desktop route. |
| Release previous model/GPU | Owned Windows process group is stopped and confirmed exited before loading a replacement. Native switches measured GPU release with Whisper still resident. |
| Failure and restart handling | Failed release blocks a second load; failed load restores the previous model when recovery succeeds. Failed recovery is disabled and no longer reported as active by the catalog. Published aliases restore the correct model at startup. |
| Preserve quotas, credentials and patient context | No API schema, database schema, prompt-policy or permission changes. Context 2,048; local routing 75 and patient answer 100 output tokens. |
| Compare performance and quality | Real PMS patient-pipeline requests in English/Hindi; routing failures retained in evidence, not hidden by changing validation. |

The standalone commands are `local-models/setup-qwen3-1.7b.bat` and
`local-models/start-qwen3-1.7b.bat`; both accept `--cpu`. Merely changing a dropdown
does not activate a model: click **Set & activate local models**. Unchanged
Whisper remains loaded, and selecting the already active pair avoids reloads.
An independently launched model server must be stopped by its owner before the
combined launcher can replace it.

## Provenance

[Official Qwen GGUF model card](https://huggingface.co/Qwen/Qwen3-1.7B-GGUF)
and [Qwen model card](https://huggingface.co/Qwen/Qwen3-1.7B).
Downloaded the official Qwen ModelScope mirror at asset revision
`dc80e1956e7551cd4aa5309c914e767b69188639`.

- File: `Qwen3-1.7B-Q8_0.gguf`, **1,834,426,016 bytes**.
- SHA-256: `061b54daade076b5d3362dac252678d17da8c68f07560be70818cace6590cb1a`.
- Existing 4B Q4_K_M: **2,497,280,256 bytes**. The 1.7B file is about 27% smaller;
  different quantization means parameter count does not directly predict file size.

## Quality limits

The dry-cough case comparison uses six question types, each twice, in the real
PMS prompt-budgeting/routing/answer pipeline. Both models use 16 GPU layers,
six CPU threads, a 256 MiB RAM prompt cache, thinking disabled and the same
75/100 output limits. This measures patient text completion, excluding ASR,
database/authentication, model startup and speech playback.

| Question type | 4B mean completion | 1.7B mean completion | Expected topic: 4B / 1.7B |
|---|---:|---:|---|
| English name | 2.25 s | 1.21 s | 2/2 / 2/2 |
| English cough onset | 4.28 s | 1.64 s | 2/2 / 2/2 |
| English medication history | 4.46 s | 2.34 s | 2/2 / 2/2 |
| Hindi age | 2.70 s | 1.28 s | 2/2 / 2/2 |
| Hindi cough onset | 9.67 s | 2.45 s | 2/2 / 0/2 |
| Hindi medication history | 14.58 s | 1.38 s | 2/2 / 0/2 |

The last two speed figures are **not equivalent-answer comparisons** because
1.7B routed incorrectly. Correctly routed English examples were about 1.9–2.6
times faster in this small sample. Results vary with prompt, output length,
cache and competing laptop work. The table uses `qwen3-4b-quiet.json` and
`qwen3-1.7b.json`; the initial 4B run overlapped installation/checks and is kept
separately rather than used for the comparison.

The 1.7B model correctly routed all six English requests and both Hindi age
requests. It selected the general complaint for Hindi cough onset (still
answering three weeks), and both Hindi medication requests produced the
authored unknown-answer fallback after invalid routing. Therefore **8/12
expected-topic matches** is a narrow routing result, not medical accuracy.
Its benchmark deliberately exits nonzero to flag these failures.

Keep 4B for the stronger observed Hindi behavior. The smaller option is useful
for experimentation and faster English case interviews; this small fixture set
does not establish general clinical fidelity. Patient guards and fallback
behavior were preserved.

## Review and checks

Native activation used the same authenticated desktop control client, launcher
and PMS routes as the Models window, with an isolated database. The sequence
**4B → 1.7B → 4B → 1.7B** completed. Each replaced process exited; Whisper's
process stayed the same. Selecting the active pair again kept both processes.
After each switch, prerecorded audio transcribed to “When did the chest pain
start?” and the selected patient's reply was “It began two days ago.” No live
microphone or speaker was used in this switch check.

| Released LLM | GPU usage before stop | After stop, before replacement | Old process |
|---|---:|---:|---|
| 4B, first switch | 3,067 MiB | 1,653 MiB | Exited |
| 1.7B | 2,985 MiB | 1,653 MiB | Exited |
| 4B, second switch | 3,105 MiB | 1,653 MiB | Exited |

These device-wide snapshots include Whisper; they show release of the LLM's
allocation, not a claim that the entire GPU becomes empty during a switch.
Native model buffers at 16 GPU layers were 1,177.62 MiB (4B) and 1,080.55 MiB
(1.7B). The shared-GPU policy stays conservative to leave room for transcription.

Separate standalone checks also passed on CPU (zero GPU layers) and full GPU
(29/29 layers). Both answered the supplied fictional onset fact correctly.
The full-GPU sample used 2,065 MiB device-wide and returned to zero after stop.
That short, 51-input-token probe is not equivalent to the larger PMS prompts in
the timing table. Full GPU was checked with Whisper stopped; the combined app
continues using 16 GPU layers. All test-owned model/API/database processes were
stopped at completion.

Review 1 checked model provenance, independent assets, CLI selection, catalog
discovery and persisted aliases. Updated the places that previously assumed
only 4B/QwenMedic, including restart selection. Review 2 checked process release,
rollback, route propagation and quality evidence. Fixed the catalog reporting a
failed/disabled recovery as an active model and reran the switch regressions.
Corrected integrity-failure guidance to name the selected model's setup batch,
and verified that a same-size corrupted 1.7B asset is rejected before loading.

- Local LLM unit checks: **37 passed**.
- Launcher checks: **93 passed**, including release ordering, failed unload,
  rollback, model discovery and saved-alias restoration.
- Human-test model-client/Tk checks: **12 passed**.
- Focused PMS patient/LLM checks: **87 passed, 2 skipped**. The two database-backed
  cases lacked a dedicated `PMS_TEST_ADMIN_DSN`; they were not pointed at an
  application database. Native switching separately uses a fresh disposable
  PostgreSQL cluster and fictional seed data.
- API Ruff lint/format and mypy passed; affected launcher/local-LLM lint/format
  and Human-test mypy passed. New Windows batch argument forwarding checked.

No application database or saved application model selection was changed by
verification. Live cloud calls and Raspberry Pi hardware were not tested.
Native scripts and non-secret result JSON are under
`.test_artifacts/smaller-qwen/`; temporary test database state remains private.
