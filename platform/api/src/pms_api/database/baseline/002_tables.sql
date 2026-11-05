-- Schema v1: twelve application tables; UUIDs are supplied by the service.

CREATE TABLE organizations (
    id uuid NOT NULL PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid,
    is_active boolean NOT NULL DEFAULT true,
    status_changed_at timestamptz NOT NULL DEFAULT now(),
    status_changed_by uuid,
    status_reason text,
    CHECK (status_reason IS NULL OR (char_length(btrim(status_reason)) > 0 AND char_length(status_reason) <= 4000)),
    name text NOT NULL,
    CHECK (name IS NULL OR (char_length(btrim(name)) > 0 AND char_length(name) <= 1024)),
    description text,
    CHECK (description IS NULL OR (char_length(btrim(description)) > 0 AND char_length(description) <= 4000)),
    contact_name text,
    CHECK (contact_name IS NULL OR (char_length(btrim(contact_name)) > 0 AND char_length(contact_name) <= 1024)),
    contact_email text,
    CHECK (contact_email IS NULL OR (char_length(btrim(contact_email)) > 0 AND char_length(contact_email) <= 1024)),
    contact_phone text,
    CHECK (contact_phone IS NULL OR (char_length(btrim(contact_phone)) > 0 AND char_length(contact_phone) <= 1024)),
    default_profile_id uuid,
    policy_settings jsonb NOT NULL,
    CHECK (policy_settings IS NULL OR (jsonb_typeof(policy_settings) = 'object' AND octet_length(policy_settings::text) <= 65536)),
    suspension_source text,
    CHECK (suspension_source IS NULL OR (char_length(btrim(suspension_source)) > 0 AND char_length(suspension_source) <= 1024)),
    last_activity_at timestamptz,
    CHECK ((is_active AND suspension_source IS NULL) OR (NOT is_active AND suspension_source IS NOT NULL AND suspension_source IN ('organization','platform'))),
    CHECK (valid_policy(policy_settings))
);

CREATE TABLE departments (
    id uuid NOT NULL PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid,
    is_active boolean NOT NULL DEFAULT true,
    status_changed_at timestamptz NOT NULL DEFAULT now(),
    status_changed_by uuid,
    status_reason text,
    CHECK (status_reason IS NULL OR (char_length(btrim(status_reason)) > 0 AND char_length(status_reason) <= 4000)),
    organization_id uuid NOT NULL,
    name text NOT NULL,
    CHECK (name IS NULL OR (char_length(btrim(name)) > 0 AND char_length(name) <= 1024)),
    description text,
    CHECK (description IS NULL OR (char_length(btrim(description)) > 0 AND char_length(description) <= 4000)),
    UNIQUE (organization_id, id)
);

CREATE TABLE users (
    id uuid NOT NULL PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid,
    is_active boolean NOT NULL DEFAULT true,
    status_changed_at timestamptz NOT NULL DEFAULT now(),
    status_changed_by uuid,
    status_reason text,
    CHECK (status_reason IS NULL OR (char_length(btrim(status_reason)) > 0 AND char_length(status_reason) <= 4000)),
    identity_issuer text NOT NULL,
    CHECK (identity_issuer IS NULL OR (char_length(btrim(identity_issuer)) > 0 AND char_length(identity_issuer) <= 2048)),
    identity_subject text NOT NULL,
    CHECK (identity_subject IS NULL OR (char_length(btrim(identity_subject)) > 0 AND char_length(identity_subject) <= 1024)),
    display_name text NOT NULL,
    CHECK (display_name IS NULL OR (char_length(btrim(display_name)) > 0 AND char_length(display_name) <= 1024)),
    email text NOT NULL,
    CHECK (email IS NULL OR (char_length(btrim(email)) > 0 AND char_length(email) <= 1024)),
    email_verified boolean NOT NULL DEFAULT false,
    phone text,
    CHECK (phone IS NULL OR (char_length(btrim(phone)) > 0 AND char_length(phone) <= 1024)),
    platform_role text,
    CHECK (platform_role IS NULL OR (char_length(btrim(platform_role)) > 0 AND char_length(platform_role) <= 1024)),
    last_login_at timestamptz,
    last_activity_at timestamptz,
    UNIQUE (identity_issuer, identity_subject),
    CHECK (platform_role IS NULL OR platform_role = 'platform_admin')
);

CREATE TABLE organization_memberships (
    id uuid NOT NULL PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid,
    is_active boolean NOT NULL DEFAULT false,
    status_changed_at timestamptz NOT NULL DEFAULT now(),
    status_changed_by uuid,
    status_reason text,
    CHECK (status_reason IS NULL OR (char_length(btrim(status_reason)) > 0 AND char_length(status_reason) <= 4000)),
    organization_id uuid NOT NULL,
    user_id uuid,
    role text NOT NULL,
    CHECK (role IS NULL OR (char_length(btrim(role)) > 0 AND char_length(role) <= 1024)),
    department_id uuid,
    invitation_status text NOT NULL DEFAULT 'pending',
    CHECK (invitation_status IS NULL OR (char_length(btrim(invitation_status)) > 0 AND char_length(invitation_status) <= 1024)),
    invited_email text,
    CHECK (invited_email IS NULL OR (char_length(btrim(invited_email)) > 0 AND char_length(invited_email) <= 1024)),
    invitation_token_hash text,
    CHECK (invitation_token_hash IS NULL OR (char_length(btrim(invitation_token_hash)) > 0 AND char_length(invitation_token_hash) <= 1024)),
    invitation_expires_at timestamptz,
    joined_at timestamptz,
    CHECK (role IN ('org_admin','org_user','org_read_only','org_trainee')),
    CHECK (role <> 'org_admin' OR department_id IS NULL),
    CHECK (invitation_status IN ('pending','accepted','expired','revoked')),
    CHECK (NOT is_active OR invitation_status = 'accepted'),
    CHECK (invitation_status <> 'accepted' OR (user_id IS NOT NULL AND joined_at IS NOT NULL)),
    CHECK ((invitation_status = 'pending' AND invited_email IS NOT NULL AND invitation_token_hash IS NOT NULL AND invitation_expires_at IS NOT NULL AND NOT is_active) OR (invitation_status <> 'pending' AND invitation_token_hash IS NULL)),
    UNIQUE (invitation_token_hash)
);

