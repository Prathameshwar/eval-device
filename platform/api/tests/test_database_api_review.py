import asyncio
from uuid import uuid4

import psycopg
from current_model_fixtures import cloud_model_body, cloud_run, local_revision
from test_worker import Adapter, tick


def test_model_revision_fences_updates_and_database_acl(platform, monkeypatch):
    p = platform
    token, _, _, _, _ = cloud_run(p, monkeypatch, Adapter())
    model = p.review_cloud_model
    path = "/platform/runtime-models/" + model["id"]
    changed = p.call(
        "PUT",
        path,
        token,
        json={**cloud_model_body(), "expected_revision": model["revision"], "is_active": False},
    )
    p.call(
        "PUT", path, token, expected=409, json={**cloud_model_body(), "expected_revision": model["revision"]}
    )
    assert changed["revision"] == model["revision"] + 1 and not changed["is_active"]
    assert (
        p.sql(
            "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a WHERE n.nspname='device_platform' AND a.grantee=0 AND a.privilege_type='EXECUTE'"
        )
        == []
    )


def test_revoked_device_cannot_start_or_dispatch_work(platform, monkeypatch):
    p = platform
    adapter = Adapter()
    token, oid, did, credential, rid = cloud_run(p, monkeypatch, adapter)
    revision = p.call("GET", f"/organizations/{oid}/runs/{rid}", token)["profile_revision_id"]
    other = p.organization(token, "Other organization")["id"]
    p.call("GET", f"/organizations/{other}/runs/{rid}", credential, expected=404)
    p.call(
        "POST",
        f"/organizations/{other}/runs",
        credential,
        expected=404,
        json={
            "request_key": str(uuid4()),
            "operation": "audio.synthesize",
            "profile_revision_id": revision,
            "text": "Wrong organization path",
        },
    )
    p.call("POST", f"/organizations/{oid}/devices/{did}/revoke", token)
    p.call(
        "POST",
        f"/organizations/{oid}/runs",
        token,
        expected=409,
        json={
            "device_id": did,
            "request_key": str(uuid4()),
            "operation": "audio.synthesize",
            "profile_revision_id": revision,
            "text": "Must not dispatch",
        },
    )
    config = p.call("GET", f"/organizations/{oid}/devices/{did}/configuration", token)
    assert not config["processing_allowed"]
    asyncio.run(tick(p, adapter))
    assert p.call("GET", f"/organizations/{oid}/runs/{rid}", token)["status"] == "cancelled"
    assert (
        p.sql(
            "SELECT count(*) FROM device_platform.activity_events WHERE run_id=%s AND event_type='processing.state_changed' AND details->>'status'='cancelled' AND details->>'cleanup_status'='pending'",
            (rid,),
        )[0][0]
        == 1
    )
    assert adapter.submissions == 0
    p.enroll(token, oid, did)
    resumed = p.call(
        "POST",
        f"/organizations/{oid}/runs",
        token,
        expected=202,
        json={
            "device_id": did,
            "request_key": str(uuid4()),
            "operation": "audio.synthesize",
            "profile_revision_id": revision,
            "text": "Enrolled again",
        },
    )["run"]
    asyncio.run(tick(p, adapter))
    assert p.call("GET", f"/organizations/{oid}/runs/{resumed['id']}", token)["status"] == "succeeded"
    assert adapter.submissions == 1


