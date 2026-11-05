# Tenant clinical release on the Ubuntu VM

This is the operator checklist for the coordinated API, web, migration and backfill release at Alembic `0031_case_draft_provenance`. Record actual values and evidence in the review log; local tests are not VM evidence.

## Target VM result (2026-10-01)

Release `20261001-123654-13281` is active on `eval.centralindia.cloudapp.azure.com`. All four systemd services are running. External HTTPS readiness returned 200, and the administrator confirmed that the signed-in `/users` list loads after a hard refresh. The database retained its one administrator and one tenant across this web fix. The pre-upgrade custom-format PostgreSQL backup is `/var/backups/pms-platform/pre-users-fix-20261001.dump` (mode 600, readable by `pg_restore --list`). Certificate-renewal and rollback drills, the hosted two-tenant journey, staff-laptop client and hardware checks remain open. The first deployment's read-only inventory found zero reference-integrity issues before administrator setup.

## Reviewed transfer files

- `start/dist/pms-platform-20261001-123541-a91b86.zip` (SHA-256 `d06fb2437d37b22ab6bd77d4a77997215ab3f7bbe8e78f490816530e39b70a69`)
- `start/deploy-platform.sh` (SHA-256 `b6e94a9de2ec1d4a4bb981f69f52c59a23a4b8ecf2d322a2d033bfc77e2de732`)
- `platform/api/deploy/tenant-clinical-inventory.sql` (SHA-256 `01277c1449c7dd271f31f5e7f00991658f898cf792d3878a60e65d507246cb8c`) for an existing database preflight and postcutover comparison

From the Windows repository root, transfer these three files with the VM access method you already use. For example, with an SSH configuration that authenticates `evaluator`:

```powershell
scp .\start\dist\pms-platform-20261001-123541-a91b86.zip .\start\deploy-platform.sh .\platform\api\deploy\tenant-clinical-inventory.sql evaluator@eval.centralindia.cloudapp.azure.com:~/
```

On Ubuntu, verify the archive before deployment:

```sh
cd ~
sha256sum pms-platform-20261001-123541-a91b86.zip deploy-platform.sh tenant-clinical-inventory.sql
```

The three values must match those above. The deploy script installs Node.js 24 and npm if needed; there is no separate Node setup step.

The release zip contains the platform API and web UI, not the `human-test/` desktop app. Update that client from this reviewed workspace on the staff laptop and restart it before the client smoke check below.

## Before deployment

1. Confirm the tenant capability and two-person publication policy with the hospital representative. A tenant administrator can assign clinical author, reviewer, reader and instructor responsibilities, including to themselves. A reviewer cannot publish their own last content edit. Each hospital reviews imported fictional cases and translations before activation.
2. If `device_platform` already exists, run the transferred inventory read-only on the VM database. With local PostgreSQL peer administration: `sudo -u postgres psql -X -v ON_ERROR_STOP=1 -d device_platform < tenant-clinical-inventory.sql`. Record the Alembic revision, tenant count, mapped/unmapped selections, approved versions, active sessions, device registrations and integrity checks. Investigate any broken reference before changing the database.
3. Quiesce all old catalog writers and new sessions. The single-VM deploy script places Nginx in maintenance mode and stops its systemd services, then checks for other database sessions. If another API replica or writer exists, stop it before continuing.
4. Take and verify a private PostgreSQL backup. For an existing managed release whose revision changes, `deploy-platform.sh` makes a custom-format dump before migration and restores it on deployment failure. On an initial installation over an existing database, take and verify an operator backup first; the script has no preceding managed release from which to infer the rollback revision.
5. Build the release archive with `start/build-platform.bat` from the reviewed checkout. Keep the zip and `start/deploy-platform.sh` together on the VM. The builder requires new deployment source files to be tracked or staged so it cannot omit a migration.

## Deploy

For the first managed deployment, run from an interactive VM terminal:

```sh
sudo bash deploy-platform.sh deploy --archive ./pms-platform-20261001-123541-a91b86.zip
sudo bash deploy-platform.sh status
sudo bash deploy-platform.sh setup-key
```

For an existing installation already managed by this script whose database revision changes, use the protected upgrade flags after the preflight and backup review:

```sh
sudo bash deploy-platform.sh deploy --archive ./pms-platform-20261001-123541-a91b86.zip --allow-schema-upgrade --allow-data-loss
sudo bash deploy-platform.sh status
```

The script installs locked dependencies, builds the UI on Linux, applies the forward migrations, maps every legacy rehearsal selection into inactive tenant copies in batches of 25, checks the mapping, applies runtime grants, starts API/web/worker/retention, and checks local and HTTPS readiness. A failed mapping stops deployment while maintenance mode is active. Keep the old API stopped until the new readiness checks pass. The first managed deployment onto a populated existing database requires a verified operator backup; the script refuses an existing database owned by a different role.

## Verify and reopen

1. Confirm `/health/ready` through HTTPS, Nginx routing, all four services, Alembic head `0031_case_draft_provenance`, and no old API process. The deploy script now requires the managed API and web service PIDs to own ports 8000 and 3000 before reporting ready. Record the release archive hash and backup path.
2. Re-run the read-only inventory SQL with the same command. Compare its tenant counts, mapped/unmapped selections, approved scenario counts, active session counts and integrity observations with the preflight. Preserve any separately captured private selection/document hashes and scenario fingerprints for a row-level comparison. Tenant copies should be inactive until reviewed. Resolve any still-unmapped legacy selection before allowing that staff member to start a new rehearsal.
3. Use two synthetic tenants: grant clinical author to a staff member in Tenant A, import/activate a fictional case, save rehearsal, copy it to a scenario draft, review/publish as a distinct reviewer, and create/lease a training session as an instructor. Confirm Tenant B cannot list, guess, edit or receive Tenant A's case, draft, session or media. Confirm a platform-only administrator cannot open tenant clinical content.
4. Have the hospital representative review the actual patient facts, answers, Hindi/English translations and rubric before routine use. Confirm device registration/physical reassignment procedures and local credential/patient-state wipe on the target hardware. Software checks alone cannot attest the physical identity of a serial-less device.
5. On the staff laptop, launch the updated Human-test client with a tenant account granted organization-wide clinical author and processing execution. Confirm a historical global selection cannot start a new interview, choose the tenant's active specialty/profile/case, enter any missing observations, save, and complete one typed question. Check the patient response and history. Confirm a different tenant's account cannot load this catalog or saved setup. Record the actual client, API and VM results; local mocks do not satisfy this step.
6. In the web app over HTTPS, sign in with an authorized tenant member-import account and download the member import template. This checks that Nginx sends `/api/member-imports/download` to Next.js while `/api/v1/` reaches the API.

## Recovery

Keep traffic blocked and writers stopped after any failed migration or mapping. The deploy script restores its pre-upgrade dump on a failed cross-revision release. A later manual rollback across schema revisions requires the matching dump and `--restore-backup PATH --allow-data-loss`; changing code alone is insufficient. Verify the restored Alembic revision, runtime grants, ready endpoints, selection hashes and tenant mapping before reopening traffic. Record data written after the backup that would be lost by a restore.

Cloud provider calls, Let's Encrypt issuance, target-VM execution, and Raspberry Pi hardware checks require their own recorded results; none are implied by local test passes.
