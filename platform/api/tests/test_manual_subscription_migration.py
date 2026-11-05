"""Forward upgrade preserves existing plans, registrations and tenant state."""

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.engine import make_url


def test_manual_subscription_upgrade_preserves_existing_assignments():
    dsn = os.environ.get("PMS_TEST_ADMIN_DSN")
    if not dsn:
        pytest.skip("Set PMS_TEST_ADMIN_DSN only to a disposable server")
    name = "pms_test_manual_upgrade_" + uuid4().hex[:12]
    url = make_url(dsn).set(database=name)
    target = url.render_as_string(hide_password=False)
    migration_url = url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)
    env = {
        **os.environ,
        "PMS_DATABASE_URL": migration_url,
        "PMS_MIGRATION_DATABASE_URL": migration_url,
        "PMS_TOKEN_PEPPER": "p" * 40,
        "PMS_MEDIA_SIGNING_KEY": "m" * 40,
    }
    root = Path(__file__).resolve().parents[1]

    def upgrade(revision):
        subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(root / "alembic.ini"), "upgrade", revision],
            env=env,
            check=True,
            capture_output=True,
        )

    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        upgrade("0024_conversation_languages")
        org_id, device_id = uuid4(), uuid4()
        with psycopg.connect(target) as c:
            c.execute(
                "UPDATE device_platform.subscription_plans SET price_amount=1234.56 WHERE code='standard'"
            )
            c.execute(
                """
                INSERT INTO device_platform.organizations(id,name,is_active,suspension_source,policy_settings,subscription_plan_id)
                SELECT %s,'Preserved tenant',false,'platform',p.default_organization_policy,s.id
                FROM device_platform.platform_settings p, device_platform.subscription_plans s WHERE s.code='standard'
            """,
                (org_id,),
            )
            c.execute(
                "INSERT INTO device_platform.devices(id,organization_id,name,device_type,is_active) VALUES(%s,%s,'Preserved device','laptop',false)",
                (device_id, org_id),
            )
            before = c.execute(
                "SELECT to_jsonb(o) FROM device_platform.organizations o WHERE id=%s", (org_id,)
            ).fetchone()[0]
        upgrade("head")
        upgrade("head")
        with psycopg.connect(target) as c:
            after = c.execute(
                "SELECT to_jsonb(o) FROM device_platform.organizations o WHERE id=%s", (org_id,)
            ).fetchone()[0]
            assert {key: after[key] for key in before} == before
            assert after["subscription_status"] == "active" and after["subscription_version"] == 1
            assert all(
                after[key] is None
                for key in (
                    "subscription_starts_at",
                    "subscription_ends_at",
                    "subscription_notes",
                    "subscription_reference",
                )
            )
            assert c.execute(
                "SELECT organization_id FROM device_platform.devices WHERE id=%s", (device_id,)
            ).fetchone() == (org_id,)
            assert (
                str(
                    c.execute(
                        "SELECT price_amount FROM device_platform.subscription_plans WHERE code='standard'"
                    ).fetchone()[0]
                )
                == "1234.56"
            )
            assert c.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_proc p, LATERAL aclexplode(p.proacl) a WHERE p.oid='device_platform.guard_manual_subscription()'::regprocedure AND a.grantee=0 AND a.privilege_type='EXECUTE')"
            ).fetchone() == (False,)
    finally:
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
