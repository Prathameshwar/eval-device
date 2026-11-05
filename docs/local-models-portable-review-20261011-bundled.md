# Local Models bundled portable review - 2026-10-11

## Result

The Windows x64 protected Local Models ZIP now includes verified Qwen 3.5 4B
Q4_K_M, Whisper large-v3, and the default Piper Ryan English voice. It includes
the pinned llama.cpp CPU and CUDA engines, an isolated ASR environment with its
CUDA dependencies, and an isolated TTS environment. Video recording requires no
model; video inference has no adapter and remains disabled. No other installed
model directory, manager key or state, or download cache was packaged.

The build fails if a selected model or native engine fails its pinned hash or
manifest verification. A fixed asset inventory restricts package paths and is
checked against the archive manifest and full archive hashes. Model and native
runtime binaries are stored without recompression to keep packaging practical.
ASR and TTS environments are built from frozen locks and repaired to the private
Python home after extraction. Five manager modules remain Cython extensions;
application scripts and adapters remain protected bytecode.

## Review fixes

- Added the missing `run.py` and `client.py` dependencies used by the LLM worker.
  The extracted self-test now imports both.
- Normalized duplicate Windows `Path`/`PATH` entries before the .NET Framework
  launcher creates its child environment. A fresh extraction originally failed
  because its parent supplied both spellings.
- Removed dependency test folders and bytecode caches from the isolated runtimes.
  Private state and unselected asset paths remain prohibited by the package
  validator.

## Verification

Final local artifact:
`start/dist/Local-Models-windows-x64-runtime-protected-20261011-090830-832271.zip`

SHA-256: `a444d0ab2f952ac6cc0935afdd969f0c331fe407762daa9a992de77da1faf422`

The ZIP is 7,852,997,778 bytes with 6,160 files, including 3,938 selected asset
files. Full archive hashes and its SHA-256 sidecar passed build verification.
A separate fresh extraction passed `Local-Models.exe --self-test` and an isolated
authenticated manager status and clean shutdown check. The self-test verified
all three model hashes and imported ASR/TTS dependencies from private Python
paths inside the extracted folder.

From an extracted copy, Whisper large-v3 initialized on CPU, Piper synthesized
its startup phrase, and the CPU llama.cpp server loaded Qwen 3.5 and processed
loopback completion requests. The test server was stopped and its port closed.
Focused packaging tests: 17 passed. Ruff check and format checks passed.

Actual CUDA inference and video inference were not verified. CUDA requires a
compatible NVIDIA driver and GPU. The protected build raises inspection cost;
it does not conceal strings or algorithms from a determined reverse engineer.