def test_device_poll_prioritizes_new_work_over_completed_history(platform):
    p = platform
    token, _ = p.admin()
    oid = p.organization(token)["id"]
    did = p.device(token, oid)["id"]
    credential = p.enroll(token, oid, did)
    revision = local_revision(p, token, oid, did, credential)
    body = {
        "device_id": did,
        "operation": "audio.transcribe",
        "profile_revision_id": revision["id"],
        "duration_seconds": 1,
    }
    old = p.call(
        "POST", f"/organizations/{oid}/runs", token, expected=202, json={**body, "request_key": str(uuid4())}
    )["run"]
    p.call(
        "POST",
        f"/device/runs/{old['id']}/result",
        credential,
        json={"status": "succeeded", "result": {"text": "Synthetic transcript"}},
    )
    p.sql(
        "INSERT INTO device_platform.processing_runs SELECT (jsonb_populate_record(NULL::device_platform.processing_runs, to_jsonb(r)||jsonb_build_object('id',gen_random_uuid(),'request_key',gen_random_uuid()))).* FROM device_platform.processing_runs r CROSS JOIN generate_series(1,50) WHERE r.id=%s",
        (old["id"],),
    )
    pending = p.call(
        "POST", f"/organizations/{oid}/runs", token, expected=202, json={**body, "request_key": str(uuid4())}
    )["run"]
    work = p.call("GET", "/device/runs", credential)["items"]
    assert len(work) == 50 and work[0]["id"] == pending["id"]


def test_provider_preflight_rejects_invalid_work_before_submission(platform, monkeypatch):
    p = platform
    adapter = Adapter()
    token, oid, _, _, rid = cloud_run(p, monkeypatch, adapter)
    # Simulate an existing queued request that predates current request limits.
    p.sql(
        "UPDATE device_platform.processing_runs SET request=request||jsonb_build_object('text',repeat('x',10001)) WHERE id=%s",
        (rid,),
    )
    asyncio.run(tick(p, adapter))
    run = p.call("GET", f"/organizations/{oid}/runs/{rid}", token)
    assert run["status"] == "failed" and run["provider_submission_status"] == "not_submitted"
    assert run["error"]["code"] == "text_too_long" and adapter.submissions == 0
    invalid = p.call(
        "POST",
        "/platform/runtime-models",
        token,
        expected=422,
        json={**cloud_model_body(), "defaults": {"format": "flac"}},
    )
    assert invalid["error"]["code"] == "invalid_request"


