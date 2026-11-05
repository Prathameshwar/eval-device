"""Upgrade existing local accounts without losing credentials or bearer sessions."""

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


def test_existing_local_accounts_upgrade_to_browser_sessions():
    dsn = os.environ.get("PMS_TEST_ADMIN_DSN")
    if not dsn:
        pytest.skip("Set PMS_TEST_ADMIN_DSN for a dedicated disposable test server")
    name = "pms_test_browser_upgrade_" + uuid4().hex[:12]
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
        upgrade("0020_management_api")
        user_id, session_id = uuid4(), uuid4()
        with psycopg.connect(target) as connection:
            assert connection.execute("SELECT count(*) FROM device_platform.users").fetchone() == (0,)
            connection.execute(
                "INSERT INTO device_platform.users(id,auth_method,display_name,email,email_verified) "
                "VALUES(%s,'local','Preserved local account','preserved@example.com',true)",
                (user_id,),
            )
            connection.execute(
                "INSERT INTO device_platform.local_credentials(user_id,login_email,password_hash,"
                "credential_version,setup_completed_at) VALUES(%s,'preserved@example.com',%s,7,now())",
                (user_id, "test-only-preserved-hash-" + "x" * 40),
            )
            connection.execute(
                "INSERT INTO device_platform.local_sessions(id,user_id,family_id,refresh_token_hash,"
                "credential_version,expires_at) VALUES(%s,%s,%s,%s,7,now()+interval '1 day')",
                (session_id, user_id, uuid4(), "a" * 64),
            )
            for purpose, digest in (("password_reset", "b"), ("email_change", "c")):
                connection.execute(
                    "INSERT INTO device_platform.account_action_tokens(id,user_id,purpose,token_hash,"
                    "target_email,expires_at) VALUES(%s,%s,%s,%s,%s,now()+interval '1 hour')",
                    (
                        uuid4(),
                        user_id,
                        purpose,
                        digest * 64,
                        "changed@example.com" if purpose == "email_change" else None,
                    ),
                )
        upgrade("head")
        with psycopg.connect(target) as connection:
            assert connection.execute(
                "SELECT credential_version,password_hash FROM device_platform.local_credentials WHERE user_id=%s",
                (user_id,),
            ).fetchone() == (7, "test-only-preserved-hash-" + "x" * 40)
            assert connection.execute(
                "SELECT refresh_token_hash,credential_version,browser_token_hash,revoked_at "
                "FROM device_platform.local_sessions WHERE id=%s",
                (session_id,),
            ).fetchone() == ("a" * 64, 7, None, None)
            assert connection.execute(
                "SELECT purpose,credential_version,consumed_at IS NOT NULL "
                "FROM device_platform.account_action_tokens ORDER BY purpose"
            ).fetchall() == [("email_change", 7, True), ("password_reset", 7, False)]
            assert connection.execute("SELECT version_num FROM public.alembic_version").fetchone() == (
                REVISION,
            )
        # Exercise the shipped read-only script after the real upgrade, so its
        # accepted revision list cannot silently lag behind the migration head.
        verifier = (root / "deploy/verify-scenario-library.sql").read_text(encoding="utf-8")
        statements = "\n".join(line for line in verifier.splitlines() if not line.startswith("\\"))
        with psycopg.connect(target, autocommit=True) as connection:
            connection.execute(statements, prepare=False)
    finally:
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
