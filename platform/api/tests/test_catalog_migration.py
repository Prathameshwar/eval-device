"""Tenant catalog expansion and legacy rehearsal backfill on disposable PostgreSQL."""

import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from alembic import command
from psycopg import sql
from sqlalchemy.engine import make_url
from test_scenario_categories import empty_database_target as empty_database_target

from pms_api.cli import migration_config
from pms_api.database.initialization import initialize_database
from pms_api.database.session import REVISION
from pms_api.database.tenant_catalog_backfill import backfill


def legacy_setup(p, organization_id):
    """Build a pre-cutover global selection without using the retired API routes."""
    user_id = p.sql(
        "SELECT user_id FROM device_platform.organization_memberships "
        "WHERE organization_id=%s AND role='org_admin' AND invitation_status='accepted' LIMIT 1",
        (organization_id,),
    )[0][0]
    selection_id = uuid4()
    template_id = p.sql(
        "INSERT INTO device_platform.patient_practice_selections "
        "(id,organization_id,user_id,template_id,category_id,patient_identity_id,"
        "template_revision,document,language) "
        "SELECT %s,%s,%s,id,category_id,patient_identity_id,revision,document,'en' "
        "FROM device_platform.patient_case_templates ORDER BY code LIMIT 1 RETURNING template_id",
        (selection_id, organization_id, user_id),
    )[0][0]
    return {"template_id": template_id, "selection_id": selection_id}


def test_seeded_global_catalog_survives_forward_upgrade_and_version_rules(empty_database_target):
    settings, dsn, _ = empty_database_target
    initialize_database(settings, lambda: command.upgrade(migration_config(), "0026_member_imports"))
    tables = ("scenario_categories", "patient_identities", "patient_case_templates")
    with psycopg.connect(dsn) as connection:
        before = {
            table: connection.execute(
                sql.SQL("SELECT to_jsonb(t) FROM device_platform.{} t ORDER BY id").format(
                    sql.Identifier(table)
                )
            ).fetchall()
            for table in tables
        }
    command.upgrade(migration_config(), "head")
    command.upgrade(migration_config(), "head")
    with psycopg.connect(dsn) as connection:
        for table in tables:
            assert (
                connection.execute(
                    sql.SQL(
                        "SELECT to_jsonb(t) - 'management_version' FROM device_platform.{} t ORDER BY id"
                    ).format(sql.Identifier(table))
                ).fetchall()
                == before[table]
            )
        identifier = before["scenario_categories"][0][0]["id"]
        assert connection.execute(
            "UPDATE device_platform.scenario_categories SET description=description "
            "WHERE id=%s RETURNING management_version",
            (identifier,),
        ).fetchone() == (2,)
        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute(
                "UPDATE device_platform.scenario_categories SET management_version=9 WHERE id=%s",
                (identifier,),
            )


