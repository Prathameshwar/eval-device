"""Regression checks for configuration versions, media projections and catalog concurrency."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

from test_patient_catalog_management import category, owner_with_author


def test_catalog_serializes_concurrent_edits_and_audits_only_the_winner(platform):
    h = platform
    token, _, org, _ = owner_with_author(h, "concurrent-owner")
    original = h.call(
        "POST",
        f"/organizations/{org}/clinical-catalog/specialties",
        token,
        expected=201,
        json=category("concurrent_category"),
    )
    path = f"/api/v1/organizations/{org}/clinical-catalog/specialties/" + original["id"]

    def edit(name):
        payload = {**category("concurrent_category"), "name": name, "names": {"en": name}}
        return h.client.patch(
            path, headers=h.headers(token), json={"expected_version": 1, "data": payload}
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(edit, ["Concurrent first", "Concurrent second"]))
    assert sorted(statuses) == [200, 409]
    assert (
        h.sql("SELECT count(*) FROM device_platform.activity_events WHERE entity_id=%s", (original["id"],))[
            0
        ][0]
        == 2
    )


def test_configuration_publish_and_archives_reject_stale_versions(platform):
    h = platform
    owner, _ = h.user("configuration-owner")
    org = h.organization(owner)["id"]
    base = f"/organizations/{org}"
    foreign, _ = h.admin("foreign-admin")
    h.call("GET", base + "/configuration-options", foreign, expected=404)
    options = h.call("GET", base + "/configuration-options", owner)
    assert options["operations"]["audio.activity"]["engines"] == {"audio_activity": None}
    connection = h.call(
        "POST",
        base + "/connections",
        owner,
        expected=201,
        json={
            "name": "Provider",
            "provider": "aws",
            "connection_type": "aws_processing",
            "auth_mode": "workload_identity",
            "settings": {"region": "ap-south-1"},
        },
    )
    cp = base + "/connections/" + connection["id"]
    changed = h.call(
        "PATCH",
        cp,
        owner,
        json={"expected_version": connection["configuration_version"], "settings": {"region": "us-east-1"}},
    )
    h.call(
        "DELETE", cp + "?expected_version=" + str(connection["configuration_version"]), owner, expected=409
    )
    h.call("DELETE", cp + "?expected_version=" + str(changed["configuration_version"]), owner)
    profile = h.call("POST", base + "/profiles", owner, expected=201, json={"name": "Local profile"})
    pp = base + "/profiles/" + profile["id"]
    edited = h.call(
        "PATCH", pp, owner, json={"expected_version": profile["management_version"], "name": "Edited profile"}
    )
    h.call(
        "POST",
        pp + "/publish",
        owner,
        expected=409,
        json={"expected_version": profile["management_version"], "expected_revision_id": None},
    )
    revision = h.call(
        "POST",
        pp + "/publish",
        owner,
        json={"expected_version": edited["management_version"], "expected_revision_id": None},
    )
    assert revision["version"] == 1
    h.call("DELETE", pp + "?expected_version=" + str(profile["management_version"]), owner, expected=409)
    department = h.call("POST", base + "/departments", owner, expected=201, json={"name": "Department"})
    dp = base + "/departments/" + department["id"]
    h.call("PATCH", dp, owner, json={"expected_version": department["management_version"], "name": "Renamed"})
    h.call("DELETE", dp + "?expected_version=" + str(department["management_version"]), owner, expected=409)


def test_media_directory_is_scoped_redacted_and_retention_bounded(platform, monkeypatch):
    h = platform
    token, _ = h.user("media-owner")
    org = h.organization(token)["id"]
    device = h.device(token, org)["id"]
    credential = h.enroll(token, org, device)
    _, revision = h.profile(token, org)
    run = h.call(
        "POST",
        f"/organizations/{org}/runs",
        token,
        expected=202,
        json={
            "request_key": str(uuid4()),
            "operation": "audio.activity",
            "device_id": device,
            "profile_revision_id": revision["id"],
            "duration_seconds": 1,
        },
    )["run"]
    h.call(
        "POST",
        "/device/runs/" + run["id"] + "/result",
        credential,
        json={"status": "succeeded", "result": {"activity": True}},
    )
    h.sql(
        "UPDATE device_platform.processing_runs SET media_manifest=%s,media_expires_at=now()+interval '1 day',cleanup_status='pending',cleanup_next_attempt_at=now()+interval '1 day' WHERE id=%s",
        (
            json.dumps(
                [
                    {"role": "input", "storage": "platform", "format": "wav", "key": "private-object-key"},
                    {"role": "output", "storage": "provider", "format": "wav", "key": "provider-private-key"},
                ]
            ),
            run["id"],
        ),
    )
    path = f"/organizations/{org}/runs/{run['id']}/media"
    foreign, _ = h.admin("platform-without-media")
    h.call("GET", path, foreign, expected=404)
    assert h.call("GET", path, token) == {
        "items": [{"index": 0, "role": "input", "format": "wav", "content_type": "audio/wav"}]
    }
    from pms_api.modules import processing

    future = processing.now() + timedelta(days=2)
    monkeypatch.setattr(processing, "now", lambda: future)
    h.call("GET", path, token, expected=410)
