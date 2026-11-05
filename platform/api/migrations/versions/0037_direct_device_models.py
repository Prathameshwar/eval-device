"""Direct typed models and device selections; preserve execution history."""

from alembic import op

revision = "0037_direct_device_models"
down_revision = "0036_media_model_configs"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE device_platform.runtime_models (
      id uuid PRIMARY KEY,
      organization_id uuid REFERENCES device_platform.organizations(id),
      name text NOT NULL CHECK(length(btrim(name)) BETWEEN 1 AND 100),
      kind text NOT NULL CHECK(kind IN ('llm','asr','tts','video','legacy_media')),
      location text NOT NULL CHECK(location IN ('local','cloud')),
      provider text NOT NULL, engine text NOT NULL, model_key text NOT NULL,
      settings jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(settings)='object'),
      defaults jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(defaults)='object'),
      legacy jsonb NOT NULL DEFAULT '{}',
      encrypted_credentials bytea, credential_key_id text,
      credential_owner_id uuid, credential_owner_org uuid,
      revision integer NOT NULL DEFAULT 1 CHECK(revision>0),
      is_active boolean NOT NULL DEFAULT true, archived_at timestamptz,
      created_by uuid REFERENCES device_platform.users(id), updated_by uuid REFERENCES device_platform.users(id),
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      last_used_at timestamptz,
      CHECK((encrypted_credentials IS NULL)=(credential_key_id IS NULL)),
      CHECK(encrypted_credentials IS NULL OR (credential_owner_id IS NOT NULL AND credential_owner_org IS NOT NULL)),
      CHECK(archived_at IS NULL OR NOT is_active),
      CHECK(location<>'local' OR encrypted_credentials IS NULL OR legacy<>'{}'::jsonb)
    );
    CREATE INDEX runtime_models_directory ON device_platform.runtime_models(kind,location,name,id);
    CREATE TABLE device_platform.device_model_selections (
      device_id uuid PRIMARY KEY,
      organization_id uuid NOT NULL,
      mode text NOT NULL CHECK(mode IN ('local','cloud','mixed')),
      llm_model_id uuid REFERENCES device_platform.runtime_models(id),
      asr_model_id uuid REFERENCES device_platform.runtime_models(id),
      tts_model_id uuid REFERENCES device_platform.runtime_models(id),
      video_model_id uuid REFERENCES device_platform.runtime_models(id),
      execution_revision_id uuid,
      version integer NOT NULL DEFAULT 1 CHECK(version>0),
      updated_by uuid REFERENCES device_platform.users(id), updated_at timestamptz NOT NULL DEFAULT now(),
      FOREIGN KEY(organization_id,device_id) REFERENCES device_platform.devices(organization_id,id)
    );
    ALTER TABLE device_platform.processing_profile_revisions ALTER COLUMN profile_id DROP NOT NULL;
    ALTER TABLE device_platform.processing_profile_revisions ADD COLUMN device_id uuid;
    ALTER TABLE device_platform.processing_profile_revisions ADD CONSTRAINT execution_device_scope
      FOREIGN KEY(organization_id,device_id) REFERENCES device_platform.devices(organization_id,id);
    ALTER TABLE device_platform.processing_profile_revisions ADD CONSTRAINT execution_owner
      CHECK(profile_id IS NOT NULL OR device_id IS NOT NULL);
    ALTER TABLE device_platform.device_model_selections ADD CONSTRAINT selection_revision_scope
      FOREIGN KEY(organization_id,execution_revision_id)
      REFERENCES device_platform.processing_profile_revisions(organization_id,id);

    -- A transition adapter keeps old clients and historical foreign keys consistent.
    -- New model/device writes never create legacy connections or profiles.
    CREATE FUNCTION device_platform.sync_legacy_runtime_model() RETURNS trigger
    LANGUAGE plpgsql SET search_path=device_platform,pg_temp AS $$
    DECLARE v jsonb:=to_jsonb(NEW); is_llm boolean:=TG_TABLE_NAME='llm_connections';
    BEGIN
      INSERT INTO runtime_models(id,organization_id,name,kind,location,provider,engine,model_key,
        settings,legacy,encrypted_credentials,credential_key_id,credential_owner_id,credential_owner_org,
        revision,is_active,archived_at,created_at,updated_at)
      VALUES(NEW.id,NEW.organization_id,NEW.name,CASE WHEN is_llm THEN 'llm' ELSE 'legacy_media' END,
        CASE WHEN v->>'provider'='local_llama_cpp' THEN 'local' ELSE 'cloud' END,NEW.provider,
        CASE WHEN is_llm THEN 'llm' ELSE v->>'connection_type' END,coalesce(v->>'model',v->>'connection_type'),
        CASE WHEN is_llm THEN v-ARRAY['encrypted_credentials','credential_key_id','id','organization_id','name']
          ELSE (v->'settings')||jsonb_build_object('connection_type',v->>'connection_type','auth_mode',v->>'auth_mode') END,
        v-ARRAY['encrypted_credentials','credential_key_id'],NEW.encrypted_credentials,NEW.credential_key_id,
        NEW.id,NEW.organization_id,coalesce((v->>'revision')::int,(v->>'configuration_version')::int),
        NEW.is_active,NEW.archived_at,NEW.created_at,NEW.updated_at)
      ON CONFLICT(id) DO UPDATE SET name=excluded.name,settings=excluded.settings,legacy=excluded.legacy,
        provider=excluded.provider,engine=excluded.engine,model_key=excluded.model_key,location=excluded.location,
        encrypted_credentials=excluded.encrypted_credentials,credential_key_id=excluded.credential_key_id,
        revision=excluded.revision,is_active=excluded.is_active,archived_at=excluded.archived_at,
        updated_at=excluded.updated_at;
      RETURN NEW;
    END $$;
    CREATE TRIGGER sync_runtime_model AFTER INSERT OR UPDATE ON device_platform.llm_connections
      FOR EACH ROW EXECUTE FUNCTION device_platform.sync_legacy_runtime_model();
    CREATE TRIGGER sync_runtime_model AFTER INSERT OR UPDATE ON device_platform.provider_connections
      FOR EACH ROW EXECUTE FUNCTION device_platform.sync_legacy_runtime_model();
    INSERT INTO device_platform.runtime_models(id,organization_id,name,kind,location,provider,engine,model_key,
      settings,legacy,encrypted_credentials,credential_key_id,credential_owner_id,credential_owner_org,
      revision,is_active,archived_at,created_at,updated_at)
    SELECT id,organization_id,name,'llm',CASE WHEN provider='local_llama_cpp' THEN 'local' ELSE 'cloud' END,
      provider,'llm',model,to_jsonb(c)-ARRAY['encrypted_credentials','credential_key_id','id','organization_id','name'],
      to_jsonb(c)-ARRAY['encrypted_credentials','credential_key_id'],encrypted_credentials,credential_key_id,
      id,organization_id,revision,is_active,archived_at,created_at,updated_at
    FROM device_platform.llm_connections c;
    INSERT INTO device_platform.runtime_models(id,organization_id,name,kind,location,provider,engine,model_key,
      settings,legacy,encrypted_credentials,credential_key_id,credential_owner_id,credential_owner_org,
      revision,is_active,archived_at,created_at,updated_at)
    SELECT id,organization_id,name,'legacy_media','cloud',provider,connection_type,connection_type,
      settings||jsonb_build_object('connection_type',connection_type,'auth_mode',auth_mode),
      to_jsonb(c)-ARRAY['encrypted_credentials','credential_key_id'],encrypted_credentials,credential_key_id,
      id,organization_id,configuration_version,is_active,archived_at,created_at,updated_at
    FROM device_platform.provider_connections c;
    INSERT INTO device_platform.runtime_models(id,name,kind,location,provider,engine,model_key,settings,
      encrypted_credentials,credential_key_id,credential_owner_id,credential_owner_org,revision,is_active,
      created_by,updated_by,created_at,updated_at,legacy)
    SELECT p.model_definition_id,d.display_name,'llm','cloud',p.provider,'llm',p.model,
      jsonb_build_object('base_url',p.base_url,'max_tokens',p.max_tokens),p.encrypted_credentials,p.credential_key_id,
      p.model_definition_id,'00000000-0000-0000-0000-000000000000',p.revision,p.is_active,
      p.created_by,p.updated_by,p.created_at,p.updated_at,
      to_jsonb(p)-ARRAY['encrypted_credentials','credential_key_id']
    FROM device_platform.platform_model_connections p JOIN device_platform.model_definitions d ON d.id=p.model_definition_id;
    INSERT INTO device_platform.runtime_models(id,name,kind,location,provider,engine,model_key,settings)
    SELECT id,display_name,CASE WHEN provider='local_llama_cpp' THEN 'llm' ELSE 'asr' END,
      'local',provider,CASE WHEN provider='local_llama_cpp' THEN 'llm' ELSE 'local_whisper' END,model_key,'{}'
    FROM device_platform.model_definitions WHERE lifecycle='active' AND provider IN ('local_llama_cpp','local_whisper')
    ON CONFLICT(id) DO NOTHING;
    INSERT INTO device_platform.runtime_models(id,name,kind,location,provider,engine,model_key)
    VALUES(gen_random_uuid(),'eSpeak NG','tts','local','local','espeak_ng','espeak_ng'),
          (gen_random_uuid(),'OpenCV motion','video','local','local','opencv_motion','opencv_motion');
    INSERT INTO device_platform.runtime_models(id,organization_id,name,kind,location,provider,engine,model_key,
      settings,defaults,encrypted_credentials,credential_key_id,credential_owner_id,credential_owner_org,
      revision,is_active,archived_at,created_by,updated_by,created_at,updated_at,legacy)
    SELECT m.id,m.organization_id,m.name,CASE m.operation WHEN 'audio.transcribe' THEN 'asr'
      WHEN 'audio.synthesize' THEN 'tts' ELSE 'video' END,'cloud',c.provider,m.engine,
      coalesce(c.settings->>'deployment',m.engine),c.settings,m.defaults,c.encrypted_credentials,c.credential_key_id,
      c.credential_owner_id,c.credential_owner_org,m.version,m.is_active,m.archived_at,
      m.created_by,m.updated_by,m.created_at,m.updated_at,to_jsonb(m)
    FROM device_platform.media_model_configs m JOIN device_platform.runtime_models c ON c.id=m.connection_id;

    -- Replace connection FKs with the canonical model FK. Shared models have NULL tenant;
    -- an additional trigger enforces tenant ownership for tenant-specific models.
    CREATE FUNCTION device_platform.check_runtime_model_scope() RETURNS trigger
    LANGUAGE plpgsql SET search_path=device_platform,pg_temp AS $$
    DECLARE model_id uuid:=(to_jsonb(NEW)->>TG_ARGV[0])::uuid; owner_id uuid;
    BEGIN
      IF TG_OP='UPDATE' AND NEW.organization_id=OLD.organization_id
        AND (to_jsonb(NEW)->>TG_ARGV[0]) IS NOT DISTINCT FROM (to_jsonb(OLD)->>TG_ARGV[0]) THEN
        RETURN NEW;
      END IF;
      IF model_id IS NOT NULL THEN
        SELECT organization_id INTO owner_id FROM runtime_models WHERE id=model_id;
        IF owner_id IS NOT NULL AND owner_id<>NEW.organization_id THEN
          RAISE EXCEPTION 'Model belongs to another tenant' USING ERRCODE='23514';
        END IF;
      END IF;
      RETURN NEW;
    END $$;
    DO $$ DECLARE f record; col text;
    BEGIN
      FOR f IN SELECT c.oid,c.conname,c.conrelid::regclass tbl,c.conkey,c.confkey,c.confrelid
        FROM pg_constraint c WHERE c.contype='f' AND c.confrelid IN
          ('device_platform.llm_connections'::regclass,'device_platform.provider_connections'::regclass)
        AND c.conrelid<>'device_platform.media_model_configs'::regclass
      LOOP
        SELECT a.attname INTO col FROM unnest(f.conkey,f.confkey) k(local_key,foreign_key)
          JOIN pg_attribute a ON a.attrelid=f.tbl AND a.attnum=k.local_key
          JOIN pg_attribute b ON b.attrelid=f.confrelid AND b.attnum=k.foreign_key WHERE b.attname='id';
        EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I',f.tbl,f.conname);
        EXECUTE format('ALTER TABLE %s ADD CONSTRAINT %I FOREIGN KEY(%I) REFERENCES device_platform.runtime_models(id)',f.tbl,f.conname,col);
        EXECUTE format('CREATE TRIGGER %I BEFORE INSERT OR UPDATE ON %s FOR EACH ROW EXECUTE FUNCTION device_platform.check_runtime_model_scope(%L)','model_scope_'||md5(f.conname),f.tbl,col);
      END LOOP;
    END $$;
    CREATE FUNCTION device_platform.check_device_models() RETURNS trigger
    LANGUAGE plpgsql SET search_path=device_platform,pg_temp AS $$
    DECLARE k text; m runtime_models; ident uuid; snapshot record;
    BEGIN
      FOREACH k IN ARRAY ARRAY['llm','asr','tts','video'] LOOP
        ident:=(to_jsonb(NEW)->>(k||'_model_id'))::uuid;
        IF ident IS NOT NULL THEN
          SELECT * INTO STRICT m FROM runtime_models WHERE id=ident FOR SHARE;
          IF m.kind<>k OR (m.organization_id IS NOT NULL AND m.organization_id<>NEW.organization_id)
            OR (NEW.mode<>'mixed' AND m.location<>NEW.mode) THEN
            RAISE EXCEPTION 'Invalid model selection' USING ERRCODE='23514';
          END IF;
        END IF;
      END LOOP;
      IF NEW.execution_revision_id IS NOT NULL THEN
        SELECT device_id INTO snapshot FROM processing_profile_revisions WHERE id=NEW.execution_revision_id;
        IF snapshot.device_id IS DISTINCT FROM NEW.device_id THEN
          RAISE EXCEPTION 'Snapshot belongs to another device' USING ERRCODE='23514';
        END IF;
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER check_device_models BEFORE INSERT OR UPDATE ON device_platform.device_model_selections
      FOR EACH ROW EXECUTE FUNCTION device_platform.check_device_models();
    CREATE FUNCTION device_platform.guard_runtime_model_identity() RETURNS trigger
    LANGUAGE plpgsql SET search_path=device_platform,pg_temp AS $$
    BEGIN
      IF ROW(NEW.id,NEW.organization_id,NEW.kind,NEW.created_at) IS DISTINCT FROM
        ROW(OLD.id,OLD.organization_id,OLD.kind,OLD.created_at) THEN
        RAISE EXCEPTION 'Model identity and scope are immutable' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER runtime_model_identity BEFORE UPDATE ON device_platform.runtime_models
      FOR EACH ROW EXECUTE FUNCTION device_platform.guard_runtime_model_identity();

    -- Flatten each effective assignment, including inherited tenant defaults. Preserve
    -- its exact settings and keep mixed assignments until an operator explicitly edits.
    DO $$ DECLARE d record; r record; section text; part jsonb; k text; ident uuid; source_id uuid;
      ids jsonb; modes text[]; snap uuid; m device_platform.runtime_models;
    BEGIN
      FOR d IN SELECT dev.*,p.published_revision_id FROM device_platform.devices dev
        JOIN device_platform.organizations o ON o.id=dev.organization_id
        JOIN device_platform.processing_profiles p ON p.id=coalesce(dev.profile_id,o.default_profile_id)
        WHERE p.is_active AND p.archived_at IS NULL AND p.published_revision_id IS NOT NULL
      LOOP
        SELECT * INTO r FROM device_platform.processing_profile_revisions WHERE id=d.published_revision_id;
        ids:='{}'; modes:=ARRAY[]::text[];
        IF r.llm_connection_id IS NOT NULL THEN
          ids:=jsonb_build_object('llm',r.llm_connection_id);
          SELECT * INTO m FROM device_platform.runtime_models WHERE id=r.llm_connection_id;
          modes:=array_append(modes,m.location);
        END IF;
        FOREACH section IN ARRAY ARRAY['audio_input','audio_output','video'] LOOP
          part:=r.settings->section;
          IF part->>'enabled'='true' THEN
            k:=CASE section WHEN 'audio_input' THEN 'asr' WHEN 'audio_output' THEN 'tts' ELSE 'video' END;
            ident:=md5(r.id::text||':'||section)::uuid;
            source_id:=(to_jsonb(r)->>(section||'_connection_id'))::uuid;
            IF source_id IS NOT NULL THEN
              SELECT * INTO m FROM device_platform.runtime_models WHERE id=source_id;
              INSERT INTO device_platform.runtime_models(id,organization_id,name,kind,location,provider,engine,
                model_key,settings,defaults,legacy,encrypted_credentials,credential_key_id,credential_owner_id,
                credential_owner_org,is_active)
              VALUES(ident,d.organization_id,left(m.name||' · '||k,100),k,'cloud',m.provider,part->>'engine',
                coalesce(part->>'model',m.settings->>'deployment',part->>'engine'),m.settings,
                CASE k WHEN 'tts' THEN jsonb_strip_nulls(jsonb_build_object('language',part->'language','voice',part->'voice','format',part->'format')) WHEN 'asr' THEN jsonb_strip_nulls(jsonb_build_object('language',part->'language')) ELSE '{}'::jsonb END,
                jsonb_build_object('section',part),m.encrypted_credentials,m.credential_key_id,
                m.credential_owner_id,m.credential_owner_org,m.is_active)
              ON CONFLICT(id) DO NOTHING;
            ELSE
              INSERT INTO device_platform.runtime_models(id,organization_id,name,kind,location,provider,engine,model_key,defaults,legacy)
              VALUES(ident,d.organization_id,left(coalesce(part->>'model',part->>'engine')||' · '||k,100),k,'local',
                CASE k WHEN 'asr' THEN 'local_whisper' ELSE 'local' END,part->>'engine',
                coalesce(part->>'model',part->>'engine'),
                CASE k WHEN 'tts' THEN jsonb_strip_nulls(jsonb_build_object('language',part->'language','voice',part->'voice','format',part->'format')) WHEN 'asr' THEN jsonb_strip_nulls(jsonb_build_object('language',part->'language')) ELSE '{}'::jsonb END,
                jsonb_build_object('section',part)) ON CONFLICT(id) DO NOTHING;
            END IF;
            ids:=ids||jsonb_build_object(k,ident);
            modes:=array_append(modes,part->>'execution_mode');
          END IF;
        END LOOP;
        snap:=gen_random_uuid();
        INSERT INTO device_platform.processing_profile_revisions(id,organization_id,device_id,version,settings,
          llm_connection_id,audio_input_connection_id,audio_output_connection_id,video_connection_id,published_by,change_note)
        VALUES(snap,d.organization_id,d.id,1,r.settings,(ids->>'llm')::uuid,
          CASE WHEN r.audio_input_connection_id IS NOT NULL THEN (ids->>'asr')::uuid END,
          CASE WHEN r.audio_output_connection_id IS NOT NULL THEN (ids->>'tts')::uuid END,
          CASE WHEN r.video_connection_id IS NOT NULL THEN (ids->>'video')::uuid END,r.published_by,'Direct model migration');
        INSERT INTO device_platform.device_model_selections(device_id,organization_id,mode,llm_model_id,asr_model_id,
          tts_model_id,video_model_id,execution_revision_id,updated_by)
        VALUES(d.id,d.organization_id,CASE WHEN 'local'=ANY(modes) AND 'cloud'=ANY(modes) THEN 'mixed'
          WHEN 'local'=ANY(modes) THEN 'local' ELSE 'cloud' END,(ids->>'llm')::uuid,(ids->>'asr')::uuid,
          (ids->>'tts')::uuid,(ids->>'video')::uuid,snap,r.published_by);
        UPDATE device_platform.devices SET profile_id=NULL WHERE id=d.id;
      END LOOP;
    END $$;
    -- These two configuration tables have no execution history of their own.
    -- Read-only views preserve old metadata readers without duplicate storage.
    DROP TABLE device_platform.media_model_configs;
    CREATE VIEW device_platform.media_model_configs AS
      SELECT id,organization_id,(legacy->>'connection_id')::uuid AS connection_id,name,engine,
        CASE kind WHEN 'asr' THEN 'audio.transcribe' WHEN 'tts' THEN 'audio.synthesize' ELSE 'video.labels' END AS operation,
        defaults,is_active,archived_at,revision AS version,created_by,updated_by,created_at,updated_at
      FROM device_platform.runtime_models WHERE legacy ? 'connection_id' AND kind IN ('asr','tts','video');
    DROP TABLE device_platform.platform_model_connections;
    CREATE VIEW device_platform.platform_model_connections AS
      SELECT id AS model_definition_id,provider,settings->>'base_url' AS base_url,model_key AS model,
        encrypted_credentials,credential_key_id,coalesce((settings->>'max_tokens')::integer,1024) AS max_tokens,
        revision,is_active,(legacy->>'tested_at')::timestamptz AS tested_at,(legacy->>'tested_revision')::integer AS tested_revision,
        created_by,updated_by,created_at,updated_at
      FROM device_platform.runtime_models WHERE legacy ? 'model_definition_id' AND organization_id IS NULL;
    REVOKE ALL ON device_platform.runtime_models,device_platform.device_model_selections FROM PUBLIC;
    REVOKE ALL ON FUNCTION device_platform.sync_legacy_runtime_model(),
      device_platform.check_runtime_model_scope(),device_platform.check_device_models(),
      device_platform.guard_runtime_model_identity() FROM PUBLIC;
    """)


def downgrade():
    raise RuntimeError("Restore a backup; model and execution history must be preserved")