def test_legacy_selections_copy_per_tenant_without_snapshot_or_revision_changes(platform):
    p = platform
    token, _ = p.user("tenant-catalog-author")
    first = p.organization(token)["id"]
    second = p.organization(token, "Second hospital")["id"]
    legacy_setup(p, first)
    legacy_setup(p, second)
    active_specialties_before = p.sql(
        "SELECT count(*) FROM device_platform.organization_clinical_specialties WHERE is_active"
    )
    before = p.sql(
        "SELECT id,organization_id,revision,md5(document::text),template_id,category_id,"
        "patient_identity_id FROM device_platform.patient_practice_selections ORDER BY id"
    )

    dry = backfill(p.settings, apply=False, after=None, limit=25)
    assert {str(row.organization_id) for row in dry} == {first, second}
    assert all(row.selections == 1 and row.mapped_selections == 0 for row in dry)
    assert p.sql("SELECT count(*) FROM device_platform.organization_case_templates") == [(4,)]

    first_batch = backfill(p.settings, apply=True, after=None, limit=1)
    second_batch = backfill(p.settings, apply=True, after=first_batch[0].organization_id, limit=1)
    applied = first_batch + second_batch
    assert len(applied) == 2
    assert all(row.cases == 3 and row.profiles == 1 and row.specialties == 3 for row in applied)
    assert all(row.mapped_selections == 1 for row in applied)
    assert (
        p.sql(
            "SELECT id,organization_id,revision,md5(document::text),template_id,category_id,"
            "patient_identity_id FROM device_platform.patient_practice_selections ORDER BY id"
        )
        == before
    )
    cases = p.sql(
        "SELECT organization_id,id,source_global_id,is_active,revision "
        "FROM device_platform.organization_case_templates "
        "WHERE source_global_id=(SELECT id FROM device_platform.patient_case_templates ORDER BY code LIMIT 1) "
        "ORDER BY organization_id"
    )
    assert len(cases) == 2 and cases[0][1] != cases[1][1]
    assert cases[0][2] == cases[1][2] and all(not row[3] and row[4] == 1 for row in cases)
    assert (
        p.sql("SELECT count(*) FROM device_platform.organization_clinical_specialties WHERE is_active")
        == active_specialties_before
    )
    assert p.sql("SELECT count(*) FROM device_platform.organization_patient_profiles WHERE is_active") == [
        (0,)
    ]
    code = p.sql(
        "SELECT code FROM device_platform.organization_clinical_specialties WHERE organization_id=%s",
        (first,),
    )[0][0]
    with pytest.raises(psycopg.errors.UniqueViolation):
        p.sql(
            "INSERT INTO device_platform.organization_clinical_specialties "
            "(organization_id,code,name,names,description) "
            "VALUES (%s,%s,'Duplicate','{\"en\":\"Duplicate\"}'::jsonb,'Duplicate specialty')",
            (first, code),
        )
    assert p.sql(
        "SELECT count(*) FROM device_platform.activity_events "
        "WHERE event_type='tenant.catalog.legacy_backfilled'"
    ) == [(2,)]
    roles = (
        make_url(p.settings.database_url.get_secret_value()).username,
        make_url(p.settings.worker_database_url.get_secret_value()).username,
        make_url(p.settings.retention_database_url.get_secret_value()).username,
    )
    for table in (
        "organization_clinical_specialties",
        "organization_patient_profiles",
        "organization_case_templates",
    ):
        for role, allowed in zip(roles, (True, False, False), strict=True):
            assert p.sql(
                "SELECT has_table_privilege(%s,%s,'SELECT')",
                (role, "device_platform." + table),
            ) == [(allowed,)]

    assert backfill(p.settings, apply=True, after=None, limit=25) == applied
    assert p.sql("SELECT count(*) FROM device_platform.organization_case_templates") == [(6,)]
    assert p.sql(
        "SELECT count(*) FROM device_platform.activity_events "
        "WHERE event_type='tenant.catalog.legacy_backfilled'"
    ) == [(2,)]

    # A foreign tenant's case ID cannot be attached to the selection even by direct SQL.
    foreign_case = next(row for row in cases if str(row[0]) == second)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        p.sql(
            "UPDATE device_platform.patient_practice_selections SET tenant_template_id=%s,"
            "revision=revision+1 WHERE organization_id=%s",
            (foreign_case[1], UUID(first)),
        )
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        p.sql(
            "INSERT INTO device_platform.organization_case_templates "
            "(organization_id,code,specialty_id,patient_profile_id,title,titles,document) "
            "SELECT %s,'foreign_case',a.specialty_id,b.patient_profile_id,'Foreign case',"
            '\'{"en":"Foreign case"}\'::jsonb,'
            '\'{"version":3,"code":"foreign_case","title":"Foreign case"}\'::jsonb '
            "FROM device_platform.organization_case_templates a "
            "CROSS JOIN device_platform.organization_case_templates b "
            "WHERE a.organization_id=%s AND b.organization_id=%s LIMIT 1",
            (UUID(first), UUID(first), UUID(second)),
        )


def test_clinical_specialty_cap_serializes_concurrent_inserts(platform):
    p = platform
    token, _ = p.user("tenant-catalog-cap")
    organization_id = p.organization(token)["id"]
    p.sql(
        "INSERT INTO device_platform.organization_clinical_specialties "
        "(organization_id,code,name,names,description) "
        "SELECT %s,'specialty_'||n,'Specialty '||n,jsonb_build_object('en','Specialty '||n),"
        "'Fictional training specialty' FROM generate_series(1,196) n",
        (organization_id,),
    )
    assert p.sql(
        "SELECT count(*) FROM device_platform.organization_clinical_specialties WHERE organization_id=%s",
        (organization_id,),
    ) == [(199,)]

    def insert(code):
        try:
            p.sql(
                "INSERT INTO device_platform.organization_clinical_specialties "
                "(organization_id,code,name,names,description) "
                "VALUES (%s,%s,%s,jsonb_build_object('en',%s::text),'Fictional training specialty')",
                (organization_id, code, code, code),
            )
            return "inserted"
        except psycopg.errors.CheckViolation:
            return "capacity_rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(insert, ("specialty_200a", "specialty_200b")))
    assert sorted(outcomes) == ["capacity_rejected", "inserted"]
    assert p.sql(
        "SELECT count(*) FROM device_platform.organization_clinical_specialties WHERE organization_id=%s",
        (organization_id,),
    ) == [(200,)]


