"""Real isolated PostgreSQL category/init coverage; never uses an application database."""

import concurrent.futures
import os
import sys
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from psycopg import sql
from pydantic import SecretStr
from sqlalchemy.engine import make_url

from pms_api.cli import admin, migration_config
from pms_api.core.config import Settings, get_settings
from pms_api.database.initialization import initialize_database
from pms_api.database.session import REVISION

CODES = ["cardiology", "nephrology", "respiratory_medicine"]


def test_seeded_categories_constraints_and_runtime_grants(platform):
    p = platform
    rows = p.sql(
        "SELECT code,name,names->>'hi',is_active,sort_order FROM device_platform.scenario_categories ORDER BY sort_order"
    )
    assert [row[0] for row in rows] == CODES
    assert [row[1] for row in rows] == ["Cardiology", "Nephrology", "Respiratory Medicine"]
    assert [row[2] for row in rows] == ["हृदय रोग", "गुर्दा रोग", "श्वसन रोग"]
    assert all(row[3] for row in rows)
    assert p.sql(
        "SELECT count(*) FROM device_platform.activity_events WHERE event_type='platform.scenario_category.seeded'"
    ) == [(3,)]
    assert p.sql(
        "SELECT count(*) FROM device_platform.activity_events WHERE event_type='platform.scenario_category.seeded' AND organization_id IS NULL AND actor_type='system'"
    ) == [(3,)]
    roles = [
        make_url(value.get_secret_value()).username
        for value in (
            p.settings.database_url,
            p.settings.worker_database_url,
            p.settings.retention_database_url,
        )
    ]
    for role in roles:
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"):
            allowed = p.sql(
                "SELECT has_table_privilege(%s,'device_platform.scenario_categories',%s)", (role, privilege)
            )[0][0]
            assert allowed == (role == roles[0] and privilege == "SELECT")
    assert p.sql(
        "SELECT count(*) FROM information_schema.table_privileges WHERE table_schema='device_platform' AND table_name='scenario_categories' AND grantee='PUBLIC'"
    ) == [(0,)]
    for clause in (
        "code='Bad Code'",
        "name=' '",
        'names=\'{"hi":""}\'',
        "description=''",
        "sort_order=-1",
        "code='other'",
        "id=gen_random_uuid()",
        "created_at=now()+interval '1 day'",
    ):
        with pytest.raises(psycopg.errors.CheckViolation):
            p.sql("UPDATE device_platform.scenario_categories SET " + clause + " WHERE code='cardiology'")
    with pytest.raises(psycopg.errors.UniqueViolation):
        p.sql("UPDATE device_platform.scenario_categories SET name='cardiology' WHERE code='nephrology'")
    p.sql(
        "UPDATE device_platform.scenario_categories SET name='Cardiac interviews',is_active=false WHERE code='cardiology'"
    )
    assert p.sql(
        "SELECT is_active,updated_at>=created_at FROM device_platform.scenario_categories WHERE code='cardiology'"
    ) == [(False, True)]
    assert p.client.get("/health/ready").status_code == 200


@pytest.fixture
def empty_database_target(monkeypatch):
    admin_dsn = os.environ.get("PMS_TEST_ADMIN_DSN")
    if not admin_dsn:
        pytest.skip("Set PMS_TEST_ADMIN_DSN to a dedicated disposable PostgreSQL server")
    name = "pms_test_categories_" + uuid4().hex[:12]
    url = make_url(admin_dsn).set(drivername="postgresql+psycopg", database=name)
    raw = url.render_as_string(hide_password=False)
    for key, value in {
        "PMS_DATABASE_URL": raw,
        "PMS_MIGRATION_DATABASE_URL": raw,
        "PMS_TOKEN_PEPPER": "p" * 40,
        "PMS_MEDIA_SIGNING_KEY": "m" * 40,
    }.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    settings = Settings(_env_file=None)
    try:
        yield settings, url.set(drivername="postgresql").render_as_string(hide_password=False), name
    finally:
        get_settings.cache_clear()
        with psycopg.connect(admin_dsn, autocommit=True) as connection:
            # Only the uniquely named test database allocated above can be removed.
            connection.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )


