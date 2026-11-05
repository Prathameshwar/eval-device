from uuid import uuid4

from current_model_fixtures import cloud_model_body, local_revision


def test_platform_language_device_lifecycle(platform):
    p = platform
    assert p.client.get("/health/ready").status_code == 200
    token, user = p.admin()
    org = p.organization(token)
    oid = org["id"]
    languages = p.call("GET", "/languages", token)
    assert languages["default"] == "en" and {x["code"] for x in languages["items"]} == {"en", "hi"}
    device = p.device(token, oid, preferred_language="hi")
    did = device["id"]
    credential = p.enroll(token, oid, did)
    config = p.call("GET", "/device/config", credential)
    assert config["effective_language"] == "hi" and config["settings"]["audio_input"]["language"] == "hi-IN"
    p.call("PATCH", f"/organizations/{oid}/devices/{did}", token, json={"preferred_language": None})
    english = p.call("GET", "/device/config", credential)
    assert (
        english["effective_language"] == "en"
        and english["configuration_hash"] != config["configuration_hash"]
    )
    p.call(
        "PATCH", f"/organizations/{oid}/devices/{did}", token, expected=422, json={"preferred_language": "fr"}
    )
    settings = p.call("GET", "/platform/settings", token)
    added = [
        *settings["languages"],
        {"code": "fr", "name": "French", "speech_locale": "fr-FR", "is_active": True},
    ]
    p.call(
        "PATCH",
        "/platform/settings",
        token,
        json={"expected_version": settings["configuration_version"], "languages": added},
    )
    p.call("PATCH", f"/organizations/{oid}/devices/{did}", token, json={"preferred_language": "fr"})
    assert p.call("GET", "/device/config", credential)["effective_language"] == "fr"
    p.call("PATCH", f"/platform/users/{user['id']}", token, expected=403, json={"is_active": False})
    assert p.call("GET", "/me", token)["user"]["is_active"]
    boot = str(uuid4())
    for _ in range(2):
        p.call(
            "POST",
            "/device/heartbeat",
            credential,
            json={"boot_id": boot, "sequence_number": 1, "metrics": {"cpu_percent": 12}},
        )
    assert p.sql("SELECT count(*) FROM device_platform.device_telemetry_samples")[0][0] == 1
    p.call("PATCH", f"/organizations/{oid}/devices/{did}", token, json={"is_active": False})
    p.call("POST", "/device/heartbeat", credential, json={"boot_id": boot, "sequence_number": 2})
    assert p.call("GET", "/device/config", credential)["is_active"] is False
    p.call("GET", "/device/runs", credential, expected=409)


def test_local_processing_idempotency_and_role_boundaries(platform):
    p = platform
    token, _ = p.admin()
    org = p.organization(token)
    oid = org["id"]
    device = p.device(token, oid)
    did = device["id"]
    credential = p.enroll(token, oid, did)
    revision = local_revision(p, token, oid, did, credential)
    config = p.call("GET", "/device/config", credential)
    p.call(
        "POST",
        "/device/heartbeat",
        credential,
        json={
            "boot_id": str(uuid4()),
            "sequence_number": 0,
            "applied_profile_revision_id": revision["id"],
            "applied_configuration_hash": config["configuration_hash"],
        },
    )
    body = {
        "request_key": str(uuid4()),
        "operation": "audio.transcribe",
        "profile_revision_id": revision["id"],
        "duration_seconds": 1,
    }
    first = p.call("POST", "/device/runs", credential, expected=202, json=body)
    retry = p.call("POST", "/device/runs", credential, expected=202, json=body)
    assert first["run"]["id"] == retry["run"]["id"] and not retry["created"]
    p.call("POST", "/device/runs", credential, expected=409, json={**body, "duration_seconds": 2})
    rid = first["run"]["id"]
    p.call(
        "POST",
        f"/device/runs/{rid}/result",
        credential,
        json={"status": "succeeded", "result": {"text": "Synthetic transcript"}},
    )
    trainee, _ = p.user("trainee")
    invitation = p.call(
        "POST",
        f"/organizations/{oid}/invitations",
        token,
        expected=201,
        json={"email": "trainee@example.com", "role": "org_trainee"},
    )
    p.call("POST", "/invitations/accept", trainee, json={"token": invitation["invitation_token"]})
    assert p.call("GET", f"/organizations/{oid}/runs/{rid}", trainee)["result"] == {
        "text": "Synthetic transcript"
    }
    p.call("GET", "/platform/runtime-models", trainee, expected=403)
    p.call(
        "POST",
        f"/organizations/{oid}/runs",
        trainee,
        expected=403,
        json={**body, "device_id": did, "request_key": str(uuid4())},
    )
    outsider, _ = p.user("outsider")
    other = p.organization(outsider)
    p.call("GET", f"/organizations/{other['id']}/devices", token, expected=404)
    p.call("GET", f"/organizations/{oid}/runs/{rid}", outsider, expected=404)


