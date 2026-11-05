import json
from uuid import uuid4

import jwt
import psycopg
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


@pytest.fixture
def interview(platform, tmp_path):
    h = platform
    key = Ed25519PrivateKey.generate()
    path = tmp_path / "training.pem"
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
    h.settings.training_key_file = path
    token, user = h.user("instructor")
    org = h.organization(token)["id"]
    h.grant_capability(token, org, user["id"], "org.clinical.author")
    h.grant_capability(token, org, user["id"], "org.training.instruct")
    reviewer_token, reviewer_user = h.user("training-reviewer")
    invite = h.call(
        "POST",
        f"/organizations/{org}/invitations",
        token,
        expected=201,
        json={"email": "training-reviewer@example.com", "role": "org_admin"},
    )
    h.call("POST", "/invitations/accept", reviewer_token, json={"token": invite["invitation_token"]})
    h.grant_capability(token, org, reviewer_user["id"], "org.clinical.review")
    h.reviewer_token = reviewer_token
    device = h.device(token, org)["id"]
    credential = h.enroll(token, org, device)
    h.sql(
        "UPDATE device_platform.devices SET capabilities=%s WHERE id=%s",
        (json.dumps({"engines": ["patient_interview_v1"]}), device),
    )
    operator, _ = h.admin("training-model-operator")
    model_path = f"/platform/devices/{device}/models"
    models = h.call("GET", model_path, operator)["models"]
    h.call(
        "PUT",
        model_path,
        operator,
        json={
            "mode": "local",
            "expected_version": 0,
            **{model["kind"] + "_model_id": model["id"] for model in models},
            "model_revisions": {model["id"]: model["revision"] for model in models},
        },
    )
    h.training_model_operator = operator

    # Seed an unapproved clinical snapshot to exercise the separate approval gate.
    from scenario_samples import example
    from training_contracts import fingerprint
    from training_contracts.clinical_cases import simplify_case
    from training_contracts.localized_cases import review_localization

    document = simplify_case(example())
    for language in ("en", "hi"):
        document = review_localization(document, language)
    identity = str(uuid4())
    h.sql(
        "INSERT INTO device_platform.training_scenarios(id,organization_id,code,version,document,request_key,fingerprint,created_by) VALUES(%s,%s,%s,1,%s,gen_random_uuid(),%s,%s)",
        (identity, org, document["code"], json.dumps(document), fingerprint(document), user["id"]),
    )
    base = f"/organizations/{org}/training"
    case = h.call("GET", base + "/scenarios/" + identity, token)
    body = {
        "request_key": str(uuid4()),
        "device_id": device,
        "learner_id": user["id"],
        "scenario_id": case["id"],
        "duration_seconds": 30,
    }
    return h, token, org, device, credential, case, base, body, key


def approve(value):
    h, token, _, _, _, case, base, _, _ = value
    h.call(
        "POST",
        base + f"/scenarios/{case['id']}/approve",
        h.reviewer_token,
        json={
            "educator_name": "Test educator",
            "statement": "Synthetic automated test approval, not clinical approval.",
        },
    )


@pytest.mark.parametrize("missing", ["llm", "asr", "tts"])
def test_training_requires_all_local_models_and_revokes_changed_selection(interview, missing):
    h, token, _, device, credential, _, base, body, _ = interview
    approve(interview)
    sid = h.call("POST", base + "/sessions", token, expected=201, json=body)["id"]
    path = f"/platform/devices/{device}/models"
    state = h.call("GET", path, h.training_model_operator)
    selection = state["selection"]
    h.call(
        "PUT",
        path,
        h.training_model_operator,
        json={
            "mode": "local",
            "expected_version": selection["version"],
            **{kind + "_model_id": selection[kind + "_model_id"] for kind in ("llm", "asr", "tts", "video")},
            missing + "_model_id": None,
            "model_revisions": {m["id"]: m["revision"] for m in state["models"]},
        },
    )
    h.call("POST", f"/device/training/sessions/{sid}/lease", credential, expected=409)
    h.call("POST", base + f"/sessions/{sid}/access?control=true", token, expected=409)
    h.call("POST", base + f"/sessions/{sid}/stop", token)
    h.call("POST", base + "/sessions", token, expected=409, json={**body, "request_key": str(uuid4())})