CREATE TABLE devices (
    id uuid NOT NULL PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid,
    is_active boolean NOT NULL DEFAULT true,
    status_changed_at timestamptz NOT NULL DEFAULT now(),
    status_changed_by uuid,
    status_reason text,
    CHECK (status_reason IS NULL OR (char_length(btrim(status_reason)) > 0 AND char_length(status_reason) <= 4000)),
    organization_id uuid NOT NULL,
    department_id uuid,
    name text NOT NULL,
    CHECK (name IS NULL OR (char_length(btrim(name)) > 0 AND char_length(name) <= 1024)),
    device_type text NOT NULL,
    CHECK (device_type IS NULL OR (char_length(btrim(device_type)) > 0 AND char_length(device_type) <= 1024)),
    role text NOT NULL DEFAULT 'org_device',
    CHECK (role IS NULL OR (char_length(btrim(role)) > 0 AND char_length(role) <= 1024)),
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (details IS NULL OR (jsonb_typeof(details) = 'object' AND octet_length(details::text) <= 65536)),
    location text,
    CHECK (location IS NULL OR (char_length(btrim(location)) > 0 AND char_length(location) <= 1024)),
    contact_name text,
    CHECK (contact_name IS NULL OR (char_length(btrim(contact_name)) > 0 AND char_length(contact_name) <= 1024)),
    contact_email text,
    CHECK (contact_email IS NULL OR (char_length(btrim(contact_email)) > 0 AND char_length(contact_email) <= 1024)),
    contact_phone text,
    CHECK (contact_phone IS NULL OR (char_length(btrim(contact_phone)) > 0 AND char_length(contact_phone) <= 1024)),
    profile_id uuid,
    applied_profile_revision_id uuid,
    applied_configuration_hash text,
    CHECK (applied_configuration_hash IS NULL OR (char_length(btrim(applied_configuration_hash)) > 0 AND char_length(applied_configuration_hash) <= 1024)),
    config_error jsonb,
    CHECK (config_error IS NULL OR (jsonb_typeof(config_error) = 'object' AND octet_length(config_error::text) <= 65536)),
    capabilities jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (capabilities IS NULL OR (jsonb_typeof(capabilities) = 'object' AND octet_length(capabilities::text) <= 65536)),
    enrollment_state text NOT NULL DEFAULT 'pending',
    CHECK (enrollment_state IS NULL OR (char_length(btrim(enrollment_state)) > 0 AND char_length(enrollment_state) <= 1024)),
    enrollment_token_hash text,
    CHECK (enrollment_token_hash IS NULL OR (char_length(btrim(enrollment_token_hash)) > 0 AND char_length(enrollment_token_hash) <= 1024)),
    enrollment_expires_at timestamptz,
    enrollment_attempt_count integer NOT NULL DEFAULT 0,
    credential_hash text,
    CHECK (credential_hash IS NULL OR (char_length(btrim(credential_hash)) > 0 AND char_length(credential_hash) <= 1024)),
    credential_version integer NOT NULL DEFAULT 0,
    credential_issued_at timestamptz,
    credential_revoked_at timestamptz,
    enrolled_at timestamptz,
    last_seen_at timestamptz,
    last_activity_at timestamptz,
    offline_authorized_until timestamptz,
    last_telemetry_at timestamptz,
    latest_health jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (latest_health IS NULL OR (jsonb_typeof(latest_health) = 'object' AND octet_length(latest_health::text) <= 65536)),
    UNIQUE (organization_id, id),
    CHECK (device_type IN ('laptop','raspberry_pi','other')),
    CHECK (role = 'org_device'),
    CHECK (enrollment_state IN ('pending','enrolled','retired')),
    CHECK ((enrollment_token_hash IS NULL) = (enrollment_expires_at IS NULL)),
    CHECK (enrollment_state = 'pending' OR enrollment_token_hash IS NULL),
    CHECK (enrollment_attempt_count >= 0 AND credential_version >= 0),
    CHECK (applied_configuration_hash IS NULL OR applied_configuration_hash ~ '^[0-9a-f]{64}$'),
    CHECK (enrollment_state <> 'enrolled' OR (enrolled_at IS NOT NULL AND credential_issued_at IS NOT NULL AND credential_version > 0)),
    CHECK (credential_hash IS NULL OR (enrollment_state = 'enrolled' AND credential_issued_at IS NOT NULL AND credential_revoked_at IS NULL AND credential_version > 0)),
    CHECK (enrollment_state <> 'retired' OR credential_hash IS NULL),
    CHECK (credential_revoked_at IS NULL OR credential_hash IS NULL),
    CHECK (NOT latest_health ? 'metrics' OR valid_metrics(latest_health->'metrics')),
    UNIQUE (enrollment_token_hash),
    UNIQUE (credential_hash)
);

CREATE TABLE provider_connections (
    id uuid NOT NULL PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid,
    is_active boolean NOT NULL DEFAULT true,
    status_changed_at timestamptz NOT NULL DEFAULT now(),
    status_changed_by uuid,
    status_reason text,
    CHECK (status_reason IS NULL OR (char_length(btrim(status_reason)) > 0 AND char_length(status_reason) <= 4000)),
    organization_id uuid NOT NULL,
    name text NOT NULL,
    CHECK (name IS NULL OR (char_length(btrim(name)) > 0 AND char_length(name) <= 1024)),
    description text,
    CHECK (description IS NULL OR (char_length(btrim(description)) > 0 AND char_length(description) <= 4000)),
    provider text NOT NULL,
    CHECK (provider IS NULL OR (char_length(btrim(provider)) > 0 AND char_length(provider) <= 1024)),
    connection_type text NOT NULL,
    CHECK (connection_type IS NULL OR (char_length(btrim(connection_type)) > 0 AND char_length(connection_type) <= 1024)),
    auth_mode text NOT NULL,
    CHECK (auth_mode IS NULL OR (char_length(btrim(auth_mode)) > 0 AND char_length(auth_mode) <= 1024)),
    settings jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (settings IS NULL OR (jsonb_typeof(settings) = 'object' AND octet_length(settings::text) <= 262144)),
    secret_ref text,
    CHECK (secret_ref IS NULL OR (char_length(btrim(secret_ref)) > 0 AND char_length(secret_ref) <= 2048)),
    configuration_version integer NOT NULL DEFAULT 1,
    validation_results jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (validation_results IS NULL OR (jsonb_typeof(validation_results) = 'object' AND octet_length(validation_results::text) <= 65536)),
    last_validated_at timestamptz,
    last_used_at timestamptz,
    UNIQUE (organization_id, id),
    CHECK ((provider = 'aws' AND connection_type = 'aws_processing' AND auth_mode IN ('workload_identity','assume_role','access_key')) OR (provider = 'azure' AND connection_type = 'azure_speech' AND auth_mode IN ('workload_identity','api_key','service_principal')) OR (provider = 'azure' AND connection_type = 'azure_video_indexer' AND auth_mode IN ('workload_identity','service_principal'))),
    CHECK (auth_mode NOT IN ('access_key','api_key','service_principal') OR secret_ref IS NOT NULL),
    CHECK (configuration_version > 0),
    CHECK (NOT settings ?| ARRAY['password','api_key','access_key_id','secret_access_key','client_secret','access_token','refresh_token','connection_string'])
);

CREATE TABLE processing_profiles (
    id uuid NOT NULL PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid,
    is_active boolean NOT NULL DEFAULT true,
    status_changed_at timestamptz NOT NULL DEFAULT now(),
    status_changed_by uuid,
    status_reason text,
    CHECK (status_reason IS NULL OR (char_length(btrim(status_reason)) > 0 AND char_length(status_reason) <= 4000)),
    organization_id uuid NOT NULL,
    name text NOT NULL,
    CHECK (name IS NULL OR (char_length(btrim(name)) > 0 AND char_length(name) <= 1024)),
    description text,
    CHECK (description IS NULL OR (char_length(btrim(description)) > 0 AND char_length(description) <= 4000)),
    draft_settings jsonb NOT NULL DEFAULT '{"schema_version":1,"audio_input":{"enabled":false},"video":{"enabled":false},"audio_output":{"enabled":false}}'::jsonb,
    CHECK (draft_settings IS NULL OR (jsonb_typeof(draft_settings) = 'object' AND octet_length(draft_settings::text) <= 262144)),
    draft_audio_input_connection_id uuid,
    draft_video_connection_id uuid,
    draft_audio_output_connection_id uuid,
    published_revision_id uuid,
    UNIQUE (organization_id, id),
    CHECK (valid_processing_settings(draft_settings, draft_audio_input_connection_id, draft_video_connection_id, draft_audio_output_connection_id))
);

