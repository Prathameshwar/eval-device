"""Fictional identity defaults, migration preservation and deployment-only writes."""

from decimal import Decimal

import psycopg
import pytest
from alembic import command
from sqlalchemy.engine import make_url
from test_scenario_categories import empty_database_target as empty_database_target
from training_contracts.scenarios import Patient

from pms_api.cli import migration_config
from pms_api.database.initialization import initialize_database


def test_alex_identity_constraints_and_runtime_access(platform):
    p = platform
    rows = p.sql(
        "SELECT code,name,names->>'hi',age_years,sex,occupations->>'en',occupations->>'hi',height_cm,weight_kg,preferred_language,languages,is_fictional,is_active FROM device_platform.patient_identities"
    )
    assert rows == [
        (
            "alex",
            "Alex",
            "एलेक्स",
            35,
            "male",
            "Schoolteacher",
            "स्कूल शिक्षक",
            Decimal("175.00"),
            Decimal("75.00"),
            "en",
            ["en", "hi"],
            True,
            True,
        )
    ]
    row = rows[0]
    patient = Patient.model_validate(
        dict(
            name=row[1],
            age_years=row[3],
            sex=row[4],
            occupation={"en": row[5], "hi": row[6]},
            height_cm=float(row[7]),
            weight_kg=float(row[8]),
        )
    )
    assert patient.name == "Alex" and patient.occupation.hi == "स्कूल शिक्षक"
    assert p.sql("SELECT count(*) FROM device_platform.scenario_categories") == [(3,)]
    events = p.sql(
        "SELECT actor_type,organization_id,details FROM device_platform.activity_events WHERE event_type='platform.patient_identity.seeded'"
    )
    assert len(events) == 1 and events[0][:2] == ("system", None)
    assert events[0][2] == dict(
        actor_role="system",
        scope="platform",
        source="migration",
        revision="0012_patient_identities",
        identity_code="alex",
    )
    roles = [
        make_url(value.get_secret_value()).username
        for value in (
            p.settings.database_url,
            p.settings.worker_database_url,
            p.settings.retention_database_url,
        )
    ]
    for role in roles:
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
            assert p.sql(
                "SELECT has_table_privilege(%s,'device_platform.patient_identities',%s)", (role, privilege)
            )[0][0] == (role == roles[0] and privilege == "SELECT")
    assert p.sql(
        "SELECT count(*) FROM information_schema.table_privileges WHERE table_schema='device_platform' AND table_name='patient_identities' AND grantee='PUBLIC'"
    ) == [(0,)]
    for clause in (
        "code='other'",
        "id=gen_random_uuid()",
        "created_at=now()+interval '1 day'",
        "name=' '",
        'names=\'{"en":""}\'',
        'occupations=\'{"en":""}\'',
        'backgrounds=\'{"hi":""}\'',
        "age_years=-1",
        "age_years=151",
        "sex='invalid'",
        "height_cm=0",
        "height_cm=401",
        "height_cm='NaN'",
        "weight_kg=0",
        "weight_kg=2001",
        "weight_kg='NaN'",
        "is_fictional=false",
        "preferred_language='fr'",
        "languages=ARRAY['hi']",
        "languages=ARRAY['en','en']",
        "languages=ARRAY['en',NULL]",
        "languages=ARRAY['en','fr']",
        "languages=ARRAY[]::text[]",
        "languages=ARRAY[['en','hi']]",
        "languages='[0:1]={en,hi}'::text[]",
    ):
        with pytest.raises(psycopg.errors.CheckViolation):
            p.sql("UPDATE device_platform.patient_identities SET " + clause + " WHERE code='alex'")
    p.sql(
        "UPDATE device_platform.patient_identities SET preferred_language='hi',languages=ARRAY['hi'],is_active=false WHERE code='alex'"
    )
    assert p.sql(
        "SELECT preferred_language,updated_at>=created_at FROM device_platform.patient_identities WHERE code='alex'"
    ) == [("hi", True)]
    assert p.client.get("/health/ready").status_code == 200


def test_identity_upgrade_is_atomic_repeatable_and_preserves_records(empty_database_target):
    settings, dsn, _ = empty_database_target
    assert initialize_database(
        settings, lambda: command.upgrade(migration_config(), "0011_scenario_categories")
    )
    with psycopg.connect(dsn) as connection:
        connection.execute(
            "UPDATE device_platform.scenario_categories SET name='Preserved category',is_active=false WHERE code='cardiology'"
        )
        connection.execute("CREATE TABLE public.identity_snapshot_fixture(document jsonb)")
        connection.execute(
            'INSERT INTO public.identity_snapshot_fixture VALUES (\'{"patient": {"name": "Existing patient", "age_years": 42}}\')'
        )
        connection.execute(
            "ALTER TABLE device_platform.activity_events ADD CONSTRAINT reject_identity_seed_fixture CHECK (event_type<>'platform.patient_identity.seeded')"
        )
    with pytest.raises(psycopg.errors.CheckViolation):
        initialize_database(settings, lambda: command.upgrade(migration_config(), "head"))
    with psycopg.connect(dsn) as connection:
        assert connection.execute("SELECT to_regclass('device_platform.patient_identities')").fetchone() == (
            None,
        )
        assert connection.execute("SELECT version_num FROM public.alembic_version").fetchone() == (
            "0011_scenario_categories",
        )
        connection.execute(
            "ALTER TABLE device_platform.activity_events DROP CONSTRAINT reject_identity_seed_fixture"
        )
    assert not initialize_database(settings, lambda: command.upgrade(migration_config(), "head"))
    with psycopg.connect(dsn) as connection:
        before = connection.execute(
            "SELECT id,code,created_at FROM device_platform.patient_identities"
        ).fetchall()
        connection.execute(
            "UPDATE device_platform.patient_identities SET age_years=40,weight_kg=80,preferred_language='hi',is_active=false WHERE code='alex'"
        )
    assert not initialize_database(settings, lambda: command.upgrade(migration_config(), "head"))
    with psycopg.connect(dsn) as connection:
        assert (
            connection.execute("SELECT id,code,created_at FROM device_platform.patient_identities").fetchall()
            == before
        )
        assert connection.execute(
            "SELECT name,age_years,weight_kg,preferred_language,is_active FROM device_platform.patient_identities"
        ).fetchone() == ("Alex", 40, Decimal("80"), "hi", False)
        assert connection.execute(
            "SELECT name,is_active FROM device_platform.scenario_categories WHERE code='cardiology'"
        ).fetchone() == ("Preserved category", False)
        assert connection.execute("SELECT document FROM public.identity_snapshot_fixture").fetchone() == (
            {"patient": {"name": "Existing patient", "age_years": 42}},
        )
        assert connection.execute(
            "SELECT count(*) FROM device_platform.activity_events WHERE event_type='platform.patient_identity.seeded'"
        ).fetchone() == (1,)
