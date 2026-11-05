import json
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from training_contracts import Scenario, fingerprint

from device_training.app import create_app
from device_training.config import Settings
from device_training.engines import EngineError
from device_training.media import wav


class Dialogue:
    def __init__(self):
        self.calls = 0
        self.fail = False

    async def select(self, case, text, history):
        self.calls += 1
        if self.fail:
            raise EngineError()
        return "onset"

    async def close(self):
        pass


class Speech:
    async def synthesize(self, text, language):
        return wav(bytes(3200))


class Transcriber:
    async def check(self):
        pass

    async def transcribe(self, chunks, language, guard, collected):
        async for chunk in chunks:
            guard()
            collected.extend(chunk)
        return "When did it start?", str(uuid4()), {"status": "disabled"}


@pytest.fixture
def rig(tmp_path):
    key = Ed25519PrivateKey.generate()
    public = tmp_path / "public.pem"
    public.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    model = tmp_path / "model.key"
    model.write_text("test-model-key-" * 4)
    org, device, sid, user = [str(uuid4()) for _ in range(4)]
    settings = Settings(
        _env_file=None,
        organization_id=org,
        device_id=device,
        platform_url="http://127.0.0.1:8080",
        public_key_file=public,
        store=tmp_path / "private",
        audio_token="a" * 40,
        video_token="v" * 40,
        video_store=tmp_path / "video",
        dialogue_key_file=model,
        speech_executable=tmp_path / "unused.exe",
    )
    document = json.loads(
        (Path(__file__).parents[1] / "src/device_training/scenarios/cough_interview_dev.json").read_text(
            encoding="utf-8"
        )
    )
    claims = {
        "iss": "pms-training-v1",
        "aud": "device-training",
        "sub": device,
        "iat": int(time.time()),
        "nbf": int(time.time()),
        "exp": int(time.time()) + 30,
        "jti": str(uuid4()),
        "scope": "device",
        "session_id": sid,
        "organization_id": org,
        "device_id": device,
        "scenario_id": str(uuid4()),
        "scenario_hash": fingerprint(document),
        "learner_id": user,
        "instructor_id": user,
        "language": "hi",
        "session_deadline": time.time() + 120,
        "duration_seconds": 120,
        "tts_budget": 3000,
        "limits": {
            "max_turns": 30,
            "max_audio_turn_seconds": 30,
            "max_width": 640,
            "max_height": 480,
            "max_fps": 10,
            "media_retention_hours": 1,
        },
    }

    def headers(**overrides):
        return {"Authorization": "Bearer " + jwt.encode({**claims, **overrides}, key, algorithm="EdDSA")}

    dialogue = Dialogue()
    app = create_app(settings, dialogue=dialogue, speech=Speech(), transcriber=Transcriber())
    with TestClient(app, base_url="http://127.0.0.1:8767", client=("127.0.0.1", 50001)) as client:
        yield SimpleNamespace(
            client=client,
            app=app,
            sid=sid,
            document=document,
            headers=headers,
            settings=settings,
            dialogue=dialogue,
            claims=claims,
        )


def start(rig):
    response = rig.client.post(
        f"/sessions/{rig.sid}/start",
        headers=rig.headers(),
        json={"scenario": rig.document, "anchor_unix_ms": int(time.time() * 1000), "simulated": True},
    )
    assert response.status_code == 200, response.text
    for _ in range(100):
        state = rig.client.get(f"/sessions/{rig.sid}", headers=rig.headers()).json()
        if state["status"] != "warming":
            assert state["status"] == "active", state
            return state
        time.sleep(0.01)
    pytest.fail("warmup did not finish")


def acknowledge(rig, tid):
    for event, offset in [("claim", 100), ("started", 101), ("finished", 110)]:
        response = rig.client.post(
            f"/sessions/{rig.sid}/turns/{tid}/playback",
            headers=rig.headers(),
            json={"event": event, "offset_ms": offset},
        )
        assert response.status_code == 200, response.text


