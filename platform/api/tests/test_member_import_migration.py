"""Upgrade existing tenants and verify the new persistence contract."""

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.engine import make_url

from pms_api.database.session import REVISION


def test_member_import_upgrade_preserves_tenants_and_invitation_constraints():
    dsn = os.environ.get("PMS_TEST_ADMIN_DSN")
    if not dsn:
        pytest.skip("Set PMS_TEST_ADMIN_DSN only to a disposable server")
    name = "pms_test_import_upgrade_" + uuid4().hex[:12]
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

    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        upgrade("0025_manual_subscriptions")
        org, user = uuid4(), uuid4()
        with psycopg.connect(target) as connection:
            connection.execute(
                """INSERT INTO device_platform.organizations(id,name,is_active,suspension_source,policy_settings,subscription_plan_id)
                SELECT %s,'Existing tenant',false,'platform',p.default_organization_policy,s.id
                FROM device_platform.platform_settings p,device_platform.subscription_plans s WHERE s.code='standard'""",
                (org,),
            )
            connection.execute(
                """INSERT INTO device_platform.users(id,auth_method,identity_issuer,identity_subject,email,display_name)
                VALUES(%s,'oidc','https://example.test','test','test@example.com','Existing user')""",
                (user,),
            )
            before = connection.execute(
                "SELECT to_jsonb(o) FROM device_platform.organizations o WHERE id=%s", (org,)
            ).fetchone()[0]
        upgrade("head")
        upgrade("head")
        # Migration 0038 deliberately retires this unused model-setup column.
        # All remaining tenant values must still survive the complete upgrade.
        assert before.pop("default_profile_id") is None
        with psycopg.connect(target) as connection:
            assert (
                connection.execute(
                    "SELECT to_jsonb(o) FROM device_platform.organizations o WHERE id=%s", (org,)
                ).fetchone()[0]
                == before
            )
            assert (
                connection.execute("SELECT version_num FROM public.alembic_version").fetchone()[0] == REVISION
            )
            for role, rows in [("platform_admin", "[{}]"), ("org_user", "[]")]:
                with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
                    connection.execute(
                        """INSERT INTO device_platform.member_imports
                        (id,organization_id,created_by,role,auth_method,rows,validated_until,expires_at)
                        VALUES(%s,%s,%s,%s,'local',%s,now()+interval '1 day',now()+interval '30 days')""",
                        (uuid4(), org, user, role, rows),
                    )
    finally:
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
