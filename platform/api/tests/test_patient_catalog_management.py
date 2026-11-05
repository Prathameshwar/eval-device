"""Tenant clinical catalog permissions, revisions, imports, and private projections."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.engine import make_url
from test_auth_sessions import local_account

from pms_api.modules.patient_catalog_schemas import CaseInput, CategoryInput, PatientInput


def category(code="test_category"):
    return {
        "code": code,
        "name": "Test category",
        "names": {"en": "Test category"},
        "description": "Synthetic practice category",
        "sort_order": 5,
    }


def patient(code="manikin"):
    return {
        "code": code,
        "name": "Morgan",
        "names": {"en": "Morgan"},
        "age_years": 40,
        "sex": "unspecified",
        "occupations": {"en": "Teacher"},
        "height_cm": 170,
        "weight_kg": 70,
        "preferred_language": "en",
        "languages": ["en"],
        "backgrounds": {"en": "Fictional patient profile"},
    }


def owner_with_author(h, subject="content-owner", name="Clinical tenant"):
    token, user = h.user(subject)
    org = h.organization(token, name)["id"]
    member = h.call("GET", f"/organizations/{org}/members", token)["items"][0]
    h.call(
        "POST",
        f"/organizations/{org}/members/{member['id']}/capabilities",
        token,
        json={"capability": "org.clinical.author"},
    )
    return token, user, org, member["id"]


@pytest.mark.parametrize(
    "body",
    [
        {**category(), "names": {"en": "Different"}},
        {**category(), "description": "bad\x00text"},
        {**category(), "sort_order": -1},
        {**category(), "description": "   "},
    ],
)
def test_category_validation(body):
    with pytest.raises(ValueError):
        CategoryInput(**body)


@pytest.mark.parametrize(
    "body",
    [
        {**patient(), "languages": ["en", "hi"]},
        {**patient(), "height_cm": float("inf")},
        {**patient(), "preferred_language": "auto"},
    ],
)
def test_patient_validation(body):
    with pytest.raises(ValueError):
        PatientInput(**body)


def test_tenant_admin_authors_clinical_catalog_without_assignment(platform):
    h = platform
    token, _ = h.user("implicit-clinical-admin")
    org = h.organization(token, "Implicit clinical tenant")["id"]
    assert "org.clinical.author" in next(
        c["permissions"] for c in h.call("GET", "/auth/context", token)["contexts"] if c["id"] == org
    )
    assert (
        h.sql(
            "SELECT count(*) FROM device_platform.organization_member_capabilities "
            "WHERE organization_id=%s AND capability='org.clinical.author'",
            (org,),
        )[0][0]
        == 0
    )
    base = f"/organizations/{org}/clinical-catalog"
    assert (
        h.call("POST", base + "/specialties", token, expected=201, json=category())["organization_id"] == org
    )
    assert h.call("POST", base + "/patients", token, expected=201, json=patient())["organization_id"] == org
    assert h.call("GET", base + "/cases", token)["total"] == 2
    global_case, global_specialty, global_patient = h.sql(
        "SELECT id,category_id,patient_identity_id FROM device_platform.patient_case_templates "
        "ORDER BY code LIMIT 1"
    )[0]
    h.call("POST", base + f"/import/specialties/{global_specialty}", token, expected=200)
    h.call("POST", base + f"/import/patients/{global_patient}", token, expected=200)
    imported = h.call("POST", base + f"/import/cases/{global_case}", token, expected=201)
    assert imported["organization_id"] == org and "document" in imported


def test_tenant_catalog_capability_revocation_and_platform_denial(platform):
    h = platform
    owner, _, org, membership = owner_with_author(h)
    other, _, other_org, _ = owner_with_author(h, "other-content-owner", "Other tenant")
    platform_admin, _ = h.admin("platform-only")
    base = f"/organizations/{org}/clinical-catalog"
    other_base = f"/organizations/{other_org}/clinical-catalog"
    h.call("GET", "/platform/patient-catalog/categories", platform_admin, expected=404)
    h.call("GET", base + "/specialties", platform_admin, expected=404)
    h.call("GET", base + "/starters", platform_admin, expected=404)
    h.call(
        "GET",
        f"/organizations/{other_org}/members/{membership}/capabilities",
        other,
        expected=404,
    )
    h.call(
        "POST",
        f"/organizations/{other_org}/members/{membership}/capabilities",
        other,
        expected=404,
        json={"capability": "org.clinical.read"},
    )
    h.call("POST", base + "/specialties", platform_admin, expected=404, json=category())
    created = h.call("POST", base + "/specialties", owner, expected=201, json=category())
    assert created["organization_id"] == org and created["version"] == 1
    assert h.call("GET", base + "/specialties", owner)["total"] == 4
    assert h.call("GET", other_base + "/specialties", other)["total"] == 3
    h.call("GET", other_base + "/specialties/" + created["id"], other, expected=404)
    h.call(
        "PATCH",
        other_base + "/specialties/" + created["id"],
        other,
        expected=404,
        json={"expected_version": 1, "data": category()},
    )
    h.call(
        "POST",
        other_base + "/specialties/" + created["id"] + "/copy",
        other,
        expected=404,
        json={"code": "stolen", "name": "Stolen"},
    )
    assert "org.clinical.author" in next(
        c["permissions"] for c in h.call("GET", "/auth/context", owner)["contexts"] if c["id"] == org
    )
    h.call(
        "DELETE",
        f"/organizations/{org}/members/{membership}/capabilities/org.clinical.author",
        owner,
    )
    assert "org.clinical.author" in next(
        c["permissions"] for c in h.call("GET", "/auth/context", owner)["contexts"] if c["id"] == org
    )
    assert h.call("GET", base + "/specialties", owner)["total"] == 4
    staff_token, staff_user = h.user("content-staff")
    staff_member = str(uuid4())
    h.sql(
        "INSERT INTO device_platform.organization_memberships "
        "(id,organization_id,user_id,role,is_active,invitation_status,joined_at) "
        "VALUES (%s,%s,%s,'org_user',true,'accepted',now())",
        (staff_member, org, staff_user["id"]),
    )
    h.call(
        "POST",
        f"/organizations/{org}/members/{staff_member}/capabilities",
        owner,
        json={"capability": "org.clinical.review"},
    )
    assert h.call("GET", base + "/specialties", staff_token)["total"] == 4
    h.call("POST", base + "/specialties", staff_token, expected=403, json=category("second"))
    h.call(
        "DELETE",
        f"/organizations/{org}/members/{staff_member}/capabilities/org.clinical.review",
        owner,
    )
    h.call(
        "POST",
        f"/organizations/{org}/members/{staff_member}/capabilities",
        owner,
        json={"capability": "org.clinical.author"},
    )
    assert h.call("GET", base + "/specialties", staff_token)["total"] == 4
    h.call(
        "DELETE",
        f"/organizations/{org}/members/{staff_member}/capabilities/org.clinical.author",
        owner,
    )
    h.call("POST", base + "/specialties", staff_token, expected=403, json=category("second"))


def test_catalog_crud_versions_audit_and_concurrency(platform):
    h = platform
    owner, _, org, _ = owner_with_author(h)
    base = f"/organizations/{org}/clinical-catalog"
    created = h.call("POST", base + "/specialties", owner, expected=201, json=category())
    path = base + "/specialties/" + created["id"]
    h.call("POST", base + "/specialties", owner, expected=409, json=category())
    renamed = {**category(), "name": "Renamed", "names": {"en": "Renamed"}}
    changed = h.call("PATCH", path, owner, json={"expected_version": 1, "data": renamed})
    assert changed["version"] == 2
    h.call("PATCH", path, owner, expected=409, json={"expected_version": 1, "data": renamed})
    h.call("DELETE", path + "?expected_version=1", owner, expected=409)
    archived = h.call("DELETE", path + "?expected_version=2", owner)
    assert archived["archived_at"] and not archived["is_active"]
    restored = h.call("POST", path + "/restore", owner, json={"expected_version": 3})
    assert restored["is_active"] and restored["version"] == 4
    copied = h.call(
        "POST",
        path + "/copy",
        owner,
        expected=201,
        json={"code": "copy_category", "name": "Copy category"},
    )
    assert copied["organization_id"] == org and not copied["is_active"]
    profile = h.call("POST", base + "/patients", owner, expected=201, json=patient())
    assert profile["is_fictional"] and profile["version"] == 1
    updated = h.call(
        "PATCH",
        base + "/patients/" + profile["id"],
        owner,
        json={"expected_version": 1, "data": {**patient(), "age_years": 41}},
    )
    assert updated["age_years"] == 41 and updated["version"] == 2
    assert h.call("GET", base + "/specialties?q=Renamed", owner)["total"] == 1
    assert (
        h.sql(
            "SELECT count(*) FROM device_platform.activity_events WHERE entity_id=%s",
            (created["id"],),
        )[0][0]
        == 4
    )

    def edit(label):
        body = {**renamed, "name": label, "names": {"en": label}}
        return h.client.patch(
            "/api/v1" + path,
            headers=h.headers(owner),
            json={"expected_version": 4, "data": body},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(edit, ["First edit", "Second edit"]))
    assert sorted(statuses) == [200, 409]
    assert (
        h.sql(
            "SELECT count(*) FROM device_platform.activity_events WHERE entity_id=%s",
            (created["id"],),
        )[0][0]
        == 5
    )


def test_active_case_prevents_parent_deactivation_through_edit(platform):
    h = platform
    owner, _, org, _ = owner_with_author(h, "catalog-parent-owner", "Catalog parent tenant")
    base = f"/organizations/{org}/clinical-catalog"
    specialty = h.call(
        "POST", base + "/import/specialties/00000000-0000-4000-8000-000000000301", owner, expected=200
    )
    patient_profile = h.call(
        "POST", base + "/import/patients/00000000-0000-4000-8000-000000000401", owner, expected=200
    )
    parents = (("specialties", specialty, CategoryInput), ("patients", patient_profile, PatientInput))
    for kind, row, _ in parents:
        h.call("POST", f"{base}/{kind}/{row['id']}/restore", owner, json={"expected_version": 1})
    case = h.call("POST", base + "/import/cases/00000000-0000-4000-8000-000000000501", owner, expected=200)
    active_case = h.call("POST", f"{base}/cases/{case['id']}/restore", owner, json={"expected_version": 1})

    for kind, row, schema in parents:
        path = f"{base}/{kind}/{row['id']}"
        current = h.call("GET", path, owner)
        form = {key: current[key] for key in schema.model_fields}
        form["is_active"] = False
        rejected = h.call(
            "PATCH",
            path,
            owner,
            expected=409,
            json={"expected_version": current["version"], "data": form},
        )
        assert rejected["error"]["code"] == "catalog_in_use"
        assert h.call("GET", path, owner)["version"] == current["version"]
        assert h.call("GET", path, owner)["is_active"]

    case_path = f"{base}/cases/{case['id']}"
    case_form = {key: active_case[key] for key in CaseInput.model_fields}
    case_form["is_active"] = False
    h.call(
        "PATCH",
        case_path,
        owner,
        json={"expected_version": active_case["version"], "data": case_form},
    )
    specialty_path = f"{base}/specialties/{specialty['id']}"
    current = h.call("GET", specialty_path, owner)
    specialty_form = {key: current[key] for key in CategoryInput.model_fields}
    specialty_form["is_active"] = False
    changed = h.call(
        "PATCH",
        specialty_path,
        owner,
        json={"expected_version": current["version"], "data": specialty_form},
    )
    assert not changed["is_active"]
    rejected = h.call(
        "POST",
        case_path + "/restore",
        owner,
        expected=409,
        json={"expected_version": active_case["version"] + 1},
    )
    assert rejected["error"]["code"] == "catalog_parent_inactive"


def test_import_preserves_seeded_parents_and_reader_cannot_see_private_case(platform):
    h = platform
    owner, _, org, member = owner_with_author(h)
    base = f"/organizations/{org}/clinical-catalog"
    global_case, global_specialty, global_patient = h.sql(
        "SELECT id,category_id,patient_identity_id FROM device_platform.patient_case_templates source "
        "WHERE NOT EXISTS (SELECT 1 FROM device_platform.organization_case_templates tenant "
        "WHERE tenant.organization_id=%s AND tenant.source_global_id=source.id) "
        "ORDER BY code LIMIT 1",
        (org,),
    )[0]
    starter_items = h.call("GET", base + "/starters", owner)["items"]
    assert any(item["id"] == str(global_case) and item["kind"] == "cases" for item in starter_items)
    specialty = h.call(
        "POST",
        base + f"/import/specialties/{global_specialty}",
        owner,
        expected=200,
    )
    profile = h.call(
        "POST",
        base + f"/import/patients/{global_patient}",
        owner,
        expected=200,
    )
    # Importing an existing provisioned parent preserves its current lifecycle.
    assert specialty["is_active"] and not profile["is_active"]
    case = h.call(
        "POST",
        base + f"/import/cases/{global_case}",
        owner,
        expected=201,
    )
    assert not case["is_active"] and case["specialty_id"] == specialty["id"]
    assert case["patient_profile_id"] == profile["id"]
    assert "document" in case
    assert any(
        item["id"] == str(global_case) and item["imported"]
        for item in h.call("GET", base + "/starters", owner)["items"]
    )
    copied_case = h.call(
        "POST",
        base + "/cases/" + case["id"] + "/copy",
        owner,
        expected=201,
        json={"code": "copied_case", "title": "Copied case"},
    )
    assert copied_case["document"]["code"] == "copied_case"
    assert copied_case["document"]["title"] == "Copied case"
    assert not copied_case["is_active"]
    other, _, other_org, _ = owner_with_author(h, "import-other-owner", "Import other tenant")
    foreign_specialty = h.call(
        "POST",
        f"/organizations/{other_org}/clinical-catalog/specialties",
        other,
        expected=201,
        json=category("foreign_specialty"),
    )
    h.call(
        "POST",
        base + "/cases/validate",
        owner,
        expected=404,
        json={
            "code": case["code"],
            "specialty_id": foreign_specialty["id"],
            "patient_profile_id": profile["id"],
            "title": case["title"],
            "titles": case["titles"],
            "document": case["document"],
        },
    )
    h.call(
        "POST",
        f"/organizations/{other_org}/clinical-catalog/import/cases/{uuid4()}",
        other,
        expected=404,
    )
    h.sql(
        "UPDATE device_platform.scenario_categories "
        "SET description=description || ' reviewed change' WHERE id=%s",
        (global_specialty,),
    )
    existing_specialty = next(
        item
        for item in h.call("GET", f"/organizations/{other_org}/clinical-catalog/specialties", other)["items"]
        if item["source_global_id"] == str(global_specialty)
    )
    unchanged = h.call(
        "POST",
        f"/organizations/{other_org}/clinical-catalog/import/specialties/{global_specialty}",
        other,
        expected=200,
    )
    assert unchanged["id"] == existing_specialty["id"]
    assert unchanged["description"] == existing_specialty["description"]
    assert "document" not in h.call("GET", base + "/cases", owner)["items"][0]
    assert h.call("POST", base + f"/import/cases/{global_case}", owner)["id"] == case["id"]
    h.call(
        "POST",
        base + "/cases/validate",
        owner,
        json={
            "code": case["code"],
            "specialty_id": specialty["id"],
            "patient_profile_id": profile["id"],
            "title": case["title"],
            "titles": case["titles"],
            "document": case["document"],
        },
    )
    reader_token, reader_user = h.user("clinical-reader")
    reader_member = str(uuid4())
    h.sql(
        "INSERT INTO device_platform.organization_memberships "
        "(id,organization_id,user_id,role,is_active,invitation_status,joined_at) "
        "VALUES (%s,%s,%s,'org_read_only',true,'accepted',now())",
        (reader_member, org, reader_user["id"]),
    )
    h.call("GET", base + "/cases/" + case["id"], reader_token, expected=403)
    h.call(
        "POST",
        f"/organizations/{org}/members/{reader_member}/capabilities",
        owner,
        json={"capability": "org.clinical.read"},
    )
    reader_case = h.call("GET", base + "/cases/" + case["id"], reader_token)
    assert "document" not in reader_case
    assert "backgrounds" not in h.call("GET", base + "/patients/" + profile["id"], reader_token)
    h.call(
        "POST",
        base + "/cases",
        reader_token,
        expected=403,
        json={
            "code": case["code"],
            "specialty_id": specialty["id"],
            "patient_profile_id": profile["id"],
            "title": case["title"],
            "titles": case["titles"],
            "document": case["document"],
        },
    )
    h.call(
        "POST",
        f"/organizations/{org}/members/{reader_member}/capabilities",
        owner,
        expected=409,
        json={"capability": "org.clinical.author"},
    )
    h.sql(
        "UPDATE device_platform.organization_memberships SET role='org_trainee' WHERE id=%s",
        (reader_member,),
    )
    h.call("GET", base + "/cases/" + case["id"], reader_token, expected=403)
    assert "org.clinical.read" not in next(
        c["permissions"] for c in h.call("GET", "/auth/context", reader_token)["contexts"] if c["id"] == org
    )
    revoked = h.call(
        "DELETE",
        f"/organizations/{org}/members/{reader_member}/capabilities/org.clinical.read",
        owner,
    )
    assert revoked["revoked_at"] is not None
    h.sql(
        "UPDATE device_platform.organization_memberships SET role='org_read_only' WHERE id=%s",
        (reader_member,),
    )
    h.call("GET", base + "/cases/" + case["id"], reader_token, expected=403)
    h.sql(
        "UPDATE device_platform.organization_memberships SET is_active=false WHERE id=%s",
        (reader_member,),
    )
    h.call("GET", base + "/cases/" + case["id"], reader_token, expected=404)


def test_capability_grant_rejects_inactive_user_and_rolls_back_with_audit(platform):
    h = platform
    owner, _, org, member = owner_with_author(h, "capability-audit-owner")
    reader_token, reader_user = h.user("inactive-content-reader")
    reader_member = str(uuid4())
    h.sql(
        "INSERT INTO device_platform.organization_memberships "
        "(id,organization_id,user_id,role,is_active,invitation_status,joined_at) "
        "VALUES (%s,%s,%s,'org_user',true,'accepted',now())",
        (reader_member, org, reader_user["id"]),
    )
    path = f"/organizations/{org}/members/{reader_member}/capabilities"
    h.sql("UPDATE device_platform.users SET is_active=false WHERE id=%s", (reader_user["id"],))
    h.call("POST", path, owner, expected=409, json={"capability": "org.clinical.read"})
    h.sql("UPDATE device_platform.users SET is_active=true WHERE id=%s", (reader_user["id"],))
    role = make_url(h.settings.database_url.get_secret_value()).username
    assert role
    with psycopg.connect(h.dsn) as connection:
        connection.execute(
            sql.SQL("REVOKE INSERT ON device_platform.activity_events FROM {}").format(sql.Identifier(role))
        )
    h.call("POST", path, owner, expected=503, json={"capability": "org.clinical.read"})
    assert (
        h.sql(
            "SELECT count(*) FROM device_platform.organization_member_capabilities "
            "WHERE membership_id=%s AND capability='org.clinical.read'",
            (reader_member,),
        )[0][0]
        == 0
    )
    h.call("GET", f"/organizations/{org}/members/{member}/capabilities", owner)
    h.call("GET", f"/organizations/{org}/clinical-catalog/specialties", reader_token, expected=403)


def test_api_runtime_role_cannot_write_shared_global_catalog(platform):
    h = platform
    role = make_url(h.settings.database_url.get_secret_value()).username
    assert role
    for table in ("scenario_categories", "patient_identities", "patient_case_templates"):
        for privilege in ("INSERT", "UPDATE", "DELETE"):
            assert not h.sql(
                "SELECT has_table_privilege(%s,%s,%s)",
                (role, f"device_platform.{table}", privilege),
            )[0][0]


def test_capability_table_rejects_cross_tenant_and_unknown_codes(platform):
    h = platform
    _, user, org, member = owner_with_author(h, "capability-constraint-owner")
    _, _, other_org, _ = owner_with_author(h, "capability-constraint-other", "Constraint other")
    statement = (
        "INSERT INTO device_platform.organization_member_capabilities "
        "(id,organization_id,membership_id,capability,granted_by) VALUES (%s,%s,%s,%s,%s)"
    )
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        h.sql(statement, (str(uuid4()), other_org, member, "org.clinical.read", user["id"]))
    with pytest.raises(psycopg.errors.CheckViolation):
        h.sql(statement, (str(uuid4()), org, member, "org.fake", user["id"]))


def test_browser_session_keeps_tenant_admin_author_after_assignment_revocation(platform):
    h = platform
    _, _, login = local_account(h, browser=True)
    token = login["session_token"]
    org = h.organization(token, "Browser clinical tenant")["id"]
    member = h.call("GET", f"/organizations/{org}/members", token)["items"][0]["id"]
    path = f"/organizations/{org}/members/{member}/capabilities"
    h.call("POST", path, token, json={"capability": "org.clinical.author"})
    base = f"/organizations/{org}/clinical-catalog"
    h.call("POST", base + "/specialties", token, expected=201, json=category())
    assert "org.clinical.author" in next(
        c["permissions"] for c in h.call("GET", "/auth/context", token)["contexts"] if c["id"] == org
    )
    h.call("DELETE", path + "/org.clinical.author", token)
    assert "org.clinical.author" in next(
        c["permissions"] for c in h.call("GET", "/auth/context", token)["contexts"] if c["id"] == org
    )
    assert h.call("GET", base + "/specialties", token)["total"] == 4
    h.call("GET", "/me", token)
