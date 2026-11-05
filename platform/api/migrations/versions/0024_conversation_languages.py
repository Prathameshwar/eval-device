"""Generic case localizations and scoped immutable conversation contexts."""

from alembic import op

revision = "0024_conversation_languages"
down_revision = "0023_patient_conversation"
branch_labels = None
depends_on = None


def upgrade():
    c = op.get_bind().connection.driver_connection
    c.execute(
        """
        CREATE FUNCTION device_platform.valid_language_map(value jsonb, maximum integer)
          RETURNS boolean LANGUAGE sql IMMUTABLE STRICT SET search_path=pg_catalog AS $$
          SELECT CASE WHEN jsonb_typeof(value)='object' THEN
            (SELECT count(*) BETWEEN 1 AND 8 AND bool_and(
              key ~ '^[a-z]{2,3}(-[A-Z][a-z]{3})?(-[A-Z]{2}|-[0-9]{3})?$'
              AND jsonb_typeof(v)='string' AND length(v #>> '{}') BETWEEN 1 AND maximum
              AND length(btrim(v #>> '{}'))>0)
             FROM jsonb_each(value) AS x(key,v)) ELSE false END
        $$;
        CREATE FUNCTION device_platform.valid_language_list(value text[], preferred text)
          RETURNS boolean LANGUAGE sql IMMUTABLE STRICT SET search_path=pg_catalog AS $$
          SELECT array_ndims(value)=1 AND array_lower(value,1)=1
            AND cardinality(value) BETWEEN 1 AND 8 AND array_position(value,NULL) IS NULL
            AND preferred=ANY(value) AND cardinality(value)=(SELECT count(DISTINCT v) FROM unnest(value) AS v)
            AND (SELECT bool_and(v ~ '^[a-z]{2,3}(-[A-Z][a-z]{3})?(-[A-Z]{2}|-[0-9]{3})?$') FROM unnest(value) AS v)
        $$;
        ALTER TABLE device_platform.scenario_categories ADD COLUMN names jsonb;
        UPDATE device_platform.scenario_categories SET names=jsonb_build_object('en',name,'hi',name_hi);
        ALTER TABLE device_platform.scenario_categories ALTER COLUMN names SET NOT NULL, DROP COLUMN name_hi;
        ALTER TABLE device_platform.patient_identities
          ADD COLUMN names jsonb, ADD COLUMN occupations jsonb, ADD COLUMN backgrounds jsonb;
        UPDATE device_platform.patient_identities SET names=jsonb_build_object('en',name,'hi',name_hi),
          occupations=jsonb_build_object('en',occupation_en,'hi',occupation_hi),
          backgrounds=jsonb_build_object('en',background_en,'hi',background_hi);
        ALTER TABLE device_platform.patient_identities
          ALTER COLUMN names SET NOT NULL, ALTER COLUMN occupations SET NOT NULL,
          ALTER COLUMN backgrounds SET NOT NULL, DROP COLUMN name_hi,
          DROP COLUMN occupation_en, DROP COLUMN occupation_hi, DROP COLUMN background_en, DROP COLUMN background_hi;
        ALTER TABLE device_platform.patient_case_templates ADD COLUMN titles jsonb;
        UPDATE device_platform.patient_case_templates SET titles=jsonb_build_object('en',title,'hi',title_hi), revision=revision+1;
        ALTER TABLE device_platform.patient_case_templates ALTER COLUMN titles SET NOT NULL, DROP COLUMN title_hi;
        ALTER TABLE device_platform.scenario_categories ADD CHECK(device_platform.valid_language_map(names,120) AND octet_length(names::text)<=8192);
        ALTER TABLE device_platform.patient_identities
          DROP CONSTRAINT patient_identities_preferred_language_check,
          DROP CONSTRAINT patient_identities_check,
          ADD CHECK(device_platform.valid_language_list(languages,preferred_language) IS TRUE),
          ADD CHECK(names ?& languages AND occupations ?& languages AND backgrounds ?& languages),
          ADD CHECK(device_platform.valid_language_map(names,120) AND octet_length(names::text)<=8192),
          ADD CHECK(device_platform.valid_language_map(occupations,600) AND octet_length(occupations::text)<=16384),
          ADD CHECK(device_platform.valid_language_map(backgrounds,600) AND octet_length(backgrounds::text)<=65536);
        ALTER TABLE device_platform.patient_case_templates ADD CHECK(device_platform.valid_language_map(titles,160) AND octet_length(titles::text)<=8192);
        INSERT INTO device_platform.activity_events
          (id,actor_type,category,event_type,severity,entity_type,occurred_at,received_at,details,expires_at)
        SELECT gen_random_uuid(),'system','audit','platform.case_localizations.converted','info',
          'platform',now(),now(),jsonb_build_object('revision','0024_conversation_languages','source','migration'),
          now()+least((p.default_organization_policy->>'audit_retention_days')::integer,
                      (p.policy_limits->>'audit_retention_days')::integer)*interval '1 day'
        FROM device_platform.platform_settings p WHERE id=1;

        DO $$ DECLARE tbl text; item record; removed integer; BEGIN
          FOREACH tbl IN ARRAY ARRAY['patient_case_templates','patient_practice_selections','training_scenarios'] LOOP
            removed := 0;
            FOR item IN SELECT conname FROM pg_constraint
              WHERE conrelid=format('device_platform.%I',tbl)::regclass AND contype='c'
                AND pg_get_constraintdef(oid) LIKE '%octet_length%'
                AND pg_get_constraintdef(oid) LIKE '%document%'
            LOOP
              EXECUTE format('ALTER TABLE device_platform.%I DROP CONSTRAINT %I',tbl,item.conname);
              removed := removed+1;
            END LOOP;
            IF removed<>1 THEN RAISE EXCEPTION 'Unexpected document constraints on %',tbl; END IF;
          END LOOP;
        END $$;
        ALTER TABLE device_platform.patient_case_templates
          ADD CONSTRAINT patient_case_templates_document_check CHECK((jsonb_typeof(document)='object'
            AND octet_length(document::text)<=524288 AND document->'version' IN ('2'::jsonb,'3'::jsonb)
            AND document->>'code'=code AND document->>'title'=title) IS TRUE);
        ALTER TABLE device_platform.patient_practice_selections
          ADD CONSTRAINT patient_practice_selections_document_check CHECK((jsonb_typeof(document)='object'
            AND octet_length(document::text)<=524288 AND document->'version' IN ('2'::jsonb,'3'::jsonb)) IS TRUE);
        ALTER TABLE device_platform.training_scenario_drafts
          DROP CONSTRAINT training_scenario_drafts_schema_version_check,
          ADD CONSTRAINT training_scenario_drafts_schema_version_check CHECK(schema_version IN (1,2,3)),
          DROP CONSTRAINT training_draft_document,
          ADD CONSTRAINT training_draft_document CHECK((jsonb_typeof(document)='object'
            AND octet_length(document::text)<=524288 AND document->'version'=to_jsonb(schema_version)
            AND document->'code'=to_jsonb(code)) IS TRUE);
        ALTER TABLE device_platform.training_scenarios
          ADD CONSTRAINT training_scenarios_document_check CHECK(jsonb_typeof(document)='object'
            AND octet_length(document::text)<=524288);

        CREATE TABLE device_platform.patient_conversations (
          id uuid PRIMARY KEY,
          organization_id uuid NOT NULL REFERENCES device_platform.organizations(id),
          user_id uuid NOT NULL REFERENCES device_platform.users(id), department_id uuid,
          request_key uuid NOT NULL, fingerprint text NOT NULL CHECK(fingerprint ~ '^[a-f0-9]{64}$'),
          practice_id uuid NOT NULL,
          context jsonb NOT NULL CHECK(jsonb_typeof(context)='object' AND octet_length(context::text)<=8192),
          snapshot jsonb NOT NULL CHECK(jsonb_typeof(snapshot)='object' AND octet_length(snapshot::text)<=65536),
          status text NOT NULL CHECK(status IN ('active','closed')),
          sequence integer NOT NULL DEFAULT 0 CHECK(sequence BETWEEN 0 AND 1000),
          history jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(history)='array'
            AND jsonb_array_length(history)<=12 AND octet_length(history::text)<=65536),
          created_at timestamptz NOT NULL, expires_at timestamptz NOT NULL, closed_at timestamptz,
          UNIQUE(organization_id,user_id,id), UNIQUE(organization_id,user_id,request_key),
          FOREIGN KEY(organization_id,user_id,practice_id)
            REFERENCES device_platform.patient_practice_selections(organization_id,user_id,id),
          FOREIGN KEY(organization_id,department_id) REFERENCES device_platform.departments(organization_id,id),
          CHECK(expires_at>created_at AND expires_at<=created_at+interval '24 hours'),
          CHECK((status='active')=(closed_at IS NULL)),
          CHECK((context->>'conversation_id'=id::text AND context->>'organization_id'=organization_id::text
            AND context->>'owner_id'=user_id::text AND context->>'practice_id'=practice_id::text) IS TRUE)
        );
        CREATE INDEX patient_conversations_expiry ON device_platform.patient_conversations(expires_at,id);
        CREATE FUNCTION device_platform.patient_conversation_guard() RETURNS trigger LANGUAGE plpgsql
          SET search_path=pg_catalog,device_platform AS $$
        BEGIN
          IF TG_OP='DELETE' THEN
            IF OLD.expires_at>clock_timestamp() THEN
              RAISE EXCEPTION 'Conversation has not expired' USING ERRCODE='23514';
            END IF;
            RETURN OLD;
          ELSIF TG_OP='INSERT' THEN
            IF current_setting('transaction_isolation')<>'read committed' THEN
              RAISE EXCEPTION 'Conversation creation requires READ COMMITTED' USING ERRCODE='25000';
            END IF;
            PERFORM 1 FROM device_platform.organizations WHERE id=NEW.organization_id FOR UPDATE;
            IF (SELECT count(*) FROM device_platform.patient_conversations
                WHERE organization_id=NEW.organization_id AND user_id=NEW.user_id)>=100 THEN
              RAISE EXCEPTION 'Conversation capacity reached' USING ERRCODE='23514';
            END IF;
            IF NEW.sequence<>0 OR NEW.history<>'[]'::jsonb OR NEW.status<>'active' THEN
              RAISE EXCEPTION 'Invalid initial conversation state' USING ERRCODE='23514';
            END IF;
          ELSE
            IF (NEW.id,NEW.organization_id,NEW.user_id,NEW.department_id,NEW.request_key,NEW.fingerprint,
                NEW.practice_id,NEW.context,NEW.snapshot,NEW.created_at,NEW.expires_at)
              IS DISTINCT FROM (OLD.id,OLD.organization_id,OLD.user_id,OLD.department_id,OLD.request_key,
                OLD.fingerprint,OLD.practice_id,OLD.context,OLD.snapshot,OLD.created_at,OLD.expires_at) THEN
              RAISE EXCEPTION 'Conversation context is immutable' USING ERRCODE='23514';
            END IF;
            IF OLD.status='closed' OR NEW.sequence<OLD.sequence OR NEW.sequence>OLD.sequence+1 THEN
              RAISE EXCEPTION 'Invalid conversation transition' USING ERRCODE='23514';
            END IF;
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER patient_conversation_guard BEFORE INSERT OR UPDATE OR DELETE
          ON device_platform.patient_conversations FOR EACH ROW EXECUTE FUNCTION device_platform.patient_conversation_guard();
        REVOKE ALL ON device_platform.patient_conversations FROM PUBLIC;
        REVOKE ALL ON FUNCTION device_platform.patient_conversation_guard() FROM PUBLIC;

        ALTER TABLE device_platform.llm_requests ADD COLUMN conversation_id uuid,
          ADD COLUMN conversation_sequence integer CHECK(conversation_sequence BETWEEN 1 AND 1000),
          ADD COLUMN conversation_input text CHECK(length(conversation_input) BETWEEN 1 AND 8000),
          ADD FOREIGN KEY(organization_id,user_id,conversation_id)
            REFERENCES device_platform.patient_conversations(organization_id,user_id,id),
          ADD CHECK((conversation_id IS NULL)=(conversation_sequence IS NULL)
            AND (conversation_id IS NULL)=(conversation_input IS NULL));
        CREATE UNIQUE INDEX llm_conversation_running ON device_platform.llm_requests(conversation_id)
          WHERE status='running' AND conversation_id IS NOT NULL;
        ALTER TABLE device_platform.local_turns
          ADD COLUMN context_ref jsonb CHECK(context_ref IS NULL OR
            (jsonb_typeof(context_ref)='object' AND octet_length(context_ref::text)<=2048)),
          ADD COLUMN request_fingerprint text CHECK(request_fingerprint ~ '^[a-f0-9]{64}$'),
          DROP CONSTRAINT local_turns_language_check,
          ADD CONSTRAINT local_turns_language_check CHECK(language ~ '^[a-z]{2,3}(-[A-Z][a-z]{3})?(-[A-Z]{2}|-[0-9]{3})?$');
        ALTER TABLE device_platform.patient_practice_selections
          DROP CONSTRAINT patient_practice_selections_language_check,
          ADD CONSTRAINT patient_practice_selections_language_check CHECK(language='auto'
            OR language ~ '^[a-z]{2,3}(-[A-Z][a-z]{3})?(-[A-Z]{2}|-[0-9]{3})?$');
        """,
        prepare=False,
    )


def downgrade():
    raise RuntimeError("Use a forward migration to preserve conversation context and localized cases")