def test_deployment_grants_are_self_contained_and_match_database_contract():
    from pathlib import Path

    api = Path(__file__).resolve().parents[1]
    source = (api.parent / "db/grant-access.sql").read_text(encoding="utf-8-sig")
    deployed = (api / "deploy/grant-runtime-access.sql").read_text(encoding="utf-8-sig")
    extra = 'GRANT SELECT ON public.alembic_version TO :"api_role", :"worker_role", :"maintenance_role";\nGRANT UPDATE ON device_platform.subscription_plans TO :"api_role";\nGRANT EXECUTE ON FUNCTION device_platform.subscription_usage(uuid) TO :"api_role";'
    extra += '\nGRANT INSERT, UPDATE ON device_platform.training_scenarios, device_platform.training_sessions TO :"api_role";\nGRANT SELECT, DELETE ON device_platform.training_sessions TO :"maintenance_role";'
    expected = source.replace("COMMIT;", extra + chr(10) + "COMMIT;")
    expected = expected.replace(
        "COMMIT;",
        "-- Drafts contain private instructor content; workers/retention do not need it.\n"
        'REVOKE ALL ON device_platform.training_scenario_drafts FROM :"worker_role", :"maintenance_role";\n'
        'GRANT SELECT, INSERT, UPDATE ON device_platform.training_scenario_drafts TO :"api_role";\nCOMMIT;',
    )
    expected = expected.replace(
        "COMMIT;",
        'REVOKE ALL ON device_platform.tenant_scenario_defaults FROM :"worker_role", :"maintenance_role";\n'
        'GRANT SELECT, INSERT, UPDATE ON device_platform.tenant_scenario_defaults TO :"api_role";\nCOMMIT;',
    )
    expected = expected.replace(
        "COMMIT;",
        'REVOKE ALL ON device_platform.llm_connections,device_platform.llm_requests FROM :"worker_role", :"maintenance_role";\n'
        'GRANT SELECT, INSERT, UPDATE ON device_platform.llm_connections,device_platform.llm_requests TO :"api_role";\n'
        'REVOKE ALL ON device_platform.speech_requests FROM :"worker_role", :"maintenance_role";\n'
        'GRANT SELECT, INSERT, UPDATE, DELETE ON device_platform.speech_requests TO :"api_role";\n'
        'GRANT SELECT, DELETE ON device_platform.llm_requests TO :"maintenance_role";\nCOMMIT;',
    )
    expected = expected.replace(
        "COMMIT;",
        "-- Shared category defaults are deployment-managed; runtime roles cannot edit them.\n"
        'REVOKE ALL ON device_platform.scenario_categories FROM :"api_role", :"worker_role", :"maintenance_role";\n'
        'GRANT SELECT ON device_platform.scenario_categories TO :"api_role";\n'
        "-- Fictional identity templates are deployment-managed and contain no tenant records.\n"
        'REVOKE ALL ON device_platform.patient_identities FROM :"api_role", :"worker_role", :"maintenance_role";\n'
        'GRANT SELECT ON device_platform.patient_identities TO :"api_role";\nCOMMIT;',
    )
    expected = expected.replace(
        "COMMIT;",
        "-- Practice snapshots belong to staff; background workers have no access.\n"
        'REVOKE ALL ON device_platform.patient_case_templates,device_platform.patient_practice_selections FROM :"api_role", :"worker_role", :"maintenance_role";\n'
        'GRANT SELECT ON device_platform.patient_case_templates TO :"api_role";\n'
        'GRANT SELECT, INSERT, UPDATE ON device_platform.patient_practice_selections TO :"api_role";\nCOMMIT;',
    )
    expected = expected.replace(
        "COMMIT;",
        "-- A turn executed on a caller's own machine is reported once and never amended here, so the\n"
        "-- API inserts and reads only; retention deletes rows the trigger has already let expire.\n"
        'REVOKE ALL ON device_platform.local_turns FROM :"api_role", :"worker_role", :"maintenance_role";\n'
        'GRANT SELECT, INSERT ON device_platform.local_turns TO :"api_role";\n'
        'GRANT SELECT, DELETE ON device_platform.local_turns TO :"maintenance_role";\nCOMMIT;',
    )
    expected = expected.replace(
        "COMMIT;",
        'REVOKE ALL ON device_platform.local_conversation_turns FROM :"api_role", :"worker_role", :"maintenance_role";\n'
        'GRANT SELECT, INSERT ON device_platform.local_conversation_turns TO :"api_role";\n'
        'GRANT SELECT, DELETE ON device_platform.local_conversation_turns TO :"maintenance_role";\nCOMMIT;',
    )
    expected = expected.replace(
        "COMMIT;",
        "-- Local identity secrets and delivery payloads are API-owned. Processing and retention workers\n"
        "-- receive no access; retention is handled by bounded API maintenance until a dedicated role exists.\n"
        "REVOKE ALL ON device_platform.local_credentials,device_platform.local_sessions,\n"
        "  device_platform.account_action_tokens,device_platform.auth_rate_limits,\n"
        '  device_platform.account_email_outbox FROM :"worker_role", :"maintenance_role";\n'
        'GRANT SELECT, INSERT, UPDATE ON device_platform.local_credentials TO :"api_role";\n'
        "GRANT SELECT, INSERT, UPDATE, DELETE ON device_platform.local_sessions,\n"
        "  device_platform.account_action_tokens,\n"
        '  device_platform.auth_rate_limits,device_platform.account_email_outbox TO :"api_role";\n'
        "-- Model definitions are platform-managed through the API; tenant workers only consume immutable\n"
        "-- profile/run snapshots and do not edit or discover this catalog.\n"
        'REVOKE ALL ON device_platform.model_definitions FROM :"worker_role", :"maintenance_role";\n'
        'GRANT SELECT, INSERT, UPDATE ON device_platform.model_definitions TO :"api_role";\nCOMMIT;',
    )
    expected = expected.replace(
        "COMMIT;",
        'REVOKE ALL ON device_platform.platform_model_connections FROM :"worker_role", :"maintenance_role";\n'
        'GRANT SELECT, INSERT, UPDATE ON device_platform.platform_model_connections TO :"api_role";\nCOMMIT;',
    )
    expected = expected.replace(
        "COMMIT;",
        'REVOKE ALL ON device_platform.patient_conversations FROM :"worker_role", :"maintenance_role";\n'
        'GRANT SELECT, INSERT, UPDATE ON device_platform.patient_conversations TO :"api_role";\n'
        'GRANT SELECT, DELETE ON device_platform.patient_conversations TO :"maintenance_role";\nCOMMIT;',
    )
    expected = expected.replace(
        "COMMIT;",
        "-- Tenant import records and encrypted invitation tokens are API-owned.\n"
        "REVOKE ALL ON device_platform.member_imports,device_platform.invitation_email_outbox\n"
        '  FROM :"worker_role", :"maintenance_role";\n'
        "GRANT SELECT, INSERT, UPDATE, DELETE ON device_platform.member_imports,device_platform.invitation_email_outbox\n"
        '  TO :"api_role";\nCOMMIT;',
    )
    expected = expected.replace(
        "COMMIT;",
        "-- Existing shared patient catalog is frozen for API callers at cutover.\n"
        "REVOKE INSERT, UPDATE, DELETE ON device_platform.scenario_categories,\n"
        '  device_platform.patient_identities,device_platform.patient_case_templates FROM :"api_role";\nCOMMIT;',
    )
    expected = expected.replace(
        "COMMIT;",
        "-- Tenant clinical drafts are API-owned; workers and retention do not read private case facts.\n"
        "REVOKE ALL ON device_platform.organization_clinical_specialties,\n"
        "  device_platform.organization_patient_profiles,device_platform.organization_case_templates\n"
        '  FROM :"worker_role", :"maintenance_role";\n'
        "GRANT SELECT, INSERT, UPDATE ON device_platform.organization_clinical_specialties,\n"
        "  device_platform.organization_patient_profiles,device_platform.organization_case_templates\n"
        '  TO :"api_role";\n'
        "REVOKE ALL ON device_platform.tenant_patient_setup_defaults\n"
        '  FROM :"worker_role", :"maintenance_role";\n'
        'GRANT SELECT, INSERT, UPDATE ON device_platform.tenant_patient_setup_defaults TO :"api_role";\n'
        "REVOKE ALL ON device_platform.organization_member_capabilities\n"
        '  FROM :"worker_role", :"maintenance_role";\n'
        'GRANT SELECT, INSERT, UPDATE ON device_platform.organization_member_capabilities TO :"api_role";\nCOMMIT;',
    )
    expected = expected.replace(
        "COMMIT;",
        "-- Localization row validators run as the API caller; workers do not edit this catalog.\n"
        "REVOKE ALL ON FUNCTION device_platform.valid_language_map(jsonb,integer),\n"
        '  device_platform.valid_language_list(text[],text) FROM PUBLIC, :"worker_role", :"maintenance_role";\n'
        "GRANT EXECUTE ON FUNCTION device_platform.valid_language_map(jsonb,integer),\n"
        '  device_platform.valid_language_list(text[],text) TO :"api_role";\nCOMMIT;',
    )
    expected = expected.replace(
        'GRANT SELECT, INSERT, UPDATE ON device_platform.platform_model_connections TO :"api_role";',
        'GRANT SELECT, INSERT, UPDATE ON device_platform.platform_model_connections TO :"api_role";\n'
        'REVOKE ALL ON device_platform.media_model_configs FROM :"worker_role", :"maintenance_role";\n'
        'GRANT SELECT, INSERT, UPDATE ON device_platform.media_model_configs TO :"api_role";',
    )
    expected = expected.replace(
        "GRANT SELECT, INSERT, UPDATE ON device_platform.platform_model_connections",
        "GRANT SELECT ON device_platform.platform_model_connections",
    )
    expected = expected.replace(
        "GRANT SELECT, INSERT, UPDATE ON device_platform.media_model_configs",
        "GRANT SELECT ON device_platform.media_model_configs",
    )
    model_grants = ', device_platform.device_model_selections TO :"api_role";\nGRANT SELECT ON device_platform.runtime_models, device_platform.device_model_selections TO :"worker_role";\nGRANT UPDATE(last_used_at) ON device_platform.runtime_models TO :"worker_role";\nREVOKE ALL ON device_platform.runtime_models, device_platform.device_model_selections FROM :"maintenance_role";\n\n-- Workers can read media credentials only; conversation credentials stay with the API.\nALTER TABLE device_platform.runtime_models ENABLE ROW LEVEL SECURITY;\nDROP POLICY IF EXISTS runtime_models_api ON device_platform.runtime_models;\nCREATE POLICY runtime_models_api ON device_platform.runtime_models TO :"api_role" USING (true) WITH CHECK (true);\nDROP POLICY IF EXISTS runtime_models_worker ON device_platform.runtime_models;\nCREATE POLICY runtime_models_worker ON device_platform.runtime_models TO :"worker_role" USING (kind<>\'llm\') WITH CHECK (kind<>\'llm\');\n\nCOMMIT;\n'
    expected = expected.replace(
        "COMMIT;\n", "GRANT SELECT, INSERT, UPDATE ON device_platform.runtime_models" + model_grants
    )
    expected = expected.replace(
        "COMMIT;\n",
        """-- Historical configurations are not an alternate management path.
REVOKE INSERT, UPDATE, DELETE ON device_platform.provider_connections,
  device_platform.llm_connections, device_platform.processing_profiles FROM :"api_role";
REVOKE UPDATE(last_used_at) ON device_platform.provider_connections FROM :"worker_role";
COMMIT;
""",
    )
    expected = expected.replace(
        'GRANT SELECT ON ALL TABLES IN SCHEMA device_platform TO :"api_role", :"worker_role";\n',
        'GRANT SELECT ON ALL TABLES IN SCHEMA device_platform TO :"api_role", :"worker_role";\n'
        'REVOKE ALL ON device_platform.device_identities FROM :"api_role", :"worker_role", :"maintenance_role";\n'
        'GRANT SELECT, INSERT ON device_platform.device_identities TO :"api_role";\n',
    )
    expected = expected.replace(
        'GRANT SELECT, INSERT, UPDATE ON device_platform.patient_practice_selections TO :"api_role";',
        "-- Migration 0043 user/device owner columns inherit these table-level grants.\n"
        'GRANT SELECT, INSERT, UPDATE ON device_platform.device_session_queues, device_platform.practice_sessions TO :"api_role";\n'
        'REVOKE ALL ON device_platform.device_session_queues, device_platform.practice_sessions FROM :"worker_role", :"maintenance_role";\n'
        "-- Devices authenticate through the API; they never receive a PostgreSQL login.\n"
        'GRANT SELECT, INSERT, UPDATE ON device_platform.patient_practice_selections TO :"api_role";',
    )
    expected = expected.replace(
        "COMMIT;",
        """-- Only the API can receive, serve and expire private session archive objects.
REVOKE ALL ON device_platform.session_archives,device_platform.session_archive_items FROM :"worker_role", :"maintenance_role";
GRANT SELECT, INSERT, UPDATE, DELETE ON device_platform.session_archives,device_platform.session_archive_items TO :"api_role";
COMMIT;""",
    )
    assert deployed.split(chr(10), 1)[1] == expected
    assert chr(92) + "ir " not in deployed


