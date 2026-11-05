# Qwen3 4B local validation

Completed 2026-09-19 on the available Windows laptop: NVIDIA RTX 500 Ada laptop GPU, 4,094 MiB VRAM, driver 573.57, Core Ultra 7 165H, approximately 64 GB system RAM.

**Download, installation, native GPU inference, CPU mode and the primary Windows batch launcher were exercised successfully.** Existing audio/video/platform implementations and private settings were not changed.

## Installed and verified

- Qwen3 4B Q4_K_M GGUF: 2,497,280,256 bytes. SHA-256 `7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5`, matching the official Hugging Face pointer and official ModelScope metadata.
- Retrieved from Qwen's pinned ModelScope revision because the Hugging Face download returned HTTP 403 on this network. Normal TLS verification remained enabled; no network filters were changed.
- llama.cpp b11046 CPU and CUDA 12.4 Windows x64 archives plus project-local CUDA libraries; all three archive sizes and publisher SHA-256 digests passed. Per-file native runtime manifests are verified before each launch.
- Python standard-library scripts; no new Python packages, system CUDA toolkit or system driver changes. Native/model requirements are pinned in `assets.lock.json`; `requirements.txt` explains the Python requirement.
- The large download was restarted from verified final assets/completed chunks with eight bounded download workers. Final complete-file SHA-256 passed before inference.

## Actual execution and timing

GPU execution reported **37/37 layers offloaded**, using one process/model for three sequential demonstration prompts and the attached batch client. Default profile: context 2,048, maximum 192 generated tokens, one slot, six CPU threads, thinking disabled.

Startup including file integrity verification, model load and warmup: **11.45 seconds**. Native buffers: model **2,375.91 MiB**, KV **288 MiB**, compute **19.25 MiB**. Device-wide NVIDIA samples peaked at **2,769 MiB** and **93% utilization**, across 19 samples. Sampling can miss brief peaks; this is not a worst-case or per-process memory guarantee. GPU memory returned to zero after the tests.

| Prompt | First content token | Complete reply | Completion tokens |
|---|---:|---:|---:|
| english | 0.078 s | 0.141 s | 3 |
| hindi | 0.069 s | 0.918 s | 34 |
| fictional_patient | 0.078 s | 0.565 s | 20 |

These are single warm local requests with short prompts. Timings exclude model startup and audio/TTS work. Prompt caching may reuse a small shared prefix. They are demonstration timings, not sustained-load benchmarks.

The English arithmetic answer was `20`. The Hindi answer was:

> मुझे आपके सभी सवाल का जवाब देना होगा।

It produced Hindi successfully, but this phrasing is awkward and does not establish strong Hindi conversational quality.

For the fictional patient fixture, the supplied facts were a three-day cough and unknown allergy history. The response was:

> I have had a cough for three days. I do not know if I have any allergies.

This answer preserved the two tested facts. It does not establish clinical accuracy, resistance to invented facts over many turns or a completed patient behavior implementation.

Explicit CPU mode also loaded the model with **0 GPU layers** and answered `5` for `2 + 3`: first token **1.08 seconds**, full reply **1.20 seconds**, startup including integrity checks **9.78 seconds**. This CPU prompt differs from the three GPU prompts, so these are functionality checks, not an equivalent CPU/GPU benchmark.

## API, launch and shutdown checks

- Missing/wrong API keys rejected with HTTP 401. Authentication succeeded using the private local credential file without printing its value or putting it on the process command line.
- Duplicate instance rejected before model loading; the resident instance continued operating.
- Oversized context rejected; no silent truncation of scenario instructions.
- `chat.bat` attached to the resident GPU model and answered a new arithmetic prompt without loading another model.
- **`start-llm.bat` was invoked from outside this folder**, loaded the GPU model, answered `15` for `7 + 8`, handled `/quit` and exited with code 0.
- GPU/CPU server processes stopped after normal cleanup. Force-terminating the owned launcher also terminated its exact native child through the Windows job object, verified by waiting on that process handle.
- No inference POST was automatically retried. No prompt/reply logs are saved by the launchers; only the explicitly synthetic test prompts/replies were stored as validation evidence.

The credential setup calls succeeded with the protected current-account/SYSTEM DACL policy. Independent DACL inspection through PowerShell, icacls and GetNamedSecurityInfo was denied by this host even after escalation, so independent ACL inspection is not claimed. The actual batch/native client did successfully read its key and authenticate. No credential permissions were weakened to make inspection pass.

## Two review passes and fixes

First review covered pinned downloads, checksum/range/size validation, archive publication, optional CPU/CUDA installation, configuration/input bounds, local authentication, logging and process cleanup. Added cancellation of queued downloads after failure, restored inherited workspace ACLs for newly staged public binaries, narrowed CORS to the local origin, and retained streaming finish/usage metadata.

Native validation exposed two confirmed findings, both fixed:

1. At verbosity 3 this runtime hid its native GPU-offload summary. Readiness correctly refused to assert GPU use. Set verbosity 4, retained only numerical GPU/startup fields and continued discarding raw native logs. Native 37/37 offloading was then confirmed.
2. Windows byte-range locking rejected a read of the instance-lock byte by a second launcher, and cleanup attempted to unlock a lock it did not own. Removed the pre-lock read, tracked ownership and added a real Windows locking regression. Duplicate-launch and cleanup tests then passed.

Final review revisited the finished files after these fixes and checked native outputs, exact entry-point execution, credentials handling, absence of implicit CPU/cloud fallback, model residency and process release. Both reviews were by the same implementation agent.

**14 unit/regression tests passed**, Ruff and formatting passed, and Python compilation checks passed. Native checks above passed. Platform/database/audio tests were not rerun for this isolated new folder; no application database was accessed. Actual Pi/Wi-Fi, simultaneous Whisper/video/TTS load, long natural Hindi/Hinglish conversations and medical-simulation acceptance remain untested.

Evidence: repository-root `.test_artifacts/local-llm/{verify.py,results.json,hold.py,checks.json,acl-check.json}`, retained failed-attempt JSONs, startup diagnostic and published asset metadata. Use [README.md](README.md) for launch and configuration instructions.

## Follow-up implementation review

See [review.md](review.md) for the subsequent fixes, 25 passing tests, fresh full/partial GPU and CPU execution, all four batch entry points, and successful ACL inspection under the interactive Windows account. The repaired installation now has independently inspected credential permissions; the earlier inspection limitation above is historical.