def test_training_lifecycle_idempotency_and_manual_feedback(interview):
    h, token, org, device, credential, case, base, body, key = interview
    h.call("POST", base + "/sessions", token, expected=409, json=body)
    approve(interview)
    row = h.call("POST", base + "/sessions", token, expected=201, json=body)
    sid = row["id"]
    assert h.call("POST", base + "/sessions", token, expected=201, json=body)["id"] == sid
    h.call("POST", base + "/sessions", token, expected=409, json={**body, "language": "hi"})
    lease = h.call("POST", f"/device/training/sessions/{sid}/lease", credential)
    claims = jwt.decode(
        lease["grant"],
        key.public_key(),
        algorithms=["EdDSA"],
        audience="device-training",
        issuer="pms-training-v1",
    )
    assert claims["scope"] == "device" and claims["device_id"] == device
    assert claims["exp"] - claims["iat"] <= 30
    assert lease["scenario"]["case"]["version"] == 4
    assert "rubric" not in lease["scenario"]
    result = {
        "event_id": str(uuid4()),
        "status": "completed",
        "turns": 1,
        "audio_recordings": [],
        "video_recordings": [],
        "recording_status": "unavailable",
        "reason": "none",
    }
    h.call("POST", f"/device/training/sessions/{sid}/result", credential, json=result)
    h.call("POST", f"/device/training/sessions/{sid}/result", credential, json=result)
    h.call(
        "POST",
        f"/device/training/sessions/{sid}/result",
        credential,
        expected=409,
        json={**result, "turns": 2},
    )
    h.call("POST", f"/device/training/sessions/{sid}/lease", credential, expected=409)
    feedback = {
        "expected_version": 0,
        "scores": {},
        "comments": "Test only",
    }
    assert h.call("POST", base + f"/sessions/{sid}/feedback", token, json=feedback)["feedback_version"] == 1
    h.call("POST", base + f"/sessions/{sid}/feedback", token, expected=409, json=feedback)
    with pytest.raises(psycopg.errors.CheckViolation):
        h.sql(
            "UPDATE device_platform.training_sessions SET status='active',ended_at=NULL WHERE id=%s", (sid,)
        )
    with pytest.raises(psycopg.errors.CheckViolation):
        h.sql("UPDATE device_platform.training_scenarios SET document='{}'::jsonb WHERE id=%s", (case["id"],))
    with pytest.raises(psycopg.errors.CheckViolation):
        h.sql("DELETE FROM device_platform.training_sessions WHERE id=%s", (sid,))


