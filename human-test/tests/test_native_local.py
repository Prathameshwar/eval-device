"""Opt-in: the resident local Qwen, driven exactly as a real local turn drives it.

PMS never dials a model that runs on this laptop, so the shared single-call conversation engine and the
native token budget are exercised here, where the turn is actually executed. Start the model
with start/start-local-models.bat, then set HUMAN_TEST_NATIVE_LLM=1.
"""

import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from local_model_client.llm import new_client
from test_flow import settings
from training_client import local_turn

CONTEXT_TOKENS = 2048
CASES = Path(__file__).parents[2] / "platform/api/migrations/versions/0014_patient_case_templates.json"
STATE_KEY = Path(__file__).parents[2] / "local-models/.manager/client-key.txt"

native = pytest.mark.skipif(
    os.getenv("HUMAN_TEST_NATIVE_LLM") != "1", reason="Opt-in resident local Qwen check"
)


def resident():
    key_file = Path(os.environ.get("HUMAN_TEST_LLM_KEY_FILE", STATE_KEY))
    route = {
        "profile_id": str(uuid4()),
        "profile_revision_id": str(uuid4()),
        "configuration_hash": "c" * 64,
        "llm": {
            "mode": "local",
            "execution": "caller",
            "provider": "local_llama_cpp",
            # PMS publishes the served alias, which is what the model server answers to.
            "model": os.environ.get("HUMAN_TEST_LLM_MODEL", "qwen3.5-4b-local"),
            "connection_id": str(uuid4()),
            "connection_revision": 1,
            "model_options": {},
            "max_tokens": 256,
            "instruction_role": "system",
            "system_prompt": "You are a helpful assistant.",
            "local_port": int(os.environ.get("HUMAN_TEST_LLM_PORT", "8787")),
            "local_context_tokens": CONTEXT_TOKENS,
        },
    }
    value = settings(
        local_models_key=key_file.read_text(encoding="utf-8").strip(),
        local_models_port=int(os.environ.get("HUMAN_TEST_MANAGER_PORT", "8790")),
    )
    client = new_client(value.timeout_seconds)
    return route, local_turn.local_model(route, value, client=client), client


def document():
    rows = json.loads(CASES.read_text(encoding="utf-8"))
    return next(row["document"] for row in rows if row["code"] == "alex_dry_cough")


@native
async def test_the_resident_model_answers_a_plain_question_here():
    route, model, client = resident()
    try:
        await local_turn.health(model)
        event = await local_turn.answer(
            model,
            route,
            None,
            [{"role": "user", "content": "Reply with one number: 12 + 8 = ?"}],
            "en",
            lambda *a: None,
        )
        assert "20" in event["text"] and event["finish_reason"] == "stop"
        assert event["language"] == "en"
    finally:
        await client.aclose()


@native
async def test_the_resident_model_uses_case_facts_and_general_knowledge_in_one_call():
    route, model, client = resident()
    case = document()
    practice = {"practice_id": str(uuid4()), "practice_revision": 1, "document": case}
    observations = []
    try:
        await local_turn.health(model)
        for question, expected in (
            ("What is your name?", "Alex"),
            ("How old are you?", "35"),
            ("What is your temperature?", str(case["vitals"]["temperature_c"])),
            ("What did you eat yesterday?", "rice"),
            ("What is the capital of France?", "Paris"),
        ):
            event = await local_turn.answer(
                model,
                route,
                practice,
                [{"role": "user", "content": question}],
                "en",
                lambda *a: None,
                diagnostic=True,
            )
            budget = event["context"]["conversation"]
            assert budget["method"] == "native_tokenizer"
            assert budget["prompt_tokens"] + budget["reserved_output_tokens"] + 128 <= CONTEXT_TOKENS
            assert event["provider_calls"] == 1 and event["answer_source"] == "patient_conversation"
            assert event["language"] == "en" and not event["topics"]
            assert expected.lower() in event["text"].lower()
            record = local_turn.turn_event(route, practice, event)
            assert event["text"] not in json.dumps(record) and question not in json.dumps(record)
            observations.append(
                {
                    "question": question,
                    "answer": event["text"],
                    "total_ms": event["total_ms"],
                    "context": event["context"],
                    "prompt_hash": event["prompt_hash"],
                    "record": record,
                }
            )
    finally:
        await client.aclose()
    if destination := os.getenv("HUMAN_TEST_PATIENT_EVIDENCE"):
        Path(destination).write_text(json.dumps(observations, ensure_ascii=False, indent=2), encoding="utf-8")
