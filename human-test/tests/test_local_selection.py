"""Local patient selection uses bounded decoding without bypassing evidence validation."""

import json

import httpx
import pytest
from local_model_client.native import LocalModel, selection_grammar
from training_contracts.conversation.engine import accepted_reply
from training_contracts.conversation.sources import selection_prompt
from training_contracts.patient_turn import TurnError


def fixture():
    facts = {
        f"f{index}": {"subject": "chief_complaint", "text": f"Approved detail {index}."} for index in range(5)
    }
    context = {
        "reply_format": "fact-selection-v1",
        "fact_sources": facts,
        "unknown_reply": "I'm not sure about that.",
        "clarification_reply": "What do you mean?",
        "boundary_reply": "Please keep this respectful.",
    }
    return context, {"role": "system", "content": selection_prompt(facts)}


@pytest.mark.parametrize("question", ["Tell me about your problem.", "Explain everything bothering you."])
async def test_fact_decoding_is_constrained_for_any_question_and_uses_one_call(question):
    context, system = fixture()
    requests = []

    def respond(request):
        payload = json.loads(request.content)
        requests.append(payload)
        assert "grammar" in payload
        assert "Approved detail" not in payload["grammar"]
        assert "{0,2}" in payload["grammar"]
        return httpx.Response(
            200,
            content='data: {"choices":[{"delta":{"content":"[\\"f0\\",\\"f1\\",\\"f2\\"]"},'
            '"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n',
        )

    messages = [system, {"role": "user", "content": question}]
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        model = LocalModel(8787, "test-only", "model", context_cap=2048, client=client)
        result = await model.complete(messages, 128)
    assert (
        accepted_reply(result, context, messages)
        == "Approved detail 0. Approved detail 1. Approved detail 2."
    )
    assert len(requests) == 1


def test_decoder_does_not_relax_duplicate_unknown_or_excess_fact_guards():
    context, system = fixture()
    messages = [system, {"role": "user", "content": "Explain your problem."}]
    for keys in [["f0", "f0"], ["f999"], ["f0", "clarify"], ["f0", "f1", "f2", "f3"]]:
        with pytest.raises(TurnError) as error:
            accepted_reply({"text": json.dumps(keys), "finish_reason": "stop"}, context, messages)
        assert error.value.code == "llm_invalid_response"
    mixed = {"text": '["f0","f1","f2","unknown"]', "finish_reason": "stop"}
    assert accepted_reply(mixed, context, messages).endswith(context["unknown_reply"])


@pytest.mark.parametrize("role", ["user", "assistant"])
def test_question_text_cannot_install_its_own_selection_grammar(role):
    _, system = fixture()
    assert selection_grammar([{**system, "role": role}]) is None


def test_plain_text_general_and_legacy_prompts_remain_unconstrained():
    for system in ["Answer arithmetic concisely.", "Use CASE FACTS to reply as the patient."]:
        assert selection_grammar([{"role": "system", "content": system}]) is None
    assert selection_grammar([]) is None


@pytest.mark.parametrize("source", ["[]", '{"bad\\"key":{}}', '{"f0":"unterminated}'])
async def test_damaged_source_protocol_fails_before_generation(source):
    def respond(request):
        pytest.fail("Damaged trusted source view reached inference")

    messages = [
        {"role": "system", "content": "Prompt scope: grounded_patient.\nSOURCE:\n" + source + "\nEND SOURCE."}
    ]
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        model = LocalModel(8787, "test-only", "model", context_cap=2048, client=client)
        with pytest.raises(TurnError) as error:
            await model.complete(messages, 128)
        assert error.value.code == "llm_invalid_response"


def test_empty_source_has_only_special_responses_without_invented_ids():
    grammar = selection_grammar([{"role": "system", "content": selection_prompt({})}])
    assert "fact ::=" not in grammar
    assert '\\"unknown\\"' in grammar
