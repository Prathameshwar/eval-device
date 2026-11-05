import json
from uuid import uuid4

import pytest
from test_llm_api import llm as llm
from test_patient_practice import setup
from training_contracts.languages import DEFAULT_REGISTRY

from pms_api.integrations.llm import LLMError
from pms_api.modules.patient_context import exact_fact_answer


@pytest.mark.parametrize(
    "topics,expected",
    [
        (["name"], True),
        (["temperature"], True),
        (["age"], True),
        (["medications"], False),
        (["duration"], False),
        (["name", "age"], False),
        ([], False),
    ],
)
def test_only_single_objective_fact_skips_paraphrasing(topics, expected):
    assert exact_fact_answer({"topics": topics}) is expected


@pytest.mark.parametrize("language", ["en", "hi"])
def test_exact_patient_facts_keep_disclosure_usage_and_idempotency(llm, monkeypatch, language):
    p, token, _, org, base, connection, body, model = llm
    installed_languages = [pack.language for pack in DEFAULT_REGISTRY.all()]
    if language not in installed_languages:
        pytest.skip(f"No bundled {language} patient conversation pack")
    p.settings.patient_enabled_languages = installed_languages
    p.settings.patient_remote_context_tokens = 16384
    _, _, saved = setup(p, token, org, language=language)
    from test_patient_conversations import start_conversation

    _, _, conversation = start_conversation(p, token, org, connection, saved, language=language)
    topic = "age"

    async def budget(client, params, settings, **kw):
        return params["messages"], {
            "prompt_tokens": 700,
            "reserved_output_tokens": params["max_tokens"],
            "safety_margin_tokens": 128,
        }

    async def events(**params):
        model.calls += 1
        if topic == "invalid_json":
            raise LLMError("llm_invalid_response")
        assert "CASE FACTS" in params["messages"][0]["content"]
        yield {
            "type": "done",
            "text": ("I am 35 years old." if language == "en" else "मेरी उम्र 35 साल है।")
            if topic == "age"
            else '{"kind":"unknown","topics":[]}',
            "finish_reason": "stop",
            "total_ms": 30,
            "usage": {"prompt_tokens": 700, "completion_tokens": 12, "total_tokens": 712},
        }

    monkeypatch.setattr("pms_api.modules.llm.fit_patient_prompt", budget)
    monkeypatch.setattr(model, "events", events)
    body.update(
        practice_id=saved["id"],
        practice_revision=saved["revision"],
        conversation_id=conversation["context"]["conversation_id"],
        language=language,
    )
    for streaming in (False, True):
        body.update(request_key=str(uuid4()), stream=streaming)
        response = p.client.post("/api/v1" + base + "/completions", headers=p.headers(token), json=body)
        assert response.status_code == 200
        result = (
            next(
                json.loads(line[5:])
                for line in response.text.splitlines()
                if line.startswith("data:") and json.loads(line[5:]).get("type") == "done"
            )
            if streaming
            else response.json()
        )
        assert result["provider_calls"] == 1 and result["answer_source"] == "patient_conversation"
        assert result["usage"]["total_tokens"] == 712
        assert "voice" not in result["context"] and "35" in result["text"]
        assert any("\u0900" <= c <= "\u097f" for c in result["text"]) == (language == "hi")
        # Retrying the same request reads the authorized saved result without another call.
        before = model.calls
        cached = p.call("POST", base + "/completions", token, json={**body, "stream": False})
        assert cached["cached"] and cached["text"] == result["text"] and model.calls == before
    # A malformed provider response is rejected after one call.
    topic = "invalid_json"
    before = model.calls
    rejected = p.call(
        "POST",
        base + "/completions",
        token,
        expected=502,
        json={**body, "request_key": str(uuid4()), "stream": False},
    )
    assert rejected["error"]["code"] == "llm_invalid_response"
    assert model.calls == before + 1