def test_initialization_creates_then_upgrades_and_preserves_customized_records(empty_database_target):
    settings, dsn, name = empty_database_target
    assert initialize_database(settings, lambda: command.upgrade(migration_config(), "0010_llm_providers"))
    with psycopg.connect(dsn) as connection:
        connection.execute("CREATE TABLE public.preserved_fixture(value text NOT NULL)")
        connection.execute("INSERT INTO public.preserved_fixture VALUES ('existing data')")
        assert connection.execute("SELECT to_regclass('device_platform.scenario_categories')").fetchone() == (
            None,
        )
        connection.execute(
            "ALTER TABLE device_platform.activity_events ADD CONSTRAINT reject_category_seed_fixture CHECK (event_type <> 'platform.scenario_category.seeded')"
        )
    # A failed audit insert must roll back the categories, schema and revision too.
    with pytest.raises(psycopg.errors.CheckViolation):
        initialize_database(settings, lambda: command.upgrade(migration_config(), "head"))
    with psycopg.connect(dsn) as connection:
        assert connection.execute("SELECT to_regclass('device_platform.scenario_categories')").fetchone() == (
            None,
        )
        assert connection.execute("SELECT version_num FROM public.alembic_version").fetchone() == (
            "0010_llm_providers",
        )
        connection.execute(
            "ALTER TABLE device_platform.activity_events DROP CONSTRAINT reject_category_seed_fixture"
        )
    assert not initialize_database(settings, lambda: command.upgrade(migration_config(), "head"))
    with psycopg.connect(dsn) as connection:
        assert connection.execute("SELECT value FROM public.preserved_fixture").fetchone() == (
            "existing data",
        )
        assert connection.execute("SELECT version_num FROM public.alembic_version").fetchone() == (REVISION,)
        before = connection.execute(
            "SELECT id,code,created_at FROM device_platform.scenario_categories ORDER BY code"
        ).fetchall()
        connection.execute(
            "UPDATE device_platform.scenario_categories SET name='Locally reviewed name',is_active=false WHERE code='cardiology'"
        )
        assert connection.execute(
            "SELECT count(*) FROM pg_database d,LATERAL aclexplode(coalesce(d.datacl,acldefault('d',d.datdba))) a WHERE d.datname=%s AND a.grantee=0",
            (name,),
        ).fetchone() == (0,)
    assert not initialize_database(settings, lambda: command.upgrade(migration_config(), "head"))
    with psycopg.connect(dsn) as connection:
        assert (
            connection.execute(
                "SELECT id,code,created_at FROM device_platform.scenario_categories ORDER BY code"
            ).fetchall()
            == before
        )
        assert connection.execute(
            "SELECT name,is_active FROM device_platform.scenario_categories WHERE code='cardiology'"
        ).fetchone() == ("Locally reviewed name", False)
        assert connection.execute(
            "SELECT count(*) FROM device_platform.activity_events WHERE event_type='platform.scenario_category.seeded'"
        ).fetchone() == (3,)


def test_concurrent_initializers_create_and_seed_once(empty_database_target):
    settings, dsn, _ = empty_database_target

    def initialize():
        return initialize_database(settings, lambda: command.upgrade(migration_config(), "head"))

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: initialize(), range(2)))
    assert sorted(outcomes) == [False, True]
    with psycopg.connect(dsn) as connection:
        assert connection.execute("SELECT count(*) FROM device_platform.scenario_categories").fetchone() == (
            3,
        )
        assert connection.execute("SELECT count(*) FROM device_platform.patient_identities").fetchone() == (
            1,
        )
        assert connection.execute(
            "SELECT count(*) FROM device_platform.activity_events WHERE event_type='platform.patient_identity.seeded'"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM device_platform.activity_events WHERE event_type='platform.scenario_category.seeded'"
        ).fetchone() == (3,)


def test_initialization_refuses_unmanaged_schema_without_modifying_it(empty_database_target):
    settings, dsn, _ = empty_database_target
    assert initialize_database(settings, lambda: None)
    with psycopg.connect(dsn) as connection:
        connection.execute("CREATE SCHEMA device_platform")
        connection.execute("CREATE TABLE device_platform.sentinel(value integer)")
        connection.execute("INSERT INTO device_platform.sentinel VALUES (42)")
    with pytest.raises(ValueError, match="adopt-baseline"):
        initialize_database(settings, lambda: pytest.fail("Must not migrate unmanaged schema"))
    with psycopg.connect(dsn) as connection:
        assert connection.execute("SELECT value FROM device_platform.sentinel").fetchone() == (42,)
        assert connection.execute("SELECT to_regclass('public.alembic_version')").fetchone() == (None,)


@pytest.mark.parametrize("error_type", [ValueError, RuntimeError])
def test_initializer_cli_never_echoes_credentials(monkeypatch, capsys, error_type):
    secret = "private-password-must-not-appear"
    monkeypatch.setattr(sys, "argv", ["pms-admin", "init-database"])
    monkeypatch.setattr("pms_api.cli.Settings", lambda: (_ for _ in ()).throw(error_type(secret)))
    with pytest.raises(SystemExit) as error:
        admin()
    assert error.value.code == 1 and secret not in capsys.readouterr().err


@pytest.mark.parametrize("target", ["postgres", "template0", "template1", "", "x" * 64])
def test_init_rejects_maintenance_or_invalid_target_before_connecting(target):
    settings = Settings(
        _env_file=None,
        token_pepper="p" * 40,
        media_signing_key="m" * 40,
        migration_database_url=SecretStr("postgresql+psycopg://owner@127.0.0.1/" + target),
    )
    with pytest.raises(ValueError, match="dedicated"):
        initialize_database(settings, lambda: pytest.fail("Unexpected migration"))
