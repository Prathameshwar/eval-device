-- Conservative starting limits for laptop/Pi development. Review these deployment
-- values before production. No provider credentials or sample tenants are seeded.
INSERT INTO platform_settings (
  id, default_organization_policy, policy_limits, device_defaults
) VALUES (
  1,
  '{
    "offline_authorization_hours":24,
    "media_retention_hours":24,
    "result_retention_days":30,
    "telemetry_retention_days":7,
    "operational_retention_days":30,
    "audit_retention_days":90,
    "capture_limits":{
      "max_audio_seconds":60,"max_video_seconds":15,
      "max_width":1280,"max_height":720,"max_fps":15,"max_upload_bytes":26214400
    },
    "usage_limits":{
      "max_concurrent_jobs":2,"daily_audio_seconds":1800,
      "daily_video_seconds":600,"daily_tts_characters":10000
    }
  }'::jsonb,
  '{
    "offline_authorization_hours":24,
    "media_retention_hours":72,
    "result_retention_days":90,
    "telemetry_retention_days":30,
    "operational_retention_days":90,
    "audit_retention_days":365,
    "capture_limits":{
      "max_audio_seconds":300,"max_video_seconds":60,
      "max_width":1920,"max_height":1080,"max_fps":30,"max_upload_bytes":104857600
    },
    "usage_limits":{
      "max_concurrent_jobs":4,"daily_audio_seconds":7200,
      "daily_video_seconds":1800,"daily_tts_characters":50000
    }
  }'::jsonb,
  '{"heartbeat_seconds":60,"offline_after_seconds":180,"active_poll_seconds":5,"telemetry_sample_seconds":300}'::jsonb
);
