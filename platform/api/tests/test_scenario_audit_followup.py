"""Close the planned workflow and overlapping retirement acceptance gaps."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import jwt
import pytest
from scenario_samples import example
from test_scenario_library import library as library
from test_scenario_library import member, publication
from test_training import approve
from test_training import interview as interview

from pms_api.modules import training


def test_kidney_authenticated_lifecycle(library):
    h, token, _, org, base = library
    document = example("audit_kidney", "kidney")
    row = h.call(
        "POST",
        base + "/scenario-drafts",
        token,
        expected=201,
        json={"request_key": str(uuid4()), "code": document["code"], "document": document},
    )["draft"]
    path = base + f"/scenario-drafts/{row['id']}"
    document["patient"]["age_years"] = 41
    saved = h.call("PUT", path, token, json={"expected_revision": 1, "document": document})
    validated = h.call("POST", path + "/validate", token, json={"expected_revision": 2})
    assert validated["publishable"] and "41" in validated["preview"]["topics"][0]["answer"]["hi"]
    case = h.call("POST", path + "/publish", h.reviewer_token, expected=201, json=publication(2))["scenario"]
    detail = base + f"/scenarios/{case['id']}"
    assert case["document"] == saved["document"]
    assert case["document"]["history"]["past_conditions"] == document["history"]["past_conditions"]
    assert h.call("GET", detail, token)["document"] == saved["document"]
    learner, _ = member(h, token, org, "kidneylearner", "org_trainee")
    safe = h.call("GET", detail, learner)
    assert safe["title"] == document["learner_label"]
    assert not set(safe) & {"document", "instructor", "history", "code", "specialty"}
    h.call("POST", detail + "/retire", h.reviewer_token)
    h.call("GET", detail, learner, expected=404)
    retired = h.call("GET", detail, token)
    assert not retired["is_active"] and retired["document"] == saved["document"]


@pytest.mark.parametrize("scope", ["device", "control"])
@pytest.mark.parametrize("validated_first", [True, False])
def test_retirement_overlaps_grant_validation(interview, monkeypatch, scope, validated_first):
    h, token, _, _, credential, case, base, body, key = interview
    approve(interview)
    sid = h.call("POST", base + "/sessions", token, expected=201, json=body)["id"]
    # Start before the overlap so the race covers renewal, not session admission.
    h.call("POST", f"/device/training/sessions/{sid}/lease", credential)
    entered, release = Event(), Event()
    original = training.validate_active

    async def paused(*args):
        if validated_first:
            result = await original(*args)
        entered.set()
        assert await asyncio.to_thread(release.wait, 10), "test coordination timed out"
        return result if validated_first else await original(*args)

    monkeypatch.setattr(training, "validate_active", paused)
    path = (
        f"/device/training/sessions/{sid}/lease"
        if scope == "device"
        else base + f"/sessions/{sid}/access?control=true"
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(
            h.client.post, "/api/v1" + path, headers=h.headers(credential if scope == "device" else token)
        )
        try:
            assert entered.wait(10), "grant validation did not start"
            h.call("POST", base + f"/scenarios/{case['id']}/retire", h.reviewer_token)
        finally:
            release.set()
        reply = pending.result(10)
    assert reply.status_code == (200 if validated_first else 409)
    if validated_first:
        claims = jwt.decode(
            reply.json()["grant"],
            key.public_key(),
            algorithms=["EdDSA"],
            audience="device-training",
            issuer="pms-training-v1",
        )
        assert claims["exp"] - claims["iat"] <= 30
    monkeypatch.setattr(training, "validate_active", original)
    h.call("POST", f"/device/training/sessions/{sid}/lease", credential, expected=409)
    h.call("POST", base + f"/sessions/{sid}/access?control=true", token, expected=409)
    retained = h.call("GET", base + f"/sessions/{sid}", token)
    assert retained["scenario_id"] == case["id"] and retained["status"] == "active"
    assert (
        h.sql("SELECT document FROM device_platform.training_scenarios WHERE id=%s", (case["id"],))[0][0]
        == case["document"]
    )