CREATE TABLE processing_profile_revisions (
    id uuid NOT NULL PRIMARY KEY,
    organization_id uuid NOT NULL,
    profile_id uuid NOT NULL,
    version integer NOT NULL,
    settings jsonb NOT NULL,
    CHECK (settings IS NULL OR (jsonb_typeof(settings) = 'object' AND octet_length(settings::text) <= 262144)),
    audio_input_connection_id uuid,
    video_connection_id uuid,
    audio_output_connection_id uuid,
    published_at timestamptz NOT NULL DEFAULT now(),
    published_by uuid NOT NULL,
    change_note text,
    CHECK (change_note IS NULL OR (char_length(btrim(change_note)) > 0 AND char_length(change_note) <= 4000)),
    UNIQUE (organization_id, id),
    UNIQUE (organization_id, profile_id, version),
    UNIQUE (organization_id, profile_id, id),
    CHECK (version > 0),
    CHECK (valid_processing_settings(settings, audio_input_connection_id, video_connection_id, audio_output_connection_id))
);

CREATE TABLE processing_runs (
    id uuid NOT NULL PRIMARY KEY,
    organization_id uuid NOT NULL,
    device_id uuid NOT NULL,
    department_id uuid,
    profile_revision_id uuid NOT NULL,
    requested_by uuid,
    capture_id uuid,
    request_key uuid NOT NULL,
    operation text NOT NULL,
    CHECK (operation IS NULL OR (char_length(btrim(operation)) > 0 AND char_length(operation) <= 1024)),
    execution_mode text NOT NULL,
    CHECK (execution_mode IS NULL OR (char_length(btrim(execution_mode)) > 0 AND char_length(execution_mode) <= 1024)),
    engine text NOT NULL,
    CHECK (engine IS NULL OR (char_length(btrim(engine)) > 0 AND char_length(engine) <= 1024)),
    connection_id uuid,
    effective_settings jsonb NOT NULL,
    CHECK (effective_settings IS NULL OR (jsonb_typeof(effective_settings) = 'object' AND octet_length(effective_settings::text) <= 262144)),
    request jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (request IS NULL OR (jsonb_typeof(request) = 'object' AND octet_length(request::text) <= 262144)),
    status text NOT NULL,
    CHECK (status IS NULL OR (char_length(btrim(status)) > 0 AND char_length(status) <= 1024)),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    captured_at timestamptz,
    started_at timestamptz,
    completed_at timestamptz,
    deadline_at timestamptz NOT NULL,
    attempt_count integer NOT NULL DEFAULT 0,
    next_attempt_at timestamptz,
    lease_token uuid,
    lease_expires_at timestamptz,
    provider_submission_status text NOT NULL DEFAULT 'not_submitted',
    CHECK (provider_submission_status IS NULL OR (char_length(btrim(provider_submission_status)) > 0 AND char_length(provider_submission_status) <= 1024)),
    provider_job_id text,
    CHECK (provider_job_id IS NULL OR (char_length(btrim(provider_job_id)) > 0 AND char_length(provider_job_id) <= 1024)),
    result jsonb,
    CHECK (result IS NULL OR (jsonb_typeof(result) = 'object' AND octet_length(result::text) <= 1048576)),
    error jsonb,
    CHECK (error IS NULL OR (jsonb_typeof(error) = 'object' AND octet_length(error::text) <= 65536)),
    usage jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (usage IS NULL OR (jsonb_typeof(usage) = 'object' AND octet_length(usage::text) <= 65536)),
    media_manifest jsonb NOT NULL DEFAULT '[]'::jsonb,
    CHECK (media_manifest IS NULL OR (jsonb_typeof(media_manifest) = 'array' AND octet_length(media_manifest::text) <= 1048576)),
    media_expires_at timestamptz,
    cleanup_status text NOT NULL DEFAULT 'not_required',
    CHECK (cleanup_status IS NULL OR (char_length(btrim(cleanup_status)) > 0 AND char_length(cleanup_status) <= 1024)),
    cleanup_next_attempt_at timestamptz,
    playback_status text NOT NULL DEFAULT 'not_requested',
    CHECK (playback_status IS NULL OR (char_length(btrim(playback_status)) > 0 AND char_length(playback_status) <= 1024)),
    playback_expires_at timestamptz,
    playback_acknowledged_at timestamptz,
    expires_at timestamptz NOT NULL,
    UNIQUE (organization_id, device_id, request_key),
    CHECK (execution_mode IN ('local','cloud')),
    CHECK ((execution_mode = 'cloud') = (connection_id IS NOT NULL)),
    CHECK (status IN ('awaiting_device','awaiting_upload','queued','running','succeeded','failed','cancelled','expired')),
    CHECK ((status IN ('succeeded','failed','cancelled','expired')) = (completed_at IS NOT NULL)),
    CHECK (status <> 'queued' OR next_attempt_at IS NOT NULL),
    CHECK (status <> 'running' OR started_at IS NOT NULL),
    CHECK (attempt_count >= 0),
    CHECK ((lease_token IS NULL) = (lease_expires_at IS NULL)),
    CHECK (provider_submission_status IN ('not_submitted','submitting','submitted','unknown')),
    CHECK (execution_mode <> 'local' OR (provider_submission_status = 'not_submitted' AND provider_job_id IS NULL)),
    CHECK (cleanup_status IN ('not_required','pending','running','succeeded','failed')),
    CHECK (cleanup_status NOT IN ('pending','running','failed') OR cleanup_next_attempt_at IS NOT NULL),
    CHECK (playback_status IN ('not_requested','pending','playing','succeeded','failed','unknown','expired','cancelled')),
    CHECK (playback_status = 'not_requested' OR playback_expires_at IS NOT NULL),
    CHECK (playback_acknowledged_at IS NULL OR playback_status IN ('succeeded','failed','expired','cancelled')),
    CHECK (deadline_at >= created_at AND expires_at >= created_at),
    CHECK (started_at IS NULL OR started_at >= created_at),
    CHECK (completed_at IS NULL OR completed_at >= COALESCE(started_at, created_at)),
    CHECK (media_expires_at IS NULL OR deadline_at <= media_expires_at),
    CHECK (jsonb_array_length(media_manifest) = 0 OR (media_expires_at IS NOT NULL AND cleanup_status <> 'not_required'))
);

