"""Check schema alignment, or back up, migrate and grant access to a stopped database.

Run with the API virtual environment. No database credentials are printed or passed
on command lines. The default is read-only; --apply changes the configured database.
"""

import argparse
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.engine import make_url
from training_contracts.privacy import private_directory

from pms_api.cli import migration_config
from pms_api.core.config import Settings
from pms_api.database import speech  # noqa: F401
from pms_api.database.models import Base
from pms_api.database.session import REVISION

ROOT = Path(__file__).resolve().parents[2]


def verify(connection, roles):
    if connection.execute("SELECT version_num FROM public.alembic_version").fetchall() != [(REVISION,)]:
        raise RuntimeError("Database migration revision does not match the application")
    rows = connection.execute(
        "SELECT t.relname,a.attname,format_type(a.atttypid,a.atttypmod),NOT a.attnotnull "
        "FROM pg_class t JOIN pg_namespace n ON n.oid=t.relnamespace "
        "JOIN pg_attribute a ON a.attrelid=t.oid WHERE n.nspname='device_platform' "
        "AND t.relkind IN ('r','p') AND a.attnum>0 AND NOT a.attisdropped"
    ).fetchall()
    expected = {
        (table.name, column.name): (
            str(column.type.compile(dialect=dialect())).lower().replace(", ", ","),
            column.nullable,
        )
        for table in Base.metadata.tables.values()
        if not table.info.get("compatibility_view")
        for column in table.columns
    }
    if {(table, column): (kind, nullable) for table, column, kind, nullable in rows} != expected:
        raise RuntimeError("Database columns/types/nullability do not match the ORM")
    keys = connection.execute(
        "SELECT t.relname,array_agg(a.attname ORDER BY k.position) "
        "FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid "
        "JOIN pg_namespace n ON n.oid=t.relnamespace "
        "CROSS JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS k(attribute,position) "
        "JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=k.attribute "
        "WHERE n.nspname='device_platform' AND c.contype='p' GROUP BY t.relname"
    ).fetchall()
    if dict(keys) != {
        table.name: [column.name for column in table.primary_key.columns]
        for table in Base.metadata.tables.values()
        if not table.info.get("compatibility_view")
    }:
        raise RuntimeError("Database primary keys do not match the ORM")
    for table in Base.metadata.tables.values():
        actual = connection.execute(
            "SELECT relkind FROM pg_class WHERE oid=to_regclass(%s)", (str(table),)
        ).fetchone()
        if actual != ("v" if table.info.get("compatibility_view") else "r",):
            raise RuntimeError("Database table/view kind does not match the ORM")
        if not connection.execute(
            "SELECT has_table_privilege(%s,%s,'SELECT')", (roles[0], str(table))
        ).fetchone()[0]:
            raise RuntimeError("API runtime grants are incomplete")
    for index, role in enumerate(roles):
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            granted = connection.execute(
                "SELECT has_table_privilege(%s,'device_platform.device_identities',%s)",
                (role, privilege),
            ).fetchone()[0]
            if granted != (index == 0 and privilege in {"SELECT", "INSERT"}):
                raise RuntimeError("Device identity grants must be API-only read/insert")
    for table in ("llm_connections", "provider_connections", "processing_profiles"):
        if connection.execute(
            "SELECT has_table_privilege(%s,%s,'INSERT,UPDATE,DELETE')",
            (roles[0], "device_platform." + table),
        ).fetchone()[0]:
            raise RuntimeError("Historical configuration still has API write grants")
    for table in (
        "patient_practice_selections",
        "patient_conversations",
        "llm_requests",
        "local_turns",
        "local_conversation_turns",
    ):
        constraints = connection.execute(
            "SELECT conname FROM pg_constraint WHERE conrelid=to_regclass(%s) AND convalidated "
            "AND conname IN (%s,%s)",
            ("device_platform." + table, table + "_owner", table + "_device_fk"),
        ).fetchall()
        if len(constraints) != 2:
            raise RuntimeError("Device Practice ownership constraints are incomplete")
        for index, role in enumerate(roles):
            allowed = (
                {"SELECT", "INSERT"}
                | ({"UPDATE"} if table not in {"local_turns", "local_conversation_turns"} else set())
                if index == 0
                else {"SELECT", "DELETE"}
                if index == 2 and table != "patient_practice_selections"
                else set()
            )
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                granted = connection.execute(
                    "SELECT has_table_privilege(%s,%s,%s)",
                    (role, "device_platform." + table, privilege),
                ).fetchone()[0]
                if granted != (privilege in allowed):
                    raise RuntimeError("Device Practice runtime grants are inconsistent")
    for table in ("device_session_queues", "practice_sessions", "session_archives", "session_archive_items"):
        for index, role in enumerate(roles):
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                expected_grant = index == 0 and (
                    privilege != "DELETE" or table in {"session_archives", "session_archive_items"}
                )
                granted = connection.execute(
                    "SELECT has_table_privilege(%s,%s,%s)",
                    (role, "device_platform." + table, privilege),
                ).fetchone()[0]
                if granted != expected_grant:
                    raise RuntimeError("Session queue/archive runtime grants are inconsistent")
    for table, trigger in (
        ("practice_sessions", "practice_session_guard"),
        ("patient_conversations", "conversation_assignment_guard"),
        ("session_archives", "session_archive_guard"),
        ("session_archive_items", "session_archive_item_guard"),
    ):
        if connection.execute(
            "SELECT tgenabled FROM pg_trigger WHERE tgrelid=to_regclass(%s) AND tgname=%s AND NOT tgisinternal",
            ("device_platform." + table, trigger),
        ).fetchone() != ("O",):
            raise RuntimeError("Session lifecycle guards are missing or disabled")
    for table in ("runtime_models", "device_model_selections"):
        if not connection.execute(
            "SELECT has_table_privilege(%s,%s,'SELECT')", (roles[1], "device_platform." + table)
        ).fetchone()[0]:
            raise RuntimeError("Worker model read grants are incomplete")
        for privilege in ("SELECT", "INSERT", "UPDATE"):
            if not connection.execute(
                "SELECT has_table_privilege(%s,%s,%s)",
                (roles[0], "device_platform." + table, privilege),
            ).fetchone()[0]:
                raise RuntimeError("Model management grants are incomplete")
        if connection.execute(
            "SELECT has_table_privilege(%s,%s,'SELECT')", (roles[2], "device_platform." + table)
        ).fetchone()[0]:
            raise RuntimeError("Retention must not access model configuration")
    if not connection.execute(
        "SELECT relrowsecurity FROM pg_class WHERE oid='device_platform.runtime_models'::regclass"
    ).fetchone()[0]:
        raise RuntimeError("Model credential row security is disabled")
    if not connection.execute(
        "SELECT has_column_privilege(%s,'device_platform.runtime_models','last_used_at','UPDATE')",
        (roles[1],),
    ).fetchone()[0]:
        raise RuntimeError("Worker model last-use grant is missing")


