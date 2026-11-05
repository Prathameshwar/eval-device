"""A profile that publishes a local model is executed here, and PMS is never on the data path.

PMS still owns the case, the persona, the language and the model selection. What must not
happen is the prompt, the transcript or the answer reaching it, or a local turn being
submitted to its completions endpoint as if the platform could run or recover it.
"""

import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from local_model_client.llm import LocalModel
from test_flow import settings
from training_client import local_turn
from training_client.controller import Controller
from training_client.pms_client import ClientError
from training_contracts.patient_turn import TurnError

QUESTION = "What brings you in today, and how long has it been going on?"
ROUTED = '{"kind":"topic","topics":["complaint","duration"]}'
SPOKEN = "I have had a dry cough for about three weeks, doctor."
PORT = 8790
CASES = Path(__file__).parents[2] / "platform/api/migrations/versions/0014_patient_case_templates.json"


def document():
    rows = json.loads(CASES.read_text(encoding="utf-8"))
    return next(row["document"] for row in rows if row["code"] == "alex_dry_cough")


def route(**llm):
    return {
        "profile_id": str(uuid4()),
        "profile_revision_id": str(uuid4()),
        "configuration_hash": "c" * 64,
        "mode": "local",
        "cloud_allowed": True,
        "llm_enabled": True,
        "audio": {"mode": "local", "model": "large-v3", "max_seconds": 30},
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
            "local_context_tokens": 4096,
            **llm,
        },
    }


def selection():
    return {"id": str(uuid4()), "revision": 3, "language": "en", "document": document()}


