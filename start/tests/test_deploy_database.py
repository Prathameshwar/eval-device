"""Optional disposable PostgreSQL check for the VM bootstrap SQL and restore path."""

import os
import shutil
import socket
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import unquote, urlsplit

from start.tests.test_deploy_platform import bash_function, python_block

ROOT = Path(__file__).resolve().parents[2]


def run(
    *args: str,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    quiet: bool = False,
) -> None:
    streams = (
        {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if quiet
        else {"capture_output": True}
    )
    result = subprocess.run(
        args,
        env=env,
        cwd=cwd,
        text=True,
        check=False,
        timeout=180,
        **streams,
    )
    if result.returncode:
        raise AssertionError(
            f"{Path(args[0]).name} failed (exit {result.returncode}) in disposable verification"
        )


@unittest.skipUnless(
    os.environ.get("PMS_DEPLOY_INTEGRATION") == "1", "Set PMS_DEPLOY_INTEGRATION=1"
)
class DisposablePostgresTests(unittest.TestCase):
    def test_bootstrap_migrate_grant_and_restore(self):
        for tool in ("initdb", "pg_ctl", "psql", "pg_dump", "pg_restore"):
            if shutil.which(tool) is None:
                self.skipTest(f"{tool} is not on PATH")
        api_python = ROOT / "platform/api/.venv/Scripts/python.exe"
        if not api_python.is_file():
            self.skipTest("The API Windows virtual environment is unavailable")
        with TemporaryDirectory(prefix="pms-deploy-postgres-") as directory:
            root = Path(directory)
            data = root / "data"
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            run(
                "initdb",
                "-D",
                str(data),
                "-A",
                "trust",
                "-U",
                "postgres",
                "--no-instructions",
            )
            started = False
            try:
                run(
                    "pg_ctl",
                    "-D",
                    str(data),
                    "-l",
                    str(root / "postgres.log"),
                    "-o",
                    f"-h 127.0.0.1 -p {port}",
                    "-w",
                    "start",
                    quiet=True,
                )
                started = True
                api_env = root / "api.env"
                migration_url = root / "migration.url"
                run(
                    sys.executable,
                    "-c",
                    python_block("init_config"),
                    str(api_env),
                    str(migration_url),
                    "eval.centralindia.cloudapp.azure.com",
                )
                sql_file = root / "bootstrap.sql"
                run(
                    sys.executable,
                    "-c",
                    python_block("bootstrap_database"),
                    str(api_env),
                    str(migration_url),
                    str(sql_file),
                    str(root / "roles.pgpass"),
                )
                run(
                    "psql",
                    "-X",
                    "-w",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-h",
                    "127.0.0.1",
                    "-p",
                    str(port),
                    "-U",
                    "postgres",
                    "-d",
                    "postgres",
                    "-f",
                    str(sql_file),
                )
                owner_url = migration_url.read_text(encoding="utf-8").strip()
                owner_password = unquote(urlsplit(owner_url).password or "")
                clean_env = {
                    key: value
                    for key, value in os.environ.items()
                    if not key.startswith(("PMS_", "PG"))
                }
                adjusted_api_env = root / "migration-api.env"
                adjusted_api_env.write_text(
                    api_env.read_text(encoding="utf-8").replace(":5432/", f":{port}/"),
                    encoding="utf-8",
                )
                adjusted_migration_url = root / "migration-owner.url"
                adjusted_migration_url.write_text(
                    owner_url.replace(":5432/", f":{port}/"), encoding="utf-8"
                )
                app_env = {**clean_env, "PYTHONUTF8": "1", "PGCLIENTENCODING": "UTF8"}
                run(
                    str(api_python),
                    "-c",
                    python_block("migrate_database"),
                    str(adjusted_api_env),
                    str(adjusted_migration_url),
                    env=app_env,
                    cwd=ROOT / "platform/api",
                )
                run(
                    str(api_python),
                    "-c",
                    python_block("backfill_tenant_catalog"),
                    str(adjusted_api_env),
                    str(adjusted_migration_url),
                    env=app_env,
                    cwd=ROOT / "platform/api",
                )
                owner_env = {**clean_env, "PGPASSWORD": owner_password}
                connection = (
                    "-h",
                    "127.0.0.1",
                    "-p",
                    str(port),
                    "-U",
                    "pms_owner",
                    "-d",
                    "device_platform",
                )
                run(
                    "psql",
                    "-X",
                    "-w",
                    "-v",
                    "ON_ERROR_STOP=1",
                    *connection,
                    "-f",
                    str(ROOT / "platform/api/deploy/tenant-clinical-inventory.sql"),
                    env=owner_env,
                )
                run(
                    "psql",
                    "-X",
                    "-w",
                    "-v",
                    "ON_ERROR_STOP=1",
                    *connection,
                    "-v",
                    "db_name=device_platform",
                    "-v",
                    "api_role=pms_api",
                    "-v",
                    "worker_role=pms_worker",
                    "-v",
                    "maintenance_role=pms_retention",
                    "-f",
                    str(ROOT / "platform/api/deploy/grant-runtime-access.sql"),
                    env=owner_env,
                )
                backup = root / "backup.dump"
                run(
                    "pg_dump",
                    "-w",
                    *connection,
                    "-Fc",
                    "-f",
                    str(backup),
                    env=owner_env,
                )
                # Simulate an upgrade adding a table which depends on an old
                # primary key. Plain pg_restore --clean cannot remove that key.
                run(
                    "psql",
                    "-X",
                    "-w",
                    "-v",
                    "ON_ERROR_STOP=1",
                    *connection,
                    "-c",
                    "CREATE TABLE device_platform.restore_new_dependency "
                    "(user_id uuid REFERENCES device_platform.users(id)); "
                    "INSERT INTO device_platform.restore_new_dependency VALUES (NULL);",
                    env=owner_env,
                )
                restore_env = {
                    **owner_env,
                    "PGHOST": "127.0.0.1",
                    "PGPORT": str(port),
                    "PGUSER": "pms_owner",
                    "PGDATABASE": "device_platform",
                    "WORK": root.as_posix(),
                    "TEST_BACKUP": backup.as_posix(),
                }
                harness = "\n".join(
                    (
                        "set -euo pipefail",
                        "log(){ :; }",
                        "require_exclusive_database(){ return 0; }",
                        (
                            "psql_owner(){ if [[ ${FAIL_RESTORE:-0} == 1 && $* == *--single-transaction* ]]; then "
                            'psql -X -w -v ON_ERROR_STOP=1 "$@" -c "SELECT 1/0"; '
                            'else psql -X -w -v ON_ERROR_STOP=1 "$@"; fi; }'
                        ),
                        "grant_roles(){ return 0; }",
                        "database_revision(){ psql_owner -Atc 'SELECT version_num FROM public.alembic_version'; }",
                        "EXPECTED_REVISION=$(database_revision)",
                        "release_revision(){ printf '%s\\n' \"$EXPECTED_REVISION\"; }",
                        bash_function("restore_database"),
                        'FAIL_RESTORE=1; if restore_database "$TEST_BACKUP" ignored; then exit 91; fi',
                        "test \"$(psql_owner -Atc 'SELECT count(*) FROM device_platform.restore_new_dependency')\" = 1",
                        "FAIL_RESTORE=0",
                        'restore_database "$TEST_BACKUP" ignored',
                        (
                            "test \"$(psql_owner -Atc \"SELECT to_regclass('device_platform.restore_new_dependency') "
                            'IS NULL")" = t'
                        ),
                    )
                )
                run("bash", "-c", harness, env=restore_env)
                run(
                    "psql",
                    "-X",
                    "-w",
                    *connection,
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-c",
                    "SELECT count(*) FROM device_platform.users;",
                    env=owner_env,
                )
            finally:
                if started:
                    run("pg_ctl", "-D", str(data), "-m", "immediate", "-w", "stop")


if __name__ == "__main__":
    unittest.main()
