"""Simplified authoring, durable cleanup, and current clinical publication."""

from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb
from pydantic import ValidationError
from scenario_samples import example
from test_default_local_models import run_upgrade, upgrade_database  # noqa: F401
from test_scenario_library import library as library
from test_scenario_library import publication
from training_contracts import fingerprint
from training_contracts.clinical_cases import ClinicalRuntime, ScenarioDraftV4, simplify_case
from training_contracts.conversation.prompt import conversation_context
from training_contracts.localized_cases import convert_v2, review_localization
from training_contracts.scenarios import validate_publication

from pms_api.modules.scenario_schemas import DraftCreate, DraftSave
from pms_api.modules.scenarios import require_runtime


def clinical():
    return simplify_case(example())


@pytest.mark.parametrize("field", ["dialogue", "instructor", "fact_disclosure"])
def test_removed_sections_are_rejected_on_every_authoring_write(field):
    document = {**clinical(), field: {}}
    for model, body in (
        (ScenarioDraftV4, document),
        (DraftCreate, {"request_key": uuid4(), "code": document["code"], "document": document}),
        (DraftSave, {"expected_revision": 1, "document": document}),
    ):
        with pytest.raises(ValidationError):
            model.model_validate(body)


def test_clinical_content_is_complete_without_question_bank_or_instructor():
    document = clinical()
    assert validate_publication(document) == []
    for language in ("en", "hi"):
        document = review_localization(document, language)
    runtime = ClinicalRuntime.model_validate(require_runtime(document))
    assert runtime.case.presentation.chief_complaint
    prompt = conversation_context(document, "en", "What happened?")["system"]
    assert document["presentation"]["chief_complaint"]["en"] in prompt
    assert document["patient"]["name"] in prompt
    assert "dialogue" not in runtime.model_dump()
    assert "instructor" not in runtime.case.model_dump()


def test_eight_vitals_only_and_no_nested_disclosure():
    assert set(ScenarioDraftV4.model_fields) == {
        "version",
        "code",
        "title",
        "learner_label",
        "specialty",
        "source_language",
        "patient",
        "presentation",
        "history",
        "vitals",
        "localizations",
    }
    for patch in (
        {"vitals": {"glucose": 100}},
        {"presentation": {"symptoms": [{"id": "pain", "disclosure": "never"}]}},
        {"history": {"allergies": {"knowledge": "none", "disclosure": "never"}}},
    ):
        with pytest.raises(ValidationError):
            ScenarioDraftV4.model_validate({**clinical(), **patch})


def test_blank_symptom_can_be_saved_but_requires_description_for_publication():
    case = ScenarioDraftV4.model_validate(
        {
            **clinical(),
            "presentation": {
                "chief_complaint": {"en": "Pain"},
                "symptoms": [{"id": "symptom_1"}],
            },
        }
    )
    assert any(
        issue.path == ["presentation", "symptoms", "0", "description"]
        for issue in validate_publication(case.model_dump(mode="json", exclude_none=True))
    )


def test_simplified_draft_review_publication_and_rejections(library):
    h, author, _, _, base = library
    document = clinical()
    created = h.call(
        "POST",
        base + "/scenario-drafts",
        author,
        expected=201,
        json={
            "request_key": str(uuid4()),
            "code": document["code"],
            "document": document,
            "specialty_id": h.test_specialty_id,
        },
    )["draft"]
    path = base + "/scenario-drafts/" + created["id"]
    for field in ("dialogue", "instructor", "fact_disclosure"):
        h.call(
            "PUT",
            path,
            author,
            expected=422,
            json={
                "expected_revision": created["revision"],
                "document": {**document, field: {}},
            },
        )
    row = h.call("POST", path + "/submit", author, json={"expected_revision": created["revision"]})
    for language in ("en", "hi"):
        body = {"expected_revision": row["revision"], "approval": publication()["approval"]}
        h.call("POST", path + f"/localizations/{language}/review", author, expected=403, json=body)
        row = h.call("POST", path + f"/localizations/{language}/review", h.reviewer_token, json=body)
    published = h.call(
        "POST", path + "/publish", h.reviewer_token, expected=201, json=publication(row["revision"])
    )["scenario"]
    assert published["schema_version"] == 4 and published["execution_supported"]
    assert not {"dialogue", "instructor", "fact_disclosure"} & published["document"].keys()
    h.call(
        "POST",
        base + "/scenarios",
        author,
        expected=405,
        json={"request_key": str(uuid4()), "scenario": example()},
    )


