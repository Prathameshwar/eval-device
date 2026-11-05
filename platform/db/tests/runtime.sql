\set ON_ERROR_STOP on
-- Integration fixture for real writes by the restricted backend roles.
-- This file is called only inside verify.py's disposable database.
SET search_path = device_platform, pg_catalog;
SET ROLE :"api_role";
BEGIN;
INSERT INTO organizations(id,name,policy_settings)
 SELECT '10000000-0000-0000-0000-000000000007','Runtime fixture',default_organization_policy FROM platform_settings;
INSERT INTO organization_memberships(id,organization_id,user_id,role,is_active,invitation_status,joined_at)
 VALUES('20000000-0000-0000-0000-000000000007','10000000-0000-0000-0000-000000000007',
 '00000000-0000-0000-0000-000000000001','org_admin',true,'accepted',now());
INSERT INTO departments(id,organization_id,name)
 VALUES('30000000-0000-0000-0000-000000000007','10000000-0000-0000-0000-000000000007','Research');
INSERT INTO provider_connections(id,organization_id,name,provider,connection_type,auth_mode,settings)
 VALUES('60000000-0000-0000-0000-000000000007','10000000-0000-0000-0000-000000000007',
 'AWS fixture','aws','aws_processing','workload_identity','{"region":"us-east-1"}');
INSERT INTO processing_profiles(id,organization_id,name,draft_settings,draft_audio_input_connection_id)
 VALUES('40000000-0000-0000-0000-000000000007','10000000-0000-0000-0000-000000000007','Audio fixture',
 '{"schema_version":1,"audio_input":{"enabled":true,"operation":"audio.transcribe","execution_mode":"cloud","engine":"aws_transcribe"},"video":{"enabled":false},"audio_output":{"enabled":false}}',
 '60000000-0000-0000-0000-000000000007');
INSERT INTO processing_profile_revisions(id,organization_id,profile_id,version,settings,audio_input_connection_id,published_by)
 SELECT '50000000-0000-0000-0000-000000000007',organization_id,id,1,draft_settings,draft_audio_input_connection_id,
 '00000000-0000-0000-0000-000000000001' FROM processing_profiles WHERE id='40000000-0000-0000-0000-000000000007';
UPDATE processing_profiles SET published_revision_id='50000000-0000-0000-0000-000000000007'
 WHERE id='40000000-0000-0000-0000-000000000007';
UPDATE organizations SET default_profile_id='40000000-0000-0000-0000-000000000007'
 WHERE id='10000000-0000-0000-0000-000000000007';
INSERT INTO devices(id,organization_id,department_id,name,device_type,profile_id)
 VALUES('70000000-0000-0000-0000-000000000007','10000000-0000-0000-0000-000000000007',
 '30000000-0000-0000-0000-000000000007','Laptop fixture','laptop','40000000-0000-0000-0000-000000000007');
UPDATE devices SET enrollment_state='enrolled',enrolled_at=now(),credential_hash='fixture-hash-only',
 applied_profile_revision_id='50000000-0000-0000-0000-000000000007',applied_configuration_hash=repeat('a',64)
 WHERE id='70000000-0000-0000-0000-000000000007';
INSERT INTO processing_runs(id,organization_id,device_id,department_id,profile_revision_id,request_key,
 operation,execution_mode,engine,connection_id,effective_settings,status,next_attempt_at,deadline_at,expires_at)
 VALUES('80000000-0000-0000-0000-000000000007','10000000-0000-0000-0000-000000000007',
 '70000000-0000-0000-0000-000000000007','30000000-0000-0000-0000-000000000007',
 '50000000-0000-0000-0000-000000000007',gen_random_uuid(),'audio.transcribe','cloud','aws_transcribe',
 '60000000-0000-0000-0000-000000000007','{}','queued',now(),now()+interval '1 hour',now()+interval '30 days');
INSERT INTO processing_runs(id,organization_id,device_id,profile_revision_id,request_key,operation,execution_mode,engine,
 effective_settings,status,created_at,completed_at,deadline_at,expires_at,cleanup_status,cleanup_next_attempt_at,result)
 VALUES('80000000-0000-0000-0000-000000000006','10000000-0000-0000-0000-000000000007',
 '70000000-0000-0000-0000-000000000007','50000000-0000-0000-0000-000000000007',gen_random_uuid(),
 'video.motion','local','opencv_motion','{}','failed',now()-interval '3 days',now()-interval '2 days',
 now()-interval '2 days',now()-interval '1 day','failed',now(),'{"expired_content":true}');
INSERT INTO device_telemetry_samples(id,organization_id,device_id,department_id,boot_id,sequence_number,metrics,expires_at)
 VALUES(gen_random_uuid(),'10000000-0000-0000-0000-000000000007','70000000-0000-0000-0000-000000000007',
 '30000000-0000-0000-0000-000000000007',gen_random_uuid(),1,'{"cpu_percent":10}',now()+interval '7 days');
INSERT INTO activity_events(id,organization_id,device_id,actor_type,source_event_id,category,event_type,occurred_at,expires_at)
 VALUES(gen_random_uuid(),'10000000-0000-0000-0000-000000000007','70000000-0000-0000-0000-000000000007',
 'device',gen_random_uuid(),'operational','device.enrolled',now(),now()+interval '30 days');
COMMIT;
RESET ROLE;

SET ROLE :"worker_role";
UPDATE processing_runs SET status='running',started_at=clock_timestamp(),attempt_count=attempt_count+1,
 lease_token='90000000-0000-0000-0000-000000000007',lease_expires_at=clock_timestamp()+interval '1 minute'
 WHERE id='80000000-0000-0000-0000-000000000007' AND status='queued';
UPDATE processing_runs SET status='succeeded',completed_at=clock_timestamp(),result='{"text":"test result"}',
 provider_submission_status='submitted',provider_job_id='fixture-job',lease_token=NULL,lease_expires_at=NULL
 WHERE id='80000000-0000-0000-0000-000000000007' AND lease_token='90000000-0000-0000-0000-000000000007';
UPDATE provider_connections SET last_used_at=clock_timestamp() WHERE id='60000000-0000-0000-0000-000000000007';
RESET ROLE;

SET ROLE :"maintenance_role";
UPDATE processing_runs SET request='{}',result=NULL,error=NULL WHERE id='80000000-0000-0000-0000-000000000006';
RESET ROLE;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM processing_runs WHERE id='80000000-0000-0000-0000-000000000006'
    AND result IS NULL AND cleanup_status='failed') THEN
    RAISE EXCEPTION 'Retention role failed to redact a pending cleanup tombstone';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM processing_runs WHERE id='80000000-0000-0000-0000-000000000007'
    AND status='succeeded' AND attempt_count=1 AND result->>'text'='test result' AND lease_token IS NULL) THEN
    RAISE EXCEPTION 'Worker failed to execute and complete the fixture run';
  END IF;
END $$;
SET ROLE :"worker_role";
UPDATE processing_runs SET cleanup_status='succeeded' WHERE id='80000000-0000-0000-0000-000000000006';
RESET ROLE;
SET ROLE :"maintenance_role";
DELETE FROM processing_runs WHERE id='80000000-0000-0000-0000-000000000006';
RESET ROLE;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM processing_runs WHERE id='80000000-0000-0000-0000-000000000006') THEN
    RAISE EXCEPTION 'Retention role failed to delete the completed cleanup tombstone';
  END IF;
END $$;