CREATE TABLE device_telemetry_samples (
    id uuid NOT NULL PRIMARY KEY,
    organization_id uuid NOT NULL,
    device_id uuid NOT NULL,
    department_id uuid,
    boot_id uuid NOT NULL,
    sequence_number bigint NOT NULL,
    observed_at timestamptz,
    received_at timestamptz NOT NULL DEFAULT now(),
    metrics jsonb NOT NULL,
    CHECK (metrics IS NULL OR (jsonb_typeof(metrics) = 'object' AND octet_length(metrics::text) <= 65536)),
    expires_at timestamptz NOT NULL,
    UNIQUE (organization_id, device_id, boot_id, sequence_number),
    CHECK (sequence_number >= 0),
    CHECK (expires_at >= received_at),
    CHECK (valid_metrics(metrics))
);

CREATE TABLE activity_events (
    id uuid NOT NULL PRIMARY KEY,
    organization_id uuid,
    department_id uuid,
    device_id uuid,
    actor_type text NOT NULL,
    CHECK (actor_type IS NULL OR (char_length(btrim(actor_type)) > 0 AND char_length(actor_type) <= 1024)),
    actor_user_id uuid,
    category text NOT NULL,
    CHECK (category IS NULL OR (char_length(btrim(category)) > 0 AND char_length(category) <= 1024)),
    event_type text NOT NULL,
    CHECK (event_type IS NULL OR (char_length(btrim(event_type)) > 0 AND char_length(event_type) <= 1024)),
    severity text NOT NULL DEFAULT 'info',
    CHECK (severity IS NULL OR (char_length(btrim(severity)) > 0 AND char_length(severity) <= 1024)),
    entity_type text,
    CHECK (entity_type IS NULL OR (char_length(btrim(entity_type)) > 0 AND char_length(entity_type) <= 1024)),
    entity_id uuid,
    run_id uuid,
    source_event_id uuid,
    occurred_at timestamptz NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    CHECK (details IS NULL OR (jsonb_typeof(details) = 'object' AND octet_length(details::text) <= 65536)),
    expires_at timestamptz NOT NULL,
    CHECK (actor_type IN ('user','device','system')),
    CHECK ((actor_type = 'user') = (actor_user_id IS NOT NULL)),
    CHECK (category IN ('audit','operational')),
    CHECK (severity IN ('info','warning','error')),
    CHECK (actor_type <> 'device' OR (organization_id IS NOT NULL AND device_id IS NOT NULL AND category = 'operational' AND source_event_id IS NOT NULL)),
    CHECK (source_event_id IS NULL OR (organization_id IS NOT NULL AND device_id IS NOT NULL)),
    CHECK (organization_id IS NOT NULL OR (department_id IS NULL AND device_id IS NULL)),
    CHECK (expires_at >= received_at)
);

CREATE TABLE platform_settings (
    id smallint NOT NULL DEFAULT 1 PRIMARY KEY,
    display_name text NOT NULL DEFAULT 'Device Platform',
    CHECK (display_name IS NULL OR (char_length(btrim(display_name)) > 0 AND char_length(display_name) <= 1024)),
    registration_mode text NOT NULL DEFAULT 'self_service',
    CHECK (registration_mode IS NULL OR (char_length(btrim(registration_mode)) > 0 AND char_length(registration_mode) <= 1024)),
    enabled_providers text[] NOT NULL DEFAULT '{}'::text[],
    default_organization_policy jsonb NOT NULL,
    CHECK (default_organization_policy IS NULL OR (jsonb_typeof(default_organization_policy) = 'object' AND octet_length(default_organization_policy::text) <= 65536)),
    policy_limits jsonb NOT NULL,
    CHECK (policy_limits IS NULL OR (jsonb_typeof(policy_limits) = 'object' AND octet_length(policy_limits::text) <= 65536)),
    device_defaults jsonb NOT NULL,
    CHECK (device_defaults IS NULL OR (jsonb_typeof(device_defaults) = 'object' AND octet_length(device_defaults::text) <= 65536)),
    maintenance_mode boolean NOT NULL DEFAULT false,
    configuration_version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by uuid,
    CHECK (id = 1),
    CHECK (registration_mode IN ('self_service','invite_only')),
    CHECK (enabled_providers <@ ARRAY['aws','azure']::text[] AND array_position(enabled_providers, NULL) IS NULL AND cardinality(enabled_providers) <= 2),
    CHECK (configuration_version > 0),
    CHECK (valid_policy(default_organization_policy) AND valid_policy(policy_limits)),
    CHECK (policy_within(default_organization_policy, policy_limits)),
    CHECK (valid_device_defaults(device_defaults))
);

-- Bound indexed TEXT by bytes as well as characters. Multibyte UTF-8 and long
-- issuer/subject pairs otherwise exceed PostgreSQL's B-tree tuple-size limit.
ALTER TABLE users ADD CONSTRAINT users_identity_index_bytes
  CHECK (octet_length(identity_issuer) + octet_length(identity_subject) <= 2048);
ALTER TABLE users ADD CONSTRAINT users_email_index_bytes
  CHECK (octet_length(lower(btrim(email))) <= 1024);
ALTER TABLE organizations ADD CONSTRAINT organizations_name_index_bytes
  CHECK (octet_length(name) <= 1024);
ALTER TABLE departments ADD CONSTRAINT departments_name_index_bytes
  CHECK (octet_length(lower(btrim(name))) <= 1024);
ALTER TABLE provider_connections ADD CONSTRAINT connections_name_index_bytes
  CHECK (octet_length(lower(btrim(name))) <= 1024);
ALTER TABLE processing_profiles ADD CONSTRAINT profiles_name_index_bytes
  CHECK (octet_length(lower(btrim(name))) <= 1024);
ALTER TABLE organization_memberships ADD CONSTRAINT memberships_invitation_index_bytes
  CHECK (octet_length(lower(btrim(invited_email))) <= 1024
    AND octet_length(invitation_token_hash) <= 1024);
ALTER TABLE devices ADD CONSTRAINT devices_token_index_bytes
  CHECK (octet_length(enrollment_token_hash) <= 1024 AND octet_length(credential_hash) <= 1024);

-- Restrictive references preserve tenant history; use inactive status for administration.

