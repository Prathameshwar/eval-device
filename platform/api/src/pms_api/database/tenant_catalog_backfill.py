"""Owner-only, resumable copy of selected legacy rehearsal content into tenant catalogs."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from pms_api.core.config import Settings
from pms_api.core.starter_cases import corrected_starter

HEAD = "0029_tenant_clinical_content"


@dataclass(frozen=True)
class BackfillCounts:
    organization_id: UUID
    selections: int
    legacy_selections: int
    mapped_selections: int
    specialties: int
    profiles: int
    cases: int


def _scalar(connection, query: str, values=()):
    return connection.exec_driver_sql(query, values).scalar_one()


def _check_owner_and_head(connection):
    if _scalar(connection, "SELECT version_num FROM public.alembic_version") not in {
        HEAD,
        "0030_clinical_capabilities",
        "0031_case_draft_provenance",
        "0032_tenant_import_passwords",
        "0033_tenant_training_starters",
        "0034_platform_model_connections",
        "0035_unified_scenarios",
        "0036_media_model_configs",
        "0037_direct_device_models",
        "0038_retire_model_setup",
        "0039_default_local_models",
        "0040_device_unique_ids",
        "0041_simple_clinical_cases",
        "0042_clinical_source_references",
        "0043_device_practice",
        "0044_session_queue",
        "0045_session_archives",
        "0046_patient_background",
        "0047_compact_starters",
        "0048_refined_starters",
    }:
        raise RuntimeError("Apply the reviewed tenant clinical migration first")
    if not _scalar(
        connection,
        "SELECT pg_has_role(current_user,nspowner,'MEMBER') "
        "FROM pg_namespace WHERE nspname='device_platform'",
    ):
        raise RuntimeError("The migration/schema owner is required for backfill")


def _organization_ids(connection, after: UUID | None, limit: int):
    return (
        connection.exec_driver_sql(
            "SELECT id FROM device_platform.organizations WHERE (%s::uuid IS NULL OR id > %s::uuid) "
            "AND EXISTS (SELECT 1 FROM device_platform.patient_practice_selections p "
            "WHERE p.organization_id=organizations.id AND p.template_id IS NOT NULL) "
            "ORDER BY id LIMIT %s",
            (after, after, limit),
        )
        .scalars()
        .all()
    )


def _counts(connection, organization_id: UUID) -> BackfillCounts:
    row = connection.exec_driver_sql(
        "SELECT count(*),count(*) FILTER (WHERE template_id IS NOT NULL),"
        "count(*) FILTER (WHERE template_id IS NOT NULL AND tenant_template_id IS NOT NULL) "
        "FROM device_platform.patient_practice_selections WHERE organization_id=%s",
        (organization_id,),
    ).one()
    copied = connection.exec_driver_sql(
        "SELECT "
        "(SELECT count(*) FROM device_platform.organization_clinical_specialties "
        "WHERE organization_id=%s AND source_global_id IS NOT NULL),"
        "(SELECT count(*) FROM device_platform.organization_patient_profiles "
        "WHERE organization_id=%s AND source_global_id IS NOT NULL),"
        "(SELECT count(*) FROM device_platform.organization_case_templates "
        "WHERE organization_id=%s AND source_global_id IS NOT NULL)",
        (organization_id, organization_id, organization_id),
    ).one()
    return BackfillCounts(organization_id, *row, *copied)


def _selection_fingerprints(connection, organization_id: UUID):
    return connection.exec_driver_sql(
        "SELECT id,revision,encode(sha256(convert_to(document::text,'UTF8')),'hex'),"
        "template_id,category_id,patient_identity_id "
        "FROM device_platform.patient_practice_selections WHERE organization_id=%s ORDER BY id",
        (organization_id,),
    ).all()


def _assert_source_versions(connection, organization_id: UUID):
    queries = (
        "SELECT count(*) FROM device_platform.patient_practice_selections p "
        "JOIN device_platform.scenario_categories g ON g.id=p.category_id "
        "JOIN device_platform.organization_clinical_specialties t "
        "ON t.organization_id=p.organization_id AND t.source_global_id=g.id "
        "WHERE p.organization_id=%s AND t.source_global_revision<>g.management_version",
        "SELECT count(*) FROM device_platform.patient_practice_selections p "
        "JOIN device_platform.patient_identities g ON g.id=p.patient_identity_id "
        "JOIN device_platform.organization_patient_profiles t "
        "ON t.organization_id=p.organization_id AND t.source_global_id=g.id "
        "WHERE p.organization_id=%s AND t.source_global_revision<>g.management_version",
    )
    if any(_scalar(connection, query, (organization_id,)) for query in queries):
        raise RuntimeError("A copied legacy record changed; review it before rerunning backfill")
    changes = connection.exec_driver_sql(
        "SELECT g.id,g.revision,g.document,t.source_global_revision,p.tenant_template_id=t.id "
        "FROM device_platform.patient_practice_selections p "
        "JOIN device_platform.patient_case_templates g ON g.id=p.template_id "
        "JOIN device_platform.organization_case_templates t "
        "ON t.organization_id=p.organization_id AND t.source_global_id=g.id "
        "WHERE p.organization_id=%s AND t.source_global_revision<>g.revision",
        (organization_id,),
    ).all()
    for template_id, source_revision, document, tenant_source_revision, already_mapped in changes:
        # A known bundled upgrade does not invalidate an existing tenant mapping.
        # Private snapshots and customized tenant content retain their older provenance.
        if not (
            already_mapped
            and tenant_source_revision in (4, 5)
            and corrected_starter(template_id, source_revision, document, allow_previous=True)
        ):
            raise RuntimeError("A copied legacy record changed; review it before rerunning backfill")


def _copy_tenant(connection, organization_id: UUID) -> BackfillCounts:
    connection.exec_driver_sql("SET LOCAL lock_timeout='5s'")
    connection.exec_driver_sql("SET LOCAL statement_timeout='60s'")
    connection.exec_driver_sql(
        "LOCK TABLE device_platform.scenario_categories,device_platform.patient_identities,"
        "device_platform.patient_case_templates IN SHARE MODE"
    )
    connection.exec_driver_sql(
        "LOCK TABLE device_platform.patient_practice_selections IN ACCESS EXCLUSIVE MODE"
    )
    connection.exec_driver_sql(
        "SELECT id FROM device_platform.organizations WHERE id=%s FOR UPDATE", (organization_id,)
    )
    before = _counts(connection, organization_id)
    fingerprints = _selection_fingerprints(connection, organization_id)
    if _scalar(
        connection,
        "SELECT count(*) FROM device_platform.training_sessions "
        "WHERE status IN ('authorized','active') AND expires_at>now()",
    ):
        raise RuntimeError("Stop active training before the clinical backfill")

    connection.exec_driver_sql(
        "INSERT INTO device_platform.organization_clinical_specialties "
        "(organization_id,code,name,names,description,sort_order,source_global_id,source_global_revision) "
        "SELECT %s,c.code,c.name,c.names,c.description,c.sort_order,c.id,c.management_version "
        "FROM device_platform.scenario_categories c "
        "WHERE c.id IN (SELECT DISTINCT category_id FROM device_platform.patient_practice_selections "
        "WHERE organization_id=%s AND template_id IS NOT NULL) "
        "ON CONFLICT (organization_id,source_global_id) DO NOTHING",
        (organization_id, organization_id),
    )
    connection.exec_driver_sql(
        "INSERT INTO device_platform.organization_patient_profiles "
        "(organization_id,code,name,names,age_years,sex,occupations,height_cm,weight_kg,"
        "preferred_language,languages,backgrounds,is_fictional,source_global_id,source_global_revision) "
        "SELECT %s,p.code,p.name,p.names,p.age_years,p.sex,p.occupations,p.height_cm,p.weight_kg,"
        "p.preferred_language,p.languages,p.backgrounds,p.is_fictional,p.id,p.management_version "
        "FROM device_platform.patient_identities p "
        "WHERE p.id IN (SELECT DISTINCT patient_identity_id FROM device_platform.patient_practice_selections "
        "WHERE organization_id=%s AND template_id IS NOT NULL) "
        "ON CONFLICT (organization_id,source_global_id) DO NOTHING",
        (organization_id, organization_id),
    )
    connection.exec_driver_sql(
        "INSERT INTO device_platform.organization_case_templates "
        "(organization_id,code,specialty_id,patient_profile_id,title,titles,document,is_synthetic,"
        "source_global_id,source_global_revision) "
        "SELECT %s,c.code,s.id,p.id,c.title,c.titles,c.document,c.is_synthetic,c.id,c.revision "
        "FROM device_platform.patient_case_templates c "
        "JOIN device_platform.organization_clinical_specialties s "
        "ON s.organization_id=%s AND s.source_global_id=c.category_id "
        "JOIN device_platform.organization_patient_profiles p "
        "ON p.organization_id=%s AND p.source_global_id=c.patient_identity_id "
        "WHERE c.id IN (SELECT DISTINCT template_id FROM device_platform.patient_practice_selections "
        "WHERE organization_id=%s AND template_id IS NOT NULL) "
        "ON CONFLICT (organization_id,source_global_id) DO NOTHING",
        (organization_id, organization_id, organization_id, organization_id),
    )
    _assert_source_versions(connection, organization_id)
    mismatches = _scalar(
        connection,
        "SELECT count(*) FROM device_platform.patient_practice_selections old "
        "JOIN device_platform.organization_case_templates new "
        "ON new.organization_id=old.organization_id AND new.source_global_id=old.template_id "
        "WHERE old.organization_id=%s AND old.tenant_template_id IS NOT NULL "
        "AND (old.tenant_template_id,old.tenant_category_id,old.tenant_patient_identity_id) "
        "IS DISTINCT FROM (new.id,new.specialty_id,new.patient_profile_id)",
        (organization_id,),
    )
    if mismatches:
        raise RuntimeError("An existing tenant selection mapping differs from its legacy source")
    # Trusted owner-only migration: the selection's document and observed revision remain fixed.
    # The table lock excludes API writes while the existing revision trigger is briefly disabled.
    connection.exec_driver_sql(
        "ALTER TABLE device_platform.patient_practice_selections DISABLE TRIGGER patient_selection_guard"
    )
    updated = connection.exec_driver_sql(
        "UPDATE device_platform.patient_practice_selections old "
        "SET tenant_template_id=new.id,tenant_category_id=new.specialty_id,"
        "tenant_patient_identity_id=new.patient_profile_id "
        "FROM device_platform.organization_case_templates new "
        "WHERE old.organization_id=%s AND old.template_id IS NOT NULL "
        "AND old.tenant_template_id IS NULL "
        "AND new.organization_id=old.organization_id AND new.source_global_id=old.template_id",
        (organization_id,),
    ).rowcount
    connection.exec_driver_sql(
        "ALTER TABLE device_platform.patient_practice_selections ENABLE TRIGGER patient_selection_guard"
    )
    after = _counts(connection, organization_id)
    if after.legacy_selections != after.mapped_selections or fingerprints != _selection_fingerprints(
        connection, organization_id
    ):
        raise RuntimeError("Backfill verification failed; selection history was not preserved")
    if before != after and updated:
        connection.exec_driver_sql(
            "INSERT INTO device_platform.activity_events "
            "(id,organization_id,actor_type,category,event_type,severity,entity_type,entity_id,"
            "occurred_at,received_at,details,expires_at) "
            "SELECT gen_random_uuid(),%s,'system','audit','tenant.catalog.legacy_backfilled',"
            "'info','organization',%s,now(),now(),"
            "jsonb_build_object('actor_role','system','scope',%s::text,"
            "'source','migration','revision',%s::text,'mapped_selections',%s::integer),"
            "now()+least((tenant.policy_settings->>'audit_retention_days')::integer,"
            "(settings.policy_limits->>'audit_retention_days')::integer)*interval '1 day' "
            "FROM device_platform.platform_settings settings "
            "JOIN device_platform.organizations tenant ON tenant.id=%s WHERE settings.id=1",
            (organization_id, organization_id, organization_id, HEAD, updated, organization_id),
        )
    return after


def backfill(settings: Settings, *, apply: bool, after: UUID | None, limit: int):
    if limit < 1 or limit > 100:
        raise ValueError("Limit must be between 1 and 100 organizations")
    if settings.migration_database_url is None:
        raise RuntimeError("Configure an explicit migration-owner database URL")
    engine = create_engine(
        settings.migration_database_url.get_secret_value(),
        poolclass=NullPool,
        isolation_level="READ COMMITTED",
    )
    try:
        with engine.begin() as connection:
            if not apply:
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            _check_owner_and_head(connection)
            organizations = _organization_ids(connection, after, limit)
            if not apply:
                return [_counts(connection, organization_id) for organization_id in organizations]
        results = []
        for organization_id in organizations:
            with engine.begin() as connection:
                _check_owner_and_head(connection)
                results.append(_copy_tenant(connection, organization_id))
        return results
    finally:
        engine.dispose()