@pytest.mark.parametrize("background", [False, True])
def test_reviewed_tenant_case_compiles_to_pinned_device_runtime(interview, background):
    from test_patient_practice import setup
    from training_contracts import fingerprint

    h, token, org, device, credential, _, base, body, _ = interview
    _, selection, _ = setup(h, token, org)
    other_org = h.organization(token, "Second hospital for copy denial")["id"]
    _, foreign_selection, _ = setup(h, token, other_org)
    h.call(
        "POST",
        base + "/scenario-drafts",
        token,
        expected=404,
        json={
            "request_key": str(uuid4()),
            "code": "foreign_case_copy",
            "source_case_id": foreign_selection["template_id"],
        },
    )
    draft = h.call(
        "POST",
        base + "/scenario-drafts",
        token,
        expected=201,
        json={
            "request_key": str(uuid4()),
            "code": "tenant_training_case",
            "source_case_id": selection["template_id"],
        },
    )["draft"]
    assert draft["source_case_id"] == selection["template_id"]
    if background:
        from test_patient_background import background_case

        document = {**draft["document"], "version": 5, "background": background_case()["background"]}
        draft = h.call(
            "PUT",
            base + f"/scenario-drafts/{draft['id']}",
            token,
            json={"expected_revision": draft["revision"], "document": document},
        )
    clinical = f"/organizations/{org}/clinical-catalog/cases/{selection['template_id']}"
    source = h.call("GET", clinical, token)
    updated_title = source["title"] + " revision"
    revised = h.call(
        "PATCH",
        clinical,
        token,
        json={
            "expected_version": source["version"],
            "data": {
                "code": source["code"],
                "specialty_id": source["specialty_id"],
                "patient_profile_id": source["patient_profile_id"],
                "title": updated_title,
                "titles": {**source["titles"], "en": updated_title},
                "document": {**source["document"], "title": updated_title},
                "is_active": True,
            },
        },
    )
    assert revised["version"] == source["version"] + 1
    stale = h.call(
        "POST",
        base + f"/scenario-drafts/{draft['id']}/validate",
        token,
        json={"expected_revision": draft["revision"]},
    )
    assert not stale["publishable"] and any(e["code"] == "case_source_stale" for e in stale["errors"])
    draft = h.call(
        "POST",
        base + f"/scenario-drafts/{draft['id']}/refresh-case",
        token,
        json={"expected_revision": draft["revision"]},
    )
    assert draft["source_case_revision"] == revised["version"]
    if background:
        assert draft["schema_version"] == 5 and draft["document"]["background"] == document["background"]
    draft = h.call(
        "POST",
        base + f"/scenario-drafts/{draft['id']}/submit",
        token,
        json={"expected_revision": draft["revision"]},
    )
    for language in ("en", "hi"):
        draft = h.call(
            "POST",
            base + f"/scenario-drafts/{draft['id']}/localizations/{language}/review",
            h.reviewer_token,
            json={
                "expected_revision": draft["revision"],
                "approval": {
                    "educator_name": "Synthetic reviewer",
                    "statement": "Software conversion fixture only, not clinical approval.",
                },
            },
        )
    h.call(
        "POST",
        base + f"/scenario-drafts/{draft['id']}/publish",
        token,
        expected=403,
        json={
            "request_key": str(uuid4()),
            "expected_revision": draft["revision"],
            "approval": {
                "educator_name": "Synthetic author",
                "statement": "Software fixture author must not self approve.",
            },
        },
    )
    published = h.call(
        "POST",
        base + f"/scenario-drafts/{draft['id']}/publish",
        h.reviewer_token,
        expected=201,
        json={
            "request_key": str(uuid4()),
            "expected_revision": draft["revision"],
            "approval": {
                "educator_name": "Synthetic reviewer",
                "statement": "Software conversion fixture only, not clinical approval.",
            },
        },
    )["scenario"]
    assert published["execution_supported"] is True
    assert published["schema_version"] == (5 if background else 4)
    session = h.call(
        "POST",
        base + "/sessions",
        token,
        expected=201,
        json={**body, "request_key": str(uuid4()), "scenario_id": published["id"]},
    )
    grant = h.call("POST", f"/device/training/sessions/{session['id']}/lease", credential)
    runtime = grant["scenario"]
    assert runtime["version"] == 2
    assert fingerprint(runtime) != published["fingerprint"]
    assert runtime["case"]["code"] == published["document"]["code"]
    if background:
        assert runtime["case"]["background"] == document["background"]
    assert not {"dialogue", "instructor", "fact_disclosure"} & runtime["case"].keys()


def test_training_scope_and_revocation(interview):
    h, token, org, device, credential, case, base, body, _ = interview
    approve(interview)
    sid = h.call("POST", base + "/sessions", token, expected=201, json=body)["id"]
    stranger, _ = h.user("stranger")
    h.call("GET", base + f"/sessions/{sid}", stranger, expected=404)
    admin, _ = h.admin()
    h.call("POST", base + f"/sessions/{sid}/access", admin, expected=404)
    other_org = h.organization(token, name="Other organization")["id"]
    other_device = h.device(token, other_org)["id"]
    other_credential = h.enroll(token, other_org, other_device)
    h.call("POST", f"/device/training/sessions/{sid}/lease", other_credential, expected=404)
    h.call("POST", base + f"/scenarios/{case['id']}/retire", h.reviewer_token)
    h.call("POST", f"/device/training/sessions/{sid}/lease", credential, expected=409)
    h.call("POST", base + f"/sessions/{sid}/access?control=true", token, expected=409)
    h.call("POST", base + f"/sessions/{sid}/stop", token)
    assert h.call("GET", base + f"/sessions/{sid}", token)["status"] == "cancelled"
    public = h.call("GET", base + "/scenarios", token)["items"][0]
    assert "document" not in public and "rubric" not in public


