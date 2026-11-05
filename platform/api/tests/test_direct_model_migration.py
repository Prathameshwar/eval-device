"""Upgrade a populated 0036 database, including encrypted and inherited models."""

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb
from sqlalchemy.engine import make_url

from pms_api.integrations.vault import CredentialVault
from pms_api.modules.schemas import ProfileSettings


def test_populated_model_upgrade(platform):
    h = platform
    admin_dsn = os.environ["PMS_TEST_ADMIN_DSN"]
    url = make_url(admin_dsn)
    name = "pms_test_models_upgrade_" + uuid4().hex[:12]
    target = url.set(database=name).render_as_string(hide_password=False)
    with psycopg.connect(admin_dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    root = Path(__file__).resolve().parents[1]
    env = {
        **os.environ,
        "PMS_MIGRATION_DATABASE_URL": url.set(
            database=name, drivername="postgresql+psycopg"
        ).render_as_string(hide_password=False),
    }

    def upgrade(revision):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(root / "alembic.ini"), "upgrade", revision],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

    try:
        upgrade("0036_media_model_configs")
        user, org, llm, provider, profile, revision, device, media = [uuid4() for _ in range(8)]
        cipher, key_id = CredentialVault(h.settings).encrypt(org, llm, {"api_key": "migration-fixture"})
        settings = ProfileSettings().model_dump(mode="json", exclude_none=True)
        settings["conversation"] = {"enabled": True, "execution_mode": "local"}
        settings["audio_output"] = {
            "enabled": True,
            "operation": "audio.synthesize",
            "engine": "aws_polly",
            "execution_mode": "cloud",
            "voice": "Aditi",
        }
        with psycopg.connect(target) as c:
            c.execute("SET search_path=device_platform,public")
            c.execute(
                "INSERT INTO users(id,identity_issuer,identity_subject,display_name,email,email_verified) VALUES(%s,'fixture','fixture','Operator','fixture@example.test',true)",
                (user,),
            )
            c.execute(
                "INSERT INTO organizations(id,name,policy_settings,subscription_plan_id) SELECT %s,'Legacy tenant',default_organization_policy,(SELECT id FROM subscription_plans WHERE code='standard') FROM platform_settings",
                (org,),
            )
            c.execute(
                "INSERT INTO organization_memberships(id,organization_id,user_id,role,is_active,invitation_status,joined_at) VALUES(gen_random_uuid(),%s,%s,'org_admin',true,'accepted',now())",
                (org, user),
            )
            c.execute(
                "INSERT INTO llm_connections(id,organization_id,created_by,name,provider,base_url,model,system_prompt,max_tokens,encrypted_credentials,credential_key_id) VALUES(%s,%s,%s,'Local conversation','local_llama_cpp','http://127.0.0.1:8787','qwen3-4b-local','Be brief',256,%s,%s)",
                (llm, org, user, cipher, key_id),
            )
            c.execute(
                "INSERT INTO provider_connections(id,organization_id,created_by,name,provider,connection_type,auth_mode,settings) VALUES(%s,%s,%s,'Cloud voice','aws','aws_processing','workload_identity','{\"region\":\"ap-south-1\"}')",
                (provider, org, user),
            )
            c.execute(
                "INSERT INTO processing_profiles(id,organization_id,created_by,name,draft_settings,draft_llm_connection_id,draft_audio_output_connection_id) VALUES(%s,%s,%s,'Existing setup',%s,%s,%s)",
                (profile, org, user, Jsonb(settings), llm, provider),
            )
            c.execute(
                "INSERT INTO processing_profile_revisions(id,organization_id,profile_id,version,settings,llm_connection_id,audio_output_connection_id,published_by) VALUES(%s,%s,%s,1,%s,%s,%s,%s)",
                (revision, org, profile, Jsonb(settings), llm, provider, user),
            )
            c.execute(
                "UPDATE processing_profiles SET published_revision_id=%s WHERE id=%s", (revision, profile)
            )
            c.execute("UPDATE organizations SET default_profile_id=%s WHERE id=%s", (profile, org))
            c.execute(
                "INSERT INTO devices(id,organization_id,name,device_type) VALUES(%s,%s,'Inherited laptop','laptop')",
                (device, org),
            )
            c.execute(
                "INSERT INTO media_model_configs(id,organization_id,connection_id,name,engine,operation,defaults,created_by,updated_by) VALUES(%s,%s,%s,'Voice preset','aws_polly','audio.synthesize','{\"voice\":\"Aditi\"}',%s,%s)",
                (media, org, provider, user, user),
            )
        upgrade("head")
        with psycopg.connect(target) as c:
            c.execute("SET search_path=device_platform,public")
            selected = c.execute(
                "SELECT mode,llm_model_id,tts_model_id,execution_revision_id FROM device_model_selections WHERE device_id=%s",
                (device,),
            ).fetchone()
            assert selected[0] == "mixed" and selected[1] == llm and selected[2]
            snapshot = c.execute(
                "SELECT profile_id,device_id,settings FROM processing_profile_revisions WHERE id=%s",
                (selected[3],),
            ).fetchone()
            assert snapshot == (None, device, settings)
            assert c.execute(
                "SELECT retired_assignments FROM processing_profiles WHERE id=%s", (profile,)
            ).fetchone()[0] == {"organization_default": True, "device_ids": []}
            assert (
                c.execute(
                    "SELECT count(*) FROM information_schema.columns WHERE table_schema='device_platform' "
                    "AND ((table_name='devices' AND column_name='profile_id') "
                    "OR (table_name='organizations' AND column_name='default_profile_id'))"
                ).fetchone()[0]
                == 0
            )
            assert (
                c.execute(
                    "SELECT settings FROM processing_profile_revisions WHERE id=%s", (revision,)
                ).fetchone()[0]
                == settings
            )
            assert c.execute(
                "SELECT encrypted_credentials,credential_key_id FROM runtime_models WHERE id=%s", (llm,)
            ).fetchone() == (cipher, key_id)
            assert c.execute("SELECT defaults FROM runtime_models WHERE id=%s", (media,)).fetchone()[0] == {
                "voice": "Aditi"
            }
            assert (
                c.execute(
                    "SELECT relkind FROM pg_class WHERE oid='device_platform.media_model_configs'::regclass"
                ).fetchone()[0]
                == "v"
            )
            assert (
                c.execute(
                    "SELECT relkind FROM pg_class WHERE oid='device_platform.platform_model_connections'::regclass"
                ).fetchone()[0]
                == "v"
            )
            with pytest.raises(psycopg.errors.CheckViolation):
                c.execute("UPDATE device_model_selections SET mode='cloud' WHERE device_id=%s", (device,))
    finally:
        with psycopg.connect(admin_dsn, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