def test_current_database_backup_restores_encrypted_credentials_and_api(platform, monkeypatch, tmp_path):
    import os
    import shutil
    import subprocess
    from pathlib import Path
    from types import SimpleNamespace

    from fastapi.testclient import TestClient
    from psycopg import sql
    from pydantic import SecretStr
    from sqlalchemy.engine import make_url

    from pms_api.database.models import Base
    from pms_api.database.session import REVISION
    from pms_api.integrations.vault import CredentialVault
    from pms_api.main import create_app

    p = platform
    token, oid, did, _, _ = cloud_run(p, monkeypatch, Adapter())
    p.call("PATCH", f"/organizations/{oid}/devices/{did}", token, json={"preferred_language": "hi"})
    # Include populated authoring data in the real backup/restore comparison.
    from scenario_samples import example
    from training_contracts.clinical_cases import simplify_case

    document = simplify_case(example("restore_case"))
    p.call(
        "POST",
        f"/organizations/{oid}/training/scenario-drafts",
        token,
        expected=201,
        json={"request_key": str(uuid4()), "code": "restore_case", "document": document},
    )
    owner = make_url(p.dsn)
    restored = "pms_test_restore_" + uuid4().hex[:12]
    admin = make_url(os.environ["PMS_TEST_ADMIN_DSN"])
    native = shutil.which(os.environ.get("PMS_TEST_PSQL", "psql"))
    native = Path(native) if native else Path("C:/Program Files/PostgreSQL/17/bin/psql.exe")
    suffix = ".exe" if os.name == "nt" else ""
    dump, restore = native.with_name("pg_dump" + suffix), native.with_name("pg_restore" + suffix)
    env = {**os.environ, "PGPASSWORD": owner.password or ""}
    args = ["-h", owner.host, "-p", str(owner.port or 5432), "-U", owner.username]
    with psycopg.connect(admin.render_as_string(hide_password=False), autocommit=True) as c:
        c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(restored)))
    try:
        archive = tmp_path / "current-schema.dump"
        subprocess.run(
            [str(dump), *args, "-Fc", "-f", str(archive), owner.database],
            env=env,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [str(restore), *args, "--single-transaction", "--exit-on-error", "-d", restored, str(archive)],
            env=env,
            check=True,
            capture_output=True,
        )
        with psycopg.connect(owner.set(database=restored).render_as_string(hide_password=False)) as c:
            assert c.execute("SELECT version_num FROM public.alembic_version").fetchone()[0] == REVISION
            for table in Base.metadata.tables.values():
                query = sql.SQL(
                    "SELECT md5(coalesce(string_agg(to_jsonb(t)::text,'' ORDER BY to_jsonb(t)::text),'')) FROM device_platform.{} t"
                ).format(sql.Identifier(table.name))
                assert c.execute(query).fetchone()[0] == p.sql(query)[0][0], table.name
            row = c.execute(
                "SELECT credential_owner_id,credential_owner_org,encrypted_credentials,credential_key_id FROM device_platform.runtime_models WHERE encrypted_credentials IS NOT NULL"
            ).fetchone()
            assert CredentialVault(p.settings).decrypt(
                SimpleNamespace(
                    id=row[0], organization_id=row[1], encrypted_credentials=row[2], credential_key_id=row[3]
                )
            ) == {"api_key": "mocked-key"}
        api_url = make_url(p.settings.database_url.get_secret_value()).set(database=restored)
        settings = p.settings.model_copy(
            update={"database_url": SecretStr(api_url.render_as_string(hide_password=False))}
        )
        with TestClient(create_app(settings)) as client:
            assert client.get("/health/ready").status_code == 200
            response = client.get(f"/api/v1/organizations/{oid}/devices/{did}", headers=p.headers(token))
            assert response.status_code == 200 and response.json()["preferred_language"] == "hi"
    finally:
        with psycopg.connect(admin.render_as_string(hide_password=False), autocommit=True) as c:
            c.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(restored)))


def test_nullable_patch_inputs_respect_nonnullable_database_fields(platform, monkeypatch):
    p = platform
    token, oid, _, _, rid = cloud_run(p, monkeypatch, Adapter())
    model = p.review_cloud_model
    settings = p.call("GET", "/platform/settings", token)
    p.call(
        "PUT",
        "/platform/runtime-models/" + model["id"],
        token,
        expected=422,
        json={**cloud_model_body(), "expected_revision": model["revision"], "settings": None},
    )
    for path, body in (
        (f"/organizations/{oid}", {"policy_settings": None}),
        (
            "/platform/settings",
            {"expected_version": settings["configuration_version"], "enabled_providers": None},
        ),
    ):
        p.call("PATCH", path, token, expected=422, json=body)
    assert (
        p.call("GET", "/platform/settings", token)["configuration_version"]
        == settings["configuration_version"]
    )
    current = next(
        row for row in p.call("GET", "/platform/runtime-models", token)["items"] if row["id"] == model["id"]
    )
    assert current["revision"] == model["revision"]
    assert p.call("GET", f"/organizations/{oid}/runs/{rid}", token)["status"] == "queued"
