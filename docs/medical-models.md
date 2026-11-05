# Optional medical models (English evaluation)

Implementation is available. **The two medical model downloads are currently blocked by this laptop's corporate filter. Neither medical model has been run or benchmarked yet.** Existing Qwen3 4B and multilingual Whisper remain the defaults.

| Component | Selection | Execution |
|---|---|---|
| LLM | `qwenmedic-v1`, API alias `qwenmedic-v1-local` | Qwen3 1.7B medical adaptation, locally converted from publisher F16 to Q4_K_M; explicit CPU/GPU selection |
| Audio | `whisper-medical-v1` | English Distil-Whisper checkpoint converted to CTranslate2 INT8/FP16; existing faster-whisper worker, CPU INT8 or optional CUDA INT8/FP16 |
| Desktop | `start/start-human-test.bat --profile medical` | Whisper Medical CPU -> transcript -> authenticated PMS -> QwenMedic -> JSON/SSE answer |

[QwenMedic publisher](https://huggingface.co/ross-dev/QwenMedic-v1-gguf) and [Whisper Medical publisher](https://huggingface.co/Crystalcareai/Whisper-Medicalv1). The medical labels do not establish an accuracy improvement. QwenMedic is smaller than the existing Qwen3 4B; patient role adherence and Hindi answers remain unmeasured. Whisper Medical is an evolving English fine-tuning workspace. Its base-model metrics are not validation of this checkpoint.

## Install and select

From the repository root, when Hugging Face downloads are accessible:

```powershell
.\local-models\setup-qwenmedic.bat
.\device\audio-process\setup-medical.bat
.\start\start-human-test.bat --profile medical
```

Before starting Human-test, prepare and start the assigned medical model services in Manage Local Models. Human-test reports missing or stopped services during connection checks and uses the existing central platform API. Close an existing Human-test window before changing desktop profiles.

For standalone QwenMedic:

```powershell
.\local-models\start-qwenmedic.bat
.\local-models\start-qwenmedic.bat --server
# Or explicit CPU installation/execution:
.\local-models\setup-qwenmedic.bat --cpu
.\local-models\start-qwenmedic.bat --cpu
```

Alternatively set `"model": "qwenmedic-v1"` in `local-models/config.local.json`. `--model qwen3-4b` selects the original model for a launch. Configs without `model` retain their original behavior. Connect to an existing medical server with `local-models/chat.bat --model qwenmedic-v1`. The GPU flag, context/output token limits, disabled thinking, authentication and request cancellation behavior are retained; no automatic model or CPU fallback is introduced.

For a separately configured audio service, select:

```dotenv
AUDIO_MODEL_NAME=whisper-medical-v1
# Remove an old AUDIO_MODEL_PATH override, or set the matching path:
AUDIO_MODEL_PATH=.models/whisper-medical-v1
AUDIO_GPU_ENABLED=false
```

Start streams with `language=en`. `hi` and `auto` are rejected before recording/inference. Use an existing multilingual Whisper selection for Hindi/Hinglish. After installing the existing optional CUDA extra, `AUDIO_GPU_ENABLED=true` uses the same explicit GPU path; real medical GPU execution remains unverified. Keep CPU audio when sharing the 4 GiB GPU with the LLM until measured.

`start/start-human-test.bat` opens the standard desktop; add `--profile medical` for the compatibility medical profile. Published device assignments choose the actual models. Provision and start the matching services in Manage Local Models before connecting Human-test; choose English for medical recognition. Human-test does not install or start inference services.

For manually configured PMS, create a normal `local_llama_cpp` connection with `base_url=http://127.0.0.1:8787`, `model=qwenmedic-v1-local`, and the private local server API key. Credentials go through the existing encrypted PMS connection API. Use its connection ID in `HUMAN_CONNECTION_ID`, with `HUMAN_AUDIO_MODEL=whisper-medical-v1` and `HUMAN_LANGUAGE=en`. No new database migration or provider protocol is required. This remains a general question/answer test; scenario-grounded patient behavior is separate work.

## Installation and runtime behavior

- QwenMedic setup resolves the publisher's commit and LFS SHA-256 once, freezes them in `.downloads/qwenmedic-v1/source.lock.json`, verifies resumable downloads, then quantizes using the existing pinned llama.cpp CPU archive. The converted GGUF and provenance manifest publish together in `.models/qwenmedic-v1`. The exact QwenMedic source revision cannot yet be recorded because metadata is blocked.
- Whisper Medical pins revision `0ed71770b69e504df1e830694d855e2aeeeb3db3`. Only FP16 safetensors and the required tokenizer/configs download; publisher Git/LFS hashes are verified. Conversion uses local files, safetensors only, and no remote Python code. `requirements-medical.txt` installs a separate `.venv-medical`; the serving environment needs no Torch or Transformers change.
- Installers serialize setup, preserve existing installations, and publish complete models atomically. Verified repeat installs reuse local assets. Repeated serving requests never download, convert, hash or reload models. Integrity checks run once at startup, before warmup/readiness.
- Bounded download retries apply to transient failures, with cached transfers resumable where supported. Permanent policy denials fail clearly. Inference requests keep the existing no-blind-retry behavior.
- Windows trusted certificates are used for the conversion installer. TLS verification stays enabled. The requested one-time `verify=False` diagnostic returned the same corporate 403 as verified HTTPS, for both repositories, including outside the sandbox. Disabling SSL is not a solution to this block.

## Validation and remaining work

Evidence lives in `.test_artifacts/medical-models/` (public synthetic fixtures and numerical test results; no private tokens).

- 160 audio, 31 local LLM and 17 desktop regression tests passed. Audio mypy, Ruff and formatting checks passed. Tests cover model selection, unchanged defaults, explicit device flags, one resident worker, English gating, source/converted checksum failures and permanent download refusal.
- A tiny, randomly initialized Whisper checkpoint was converted through the actual installer with mocked publisher downloads. Actual CTranslate2 CPU encoding, source verification, safe-tensor loading, atomic publication and repeat installation passed. **This is converter validation, not medical model inference or quality evidence.**
- Real standard-profile compatibility passed through the actual audio WebSocket, authenticated PMS and native Qwen server: English non-streaming and Hindi streaming. ASR finalization measured 1.468 s / 2.500 s; LLM generation measured 1.687 s / 3.359 s. These are **existing small-Whisper/Qwen3 4B measurements**, not medical-model results. Both completed without token truncation. Missing medical assets fail before the demo database starts; owned baseline services were stopped.
- Audio and desktop source/wheel builds passed. No PMS API source or database schema changed; the full disposable-database PMS suite was not rerun for this change. The real demo exercised current PMS authentication, encrypted connection handling, JSON and SSE paths.
- Review 1 fixed optional converter dependency isolation, source hash checks, explicit local safetensor loading, language gating and profile/alias consistency. Review 2 fixed test header mutation, a nullable metadata typing issue, restart-safe source-lock writes, model-specific setup errors, and demo connection/readiness validation. Affected tests/static checks and native baseline flow passed after fixes.
- QwenMedic and Whisper Medical native inference, their GPU memory usage, accuracy, latency and medical-to-PMS end-to-end operation remain pending model access. No medical accuracy or speed result is claimed.

To unblock the requested native tests, allow the two exact publisher repositories' Hugging Face metadata/file requests and their legitimate download redirects through the corporate filter, then rerun the setup scripts. Test the same de-identified English clips for both ASR selections, including negations, drug names and numbers, and compare patient-fact adherence with Qwen3 4B before choosing a new default.