def test_instructor_capability_revocation_blocks_new_and_active_controls(interview):
    h, token, org, _, credential, _, base, body, _ = interview
    approve(interview)
    sid = h.call("POST", base + "/sessions", token, expected=201, json=body)["id"]
    membership_id = h.sql(
        "SELECT id FROM device_platform.organization_memberships "
        "WHERE organization_id=%s AND user_id=(SELECT instructor_id FROM device_platform.training_sessions WHERE id=%s)",
        (org, sid),
    )[0][0]
    h.call(
        "DELETE",
        f"/organizations/{org}/members/{membership_id}/capabilities/org.training.instruct",
        token,
    )
    h.call(
        "POST",
        base + "/sessions",
        token,
        expected=403,
        json={**body, "request_key": str(uuid4())},
    )
    h.call("POST", base + f"/sessions/{sid}/access?control=true", token, expected=403)
    h.call("POST", f"/device/training/sessions/{sid}/lease", credential, expected=403)


def test_training_concurrent_admission_and_cancelled_receipt(interview):
    from concurrent.futures import ThreadPoolExecutor

    h, token, _, _, credential, _, base, body, _ = interview
    approve(interview)

    def submit(_):
        return h.client.post(
            "/api/v1" + base + "/sessions",
            headers=h.headers(token),
            json={**body, "request_key": str(uuid4())},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(submit, range(2)))
    assert sorted(r.status_code for r in replies) in ([201, 409], [201, 429])
    sid = next(r.json()["id"] for r in replies if r.status_code == 201)
    h.call("POST", f"/device/training/sessions/{sid}/lease", credential)
    h.call("POST", base + f"/sessions/{sid}/stop", token)
    receipt = {"event_id": str(uuid4()), "status": "completed", "turns": 1, "recording_status": "incomplete"}
    final = h.call("POST", f"/device/training/sessions/{sid}/result", credential, json=receipt)
    assert final["status"] == "cancelled" and final["result"]["status"] == "completed"
    h.call("POST", f"/device/training/sessions/{sid}/result", credential, json=receipt)
    h.call(
        "POST",
        f"/device/training/sessions/{sid}/result",
        credential,
        expected=409,
        json={**receipt, "event_id": str(uuid4())},
    )


def test_trainee_scope_and_configuration_revocation(interview):
    h, token, org, _, credential, _, base, body, _ = interview
    approve(interview)
    trainee, learner = h.user("learner")
    invite = h.call(
        "POST",
        f"/organizations/{org}/invitations",
        token,
        expected=201,
        json={"email": "learner@example.com", "role": "org_trainee"},
    )
    h.call("POST", "/invitations/accept", trainee, json={"token": invite["invitation_token"]})
    sid = h.call("POST", base + "/sessions", token, expected=201, json={**body, "learner_id": learner["id"]})[
        "id"
    ]
    assert h.call("GET", base + f"/sessions/{sid}", trainee)["id"] == sid
    for path in [f"/sessions/{sid}/stop", f"/sessions/{sid}/access?control=true"]:
        h.call("POST", base + path, trainee, expected=403)
    h.call("POST", base + "/sessions", trainee, expected=403, json=body)
    h.sql("UPDATE device_platform.devices SET preferred_language='hi' WHERE id=%s", (body["device_id"],))
    h.call("POST", f"/device/training/sessions/{sid}/lease", credential, expected=409)


def test_training_quota_reservation_and_result_limit(interview):
    h, token, org, _, credential, _, base, body, _ = interview
    approve(interview)
    # Policy is enforced from resolved server state, not a device-provided number.
    h.sql(
        "UPDATE device_platform.organizations SET policy_settings=jsonb_set(policy_settings,'{usage_limits,daily_audio_seconds}','20'::jsonb) WHERE id=%s",
        (org,),
    )
    h.call("POST", base + "/sessions", token, expected=429, json=body)


def test_department_scope_and_disabled_instructor(interview):
    h, token, org, _, credential, _, base, body, _ = interview
    approve(interview)
    dept = h.call(
        "POST", f"/organizations/{org}/departments", token, expected=201, json={"name": "Other department"}
    )["id"]
    operator, user = h.user("deptoperator")
    invite = h.call(
        "POST",
        f"/organizations/{org}/invitations",
        token,
        expected=201,
        json={"email": "deptoperator@example.com", "role": "org_user", "department_id": dept},
    )
    h.call("POST", "/invitations/accept", operator, json={"token": invite["invitation_token"]})
    sid = h.call("POST", base + "/sessions", token, expected=201, json=body)["id"]
    h.call("GET", base + f"/sessions/{sid}", operator, expected=404)
    h.call("POST", base + f"/sessions/{sid}/access", operator, expected=404)
    h.sql(
        "UPDATE device_platform.organization_memberships SET role='org_admin',department_id=NULL WHERE organization_id=%s AND user_id=%s",
        (org, user["id"]),
    )
    h.sql("UPDATE device_platform.users SET is_active=false WHERE id=%s", (body["learner_id"],))
    h.call("POST", f"/device/training/sessions/{sid}/lease", credential, expected=403)


