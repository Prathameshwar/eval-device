"""Keep deployed migration scripts, readiness and ORM mappings on one schema contract."""

import importlib.util
from importlib.resources import files
from pathlib import Path

import psycopg
from alembic.script import ScriptDirectory
from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.engine import make_url

from pms_api.cli import migration_config
from pms_api.database import speech  # noqa: F401 -- register every ORM table independently of API imports
from pms_api.database.models import Base
from pms_api.database.session import REVISION


def sync_script():
    path = Path(__file__).resolve().parents[2] / "db/sync.py"
    spec = importlib.util.spec_from_file_location("database_sync_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sync_script_verifies_current_schema_and_rejects_historical_writes(platform):
    import pytest

    module = sync_script()
    roles = [
        make_url(value.get_secret_value()).username
        for value in (
            platform.settings.database_url,
            platform.settings.worker_database_url,
            platform.settings.retention_database_url,
        )
    ]
    with psycopg.connect(platform.dsn) as connection:
        module.verify(connection, roles)
        connection.execute(
            psycopg.sql.SQL("GRANT UPDATE ON device_platform.processing_profiles TO {}").format(
                psycopg.sql.Identifier(roles[0])
            )
        )
        with pytest.raises(RuntimeError, match="Historical configuration"):
            module.verify(connection, roles)
        connection.rollback()
        connection.execute(
            psycopg.sql.SQL("GRANT SELECT ON device_platform.patient_conversations TO {}").format(
                psycopg.sql.Identifier(roles[1])
            )
        )
        with pytest.raises(RuntimeError, match="Device Practice runtime grants"):
            module.verify(connection, roles)
        connection.rollback()
        for table in (
            "device_session_queues",
            "practice_sessions",
            "session_archives",
            "session_archive_items",
        ):
            connection.execute(
                psycopg.sql.SQL("GRANT SELECT ON device_platform.{} TO {}").format(
                    psycopg.sql.Identifier(table), psycopg.sql.Identifier(roles[1])
                )
            )
            with pytest.raises(RuntimeError, match="Session queue/archive runtime grants"):
                module.verify(connection, roles)
            connection.rollback()
        connection.execute(
            "ALTER TABLE device_platform.session_archives DISABLE TRIGGER session_archive_guard"
        )
        with pytest.raises(RuntimeError, match="Session lifecycle guards"):
            module.verify(connection, roles)
        connection.rollback()


def test_sync_apply_refuses_connected_services_before_backup(platform, monkeypatch):
    import pytest

    module = sync_script()
    monkeypatch.setattr(module, "Settings", lambda: platform.settings)
    calls = []
    monkeypatch.setattr(module, "run_tool", lambda *args: calls.append(args))
    with psycopg.connect(platform.dsn):
        with pytest.raises(RuntimeError, match="Stop services"):
            module.sync(apply=True)
    assert calls == []


def test_readiness_requires_the_single_migration_head():
    scripts = ScriptDirectory.from_config(migration_config())
    assert scripts.get_heads() == [REVISION]


def test_deployment_backfill_accepts_current_head(platform):
    from sqlalchemy import create_engine

    from pms_api.database.tenant_catalog_backfill import _check_owner_and_head

    engine = create_engine(make_url(platform.dsn).set(drivername="postgresql+psycopg"))
    try:
        with engine.connect() as connection:
            _check_owner_and_head(connection)
    finally:
        engine.dispose()


def test_packaged_baseline_matches_frozen_install_scripts():
    source = Path(__file__).resolve().parents[2] / "db/sql"
    packaged = files("pms_api.database.baseline")
    names = {p.name for p in source.glob("*.sql")}
    assert names == {p.name for p in packaged.iterdir() if p.name.endswith(".sql")}
    for name in names:
        assert (source / name).read_text(encoding="utf-8-sig") == packaged.joinpath(name).read_text(
            encoding="utf-8-sig"
        ), name


def test_fresh_database_matches_all_orm_columns_and_keys_with_runtime_access(platform):
    url = make_url(platform.settings.database_url.get_secret_value()).set(drivername="postgresql")
    with psycopg.connect(url.render_as_string(hide_password=False)) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        assert connection.execute("SELECT version_num FROM public.alembic_version").fetchall() == [
            (REVISION,)
        ]
        rows = connection.execute(
            "SELECT t.relname,a.attname,format_type(a.atttypid,a.atttypmod),NOT a.attnotnull "
            "FROM pg_class t JOIN pg_namespace n ON n.oid=t.relnamespace "
            "JOIN pg_attribute a ON a.attrelid=t.oid "
            "WHERE n.nspname='device_platform' AND t.relkind IN ('r','p') "
            "AND a.attnum>0 AND NOT a.attisdropped"
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
        assert {(table, column): (kind, nullable) for table, column, kind, nullable in rows} == expected
        keys = connection.execute(
            "SELECT t.relname,array_agg(a.attname ORDER BY k.position) "
            "FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid "
            "JOIN pg_namespace n ON n.oid=t.relnamespace "
            "CROSS JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS k(attribute,position) "
            "JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=k.attribute "
            "WHERE n.nspname='device_platform' AND c.contype='p' GROUP BY t.relname"
        ).fetchall()
        assert dict(keys) == {
            table.name: [column.name for column in table.primary_key.columns]
            for table in Base.metadata.tables.values()
            if not table.info.get("compatibility_view")
        }
        for table in Base.metadata.tables.values():
            assert connection.execute(
                "SELECT has_table_privilege(current_user,%s,'SELECT')", (str(table),)
            ).fetchone() == (True,), table.name
    assert platform.client.get("/health/ready").status_code == 200


def test_platform_model_migration_limits_credentials_and_updates_role_view(platform):
    assert platform.sql(
        "SELECT count(*) FROM device_platform.model_definitions "
        "WHERE provider='local_llama_cpp' AND adapter_status='available'"
    ) == [(4,)]
    assert platform.sql(
        "SELECT count(*) FROM device_platform.default_role_permissions "
        "WHERE role_code='org_admin' AND permission IN "
        "('org.connections.manage','org.profiles.manage')"
    ) == [(0,)]
    roles = [
        platform.settings.database_url,
        platform.settings.worker_database_url,
        platform.settings.retention_database_url,
    ]
    for index, value in enumerate(roles):
        role = make_url(value.get_secret_value()).username
        assert platform.sql(
            "SELECT has_table_privilege(%s,%s,'SELECT')", (role, "device_platform.platform_model_connections")
        ) == [(index == 0,)]


def test_scenario_default_grants_and_inventory_match_published_practice(platform):
    h = platform
    token, _ = h.user("schema-practice-user")
    org = h.organization(token)["id"]
    base = f"/organizations/{org}/patient-practice"
    options = h.call("GET", base + "/scenario-options", token)
    scenario = next(row for row in options["items"] if row["id"] == options["default"]["scenario_id"])
    h.call(
        "PUT",
        base + "/scenario-selection",
        token,
        json={
            "expected_revision": 0,
            "scenario_id": scenario["id"],
            "language": "en",
            "vitals": scenario["vitals"],
        },
    )
    for index, value in enumerate(
        (
            h.settings.database_url,
            h.settings.worker_database_url,
            h.settings.retention_database_url,
        )
    ):
        role = make_url(value.get_secret_value()).username
        for privilege in ("SELECT", "INSERT", "UPDATE"):
            assert h.sql(
                "SELECT has_table_privilege(%s,%s,%s)",
                (role, "device_platform.tenant_scenario_defaults", privilege),
            ) == [(index == 0,)]
        assert h.sql(
            "SELECT has_table_privilege(%s,%s,'DELETE')",
            (role, "device_platform.tenant_scenario_defaults"),
        ) == [(False,)]
    source = Path(__file__).resolve().parents[1] / "deploy/tenant-clinical-inventory.sql"
    with psycopg.connect(h.dsn) as connection:
        cursor = connection.execute(source.read_text(encoding="utf-8"))
        found = False
        while True:
            names = [column.name for column in cursor.description or []]
            if "published_scenario_selections" in names:
                counts = dict(zip(names, cursor.fetchone(), strict=True))
                assert counts["practice_selections"] == counts["published_scenario_selections"] == 1
                assert counts["mapped_tenant_selections"] == counts["unmapped_legacy_selections"] == 0
                found = True
            if not cursor.nextset():
                break
        assert found


def test_language_validators_are_explicitly_api_only(platform):
    values = (
        platform.settings.database_url,
        platform.settings.worker_database_url,
        platform.settings.retention_database_url,
    )
    for index, value in enumerate(values):
        role = make_url(value.get_secret_value()).username
        for signature in ("valid_language_map(jsonb,integer)", "valid_language_list(text[],text)"):
            assert platform.sql(
                "SELECT has_function_privilege(%s,%s,'EXECUTE')", (role, "device_platform." + signature)
            ) == [(index == 0,)]
    url = make_url(values[0].get_secret_value()).set(drivername="postgresql")
    with psycopg.connect(url.render_as_string(hide_password=False)) as connection:
        assert connection.execute(
            "SELECT device_platform.valid_language_map(%s::jsonb,120), "
            "device_platform.valid_language_list(ARRAY['en','hi'],'en')",
            ('{"en":"Patient"}',),
        ).fetchone() == (True, True)


def test_readiness_rejects_missing_old_or_multiple_database_heads(platform):
    for revisions in ([REVISION, "unexpected_branch"], [], ["0027_catalog_management"], [REVISION]):
        platform.sql("DELETE FROM public.alembic_version")
        for revision in revisions:
            platform.sql("INSERT INTO public.alembic_version(version_num) VALUES(%s)", (revision,))
        response = platform.client.get("/health/ready")
        assert response.status_code == (200 if revisions == [REVISION] else 503)
        if response.status_code == 503:
            assert response.json()["reason"] == "schema_mismatch"
