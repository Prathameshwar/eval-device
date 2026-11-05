# Local Models protected portable review - 2026-10-11

This records the earlier manager-only build. The later bundled-model build is
reviewed in [the bundled portable review](local-models-portable-review-20261011-bundled.md).

## Scope and implementation

The separate package contains Manage Local Models, its detached manager and
installers, pinned catalogs and runtime project locks, audio adapter code, private
Python/Tcl and bundled `uv` with its license texts. It excludes installed models,
native inference engines, GPU libraries, download caches, manager state and keys.
Models and isolated native runtimes are prepared only through explicit verified
manager actions after extraction. Human-test remains a separate client package.

Five manager modules (`assets`, `catalog`, `manager`, `security`, `storage`) are
Cython native extensions. Other application modules are bytecode, with small
entry shims where direct script execution is required. Build tools and source
for protected modules are absent from the ZIP. This protection raises inspection
cost, not secrecy guarantees.

The runtime preparation calls now pass the bundled manager's `sys.executable`
to `uv sync`, so ASR, TTS and medical conversion do not depend on a system Python.
The release verifier checks package paths, inventory, hashes, metadata and the
exact native module set. The executable self-test runs after relocation and
allows private state created during normal use.

## Build and verification

Final archive:
`start/dist/Local-Models-windows-x64-runtime-protected-20261011-084045-222585.zip`

SHA-256:
`8829eb23a692ecfd06c2d50ea37a581ca07e0e42b5e573614dffe0aa9f29a844`

The ZIP has 2,217 files and is 37,651,646 bytes. Full archive hashes and its
adjacent SHA-256 sidecar match. The packaged scope has no model weights, private
state or downloaded runtimes. The final folder and a fresh extraction into a
path with spaces both passed `Local-Models.exe --self-test`; the extracted copy
also passed `--help` after a harmless `.manager` fixture was created.

An isolated manager launched from the extracted package, answered an authenticated
loopback status request, and shut down cleanly without a model. The Local Models
unit suite passed 101 tests when the shared training contracts source path was
available; portable packaging passed 16 tests. Targeted Ruff check and format
checks passed. No publisher download, model load, CUDA execution, clinical
inference or hardware verification was performed.