def model_server(calls, *, models=("qwen3-4b-local",)):
    def handler(request):
        assert request.url.host == "127.0.0.1" and request.url.port == PORT
        assert request.headers["authorization"] == "Bearer laptop-model-key"
        path = request.url.path
        data = json.loads(request.content) if request.content else {}
        if path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": name} for name in models]})
        if path == "/props":
            return httpx.Response(200, json={"default_generation_settings": {"n_ctx": 4096}})
        if path == "/apply-template":
            return httpx.Response(200, json={"prompt": "".join(m["content"] for m in data["messages"])})
        if path == "/tokenize":
            return httpx.Response(200, json={"tokens": [1] * (len(data["content"]) // 3)})
        assert path == "/v1/chat/completions", path
        calls.append(data)
        text = SPOKEN if "CASE FACTS" in data["messages"][0]["content"] else ROUTED
        return httpx.Response(
            200,
            content="data: "
            + json.dumps({"choices": [{"delta": {"content": text}, "finish_reason": "stop"}]})
            + '\n\ndata: {"choices":[],"usage":{"prompt_tokens":700,"completion_tokens":20}}\n\n'
            + "data: [DONE]\n\n",
        )

    return gateway(handler)


def local_settings(**kw):
    return settings(local_models_key="laptop-model-key", streaming=True, **kw)


def conversation_transport(c, handler):
    """Mock PMS context admission, while retaining real client validation and prompting."""
    from datetime import UTC, datetime, timedelta

    from training_contracts import fingerprint
    from training_contracts.conversation.context import ConversationContext
    from training_contracts.conversation.prompt import COMPILER_VERSION, conversation_context
    from training_contracts.languages import get_pack

    def dispatch(request):
        if request.url.path.endswith("/conversations"):
            data = json.loads(request.content)
            pack = get_pack(data["language"])
            now = datetime.now(UTC)
            context = ConversationContext(
                conversation_id=uuid4(),
                organization_id=c.settings.organization_id,
                owner_id=uuid4(),
                practice_id=data["practice_id"],
                practice_revision=data["practice_revision"],
                case_snapshot_hash=fingerprint(c.pms.practice_document),
                language=pack.language,
                language_pack_version=pack.version,
                language_pack_hash=pack.content_hash,
                localization_revision=1,
                policy_version="patient-conversation-v1",
                compiler_version=COMPILER_VERSION,
                profile_revision_id=data.get("profile_revision_id"),
                configuration_hash=c.pms.model_route["configuration_hash"],
                connection_id=data["connection_id"],
                connection_revision=1,
                execution="caller",
                speech_locale=pack.speech_locales[0],
                created_at=now,
                expires_at=now + timedelta(hours=24),
            )
            return httpx.Response(
                200,
                json={
                    "context": context.model_dump(mode="json"),
                    "status": "active",
                    "sequence": 0,
                    "snapshot": conversation_context(c.pms.practice_document, pack.language, "Hello"),
                },
            )
        if request.url.path.endswith("/close"):
            return httpx.Response(200, json={"status": "closed"})
        return handler(request)

    return httpx.MockTransport(dispatch)


def controller(monkeypatch, pms_handler, model_handler, **kw):
    """A controller whose PMS and local model are both stubs, so nothing leaves the test."""
    c = Controller(local_settings(**kw), lambda *args: None)
    c.pms.http = httpx.AsyncClient(
        transport=conversation_transport(c, pms_handler), base_url="http://pms.invalid"
    )
    c._local_http = httpx.AsyncClient(transport=httpx.MockTransport(gateway(model_handler)))
    return c


def test_only_a_published_local_route_is_executed_here():
    assert local_turn.runs_locally(route())
    for llm in ({"mode": "cloud"}, {"execution": "platform"}):
        assert not local_turn.runs_locally(route(**llm))
    assert not local_turn.runs_locally({}) and not local_turn.runs_locally(None)


def test_the_local_model_key_never_comes_from_pms():
    value = route()
    # PMS publishes what to run and where, never the credential for it.
    assert "api_key" not in json.dumps(value) and "key" not in value["llm"]
    with pytest.raises(ClientError) as missing:
        local_turn.local_model(value, settings())
    assert missing.value.code == "llm_local_key_missing"
    model = local_turn.local_model(value, local_settings())
    assert (model.root, model.model, model.local_context_cap) == (
        f"http://127.0.0.1:{PORT}",
        "qwen3-4b-local",
        4096,
    )
    assert model.key == "laptop-model-key"


async def test_local_readiness_checks_this_laptop_and_not_pms():
    for models, code in ((("some-other-model",), "llm_model_mismatch"), ((), "llm_unavailable")):
        client = httpx.AsyncClient(transport=httpx.MockTransport(model_server([], models=models)))
        model = LocalModel(PORT, "laptop-model-key", "qwen3-4b-local", context_cap=4096, client=client)
        with pytest.raises(ClientError) as error:
            await local_turn.health(model)
        assert error.value.code == code
        assert "Manage Local Models" in str(error.value) or "different model than PMS has published" in str(
            error.value
        )
        await client.aclose()

    def refused(request):
        raise httpx.ConnectError("no server")

    client = httpx.AsyncClient(transport=httpx.MockTransport(refused))
    model = LocalModel(PORT, "laptop-model-key", "qwen3-4b-local", context_cap=4096, client=client)
    with pytest.raises(ClientError) as error:
        await local_turn.health(model)
    assert error.value.code == "llm_unavailable" and "Manage Local Models" in str(error.value)
    await client.aclose()


async def test_a_local_turn_never_reaches_pms_completions(monkeypatch):
    model_calls: list = []
    pms_calls: list = []

    def pms(request):
        pms_calls.append((request.method, request.url.path, json.loads(request.content or b"{}")))
        assert not request.url.path.endswith("/completions"), "A local turn was submitted to PMS"
        return httpx.Response(200, json={"id": str(uuid4()), "turn_key": pms_calls[-1][2]["turn_key"]})

    c = controller(monkeypatch, pms, model_server(model_calls))
    events: list = []
    c.emit = lambda kind, value: events.append((kind, value))
    try:
        c.pms.use_models(route())
        c.use_selection(selection())
        assert c.runs_locally()
        result = await c.text_turn(QUESTION)
    finally:
        await c.close()
    assert result["answer"] == SPOKEN and len(model_calls) == 1
    # Nothing was submitted, so there is no PMS request key to check or recover.
    assert c.pms.last_request is None and result["metrics"]["request_key"] is None
    assert [(method, path) for method, path, _ in pms_calls] == [
        ("POST", f"/api/v1/organizations/{c.settings.organization_id}/llm/local-turns")
    ]
    record = pms_calls[0][2]
    assert SPOKEN not in json.dumps(record) and QUESTION not in json.dumps(record)
    assert record["answer_source"] == "patient_conversation" and record["provider_calls"] == 1
    assert record["topics"] == [] and record["language"] == "en"
    assert record["prompt_tokens"] == 700 and record["completion_tokens"] == 20
    assert record["profile_revision_id"] == c.pms.model_route["profile_revision_id"]
    assert record["practice_id"] == c.pms.practice["practice_id"]
    assert [kind for kind, _ in events if kind in ("answer", "speak", "metrics")] == [
        "answer",
        "answer",
        "speak",
        "metrics",
    ]


async def test_background_source_selection_reaches_spoken_result_in_one_local_call(monkeypatch):
    from training_contracts.conversation.background import restore_starter_background
    from training_contracts.localized_cases import review_localization

    calls, records = [], []
    expected = "Yesterday I ate rice, dal and vegetables."

    def model(request):
        if request.url.path != "/v1/chat/completions":
            return model_server(calls)(request)
        payload = json.loads(request.content)
        calls.append(payload)
        system = payload["messages"][0]["content"]
        assert "dry cough" not in system  # A clear meal question does not prefill clinical facts.
        sources = json.loads(system.split("\nSOURCE:\n", 1)[1].split("\nEND SOURCE.", 1)[0])
        key = next(key for key, fact in sources.items() if fact["text"] == expected)
        content = json.dumps([key])
        return httpx.Response(
            200,
            content="data: "
            + json.dumps({"choices": [{"delta": {"content": content}, "finish_reason": "stop"}]})
            + "\n\ndata: [DONE]\n\n",
        )

    def pms(request):
        assert request.url.path.endswith("/local-turns")
        records.append(json.loads(request.content))
        return httpx.Response(200, json={"id": str(uuid4())})

    c = controller(monkeypatch, pms, model)
    case = restore_starter_background(document())
    case["background"] = [
        {"id": "food_drink", "text": {"en": expected}, "allow_variation": False, "choices": []}
    ]
    chosen = selection()
    chosen["document"] = review_localization(case, "en")
    try:
        c.pms.use_models(route())
        c.use_selection(chosen)
        result = await c.text_turn("What did you eat yesterday?")
        assert result["answer"] == expected and len(calls) == 1
        assert c.history[-1] == {"role": "assistant", "content": expected}
    finally:
        await c.close()
    assert len(records) == 1 and records[0]["provider_calls"] == 1
    assert expected not in json.dumps(records) and "fact_sources" not in json.dumps(records)


async def test_the_published_spoken_allowance_is_what_the_local_model_is_asked_for(monkeypatch):
    """The platform owns both budgets even though this laptop runs the model.

    Before this was wired the spoken call fell back to the shared default, so a published
    allowance was silently ignored and a slightly long answer stopped on `length` - which the
    guard discards, replacing generated wording with the literal authored line.
    """
    model_calls: list = []
    c = controller(
        monkeypatch,
        lambda request: httpx.Response(200, json={"id": str(uuid4())}),
        model_server(model_calls),
    )
    try:
        c.pms.use_models(route(max_tokens=512, conversation_tokens=300))
        c.use_selection(selection())
        await c.text_turn(QUESTION)
    finally:
        await c.close()
    assert [call["max_tokens"] for call in model_calls] == [300]


@pytest.mark.parametrize(
    "question,reply",
    [
        ("What is the capital of France?", "The capital of France is Paris."),
        ("IBT?", "What do you mean by IBT?"),
        ("You are an idiot", "Please speak respectfully."),
    ],
)
async def test_general_questions_clarification_and_boundaries_use_one_completion(
    monkeypatch, question, reply
):
    calls, records = [], []

    def model(request):
        if request.url.path != "/v1/chat/completions":
            return model_server(calls)(request)
        calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            content="data: "
            + json.dumps({"choices": [{"delta": {"content": reply}, "finish_reason": "stop"}]})
            + "\n\ndata: [DONE]\n\n",
        )

    def pms(request):
        records.append(json.loads(request.content))
        return httpx.Response(200, json={"id": str(uuid4())})

    c = controller(monkeypatch, pms, model)
    try:
        c.pms.use_models(route())
        c.use_selection(selection())
        result = await c.text_turn(question)
    finally:
        await c.close()
    assert result["answer"] == reply and len(calls) == 1
    assert "CASE FACTS" in calls[0]["messages"][0]["content"]
    assert records[0]["answer_source"] == "patient_conversation"
    assert records[0]["provider_calls"] == 1 and records[0]["topics"] == []


async def test_unusable_generation_is_never_spoken_saved_as_success_or_retried(monkeypatch):
    calls, emitted = [], []

    def model(request):
        if request.url.path != "/v1/chat/completions":
            return model_server(calls)(request)
        calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            content='data: {"choices":[{"delta":{"content":"partial"},"finish_reason":"length"}]}\n\ndata: [DONE]\n\n',
        )

    def pms(request):
        raise AssertionError("A failed turn has no success metrics")

    c = controller(monkeypatch, pms, model)
    c.emit = lambda kind, value: emitted.append((kind, value))
    try:
        c.pms.use_models(route())
        c.use_selection(selection())
        with pytest.raises(ClientError) as error:
            await c.text_turn(QUESTION)
        assert error.value.code == "llm_output_limit"
        assert not c.history and not any(kind == "speak" for kind, value in emitted)
        assert len(calls) == 1
    finally:
        await c.close()


async def test_a_failed_record_never_costs_the_learner_the_answer(monkeypatch):
    def pms(request):
        return httpx.Response(503, json={"error": {"code": "database_unavailable"}})

    c = controller(monkeypatch, pms, model_server([]))
    states: list = []
    c.emit = lambda kind, value: states.append(value) if kind == "state" else None
    try:
        c.pms.use_models(route())
        c.use_selection(selection())
        result = await c.text_turn(QUESTION)
    finally:
        await c.close()
    assert result["answer"] == SPOKEN
    assert "PMS did not record this local turn's metrics" in states[-1]


async def test_a_local_profile_is_ready_when_this_laptop_is_ready(monkeypatch):
    def pms(request):
        pytest.fail("PMS was asked about a model it cannot reach: " + request.url.path)

    c = controller(monkeypatch, pms, model_server([]))
    ready: list = []
    c.emit = lambda kind, value: ready.append((kind, value))
    try:
        c.pms.use_models(route())
        monkeypatch.setattr("training_client.audio_client.preflight", lambda s, **kwargs: _ok())
        await c.preflight()
    finally:
        await c.close()
    assert ("ready", "ASR connected | PMS ready | LLM running on this laptop") in ready


async def _ok():
    return None


async def test_a_plain_local_turn_without_a_case_reports_one_call(monkeypatch):
    model_calls: list = []
    records: list = []

    def pms(request):
        records.append(json.loads(request.content))
        return httpx.Response(200, json={"id": str(uuid4()), "turn_key": records[-1]["turn_key"]})

    def model(request):
        if request.url.path == "/v1/chat/completions":
            model_calls.append(json.loads(request.content))
            return httpx.Response(
                200,
                content="data: "
                + json.dumps({"choices": [{"delta": {"content": "Hello."}, "finish_reason": "stop"}]})
                + "\n\ndata: [DONE]\n\n",
            )
        return model_server(model_calls)(request)

    c = controller(monkeypatch, pms, model)
    try:
        c.pms.use_models(route())
        result = await c.text_turn("Hello")
    finally:
        await c.close()
    assert result["answer"] == "Hello." and len(model_calls) == 1
    # No case is selected, so the whole connection allowance is available for the one call.
    assert model_calls[0]["max_tokens"] == 100
    assert model_calls[0]["messages"][0]["content"].endswith("Reply in English.")
    assert records[0]["answer_source"] == "plain_completion" and records[0]["provider_calls"] == 1
    assert records[0]["practice_id"] is None and records[0]["topics"] == []


async def test_a_local_model_failure_is_reported_in_this_app_s_words():
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(401, json={"error": "nope"}))
    )
    model = LocalModel(PORT, "laptop-model-key", "qwen3-4b-local", context_cap=4096, client=client)
    with pytest.raises(TurnError) as error:
        await model.complete([{"role": "user", "content": "hi"}], 50)
    assert error.value.code == "llm_credentials_rejected"
    with pytest.raises(ClientError) as raised:
        await local_turn.answer(
            model, route(), None, [{"role": "user", "content": "hi"}], "en", lambda *a: None
        )
    assert raised.value.code == "llm_credentials_rejected"
    assert "Reconnect Human-test to Manage Local Models" in str(raised.value)
    await client.aclose()


