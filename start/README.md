# Windows launchers

## Manage Local Models desktop

Double-click [start-local-models.bat](start-local-models.bat), or run it from
PowerShell in the repository root:

```powershell
.\start\start-local-models.bat
```

The batch file opens the existing Manage Local Models desktop and works from
other working directories. It forwards arguments; `--preview` opens the sample
layout and `--help` shows usage without opening a window. Python 3.12+ with
Tcl/Tk must be on PATH. See [local-model setup and controls](../local-models/README.md).
Closing the desktop leaves background inference running. Windows service
registration and reboot auto-start remain queued.

## Build an Ubuntu VM transfer archive

Run `start/build-platform.bat` on Windows with Python 3.12 or 3.13, Node.js/npm,
uv, and Git on PATH. The command runs `npm ci` and a Next.js production build,
builds platform-independent API and `training-contracts` wheels, then writes a
timestamped `start/dist/pms-platform-*.zip`. It fails if deployment source files
are untracked, so the archive cannot silently omit new source. Existing archives
are kept.

The zip contains the production Next.js build, API wheels, migration and grant
files, npm/Python lockfiles, and source needed for a Linux-side rebuild. It does
not contain `node_modules`, a Python virtual environment, local `.env` files,
keys, or media. Keep the archive private because it contains application source.
The build refuses local web `.env` files and strips platform build variables from
its child processes so local settings cannot be captured during compilation.
The Ubuntu deployment script is [deploy-platform.sh](deploy-platform.sh). Copy
it alongside the zip to the VM. It rebuilds the UI on Linux, so the Windows
Next.js output is a checked transfer artifact rather than a portability
assumption.

On the Ubuntu VM, run the following as an administrator. The script defaults
to `eval.centralindia.cloudapp.azure.com` and uses
`net.pratham@hotmail.com` for Let's Encrypt expiry notices:

```sh
sudo bash deploy-platform.sh deploy --archive ./pms-platform-YYYYMMDD-HHMMSS-XXXXXX.zip
sudo bash deploy-platform.sh status
```

That single `deploy` command installs the required Ubuntu packages, Node.js 24
and npm; creates the API virtual environment; installs locked Python and Node
dependencies; builds the UI; creates the database when needed; applies
migrations, maps existing legacy rehearsal selections into private tenant catalogs,
applies grants, and configures systemd, Nginx and HTTPS. Migrated cases remain
inactive until a tenant clinical author reviews and activates them. The command also creates
`device_platform`, an owner and three unprivileged PostgreSQL roles, independent
random role passwords and application keys. It
uses local `postgres` peer access where available; otherwise it asks for the
PostgreSQL administrator password on the VM terminal. Do not send that
password in chat or put it on a command line. It keeps the migration-owner URL
root-only in `/etc/pms-platform/migration.url`. The generated master
`/etc/pms-platform/api.env` is also root-only and needs no manual editing for
this VM-local deployment. On deploy, the script derives
separate private `.env` files and Unix accounts for the API, worker and
retention services; each receives only its own PostgreSQL password. The web
service has no database password. VM-local mode uses password sign-in and a
private, 5 GB bounded media directory at `/var/lib/pms-media`. Email invitation
and password-reset delivery and external OIDC sign-in remain unavailable until
real providers are configured in a later deployment. Redis is not used by this
API.

New VM-local configurations set `PMS_LLM_ENABLED=true`, so tenant administrators
can use assigned conversation models. Platform Admin manages **Settings > Models**.
Fresh deployment provides **Whisper large-v3**, **qwen3.5-4b-local**, and **eSpeak NG**
as the three default Models page entries. Deployment runs `init-database` through
migration 0039; upgrades preserve configured or assigned models, and redeployment
does not restore deleted entries. Device runtime downloads and assignments remain
separate. See [Models defaults](../docs/platform-models.md).

