"""Tenant wizard provisioning is atomic and keeps transferred device history private."""

from copy import deepcopy
from uuid import uuid4

import psycopg
import pytest
from training_contracts.clinical_cases import ClinicalRuntime
from training_contracts.localized_cases import localization_ready
from training_contracts.scenarios import validate_publication

from pms_api.modules.patient_catalog_schemas import CaseInput
from pms_api.modules.scenarios import require_runtime


def _plan(h):
    return str(h.sql("SELECT id FROM device_platform.subscription_plans WHERE code='standard'")[0][0])


def test_new_tenant_admin_and_device_are_ready_together(platform):
    h = platform
    administrator, _ = h.admin("provision-operator")
    password = "test-only-tenant-password-2026"
    created = h.call(
        "POST",
        "/platform/organizations/provision",
        administrator,
        expected=201,
        json={
            "tenant": {"name": "Wizard hospital", "subscription_plan_id": _plan(h)},
            "device": {
                "kind": "new",
                "name": "Simulation manikin",
                "device_unique_id": str(uuid4()),
                "device_type": "manikin",
            },
            "administrator": {
                "kind": "new",
                "display_name": "Hospital admin",
                "email": "wizard-admin@example.com",
                "password": password,
            },
        },
    )
    org = created["tenant"]["id"]
    assert created["tenant"]["is_active"]
    assert created["device"]["organization_id"] == org
    assert created["device"]["device_type"] == "manikin"
    assert created["device"]["enrollment_state"] == "pending"
    assert h.sql(
        "SELECT role,invitation_status,is_active FROM device_platform.organization_memberships "
        "WHERE organization_id=%s",
        (org,),
    ) == [("org_admin", "accepted", True)]
    login = h.call("POST", "/auth/login", json={"email": "wizard-admin@example.com", "password": password})
    assert login["user"]["id"] == created["administrator"]["id"]
    profiles = h.call("GET", f"/organizations/{org}/clinical-catalog/patients", login["access_token"])
    assert profiles["total"] == 1
    assert profiles["items"][0]["code"] == "alex"
    assert not profiles["items"][0]["is_active"]
    specialties = h.call("GET", f"/organizations/{org}/clinical-catalog/specialties", login["access_token"])
    assert specialties["total"] == 3
    assert {item["code"] for item in specialties["items"]} == {
        "cardiology",
        "nephrology",
        "respiratory_medicine",
    }
    assert all(item["is_active"] for item in specialties["items"])
    cases = h.call("GET", f"/organizations/{org}/clinical-catalog/cases", login["access_token"])
    assert cases["total"] == 2
    assert {item["code"] for item in cases["items"]} == {"alex_chest_discomfort", "alex_wheeze"}
    assert all(not item["is_active"] for item in cases["items"])
    assert {item["patient_profile_id"] for item in cases["items"]} == {profiles["items"][0]["id"]}
    specialty_ids = {item["code"]: item["id"] for item in specialties["items"]}
    case_specialties = {item["code"]: item["specialty_id"] for item in cases["items"]}
    assert case_specialties == {
        "alex_chest_discomfort": specialty_ids["cardiology"],
        "alex_wheeze": specialty_ids["respiratory_medicine"],
    }
    for item in cases["items"]:
        detail = h.call(
            "GET", f"/organizations/{org}/clinical-catalog/cases/{item['id']}", login["access_token"]
        )
        document = detail["document"]
        assert document["version"] == 5
        assert len(document["background"]) == 4
        assert document["presentation"]["onset"] != document["presentation"]["duration"]
        assert detail["source_global_revision"] == 6
        assert document["localizations"] == {}
        background = {entry["id"]: entry["text"]["en"] for entry in document["background"]}
        assert "eight hours" in background["sleep_activity"]
        assert "five days" in background["work_home"]
        assert all(key in document for key in ("presentation", "history", "vitals"))
        assert not {"dialogue", "instructor", "fact_disclosure"} & document.keys()
        assert document["patient"]["name"] == "Alex"
        assert document["specialty"] in {"Cardiology", "Respiratory Medicine"}
        assert document["presentation"]["chief_complaint"]["en"]
        assert document["presentation"]["chief_complaint"]["hi"]
        assert validate_publication(document) == []
    assert h.sql(
        "SELECT count(*) FROM device_platform.activity_events "
        "WHERE organization_id=%s AND event_type='platform.organization.case_draft_seeded'",
        (org,),
    ) == [(2,)]
    published = h.call(
        "GET", f"/organizations/{org}/training/scenarios?schema_version=all&status=all", login["access_token"]
    )["items"]
    assert {item["code"] for item in published} == {"alex_chest_discomfort", "alex_wheeze"}
    assert all(
        item["publication_source"] == "system_starter" and item["execution_supported"] for item in published
    )
    for item in published:
        row = h.call("GET", f"/organizations/{org}/training/scenarios/{item['id']}", login["access_token"])
        assert row["approved_by"] is None and row["approval"] is None and row["approved_at"]
        assert row["starter_case_id"] in {case["id"] for case in cases["items"]}
        assert row["document"]["version"] == 5
        assert {value["status"] for value in row["document"]["localizations"].values()} == {"system_starter"}
        runtime = ClinicalRuntime.model_validate(require_runtime(row["document"]))
        assert runtime.case.version == 5
        source_case = next(case for case in cases["items"] if case["id"] == row["starter_case_id"])
        source_doc = h.call(
            "GET", f"/organizations/{org}/clinical-catalog/cases/{source_case['id']}", login["access_token"]
        )["document"]
        assert (
            runtime.case.presentation.model_dump(mode="json", exclude_none=True) == source_doc["presentation"]
        )
        h.call("GET", f"/organizations/{org}/training/scenarios/{item['id']}", administrator, expected=404)
    setup = h.call("GET", f"/organizations/{org}/patient-practice/selection", login["access_token"])
    assert setup["selection"] is None
    drafts = h.call("GET", f"/organizations/{org}/training/scenario-drafts", login["access_token"])["items"]
    assert drafts == []
    practice = h.call("GET", f"/organizations/{org}/patient-practice/scenario-options", login["access_token"])
    assert len(practice["items"]) == 2
    assert all(set(item["languages"]) == {"en", "hi"} for item in practice["items"])
    assert practice["default"]["scenario_id"] == next(
        item["id"] for item in published if item["code"] == "alex_chest_discomfort"
    )
    selected = next(item for item in practice["items"] if item["id"] == practice["default"]["scenario_id"])
    private_vitals = {**selected["vitals"], "heart_rate_bpm": selected["vitals"]["heart_rate_bpm"] + 1}
    saved = h.call(
        "PUT",
        f"/organizations/{org}/patient-practice/scenario-selection",
        login["access_token"],
        json={
            "expected_revision": 0,
            "scenario_id": selected["id"],
            "language": "en",
            "vitals": private_vitals,
        },
    )
    assert saved["selection"]["scenario_id"] == selected["id"]
    assert saved["selection"]["document"]["localizations"]["en"]["status"] == "practice_override"
    assert localization_ready(saved["selection"]["document"], "en")
    assert not localization_ready(saved["selection"]["document"], "hi")
    assert (
        h.call("GET", f"/organizations/{org}/patient-practice/scenario-selection", login["access_token"])[
            "selection"
        ]["scenario_id"]
        == selected["id"]
    )
    learner, _ = h.user("practice-learner")
    invitation = h.call(
        "POST",
        f"/organizations/{org}/invitations",
        login["access_token"],
        expected=201,
        json={"email": "practice-learner@example.com", "role": "org_user"},
    )
    h.call("POST", "/invitations/accept", learner, json={"token": invitation["invitation_token"]})
    assert (
        h.call("GET", f"/organizations/{org}/patient-practice/scenario-selection", learner)["selection"]
        is None
    )
    assert (
        len(h.call("GET", f"/organizations/{org}/patient-practice/scenario-options", learner)["items"]) == 2
    )
    h.call("GET", f"/organizations/{org}/patient-practice/selection", learner, expected=403)
    learner_choice = h.call(
        "PUT",
        f"/organizations/{org}/patient-practice/scenario-selection",
        learner,
        json={
            "expected_revision": 0,
            "scenario_id": selected["id"],
            "language": "en",
            "vitals": selected["vitals"],
        },
    )
    assert learner_choice["selection"]["scenario_id"] == selected["id"]
    assert (
        h.call("GET", f"/organizations/{org}/patient-practice/scenario-selection", learner) == learner_choice
    )
    h.call(
        "PUT",
        f"/organizations/{org}/patient-practice/scenario-default",
        learner,
        expected=403,
        json={"expected_revision": 1, "scenario_id": selected["id"], "language": "en"},
    )
    h.call(
        "PUT",
        f"/organizations/{org}/patient-practice/scenario-selection",
        learner,
        expected=409,
        json={
            "expected_revision": 0,
            "scenario_id": selected["id"],
            "language": "en",
            "vitals": selected["vitals"],
        },
    )
    retire_path = f"/organizations/{org}/training/scenarios/{selected['id']}/retire"
    h.grant_capability(login["access_token"], org, created["administrator"]["id"], "org.clinical.review")
    h.call("POST", retire_path, login["access_token"], expected=409)
    replacement = next(item for item in practice["items"] if item["id"] != selected["id"])
    new_default = h.call(
        "PUT",
        f"/organizations/{org}/patient-practice/scenario-default",
        login["access_token"],
        json={"expected_revision": 1, "scenario_id": replacement["id"], "language": "en"},
    )
    assert new_default["default"]["revision"] == 2
    h.call("POST", retire_path, login["access_token"])
    assert setup["default"] == {
        "template_id": next(item["id"] for item in cases["items"] if item["code"] == "alex_chest_discomfort"),
        "category_id": specialty_ids["cardiology"],
        "patient_identity_id": profiles["items"][0]["id"],
        "language": "en",
        "revision": 1,
    }
    assert (
        str(
            h.sql(
                "SELECT source_global_id FROM device_platform.organization_patient_profiles "
                "WHERE organization_id=%s",
                (org,),
            )[0][0]
        )
        == "00000000-0000-4000-8000-000000000401"
    )
    practice_path = f"/organizations/{org}/patient-practice/catalog"
    assert h.call("GET", practice_path, login["access_token"])["cases"] == []
    for kind, item in (
        ("specialties", next(row for row in specialties["items"] if row["code"] == "cardiology")),
        ("specialties", next(row for row in specialties["items"] if row["code"] == "respiratory_medicine")),
        ("patients", profiles["items"][0]),
    ):
        h.call(
            "POST",
            f"/organizations/{org}/clinical-catalog/{kind}/{item['id']}/restore",
            login["access_token"],
            json={"expected_version": item["version"]},
        )
    first_case = next(row for row in cases["items"] if row["code"] == "alex_chest_discomfort")
    h.call(
        "POST",
        f"/organizations/{org}/clinical-catalog/cases/{first_case['id']}/restore",
        login["access_token"],
        json={"expected_version": first_case["version"]},
    )
    assert [row["id"] for row in h.call("GET", practice_path, login["access_token"])["cases"]] == [
        first_case["id"]
    ]
    active_case = h.call(
        "GET", f"/organizations/{org}/patient-practice/cases/{first_case['id']}", login["access_token"]
    )
    adopted = h.call(
        "PUT",
        f"/organizations/{org}/patient-practice/selection",
        login["access_token"],
        json={
            "expected_revision": 1,
            "template_id": first_case["id"],
            "template_revision": active_case["revision"],
            "category_id": specialty_ids["cardiology"],
            "patient_identity_id": profiles["items"][0]["id"],
            "language": setup["default"]["language"],
            "vitals": active_case["document"]["vitals"],
        },
    )["selection"]
    assert adopted["template_id"] == setup["default"]["template_id"]
    published_chest = next(item for item in published if item["code"] == "alex_chest_discomfort")
    published_before = h.call(
        "GET", f"/organizations/{org}/training/scenarios/{published_chest['id']}", login["access_token"]
    )["document"]
    form = {key: active_case[key] for key in CaseInput.model_fields}
    form["document"] = deepcopy(form["document"])
    form["document"]["presentation"]["chief_complaint"]["en"] = "The tenant has revised this presentation."
    revised = h.call(
        "PATCH",
        f"/organizations/{org}/clinical-catalog/cases/{first_case['id']}",
        login["access_token"],
        json={"expected_version": active_case["version"], "data": form},
    )
    assert (
        revised["document"]["presentation"]["chief_complaint"]["en"]
        == "The tenant has revised this presentation."
    )
    assert (
        h.call(
            "GET", f"/organizations/{org}/training/scenarios/{published_chest['id']}", login["access_token"]
        )["document"]
        == published_before
    )
    assert password not in str(created)