async def test_cloud_local_cloud_local_switch_keeps_local_inference_on_laptop(monkeypatch):
    model_calls, pms_calls = [], []
    selected_local = route()
    selected_cloud = route(mode="cloud", execution="platform", provider="azure_openai")
    selected_cloud["mode"] = selected_cloud["audio"]["mode"] = "cloud"
    phase = ""

    def pms(request):
        data = json.loads(request.content or b"{}")
        pms_calls.append((phase, request.url.path, data))
        assert request.url.host == "hosted-pms.invalid"
        assert "laptop-model-key" not in str(request.headers) + request.content.decode()
        if phase == "local":
            assert request.url.path.endswith("/llm/local-turns")
            assert QUESTION not in request.content.decode() and SPOKEN not in request.content.decode()
            return httpx.Response(200, json={"id": str(uuid4()), "turn_key": data["turn_key"]})
        assert request.url.path.endswith("/completions")
        return httpx.Response(
            200,
            json={
                "request_key": data["request_key"],
                "status": "succeeded",
                "text": "Cloud answer",
                "finish_reason": "stop",
                "usage": None,
            },
        )

    c = controller(monkeypatch, pms, model_server(model_calls))
    await c.pms.http.aclose()
    c.pms.http = httpx.AsyncClient(
        base_url="https://hosted-pms.invalid", transport=conversation_transport(c, pms)
    )
    c.settings.streaming = False
    c.use_selection(selection())
    try:
        for phase in ("cloud", "local", "cloud", "local"):
            c.use_models(selected_local if phase == "local" else selected_cloud)
            assert c.runs_locally() == (phase == "local") and not c.history
            result = await c.text_turn(QUESTION)
            assert result["answer"] == (SPOKEN if phase == "local" else "Cloud answer")
            await c.metrics_reporter.queue.join()  # Delivery is deliberately asynchronous.
        assert len(model_calls) == 2
        assert [kind for kind, _, _ in pms_calls] == ["cloud", "local", "cloud", "local"]
        assert c.settings.local_models_key.get_secret_value() == "laptop-model-key"
    finally:
        await c.close()


