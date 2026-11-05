"""Deployment defaults and preservation of administrator/device configuration."""

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.engine import make_url

DEFAULTS = {("asr", "large-v3"), ("llm", "qwen3.5-4b-local"), ("tts", "espeak_ng")}
ROOT = Path(__file__).resolve().parents[1]


def run_upgrade(dsn, revision="head", initialize=False):
    url = make_url(dsn).set(drivername="postgresql+psycopg").render_as_string(hide_password=False)
    args = (
        ["-c", "from pms_api.cli import admin; admin()", "init-database"]
        if initialize
        else ["-m", "alembic", "-c", str(ROOT / "alembic.ini"), "upgrade", revision]
    )
    result = subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        env={**os.environ, "PMS_MIGRATION_DATABASE_URL": url},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.fixture
def upgrade_database():
    admin_dsn = os.environ.get("PMS_TEST_ADMIN_DSN")
    if not admin_dsn:
        pytest.skip("Set PMS_TEST_ADMIN_DSN for disposable PostgreSQL integration tests")
    name = "pms_test_defaults_" + uuid4().hex[:12]
    target = make_url(admin_dsn).set(database=name).render_as_string(hide_password=False)
    with psycopg.connect(admin_dsn, autocommit=True) as c:
        c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        yield target
    finally:
        with psycopg.connect(admin_dsn, autocommit=True) as c:
            c.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def test_fresh_defaults_visible_through_authorized_api(platform):
    h = platform
    admin, _ = h.admin("default-models-admin")
    rows = h.call("GET", "/platform/runtime-models", admin)["items"]
    assert {(r["kind"], r["model_key"]) for r in rows} == DEFAULTS
    assert len(rows) == 3
    assert all(r["location"] == "local" and r["is_active"] and not r["has_credentials"] for r in rows)
    assert h.sql("SELECT count(*) FROM device_platform.device_model_selections") == [(0,)]
    ready = h.client.get("/health/ready")
    assert ready.status_code == 200 and ready.json()["status"] == "ready"


def test_initialization_is_repeatable_and_preserves_deleted_defaults(upgrade_database):
    target = upgrade_database
    run_upgrade(target, initialize=True)
    with psycopg.connect(target) as c:
        rows = c.execute(
            "SELECT kind,model_key FROM device_platform.runtime_models WHERE archived_at IS NULL"
        ).fetchall()
        assert set(rows) == DEFAULTS and len(rows) == 3
        archived = c.execute(
            "SELECT id FROM device_platform.runtime_models WHERE archived_at IS NOT NULL"
        ).fetchall()
        assert len(archived) == 10
        audits = c.execute(
            "SELECT entity_id FROM device_platform.activity_events "
            "WHERE details->>'source'='0039_default_local_models'"
        ).fetchall()
        assert set(audits) == set(archived)
        c.execute(
            "UPDATE device_platform.runtime_models SET archived_at=now(),is_active=false,revision=revision+1 "
            "WHERE model_key='large-v3'"
        )
        c.execute(
            "UPDATE device_platform.runtime_models SET name='My Qwen',revision=2 WHERE kind='llm' AND archived_at IS NULL"
        )
        before = c.execute("SELECT to_jsonb(m) FROM device_platform.runtime_models m ORDER BY id").fetchall()
    run_upgrade(target, initialize=True)
    with psycopg.connect(target) as c:
        assert (
            c.execute("SELECT to_jsonb(m) FROM device_platform.runtime_models m ORDER BY id").fetchall()
            == before
        )
        assert c.execute(
            "SELECT count(*) FROM device_platform.activity_events WHERE details->>'source'='0039_default_local_models'"
        ).fetchone() == (10,)


