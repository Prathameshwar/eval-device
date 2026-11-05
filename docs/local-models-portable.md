# Portable Manage Local Models

Build on Windows x64 with Python 3.12, `uv`, the Visual Studio x64 CRT files, and
the .NET Framework C# compiler:

```powershell
.\start\build-local-models.bat
```

The resulting `Local-Models-windows-x64-runtime-protected-*.zip` extracts to
`Local-Models/`. Run `Local-Models.exe` from a writable local folder. The build
requires verified local installations of Qwen 3.5 4B Q4_K_M, Whisper large-v3,
the Ryan English voice, and both pinned llama.cpp CPU/CUDA engines. It bundles
only these models, the two native engines, isolated ASR/TTS Python dependencies,
the manager UI and service, Python/Tcl, and `uv`. First run needs no model or
runtime download. An NVIDIA driver and compatible GPU are still needed for GPU
inference; CPU mode is available for Qwen and Whisper.

The build verifies local model hashes and native engine manifests before copying.
The package excludes all other installed models, manager keys, worker credentials,
saved configuration, and download caches. Audio includes Whisper speech recognition
and the default English synthesis voice. Video recording uses no model; the video
inference action is disabled pending an adapter.

Five manager modules are compiled with Cython. Remaining manager, desktop,
installer and audio adapter code is bytecode. This raises inspection cost, but
does not make strings or algorithms secret. The Cython compiler and build tools
are absent from the release. `uv`'s Apache and MIT license texts are included.

`Local-Models.exe --self-test` checks native imports, catalog/config defaults,
private Python paths, Tcl, bundled `uv`, and child-process startup. It makes no
model download or inference request. The build writes a file manifest and SHA-256
sidecar for the ZIP. Extract the complete ZIP; the archive is several gigabytes.

For Human-test local assignments, point `HUMAN_LOCAL_MODELS_STATE_DIR` at this
installation's `local-models/.manager` folder. Keep the two applications under
the same Windows operator account; Human-test reads only the inference client
key. Closing either desktop window leaves the manager and workers running.