def test_upgrade_cleans_catalog_drafts_published_private_and_historical_context(upgrade_database):  # noqa: F811
    target = upgrade_database
    run_upgrade(target, "0040_device_unique_ids")
    org, user, draft, published, selection, conversation = [uuid4() for _ in range(6)]
    old = convert_v2(example(), review_languages=("en", "hi"))
    with psycopg.connect(target) as c:
        c.execute("SET search_path=device_platform,public")
        c.execute(
            "INSERT INTO users(id,identity_issuer,identity_subject,display_name,email,email_verified) VALUES(%s,'fixture','fixture','Operator','fixture@example.test',true)",
            (user,),
        )
        c.execute(
            "INSERT INTO organizations(id,name,policy_settings,subscription_plan_id) SELECT %s,'Clinical cleanup',default_organization_policy,(SELECT id FROM subscription_plans WHERE code='standard') FROM platform_settings",
            (org,),
        )
        c.execute(
            "INSERT INTO organization_memberships(id,organization_id,user_id,role,is_active,invitation_status,joined_at) VALUES(gen_random_uuid(),%s,%s,'org_admin',true,'accepted',now())",
            (org, user),
        )
        c.execute(
            "INSERT INTO training_scenario_drafts(id,organization_id,code,schema_version,document,request_key,request_fingerprint,created_by,updated_by) VALUES(%s,%s,%s,3,%s,gen_random_uuid(),%s,%s,%s)",
            (draft, org, old["code"], Jsonb(old), fingerprint(old), user, user),
        )
        c.execute(
            "INSERT INTO training_scenarios(id,organization_id,code,version,document,request_key,fingerprint,created_by) VALUES(%s,%s,%s,1,%s,gen_random_uuid(),%s,%s)",
            (published, org, old["code"], Jsonb(old), fingerprint(old), user),
        )
        c.execute(
            "INSERT INTO patient_practice_selections(id,organization_id,user_id,template_id,category_id,patient_identity_id,template_revision,document,language) SELECT %s,%s,%s,id,category_id,patient_identity_id,revision,%s,'en' FROM patient_case_templates ORDER BY code LIMIT 1",
            (selection, org, user, Jsonb(old)),
        )
        context = {
            "conversation_id": str(conversation),
            "organization_id": str(org),
            "owner_id": str(user),
            "practice_id": str(selection),
        }
        c.execute(
            "INSERT INTO patient_conversations(id,organization_id,user_id,request_key,fingerprint,practice_id,context,snapshot,status,created_at,expires_at) VALUES(%s,%s,%s,gen_random_uuid(),%s,%s,%s,%s,'active',now(),now()+interval '1 hour')",
            (
                conversation,
                org,
                user,
                fingerprint(old),
                selection,
                Jsonb(context),
                Jsonb({"system": "Legacy question bank content", "language": "en"}),
            ),
        )
    run_upgrade(target, "0041_simple_clinical_cases")
    with psycopg.connect(target) as c:
        for table in (
            "patient_case_templates",
            "training_scenario_drafts",
            "training_scenarios",
            "patient_practice_selections",
        ):
            rows = c.execute(f"SELECT document FROM device_platform.{table}").fetchall()
            assert rows
            for (document,) in rows:
                ScenarioDraftV4.model_validate(document)
                assert not {"dialogue", "instructor", "fact_disclosure"} & document.keys()
        document, digest = c.execute(
            "SELECT document,fingerprint FROM device_platform.training_scenarios WHERE id=%s", (published,)
        ).fetchone()
        assert document["history"]["allergies"]["knowledge"] == old["history"]["allergies"]["knowledge"]
        assert digest == fingerprint(document)
        assert require_runtime(document)
        snapshot, status = c.execute(
            "SELECT snapshot,status FROM device_platform.patient_conversations WHERE id=%s", (conversation,)
        ).fetchone()
        assert status == "closed" and "system" not in snapshot and snapshot["scenario_context_removed"]
        for patch in (
            {"dialogue": {}},
            {"instructor": {}},
            {"fact_disclosure": {}},
            {"vitals": {"glucose": 10}},
        ):
            with pytest.raises(psycopg.errors.CheckViolation), c.transaction():
                c.execute(
                    "UPDATE device_platform.training_scenario_drafts SET document=document || %s WHERE id=%s",
                    (Jsonb(patch), draft),
                )
    run_upgrade(target, "0041_simple_clinical_cases")