def test_trainee_dashboard_stats(interview):
    h, token, org, _, _, _, base, body, _ = interview
    approve(interview)
    trainee, learner = h.user("learner")
    invite = h.call(
        "POST",
        f"/organizations/{org}/invitations",
        token,
        expected=201,
        json={"email": "learner@example.com", "role": "org_trainee"},
    )
    h.call("POST", "/invitations/accept", trainee, json={"token": invite["invitation_token"]})

    # Check Trainee Stats (no sessions initially)
    stats = h.call("GET", base + "/stats", trainee)
    assert stats["sessions"] == 0
    assert stats["hours_practiced"] == 0.0
    assert stats["average_score"] is None
    assert stats["awaiting_review"] == 0


def test_personal_stats_respect_scope_retention_and_feedback(interview, monkeypatch):
    h, token, org, _, credential, _, base, body, _ = interview
    approve(interview)
    sid = h.call("POST", base + "/sessions", token, expected=201, json=body)["id"]
    h.call("POST", f"/device/training/sessions/{sid}/lease", credential)
    h.call(
        "POST",
        f"/device/training/sessions/{sid}/result",
        credential,
        json={"event_id": str(uuid4()), "status": "completed", "turns": 1, "recording_status": "incomplete"},
    )
    h.sql(
        "UPDATE device_platform.training_sessions SET feedback=%s WHERE id=%s",
        (
            json.dumps(
                {"scores": {"one": "met", "two": "partial", "three": "not_met", "unrated": "not_observed"}}
            ),
            sid,
        ),
    )
    assert h.call("GET", base + "/stats", token)["average_score"] == 50
    dept = h.call(
        "POST", f"/organizations/{org}/departments", token, expected=201, json={"name": "Different"}
    )["id"]
    replacement, _ = h.user("replacement")
    invite = h.call(
        "POST",
        f"/organizations/{org}/invitations",
        token,
        expected=201,
        json={"email": "replacement@example.com", "role": "org_admin"},
    )
    h.call("POST", "/invitations/accept", replacement, json={"token": invite["invitation_token"]})
    h.sql(
        "UPDATE device_platform.organization_memberships SET role='org_user',department_id=%s WHERE user_id=%s",
        (dept, body["learner_id"]),
    )
    stats = h.call("GET", base + "/stats", token)
    assert stats["sessions"] == 0 and stats["average_score"] is None
    assert not h.call("GET", base + "/sessions?mine=true", token)["items"]
    h.sql(
        "UPDATE device_platform.organization_memberships SET department_id=NULL WHERE user_id=%s",
        (body["learner_id"],),
    )
    from datetime import timedelta

    from pms_api.modules import training

    future = training.now() + timedelta(days=365)
    monkeypatch.setattr(training, "now", lambda: future)
    assert h.call("GET", base + "/stats", token)["sessions"] == 0


def test_training_session_directory_pages_and_binds_scope(interview):
    h, token, _, _, _, _, base, body, _ = interview
    approve(interview)
    created = []
    for _ in range(2):
        row = h.call(
            "POST", base + "/sessions", token, expected=201, json={**body, "request_key": str(uuid4())}
        )
        created.append(row["id"])
        h.call("POST", base + "/sessions/" + row["id"] + "/stop", token)
    first = h.call("GET", base + "/sessions?limit=1", token)
    assert first["total"] == 2 and first["has_more"]
    second = h.call("GET", base + "/sessions?limit=1&cursor=" + first["next_cursor"], token)
    assert not second["has_more"]
    assert {first["items"][0]["id"], second["items"][0]["id"]} == set(created)
    h.call("GET", base + "/sessions?limit=1&mine=true&cursor=" + first["next_cursor"], token, expected=422)
