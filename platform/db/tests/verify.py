"""Validate schema v1 on a disposable database using only Python stdlib and psql.

Requires a PostgreSQL test operator with CREATEDB/CREATEROLE and role-administration
rights. Never installs into a caller-supplied database. Uses PG* environment values
for credentials; do not put passwords in command arguments.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import shutil
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--psql', default='psql')
    parser.add_argument('--pg-dump', default=None)
    parser.add_argument('--pg-restore', default=None)
    parser.add_argument('--host', default=os.environ.get('PGHOST', '127.0.0.1'))
    parser.add_argument('--port', default=os.environ.get('PGPORT', '5432'))
    parser.add_argument('--user', default=os.environ.get('PGUSER', 'postgres'))
    args = parser.parse_args()
    psql_path = Path(shutil.which(args.psql) or args.psql)
    suffix = psql_path.suffix if os.name == 'nt' else ''
    pg_dump = args.pg_dump or str(psql_path.with_name('pg_dump'+suffix))
    pg_restore = args.pg_restore or str(psql_path.with_name('pg_restore'+suffix))
    prefix = 'poc_db_test_' + uuid.uuid4().hex[:12]
    database = prefix
    owner = prefix + '_owner'
    restored_database = prefix + '_restore'
    roles = [prefix + suffix for suffix in ('_api', '_worker', '_retention')]
    env = os.environ.copy()
    env['PGOPTIONS'] = '-c timezone=UTC -c statement_timeout=15000 -c lock_timeout=10000'
    base = [args.psql, '-X', '-q', '-A', '-t', '-h', args.host, '-p', args.port,
            '-U', args.user, '-v', 'ON_ERROR_STOP=1', '-v', 'VERBOSITY=verbose']
    checks = 0

    def run(sql=None, file=None, db=None, variables=None, error=None, role=None):
        nonlocal checks
        cmd = base + ['-d', db or database]
        if role:
            cmd += ['-c', f'SET ROLE "{role}"']
        for key, value in (variables or {}).items():
            cmd += ['-v', f'{key}={value}']
        cmd += ['-f', str(file)] if file else ['-c', sql]
        result = subprocess.run(cmd, text=True, capture_output=True, env=env, timeout=30)
        if error:
            assert result.returncode != 0 and error in result.stderr, (cmd, result.stdout, result.stderr)
        else:
            assert result.returncode == 0, (cmd, result.stdout, result.stderr)
        checks += 1
        return result.stdout.strip()

    created = False
    restored = False
    created_roles = []
    try:
        for script, required in {
            'create-database.sql': {'db_name':database},
            'bootstrap-admin.sql': {'admin_id':'00000000-0000-0000-0000-000000000001',
                'issuer':'https://identity.example.test','subject':'platform-admin',
                'email':'platform@example.test','display_name':'Administrator'},
            'grant-access.sql': dict(zip(('api_role','worker_role','maintenance_role'),roles)) | {'db_name':database},
        }.items():
            for missing in required:
                run(file=ROOT/script, db='postgres', variables={k:v for k,v in required.items() if k != missing}, error='22023')
        print('Every missing-argument preflight returns a failure exit code.', flush=True)
        run(sql=f'CREATE ROLE "{owner}" NOLOGIN', db='postgres')
        created_roles.append(owner)
        run(file=ROOT/'create-database.sql', db='postgres', variables={'db_name': database})
        created = True
        run(sql=f'ALTER DATABASE "{database}" OWNER TO "{owner}"', db='postgres')
        run(file=ROOT/'install.sql', role=owner)
        run(file=ROOT/'install.sql', role=owner, error='42P06')  # Never silently reinstall or overwrite.
        print('Installation as a non-superuser owner and repeat-install rejection passed.', flush=True)
        actual = json.loads(run(sql="""SELECT json_object_agg(table_name, columns) FROM (
          SELECT table_name, json_agg(json_build_array(column_name,data_type,is_nullable) ORDER BY ordinal_position) columns
          FROM information_schema.columns WHERE table_schema='device_platform'
          AND table_name NOT IN ('default_roles','default_role_permissions') GROUP BY table_name
        ) s"""))
        expected = {}
        types = {'uuid':'uuid','text':'text','jsonb':'jsonb','boolean':'boolean',
                 'integer':'integer','bigint':'bigint','smallint':'smallint',
                 'timestamptz':'timestamp with time zone','text[]':'ARRAY'}
        spec = (ROOT/'table-fields.md').read_text(encoding='utf-8-sig')
        for table, body in re.findall(r'## \d+\. `([^`]+)`\n(.*?)(?=\n## |\Z)', spec, re.S):
            expected[table] = [[name,types[dtype],'NO' if required=='Yes' else 'YES']
                for name,dtype,required in re.findall(r'^\| `([^`]+)` \| `([^`]+)` \| (Yes|No) \|',body,re.M)]
        assert actual == expected, 'Database columns/types/nullability differ from field specification'
        catalog = json.loads((ROOT/'default-roles.json').read_text(encoding='utf-8-sig'))['roles']
        actual_grants = json.loads(run(sql="SELECT json_agg(json_build_array(role_code,permission) ORDER BY role_code,permission) FROM device_platform.default_role_permissions"))
        assert actual_grants == sorted([[r['code'], p] for r in catalog for p in r['permissions']])
        actual_roles = json.loads(run(sql="SELECT json_agg(row_to_json(r) ORDER BY code) FROM device_platform.default_roles r"))
        assert actual_roles == sorted([{k:v for k,v in r.items() if k!='permissions'} for r in catalog], key=lambda r:r['code'])
        assert run(sql='SELECT cardinality(enabled_providers) FROM device_platform.platform_settings') == '0'
        assert run(sql="SELECT count(*) FROM pg_constraint WHERE connamespace='device_platform'::regnamespace AND NOT convalidated") == '0'
        assert run(sql="SELECT count(*) FROM pg_index i JOIN pg_class t ON t.oid=i.indrelid WHERE t.relnamespace='device_platform'::regnamespace AND (NOT i.indisvalid OR NOT i.indisready)") == '0'
        print('12 tables / 223 fields and six role definitions match the approved contracts.', flush=True)
        bootstrap = {'admin_id':'00000000-0000-0000-0000-000000000001',
            'issuer':'https://identity.example.test','subject':'platform-admin',
            'email':'platform@example.test','display_name':'Test Administrator'}
        run(file=ROOT/'bootstrap-admin.sql', variables=bootstrap, role=owner)
        run(file=ROOT/'bootstrap-admin.sql', variables=bootstrap, error='Bootstrap already completed')
        run(file=ROOT/'tests/constraints.sql', role=owner)
        print('Bootstrap and constraint/lifecycle assertions passed.', flush=True)
        for role in roles:
            run(sql=f'CREATE ROLE "{role}" NOLOGIN', db='postgres')
            created_roles.append(role)
        grants = dict(zip(('api_role','worker_role','maintenance_role'),roles)) | {'db_name':database}
        run(file=ROOT/'grant-access.sql',variables=grants | {'db_name':'wrong_database'}, role=owner, error='22023')
        run(file=ROOT/'grant-access.sql',variables=grants | {'worker_role':roles[0]}, role=owner, error='22023')
        run(file=ROOT/'grant-access.sql',variables=grants | {'api_role':owner}, role=owner, error='22023')
        run(file=ROOT/'grant-access.sql',variables=grants, role=owner)
        api, worker, retention = roles
        run(sql=f'''SET ROLE "{api}"; BEGIN; INSERT INTO device_platform.organizations(id,name,policy_settings,is_active,suspension_source)
            SELECT gen_random_uuid(),'API test',default_organization_policy,false,'organization' FROM device_platform.platform_settings; ROLLBACK''')
        run(sql=f'SET ROLE "{api}"; DELETE FROM device_platform.activity_events',error='42501')
        run(sql=f'SET ROLE "{api}"; UPDATE device_platform.processing_profile_revisions SET version=2',error='42501')
        run(sql=f'SET ROLE "{worker}"; UPDATE device_platform.processing_runs SET result=result')
        run(sql=f'SET ROLE "{worker}"; UPDATE device_platform.users SET platform_role=NULL',error='42501')
        run(sql=f'SET ROLE "{retention}"; DELETE FROM device_platform.activity_events',error='23514')
        run(sql=f'SET ROLE "{retention}"; UPDATE device_platform.activity_events SET details=details',error='42501')
        run(sql=f'SET ROLE "{retention}"; TRUNCATE device_platform.device_telemetry_samples',error='42501')
        run(sql="""INSERT INTO device_platform.activity_events(id,actor_type,category,event_type,occurred_at,received_at,expires_at)
            VALUES(gen_random_uuid(),'system','operational','test.expired',now()-interval '2 days',now()-interval '2 days',now()-interval '1 day')""")
        run(sql=f"SET ROLE \"{retention}\"; DELETE FROM device_platform.activity_events WHERE event_type='test.expired'")
        assert run(sql="SELECT count(*) FROM device_platform.activity_events WHERE event_type='test.expired'") == '0'
        run(sql="BEGIN ISOLATION LEVEL REPEATABLE READ; UPDATE device_platform.users SET is_active=false",error='25000')
        print('Backend API, worker, and retention privilege boundaries passed.', flush=True)

        # Two committed platform administrators; concurrent demotions must leave one.
        run(sql="""INSERT INTO device_platform.users(id,identity_issuer,identity_subject,display_name,email,platform_role)
          VALUES('00000000-0000-0000-0000-000000000004','https://identity.example.test','second-admin','Second','second@example.test','platform_admin')""")
        first_sql = """BEGIN; UPDATE device_platform.users SET platform_role=NULL
          WHERE id='00000000-0000-0000-0000-000000000001'; SELECT pg_sleep(2); COMMIT;"""
        first_env = env | {'PGAPPNAME':prefix+'_race_a'}
        first = subprocess.Popen(base+['-d',database,'-c',first_sql],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=first_env)
        try:
            deadline = time.monotonic()+8
            while time.monotonic()<deadline:
                sleeping = run(sql=f"SELECT count(*) FROM pg_stat_activity WHERE application_name='{prefix}_race_a' AND wait_event='PgSleep'")
                if sleeping == '1': break
                time.sleep(0.05)
            else: raise AssertionError('First transaction did not reach the controlled lock window')
            run(sql="UPDATE device_platform.users SET platform_role=NULL WHERE id='00000000-0000-0000-0000-000000000004'",error='23514')
            out, err = first.communicate(timeout=15)
            assert first.returncode == 0, (out,err)
        finally:
            if first.poll() is None:
                first.kill()
                first.communicate()
        assert run(sql="SELECT count(*) FROM device_platform.users WHERE platform_role='platform_admin' AND is_active") == '1'
        print('Concurrent last-platform-admin protection passed.', flush=True)
        run(sql="""BEGIN;
            INSERT INTO device_platform.organizations(id,name,policy_settings)
              SELECT '10000000-0000-0000-0000-000000000009','Concurrent org',default_organization_policy FROM device_platform.platform_settings;
            INSERT INTO device_platform.organization_memberships(id,organization_id,user_id,role,is_active,invitation_status,joined_at) VALUES
              ('20000000-0000-0000-0000-000000000008','10000000-0000-0000-0000-000000000009','00000000-0000-0000-0000-000000000001','org_admin',true,'accepted',now()),
              ('20000000-0000-0000-0000-000000000009','10000000-0000-0000-0000-000000000009','00000000-0000-0000-0000-000000000004','org_admin',true,'accepted',now()); COMMIT""")
        first_sql = """BEGIN; UPDATE device_platform.organization_memberships SET role='org_user'
          WHERE id='20000000-0000-0000-0000-000000000008'; SELECT pg_sleep(2); COMMIT;"""
        first = subprocess.Popen(base+['-d',database,'-c',first_sql],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=first_env)
        try:
            deadline = time.monotonic()+8
            while time.monotonic()<deadline:
                if run(sql=f"SELECT count(*) FROM pg_stat_activity WHERE application_name='{prefix}_race_a' AND wait_event='PgSleep'") == '1': break
                time.sleep(0.05)
            else: raise AssertionError('Organization race did not reach the controlled lock window')
            run(sql="UPDATE device_platform.organization_memberships SET role='org_user' WHERE id='20000000-0000-0000-0000-000000000009'",error='23514')
            out, err = first.communicate(timeout=15)
            assert first.returncode == 0, (out,err)
        finally:
            if first.poll() is None:
                first.kill()
                first.communicate()
        assert run(sql="SELECT count(*) FROM device_platform.organization_memberships WHERE role='org_admin' AND is_active") == '1'
        print('Concurrent last-organization-admin protection passed.', flush=True)
        run(file=ROOT/'tests/runtime.sql', variables=grants)
        for table in expected:
            assert int(run(sql=f'SELECT count(*) FROM device_platform.{table}')) > 0, table
        print('Real API/worker/retention writes passed; all twelve tables are populated for backup.', flush=True)
        # Full logical backup/restore must handle the circular FK graph, immutable
        # history, custom CHECK functions, deferred guards and backend grants.
        run(file=ROOT/'create-database.sql', db='postgres', variables={'db_name':restored_database})
        restored = True
        run(sql=f'ALTER DATABASE "{restored_database}" OWNER TO "{owner}"', db='postgres')
        with tempfile.TemporaryDirectory(prefix='poc-db-backup-') as temporary:
            archive = Path(temporary)/'platform.dump'
            connection = ['-h',args.host,'-p',args.port,'-U',args.user]
            dumped = subprocess.run([pg_dump,*connection,'--role',owner,'-Fc','-f',str(archive),database],
                text=True,capture_output=True,env=env,timeout=60)
            assert dumped.returncode == 0, dumped.stderr
            loaded = subprocess.run([pg_restore,*connection,'--role',owner,'--single-transaction',
                '--exit-on-error','-d',restored_database,str(archive)],
                text=True,capture_output=True,env=env,timeout=60)
            assert loaded.returncode == 0, loaded.stderr
        for table in expected:
            fingerprint = f"SELECT md5(COALESCE(string_agg(to_jsonb(t)::text,'' ORDER BY id),'')) FROM device_platform.{table} t"
            assert run(sql=fingerprint) == run(sql=fingerprint,db=restored_database), table
        run(sql="UPDATE device_platform.users SET platform_role=NULL WHERE platform_role='platform_admin'",db=restored_database,error='23514')
        run(sql=f'SET ROLE "{api}"; UPDATE device_platform.processing_profile_revisions SET version=2',db=restored_database,error='42501')
        print('Full pg_dump/pg_restore round trip as a non-superuser owner passed.', flush=True)
        print(f'PASS: {checks} database operations plus field/catalog and SQL assertions.', flush=True)
    finally:
        # These identifiers are generated above, never taken from a supplied target.
        if restored:
            run(sql=f'DROP DATABASE "{restored_database}" WITH (FORCE)', db='postgres')
        if created:
            run(sql=f'DROP DATABASE "{database}" WITH (FORCE)', db='postgres')
        for role in reversed(created_roles):
            run(sql=f'DROP ROLE "{role}"', db='postgres')


if __name__ == '__main__':
    main()
