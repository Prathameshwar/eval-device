"""Online selection contracts; provider calls are mocked, PostgreSQL is disposable."""

import json
from uuid import uuid4

import pytest
from test_cloud_models import AZURE, configure
from test_llm_api import llm as llm


def payload(remote, speech, route):
    return {
        "profile_id": route["profile_id"],
        "expected_revision_id": route["profile_revision_id"],
        "llm_connection_id": remote["id"],
        "speech_connection_id": speech["id"],
        "expected_llm_revision": remote["revision"],
        "expected_speech_revision": speech["configuration_version"],
        "activate": True,
    }


def test_online_catalog_and_model_switches(llm, monkeypatch):
    p, token, org, remote, speech, route, _ = configure(llm, monkeypatch)
    base = f"/organizations/{org}"
    options = p.call("GET", base + "/model-options", token)
    assert options["availability"]["cloud_allowed"]
    assert options["speech"][0]["revision"] == speech["configuration_version"]
    assert "fixture" not in json.dumps(options) and "base_url" not in json.dumps(options)
    assert "api_key" not in json.dumps(options)
    outsider, _ = p.admin("online-catalog-outsider")
    p.call("GET", base + "/model-options", outsider, expected=404)
    user, _ = p.user("online-no-membership")
    p.call("POST", base + "/model-profiles", user, expected=403, json=payload(remote, speech, route))
    p.settings.llm_allowed_base_urls += ["https://api.openai.com/v1", "https://models.example/v1"]
    for provider, url, model in (
        ("openai", "https://api.openai.com/v1", "gpt-4.1"),
        ("openai_compatible", "https://models.example/v1", "configured-alias"),
        ("azure_openai", AZURE, "alternate-patient-deployment"),
    ):
        selected = p.call(
            "POST",
            base + "/llm/connections",
            token,
            expected=201,
            json={
                "name": provider,
                "provider": provider,
                "base_url": url,
                "model": model,
                "api_key": "fixture-switch-key",
                "model_options": {"context_tokens": 8192},
            },
        )
        ready = p.call("GET", base + f"/llm/connections/{selected['id']}/status", token)
        assert ready["status"] == "ready" and ready["inference_verified"] is False
        previous = route
        route = p.call("POST", base + "/model-profiles", token, json=payload(selected, speech, route))
        assert route["llm"]["provider"] == provider and route["llm"]["model"] == model
        assert route["llm"]["requires_external"] is True
        assert route["configuration_hash"] != previous["configuration_hash"]
        stale = p.call(
            "POST", base + "/model-profiles", token, expected=409, json=payload(selected, speech, previous)
        )
        assert stale["error"]["code"] == "version_conflict"


@pytest.mark.parametrize("kind", ["llm", "speech"])
def test_activation_rejects_changed_connection_without_publication(llm, monkeypatch, kind):
    p, token, org, remote, speech, route, _ = configure(llm, monkeypatch)
    base = f"/organizations/{org}"
    body = payload(remote, speech, route)
    body[f"expected_{kind}_revision"] += 1
    failure = p.call("POST", base + "/model-profiles", token, expected=409, json=body)
    assert failure["error"]["code"] == f"{kind}_connection_changed"
    assert p.call("GET", base + "/model-config", token)["profile_revision_id"] == route["profile_revision_id"]


@pytest.mark.parametrize("gate", ["external_calls_enabled", "speech_enabled", "llm_enabled"])
def test_online_activation_rechecks_operator_gates(llm, monkeypatch, gate):
    p, token, org, remote, speech, route, _ = configure(llm, monkeypatch)
    setattr(p.settings, gate, False)
    base = f"/organizations/{org}"
    p.call("POST", base + "/model-profiles", token, expected=503, json=payload(remote, speech, route))
    assert p.call("GET", base + "/model-config", token)["profile_revision_id"] == route["profile_revision_id"]


