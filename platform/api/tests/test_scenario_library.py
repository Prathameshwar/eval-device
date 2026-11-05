"""API authorization, retries and transactions on disposable PostgreSQL."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest
from scenario_samples import example
from test_scenario_drafts import AuthorFixture, connect, draft
from test_training import interview as interview
from training_contracts import fingerprint

from pms_api.core.common import AppError
from pms_api.modules import scenarios


@pytest.fixture
def library(platform):
    token, user = platform.user("author")
    org = platform.organization(token)["id"]
    platform.grant_capability(token, org, user["id"], "org.clinical.author")
    specialty = platform.call(
        "POST",
        f"/organizations/{org}/clinical-catalog/specialties",
        token,
        expected=201,
        json={
            "code": "internal_teaching_category",
            "name": "Internal teaching category",
            "names": {"en": "Internal teaching category"},
            "description": "Synthetic test category",
            "sort_order": 5,
            "is_active": True,
        },
    )
    platform.test_specialty_id = specialty["id"]
    reviewer, reviewer_user = member(platform, token, org, "reviewer", "org_admin")
    platform.grant_capability(token, org, reviewer_user["id"], "org.clinical.review")
    platform.reviewer_token = reviewer
    platform.reviewer_user_id = reviewer_user["id"]
    return AuthorFixture((platform, token, user["id"], org, f"/organizations/{org}/training"))


def create(value, code="sample_cough", document=True, **extra):
    h, token, _, _, base = value
    body = {"request_key": str(uuid4()), "code": code, **extra}
    if "source_scenario_id" not in body and "source_case_id" not in body and hasattr(h, "test_specialty_id"):
        body["specialty_id"] = h.test_specialty_id
    if document:
        body["document"] = example(code)
    return h.call("POST", base + "/scenario-drafts", token, expected=201, json=body)["draft"], body


def publication(revision=1):
    return {
        "request_key": str(uuid4()),
        "expected_revision": revision,
        "approval": {
            "educator_name": "Synthetic reviewer",
            "statement": "Software test only; not clinical approval.",
        },
    }


def publish(value, row, body=None):
    h, token, _, _, base = value
    if row["workflow_version"] == 2 and row["submitted_revision"] != row["revision"]:
        row = h.call(
            "POST",
            base + f"/scenario-drafts/{row['id']}/submit",
            token,
            json={"expected_revision": row["revision"]},
        )
    body = body or publication(row["revision"])
    body["expected_revision"] = row["revision"]
    result = h.call(
        "POST", base + f"/scenario-drafts/{row['id']}/publish", h.reviewer_token, expected=201, json=body
    )
    return result["scenario"], body


def member(h, token, org, name, role="org_user", department=None):
    credential, user = h.user(name)
    body = {"email": name + "@example.com", "role": role}
    if department:
        body["department_id"] = department
    invitation = h.call("POST", f"/organizations/{org}/invitations", token, expected=201, json=body)
    h.call("POST", "/invitations/accept", credential, json={"token": invitation["invitation_token"]})
    return credential, user


def test_draft_lifecycle_and_original_request_replay(library):
    h, token, _, _, base = library
    row, original = create(library, document=False)
    path = base + f"/scenario-drafts/{row['id']}"
    validation = h.call("POST", path + "/validate", token, json={"expected_revision": 1})
    assert not validation["publishable"] and validation["errors"]
    h.call("POST", path + "/publish", h.reviewer_token, expected=422, json=publication())
    saved = h.call("PUT", path, token, json={"expected_revision": 1, "document": example()})
    assert saved["revision"] == 2 and saved["created_at"] == row["created_at"]
    replay = h.call("POST", base + "/scenario-drafts", token, json=original)
    assert replay["replayed"] and replay["draft"] == saved
    h.call("POST", base + "/scenario-drafts", token, expected=409, json={**original, "document": example()})
    h.call("PUT", path, token, expected=409, json={"expected_revision": 1, "document": example()})
    h.call("POST", path + "/validate", token, expected=409, json={"expected_revision": 1})
    archived = h.call("PATCH", path, token, json={"expected_revision": 2, "is_archived": True})
    assert archived["revision"] == 3
    h.call("PUT", path, token, expected=409, json={"expected_revision": 3, "document": example()})
    assert not h.call("POST", path + "/validate", token, json={"expected_revision": 3})["publishable"]
    h.call("POST", path + "/publish", h.reviewer_token, expected=409, json=publication(3))
    assert h.call("GET", base + "/scenario-drafts", token)["items"] == []
    assert len(h.call("GET", base + "/scenario-drafts?archived=true", token)["items"]) == 1
    restored = h.call("PATCH", path, token, json={"expected_revision": 3, "is_archived": False})
    assert restored["revision"] == 4
    response = h.call("POST", path + "/validate", token, json={"expected_revision": 4})
    assert response["publishable"] and "35" in response["preview"]["topics"][0]["answer"]["hi"]
    assert h.call("GET", path, token)["revision"] == 4


def test_publish_exact_snapshot_replay_and_retirement(library):
    h, token, user, org, base = library
    row, _ = create(library)
    case, body = publish(library, row)
    assert case["document"] == row["document"]
    assert case["fingerprint"] == fingerprint(row["document"])
    assert case["source_draft_id"] == row["id"] and case["source_draft_revision"] == 1
    assert case["created_by"] == user
    assert case["approved_by"] == h.reviewer_user_id and not case["execution_supported"]
    path = base + f"/scenario-drafts/{row['id']}"
    h.call("POST", path + "/publish", h.reviewer_token, expected=409, json=publication())
    h.call(
        "POST",
        path + "/publish",
        h.reviewer_token,
        expected=409,
        json={**body, "approval": {**body["approval"], "educator_name": "Changed name"}},
    )
    changed = example()
    changed["patient"]["age_years"] = 40
    saved = h.call("PUT", path, token, json={"expected_revision": 1, "document": changed})
    again = h.call("POST", path + "/publish", h.reviewer_token, json=body)
    assert again["replayed"] and again["scenario"] == case
    second, _ = publish(library, saved)
    assert second["version"] == 2 and second["document"] != case["document"]
    h.call("PATCH", path, token, json={"expected_revision": 2, "is_archived": True})
    retire = base + f"/scenarios/{case['id']}/retire"
    h.call("POST", retire, h.reviewer_token)
    h.call("POST", retire, h.reviewer_token)
    again = h.call("POST", path + "/publish", h.reviewer_token, json=body)
    assert again["scenario"]["id"] == case["id"] and not again["scenario"]["is_active"]
    assert (
        h.sql(
            "SELECT count(*) FROM device_platform.activity_events WHERE event_type='training.scenario.retired' AND entity_id=%s",
            (case["id"],),
        )[0][0]
        == 1
    )
    assert (
        h.sql("SELECT count(*) FROM device_platform.training_scenarios WHERE organization_id=%s", (org,))[0][
            0
        ]
        == 4
    )
    assert h.call("GET", base + "/scenarios", token)["items"] == []
    all_versions = h.call("GET", base + "/scenarios?schema_version=all", token)["items"]
    assert len(all_versions) == 4
    assert sum(row["publication_source"] == "system_starter" for row in all_versions) == 2


def test_v3_submission_requires_independent_review_of_current_revision(library):
    h, author, _, _, base = library
    starter = next(
        row
        for row in h.call("GET", base + "/scenarios?schema_version=all", author)["items"]
        if row["publication_source"] == "system_starter"
    )
    row, _ = create(library, code="reviewed_starter", document=False, source_scenario_id=starter["id"])
    path = base + f"/scenario-drafts/{row['id']}"
    assert row["workflow_version"] == 2 and row["specialty_id"] == starter["specialty_id"]
    h.call("POST", path + "/publish", h.reviewer_token, expected=409, json=publication())
    submitted = h.call("POST", path + "/submit", author, json={"expected_revision": row["revision"]})
    assert submitted["submitted_revision"] == submitted["revision"] == 2
    # A save with identical content still increments the database revision and keeps the submission current.
    saved = h.call(
        "PUT",
        path,
        author,
        json={"expected_revision": 2, "specialty_id": row["specialty_id"], "document": submitted["document"]},
    )
    assert saved["submitted_revision"] == saved["revision"] == 3
    review = {"expected_revision": 3, "approval": publication()["approval"]}
    h.call("POST", path + "/localizations/en/review", author, expected=403, json=review)
    reviewed = h.call("POST", path + "/localizations/en/review", h.reviewer_token, json=review)
    assert reviewed["submitted_revision"] == reviewed["revision"] == 4
    reviewed = h.call(
        "POST",
        path + "/localizations/hi/review",
        h.reviewer_token,
        json={"expected_revision": 4, "approval": publication()["approval"]},
    )
    assert reviewed["submitted_revision"] == reviewed["revision"] == 5
    published, _ = publish(library, reviewed)
    assert published["schema_version"] == 3 and published["execution_supported"]
    edited = dict(reviewed["document"])
    edited["title"] = "Updated after review"
    changed = h.call(
        "PUT",
        path,
        author,
        json={
            "expected_revision": reviewed["revision"],
            "specialty_id": row["specialty_id"],
            "document": edited,
        },
    )
    assert changed["submitted_revision"] is None
    h.call("POST", path + "/publish", h.reviewer_token, expected=409, json=publication(changed["revision"]))


def test_new_guided_draft_can_start_incomplete_but_cannot_be_submitted(library):
    h, author, _, _, base = library
    document = {
        "version": 3,
        "code": "new_patient_story",
        "title": "New patient story",
        "source_language": "en",
        "patient": {},
        "presentation": {"symptoms": []},
        "history": {},
        "vitals": {},
        "dialogue": {"topics": []},
        "instructor": {"objectives": [], "rubric": []},
        "fact_disclosure": {},
        "localizations": {},
    }
    row = h.call(
        "POST",
        base + "/scenario-drafts",
        author,
        expected=201,
        json={
            "request_key": str(uuid4()),
            "code": document["code"],
            "specialty_id": h.test_specialty_id,
            "document": document,
        },
    )["draft"]
    assert row["schema_version"] == 3 and row["workflow_version"] == 2
    assert row["specialty_id"] == h.test_specialty_id
    path = base + f"/scenario-drafts/{row['id']}"
    assert not h.call("POST", path + "/validate", author, json={"expected_revision": row["revision"]})[
        "publishable"
    ]
    h.call("POST", path + "/submit", author, expected=422, json={"expected_revision": row["revision"]})


@pytest.mark.parametrize("role", ["org_user", "org_read_only", "org_trainee"])
def test_role_projections_private_filters_and_every_authoring_route(library, role):
    h, token, _, org, base = library
    row, _ = create(library)
    case, _ = publish(library, row)
    dept = h.call(
        "POST", f"/organizations/{org}/departments", token, expected=201, json={"name": "Training"}
    )["id"]
    reader, _ = member(h, token, org, "reader", role, dept)
    path = base + f"/scenario-drafts/{row['id']}"
    for method, suffix, body in [
        ("GET", "/scenario-drafts", None),
        ("GET", f"/scenario-drafts/{row['id']}", None),
        ("POST", "/scenario-drafts", {"request_key": str(uuid4()), "code": "forbidden"}),
        ("PUT", f"/scenario-drafts/{row['id']}", {"expected_revision": 1, "document": example()}),
        ("PATCH", f"/scenario-drafts/{row['id']}", {"expected_revision": 1, "is_archived": True}),
        ("POST", f"/scenario-drafts/{row['id']}/validate", {"expected_revision": 1}),
        ("POST", f"/scenario-drafts/{row['id']}/publish", publication()),
        ("POST", f"/scenarios/{case['id']}/retire", None),
    ]:
        h.call(method, base + suffix, reader, expected=403, **({"json": body} if body else {}))
    summary = h.call("GET", base + "/scenarios?schema_version=all", reader)["items"][0]
    assert summary["title"] == "Patient interview A"
    assert not set(summary) & {"code", "specialty", "document", "approval", "fingerprint", "source_draft_id"}
    assert h.call("GET", base + f"/scenarios/{case['id']}", reader) == summary
    assert h.call("GET", base + "/scenarios?schema_version=all&q=Private", reader)["items"] == []
    for query in ("code=sample_cough", "specialty=Hidden", "status=all"):
        h.call("GET", base + "/scenarios?" + query, reader, expected=403)
    h.call("POST", base + f"/scenarios/{case['id']}/retire", h.reviewer_token)
    h.call("GET", base + f"/scenarios/{case['id']}", reader, expected=404)
    assert h.call("GET", path, token)["id"] == row["id"]


def test_tenant_platform_device_inactive_and_maintenance_boundaries(library):
    h, token, _, org, base = library
    row, _ = create(library)
    case, _ = publish(library, row)
    path = base + f"/scenario-drafts/{row['id']}"
    h.call("GET", path, expected=401)
    stranger, platform_admin = h.admin()
    h.call("GET", path, stranger, expected=404)
    other_org = h.organization(stranger)["id"]
    h.grant_capability(stranger, other_org, platform_admin["id"], "org.clinical.author")
    other_base = f"/organizations/{other_org}/training"
    h.call("GET", other_base + f"/scenario-drafts/{row['id']}", stranger, expected=404)
    h.call(
        "POST",
        other_base + "/scenario-drafts",
        stranger,
        expected=404,
        json={"request_key": str(uuid4()), "code": "copy", "source_scenario_id": case["id"]},
    )
    device = h.device(token, org)["id"]
    credential = h.enroll(token, org, device)
    h.call("GET", path, credential, expected=403)
    h.sql(
        "UPDATE device_platform.platform_settings SET maintenance_mode=true,updated_by=%s WHERE id=1",
        (platform_admin["id"],),
    )
    assert h.call("GET", path, token)["id"] == row["id"]
    assert h.call("POST", path + "/validate", token, json={"expected_revision": 1})["publishable"]
    h.call("POST", path + "/publish", h.reviewer_token, expected=503, json=publication())
    h.call("PATCH", path, token, expected=503, json={"expected_revision": 1, "is_archived": True})
    h.sql(
        "UPDATE device_platform.platform_settings SET maintenance_mode=false,updated_by=%s WHERE id=1",
        (platform_admin["id"],),
    )
    h.call(
        "PATCH",
        f"/organizations/{org}",
        token,
        json={"is_active": False, "status_reason": "Synthetic suspension"},
    )
    h.call("GET", path, token, expected=409)


def test_listing_cursors_are_stable_and_query_scoped(library):
    h, token, _, _, base = library
    rows = [create(library, code=f"case_{i}")[0] for i in range(3)]
    first = h.call("GET", base + "/scenario-drafts?limit=2", token)
    assert len(first["items"]) == 2 and first["next_cursor"]
    assert "document" not in first["items"][0]
    row = rows[0]
    changed = example(row["code"])
    changed["title"] = "An edited title"
    h.call(
        "PUT",
        base + f"/scenario-drafts/{row['id']}",
        token,
        json={"expected_revision": 1, "document": changed},
    )
    second = h.call("GET", base + "/scenario-drafts?limit=2&cursor=" + first["next_cursor"], token)
    assert second["next_cursor"] is None
    assert {r["id"] for r in first["items"] + second["items"]} == {r["id"] for r in rows}
    for query in ("limit=101", "cursor=garbage", "q=edited&cursor=" + first["next_cursor"]):
        h.call("GET", base + "/scenario-drafts?" + query, token, expected=422)
    assert len(h.call("GET", base + "/scenario-drafts?q=edited", token)["items"]) == 1


def test_concurrent_saves_and_publication(library):
    h, token, _, _, base = library
    row, _ = create(library)
    path = "/api/v1" + base + f"/scenario-drafts/{row['id']}"

    def save(age):
        value = example()
        value["patient"]["age_years"] = age
        return h.client.put(path, headers=h.headers(token), json={"expected_revision": 1, "document": value})

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, (40, 50)))
    assert sorted(r.status_code for r in results) == [200, 409]
    same = publication(2)

    def submit(body):
        return h.client.post(path + "/publish", headers=h.headers(h.reviewer_token), json=body)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, [same, same]))
    assert sorted(r.status_code for r in results) == [200, 201]
    assert len({r.json()["scenario"]["id"] for r in results}) == 1
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, [publication(2), publication(2)]))
    assert [r.status_code for r in results] == [409, 409]


def test_rollback_of_content_and_audit(library, monkeypatch):
    h, token, _, org, base = library
    row, _ = create(library)
    path = base + f"/scenario-drafts/{row['id']}"
    original_audit = scenarios.audit

    async def broken_audit(session, *args, **kwargs):
        await original_audit(session, *args, **kwargs)
        await session.flush()
        raise AppError(503, "test_audit_failure", "Synthetic transaction failure")

    monkeypatch.setattr(scenarios, "audit", broken_audit)
    h.call("POST", path + "/publish", h.reviewer_token, expected=503, json=publication())
    changed = example()
    changed["title"] = "Uncommitted title"
    h.call("PUT", path, token, expected=503, json={"expected_revision": 1, "document": changed})
    assert h.call("GET", path, token) == row
    assert (
        h.sql("SELECT count(*) FROM device_platform.training_scenarios WHERE organization_id=%s", (org,))[0][
            0
        ]
        == 2
    )
    assert (
        h.sql(
            "SELECT count(*) FROM device_platform.activity_events WHERE event_type IN ('training.scenario.published','training.draft.saved') AND organization_id=%s",
            (org,),
        )[0][0]
        == 0
    )
    monkeypatch.setattr(scenarios, "audit", original_audit)
    assert publish(library, row)[0]["id"]


def test_draft_quota_race_and_replay_at_capacity(library):
    h, token, user, org, base = library
    row, body = create(library)
    with connect(h) as connection:
        for index in range(98):
            draft(connection, org, user, code=f"seed_{index}")

    def submit(code):
        return h.client.post(
            "/api/v1" + base + "/scenario-drafts",
            headers=h.headers(token),
            json={"request_key": str(uuid4()), "code": code},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, ("last_a", "last_b")))
    assert sorted(r.status_code for r in results) == [201, 429]
    assert h.call("POST", base + "/scenario-drafts", token, json=body)["draft"]["id"] == row["id"]
    h.call(
        "PATCH",
        base + f"/scenario-drafts/{row['id']}",
        token,
        json={"expected_revision": 1, "is_archived": True},
    )
    assert submit("still_full").status_code == 429


def test_publication_quota_and_matching_replay(library):
    h, token, user, org, base = library
    row, _ = create(library)
    case, body = publish(library, row)
    document = json.dumps(row["document"])
    h.sql(
        "INSERT INTO device_platform.training_scenarios(id,organization_id,request_key,code,version,document,fingerprint,created_by) SELECT gen_random_uuid(),%s,gen_random_uuid(),'seed_' || i,1,%s::jsonb,%s,%s FROM generate_series(1,96) i",
        (org, document, fingerprint(row["document"]), user),
    )
    candidates = [create(library, code)[0] for code in ("last_case_a", "last_case_b")]

    def submit(candidate):
        return h.client.post(
            "/api/v1" + base + f"/scenario-drafts/{candidate['id']}/publish",
            headers=h.headers(h.reviewer_token),
            json=publication(),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, candidates))
    assert sorted(result.status_code for result in results) == [201, 429]
    path = base + f"/scenario-drafts/{row['id']}"
    assert h.call("POST", path + "/publish", h.reviewer_token, json=body)["scenario"]["id"] == case["id"]
    updated = h.call("PUT", path, token, json={"expected_revision": 1, "document": example()})
    h.call("POST", path + "/publish", h.reviewer_token, expected=429, json=publication(updated["revision"]))


def test_revocation_while_waiting_for_organization_lock(library):
    h, token, user, org, base = library
    member(h, token, org, "replacement", "org_admin")
    with psycopg.connect(h.dsn) as blocker, ThreadPoolExecutor(max_workers=1) as pool:
        blocker.execute("SELECT id FROM device_platform.organizations WHERE id=%s FOR UPDATE", (org,))
        future = pool.submit(
            h.client.post,
            "/api/v1" + base + "/scenario-drafts",
            headers=h.headers(token),
            json={"request_key": str(uuid4()), "code": "blocked"},
        )
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            waiting = h.sql(
                "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock'"
            )[0][0]
            if waiting:
                break
            time.sleep(0.02)
        assert waiting, "request never reached the serialization lock"
        blocker.execute(
            "UPDATE device_platform.organization_memberships SET role='org_read_only' WHERE organization_id=%s AND user_id=%s",
            (org, user),
        )
        blocker.commit()
        assert future.result(timeout=5).status_code == 403
    assert (
        h.sql(
            "SELECT count(*) FROM device_platform.training_scenario_drafts WHERE organization_id=%s", (org,)
        )[0][0]
        == 0
    )


def test_version_one_copy_and_version_two_runtime_guard(interview):
    h, token, org, _, credential, legacy, base, session_body, _ = interview
    user = h.sql("SELECT created_by FROM device_platform.training_scenarios WHERE id=%s", (legacy["id"],))[0][
        0
    ]
    value = AuthorFixture((h, token, str(user), org, base))
    copied, _ = create(value, "legacy_copy", False, source_scenario_id=legacy["id"])
    assert copied["schema_version"] == 1 and copied["document"]["code"] == "legacy_copy"
    case, _ = publish(value, copied)
    assert case["execution_supported"]
    sid = h.call(
        "POST", base + "/sessions", token, expected=201, json={**session_body, "scenario_id": case["id"]}
    )["id"]
    assert h.call("POST", f"/device/training/sessions/{sid}/lease", credential)["scenario"]["version"] == 1
    h.call("POST", base + f"/sessions/{sid}/stop", token)
    row, _ = create(value)
    case, _ = publish(value, row)
    reply = h.call(
        "POST",
        base + "/sessions",
        token,
        expected=409,
        json={**session_body, "request_key": str(uuid4()), "scenario_id": case["id"]},
    )
    assert reply["error"]["code"] == "scenario_runtime_unsupported"
    assert (
        h.sql("SELECT count(*) FROM device_platform.training_sessions WHERE scenario_id=%s", (case["id"],))[
            0
        ][0]
        == 0
    )
    h.call(
        "POST",
        base + f"/scenarios/{case['id']}/approve",
        h.reviewer_token,
        expected=409,
        json=publication()["approval"],
    )


def test_request_bounds_and_openapi(library):
    h, token, _, _, base = library
    response = h.client.post(
        "/api/v1" + base + "/scenario-drafts", headers=h.headers(token), content=b" " * (128 * 1024 + 1)
    )
    assert response.status_code == 413 and len(response.content) < 1000
    row, _ = create(library)
    path = base + f"/scenario-drafts/{row['id']}"
    for revision in (True, None, "1", 0):
        h.call("PUT", path, token, expected=422, json={"expected_revision": revision, "document": example()})
    value = example()
    value["private_secret"] = "must-not-echo-this-value"
    invalid = h.call("PUT", path, token, expected=422, json={"expected_revision": 1, "document": value})
    assert "must-not-echo-this-value" not in json.dumps(invalid)
    schema = h.client.get("/openapi.json").json()
    assert "DraftCreate" in schema["components"]["schemas"]
    assert "ScenarioDraftV2" in schema["components"]["schemas"]
    assert all(
        "Cache-Control" in h.client.get("/api/v1" + path, headers=h.headers(token)).headers for _ in range(1)
    )