ALTER TABLE organizations ADD FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE organizations ADD FOREIGN KEY (status_changed_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE departments ADD FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE departments ADD FOREIGN KEY (status_changed_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE departments ADD FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT;
ALTER TABLE users ADD FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE users ADD FOREIGN KEY (status_changed_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE organization_memberships ADD FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE organization_memberships ADD FOREIGN KEY (status_changed_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE organization_memberships ADD FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT;
ALTER TABLE organization_memberships ADD FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE organization_memberships ADD FOREIGN KEY (organization_id, department_id) REFERENCES departments(organization_id, id) ON DELETE RESTRICT;
ALTER TABLE devices ADD FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE devices ADD FOREIGN KEY (status_changed_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE devices ADD FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT;
ALTER TABLE devices ADD FOREIGN KEY (organization_id, department_id) REFERENCES departments(organization_id, id) ON DELETE RESTRICT;
ALTER TABLE devices ADD FOREIGN KEY (organization_id, profile_id) REFERENCES processing_profiles(organization_id, id) ON DELETE RESTRICT;
ALTER TABLE devices ADD FOREIGN KEY (organization_id, applied_profile_revision_id) REFERENCES processing_profile_revisions(organization_id, id) ON DELETE RESTRICT;
ALTER TABLE provider_connections ADD FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE provider_connections ADD FOREIGN KEY (status_changed_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE provider_connections ADD FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT;
ALTER TABLE processing_profiles ADD FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE processing_profiles ADD FOREIGN KEY (status_changed_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE processing_profiles ADD FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT;
ALTER TABLE processing_profiles ADD FOREIGN KEY (organization_id, draft_audio_input_connection_id) REFERENCES provider_connections(organization_id, id) ON DELETE RESTRICT;
ALTER TABLE processing_profiles ADD FOREIGN KEY (organization_id, draft_video_connection_id) REFERENCES provider_connections(organization_id, id) ON DELETE RESTRICT;
ALTER TABLE processing_profiles ADD FOREIGN KEY (organization_id, draft_audio_output_connection_id) REFERENCES provider_connections(organization_id, id) ON DELETE RESTRICT;
ALTER TABLE processing_profile_revisions ADD FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT;
ALTER TABLE processing_profile_revisions ADD FOREIGN KEY (organization_id, profile_id) REFERENCES processing_profiles(organization_id, id) ON DELETE RESTRICT;
ALTER TABLE processing_profile_revisions ADD FOREIGN KEY (organization_id, audio_input_connection_id) REFERENCES provider_connections(organization_id, id) ON DELETE RESTRICT;
ALTER TABLE processing_profile_revisions ADD FOREIGN KEY (organization_id, video_connection_id) REFERENCES provider_connections(organization_id, id) ON DELETE RESTRICT;
ALTER TABLE processing_profile_revisions ADD FOREIGN KEY (organization_id, audio_output_connection_id) REFERENCES provider_connections(organization_id, id) ON DELETE RESTRICT;
ALTER TABLE processing_profile_revisions ADD FOREIGN KEY (published_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE processing_runs ADD FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT;
ALTER TABLE processing_runs ADD FOREIGN KEY (organization_id, device_id) REFERENCES devices(organization_id, id) ON DELETE RESTRICT;
ALTER TABLE processing_runs ADD FOREIGN KEY (organization_id, department_id) REFERENCES departments(organization_id, id) ON DELETE RESTRICT;
ALTER TABLE processing_runs ADD FOREIGN KEY (organization_id, profile_revision_id) REFERENCES processing_profile_revisions(organization_id, id) ON DELETE RESTRICT;
ALTER TABLE processing_runs ADD FOREIGN KEY (requested_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE processing_runs ADD FOREIGN KEY (organization_id, connection_id) REFERENCES provider_connections(organization_id, id) ON DELETE RESTRICT;
ALTER TABLE device_telemetry_samples ADD FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT;
ALTER TABLE device_telemetry_samples ADD FOREIGN KEY (organization_id, device_id) REFERENCES devices(organization_id, id) ON DELETE RESTRICT;
ALTER TABLE device_telemetry_samples ADD FOREIGN KEY (organization_id, department_id) REFERENCES departments(organization_id, id) ON DELETE RESTRICT;
ALTER TABLE activity_events ADD FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT;
ALTER TABLE activity_events ADD FOREIGN KEY (organization_id, department_id) REFERENCES departments(organization_id, id) ON DELETE RESTRICT;
ALTER TABLE activity_events ADD FOREIGN KEY (organization_id, device_id) REFERENCES devices(organization_id, id) ON DELETE RESTRICT;
ALTER TABLE activity_events ADD FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE platform_settings ADD FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE RESTRICT;
ALTER TABLE organizations ADD FOREIGN KEY (id, default_profile_id) REFERENCES processing_profiles(organization_id, id) ON DELETE RESTRICT;
ALTER TABLE processing_profiles ADD FOREIGN KEY (organization_id, id, published_revision_id) REFERENCES processing_profile_revisions(organization_id, profile_id, id) ON DELETE RESTRICT;

-- Column documentation is queryable through PostgreSQL tools.

COMMENT ON COLUMN organizations.id IS 'Primary key.';
COMMENT ON COLUMN organizations.created_at IS 'Server creation time; registration date for users/devices.';
COMMENT ON COLUMN organizations.updated_at IS 'Set by a database trigger on every update.';
COMMENT ON COLUMN organizations.created_by IS 'User who created the record; FK users.id; NULL for bootstrap/system.';
COMMENT ON COLUMN organizations.is_active IS 'Administrative flag; parent status and lifecycle still apply.';
COMMENT ON COLUMN organizations.status_changed_at IS 'Time the active flag last changed.';
COMMENT ON COLUMN organizations.status_changed_by IS 'User who changed status; FK users.id; NULL for system.';
COMMENT ON COLUMN organizations.status_reason IS 'Short explanation of the current status.';
COMMENT ON COLUMN organizations.name IS 'Nonblank display name.';
COMMENT ON COLUMN organizations.description IS 'Optional short description.';
COMMENT ON COLUMN organizations.contact_name IS 'Primary contact person''s name.';
COMMENT ON COLUMN organizations.contact_email IS 'Primary contact email; does not grant access.';
COMMENT ON COLUMN organizations.contact_phone IS 'Primary contact phone number.';
COMMENT ON COLUMN organizations.default_profile_id IS 'Default processing profile; must belong to this organization.';
COMMENT ON COLUMN organizations.policy_settings IS 'Validated retention, usage, capture, and offline limits; see JSON contracts.';
COMMENT ON COLUMN organizations.suspension_source IS 'organization or platform when inactive; NULL when active.';
COMMENT ON COLUMN organizations.last_activity_at IS 'Latest meaningful tenant activity; excludes heartbeats and backfills.';
COMMENT ON TABLE organizations IS 'Tenant boundary, organization contacts, processing defaults, and policy limits.';
COMMENT ON COLUMN departments.id IS 'Primary key.';
COMMENT ON COLUMN departments.created_at IS 'Server creation time; registration date for users/devices.';
COMMENT ON COLUMN departments.updated_at IS 'Set by a database trigger on every update.';
COMMENT ON COLUMN departments.created_by IS 'User who created the record; FK users.id; NULL for bootstrap/system.';
COMMENT ON COLUMN departments.is_active IS 'Administrative flag; parent status and lifecycle still apply.';
COMMENT ON COLUMN departments.status_changed_at IS 'Time the active flag last changed.';
COMMENT ON COLUMN departments.status_changed_by IS 'User who changed status; FK users.id; NULL for system.';
COMMENT ON COLUMN departments.status_reason IS 'Short explanation of the current status.';
COMMENT ON COLUMN departments.organization_id IS 'Owning organization; FK organizations.id.';
COMMENT ON COLUMN departments.name IS 'Nonblank display name.';
COMMENT ON COLUMN departments.description IS 'Optional short description.';
COMMENT ON TABLE departments IS 'Flat organizational units for device grouping and scoped access.';
COMMENT ON COLUMN users.id IS 'Primary key.';
COMMENT ON COLUMN users.created_at IS 'Server creation time; registration date for users/devices.';
COMMENT ON COLUMN users.updated_at IS 'Set by a database trigger on every update.';
COMMENT ON COLUMN users.created_by IS 'User who created the record; FK users.id; NULL for bootstrap/system.';
COMMENT ON COLUMN users.is_active IS 'Administrative flag; parent status and lifecycle still apply.';
COMMENT ON COLUMN users.status_changed_at IS 'Time the active flag last changed.';
COMMENT ON COLUMN users.status_changed_by IS 'User who changed status; FK users.id; NULL for system.';
COMMENT ON COLUMN users.status_reason IS 'Short explanation of the current status.';
COMMENT ON COLUMN users.identity_issuer IS 'Trusted OIDC issuer identifier.';
COMMENT ON COLUMN users.identity_subject IS 'Opaque subject from the verified identity token.';
COMMENT ON COLUMN users.display_name IS 'User''s display name.';
COMMENT ON COLUMN users.email IS 'Contact/login email received from the identity service.';
COMMENT ON COLUMN users.email_verified IS 'Updated only from trusted identity verification.';
COMMENT ON COLUMN users.phone IS 'Optional contact number.';
COMMENT ON COLUMN users.platform_role IS 'NULL or platform_admin; independent of organization memberships.';
COMMENT ON COLUMN users.last_login_at IS 'Last successful interactive login.';
COMMENT ON COLUMN users.last_activity_at IS 'Last meaningful authenticated application action.';
COMMENT ON TABLE users IS 'Global application users mapped to the login identity provider.';
COMMENT ON COLUMN organization_memberships.id IS 'Primary key.';
COMMENT ON COLUMN organization_memberships.created_at IS 'Server creation time; registration date for users/devices.';
COMMENT ON COLUMN organization_memberships.updated_at IS 'Set by a database trigger on every update.';
COMMENT ON COLUMN organization_memberships.created_by IS 'User who created the record; FK users.id; NULL for bootstrap/system.';
COMMENT ON COLUMN organization_memberships.is_active IS 'Pending invitations start inactive; accepted membership can be active.';
COMMENT ON COLUMN organization_memberships.status_changed_at IS 'Time the active flag last changed.';
COMMENT ON COLUMN organization_memberships.status_changed_by IS 'User who changed status; FK users.id; NULL for system.';
COMMENT ON COLUMN organization_memberships.status_reason IS 'Short explanation of the current status.';
COMMENT ON COLUMN organization_memberships.organization_id IS 'Owning organization; FK organizations.id.';
COMMENT ON COLUMN organization_memberships.user_id IS 'FK users.id; required after acceptance.';
COMMENT ON COLUMN organization_memberships.role IS 'org_admin, org_user, org_read_only, or org_trainee.';
COMMENT ON COLUMN organization_memberships.department_id IS 'Same-organization department scope; NULL means organization-wide.';
COMMENT ON COLUMN organization_memberships.invitation_status IS 'pending, accepted, expired, or revoked.';
COMMENT ON COLUMN organization_memberships.invited_email IS 'Required for invitation flow; optional for directly created first-admin membership.';
COMMENT ON COLUMN organization_memberships.invitation_token_hash IS 'Unique hash of the pending invitation token; never the plaintext token.';
COMMENT ON COLUMN organization_memberships.invitation_expires_at IS 'Required while pending.';
COMMENT ON COLUMN organization_memberships.joined_at IS 'Acceptance/join time; required for accepted memberships.';
COMMENT ON TABLE organization_memberships IS 'Organization roles, optional department scope, and invitation acceptance.';
COMMENT ON COLUMN devices.id IS 'Primary key.';
COMMENT ON COLUMN devices.created_at IS 'Server creation time; registration date for users/devices.';
COMMENT ON COLUMN devices.updated_at IS 'Set by a database trigger on every update.';
COMMENT ON COLUMN devices.created_by IS 'User who created the record; FK users.id; NULL for bootstrap/system.';
COMMENT ON COLUMN devices.is_active IS 'Administrative flag; parent status and lifecycle still apply.';
COMMENT ON COLUMN devices.status_changed_at IS 'Time the active flag last changed.';
COMMENT ON COLUMN devices.status_changed_by IS 'User who changed status; FK users.id; NULL for system.';
COMMENT ON COLUMN devices.status_reason IS 'Short explanation of the current status.';
COMMENT ON COLUMN devices.organization_id IS 'Owning organization; FK organizations.id.';
COMMENT ON COLUMN devices.department_id IS 'Current department; same-organization FK.';
COMMENT ON COLUMN devices.name IS 'Nonblank display name.';
COMMENT ON COLUMN devices.device_type IS 'laptop, raspberry_pi, or other.';
COMMENT ON COLUMN devices.role IS 'Fixed non-human role; CHECK role = org_device.';
COMMENT ON COLUMN devices.details IS 'Optional model, serial number, OS, agent version, and hardware notes.';
COMMENT ON COLUMN devices.location IS 'Simple location label.';
COMMENT ON COLUMN devices.contact_name IS 'Responsible contact person''s name.';
COMMENT ON COLUMN devices.contact_email IS 'Contact email.';
COMMENT ON COLUMN devices.contact_phone IS 'Contact phone.';
COMMENT ON COLUMN devices.profile_id IS 'Explicit same-organization profile assignment; NULL uses organization default.';
COMMENT ON COLUMN devices.applied_profile_revision_id IS 'Last acknowledged, same-organization revision.';
COMMENT ON COLUMN devices.applied_configuration_hash IS 'SHA-256 hex of acknowledged resolved configuration, including relevant platform/org policy.';
COMMENT ON COLUMN devices.config_error IS 'Rejected revision ID, error code, and bounded diagnostic message.';
COMMENT ON COLUMN devices.capabilities IS 'Available capture/output devices and installed local engines.';
COMMENT ON COLUMN devices.enrollment_state IS 'pending, enrolled, or retired; independent of is_active.';
COMMENT ON COLUMN devices.enrollment_token_hash IS 'Unique hashed one-time enrollment code.';
COMMENT ON COLUMN devices.enrollment_expires_at IS 'Expiry of the currently issued enrollment code.';
COMMENT ON COLUMN devices.enrollment_attempt_count IS 'Nonnegative redemption attempts for the current code.';
COMMENT ON COLUMN devices.credential_hash IS 'Unique hash of this device''s current high-entropy credential.';
COMMENT ON COLUMN devices.credential_version IS 'Incremented on credential issuance/rotation/revocation.';
COMMENT ON COLUMN devices.credential_issued_at IS 'Current credential issuance time.';
COMMENT ON COLUMN devices.credential_revoked_at IS 'Revocation time; inactive alone does not revoke.';
COMMENT ON COLUMN devices.enrolled_at IS 'First successful enrollment of this registration.';
COMMENT ON COLUMN devices.last_seen_at IS 'Last authenticated contact, measured by the server.';
COMMENT ON COLUMN devices.last_activity_at IS 'Latest meaningful current capture/control/processing event.';
COMMENT ON COLUMN devices.offline_authorized_until IS 'Last issued offline authorization expiry.';
COMMENT ON COLUMN devices.last_telemetry_at IS 'Server receipt time for latest health snapshot.';
COMMENT ON COLUMN devices.latest_health IS 'Latest validated measurements and component status.';
COMMENT ON TABLE devices IS 'Registered laptop/Pi identities, assignments, configuration, enrollment, and current health.';
COMMENT ON COLUMN provider_connections.id IS 'Primary key.';
COMMENT ON COLUMN provider_connections.created_at IS 'Server creation time; registration date for users/devices.';
COMMENT ON COLUMN provider_connections.updated_at IS 'Set by a database trigger on every update.';
COMMENT ON COLUMN provider_connections.created_by IS 'User who created the record; FK users.id; NULL for bootstrap/system.';
COMMENT ON COLUMN provider_connections.is_active IS 'Administrative flag; parent status and lifecycle still apply.';
COMMENT ON COLUMN provider_connections.status_changed_at IS 'Time the active flag last changed.';
COMMENT ON COLUMN provider_connections.status_changed_by IS 'User who changed status; FK users.id; NULL for system.';
COMMENT ON COLUMN provider_connections.status_reason IS 'Short explanation of the current status.';
COMMENT ON COLUMN provider_connections.organization_id IS 'Owning organization; FK organizations.id.';
COMMENT ON COLUMN provider_connections.name IS 'Nonblank display name.';
COMMENT ON COLUMN provider_connections.description IS 'Optional short description.';
COMMENT ON COLUMN provider_connections.provider IS 'aws or azure initially.';
COMMENT ON COLUMN provider_connections.connection_type IS 'aws_processing, azure_speech, or azure_video_indexer.';
COMMENT ON COLUMN provider_connections.auth_mode IS 'workload_identity, assume_role, access_key, api_key, or service_principal as supported.';
COMMENT ON COLUMN provider_connections.settings IS 'Non-secret region/resource/storage settings; see contracts.';
COMMENT ON COLUMN provider_connections.secret_ref IS 'Reference to a secret-manager object; required for secret-based auth.';
COMMENT ON COLUMN provider_connections.configuration_version IS 'Positive version; increment when settings/authentication change.';
COMMENT ON COLUMN provider_connections.validation_results IS 'Per-service check status/error/time and checked configuration version.';
COMMENT ON COLUMN provider_connections.last_validated_at IS 'Most recent current-configuration validation.';
COMMENT ON COLUMN provider_connections.last_used_at IS 'Most recent authorized provider operation.';
COMMENT ON TABLE provider_connections IS 'Reusable organization-owned cloud configuration and secret references.';
COMMENT ON COLUMN processing_profiles.id IS 'Primary key.';
COMMENT ON COLUMN processing_profiles.created_at IS 'Server creation time; registration date for users/devices.';
COMMENT ON COLUMN processing_profiles.updated_at IS 'Set by a database trigger on every update.';
COMMENT ON COLUMN processing_profiles.created_by IS 'User who created the record; FK users.id; NULL for bootstrap/system.';
COMMENT ON COLUMN processing_profiles.is_active IS 'Administrative flag; parent status and lifecycle still apply.';
COMMENT ON COLUMN processing_profiles.status_changed_at IS 'Time the active flag last changed.';
COMMENT ON COLUMN processing_profiles.status_changed_by IS 'User who changed status; FK users.id; NULL for system.';
COMMENT ON COLUMN processing_profiles.status_reason IS 'Short explanation of the current status.';
COMMENT ON COLUMN processing_profiles.organization_id IS 'Owning organization; FK organizations.id.';
COMMENT ON COLUMN processing_profiles.name IS 'Nonblank display name.';
COMMENT ON COLUMN processing_profiles.description IS 'Optional short description.';
COMMENT ON COLUMN processing_profiles.draft_settings IS 'Audio/video/output and capture policy settings; schema_version=1.';
COMMENT ON COLUMN processing_profiles.draft_audio_input_connection_id IS 'Cloud audio input connection; same-organization FK.';
COMMENT ON COLUMN processing_profiles.draft_video_connection_id IS 'Cloud video connection; same-organization FK.';
COMMENT ON COLUMN processing_profiles.draft_audio_output_connection_id IS 'Cloud synthesis connection; same-organization FK.';
COMMENT ON COLUMN processing_profiles.published_revision_id IS 'Current immutable revision of this exact profile.';
COMMENT ON TABLE processing_profiles IS 'Editable draft and pointer to the current immutable published revision.';
COMMENT ON COLUMN processing_profile_revisions.id IS 'Primary key.';
COMMENT ON COLUMN processing_profile_revisions.organization_id IS 'Owning organization; FK organizations.id.';
COMMENT ON COLUMN processing_profile_revisions.profile_id IS 'Same-organization parent profile.';
COMMENT ON COLUMN processing_profile_revisions.version IS 'Positive sequence within this profile.';
COMMENT ON COLUMN processing_profile_revisions.settings IS 'Validated complete settings snapshot, including schema_version.';
COMMENT ON COLUMN processing_profile_revisions.audio_input_connection_id IS 'Same-organization audio input connection.';
COMMENT ON COLUMN processing_profile_revisions.video_connection_id IS 'Same-organization video connection.';
COMMENT ON COLUMN processing_profile_revisions.audio_output_connection_id IS 'Same-organization audio output connection.';
COMMENT ON COLUMN processing_profile_revisions.published_at IS 'Publication time.';
COMMENT ON COLUMN processing_profile_revisions.published_by IS 'Publishing user; FK users.id.';
COMMENT ON COLUMN processing_profile_revisions.change_note IS 'Optional brief publication/rollback explanation.';
COMMENT ON TABLE processing_profile_revisions IS 'Immutable settings and provider bindings sent to devices.';
COMMENT ON COLUMN processing_runs.id IS 'Primary key and output playback deduplication ID.';
COMMENT ON COLUMN processing_runs.organization_id IS 'Owning organization; FK organizations.id.';
COMMENT ON COLUMN processing_runs.device_id IS 'Same-organization device.';
COMMENT ON COLUMN processing_runs.department_id IS 'Authorized department snapshot at capture/request time.';
COMMENT ON COLUMN processing_runs.profile_revision_id IS 'Same-organization executed/authorized revision.';
COMMENT ON COLUMN processing_runs.requested_by IS 'Requesting user; NULL for permitted device/system work.';
COMMENT ON COLUMN processing_runs.capture_id IS 'Correlation ID linking related audio and video; not a separate table.';
COMMENT ON COLUMN processing_runs.request_key IS 'Client-generated idempotency key for this device request.';
COMMENT ON COLUMN processing_runs.operation IS 'Registry operation, e.g. audio.transcribe, video.labels, audio.synthesize, audio.playback.';
COMMENT ON COLUMN processing_runs.execution_mode IS 'local or cloud.';
COMMENT ON COLUMN processing_runs.engine IS 'Registry engine, e.g. aws_transcribe, azure_speech, opencv_motion.';
COMMENT ON COLUMN processing_runs.connection_id IS 'Required for cloud execution; NULL for local.';
COMMENT ON COLUMN processing_runs.effective_settings IS 'Resolved non-secret configuration, provider settings/version, and policy snapshot.';
COMMENT ON COLUMN processing_runs.request IS 'Bounded operation input/options; may contain synthesis text, never credentials.';
COMMENT ON COLUMN processing_runs.status IS 'awaiting_device, awaiting_upload, queued, running, succeeded, failed, cancelled, or expired.';
COMMENT ON COLUMN processing_runs.created_at IS 'Server acceptance/creation time.';
COMMENT ON COLUMN processing_runs.updated_at IS 'Trigger-maintained last modification.';
COMMENT ON COLUMN processing_runs.captured_at IS 'Device-reported capture start; not used to prove liveness.';
COMMENT ON COLUMN processing_runs.started_at IS 'Processing start time.';
COMMENT ON COLUMN processing_runs.completed_at IS 'Terminal processing time, including cancellation/expiry.';
COMMENT ON COLUMN processing_runs.deadline_at IS 'Latest allowed processing completion; bounded by media lifetime.';
COMMENT ON COLUMN processing_runs.attempt_count IS 'Nonnegative processing dispatch count.';
COMMENT ON COLUMN processing_runs.next_attempt_at IS 'Next dispatch/poll retry time; required for scheduled queued work.';
COMMENT ON COLUMN processing_runs.lease_token IS 'Random worker-claim token; required when claimed.';
COMMENT ON COLUMN processing_runs.lease_expires_at IS 'Claim expiry for recovery; changed with lease_token.';
COMMENT ON COLUMN processing_runs.provider_submission_status IS 'not_submitted, submitting, submitted, or unknown; supports reconciliation.';
COMMENT ON COLUMN processing_runs.provider_job_id IS 'External asynchronous job identifier, where one exists.';
COMMENT ON COLUMN processing_runs.result IS 'Normalized transcript, labels, local event, or audio metadata.';
COMMENT ON COLUMN processing_runs.error IS 'Bounded code/message/retryable details without secrets.';
COMMENT ON COLUMN processing_runs.usage IS 'Reserved/actual usage by unit and accounting date, independent of retry count.';
COMMENT ON COLUMN processing_runs.media_manifest IS 'Private object/provider-copy references and per-copy cleanup state.';
COMMENT ON COLUMN processing_runs.media_expires_at IS 'Earliest required media-cleanup deadline.';
COMMENT ON COLUMN processing_runs.cleanup_status IS 'not_required, pending, running, succeeded, or failed.';
COMMENT ON COLUMN processing_runs.cleanup_next_attempt_at IS 'Due time for pending/retried cleanup.';
COMMENT ON COLUMN processing_runs.playback_status IS 'not_requested, pending, playing, succeeded, failed, unknown, expired, or cancelled.';
COMMENT ON COLUMN processing_runs.playback_expires_at IS 'Deadline after which audio must not play.';
COMMENT ON COLUMN processing_runs.playback_acknowledged_at IS 'Receipt time of the device''s final playback acknowledgment.';
COMMENT ON COLUMN processing_runs.expires_at IS 'Result/request retention deadline; normally creation plus 30 days.';
COMMENT ON TABLE processing_runs IS 'One local/cloud operation, queue lifecycle, results, media cleanup, and optional playback.';
COMMENT ON COLUMN device_telemetry_samples.id IS 'Primary key.';
COMMENT ON COLUMN device_telemetry_samples.organization_id IS 'Owning organization; FK organizations.id.';
COMMENT ON COLUMN device_telemetry_samples.device_id IS 'Same-organization device.';
COMMENT ON COLUMN device_telemetry_samples.department_id IS 'Server-authorized department context when sampled.';
COMMENT ON COLUMN device_telemetry_samples.boot_id IS 'Agent-generated ID for this runtime/boot.';
COMMENT ON COLUMN device_telemetry_samples.sequence_number IS 'Nonnegative, increasing within boot_id.';
COMMENT ON COLUMN device_telemetry_samples.observed_at IS 'Reported measurement time; NULL if unavailable/unreliable.';
COMMENT ON COLUMN device_telemetry_samples.received_at IS 'Server receipt time.';
COMMENT ON COLUMN device_telemetry_samples.metrics IS 'Validated CPU/memory/disk/temperature/capture measurements.';
COMMENT ON COLUMN device_telemetry_samples.expires_at IS 'Usually received_at plus 7 days.';
COMMENT ON TABLE device_telemetry_samples IS 'Sampled device-health history; latest health remains on devices.';
COMMENT ON COLUMN activity_events.id IS 'Primary key.';
COMMENT ON COLUMN activity_events.organization_id IS 'Tenant context; NULL only for global identity/platform events.';
COMMENT ON COLUMN activity_events.department_id IS 'Historical scope for operational entries.';
COMMENT ON COLUMN activity_events.device_id IS 'Device context, including when a user/system acted on it.';
COMMENT ON COLUMN activity_events.actor_type IS 'user, device, or system.';
COMMENT ON COLUMN activity_events.actor_user_id IS 'FK users.id; required when actor_type=user.';
COMMENT ON COLUMN activity_events.category IS 'audit or operational.';
COMMENT ON COLUMN activity_events.event_type IS 'Registry action, e.g. device.enrolled or profile.published.';
COMMENT ON COLUMN activity_events.severity IS 'info, warning, or error.';
COMMENT ON COLUMN activity_events.entity_type IS 'Kind of affected record.';
COMMENT ON COLUMN activity_events.entity_id IS 'Stable historical record identifier; validated at event creation.';
COMMENT ON COLUMN activity_events.run_id IS 'Correlation to a run; may outlive run retention.';
COMMENT ON COLUMN activity_events.source_event_id IS 'Device-generated event deduplication ID; required for device-originated events.';
COMMENT ON COLUMN activity_events.occurred_at IS 'Event occurrence time; device time is informational.';
COMMENT ON COLUMN activity_events.received_at IS 'Server ingestion time.';
COMMENT ON COLUMN activity_events.details IS 'Bounded redacted metadata, optional boot/sequence, and historical flag.';
COMMENT ON COLUMN activity_events.expires_at IS 'Typically receipt plus 90 days for audit, 30 days for operational.';
COMMENT ON TABLE activity_events IS 'Administrative audit and operational device events with scoped visibility.';
COMMENT ON COLUMN platform_settings.id IS 'Singleton primary key; CHECK id = 1.';
COMMENT ON COLUMN platform_settings.display_name IS 'Platform name shown in the application.';
COMMENT ON COLUMN platform_settings.registration_mode IS 'self_service or invite_only; controls organization creation/onboarding.';
COMMENT ON COLUMN platform_settings.enabled_providers IS 'Global provider allowlist; enable aws/azure after their adapters and configuration are ready.';
COMMENT ON COLUMN platform_settings.default_organization_policy IS 'Policy copied when an organization is created.';
COMMENT ON COLUMN platform_settings.policy_limits IS 'Validated hard ceilings for tenant retention, usage, capture, and offline authorization.';
COMMENT ON COLUMN platform_settings.device_defaults IS 'Heartbeat/control/history intervals and offline timeout.';
COMMENT ON COLUMN platform_settings.maintenance_mode IS 'Pause new enrollment/processing while preserving recovery, reads, health/status, and cleanup.';
COMMENT ON COLUMN platform_settings.configuration_version IS 'Positive version, incremented on every configuration update.';
COMMENT ON COLUMN platform_settings.created_at IS 'Seed-row creation time.';
COMMENT ON COLUMN platform_settings.updated_at IS 'Trigger-maintained last modification.';
COMMENT ON COLUMN platform_settings.updated_by IS 'FK users.id; NULL only for bootstrap/system initialization.';
COMMENT ON TABLE platform_settings IS 'One platform-wide configuration record, managed only by platform_admin. It has no organization_id and is not a tenant-owned table.';