def test_real_journal_turn_and_no_duplicate_playback(rig):
    state = start(rig)
    acknowledge(rig, state["turns"][0]["id"])
    tid = str(uuid4())
    path = f"/sessions/{rig.sid}/turns/{tid}"
    headers = {**rig.headers(), "X-Capture-Offset-Ms": "111"}
    response = rig.client.post(path, headers=headers, content=bytes(6400))
    assert response.status_code == 200, response.text
    turn = response.json()
    assert turn["topic"] == "onset" and any("\u0900" <= c <= "\u097f" for c in turn["answer"])
    assert rig.client.post(path, headers=headers, content=bytes(6400)).status_code == 409
    # Claim/ack transitions must not automatically replay after uncertain delivery.
    playback = path + "/playback"
    assert (
        rig.client.post(
            playback, headers=rig.headers(), json={"event": "claim", "offset_ms": 200}
        ).status_code
        == 200
    )
    assert (
        rig.client.post(
            playback, headers=rig.headers(), json={"event": "claim", "offset_ms": 200}
        ).status_code
        == 409
    )
    content = rig.client.get(path + "/patient.wav", headers=rig.headers(scope="read")).content
    assert content.startswith(b"RIFF")
    response = rig.client.post(f"/sessions/{rig.sid}/stop", headers=rig.headers(scope="control"), json={})
    assert response.json()["turns"][-1]["playback"] == "unknown"
    assert (
        rig.client.post(
            playback, headers=rig.headers(), json={"event": "started", "offset_ms": 201}
        ).status_code
        == 409
    )
    saved = (rig.settings.store / rig.sid / "session.json").read_text(encoding="utf-8")
    assert "Bearer" not in saved and "eyJ" not in saved
    assert rig.dialogue.calls == 2


def test_authorization_origin_and_scenario_integrity(rig):
    body = {"scenario": rig.document, "anchor_unix_ms": 1}
    path = f"/sessions/{rig.sid}/start"
    for headers in [
        {},
        rig.headers(scope="read"),
        rig.headers(organization_id=str(uuid4())),
        rig.headers(exp=int(time.time()) - 1),
    ]:
        assert rig.client.post(path, headers=headers, json=body).status_code == 401
    assert (
        rig.client.post(
            path, headers={**rig.headers(), "Origin": "https://evil.example"}, json=body
        ).status_code
        == 403
    )
    assert (
        rig.client.post(path, headers={**rig.headers(), "Host": "evil.example"}, json=body).status_code == 403
    )
    assert rig.client.post(path + "?token=invalid", headers=rig.headers(), json=body).status_code == 400
    body["scenario"] = {**rig.document, "title": "Tampered"}
    assert rig.client.post(path, headers=rig.headers(), json=body).status_code == 409
    assert rig.client.post(path, headers=rig.headers(), json={"oops": 1}).status_code == 422


def test_dialogue_fallback_and_lease_expiry(rig):
    state = start(rig)
    acknowledge(rig, state["turns"][0]["id"])
    rig.dialogue.fail = True
    response = rig.client.post(
        f"/sessions/{rig.sid}/turns/{uuid4()}",
        headers={**rig.headers(), "X-Capture-Offset-Ms": "111"},
        content=bytes(6400),
    )
    assert response.status_code == 200
    assert response.json()["fallback"] and response.json()["topic"] == "clarify"
    rig.app.state.coordinator.claims["exp"] = time.time() - 1
    time.sleep(0.3)
    state = rig.client.get(f"/sessions/{rig.sid}", headers=rig.headers(scope="read")).json()
    assert state["status"] == "failed" and state["reason"] == "authorization_expired"
    assert rig.client.post(f"/sessions/{rig.sid}/lease", headers=rig.headers()).status_code == 409


def test_no_live_bulk_extraction_and_oversize_input(rig):
    state = start(rig)
    acknowledge(rig, state["turns"][0]["id"])
    assert (
        rig.client.post(
            f"/sessions/{rig.sid}/prepare-replay", headers=rig.headers(scope="read"), json={}
        ).status_code
        == 409
    )
    response = rig.client.post(
        f"/sessions/{rig.sid}/turns/{uuid4()}",
        headers={**rig.headers(), "X-Capture-Offset-Ms": "111"},
        content=bytes(960002),
    )
    assert response.status_code == 413
    assert rig.client.get(f"/sessions/{rig.sid}", headers=rig.headers()).json()["status"] == "failed"


def test_synthetic_case_preserves_hindi_and_excludes_rubric_from_patient(rig):
    case = Scenario.model_validate(rig.document)
    assert "rubric" not in case.patient()
    for value in [case.greeting, case.clarification, *(t.answer for t in case.topics)]:
        assert any("\u0900" <= c <= "\u097f" for c in value.hi)


