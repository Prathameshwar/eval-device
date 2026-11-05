# Portable Human-test client

The portable package contains the Human-test desktop, its private Python/Tcl runtime,
microphone/speaker/camera libraries, the shared training-client runtime, clinical
contracts and the thin central inference client. Client libraries are installed inside the Human-test runtime's
`Lib/site-packages/`. There is no Local Models application folder in this package.

Model engines, weights, downloads, native inference runtimes, service workers and
manager credentials belong to the separate Local Models distribution. This builder
has no GPU, model-bundling or model-protection choices.

## Build

Run `start/build-human-test.bat` from any directory. The default offline build uses
locked cached wheels. `--online` permits fetching missing desktop dependencies.

| Option | Purpose |
| --- | --- |
| `--online` | Fetch missing locked desktop/build dependencies |
| `--no-zip` | Produce the verified executable folder without a ZIP |
| `--protection cython` | Default: native protection for 11 desktop/shared runtime modules |
| `--protection none` | Development source build; publishing refuses it |
| `--protection-python PATH` | Existing build-only Python with pinned protection tools |
| `--vc-runtime PATH` | Visual Studio x64 CRT redistributable directory |

Protection applies to Human-test and its extracted training-client logic. Shared clinical contracts and the
HTTP inference client are ordinary runtime dependencies; this build does not
compile or obfuscate Local Models code. Protection raises inspection cost;
bytecode/native strings remain recoverable. Compilers are not shipped.

The builder creates one private desktop environment, performs executable self-tests,
and writes an immutable release folder, ZIP, file manifest and archive SHA-256.
The filename uses `Human-test-windows-x64-runtime-protected-...` and the ZIP extracts
to `Desktop-App/`. The runtime metadata declares application `human-test` and role
`client`, with no model/GPU configuration.

Source selection includes only app/runtime launch modules and excludes benchmarks,
setup metadata, tests and unrelated applications. Build/self-test/publication scope
checks reject model assets, known native engine packages, management scripts,
private credentials/state and paths outside the client layout. New packages must
be rebuilt; the former GPU build wrapper and model-bundle refresh tool are removed.
The OpenCV wheel includes unused pretrained Haar cascade detectors by default;
the builder removes them and rejects any remaining cascade/model assets before
creating a release. It also removes dependency test suites from installed wheels.

## Run

Extract the whole folder and run `Human-test.exe`. No Python installation is needed
on the destination. Enroll that device independently. Cloud assignments use the
platform API. For local assignments, install/provision/start services separately
in Manage Local Models before opening Practice.

The connection window uses the hosted API default and saves enrollment under
`human-test/.local/`. For manual settings, copy `human-test/.env.example` to
`human-test/.env` in the extracted folder and edit the copy. The example has no
credentials; the build never includes an enrolled `.env` or `.local` state.

Set `HUMAN_LOCAL_MODELS_STATE_DIR` in the app's `.env` to the separate manager's
private `.manager` directory and set `HUMAN_LOCAL_MODELS_PORT` if it differs from
8790. Both currently run under the same Windows operator. Human-test reads only
the inference-client credential. Closing Human-test leaves model services running.

`Human-test.exe --self-test` checks package scope, native app imports, isolated
runtime paths, Tcl and recording-process startup without enrollment, inference,
camera or microphone calls. It checks the release manifest, so it also works after
the app has created its private `.env` and `.local` files. Live cloud and
physical-device checks remain separate.

## Release tooling

After reviewing a protected client ZIP, the local publication tool accepts only:

```powershell
python start/publish_desktop_downloads.py --root PATH_TO_DOWNLOADS --client PATH_TO_PROTECTED_ZIP
```

It verifies archive scope, metadata, file hashes and the ZIP sidecar before atomically
publishing the immutable file and catalog. The existing `desktop-runtime` catalog
identifier remains for API compatibility; there is one Human-test client package.
Historical hosted archives stay untouched until a separately authorized publication.
Local Models packaging and downloads will have their own workflow.

Private history, recordings, pairing and launcher logs remain under `human-test/.local/`.
See [Human-test usage](../human-test/README.md), [central client migration](local-model-client-migration.md),
and [platform/client boundary](human-test-api-boundary.md).