def test_existing_device_transfer_and_administrator_reuse(platform):
    h = platform
    operator, _ = h.admin("transfer-operator")
    owner, _ = h.user("transfer-origin-owner")
    source_org = h.organization(owner, "Origin hospital")["id"]
    source = h.device(
        owner,
        source_org,
        name="Reusable laptop",
        location="Private room",
        details={"notes": "Private prior tenant"},
    )
    candidate, person = h.user("reusable-tenant-admin")
    body = {
        "tenant": {"name": "Destination hospital", "subscription_plan_id": _plan(h)},
        "device": {"kind": "existing", "device_id": source["id"], "expected_etag": source["management_etag"]},
        "administrator": {"kind": "existing", "user_id": person["id"]},
    }
    h.call("POST", "/platform/organizations/provision", owner, expected=403, json=body)
    counts = h.sql("SELECT count(*) FROM device_platform.organizations")[0][0]
    stale = {**body, "device": {**body["device"], "expected_etag": "0" * 64}}
    h.call("POST", "/platform/organizations/provision", operator, expected=409, json=stale)
    assert h.sql("SELECT count(*) FROM device_platform.organizations")[0][0] == counts
    assert h.sql(
        "SELECT count(*) FROM device_platform.organization_patient_profiles p "
        "JOIN device_platform.organizations o ON o.id=p.organization_id "
        "WHERE o.name='Destination hospital'"
    ) == [(0,)]
    assert h.sql(
        "SELECT count(*) FROM device_platform.organization_clinical_specialties s "
        "JOIN device_platform.organizations o ON o.id=s.organization_id "
        "WHERE o.name='Destination hospital'"
    ) == [(0,)]
    assert h.sql(
        "SELECT count(*) FROM device_platform.organization_case_templates c "
        "JOIN device_platform.organizations o ON o.id=c.organization_id "
        "WHERE o.name='Destination hospital'"
    ) == [(0,)]
    assert h.sql(
        "SELECT count(*) FROM device_platform.training_scenarios s "
        "JOIN device_platform.organizations o ON o.id=s.organization_id "
        "WHERE o.name='Destination hospital'"
    ) == [(0,)]
    assert h.sql(
        "SELECT count(*) FROM device_platform.tenant_patient_setup_defaults d "
        "JOIN device_platform.organizations o ON o.id=d.organization_id "
        "WHERE o.name='Destination hospital'"
    ) == [(0,)]
    created = h.call("POST", "/platform/organizations/provision", operator, expected=201, json=body)
    assert created["administrator"]["id"] == person["id"]
    assert created["device"]["id"] != source["id"]
    assert created["device"]["device_unique_id"] == source["device_unique_id"]
    old = h.call("GET", f"/organizations/{source_org}/devices/{source['id']}", owner)
    assert old["enrollment_state"] == "retired" and not old["is_active"]
    fresh = h.call(
        "GET", f"/organizations/{created['tenant']['id']}/devices/{created['device']['id']}", candidate
    )
    assert fresh["location"] is None and fresh["details"] in ({}, None)
    assert "Private prior tenant" not in str(fresh)
    assert h.sql(
        "SELECT count(*) FROM device_platform.devices WHERE organization_id=%s", (created["tenant"]["id"],)
    ) == [(1,)]
    assert h.sql(
        "SELECT count(*) FROM device_platform.organization_patient_profiles WHERE organization_id=%s",
        (created["tenant"]["id"],),
    ) == [(1,)]
    assert h.sql(
        "SELECT count(*) FROM device_platform.organization_clinical_specialties WHERE organization_id=%s",
        (created["tenant"]["id"],),
    ) == [(3,)]
    assert h.sql(
        "SELECT count(*) FROM device_platform.organization_case_templates WHERE organization_id=%s",
        (created["tenant"]["id"],),
    ) == [(2,)]
    assert h.sql(
        "SELECT count(*) FROM device_platform.training_scenarios WHERE organization_id=%s",
        (created["tenant"]["id"],),
    ) == [(2,)]
    assert h.sql(
        "SELECT count(*) FROM device_platform.tenant_patient_setup_defaults WHERE organization_id=%s",
        (created["tenant"]["id"],),
    ) == [(1,)]


