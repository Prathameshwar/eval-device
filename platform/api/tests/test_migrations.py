import os
from importlib.resources import files
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.engine import make_url

from pms_api.cli import adopt
from pms_api.database import speech  # noqa: F401 -- register speech metadata for standalone execution
from pms_api.database.models import Base
from pms_api.database.verification import verify_baseline


def test_verified_adoption_rejects_drift_and_preserves_data(monkeypatch):
    dsn = os.environ.get("PMS_TEST_ADMIN_DSN")
    if not dsn:
        pytest.skip("Set PMS_TEST_ADMIN_DSN")
    url = make_url(dsn)
    name = "pms_test_adopt_" + uuid4().hex[:12]
    schema_owner = name + "_owner"
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(schema_owner)))
        c.execute(
            sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(name), sql.Identifier(schema_owner))
        )
    target = url.set(database=name).render_as_string(hide_password=False)
    url = url.set(query={**url.query, "options": "-c role=" + schema_owner})
    try:
        with psycopg.connect(target, options="-c role=" + schema_owner) as c:
            c.execute("CREATE SCHEMA device_platform")
            c.execute("SET LOCAL search_path=device_platform,pg_catalog")
            for file in sorted(files("pms_api.database.baseline").iterdir(), key=lambda p: p.name):
                if file.name.endswith(".sql"):
                    c.execute(file.read_text(encoding="utf-8-sig"), prepare=False)
            assert verify_baseline(c)
            c.execute("SAVEPOINT drift")
            c.execute("ALTER TABLE device_platform.devices ALTER COLUMN is_active SET DEFAULT false")
            with pytest.raises(RuntimeError, match="structural drift"):
                verify_baseline(c)
            c.execute("ROLLBACK TO SAVEPOINT drift")
            c.execute("SAVEPOINT trigger_drift")
            c.execute("ALTER TABLE device_platform.users DISABLE TRIGGER USER")
            with pytest.raises(RuntimeError, match="structural drift"):
                verify_baseline(c)
            c.execute("ROLLBACK TO SAVEPOINT trigger_drift")
            c.execute(
                "INSERT INTO device_platform.users(id,identity_issuer,identity_subject,display_name,email,email_verified) VALUES(%s,'https://issuer.test','preserved','Preserved','preserved@example.com',true)",
                (uuid4(),),
            )
        with psycopg.connect(target, options="-c role=" + schema_owner) as c:
            legacy_org = uuid4()
            c.execute(
                "INSERT INTO device_platform.organizations(id,name,policy_settings) SELECT %s,'Legacy organization',default_organization_policy FROM device_platform.platform_settings",
                (legacy_org,),
            )
            c.execute(
                "INSERT INTO device_platform.organization_memberships(id,organization_id,user_id,role,is_active,invitation_status,joined_at) SELECT gen_random_uuid(),%s,id,'org_admin',true,'accepted',now() FROM device_platform.users WHERE identity_subject='preserved'",
                (legacy_org,),
            )
            c.execute(
                "INSERT INTO device_platform.devices(id,organization_id,name,device_type) SELECT gen_random_uuid(),%s,'Legacy device '||n,'laptop' FROM generate_series(1,11) n",
                (legacy_org,),
            )
        migration_target = url.set(drivername="postgresql+psycopg", database=name).render_as_string(
            hide_password=False
        )
        monkeypatch.setenv("PMS_DATABASE_URL", migration_target)
        monkeypatch.setenv("PMS_MIGRATION_DATABASE_URL", migration_target)
        monkeypatch.setenv("PMS_TOKEN_PEPPER", "p" * 40)
        monkeypatch.setenv("PMS_MEDIA_SIGNING_KEY", "m" * 40)
        adopt()
        from alembic import command

        from pms_api.cli import migration_config
        from pms_api.core.config import get_settings

        get_settings.cache_clear()
        command.upgrade(migration_config(), "0005_subscriptions")
        # Exercise a real upgrade: preserve commercial edits and customized caps,
        # while updating the untouched Standard capacity pair despite legacy overage.
        with psycopg.connect(target, options="-c role=" + schema_owner) as c:
            c.execute(
                "UPDATE device_platform.subscription_plans SET price_amount=345678.90, currency='USD', billing_period='one_time' WHERE code='standard'"
            )
            c.execute(
                "UPDATE device_platform.subscription_plans SET max_users=77, max_devices=8, is_active=false WHERE code='advanced'"
            )
        command.upgrade(migration_config(), "0007_training_pilot")
        # Preserve a real pre-authoring approved case and active session byte-for-byte.
        import json
        from pathlib import Path

        from psycopg.types.json import Jsonb
        from training_contracts import fingerprint

        case_document = json.loads(
            (
                Path(__file__).resolve().parents[3]
                / "device/training/src/device_training/scenarios/cough_interview_dev.json"
            ).read_text(encoding="utf-8")
        )
        legacy_case, legacy_session = uuid4(), uuid4()
        with psycopg.connect(target, options="-c role=" + schema_owner) as c:
            author_id = c.execute(
                "SELECT id FROM device_platform.users WHERE identity_subject='preserved'"
            ).fetchone()[0]
            device_id = c.execute(
                "SELECT id FROM device_platform.devices WHERE organization_id=%s LIMIT 1", (legacy_org,)
            ).fetchone()[0]
            c.execute(
                "INSERT INTO device_platform.training_scenarios(id,organization_id,request_key,code,version,document,fingerprint,created_by,approved_by,approved_at,approval) VALUES(%s,%s,%s,%s,1,%s,%s,%s,%s,now(),%s)",
                (
                    legacy_case,
                    legacy_org,
                    uuid4(),
                    case_document["code"],
                    Jsonb(case_document),
                    fingerprint(case_document),
                    author_id,
                    author_id,
                    Jsonb({"statement": "Test upgrade fixture only"}),
                ),
            )
            c.execute(
                "INSERT INTO device_platform.training_sessions(id,organization_id,device_id,learner_id,instructor_id,scenario_id,request_key,fingerprint,device_credential_version,language,status,duration_seconds,limits,expires_at,results_expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,1,'hi','active',300,'{}',now()+interval '5 minutes',now()+interval '1 day')",
                (legacy_session, legacy_org, device_id, author_id, author_id, legacy_case, uuid4(), "a" * 64),
            )
            before_case = c.execute(
                "SELECT to_jsonb(t) FROM device_platform.training_scenarios t WHERE id=%s", (legacy_case,)
            ).fetchone()[0]
            before_session = c.execute(
                "SELECT to_jsonb(t) FROM device_platform.training_sessions t WHERE id=%s", (legacy_session,)
            ).fetchone()[0]
        command.upgrade(migration_config(), "0009_local_llm")
        legacy_llm, legacy_request = uuid4(), uuid4()
        with psycopg.connect(target, options="-c role=" + schema_owner) as c:
            c.execute(
                "INSERT INTO device_platform.llm_connections "
                "(id,organization_id,created_by,name,base_url,model,system_prompt,max_tokens,"
                "encrypted_credentials,credential_key_id) VALUES (%s,%s,%s,'Preserved local',"
                "'http://127.0.0.1:8787','qwen3-4b-local','Preserved instructions',192,%s,'old-key')",
                (legacy_llm, legacy_org, author_id, b"opaque-encrypted-fixture"),
            )
            c.execute(
                "INSERT INTO device_platform.llm_requests "
                "(id,organization_id,user_id,connection_id,connection_revision,request_key,fingerprint,"
                "target_key,status,reserved_tokens,lease_token,created_at,lease_expires_at,expires_at) "
                "VALUES (%s,%s,%s,%s,1,%s,%s,%s,'running',192,%s,now(),now()+interval '2 minutes',"
                "now()+interval '24 hours')",
                (legacy_request, legacy_org, author_id, legacy_llm, uuid4(), "a" * 64, "b" * 64, uuid4()),
            )
            llm_before = c.execute(
                "SELECT to_jsonb(t) FROM device_platform.llm_connections t WHERE id=%s", (legacy_llm,)
            ).fetchone()[0]
            request_before = c.execute(
                "SELECT to_jsonb(t) FROM device_platform.llm_requests t WHERE id=%s", (legacy_request,)
            ).fetchone()[0]
        command.upgrade(migration_config(), "0016_local_turns")
        historical_cloud = uuid4()
        with psycopg.connect(target, options="-c role=" + schema_owner) as c:
            c.execute(
                "INSERT INTO device_platform.llm_connections "
                "(id,organization_id,created_by,name,base_url,model,system_prompt,max_tokens,"
                "encrypted_credentials,credential_key_id,provider) VALUES (%s,%s,%s,'Cloud history',"
                "'https://models.example/v1','cloud-model','Preserved instructions',192,%s,'old-key','openai_compatible')",
                (historical_cloud, legacy_org, author_id, b"opaque-encrypted-fixture"),
            )
            historical_usage = [
                {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
                {"completion_tokens": 8},
                {"prompt_tokens": True, "completion_tokens": 8},
                {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 1},
            ]
            for usage in historical_usage:
                request_id = uuid4()
                c.execute(
                    "INSERT INTO device_platform.llm_requests "
                    "(id,organization_id,user_id,connection_id,connection_revision,request_key,fingerprint,"
                    "target_key,status,reserved_tokens,lease_token,created_at,lease_expires_at,expires_at) "
                    "VALUES (%s,%s,%s,%s,1,%s,%s,%s,'running',192,%s,now(),now()+interval '2 minutes',"
                    "now()+interval '24 hours')",
                    (
                        request_id,
                        legacy_org,
                        author_id,
                        historical_cloud,
                        uuid4(),
                        "c" * 64,
                        uuid4().hex * 2,
                        uuid4(),
                    ),
                )
                c.execute(
                    "UPDATE device_platform.llm_requests SET status='succeeded',completed_at=now(),result=%s WHERE id=%s",
                    (Jsonb({"usage": usage}), request_id),
                )
        command.upgrade(migration_config(), "head")
        with psycopg.connect(target, options="-c role=" + schema_owner) as c:
            assert c.execute(
                "SELECT reserved_total_tokens,charged_total_tokens FROM device_platform.llm_requests WHERE id=%s",
                (legacy_request,),
            ).fetchone() == (0, None)
            assert c.execute(
                "SELECT reserved_total_tokens,charged_total_tokens FROM device_platform.llm_requests "
                "WHERE connection_id=%s ORDER BY charged_total_tokens NULLS LAST",
                (historical_cloud,),
            ).fetchall() == [(100000, 20), (100000, None), (100000, None), (100000, None)]
        with psycopg.connect(target, options="-c role=" + schema_owner) as c:
            llm_after = c.execute(
                "SELECT to_jsonb(t) FROM device_platform.llm_connections t WHERE id=%s", (legacy_llm,)
            ).fetchone()[0]
            for key, expected in {
                "provider": "local_llama_cpp",
                "token_parameter": "max_tokens",
                "stream_usage": True,
                "instruction_role": "system",
                "model_options": {},
                "archived_at": None,
                "archived_by": None,
                "model_definition_id": None,
                "managed_by_platform": False,
            }.items():
                assert llm_after.pop(key) == expected
            assert llm_after["max_tokens"] == 256
            assert llm_after["revision"] == llm_before["revision"] + 1
            assert llm_after["updated_at"] >= llm_before["updated_at"]
            for changed_field in ("max_tokens", "revision", "updated_at"):
                llm_after.pop(changed_field)
                llm_before.pop(changed_field)
            assert llm_after == llm_before
            assert (
                c.execute(
                    "SELECT to_jsonb(t)-ARRAY['practice_id','practice_revision','practice_snapshot_hash','profile_revision_id','configuration_hash','reserved_total_tokens','charged_total_tokens','conversation_id','conversation_sequence','conversation_input','device_id','device_credential_version'] FROM device_platform.llm_requests t WHERE id=%s",
                    (legacy_request,),
                ).fetchone()[0]
                == request_before
            )
        with psycopg.connect(target, options="-c role=" + schema_owner) as c:
            # Migration 0041 intentionally simplified historical case documents.
            # The subsequent device-ownership migration preserves their metadata.
            after_document = c.execute(
                "SELECT document,fingerprint FROM device_platform.training_scenarios WHERE id=%s",
                (legacy_case,),
            ).fetchone()
            assert after_document[0]["version"] == 4
            assert not {"qna", "instructor", "fact_disclosure"} & after_document[0].keys()
            assert after_document[1] == fingerprint(after_document[0])
            before_case.pop("document")
            before_case.pop("fingerprint")
            assert (
                c.execute(
                    "SELECT to_jsonb(t)-ARRAY['document','fingerprint','source_draft_id','source_draft_revision','specialty_id','publication_source','starter_case_id'] FROM device_platform.training_scenarios t WHERE id=%s",
                    (legacy_case,),
                ).fetchone()[0]
                == before_case
            )
            assert (
                c.execute(
                    "SELECT to_jsonb(t) FROM device_platform.training_sessions t WHERE id=%s",
                    (legacy_session,),
                ).fetchone()[0]
                == before_session
            )
            assert c.execute(
                "SELECT source_draft_id,source_draft_revision,specialty_id,publication_source,starter_case_id FROM device_platform.training_scenarios WHERE id=%s",
                (legacy_case,),
            ).fetchone() == (None, None, None, "tenant_review", None)
        with psycopg.connect(target, options="-c role=" + schema_owner) as c:
            standard = c.execute(
                "SELECT max_users,max_devices,price_amount::text,currency,billing_period,configuration_version FROM device_platform.subscription_plans WHERE code='standard'"
            ).fetchone()
            assert standard == (200, 1, "345678.90", "USD", "one_time", 3)
            advanced = c.execute(
                "SELECT max_users,max_devices,is_active,configuration_version FROM device_platform.subscription_plans WHERE code='advanced'"
            ).fetchone()
            assert advanced == (77, 8, False, 2)
            assert c.execute(
                "SELECT tgenabled FROM pg_trigger WHERE tgrelid='device_platform.subscription_plans'::regclass AND tgname='subscription_plan_guard'"
            ).fetchone() == ("O",)
            c.execute("SAVEPOINT restored_guard")
            with pytest.raises(psycopg.errors.CheckViolation):
                c.execute(
                    "UPDATE device_platform.subscription_plans SET configuration_version=999 WHERE code='standard'"
                )
            c.execute("ROLLBACK TO SAVEPOINT restored_guard")
        import asyncio

        from sqlalchemy import text as sql_text

        from pms_api.database.session import engine_for

        async def check_runtime_options():
            engine = engine_for(get_settings(), "migration")
            try:
                async with engine.connect() as connection:
                    result = (
                        await connection.execute(
                            sql_text(
                                "SELECT current_user,current_setting('TimeZone'),current_setting('statement_timeout')"
                            )
                        )
                    ).one()
                    assert tuple(result) == (schema_owner, "UTC", "15s")
            finally:
                await engine.dispose()

        asyncio.run(check_runtime_options())
        with psycopg.connect(target, options="-c role=" + schema_owner) as c:
            assert (
                c.execute(
                    "SELECT display_name FROM device_platform.users WHERE identity_subject='preserved'"
                ).fetchone()[0]
                == "Preserved"
            )
            adopted = c.execute(
                "SELECT p.code,o.subscription_assigned_at=o.created_at,(SELECT count(*) FROM device_platform.devices WHERE organization_id=o.id) FROM device_platform.organizations o JOIN device_platform.subscription_plans p ON p.id=o.subscription_plan_id WHERE o.id=%s",
                (legacy_org,),
            ).fetchone()
            assert adopted == ("standard", True, 11)
            c.execute("SAVEPOINT over_capacity")
            with pytest.raises(psycopg.errors.CheckViolation) as rejected:
                c.execute(
                    "INSERT INTO device_platform.devices(id,organization_id,name,device_type,device_unique_id) VALUES(gen_random_uuid(),%s,'Beyond legacy capacity','laptop','legacy-capacity-extra')",
                    (legacy_org,),
                )
            assert rejected.value.diag.constraint_name == "subscription_device_limit"
            c.execute("ROLLBACK TO SAVEPOINT over_capacity")
            rows = c.execute(
                "SELECT table_name,column_name FROM information_schema.columns WHERE table_schema='device_platform' AND table_name NOT IN ('default_roles','default_role_permissions')"
            ).fetchall()
            mapped = {
                (table.name, column.name)
                for table in Base.metadata.tables.values()
                for column in table.columns
            }
            assert rows and set(rows) == mapped
            # Column names alone miss ORM drift that can break otherwise valid SQL.
            columns = c.execute(
                "SELECT t.relname,a.attname,format_type(a.atttypid,a.atttypmod),NOT a.attnotnull "
                "FROM pg_class t JOIN pg_namespace n ON n.oid=t.relnamespace "
                "JOIN pg_attribute a ON a.attrelid=t.oid "
                "WHERE n.nspname='device_platform' AND t.relkind='r' "
                "AND a.attnum>0 AND NOT a.attisdropped"
            ).fetchall()
            expected_columns = {
                (table.name, column.name): (
                    str(column.type.compile(dialect=dialect())).lower().replace(", ", ","),
                    column.nullable,
                )
                for table in Base.metadata.tables.values()
                if not table.info.get("compatibility_view")
                for column in table.columns
            }
            assert {(table, name): (kind, nullable) for table, name, kind, nullable in columns} == (
                expected_columns
            )
            compatibility_views = {
                table.name for table in Base.metadata.tables.values() if table.info.get("compatibility_view")
            }
            assert compatibility_views == {"media_model_configs", "platform_model_connections"}
            assert set(
                c.execute(
                    "SELECT table_name FROM information_schema.views WHERE table_schema='device_platform' AND table_name IN ('media_model_configs','platform_model_connections')"
                ).fetchall()
            ) == {(name,) for name in compatibility_views}
            assert (
                c.execute("SELECT languages FROM device_platform.platform_settings").fetchone()[0][1]["code"]
                == "hi"
            )
    finally:
        from pms_api.core.config import get_settings

        get_settings.cache_clear()
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
            c.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(schema_owner)))