def test_encrypted_model_credentials_and_errors(platform):
    p = platform
    token, _ = p.admin()
    secret = "integration-test-secret"
    body = {**cloud_model_body(), "credentials": {"api_key": secret}}
    path = "/platform/runtime-models"
    model = p.call("POST", path, token, expected=201, json=body)
    assert model["has_credentials"] and secret not in str(model)
    stored = p.sql(
        "SELECT encrypted_credentials,credential_key_id FROM device_platform.runtime_models WHERE id=%s",
        (model["id"],),
    )[0]
    assert secret.encode() not in bytes(stored[0]) and stored[1] == "test-v1"
    changed = p.call(
        "PUT",
        path + "/" + model["id"],
        token,
        json={
            **body,
            "expected_revision": model["revision"],
            "credentials": {"api_key": "rotated-test-key"},
        },
    )
    p.call(
        "PUT",
        path + "/" + model["id"],
        token,
        expected=409,
        json={**body, "expected_revision": model["revision"]},
    )
    response = p.client.post(
        "/api/v1" + path, headers=p.headers(token), json={"credentials": {"api_key": secret}}
    )
    assert response.status_code == 422 and secret not in response.text
    assert secret not in str(p.sql("SELECT details FROM device_platform.activity_events"))
    assert changed["revision"] == model["revision"] + 1


def test_department_history_scope_and_catalog_safeguards(platform):
    p = platform
    token, _ = p.admin()
    oid = p.organization(token)["id"]
    first = p.call("POST", f"/organizations/{oid}/departments", token, expected=201, json={"name": "First"})[
        "id"
    ]
    second = p.call(
        "POST", f"/organizations/{oid}/departments", token, expected=201, json={"name": "Second"}
    )["id"]
    trainee, _ = p.user("department-trainee")
    invite = p.call(
        "POST",
        f"/organizations/{oid}/invitations",
        token,
        expected=201,
        json={"email": "department-trainee@example.com", "role": "org_trainee", "department_id": first},
    )
    p.call("POST", "/invitations/accept", trainee, json={"token": invite["invitation_token"]})
    did = p.device(token, oid, department_id=first)["id"]
    credential = p.enroll(token, oid, did)
    revision = local_revision(p, token, oid, did, credential)
    created = p.call(
        "POST",
        f"/organizations/{oid}/runs",
        token,
        expected=202,
        json={
            "device_id": did,
            "request_key": str(uuid4()),
            "operation": "audio.transcribe",
            "profile_revision_id": revision["id"],
        },
    )["run"]
    p.call(
        "POST",
        f"/device/runs/{created['id']}/result",
        credential,
        json={"status": "succeeded", "result": {"text": "Synthetic transcript"}},
    )
    p.call("PATCH", f"/organizations/{oid}/devices/{did}", token, json={"department_id": second})
    assert p.call("GET", f"/organizations/{oid}/devices", trainee)["items"] == []
    assert p.call("GET", f"/organizations/{oid}/runs/{created['id']}", trainee)["department_id"] == first
    membership = invite["membership"]["id"]
    p.call("PATCH", f"/organizations/{oid}/members/{membership}", token, json={"department_id": second})
    p.call("GET", f"/organizations/{oid}/runs/{created['id']}", trainee, expected=404)
    p.call("PATCH", f"/organizations/{oid}/devices/{did}", token, json={"preferred_language": "hi"})
    settings = p.call("GET", "/platform/settings", token)
    p.call(
        "PATCH",
        "/platform/settings",
        token,
        expected=409,
        json={"expected_version": settings["configuration_version"], "languages": [settings["languages"][0]]},
    )
    p.call(
        "PATCH",
        "/platform/settings",
        token,
        expected=409,
        json={"expected_version": settings["configuration_version"], "languages": [settings["languages"][1]]},
    )
    inactive = [
        {**item, "is_active": False} if item["code"] == "hi" else item for item in settings["languages"]
    ]
    p.call(
        "PATCH",
        "/platform/settings",
        token,
        json={"expected_version": settings["configuration_version"], "languages": inactive},
    )
    assert p.call("GET", "/device/config", credential)["effective_language"] == "en"