def test_standard_tenant_creation_seeds_independent_patient_profiles(platform):
    h = platform
    owner, _ = h.user("two-tenant-clinical-owner")
    first = h.organization(owner, "First clinical tenant")["id"]
    second = h.organization(owner, "Second clinical tenant")["id"]
    profiles = h.sql(
        "SELECT organization_id,id,code,is_active FROM device_platform.organization_patient_profiles "
        "WHERE organization_id IN (%s,%s) ORDER BY organization_id",
        (first, second),
    )
    assert len(profiles) == 2
    assert {str(row[0]) for row in profiles} == {first, second}
    assert profiles[0][1] != profiles[1][1]
    assert all(row[2] == "alex" and not row[3] for row in profiles)
    specialties = h.sql(
        "SELECT organization_id,id,code,is_active FROM device_platform.organization_clinical_specialties "
        "WHERE organization_id IN (%s,%s)",
        (first, second),
    )
    assert len(specialties) == 6
    assert all(row[3] for row in specialties)
    assert {row[2] for row in specialties} == {"cardiology", "nephrology", "respiratory_medicine"}
    assert len({row[1] for row in specialties}) == 6
    cases = h.sql(
        "SELECT organization_id,id,code,is_active,source_global_id FROM device_platform.organization_case_templates "
        "WHERE organization_id IN (%s,%s)",
        (first, second),
    )
    assert len(cases) == 4
    assert {row[2] for row in cases} == {"alex_chest_discomfort", "alex_wheeze"}
    assert len({row[1] for row in cases}) == 4
    assert all(not row[3] and row[4] is not None for row in cases)
    published_counts = h.sql(
        "SELECT organization_id,count(*) FROM device_platform.training_scenarios "
        "WHERE organization_id IN (%s,%s) GROUP BY organization_id",
        (first, second),
    )
    assert {str(org): count for org, count in published_counts} == {first: 2, second: 2}
    defaults = h.sql(
        "SELECT organization_id,case_id,specialty_id,patient_profile_id "
        "FROM device_platform.tenant_patient_setup_defaults "
        "WHERE organization_id IN (%s,%s)",
        (first, second),
    )
    assert {str(row[0]) for row in defaults} == {first, second}
    assert len({row[1] for row in defaults}) == 2
    first_default = next(row for row in defaults if str(row[0]) == first)
    second_default = next(row for row in defaults if str(row[0]) == second)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        h.sql(
            "UPDATE device_platform.tenant_patient_setup_defaults "
            "SET case_id=%s,specialty_id=%s,patient_profile_id=%s,revision=revision+1 "
            "WHERE organization_id=%s",
            (*second_default[1:], first_default[0]),
        )
    first_case = next(row[1] for row in cases if str(row[0]) == first)
    h.call("GET", f"/organizations/{second}/clinical-catalog/cases/{first_case}", owner, expected=404)
    first_cardiology = next(row[1] for row in specialties if str(row[0]) == first and row[2] == "cardiology")
    second_cardiology = next(
        row[1] for row in specialties if str(row[0]) == second and row[2] == "cardiology"
    )
    first_path = f"/organizations/{first}/clinical-catalog/specialties/{first_cardiology}"
    h.call(
        "GET", f"/organizations/{second}/clinical-catalog/specialties/{first_cardiology}", owner, expected=404
    )
    original = h.call("GET", first_path, owner)
    h.call(
        "PATCH",
        first_path,
        owner,
        json={
            "expected_version": original["version"],
            "data": {
                "code": original["code"],
                "name": original["name"],
                "names": original["names"],
                "description": "First tenant cardiology",
                "sort_order": original["sort_order"],
                "is_active": True,
            },
        },
    )
    assert h.call("GET", first_path, owner)["description"] == "First tenant cardiology"
    assert (
        h.call("GET", f"/organizations/{second}/clinical-catalog/specialties/{second_cardiology}", owner)[
            "description"
        ]
        != "First tenant cardiology"
    )
    first_profile = next(row[1] for row in profiles if str(row[0]) == first)
    h.call("GET", f"/organizations/{second}/clinical-catalog/patients/{first_profile}", owner, expected=404)


