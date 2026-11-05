"""One authored case, two hosts: the same answer whether the platform or the laptop runs it.

A cloud model is dispatched by this service; a local model is executed on the laptop and this
service never sees the prompt or the answer. Both hosts drive the same shared pipeline, so the
prompts they build and the events they produce must match. What may differ is only what the
host owns: the per-call output allowance a native server needs, and how a prompt is measured.
"""

import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from test_patient_practice import expanded_document, routing
from training_contracts.patient_conversation import conversation_context, run_conversation
from training_contracts.patient_turn import (
    authored_event,
    frame,
    patient_context,
    patient_event,
    route,
    voice_messages,
)

from pms_api.core.config import Settings
from pms_api.integrations.llm import LLMClient
from pms_api.integrations.llm.budget import fit_patient_prompt as platform_fit
from pms_api.integrations.llm.runner import ProviderRunner

QUESTION = "What brings you in today, and how long has it been going on?"
ROUTED = '{"kind":"topic","topics":["complaint","duration"]}'
# No digit anywhere: the fact guard rejects any number the authored facts do not contain.
SPOKEN = "I have had a dry cough for about three weeks, doctor."
CLOUD_URL = "https://models.example/v1"
PORT = 8787
USAGE = {"prompt_tokens": 700, "completion_tokens": 20, "total_tokens": 720}
# Equal limits on both sides so this test compares prompt construction, not context sizing;
# the real 2048-token local window and the remote estimate are covered by
# test_routing_prompt_stays_inside_the_local_context_budget.
SETTINGS = Settings.model_construct(patient_local_context_tokens=8192, patient_remote_context_tokens=8192)


def sse(text):
    chunks = [
        {"choices": [{"delta": {"content": text}, "finish_reason": "stop"}]},
        {"choices": [], "usage": USAGE},
    ]
    return "".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks) + "data: [DONE]\n\n"


def model_server(calls):
    """One llama.cpp-compatible server, reachable as loopback and as a cloud endpoint."""

    def handler(request):
        path = request.url.path
        data = json.loads(request.content) if request.content else {}
        if path == "/props":
            return httpx.Response(200, json={"default_generation_settings": {"n_ctx": 8192}})
        if path == "/apply-template":
            return httpx.Response(
                200, json={"prompt": "".join(m["role"] + ":" + m["content"] for m in data["messages"])}
            )
        if path == "/tokenize":
            return httpx.Response(200, json={"tokens": [1] * (len(data["content"]) // 3)})
        assert path == "/v1/chat/completions", path
        calls.append(data)
        speaking = "CASE FACTS" in data["messages"][0]["content"]
        return httpx.Response(200, content=sse(SPOKEN if speaking else ROUTED))

    return handler


def mock_client(calls, *, central=False):
    native = model_server(calls)

    def manager(request):
        payload = json.loads(request.content or b"{}")
        if request.url.path == "/v1/capabilities":
            return httpx.Response(
                200,
                json={
                    "version": 1,
                    "revision": 1,
                    "models": [
                        {"id": "fixture", "alias": "qwen3-4b-local", "name": "Fixture", "capability": "llm"}
                    ],
                    "services": {"llm": {"model_id": "fixture", "ready": True, "state": "Ready"}},
                },
            )
        assert payload["model"] == "qwen3-4b-local"
        if request.url.path == "/v1/llm/inspect":
            operation = payload["operation"]
            return native(
                httpx.Request(
                    "GET" if operation == "props" else "POST",
                    request.url.copy_with(path="/" + operation),
                    json=payload["payload"],
                )
            )
        assert request.url.path == "/v1/infer/llm"
        calls.append(payload)
        speaking = "CASE FACTS" in payload["messages"][0]["content"]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": SPOKEN if speaking else ROUTED}, "finish_reason": "stop"}
                ],
                "usage": USAGE,
            },
        )

    return httpx.AsyncClient(transport=httpx.MockTransport(manager if central else native))


async def platform_turn(document, calls):
    """The cloud path: this service dispatches both completions itself."""
    client = LLMClient(10)
    await client.client.aclose()
    client.client = mock_client(calls)
    context = conversation_context(document, "en", QUESTION)
    routing_max = 100
    params = {
        "base_url": CLOUD_URL,
        "model": "qwen3-4b-cloud",
        "key": "private-parity-key",
        "provider": "openai_compatible",
        "token_parameter": "max_tokens",
        "stream_usage": True,
        "max_tokens": routing_max,
        "messages": [
            {"role": "system", "content": context["system"]},
            {"role": "user", "content": QUESTION},
        ],
        "streaming": True,
    }
    params["messages"], budget = await platform_fit(client, params, SETTINGS, margin=128)
    context["budget"] = {"conversation": budget}
    try:
        return await run_conversation(
            ProviderRunner(client, params, SETTINGS), context, params["messages"], 100
        )
    finally:
        await client.close()


def local_route(practice_answer_mode="generated"):
    return {
        "profile_revision_id": str(uuid4()),
        "configuration_hash": "c" * 64,
        "llm": {
            "mode": "local",
            "execution": "caller",
            "provider": "local_llama_cpp",
            "model": "qwen3-4b-local",
            "connection_id": str(uuid4()),
            "connection_revision": 1,
            "model_options": {},
            "max_tokens": 100,
            "instruction_role": "system",
            "system_prompt": "You are a helpful assistant.",
            "local_port": PORT,
            "local_context_tokens": 8192,
        },
    }