def test_restored_phase_one_backup_keeps_selection_and_tenant_mapping(platform, tmp_path):
    if not shutil.which("pg_dump") or not shutil.which("pg_restore"):
        pytest.skip("PostgreSQL backup tools are required for the restore rehearsal")
    p = platform
    token, _ = p.user("tenant-restore")
    organization_id = p.organization(token)["id"]
    legacy_setup(p, organization_id)
    backfill(p.settings, apply=True, after=None, limit=25)
    source_name = make_url(p.settings.migration_database_url.get_secret_value()).database
    admin_url = make_url(os.environ["PMS_TEST_ADMIN_DSN"])
    source_dsn = admin_url.set(database=source_name).render_as_string(hide_password=False)
    restored_name = "pms_test_tenant_restore_" + uuid4().hex[:12]
    restored_dsn = admin_url.set(database=restored_name).render_as_string(hide_password=False)
    archive = tmp_path / "tenant-clinical-backup.dump"
    subprocess.run(["pg_dump", "-Fc", "-f", str(archive), source_dsn], check=True, capture_output=True)
    with psycopg.connect(admin_url.render_as_string(hide_password=False), autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(restored_name)))
    try:
        subprocess.run(
            ["pg_restore", "--no-owner", "--no-acl", "-d", restored_dsn, str(archive)],
            check=True,
            capture_output=True,
        )
        verification = (
            "SELECT p.id,p.revision,encode(sha256(convert_to(p.document::text,'UTF8')),'hex'),"
            "p.tenant_template_id,c.organization_id,c.source_global_id,c.is_active "
            "FROM device_platform.patient_practice_selections p "
            "JOIN device_platform.organization_case_templates c ON c.id=p.tenant_template_id "
            "WHERE p.organization_id=%s"
        )
        with psycopg.connect(source_dsn) as source, psycopg.connect(restored_dsn) as restored:
            assert (
                source.execute(verification, (organization_id,)).fetchall()
                == restored.execute(verification, (organization_id,)).fetchall()
            )
            assert restored.execute("SELECT version_num FROM public.alembic_version").fetchone() == (
                REVISION,
            )
    finally:
        with psycopg.connect(admin_url.render_as_string(hide_password=False), autocommit=True) as connection:
            connection.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(restored_name)))


