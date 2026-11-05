"""Clinical patient replies use facts, with bounded local inference and no Q&A bank."""

import json
import time
from uuid import uuid4

import httpx
import pytest
from test_coordinator import acknowledge, rig, start  # noqa: F401
from training_contracts import fingerprint
from training_contracts.clinical_cases import ClinicalRuntime
from training_contracts.localized_cases import review_localization
from training_contracts.scenarios import parse_draft

from device_training.engines import Dialogue, EngineError


def runtime(background=False):
    document = {
        "version": 4,
        "code": "clinical",
        "title": "Clinical interview",
        "learner_label": "Patient interview",
        "patient": {"name": "Alex", "age_years": 40},
        "presentation": {"chief_complaint": {"en": "My knee hurts.", "hi": "Knee pain"}},
        "history": {"allergies": {"knowledge": "none"}, "medications": {"knowledge": "unknown"}},
        "vitals": {"temperature_c": 37.1},
    }
    if background:
        document.update(
            version=5,
            background=[
                {
                    "id": "food_drink",
                    "text": {"en": "Home meals.", "hi": "Home meals"},
                    "allow_variation": True,
                    "choices": [
                        {"id": "rice", "text": {"en": "Rice and vegetables.", "hi": "Rice"}},
                        {"id": "bread", "text": {"en": "Bread and vegetables.", "hi": "Bread"}},
                    ],
                }
            ],
        )
    for language in ("en", "hi"):
        document = review_localization(document, language)
    return ClinicalRuntime(case=parse_draft(document))


def model_transport(handler):
    def route(request):
        if request.url.path == "/props":
            return httpx.Response(200, json={"default_generation_settings": {"n_ctx": 2048}})
        if request.url.path == "/apply-template":
            return httpx.Response(200, json={"prompt": "native fixture"})
        if request.url.path == "/tokenize":
            return httpx.Response(200, json={"tokens": [1] * 100})
        return handler(request)

    return httpx.MockTransport(route)


def selected_reply(payload, text):
    sources = json.loads(
        payload["messages"][0]["content"].split("\nSOURCE:\n", 1)[1].split("\nEND SOURCE.", 1)[0]
    )
    key = next(key for key, fact in sources.items() if fact["text"] == text)
    return httpx.Response(
        200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps([key])}}]}
    )


async def test_local_reply_uses_clinical_facts_and_completed_history():
    def handler(request):
        payload = json.loads(request.content)
        assert "response_format" not in payload
        assert "My knee hurts." in payload["messages"][0]["content"]
        assert "37.1" in payload["messages"][0]["content"]
        assert payload["messages"][-1] == {"role": "user", "content": "Where?"}
        return selected_reply(payload, "My knee hurts.")

    client = httpx.AsyncClient(base_url="http://127.0.0.1", transport=model_transport(handler))
    engine = Dialogue("http://127.0.0.1", "local", client=client)
    try:
        assert await engine.reply(runtime(), "Where?", [], "en") == "My knee hurts."
    finally:
        await engine.close()


@pytest.mark.parametrize(
    "content,finish",
    [
        ("x" * 601, "stop"),
        ("", "stop"),
        ("<think>secret</think>", "stop"),
        ("Cut off", "length"),
        ('{"answer":"My knee hurts"}', "stop"),
        ("<analysis>internal text</analysis>", "stop"),
        ("Patient: My knee hurts.", "stop"),
        ("```My knee hurts.```", "stop"),
    ],
)
async def test_invalid_reply_fails_closed(content, finish):
    client = httpx.AsyncClient(
        base_url="http://127.0.0.1",
        transport=model_transport(
            lambda request: httpx.Response(
                200, json={"choices": [{"finish_reason": finish, "message": {"content": content}}]}
            )
        ),
    )
    engine = Dialogue("http://127.0.0.1", "local", client=client)
    try:
        with pytest.raises(EngineError):
            await engine.reply(runtime(), "Hello", [], "en")
    finally:
        await engine.close()