def gateway(handler):
    """Translate the legacy fictional native fixture to the central client protocol."""

    def dispatch(request):
        path = request.url.path
        payload = json.loads(request.content or b"{}")
        if path == "/v1/capabilities":
            raw = handler(
                httpx.Request("GET", str(request.url.copy_with(path="/v1/models")), headers=request.headers)
            )
            if raw.status_code != 200:
                return raw
            names = [entry["id"] for entry in raw.json()["data"]]
            models = [
                {"id": name.removesuffix("-local"), "alias": name, "capability": "llm", "name": name}
                for name in names
            ]
            return httpx.Response(
                200,
                json={
                    "version": 1,
                    "revision": 1,
                    "models": models,
                    "services": {
                        "llm": {
                            "model_id": models[0]["id"] if models else "missing",
                            "ready": bool(models),
                            "state": "Ready" if models else "Stopped",
                        }
                    },
                },
            )
        if path == "/v1/llm/inspect":
            assert payload["model"] == "qwen3-4b-local"
            method, native_path = {
                "props": ("GET", "/props"),
                "apply-template": ("POST", "/apply-template"),
                "tokenize": ("POST", "/tokenize"),
            }[payload["operation"]]
            return handler(
                httpx.Request(
                    method,
                    str(request.url.copy_with(path=native_path)),
                    headers=request.headers,
                    json=payload["payload"],
                )
            )
        if path == "/v1/infer/llm":
            raw = handler(
                httpx.Request(
                    "POST",
                    str(request.url.copy_with(path="/v1/chat/completions")),
                    headers=request.headers,
                    json=payload,
                )
            )
            if raw.status_code != 200:
                return raw
            if raw.headers.get("content-type", "").startswith("application/json"):
                return raw
            text, reason, counts = "", None, None
            for line in raw.text.splitlines():
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                event = json.loads(line[6:])
                counts = event.get("usage", counts)
                for choice in event.get("choices", []):
                    text += choice.get("delta", {}).get("content", "")
                    reason = choice.get("finish_reason", reason)
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": text}, "finish_reason": reason}], "usage": counts},
            )
        return handler(request)

    return dispatch


@pytest.mark.parametrize(
    "llm",
    [
        {"local_context_tokens": None},
        {"local_context_tokens": 128},
        {"model": ""},
        {"max_tokens": 0},
        {"instruction_role": "assistant"},
        {"system_prompt": None},
    ],
)
def test_an_unusable_local_route_is_refused_before_any_turn(llm):
    with pytest.raises(ClientError) as error:
        local_turn.local_model(route(**llm), local_settings())
    assert error.value.code == "llm_local_route_invalid"


def test_published_engine_port_cannot_redirect_central_client():
    model = local_turn.local_model(route(local_port=11434), local_settings())
    assert model.root == "http://127.0.0.1:8790"