def test_format_upgrade_repairs_only_previously_current_untouched_sources(upgrade_database):  # noqa: F811
    target = upgrade_database
    run_upgrade(target, "0040_device_unique_ids")
    org, user, specialty, patient, case_id, selection = [uuid4() for _ in range(6)]
    drafts = {kind: uuid4() for kind in ("current", "stale", "edited")}
    document = convert_v2(example(), review_languages=("en", "hi"))
    with psycopg.connect(target) as c:
        c.execute("SET search_path=device_platform,public")
        c.execute(
            "INSERT INTO users(id,identity_issuer,identity_subject,display_name,email,email_verified) VALUES(%s,'fixture','fixture','Operator','fixture@example.test',true)",
            (user,),
        )
        c.execute(
            "INSERT INTO organizations(id,name,policy_settings,subscription_plan_id) SELECT %s,'Source references',default_organization_policy,(SELECT id FROM subscription_plans WHERE code='standard') FROM platform_settings",
            (org,),
        )
        c.execute(
            "INSERT INTO organization_memberships(id,organization_id,user_id,role,is_active,invitation_status,joined_at) VALUES(gen_random_uuid(),%s,%s,'org_admin',true,'accepted',now())",
            (org, user),
        )
        c.execute(
            "INSERT INTO organization_clinical_specialties(id,organization_id,code,name,names,description) VALUES(%s,%s,'clinical','Clinical','{\"en\":\"Clinical\"}','Test specialty')",
            (specialty, org),
        )
        c.execute(
            "INSERT INTO organization_patient_profiles(id,organization_id,code,name,names,age_years,sex,occupations,height_cm,weight_kg,preferred_language,languages,backgrounds) SELECT %s,%s,code,name,names,age_years,sex,occupations,height_cm,weight_kg,preferred_language,languages,backgrounds FROM patient_identities ORDER BY code LIMIT 1",
            (patient, org),
        )
        c.execute(
            "INSERT INTO organization_case_templates(id,organization_id,code,specialty_id,patient_profile_id,title,titles,document,source_global_id,source_global_revision) SELECT %s,%s,%s,%s,%s,%s,%s,%s,id,revision FROM patient_case_templates ORDER BY code LIMIT 1",
            (
                case_id,
                org,
                document["code"],
                specialty,
                patient,
                document["title"],
                Jsonb({"en": document["title"]}),
                Jsonb(document),
            ),
        )
        c.execute("UPDATE organization_case_templates SET revision=2 WHERE id=%s", (case_id,))
        for kind, identity in drafts.items():
            copied = {**document, "code": kind, "title": "Custom author title"}
            c.execute(
                "INSERT INTO training_scenario_drafts(id,organization_id,code,schema_version,document,request_key,request_fingerprint,created_by,updated_by,source_case_id,source_case_revision) VALUES(%s,%s,%s,3,%s,gen_random_uuid(),%s,%s,%s,%s,%s)",
                (
                    identity,
                    org,
                    kind,
                    Jsonb(copied),
                    fingerprint(copied),
                    user,
                    user,
                    case_id,
                    1 if kind == "stale" else 2,
                ),
            )
        c.execute(
            "INSERT INTO patient_practice_selections(id,organization_id,user_id,tenant_template_id,tenant_category_id,tenant_patient_identity_id,template_revision,document,language) VALUES(%s,%s,%s,%s,%s,%s,2,%s,'en')",
            (selection, org, user, case_id, specialty, patient, Jsonb(document)),
        )
    run_upgrade(target, "0041_simple_clinical_cases")
    with psycopg.connect(target) as c:
        c.execute(
            "UPDATE device_platform.training_scenario_drafts SET document=jsonb_set(document,'{title}','\"Edited after migration\"'), revision=2 WHERE id=%s",
            (drafts["edited"],),
        )
        snapshots = dict(
            c.execute("SELECT id,document FROM device_platform.training_scenario_drafts").fetchall()
        )
    run_upgrade(target)
    with psycopg.connect(target) as c:
        refs = {
            code: (source, revision)
            for code, source, revision in c.execute(
                "SELECT code,source_case_revision,revision FROM device_platform.training_scenario_drafts"
            ).fetchall()
        }
        assert refs == {"current": (3, 3), "stale": (1, 2), "edited": (2, 3)}
        assert (
            dict(c.execute("SELECT id,document FROM device_platform.training_scenario_drafts").fetchall())
            == snapshots
        )
        assert c.execute(
            "SELECT c.source_global_revision=g.revision FROM device_platform.organization_case_templates c JOIN device_platform.patient_case_templates g ON g.id=c.source_global_id"
        ).fetchone() == (True,)
        assert c.execute(
            "SELECT template_revision,revision FROM device_platform.patient_practice_selections WHERE id=%s",
            (selection,),
        ).fetchone() == (3, 3)
        assert c.execute(
            "SELECT count(*) FROM pg_trigger WHERE tgname IN ('training_draft_guard','organization_case_templates_guard','patient_selection_guard') AND tgenabled<>'O'"
        ).fetchone() == (0,)
    run_upgrade(target)
