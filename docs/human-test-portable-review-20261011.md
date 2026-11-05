# Human-test protected portable review - 2026-10-11

## Finding and fix

The older protected ZIP contained 17 pretrained OpenCV Haar cascade XML files
from the camera dependency. Human-test does not use those detectors. The builder
now removes the XML files from `cv2/data` while keeping its Python package file.
The shared build/publication path validator also rejects cascade names, common
model-weight formats, and model/weight/checkpoint/voice directories. Tests cover
removal and rejection from a staged release.

The first finished-folder check found that the Windows .NET launcher failed when
its environment contained both `PATH` and `Path`. It now sanitizes Python
environment variables without asking .NET to build that case-insensitive map.
The builder also runs the self-test after relocating the release and before it
exposes the final ZIP name. A failed relocated check restores the staging name.

The earlier self-test rejected a used portable folder because normal `.env` and
`.local` state looked like leaked build inputs. It now checks the fixed release
manifest's file list; the build/publication checks still reject private data in
the released ZIP. The package includes the credential-free `.env.example` so a
fresh extraction has its manual config reference. The example and startup UI
now describe the separate manager path and services without requiring source-only
batch files. Installed wheel test suites were also removed.

## Current build evidence

Built `start/dist/Human-test-windows-x64-runtime-protected-20261011-081108-351812.zip`
with the default offline Cython mode. Its SHA-256 is
`e7f9a365bf0601a588886931383abb82370914372d216fad5a9032142c6e1dc9`.
The ZIP contains 3,479 files, including 11 expected native application modules.
It contains no detected cascade files, model-weight suffixes, or model/weight/voice
directories, and no dependency test suites. The finished-folder self-test passed private imports, Tcl,
recording-process startup, and native-module loading. A fresh extraction into a
directory with spaces, with a harmless `.env` and `.local` fixture added, also
passed `Human-test.exe --self-test`. The archive passed full manifest hash and
publication-scope verification. The app bytecode contains the latest shutdown
message; the compiled controller and sync modules contain their recent shutdown
error messages. The adjacent ZIP SHA-256 sidecar matches the archive.

The 11 selected Human-test/training-client modules use Cython. Other application
modules use adjacent bytecode; Cython and bytecode raise inspection cost but are
not secrecy guarantees. `local_model_client` is transport code for separate
services and contains no model weights.

Packaging and publication regressions: 71 passed. Affected Human-test startup and
external configuration tests: 50 passed. Targeted Ruff checks and
formatting passed. A wider `start/` lint/format sweep reports existing unrelated
issues in platform deployment files; those files were not changed for this review.
No hosted download, enrollment, real camera, or model execution was performed.
The previous locally built ZIPs remain historical artifacts; use the exact verified
filename and checksum above for this source revision.