def test_pending_platform_tenant_gets_private_inactive_starter(platform):
    h = platform
    operator, _ = h.admin("pending-profile-operator")
    tenant = h.call(
        "POST",
        "/platform/organizations",
        operator,
        expected=201,
        json={"name": "Pending clinical tenant", "subscription_plan_id": _plan(h)},
    )
    assert not tenant["is_active"]
    assert h.sql(
        "SELECT code,is_active FROM device_platform.organization_patient_profiles WHERE organization_id=%s",
        (tenant["id"],),
    ) == [("alex", False)]
    assert h.sql(
        "SELECT code,is_active FROM device_platform.organization_clinical_specialties "
        "WHERE organization_id=%s ORDER BY code",
        (tenant["id"],),
    ) == [("cardiology", True), ("nephrology", True), ("respiratory_medicine", True)]
    assert h.sql(
        "SELECT code,is_active FROM device_platform.organization_case_templates "
        "WHERE organization_id=%s ORDER BY code",
        (tenant["id"],),
    ) == [("alex_chest_discomfort", False), ("alex_wheeze", False)]
    assert h.sql(
        "SELECT code,publication_source,approved_by FROM device_platform.training_scenarios "
        "WHERE organization_id=%s ORDER BY code",
        (tenant["id"],),
    ) == [
        ("alex_chest_discomfort", "system_starter", None),
        ("alex_wheeze", "system_starter", None),
    ]
    assert h.sql(
        "SELECT count(*) FROM device_platform.tenant_patient_setup_defaults WHERE organization_id=%s",
        (tenant["id"],),
    ) == [(1,)]
    h.call("GET", f"/organizations/{tenant['id']}/clinical-catalog/patients", operator, expected=404)
    h.call("GET", f"/organizations/{tenant['id']}/clinical-catalog/cases", operator, expected=404)