def test_upgrade_preserves_customized_used_scoped_and_assigned_models(upgrade_database):
    target = upgrade_database
    run_upgrade(target, "0038_retire_model_setup")
    org, device, custom, cloud, user, scoped = [uuid4() for _ in range(6)]
    with psycopg.connect(target) as c:
        c.execute("SET search_path=device_platform,public")
        c.execute(
            "INSERT INTO users(id,identity_issuer,identity_subject,display_name,email,email_verified) "
            "VALUES(%s,'fixture','fixture','Operator','fixture@example.test',true)",
            (user,),
        )
        c.execute(
            "INSERT INTO organizations(id,name,policy_settings,subscription_plan_id) "
            "SELECT %s,'Upgrade fixture',default_organization_policy,"
            "(SELECT id FROM subscription_plans WHERE code='standard') FROM platform_settings",
            (org,),
        )
        c.execute(
            "INSERT INTO organization_memberships(id,organization_id,user_id,role,is_active,invitation_status,joined_at) "
            "VALUES(gen_random_uuid(),%s,%s,'org_admin',true,'accepted',now())",
            (org, user),
        )
        c.execute(
            "INSERT INTO devices(id,organization_id,name,device_type) VALUES(%s,%s,'Assigned laptop','laptop')",
            (device, org),
        )
        c.execute(
            "INSERT INTO device_model_selections(device_id,organization_id,mode,asr_model_id) "
            "SELECT %s,%s,'local',id FROM runtime_models WHERE model_key='base'",
            (device, org),
        )
        c.execute("UPDATE runtime_models SET name='Custom small',revision=2 WHERE model_key='small'")
        c.execute("UPDATE runtime_models SET last_used_at=now() WHERE model_key='medium'")
        c.execute("UPDATE runtime_models SET defaults='{\"language\":\"hi\"}' WHERE model_key='tiny'")
        c.execute(
            "UPDATE runtime_models SET legacy='{\"preserved\":true}' WHERE model_key='whisper-medical-v1'"
        )
        c.execute(
            "INSERT INTO runtime_models(id,organization_id,name,kind,location,provider,engine,model_key) "
            "VALUES(%s,%s,'OpenCV motion','video','local','local','opencv_motion','opencv_motion')",
            (scoped, org),
        )
        c.execute("UPDATE runtime_models SET is_active=false WHERE model_key='qwenmedic-v1-local'")
        c.execute(
            "UPDATE runtime_models SET settings='{\"context_tokens\":4096}' WHERE model_key='qwen3-4b-local'"
        )
        c.execute(
            "INSERT INTO runtime_models(id,name,kind,location,provider,engine,model_key) "
            "VALUES(%s,'Whisper large-v3-turbo','asr','local','local_whisper','local_whisper','large-v3-turbo')",
            (custom,),
        )
        c.execute(
            "INSERT INTO runtime_models(id,name,kind,location,provider,engine,model_key) "
            "VALUES(%s,'Cloud model','llm','cloud','openai','llm','custom-cloud')",
            (cloud,),
        )
        before = dict(c.execute("SELECT id,to_jsonb(m) FROM runtime_models m").fetchall())
        selection = c.execute("SELECT to_jsonb(s) FROM device_model_selections s").fetchall()
    run_upgrade(target)
    with psycopg.connect(target) as c:
        after = dict(c.execute("SELECT id,to_jsonb(m) FROM device_platform.runtime_models m").fetchall())
        assert set(before) == set(after)
        changed = {ident for ident in before if before[ident] != after[ident]}
        assert {before[ident]["model_key"] for ident in changed} == {
            "large-v3-turbo",
            "qwen3-1.7b-local",
            "opencv_motion",
        }
        assert custom not in changed and cloud not in changed and scoped not in changed
        assert all(
            after[ident]["archived_at"] and not after[ident]["is_active"] and after[ident]["revision"] == 2
            for ident in changed
        )
        assert (
            c.execute("SELECT to_jsonb(s) FROM device_platform.device_model_selections s").fetchall()
            == selection
        )
        audits = c.execute(
            "SELECT entity_id FROM device_platform.activity_events WHERE details->>'source'='0039_default_local_models'"
        ).fetchall()
        assert {row[0] for row in audits} == changed