@pytest.mark.parametrize("background", [False, True])
def test_coordinator_starts_and_speaks_without_authored_topics(rig, background):  # noqa: F811
    rig.document = runtime(background).model_dump(mode="json")
    rig.claims["scenario_hash"] = fingerprint(rig.document)

    async def reply(case, text, history, language):
        assert isinstance(case, ClinicalRuntime)
        return "My knee hurts."

    rig.dialogue.reply = reply
    state = start(rig)
    acknowledge(rig, state["turns"][0]["id"])
    response = rig.client.post(
        f"/sessions/{rig.sid}/turns/{uuid4()}",
        headers={**rig.headers(), "X-Capture-Offset-Ms": "111"},
        content=bytes(6400),
    )
    assert response.status_code == 200
    assert response.json()["answer"] == "My knee hurts."
    assert response.json()["topic"] == "clinical"


async def test_background_prepared_once_and_survives_short_history():
    snapshots = []

    def handler(request):
        payload = json.loads(request.content)
        snapshots.append(payload["messages"][0]["content"])
        assert payload["max_tokens"] == 128 and len(payload["messages"]) <= 6
        return selected_reply(payload, prepared["session_background"][0]["detail"])

    client = httpx.AsyncClient(base_url="http://127.0.0.1", transport=model_transport(handler))
    engine = Dialogue("http://127.0.0.1", "local", client=client)
    case = runtime(True)
    prepared = engine.prepare(case, "en", "session-one")
    try:
        first = await engine.reply(case, "What do you eat?", [], "en")
        history = [{"text": "Hello", "answer": "Hello", "playback": "finished"}] * 8
        second = await engine.reply(case, "What do you eat?", history, "en")
        assert snapshots[0] == snapshots[1] and "My knee hurts." not in snapshots[0]
        assert first == second == prepared["session_background"][0]["detail"]
        assert len(prepared["session_background"]) == 1
    finally:
        await engine.close()


async def test_history_window_keeps_last_two_completed_pairs_across_failed_turns():
    seen = []

    def handler(request):
        payload = json.loads(request.content)
        seen.extend(payload["messages"])
        return selected_reply(payload, "My knee hurts.")

    client = httpx.AsyncClient(base_url="http://127.0.0.1", transport=model_transport(handler))
    engine = Dialogue("http://127.0.0.1", "local", client=client)
    history = [
        {"text": text, "answer": answer, "playback": playback}
        for text, answer, playback in [
            ("Old", "Old answer", "finished"),
            ("Where?", "My knee", "finished"),
            ("Failed", "Never heard", "failed"),
            ("When?", "Yesterday", "finished"),
            ("Interrupted", "Never heard", "failed"),
        ]
    ]
    try:
        await engine.reply(runtime(True), "And now?", history, "en")
        assert [message["content"] for message in seen[1:]] == [
            "Where?",
            "My knee",
            "When?",
            "Yesterday",
            "And now?",
        ]
    finally:
        await engine.close()


def test_rejected_background_translation_does_not_admit_or_strand_session(rig):  # noqa: F811
    case = runtime(True)
    rig.claims["language"] = "en"
    rig.document = case.model_dump(mode="json")
    rig.document["case"]["background"][0]["text"]["en"] = "Unreviewed edit"
    rig.claims["scenario_hash"] = fingerprint(rig.document)
    coordinator = rig.app.state.coordinator

    def prepare(case, language, seed):
        from training_contracts.conversation.prompt import conversation_context

        return conversation_context(case.case.model_dump(mode="json"), language, "", seed=seed)

    rig.dialogue.prepare = prepare
    path = f"/sessions/{rig.sid}/start"
    body = {"scenario": rig.document, "anchor_unix_ms": int(time.time() * 1000)}
    for _ in range(2):
        response = rig.client.post(path, headers=rig.headers(), json=body)
        assert response.status_code == 422 and response.json()["detail"] == "scenario_language_unavailable"
        assert not coordinator.data and not coordinator.tasks and not coordinator.claims
    rig.document = case.model_dump(mode="json")
    rig.claims["scenario_hash"] = fingerprint(rig.document)

    async def reply(case, text, history, language):
        return "My knee hurts."

    rig.dialogue.reply = reply
    assert start(rig)["status"] == "active"