def test_tenant_default_can_be_changed_after_activation_only_by_its_administrator(platform):
    h = platform
    admin, _ = h.user("default-administrator")
    org = h.organization(admin, "Default setup hospital")["id"]
    other_org = h.organization(admin, "Unrelated setup hospital")["id"]
    base = f"/organizations/{org}"
    catalog = base + "/clinical-catalog"
    specialty = next(
        item
        for item in h.call("GET", catalog + "/specialties", admin)["items"]
        if item["code"] == "respiratory_medicine"
    )
    profile = h.call("GET", catalog + "/patients", admin)["items"][0]
    case = next(
        item for item in h.call("GET", catalog + "/cases", admin)["items"] if item["code"] == "alex_wheeze"
    )
    for kind, item in (("specialties", specialty), ("patients", profile), ("cases", case)):
        if item["is_active"]:
            continue
        h.call(
            "POST",
            f"{catalog}/{kind}/{item['id']}/restore",
            admin,
            json={"expected_version": item["version"]},
        )
    staff, person = h.user("default-staff")
    invitation = h.call(
        "POST",
        base + "/invitations",
        admin,
        expected=201,
        json={"email": person["email"], "role": "org_user"},
    )
    h.call("POST", "/invitations/accept", staff, json={"token": invitation["invitation_token"]})
    h.grant_capability(admin, org, person["id"], "org.clinical.author")
    body = {
        "expected_revision": 1,
        "template_id": case["id"],
        "template_revision": case["version"] + 1,
        "language": "en",
    }
    h.call("PUT", base + "/patient-practice/default", staff, expected=403, json=body)
    h.call(
        "PUT",
        base + "/patient-practice/default",
        admin,
        expected=409,
        json={**body, "template_revision": case["version"]},
    )
    foreign_case = h.call("GET", f"/organizations/{other_org}/clinical-catalog/cases", admin)["items"][0]
    h.call(
        "PUT",
        base + "/patient-practice/default",
        admin,
        expected=404,
        json={**body, "template_id": foreign_case["id"]},
    )
    changed = h.call("PUT", base + "/patient-practice/default", admin, json=body)["default"]
    assert changed["template_id"] == case["id"] and changed["revision"] == 2
    h.call("PUT", base + "/patient-practice/default", admin, expected=409, json=body)
    assert h.call("GET", base + "/patient-practice/selection", staff)["default"] == changed