Fresh deployments and upgrades also provision training signing automatically after
installing API dependencies. The persistent Ed25519 private key is stored at
`/etc/pms-platform/api/training-private.pem` with root ownership and API-group read
access (0640); the master and API role configurations receive its path. An existing
configured key is preserved, including the earlier hosted repair. Other runtime
roles receive no training key setting. Deployment checks readability and key type
as the API account, then checks the verification-key endpoint after startup.
Failed deployment restores the previous configuration and retains the key for a
retry. A missing or invalid configured key requires recovery of that identity;
deployment never silently rotates it. No manual key generation is needed for a
fresh managed deployment. Back up the private key securely, and distribute only
the public key to training agents through the established trusted channel.
Cloud model calls remain disabled by
`PMS_EXTERNAL_CALLS_ENABLED=false` until the operator separately enables them.
The deployment preserves an existing `/etc/pms-platform/api.env`; for an older
installation showing “LLM access is disabled,” the operator must add
`PMS_LLM_ENABLED=true` to that root-owned file before the next deployment. The
deployment then copies the setting into the private API role configuration and
restarts the API. Do not put provider API keys in these settings; enter them in
the Platform Admin model editor, which stores them encrypted.

After the first deployment, display the one-time web setup key directly on the
  private VM terminal, then paste it into the initial setup screen and create the
first administrator:

```sh
sudo bash deploy-platform.sh setup-key
```

The command refuses redirected output so the key is not copied into a log.

The VM must resolve the DNS name to its public IP and permit inbound ports 80
and 443 in Azure network rules and the VM firewall. The script installs Node.js
24, pinned `uv`, FFmpeg, PostgreSQL client tools and Certbot; it requests and
renews the certificate, builds Linux dependencies, runs migrations and grants,
and starts separate API, web, worker and retention systemd services behind
Nginx. It verifies that the managed API/web service PIDs own their listeners,
that both background services are active, and that API/web readiness and HTTPS
pass before reporting success. The
archive and script must come from a trusted transfer path; the manifest checks
integrity but does not authenticate a sender.

To return to the preceding release when its database revision still matches:

```sh
sudo bash deploy-platform.sh rollback
```

For a release that changes the database revision, deploy with
`--allow-schema-upgrade --allow-data-loss`. The script puts Nginx into
maintenance mode, stops application writers, takes a private PostgreSQL dump,
and restores it automatically if deployment fails. Recovery removes and restores
the managed application schema in a single transaction, including tables added
by the failed upgrade; a restore error rolls back that transaction. A later manual rollback
across revisions requires the matching dump plus `--restore-backup PATH
--allow-data-loss`; restoring an earlier dump removes data written since it
was taken. Before that restore, the script also backs up the current database
so a failed rollback can return to the current release. Backups stay in
`/var/backups/pms-platform`. Keep other writers off this single-VM database
during a deployment. Hosted verification is recorded in
[the API review log](../docs/pms-api-reviews.md).

For a clinical tenant-ownership release, follow the
[tenant clinical rollout checklist](../docs/tenant-clinical-rollout.md) for the
preflight inventory, activation and two-tenant smoke test.

## Platform web UI and API

Local `pms-admin init-local` creates the training key and its setting automatically.
The launcher and `pms-api` also fill a missing setting in an existing local `.env`;
later launches preserve the same key. The launcher checks training readiness and
asks for an API restart if an already-running process still has old settings.

Double-click **`start-platform.bat`** in this folder, or run it from any working directory:

```powershell
C:\Pratham\poc-device\start\start-platform.bat
```

It checks the API and Next.js web UI separately, reuses running platform services, and starts only the missing ones. It waits for API database/schema readiness and the UI readiness endpoint before reporting success. Open **http://127.0.0.1:3000**. The API defaults to **http://127.0.0.1:8000**; `PMS_PORT` in `platform/api/.env` is respected. Newly started services bind to loopback, and the UI's API URL is set automatically for this launch without modifying environment files. A reused UI must identify itself and confirm its API configuration matches the selected local API; an incompatible UI is refused with instructions to restart its owner or choose a free UI port. Older UI builds without the readiness endpoint must be restarted from this checkout. Readiness probes do not follow redirects. Keep the console open for services it starts; **Ctrl+C stops only those services**, leaving reused services running. Closing the console also closes the owned process tree. If both services are already running, the launcher checks them and exits successfully. An occupied port must pass the platform identity/readiness check; unrelated or unhealthy services are never stopped or replaced.

One-time prerequisites:

1. From `platform/api`, run `uv sync --frozen` and `uv run pms-admin init-local` if `.env` is absent.
2. Configure PostgreSQL and authentication in `platform/api/.env`, initialize/upgrade with `uv run pms-admin init-database`, and apply `deploy/grant-runtime-access.sql` as described in the [API setup](../platform/api/README.md). PostgreSQL must already be running. The launcher does not create databases, credentials or administrator accounts.
3. From `platform/ui`, run `npm ci`. Node.js must be on PATH.

On a fresh database, the web UI opens the initial setup wizard. Paste the private
`PMS_INITIAL_SETUP_KEY` generated in `platform/api/.env`, choose the administrator's
name, email and password, then review and create the account. Setup closes once an
account exists. Existing installations continue to the normal sign-in screen.
See [first-run setup](../platform/api/README.md#first-run-web-setup-recommended-for-password-accounts).

Optional overrides and startup verification:

```powershell
.\start-platform.bat --api-port 8001 --ui-port 3001
.\start-platform.bat --check
```

`--check` checks both services, starts any missing ones, then stops only services it started. Existing services stay running. The launcher is for local/test configuration, not hosted deployment. It does not start Human-test, models, processing workers or retention workers. Run workers separately when needed. Startup failures show safe messages; raw child output is suppressed so connection details or tokens cannot be copied into launcher logs. To investigate an API failure, run `uv run pms-api` from `platform/api`; for UI failures, run `npm run dev` from `platform/ui`. Set `PMS_START_NO_PAUSE=1` for scripted use.

## Development UI responsiveness

The platform launcher uses Next.js Turbopack and a development output directory specific to the UI port. Production builds use a separate directory. This prevents a build or a review server from deleting JavaScript used by a running UI. For additional manually started development servers, set a unique `PMS_WEB_INSTANCE` before `npm run dev`. First visits can still take a few seconds to compile; subsequent navigation reuses compiled pages. If updating from an older launcher with missing JavaScript/404 errors, restart the platform launcher and reload the browser once.

## Human-test client

Run `human-test/setup.bat` once, then `start/start-human-test.bat`. Desktop start shortcuts are centralized in this `start/` folder; the old `human-test/start-*.bat` wrappers have been removed. Enter the platform
address, device ID and enrollment token. Saved pairing is reused; `--connect` opens
connection settings. Enrollment, tenant/device scope and model assignments stay
with the platform API. `--check` verifies the saved connection without opening
Practice or submitting inference.

For local assignments, first download/verify, provision and start the matching
services in [Manage Local Models](../local-models/README.md). Human-test uses the
manager's inference-only connection on port 8790; it never starts, stops, installs
or cleans up model services. Closing Human-test releases only its desktop/capture
processes. Cloud assignments continue through the platform API.

The gear icon reopens device connection settings. Clearing provisioning removes
this app's saved enrollment while retaining recordings/history, models and the
platform registration. Local model management is available only in Manage Local
Models. CPU/GPU choice belongs there; old `--audio-device`, `--all-services` and
processing profile hints are compatibility options and do not launch model engines.

After changing the platform assignment, start the matching central service and
reload assigned models in Human-test. The reload also refreshes available voices.
See [Human-test](../human-test/README.md) and [client migration](../docs/local-model-client-migration.md).

### Sign-in after a web deployment

An already-open login tab can reference a Server Action from the previous release. Refresh the page (Ctrl+Shift+R) before signing in. The updated login form detects an unrecognized action, clears the password, and offers **Refresh page**; it does not automatically resubmit credentials. Ordinary connectivity failures still allow retry.


## Human-test portable build scope (2026-10-09)

Use `build-human-test.bat` for the single desktop/runtime package. Only Human-test
code is compiled/obfuscated; shared clinical contracts and the central HTTP client
are installed as ordinary dependencies inside its private runtime. Models, engines,
GPU runtimes, downloads, management services and other applications are excluded.
The GPU wrapper and legacy model-bundle refresh helper are removed. The publication
helper accepts one `--client` ZIP, preserving the API's `desktop-runtime` identifier.
No hosted artifacts are replaced by a local build. See [portable build/run options](../docs/human-test-portable.md).
The separate [Local Models portable build](../docs/local-models-portable.md)
uses `build-local-models.bat`. It bundles the manager, private runtime and verified
download flow without model assets or private manager state.
