\set ON_ERROR_STOP on
BEGIN;
SET LOCAL search_path = device_platform, pg_catalog;
CREATE FUNCTION pg_temp.assert_true(condition boolean, label text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  IF condition IS DISTINCT FROM true THEN RAISE EXCEPTION 'Assertion failed: %', label; END IF;
END $$;
CREATE FUNCTION pg_temp.reject(statement text, expected_state text) RETURNS void LANGUAGE plpgsql AS $$
DECLARE actual_state text;
BEGIN
  BEGIN
    EXECUTE statement;
    SET CONSTRAINTS ALL IMMEDIATE;
  EXCEPTION WHEN OTHERS THEN
    GET STACKED DIAGNOSTICS actual_state = RETURNED_SQLSTATE;
    IF actual_state = expected_state THEN RETURN; END IF;
    RAISE EXCEPTION 'Expected %, received % for %: %', expected_state, actual_state, statement, SQLERRM;
  END;
  RAISE EXCEPTION 'Expected rejection but succeeded: %', statement;
END $$;

-- Bootstrap is already present. All remaining fixtures roll back at the end.
INSERT INTO users (id,identity_issuer,identity_subject,display_name,email,email_verified) VALUES
 ('00000000-0000-0000-0000-000000000002','https://identity.example.test','org-admin','Org Admin','admin@example.test',true),
 ('00000000-0000-0000-0000-000000000003','https://identity.example.test','trainee','Trainee','trainee@example.test',true);
INSERT INTO organizations (id,name,policy_settings)
 SELECT '10000000-0000-0000-0000-000000000001','Organization A',default_organization_policy FROM platform_settings;
INSERT INTO organization_memberships (id,organization_id,user_id,role,invitation_status,is_active,joined_at)
 VALUES ('20000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000001',
 '00000000-0000-0000-0000-000000000002','org_admin','accepted',true,now());
INSERT INTO organizations (id,name,policy_settings,is_active,suspension_source)
 SELECT '10000000-0000-0000-0000-000000000002','Organization B',default_organization_policy,false,'organization' FROM platform_settings;
INSERT INTO departments (id,organization_id,name) VALUES
 ('30000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000001','Training'),
 ('30000000-0000-0000-0000-000000000002','10000000-0000-0000-0000-000000000002','Other');
INSERT INTO organization_memberships (id,organization_id,user_id,role,department_id,invitation_status,is_active,joined_at)
 VALUES ('20000000-0000-0000-0000-000000000002','10000000-0000-0000-0000-000000000001',
 '00000000-0000-0000-0000-000000000003','org_trainee','30000000-0000-0000-0000-000000000001','accepted',true,now());
SET CONSTRAINTS ALL IMMEDIATE;
SET CONSTRAINTS ALL DEFERRED;

SELECT pg_temp.assert_true((SELECT count(*)=4 FROM default_role_permissions WHERE role_code='org_trainee'),'trainee four read grants');
SELECT pg_temp.assert_true(NOT EXISTS(SELECT 1 FROM default_role_permissions WHERE role_code='platform_admin' AND permission LIKE 'org.%'),'no implied tenant grants');
SELECT pg_temp.reject($q$ UPDATE users SET is_active=false WHERE id='00000000-0000-0000-0000-000000000001' $q$,'23514');
SELECT pg_temp.reject($q$ UPDATE users SET platform_role=NULL WHERE id='00000000-0000-0000-0000-000000000001' $q$,'23514');
SELECT pg_temp.reject($q$ UPDATE users SET is_active=false WHERE id='00000000-0000-0000-0000-000000000002' $q$,'23514');
SELECT pg_temp.reject($q$ UPDATE organization_memberships SET role='org_user' WHERE id='20000000-0000-0000-0000-000000000001' $q$,'23514');
SELECT pg_temp.reject($q$ UPDATE organization_memberships SET role='platform_admin' WHERE role='org_trainee' $q$,'23514');
SELECT pg_temp.reject($q$ UPDATE organization_memberships SET department_id='30000000-0000-0000-0000-000000000001' WHERE role='org_admin' $q$,'23514');
SELECT pg_temp.reject($q$ UPDATE organizations SET is_active=true,suspension_source=NULL WHERE id='10000000-0000-0000-0000-000000000002' $q$,'23514');
SELECT pg_temp.reject($q$ INSERT INTO organizations (id,name,policy_settings) SELECT gen_random_uuid(),'Missing admin',default_organization_policy FROM platform_settings $q$,'23514');
SELECT pg_temp.reject($q$ INSERT INTO departments (id,organization_id,name) VALUES(gen_random_uuid(),'10000000-0000-0000-0000-000000000001',' training ') $q$,'23505');
SELECT pg_temp.reject($q$ INSERT INTO organization_memberships (id,organization_id,role) VALUES(gen_random_uuid(),'10000000-0000-0000-0000-000000000001','org_user') $q$,'23514');
INSERT INTO organization_memberships(id,organization_id,role,invited_email,invitation_token_hash,invitation_expires_at)
 VALUES('20000000-0000-0000-0000-000000000003','10000000-0000-0000-0000-000000000001','org_user','invite@example.test','test-hash',now()+interval '1 day');
SELECT pg_temp.reject($q$ INSERT INTO organization_memberships(id,organization_id,role,invited_email,invitation_token_hash,invitation_expires_at)
 VALUES(gen_random_uuid(),'10000000-0000-0000-0000-000000000001','org_user','INVITE@example.test','test-hash-2',now()+interval '1 day') $q$,'23505');
UPDATE organization_memberships SET invitation_status='expired',invitation_token_hash=NULL WHERE id='20000000-0000-0000-0000-000000000003';

INSERT INTO processing_profiles (id,organization_id,name) VALUES
 ('40000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000001','Local'),
 ('40000000-0000-0000-0000-000000000002','10000000-0000-0000-0000-000000000001','Other profile');
INSERT INTO processing_profile_revisions(id,organization_id,profile_id,version,settings,published_by)
 SELECT '50000000-0000-0000-0000-000000000001',organization_id,id,1,draft_settings,'00000000-0000-0000-0000-000000000002'
 FROM processing_profiles WHERE id='40000000-0000-0000-0000-000000000001';
UPDATE processing_profiles SET published_revision_id='50000000-0000-0000-0000-000000000001' WHERE id='40000000-0000-0000-0000-000000000001';
UPDATE organizations SET default_profile_id='40000000-0000-0000-0000-000000000001' WHERE id='10000000-0000-0000-0000-000000000001';
SELECT pg_temp.reject($q$ UPDATE processing_profiles SET published_revision_id='50000000-0000-0000-0000-000000000001' WHERE id='40000000-0000-0000-0000-000000000002' $q$,'23503');
SELECT pg_temp.reject($q$ UPDATE organizations SET default_profile_id='40000000-0000-0000-0000-000000000001' WHERE id='10000000-0000-0000-0000-000000000002' $q$,'23503');
SELECT pg_temp.reject($q$ UPDATE processing_profile_revisions SET change_note='changed' $q$,'23514');
SELECT pg_temp.reject($q$ DELETE FROM processing_profile_revisions $q$,'23514');
SELECT pg_temp.reject($q$ UPDATE processing_profiles SET draft_settings=jsonb_set(draft_settings,'{video}','{"enabled":true,"operation":"video.labels","execution_mode":"cloud","engine":"aws_rekognition"}') WHERE id='40000000-0000-0000-0000-000000000001' $q$,'23514');
INSERT INTO provider_connections(id,organization_id,name,provider,connection_type,auth_mode,settings,validation_results,last_validated_at)
 VALUES('60000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000001','AWS','aws','aws_processing','workload_identity','{"region":"us-east-1"}','{"audio.transcribe":{"status":"valid","configuration_version":1}}',now());
UPDATE provider_connections SET settings='{"region":"us-west-2"}' WHERE id='60000000-0000-0000-0000-000000000001';
SELECT pg_temp.assert_true((SELECT configuration_version=2 AND validation_results='{}' AND last_validated_at IS NULL FROM provider_connections LIMIT 1),'connection validation reset');
SELECT pg_temp.reject($q$ UPDATE provider_connections SET auth_mode='api_key' $q$,'23514');
SELECT pg_temp.reject($q$ UPDATE provider_connections SET auth_mode='access_key' $q$,'23514');
SELECT pg_temp.reject($q$ UPDATE provider_connections SET settings='{"secret_access_key":"do-not-store"}' $q$,'23514');

INSERT INTO devices(id,organization_id,department_id,name,device_type)
 VALUES('70000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000001','30000000-0000-0000-0000-000000000001','Laptop','laptop');
SELECT pg_temp.reject($q$ UPDATE devices SET department_id='30000000-0000-0000-0000-000000000002' $q$,'23503');
SELECT pg_temp.reject($q$ UPDATE devices SET organization_id='10000000-0000-0000-0000-000000000002' $q$,'23514');
SELECT pg_temp.reject($q$ UPDATE devices SET role='org_admin' $q$,'23514');
SELECT pg_temp.reject($q$ UPDATE devices SET applied_configuration_hash='wrong' $q$,'23514');
SELECT pg_temp.reject($q$ UPDATE devices SET enrollment_token_hash='token-hash' $q$,'23514');
UPDATE devices SET enrollment_state='enrolled',enrolled_at=now(),credential_hash='first-hash';
SELECT pg_temp.assert_true((SELECT credential_version=1 AND credential_issued_at IS NOT NULL FROM devices LIMIT 1),'credential issued');
UPDATE devices SET credential_hash='rotated-hash';
UPDATE devices SET credential_hash=NULL;
SELECT pg_temp.assert_true((SELECT credential_version=3 AND credential_revoked_at IS NOT NULL FROM devices LIMIT 1),'credential revoked');

INSERT INTO processing_runs(id,organization_id,device_id,department_id,profile_revision_id,request_key,operation,execution_mode,engine,effective_settings,status,next_attempt_at,deadline_at,expires_at)
 VALUES('80000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000001','70000000-0000-0000-0000-000000000001','30000000-0000-0000-0000-000000000001','50000000-0000-0000-0000-000000000001',
 '90000000-0000-0000-0000-000000000001','video.motion','local','opencv_motion','{}','queued',now(),now()+interval '1 hour',now()+interval '30 days');
SELECT pg_temp.reject($q$ UPDATE processing_runs SET status='succeeded' $q$,'23514');
SELECT pg_temp.reject($q$ UPDATE processing_runs SET lease_token=gen_random_uuid() $q$,'23514');
SELECT pg_temp.reject($q$ UPDATE processing_runs SET next_attempt_at=NULL $q$,'23514');
SELECT pg_temp.reject($q$ UPDATE processing_runs SET request_key=gen_random_uuid() $q$,'23514');
SELECT pg_temp.reject($q$ UPDATE processing_runs SET media_manifest='[{"key":"private-object"}]' $q$,'23514');
SELECT pg_temp.reject($q$ DELETE FROM processing_runs $q$,'23514');
UPDATE processing_runs SET status='succeeded',completed_at=clock_timestamp(),result='{"motion":true}';
UPDATE devices SET department_id=NULL;
SELECT pg_temp.assert_true((SELECT department_id='30000000-0000-0000-0000-000000000001'::uuid FROM processing_runs LIMIT 1),'historical department preserved');

INSERT INTO device_telemetry_samples(id,organization_id,device_id,boot_id,sequence_number,metrics,expires_at)
 VALUES('a0000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000001','70000000-0000-0000-0000-000000000001','b0000000-0000-0000-0000-000000000001',0,'{"cpu_percent":25,"temperature_c":-5,"memory_percent":null}',now()+interval '7 days');
SELECT pg_temp.reject($q$ UPDATE device_telemetry_samples SET metrics='{}' $q$,'23514');
SELECT pg_temp.reject($q$ DELETE FROM device_telemetry_samples $q$,'23514');
SELECT pg_temp.reject($q$ INSERT INTO device_telemetry_samples(id,organization_id,device_id,boot_id,sequence_number,metrics,expires_at)
 SELECT gen_random_uuid(),organization_id,device_id,boot_id,sequence_number,metrics,expires_at FROM device_telemetry_samples $q$,'23505');
SELECT pg_temp.reject($q$ INSERT INTO device_telemetry_samples(id,organization_id,device_id,boot_id,sequence_number,metrics,expires_at)
 SELECT gen_random_uuid(),organization_id,device_id,boot_id,1,'{"cpu_percent":101}',expires_at FROM device_telemetry_samples $q$,'23514');
SELECT pg_temp.reject($q$ INSERT INTO activity_events(id,device_id,actor_type,category,event_type,occurred_at,expires_at)
 VALUES(gen_random_uuid(),'70000000-0000-0000-0000-000000000001','system','operational','test',now(),now()+interval '1 day') $q$,'23514');
SELECT pg_temp.reject($q$ INSERT INTO activity_events(id,organization_id,device_id,source_event_id,actor_type,category,event_type,occurred_at,expires_at)
 VALUES(gen_random_uuid(),'10000000-0000-0000-0000-000000000001','70000000-0000-0000-0000-000000000001',gen_random_uuid(),'device','audit','test',now(),now()+interval '1 day') $q$,'23514');
SELECT pg_temp.reject($q$ UPDATE activity_events SET details='{}' $q$,'23514');
SELECT pg_temp.reject($q$ DELETE FROM platform_settings $q$,'23514');
SELECT pg_temp.reject($q$ UPDATE platform_settings SET display_name='Changed' $q$,'23514');
SELECT pg_temp.reject($q$ UPDATE platform_settings SET updated_by='00000000-0000-0000-0000-000000000001',policy_limits='{}' $q$,'23514');
SELECT pg_temp.reject($q$ UPDATE platform_settings SET updated_by='00000000-0000-0000-0000-000000000001',enabled_providers=ARRAY['unknown'] $q$,'23514');
UPDATE platform_settings SET updated_by='00000000-0000-0000-0000-000000000001',display_name='Verified';
SELECT pg_temp.assert_true((SELECT configuration_version=2 FROM platform_settings),'settings version maintained');
-- Values must fail as ordinary row constraints, before oversized B-tree entries.
SELECT pg_temp.reject($q$ INSERT INTO users(id,identity_issuer,identity_subject,display_name,email)
 SELECT gen_random_uuid(),(SELECT string_agg(md5(g::text),'') FROM generate_series(1,64) g),
 (SELECT string_agg(md5(g::text),'') FROM generate_series(65,96) g),'Long identity','long@example.test' $q$,'23514');
SELECT pg_temp.reject($q$ UPDATE departments SET name=repeat(chr(20013),400) $q$,'23514');
SELECT pg_temp.reject($q$ UPDATE users SET email=repeat(chr(20013),400) $q$,'23514');
SELECT pg_temp.reject($q$ UPDATE devices SET credential_hash=repeat(chr(20013),400),credential_revoked_at=NULL $q$,'23514');
-- A supported UTF-8 indexed value remains valid.
INSERT INTO departments(id,organization_id,name)
 VALUES(gen_random_uuid(),'10000000-0000-0000-0000-000000000001',repeat(chr(20013),300));

-- Valid malformed-policy rejection and expired-history cleanup paths.
SELECT pg_temp.reject($q$ UPDATE platform_settings SET updated_by='00000000-0000-0000-0000-000000000001',
 default_organization_policy=jsonb_set(default_organization_policy,'{media_retention_hours}','"invalid"') $q$,'23514');
SELECT pg_temp.reject($q$ INSERT INTO processing_runs(id,organization_id,device_id,profile_revision_id,request_key,operation,execution_mode,engine,effective_settings,status,next_attempt_at,deadline_at,expires_at)
 SELECT gen_random_uuid(),organization_id,device_id,profile_revision_id,request_key,operation,execution_mode,engine,effective_settings,'queued',now(),deadline_at,expires_at FROM processing_runs $q$,'23505');
INSERT INTO activity_events(id,actor_type,category,event_type,occurred_at,received_at,expires_at)
 VALUES(gen_random_uuid(),'system','operational','test.expired',now()-interval '2 days',now()-interval '2 days',now()-interval '1 day');
DELETE FROM activity_events WHERE event_type='test.expired';
SELECT pg_temp.assert_true(NOT EXISTS(SELECT 1 FROM activity_events WHERE event_type='test.expired'),'expired history deleted');
INSERT INTO processing_runs(id,organization_id,device_id,profile_revision_id,request_key,operation,execution_mode,engine,effective_settings,status,created_at,completed_at,deadline_at,expires_at,cleanup_status,cleanup_next_attempt_at,result)
 SELECT '80000000-0000-0000-0000-000000000002',organization_id,device_id,profile_revision_id,gen_random_uuid(),operation,execution_mode,engine,effective_settings,
 'failed',now()-interval '3 days',now()-interval '2 days',now()-interval '2 days',now()-interval '1 day','failed',now(),'{}' FROM processing_runs;
SELECT pg_temp.reject($q$ DELETE FROM processing_runs WHERE id='80000000-0000-0000-0000-000000000002' $q$,'23514');
UPDATE processing_runs SET request='{}',result=NULL,error=NULL WHERE id='80000000-0000-0000-0000-000000000002';
SELECT pg_temp.assert_true((SELECT result IS NULL FROM processing_runs WHERE id='80000000-0000-0000-0000-000000000002'),'cleanup tombstone redaction');
UPDATE processing_runs SET cleanup_status='succeeded' WHERE id='80000000-0000-0000-0000-000000000002';
DELETE FROM processing_runs WHERE id='80000000-0000-0000-0000-000000000002';
-- Atomic admin replacement succeeds even when the old membership changes first.
UPDATE organization_memberships SET role='org_user' WHERE id='20000000-0000-0000-0000-000000000001';
UPDATE organization_memberships SET role='org_admin',department_id=NULL WHERE id='20000000-0000-0000-0000-000000000002';
SET CONSTRAINTS ALL IMMEDIATE;
ROLLBACK;
\echo 'Constraint and lifecycle assertions passed.'