@pytest.mark.parametrize(
    ("table", "source_id", "error"),
    [
        ("scenario_categories", 301, "clinical_starters_unavailable"),
        ("patient_identities", 401, "patient_starter_unavailable"),
        ("patient_case_templates", 501, "case_starters_unavailable"),
    ],
)
def test_changed_global_starter_cannot_be_copied_into_new_tenant(platform, table, source_id, error):
    h = platform
    operator, _ = h.admin("changed-starter-operator")
    change = (
        "is_active=false, revision=revision+1" if table == "patient_case_templates" else "is_active=false"
    )
    h.sql(
        f"UPDATE device_platform.{table} SET {change} WHERE id=%s",
        (f"00000000-0000-4000-8000-{source_id:012d}",),
    )
    created = h.call(
        "POST",
        "/platform/organizations/provision",
        operator,
        expected=503,
        json={
            "tenant": {"name": "Changed starter hospital", "subscription_plan_id": _plan(h)},
            "device": {
                "kind": "new",
                "name": "Uncreated laptop",
                "device_unique_id": str(uuid4()),
                "device_type": "laptop",
            },
            "administrator": {
                "kind": "new",
                "display_name": "Uncreated admin",
                "email": "uncreated-admin@example.com",
                "password": "test-only-tenant-password-2026",
            },
        },
    )
    assert created["error"]["code"] == error
    assert h.sql(
        "SELECT count(*) FROM device_platform.organizations WHERE name='Changed starter hospital'"
    ) == [(0,)]
    assert h.sql("SELECT count(*) FROM device_platform.devices WHERE name='Uncreated laptop'") == [(0,)]
    assert h.sql("SELECT count(*) FROM device_platform.users WHERE email='uncreated-admin@example.com'") == [
        (0,)
    ]
    assert h.sql(
        "SELECT count(*) FROM device_platform.training_scenarios s "
        "JOIN device_platform.organizations o ON o.id=s.organization_id "
        "WHERE o.name='Changed starter hospital'"
    ) == [(0,)]


