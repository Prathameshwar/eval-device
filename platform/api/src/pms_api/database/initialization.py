"""Trusted owner-only initialization, preserving existing databases and data."""

from collections.abc import Callable

from psycopg import sql
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from pms_api.core.config import Settings


def initialize_database(
    settings: Settings, migrate: Callable[[], None], maintenance_database: str = "postgres"
) -> bool:
    if settings.migration_database_url is None:
        raise ValueError("Set PMS_MIGRATION_DATABASE_URL to a deployment-owner connection for initialization")
    url = make_url(settings.migration_database_url.get_secret_value())
    target = url.database
    if url.drivername != "postgresql+psycopg":
        raise ValueError("Initialization requires a postgresql+psycopg owner URL")
    if (
        not target
        or len(target.encode("utf-8")) > 63
        or "\x00" in target
        or target in {"postgres", "template0", "template1"}
    ):
        raise ValueError("Choose a dedicated application database in PMS_MIGRATION_DATABASE_URL")
    if (
        not maintenance_database
        or len(maintenance_database.encode("utf-8")) > 63
        or "\x00" in maintenance_database
        or maintenance_database == target
    ):
        raise ValueError("Use a separate PostgreSQL maintenance database")
    options = url.query.get("options", "")
    if not isinstance(options, str):
        raise ValueError("Configure a single PostgreSQL options value")
    options = (options + " -c lock_timeout=15000").strip()
    engine = create_engine(
        url.set(database=maintenance_database),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
        connect_args={"connect_timeout": 5, "options": options},
    )
    created = False
    try:
        with engine.connect() as connection:
            driver = connection.connection.driver_connection
            assert driver is not None
            # Keep one connection/lock across CREATE DATABASE and the complete upgrade.
            # Concurrent invocations of this initializer cannot race or duplicate seeds.
            driver.execute("SELECT pg_advisory_lock(hashtext('pms_database_init'),hashtext(%s))", (target,))
            try:
                exists = driver.execute("SELECT 1 FROM pg_database WHERE datname=%s", (target,)).fetchone()
                if not exists:
                    driver.execute(
                        sql.SQL(
                            "CREATE DATABASE {} TEMPLATE template0 ENCODING 'UTF8' ALLOW_CONNECTIONS=false"
                        ).format(sql.Identifier(target))
                    )
                    created = True
                    driver.execute(
                        sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(target))
                    )
                    driver.execute(
                        sql.SQL("ALTER DATABASE {} SET timezone TO 'UTC'").format(sql.Identifier(target))
                    )
                    # Publish access only after privileges and UTC are configured.
                    driver.execute(
                        sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS=true").format(sql.Identifier(target))
                    )
                target_engine = create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": 5})
                try:
                    with target_engine.connect() as target_connection:
                        raw = target_connection.connection.driver_connection
                        assert raw is not None
                        state = raw.execute(
                            "SELECT to_regnamespace('device_platform'),to_regclass('public.alembic_version')"
                        ).fetchone()
                        if state and state[0] and not state[1]:
                            raise ValueError(
                                "Existing unmanaged schema: run pms-admin adopt-baseline before initialization"
                            )
                finally:
                    target_engine.dispose()
                migrate()
            finally:
                driver.execute(
                    "SELECT pg_advisory_unlock(hashtext('pms_database_init'),hashtext(%s))", (target,)
                )
    finally:
        engine.dispose()
    return created