def pg_tool(name):
    found = shutil.which(name)
    candidate = Path("C:/Program Files/PostgreSQL/17/bin") / (name + ".exe")
    if found:
        return found
    if os.name == "nt" and candidate.is_file():
        return str(candidate)
    raise RuntimeError("Install PostgreSQL client tools on PATH")


def run_tool(name, arguments, env):
    result = subprocess.run([pg_tool(name), *arguments], env=env, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f"{name} failed; synchronization stopped (private tool output withheld)")


def sync(apply=False):
    os.chdir(ROOT / "platform/api")
    settings = Settings()
    if not settings.migration_database_url:
        raise RuntimeError("Configure PMS_MIGRATION_DATABASE_URL for the database owner")
    owner = make_url(settings.migration_database_url.get_secret_value())
    runtime = [
        make_url(value.get_secret_value())
        for value in (settings.database_url, settings.worker_database_url, settings.retention_database_url)
        if value
    ]
    if len(runtime) != 3 or any(
        (url.host, url.port or 5432, url.database) != (owner.host, owner.port or 5432, owner.database)
        for url in runtime
    ):
        raise RuntimeError("All three runtime roles must target the same database as the migration owner")
    roles = [url.username for url in runtime]
    if len(set(roles)) != 3 or owner.username in roles or not all(roles):
        raise RuntimeError("Use three distinct runtime roles and a separate migration owner")
    if ScriptDirectory.from_config(migration_config()).get_heads() != [REVISION]:
        raise RuntimeError("Migration scripts and API readiness disagree")
    dsn = owner.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as connection:
        if apply:
            connection.execute("SELECT pg_advisory_lock(hashtext('pms_database_sync'))")
            if connection.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
                "AND pid<>pg_backend_pid()"
            ).fetchone()[0]:
                raise RuntimeError("Stop services using this database before --apply")
            env = {
                **os.environ,
                "PGHOST": owner.host or "127.0.0.1",
                "PGPORT": str(owner.port or 5432),
                "PGDATABASE": owner.database or "",
                "PGUSER": owner.username or "",
                "PGPASSWORD": owner.password or "",
            }
            for key, value in owner.query.items():
                if key in {"sslmode", "sslrootcert", "sslcert", "sslkey", "options"}:
                    env["PG" + key.upper()] = str(value)
            backups = ROOT / ".local/db-backups"
            backups.mkdir(mode=0o700, parents=True, exist_ok=True)
            private_directory(backups)
            backup = backups / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".dump")
            run_tool("pg_dump", ["-Fc", "--file", str(backup)], env)
            run_tool("pg_restore", ["--list", str(backup)], env)
            print("Backup created: " + str(backup))
            command.upgrade(migration_config(), "head")
            run_tool(
                "psql",
                [
                    "-X",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-v",
                    "db_name=" + str(owner.database),
                    "-v",
                    "api_role=" + str(roles[0]),
                    "-v",
                    "worker_role=" + str(roles[1]),
                    "-v",
                    "maintenance_role=" + str(roles[2]),
                    "-f",
                    str(ROOT / "platform/api/deploy/grant-runtime-access.sql"),
                ],
                env,
            )
        with connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")
            verify(connection, roles)
    print(f"Verified {REVISION}: database, ORM, migration scripts and runtime grants agree.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Back up and upgrade the stopped configured database"
    )
    try:
        sync(parser.parse_args().apply)
    except Exception as error:
        print(
            str(error) if isinstance(error, RuntimeError) else "Database sync failed: " + type(error).__name__
        )
        raise SystemExit(1) from None