def test_wizard_rejects_incomplete_choices(platform):
    h = platform
    operator, _ = h.admin("invalid-wizard-operator")
    base = {
        "tenant": {"name": "Invalid wizard", "subscription_plan_id": _plan(h)},
        "administrator": {"kind": "existing", "user_id": str(uuid4())},
    }
    h.call(
        "POST",
        "/platform/organizations/provision",
        operator,
        expected=422,
        json={**base, "device": {"kind": "new", "name": "Missing type"}},
    )
    assert h.sql("SELECT count(*) FROM device_platform.organizations WHERE name='Invalid wizard'") == [(0,)]


def test_existing_account_requires_completed_setup_and_cannot_be_recreated(platform):
    h = platform
    operator, _ = h.admin("pending-operator")
    pending = h.call(
        "POST",
        "/platform/users",
        operator,
        expected=201,
        json={"display_name": "Pending administrator", "email": "pending-wizard@example.com"},
    )["user"]
    base = {
        "tenant": {"name": "Pending wizard hospital", "subscription_plan_id": _plan(h)},
        "device": {
            "kind": "new",
            "name": "Pending laptop",
            "device_unique_id": str(uuid4()),
            "device_type": "laptop",
        },
    }
    h.call(
        "POST",
        "/platform/organizations/provision",
        operator,
        expected=409,
        json={
            **base,
            "administrator": {
                "kind": "new",
                "display_name": "Duplicate local administrator",
                "email": "pending-wizard@example.com",
                "password": "test-only-tenant-password-2026",
            },
        },
    )
    h.call(
        "POST",
        "/platform/organizations/provision",
        operator,
        expected=422,
        json={**base, "administrator": {"kind": "existing", "user_id": pending["id"]}},
    )
    assert h.sql(
        "SELECT count(*) FROM device_platform.organizations WHERE name='Pending wizard hospital'"
    ) == [(0,)]
    assert h.sql("SELECT count(*) FROM device_platform.devices WHERE name='Pending laptop'") == [(0,)]