@pytest.fixture
def human_test(monkeypatch):
    root = Path(__file__).resolve().parents[3]
    monkeypatch.syspath_prepend(str(root / "human-test/src"))
    monkeypatch.syspath_prepend(str(root / "local-models/client/src"))


async def laptop_turn(document, calls, practice_id):
    """The local path: the laptop executes both completions against its own server."""
    from local_model_client.llm import LocalModel
    from training_client.local_turn import answer

    model = LocalModel(
        PORT,
        "private-parity-key",
        "qwen3-4b-local",
        context_cap=8192,
        client=mock_client(calls, central=True),
    )
    practice = {"practice_id": practice_id, "practice_revision": 1, "document": document}
    emitted = []
    event = await answer(
        model,
        local_route(),
        practice,
        [{"role": "user", "content": QUESTION}],
        "en",
        lambda name, value: emitted.append((name, value)),
        diagnostic=True,
    )
    # The desktop shows a local answer exactly as it shows a streamed cloud answer.
    assert emitted == [("answer_delta", event["text"]), ("answer", event["text"])]
    return event


async def test_a_local_turn_and_a_cloud_turn_build_the_same_prompts_and_answer(human_test):
    document = expanded_document()
    assert {"complaint", "duration"} <= set(patient_context(document, "en", QUESTION)["answers"])
    cloud_calls: list = []
    local_calls: list = []
    cloud = await platform_turn(document, cloud_calls)
    practice_id = str(uuid4())
    local = await laptop_turn(document, local_calls, practice_id)

    assert len(cloud_calls) == len(local_calls) == 1
    assert local_calls[0]["messages"] == cloud_calls[0]["messages"]
    assert cloud["text"] == local["text"] == SPOKEN
    timings = {"context", "total_ms", "first_token_ms"}
    assert {k: v for k, v in local.items() if k not in timings} == {
        k: v for k, v in cloud.items() if k not in timings
    }
    assert local["answer_source"] == "patient_conversation" and local["topics"] == []
    assert local["provider_calls"] == 1 and local["usage"]["completion_tokens"] == 20
    assert local_calls[0]["max_tokens"] == cloud_calls[0]["max_tokens"] == 100
    assert local["context"]["conversation"]["method"] == "native_tokenizer"
    assert cloud["context"]["conversation"]["method"] == "utf8_upper_estimate"


def test_every_outcome_the_shared_pipeline_can_produce_is_an_acceptable_report(human_test):
    """The report schema must accept every event the pipeline really builds, not just the happy one.

    A guard-rejected turn spends both calls and still answers from the authored case; refusing
    that report would drop exactly the turns the fact guard acted on.
    """
    from training_client.local_turn import turn_event

    from pms_api.modules.local_turns import LocalTurnEvent

    document = expanded_document()
    practice = {"practice_id": str(uuid4()), "practice_revision": 1, "document": document}
    context = patient_context(document, "en", QUESTION)
    context["budget"] = {}
    routed = route(context, routing(ROUTED))
    _, source = voice_messages(context, routed, [])
    events = [
        patient_event(context, routed, routing(ROUTED), routing(SPOKEN), source),
        # The guard rejected an invented number after the spoken call ran: two calls, authored text.
        patient_event(context, routed, routing(ROUTED), routing("I take 500 mg daily."), source),
        # An objective topic answers after routing alone.
        {
            **frame(context, route(context, routing('{"kind":"topic","topics":["name"]}')), routing(ROUTED)),
            "text": "Alex",
            "answer_source": "scripted_case",
        },
    ]
    for reply in ('{"kind":"backchannel","topics":[]}', '{"kind":"command","topics":[]}', "not json"):
        decision = route(context, routing(reply))
        events.append(authored_event(context, decision, routing(reply)))
    sources = set()
    for event in events:
        event["language"] = "en"
        report = LocalTurnEvent.model_validate(turn_event(local_route(), practice, event))
        assert report.provider_calls == event["provider_calls"]
        sources.add(report.answer_source)
    assert sources == {
        "patient_voice",
        "scripted_case",
        "case_backchannel",
        "case_command_ack",
        "routing_invalid",
    }
    # A turn with no case selected reports a plain completion and no routing outcome.
    plain = {"text": SPOKEN, "finish_reason": "stop", "language": "en", "usage": USAGE, "total_ms": 5}
    assert LocalTurnEvent.model_validate(turn_event(local_route(), None, plain)).routing_status is None


async def test_the_record_of_a_local_turn_carries_no_prompt_or_answer(human_test):
    from training_client.local_turn import turn_event

    document = expanded_document()
    calls: list = []
    practice_id = str(uuid4())
    event = await laptop_turn(document, calls, practice_id)
    record = turn_event(
        local_route(), {"practice_id": practice_id, "practice_revision": 1, "document": document}, event
    )
    text = json.dumps(record)
    assert SPOKEN not in text and QUESTION not in text and ROUTED not in text
    for message in calls[0]["messages"]:
        for line in message["content"].splitlines():
            assert len(line) < 8 or line not in text
    assert record["practice_snapshot_hash"] and record["practice_id"] == practice_id
    assert (record["answer_source"], record["provider_calls"], record["topics"]) == (
        "patient_conversation",
        1,
        [],
    )
    assert record["prompt_tokens"] == 700 and record["completion_tokens"] == 20