def test_oidc_verification_and_no_registration_escalation(platform):
    p = platform
    for claims in (
        {"aud": "wrong"},
        {"iss": "https://untrusted.test"},
        {"exp": 1},
        {"email_verified": "true"},
    ):
        token = p.token("new-user", **claims)
        if claims.get("email_verified"):
            user = p.call("POST", "/identity/sync", token)
            assert not user["email_verified"]
            p.call(
                "POST",
                "/organizations",
                token,
                expected=403,
                json={
                    "name": "No unverified creation",
                    "subscription_plan_id": "00000000-0000-4000-8000-000000000101",
                },
            )
        else:
            p.call("POST", "/identity/sync", token, expected=401)
    token = p.token("role-claim", platform_role="platform_admin", role="platform_admin")
    user = p.call("POST", "/identity/sync", token)
    assert user["platform_role"] is None
    p.call("GET", "/platform/settings", token, expected=403)


def test_enrollment_rechecks_department_status(platform):
    p = platform
    token, _ = p.admin()
    oid = p.organization(token)["id"]
    department = p.call(
        "POST", f"/organizations/{oid}/departments", token, expected=201, json={"name": "Lab"}
    )["id"]
    did = p.device(token, oid, department_id=department)["id"]
    invite = p.call("POST", f"/organizations/{oid}/devices/{did}/enrollment", token)
    p.call("PATCH", f"/organizations/{oid}/departments/{department}", token, json={"is_active": False})
    p.call("POST", "/device/enroll", expected=422, json={"token": invite["enrollment_token"]})
    assert p.sql(
        "SELECT enrollment_state,credential_hash FROM device_platform.devices WHERE id=%s", (did,)
    ) == [("pending", None)]
    p.call("PATCH", f"/organizations/{oid}/departments/{department}", token, json={"is_active": True})
    enrolled = p.call("POST", "/device/enroll", json={"token": invite["enrollment_token"]})
    assert enrolled["device_id"] == did
    p.call("POST", "/device/enroll", expected=409, json={"token": invite["enrollment_token"]})


def test_model_capture_limits_govern_run_admission(platform):
    p = platform
    token, _ = p.admin()
    oid = p.organization(token)["id"]
    did = p.device(token, oid)["id"]
    credential = p.enroll(token, oid, did)
    revision = local_revision(p, token, oid, did, credential)
    policy = p.call("GET", f"/organizations/{oid}", token)["policy_settings"]
    policy["capture_limits"]["max_audio_seconds"] = 5
    p.call("PATCH", f"/organizations/{oid}", token, json={"policy_settings": policy})
    body = {
        "device_id": did,
        "request_key": str(uuid4()),
        "operation": "audio.transcribe",
        "profile_revision_id": revision["id"],
    }
    blocked = p.call(
        "POST", f"/organizations/{oid}/runs", token, expected=422, json={**body, "duration_seconds": 6}
    )
    assert blocked["error"]["code"] == "capture_limit"
    config = p.call("GET", f"/organizations/{oid}/devices/{did}/configuration", token)
    assert config["policy"]["capture_limits"]["max_audio_seconds"] == 5
    run = p.call("POST", f"/organizations/{oid}/runs", token, expected=202, json=body)["run"]
    snapshot, usage = p.sql(
        "SELECT effective_settings,usage FROM device_platform.processing_runs WHERE id=%s", (run["id"],)
    )[0]
    assert usage["reserved"] == 5
    policy["capture_limits"]["max_audio_seconds"] = 2
    p.call("PATCH", f"/organizations/{oid}", token, json={"policy_settings": policy})
    tightened = p.call("GET", f"/organizations/{oid}/devices/{did}/configuration", token)
    assert tightened["policy"]["capture_limits"]["max_audio_seconds"] == 2
    assert tightened["configuration_hash"] != config["configuration_hash"]
    p.call(
        "POST",
        f"/organizations/{oid}/runs",
        token,
        expected=422,
        json={**body, "request_key": str(uuid4()), "duration_seconds": 3},
    )
    assert (
        p.sql("SELECT effective_settings FROM device_platform.processing_runs WHERE id=%s", (run["id"],))[0][
            0
        ]
        == snapshot
    )