def test_runtime_grants_reject_worker_inheriting_private_catalog_access(platform):
    if not shutil.which("psql"):
        pytest.skip("psql is required for the runtime-grant preflight")
    p = platform
    api_role = make_url(p.settings.database_url.get_secret_value()).username
    worker_role = make_url(p.settings.worker_database_url.get_secret_value()).username
    maintenance_role = make_url(p.settings.retention_database_url.get_secret_value()).username
    database = make_url(p.settings.migration_database_url.get_secret_value()).database
    admin_dsn = (
        make_url(os.environ["PMS_TEST_ADMIN_DSN"])
        .set(database=database)
        .render_as_string(hide_password=False)
    )
    with psycopg.connect(admin_dsn) as connection:
        connection.execute(
            sql.SQL("GRANT {} TO {}").format(sql.Identifier(api_role), sql.Identifier(worker_role))
        )
    try:
        script = Path(__file__).resolve().parents[1] / "deploy" / "grant-runtime-access.sql"
        result = subprocess.run(
            [
                "psql",
                "-X",
                "-v",
                "ON_ERROR_STOP=1",
                "-v",
                f"db_name={database}",
                "-v",
                f"api_role={api_role}",
                "-v",
                f"worker_role={worker_role}",
                "-v",
                f"maintenance_role={maintenance_role}",
                "-f",
                str(script),
                admin_dsn,
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode != 0
        assert "without inherited access" in result.stderr
    finally:
        with psycopg.connect(admin_dsn) as connection:
            connection.execute(
                sql.SQL("REVOKE {} FROM {}").format(sql.Identifier(api_role), sql.Identifier(worker_role))
            )
    assert p.sql(
        "SELECT has_table_privilege(%s,%s,'SELECT')",
        (worker_role, "device_platform.organization_case_templates"),
    ) == [(False,)]


def test_backfill_detects_changed_legacy_source_and_rolls_back(platform):
    p = platform
    token, _ = p.user("tenant-source-drift")
    organization_id = p.organization(token)["id"]
    body = legacy_setup(p, organization_id)
    backfill(p.settings, apply=True, after=None, limit=25)
    p.sql(
        "UPDATE device_platform.patient_case_templates SET revision=revision+1 WHERE id=%s",
        (body["template_id"],),
    )
    with pytest.raises(RuntimeError, match="copied legacy record changed"):
        backfill(p.settings, apply=True, after=None, limit=25)
    assert p.sql("SELECT count(*) FROM device_platform.organization_case_templates") == [(3,)]
    assert p.sql(
        "SELECT count(*) FROM device_platform.activity_events "
        "WHERE event_type='tenant.catalog.legacy_backfilled'"
    ) == [(1,)]


def test_upgrade_from_previous_head_preserves_an_existing_selection(empty_database_target):
    settings, dsn, _ = empty_database_target
    initialize_database(settings, lambda: command.upgrade(migration_config(), "0028_language_validator_acl"))
    org_id, user_id, selection_id = uuid4(), uuid4(), uuid4()
    with psycopg.connect(dsn) as connection:
        connection.execute(
            "INSERT INTO device_platform.users "
            "(id,identity_issuer,identity_subject,display_name,email,email_verified) "
            "VALUES (%s,'https://issuer.test','phase1','Phase One','phase1@example.test',true)",
            (user_id,),
        )
        connection.execute(
            "INSERT INTO device_platform.organizations "
            "(id,name,subscription_plan_id,policy_settings) "
            "SELECT %s,'Previous head hospital',plan.id,settings.default_organization_policy "
            "FROM device_platform.subscription_plans plan CROSS JOIN device_platform.platform_settings settings "
            "WHERE plan.code='standard' AND settings.id=1",
            (org_id,),
        )
        connection.execute(
            "INSERT INTO device_platform.organization_memberships "
            "(id,organization_id,user_id,role,is_active,invitation_status,joined_at) "
            "VALUES (%s,%s,%s,'org_admin',true,'accepted',now())",
            (uuid4(), org_id, user_id),
        )
        connection.execute(
            "INSERT INTO device_platform.patient_practice_selections "
            "(id,organization_id,user_id,template_id,category_id,patient_identity_id,"
            "template_revision,document,language) "
            "SELECT %s,%s,%s,id,category_id,patient_identity_id,revision,document,'en' "
            "FROM device_platform.patient_case_templates ORDER BY code LIMIT 1",
            (selection_id, org_id, user_id),
        )
        before = connection.execute(
            "SELECT id,revision,md5(document::text),template_id,category_id,patient_identity_id "
            "FROM device_platform.patient_practice_selections WHERE id=%s",
            (selection_id,),
        ).fetchone()
    command.upgrade(migration_config(), "head")
    with psycopg.connect(dsn) as connection:
        assert (
            connection.execute(
                "SELECT id,revision,md5(document::text),template_id,category_id,patient_identity_id "
                "FROM device_platform.patient_practice_selections WHERE id=%s",
                (selection_id,),
            ).fetchone()
            == before
        )
        assert connection.execute(
            "SELECT tenant_template_id FROM device_platform.patient_practice_selections WHERE id=%s",
            (selection_id,),
        ).fetchone() == (None,)
    result = backfill(settings, apply=True, after=None, limit=25)
    assert len(result) == 1 and result[0].mapped_selections == 1
    with psycopg.connect(dsn) as connection:
        assert (
            connection.execute(
                "SELECT id,revision,md5(document::text),template_id,category_id,patient_identity_id "
                "FROM device_platform.patient_practice_selections WHERE id=%s",
                (selection_id,),
            ).fetchone()
            == before
        )
