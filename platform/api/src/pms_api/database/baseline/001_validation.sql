-- Pure row validators. Provider capability, permission, quota and secret validation
-- still belong to the trusted service, using versioned application schemas.
CREATE FUNCTION positive_integer(value jsonb) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
BEGIN
  IF jsonb_typeof(value) IS DISTINCT FROM 'number' OR value::text !~ '^[0-9]+$' THEN
    RETURN false;
  END IF;
  RETURN value::text::numeric > 0;
END $$;

CREATE FUNCTION valid_policy(value jsonb) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE k text; section text; required_keys text[];
BEGIN
  IF jsonb_typeof(value) IS DISTINCT FROM 'object' THEN RETURN false; END IF;
  FOREACH k IN ARRAY ARRAY['offline_authorization_hours','media_retention_hours',
    'result_retention_days','telemetry_retention_days','operational_retention_days','audit_retention_days'] LOOP
    IF NOT device_platform.positive_integer(value->k) THEN RETURN false; END IF;
  END LOOP;
  FOREACH section IN ARRAY ARRAY['capture_limits','usage_limits'] LOOP
    IF jsonb_typeof(value->section) IS DISTINCT FROM 'object' THEN RETURN false; END IF;
    required_keys := CASE section WHEN 'capture_limits' THEN
      ARRAY['max_audio_seconds','max_video_seconds','max_width','max_height','max_fps','max_upload_bytes']
      ELSE ARRAY['max_concurrent_jobs','daily_audio_seconds','daily_video_seconds','daily_tts_characters'] END;
    FOREACH k IN ARRAY required_keys LOOP
      IF NOT device_platform.positive_integer(value->section->k) THEN RETURN false; END IF;
    END LOOP;
  END LOOP;
  RETURN true;
END $$;

CREATE FUNCTION policy_within(candidate jsonb, limits jsonb) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE entry record;
BEGIN
  IF jsonb_typeof(candidate) IS DISTINCT FROM 'object'
    OR jsonb_typeof(limits) IS DISTINCT FROM 'object' THEN RETURN false; END IF;
  FOR entry IN SELECT * FROM jsonb_each(limits) LOOP
    IF NOT candidate ? entry.key THEN RETURN false; END IF;
    IF jsonb_typeof(entry.value) = 'object' THEN
      IF NOT device_platform.policy_within(candidate->entry.key, entry.value) THEN RETURN false; END IF;
    ELSIF jsonb_typeof(candidate->entry.key) IS DISTINCT FROM 'number' THEN RETURN false;
    ELSIF (candidate->>entry.key)::numeric > entry.value::text::numeric THEN RETURN false;
    END IF;
  END LOOP;
  RETURN true;
END $$;

CREATE FUNCTION valid_device_defaults(value jsonb) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE k text;
BEGIN
  IF jsonb_typeof(value) IS DISTINCT FROM 'object' THEN RETURN false; END IF;
  FOREACH k IN ARRAY ARRAY['heartbeat_seconds','offline_after_seconds','active_poll_seconds','telemetry_sample_seconds'] LOOP
    IF NOT device_platform.positive_integer(value->k) THEN RETURN false; END IF;
  END LOOP;
  RETURN (value->>'offline_after_seconds')::numeric > (value->>'heartbeat_seconds')::numeric;
END $$;

CREATE FUNCTION valid_processing_settings(value jsonb, audio_connection uuid,
  video_connection uuid, output_connection uuid) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE sections text[] := ARRAY['audio_input','video','audio_output'];
  bindings uuid[] := ARRAY[audio_connection,video_connection,output_connection];
  part jsonb; i integer;
BEGIN
  IF jsonb_typeof(value) IS DISTINCT FROM 'object' OR value->'schema_version' IS DISTINCT FROM '1'::jsonb THEN RETURN false; END IF;
  FOR i IN 1..3 LOOP
    part := value->sections[i];
    IF jsonb_typeof(part) IS DISTINCT FROM 'object'
      OR jsonb_typeof(part->'enabled') IS DISTINCT FROM 'boolean'
      OR part ? 'connection_id' THEN RETURN false; END IF;
    IF part->'enabled' = 'true'::jsonb THEN
      IF COALESCE(part->>'execution_mode','') NOT IN ('local','cloud')
        OR jsonb_typeof(part->'operation') IS DISTINCT FROM 'string'
        OR jsonb_typeof(part->'engine') IS DISTINCT FROM 'string'
        OR btrim(part->>'operation') = '' OR btrim(part->>'engine') = '' THEN RETURN false; END IF;
      IF (part->>'execution_mode' = 'cloud') <> (bindings[i] IS NOT NULL) THEN RETURN false; END IF;
    ELSIF bindings[i] IS NOT NULL THEN RETURN false;
    END IF;
  END LOOP;
  RETURN true;
END $$;

CREATE FUNCTION valid_metrics(value jsonb) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
DECLARE k text; v jsonb;
BEGIN
  IF jsonb_typeof(value) IS DISTINCT FROM 'object' THEN RETURN false; END IF;
  FOREACH k IN ARRAY ARRAY['cpu_percent','memory_percent','disk_free_bytes','temperature_c',
    'uptime_seconds','capture_fps','dropped_video_frames','audio_overflows','audio_underflows',
    'processing_latency_ms','upload_failures','pending_runs'] LOOP
    v := value->k;
    IF v IS NULL OR v = 'null'::jsonb THEN CONTINUE; END IF;
    IF jsonb_typeof(v) <> 'number' THEN RETURN false; END IF;
    IF k <> 'temperature_c' AND v::text::numeric < 0 THEN RETURN false; END IF;
    IF k IN ('cpu_percent','memory_percent') AND v::text::numeric > 100 THEN RETURN false; END IF;
  END LOOP;
  FOREACH k IN ARRAY ARRAY['camera_status','microphone_status','speaker_status'] LOOP
    v := value->k;
    IF v IS NULL OR v = 'null'::jsonb THEN CONTINUE; END IF;
    IF jsonb_typeof(v) <> 'string' OR value->>k NOT IN ('ready','busy','absent','error','unknown') THEN RETURN false; END IF;
  END LOOP;
  RETURN true;
END $$;