def test_two_cases_on_one_device_keep_answers_and_media_separate(rig):
    first = start(rig)
    acknowledge(rig, first["turns"][0]["id"])
    first_turn = str(uuid4())
    first_response = rig.client.post(
        f"/sessions/{rig.sid}/turns/{first_turn}",
        headers={**rig.headers(), "X-Capture-Offset-Ms": "111"},
        content=bytes(6400),
    )
    assert first_response.status_code == 200
    first_answer = first_response.json()["answer"]
    assert rig.client.post(f"/sessions/{rig.sid}/stop",
                           headers=rig.headers(scope="control"), json={}).status_code == 200

    second_case = json.loads(json.dumps(rig.document))
    topic = next(item for item in second_case["topics"] if item["id"] == "onset")
    topic["answer"] = {"en": "Second fictional case answer.",
                       "hi": "दूसरे काल्पनिक मामले का उत्तर।"}
    second_case["greeting"] = {"en": "Second fictional patient.",
                               "hi": "दूसरा काल्पनिक रोगी।"}
    second = str(uuid4())
    grants = {"session_id": second, "scenario_id": str(uuid4()),
              "scenario_hash": fingerprint(second_case)}
    response = rig.client.post(f"/sessions/{second}/start", headers=rig.headers(**grants),
                               json={"scenario": second_case, "anchor_unix_ms": 1,
                                     "simulated": True})
    assert response.status_code == 200, response.text
    for _ in range(100):
        state = rig.client.get(f"/sessions/{second}", headers=rig.headers(**grants)).json()
        if state["status"] == "active":
            break
        time.sleep(0.01)
    assert state["status"] == "active"
    for event, offset in (("claim", 100), ("started", 101), ("finished", 110)):
        assert rig.client.post(f"/sessions/{second}/turns/{state['turns'][0]['id']}/playback",
                               headers=rig.headers(**grants),
                               json={"event": event, "offset_ms": offset}).status_code == 200
    second_turn = str(uuid4())
    reply = rig.client.post(f"/sessions/{second}/turns/{second_turn}",
                            headers={**rig.headers(**grants), "X-Capture-Offset-Ms": "111"},
                            content=bytes(6400))
    assert reply.status_code == 200
    assert reply.json()["answer"] == topic["answer"]["hi"]
    assert reply.json()["answer"] != first_answer
    saved = (rig.settings.store / second / "session.json").read_text(encoding="utf-8")
    assert first_answer not in saved and rig.sid not in saved and first_turn not in saved
    assert second_turn + "-patient.wav" in {item.name for item in (rig.settings.store / second).iterdir()}
    assert first_turn + "-patient.wav" not in {item.name for item in (rig.settings.store / second).iterdir()}


def test_stop_during_warmup_cannot_deliver_into_new_session(rig):
    import asyncio
    import threading

    entered, release = threading.Event(), threading.Event()

    async def blocked(case, text, history):
        entered.set()
        while not release.is_set():
            await asyncio.sleep(0.01)
        return "onset"

    rig.dialogue.select = blocked
    body = {"scenario": rig.document, "anchor_unix_ms": 1}
    assert rig.client.post(f"/sessions/{rig.sid}/start", headers=rig.headers(), json=body).status_code == 200
    assert entered.wait(1)
    assert (
        rig.client.post(
            f"/sessions/{rig.sid}/stop", headers=rig.headers(scope="control"), json={}
        ).status_code
        == 200
    )
    replacement = str(uuid4())
    assert (
        rig.client.post(
            f"/sessions/{replacement}/start", headers=rig.headers(session_id=replacement), json=body
        ).status_code
        == 409
    )
    release.set()
    time.sleep(0.05)
    state = rig.client.get(f"/sessions/{rig.sid}", headers=rig.headers(scope="read")).json()
    assert state["status"] == "cancelled" and state["turns"] == []


def test_peer_device_scope_and_expired_recording_cannot_read(rig):
    start(rig)
    path = f"/sessions/{rig.sid}"
    assert rig.client.get(path, headers=rig.headers(device_id=str(uuid4()), scope="read")).status_code == 401
    rig.app.state.coordinator.data["expires_at"] = time.time() - 1
    assert rig.client.get(path, headers=rig.headers(scope="read")).status_code == 404