def test_platform_media_switches_independently_and_survives_patient_model_save(llm, monkeypatch):
    p, token, org, remote, speech, route, _ = configure(llm, monkeypatch)
    base = f"/organizations/{org}"

    class AccessCheck:
        async def validate(self, operation, sample):
            assert sample is False
            return True

    monkeypatch.setattr(
        "pms_api.integrations.providers.ProviderFactory.for_connection", lambda *args: AccessCheck()
    )
    connections = {}
    for name, provider, kind, auth, settings, credentials in (
        (
            "AWS",
            "aws",
            "aws_processing",
            "access_key",
            {"region": "ap-south-1"},
            {"access_key_id": "fixture", "secret_access_key": "fixture-secret"},
        ),
        (
            "Azure video",
            "azure",
            "azure_video_indexer",
            "service_principal",
            {
                "subscription_id": str(uuid4()),
                "resource_group": "fixture",
                "account_name": "fixture",
                "account_id": str(uuid4()),
                "location": "centralindia",
                "tenant_id": str(uuid4()),
                "client_id": str(uuid4()),
            },
            {"client_secret": "fixture-secret"},
        ),
        (
            "Azure voice",
            "azure",
            "azure_speech",
            "api_key",
            {"region": "centralindia"},
            {"api_key": "fixture-key"},
        ),
    ):
        conn = p.call(
            "POST",
            base + "/connections",
            token,
            expected=201,
            json={
                "name": name,
                "provider": provider,
                "connection_type": kind,
                "auth_mode": auth,
                "settings": settings,
                "credentials": credentials,
            },
        )
        connections[name] = conn["id"]
        for operation in (
            ["video.labels", "audio.synthesize", "audio.transcribe"]
            if name == "AWS"
            else ["video.labels"]
            if name == "Azure video"
            else ["audio.synthesize", "audio.transcribe"]
        ):
            p.call(
                "POST",
                base + f"/connections/{conn['id']}/validate",
                token,
                json={"operation": operation, "sample": False},
            )
    options = p.call("GET", base + "/model-options", token)
    assert {x["name"] for x in options["platform_services"]} == set(connections)
    assert {x["id"] for x in options["speech"]} == {speech["id"]}, (
        "Batch engines must not masquerade as interactive speech"
    )
    device = p.device(token, org)
    credential = p.enroll(token, org, device["id"])
    profile_path = base + f"/profiles/{route['profile_id']}"
    for video_name, video_engine, voice_name, voice_engine in (
        ("AWS", "aws_rekognition", "AWS", "aws_polly"),
        ("Azure video", "azure_video_indexer", "Azure voice", "azure_speech"),
    ):
        draft = next(
            item["draft_settings"]
            for item in p.call("GET", base + "/profiles", token)["items"]
            if item["id"] == route["profile_id"]
        )
        draft["video"] = {
            "enabled": True,
            "operation": "video.labels",
            "execution_mode": "cloud",
            "engine": video_engine,
            "format": "mp4",
            "clip_seconds": 5,
            "width": 640,
            "height": 480,
            "fps": 10,
        }
        draft["audio_output"] = {
            "enabled": True,
            "operation": "audio.synthesize",
            "execution_mode": "cloud",
            "engine": voice_engine,
            "format": "wav",
            "language": "hi-IN",
        }
        p.call(
            "PATCH",
            profile_path,
            token,
            json={
                "draft_settings": draft,
                "draft_video_connection_id": connections[video_name],
                "draft_audio_output_connection_id": connections[voice_name],
            },
        )
        p.call(
            "POST",
            profile_path + "/publish",
            token,
            json={"expected_revision_id": route["profile_revision_id"]},
        )
        route = p.call("GET", base + "/model-config", token)
        route = p.call("POST", base + "/model-profiles", token, json=payload(remote, speech, route))
        config = p.call("GET", "/device/config", credential)
        assert config["settings"]["video"]["engine"] == video_engine
        assert config["connections"]["video"]["id"] == connections[video_name]
        assert config["connections"]["audio_output"]["id"] == connections[voice_name]
        assert route["platform_media"]["video"]["connection_id"] == connections[video_name]
        assert route["platform_media"]["audio_output"]["settings"]["language"] == "hi-IN"
