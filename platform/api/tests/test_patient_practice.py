import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
import pytest
from alembic import command
from sqlalchemy.engine import make_url
from test_llm_api import llm as llm
from test_scenario_categories import empty_database_target as empty_database_target
from training_contracts.scenarios import PublishedScenarioV2

from pms_api.cli import migration_config
from pms_api.core.common import AppError, canonical, token_hash
from pms_api.core.config import Settings
from pms_api.database.initialization import initialize_database
from pms_api.integrations.llm import LLMClient
from pms_api.integrations.llm.budget import fit_patient_prompt
from pms_api.modules.llm_schemas import Completion
from pms_api.modules.patient_context import (
    REPAIR_RULE,
    REPLY_FOR,
    ROUTING_TOKENS,
    VOICE_TOKENS,
    authored_event,
    bounded_history,
    deflection_messages,
    literal_answer,
    patient_context,
    patient_event,
    repair_budget,
    route,
    turn_budget,
    voice_messages,
)


def setup(p, token, org, *, language="en"):
    user_id = p.sql(
        "SELECT user_id FROM device_platform.organization_memberships "
        "WHERE organization_id=%s AND role='org_admin' AND invitation_status='accepted' LIMIT 1",
        (org,),
    )[0][0]
    p.grant_capability(token, org, user_id, "org.clinical.author")
    clinical = f"/organizations/{org}/clinical-catalog"
    specialty = p.call(
        "POST", clinical + "/import/specialties/00000000-0000-4000-8000-000000000301", token, expected=200
    )
    patient = p.call(
        "POST", clinical + "/import/patients/00000000-0000-4000-8000-000000000401", token, expected=200
    )
    for kind, row in (("specialties", specialty), ("patients", patient)):
        p.call(
            "POST", f"{clinical}/{kind}/{row['id']}/restore", token, json={"expected_version": row["version"]}
        )
    imported = p.call(
        "POST", clinical + "/import/cases/00000000-0000-4000-8000-000000000501", token, expected=200
    )
    p.call(
        "POST",
        f"{clinical}/cases/{imported['id']}/restore",
        token,
        json={"expected_version": imported["version"]},
    )
    base = f"/organizations/{org}/patient-practice"
    catalog = p.call("GET", base + "/catalog", token)
    case = catalog["cases"][0]
    detail = p.call("GET", base + "/cases/" + case["id"], token)
    body = {
        "expected_revision": 0,
        "template_id": case["id"],
        "template_revision": case["revision"],
        "category_id": case["category_id"],
        "patient_identity_id": case["patient_identity_id"],
        "language": language,
        "vitals": detail["document"]["vitals"],
    }
    saved = p.call("PUT", base + "/selection", token, json=body)["selection"]
    return base, body, saved


def test_case_catalog_counts_security_save_and_concurrency(platform):
    p = platform
    token, staff_user = p.user("practice-staff")
    org = p.organization(token)["id"]
    base, body, saved = setup(p, token, org)
    catalog = p.call("GET", base + "/catalog", token)
    assert len(catalog["patients"]) == 1 and catalog["patients"][0]["name"] == "Alex"
    assert len(catalog["cases"]) == 1
    assert sum(c["category_id"] == cat["id"] for c in catalog["cases"] for cat in catalog["categories"]) == 1
    for document, template_revision in p.sql(
        "SELECT document,revision FROM device_platform.patient_case_templates"
    ):
        case = PublishedScenarioV2.model_validate(document)
        assert case.patient.name == "Alex"
        # 0014 expanded every seeded case in place: clinical topics plus ten everyday ones.
        assert template_revision == 3 and len(case.dialogue.topics) == 32
        assert {"diet_meals", "sleep", "bowel_bladder"} <= {t.id for t in case.dialogue.topics}
        assert case.dialogue.backchannel and case.dialogue.command_ack and case.dialogue.boundary
        assert "I am sorry, doctor" in case.dialogue.clarification.en
    outsider, _ = p.admin("practice-outsider")
    for path in ("/catalog", "/selection", "/cases/" + body["template_id"]):
        p.call("GET", base + path, outsider, expected=404)
        p.call("GET", base + path, expected=401)
    other_org = p.organization(token, "Other")["id"]
    p.grant_capability(token, other_org, staff_user["id"], "org.clinical.author")
    assert p.call("GET", f"/organizations/{other_org}/patient-practice/selection", token)["selection"] is None
    assert p.call("GET", base + "/selection", token)["selection"]["id"] == saved["id"]
    p.call("PUT", base + "/selection", token, expected=409, json=body)
    p.call(
        "PUT",
        base + "/selection",
        token,
        expected=422,
        json={**body, "expected_revision": 1, "category_id": str(uuid4())},
    )
    changed = {**body, "expected_revision": 1, "vitals": {**body["vitals"], "temperature_c": 38.2}}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda _: p.client.put(
                    "/api/v1" + base + "/selection", headers=p.headers(token), json=changed
                ),
                range(2),
            )
        )
    assert sorted(r.status_code for r in responses) == [200, 409]
    current = p.call("GET", base + "/selection", token)["selection"]
    assert current["revision"] == 2 and current["document"]["vitals"]["temperature_c"] == 38.2
    assert p.sql(
        "SELECT count(*) FROM device_platform.activity_events WHERE event_type='patient.practice.saved'"
    ) == [(2,)]
    p.call(
        "PUT",
        base + "/selection",
        token,
        expected=422,
        json={
            **changed,
            "expected_revision": 2,
            "vitals": {**body["vitals"], "systolic_mmhg": 70.0, "diastolic_mmhg": 100.0},
        },
    )
    p.sql(
        "UPDATE device_platform.organization_case_templates SET is_active=false,revision=revision+1 WHERE id=%s",
        (body["template_id"],),
    )
    p.call("PUT", base + "/selection", token, expected=409, json={**changed, "expected_revision": 2})


def test_patient_setup_rejects_unavailable_profile_language_without_mutation(platform):
    p = platform
    token, _ = p.user("practice-language-owner")
    org = p.organization(token)["id"]
    base, body, saved = setup(p, token, org)
    profile_path = f"/organizations/{org}/clinical-catalog/patients/{body['patient_identity_id']}"
    profile = p.call("GET", profile_path, token)
    fields = (
        "code",
        "name",
        "names",
        "age_years",
        "sex",
        "occupations",
        "height_cm",
        "weight_kg",
        "preferred_language",
        "languages",
        "backgrounds",
        "is_active",
    )
    form = {key: profile[key] for key in fields}
    form["languages"] = ["hi"]
    form["preferred_language"] = "hi"
    form["names"] = {"en": profile["names"]["en"], "hi": profile["names"]["hi"]}
    for key in ("occupations", "backgrounds"):
        form[key] = {"hi": profile[key]["hi"]}
    p.call("PATCH", profile_path, token, json={"expected_version": profile["version"], "data": form})

    rejected = p.call(
        "PUT",
        base + "/selection",
        token,
        expected=422,
        json={**body, "expected_revision": saved["revision"], "language": "en"},
    )
    assert rejected["error"]["code"] == "patient_language_unavailable", rejected
    assert p.call("GET", base + "/selection", token)["selection"]["revision"] == saved["revision"]
    assert p.sql(
        "SELECT count(*) FROM device_platform.activity_events WHERE event_type='patient.practice.saved'"
    ) == [(1,)]


def test_case_role_scope_and_database_guards(platform):
    p = platform
    token, _ = p.user("scope-owner")
    org = p.organization(token)["id"]
    base, body, saved = setup(p, token, org)
    staff, staff_user = p.user("limited-staff")
    invite = p.call(
        "POST",
        f"/organizations/{org}/invitations",
        token,
        expected=201,
        json={"email": "limited-staff@example.com", "role": "org_user"},
    )
    p.call("POST", "/invitations/accept", staff, json={"token": invite["invitation_token"]})
    p.call("GET", base + "/selection", staff, expected=403)
    p.call(
        "PATCH",
        f"/organizations/{org}/members/{invite['membership']['id']}",
        token,
        json={"role": "org_admin"},
    )
    p.grant_capability(token, org, staff_user["id"], "org.clinical.author")
    assert p.call("GET", base + "/selection", staff)["selection"] is None
    dept = p.call("POST", f"/organizations/{org}/departments", token, expected=201, json={"name": "Ward"})[
        "id"
    ]
    p.call(
        "PATCH",
        f"/organizations/{org}/members/{invite['membership']['id']}",
        token,
        json={"role": "org_user", "department_id": dept},
    )
    p.call("GET", base + "/catalog", staff, expected=403)
    p.call("PUT", base + "/selection", staff, expected=403, json=body)
    for clause in (
        "revision=revision",
        "user_id=gen_random_uuid(),revision=revision+1",
        "document='{}',revision=revision+1",
    ):
        with pytest.raises(psycopg.errors.CheckViolation):
            p.sql(
                "UPDATE device_platform.patient_practice_selections SET " + clause + " WHERE id=%s",
                (saved["id"],),
            )
    with pytest.raises(psycopg.errors.CheckViolation):
        p.sql(
            "UPDATE device_platform.organization_case_templates SET document='{}',revision=revision+1 WHERE id=%s",
            (body["template_id"],),
        )
    roles = [
        make_url(v.get_secret_value()).username
        for v in (p.settings.database_url, p.settings.worker_database_url, p.settings.retention_database_url)
    ]
    for table, writes in (
        ("patient_case_templates", False),
        ("patient_practice_selections", True),
        ("organization_case_templates", True),
    ):
        for role in roles:
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                assert p.sql(
                    "SELECT has_table_privilege(%s,%s,%s)", (role, "device_platform." + table, privilege)
                )[0][0] == (
                    role == roles[0]
                    and (privilege == "SELECT" or writes and privilege in {"INSERT", "UPDATE"})
                )


def test_case_upgrade_preserves_identity_and_seeds_once(empty_database_target):
    settings, dsn, _ = empty_database_target
    initialize_database(settings, lambda: command.upgrade(migration_config(), "0012_patient_identities"))
    with psycopg.connect(dsn) as c:
        before = c.execute(
            "SELECT id,code,name,age_years,sex,height_cm,weight_kg,created_at FROM device_platform.patient_identities p"
        ).fetchall()
    for _ in range(2):
        initialize_database(settings, lambda: command.upgrade(migration_config(), "head"))
    with psycopg.connect(dsn) as c:
        assert (
            c.execute(
                "SELECT id,code,name,age_years,sex,height_cm,weight_kg,created_at FROM device_platform.patient_identities p"
            ).fetchall()
            == before
        )
        assert c.execute(
            "SELECT count(*),count(DISTINCT patient_identity_id) FROM device_platform.patient_case_templates"
        ).fetchone() == (9, 1)
        assert c.execute(
            "SELECT count(*) FROM device_platform.activity_events WHERE event_type='platform.patient_case.seeded'"
        ).fetchone() == (9,)


def seeded_documents(migration):
    return json.loads(
        (
            Path(__file__).parents[1] / f"migrations/versions/{migration}_patient_case_templates.json"
        ).read_text(encoding="utf-8")
    )


def fixture_document():
    return seeded_documents("0013")[0]["document"]


def expanded_document():
    """The dry-cough case after 0014: everyday topics plus authored non-clinical replies."""
    return next(r["document"] for r in seeded_documents("0014") if r["code"] == "alex_dry_cough")


def routing(text, **extra):
    return {"text": text, "finish_reason": "stop", **extra}


def test_patient_projection_and_fail_closed_routing():
    doc = fixture_document()
    doc["instructor"]["notes"] = "SECRET-INSTRUCTOR"
    next(t for t in doc["dialogue"]["topics"] if t["id"] == "temperature")["disclosure"] = "never"
    context = patient_context(doc, "auto", "आपका नाम क्या है?")
    context["budget"] = {}
    assert "SECRET-INSTRUCTOR" not in context["system"] and "temperature|" not in context["system"]
    # A concealed topic cannot be routed even when the model names it.
    assert route(context, routing('{"kind":"topic","topics":["temperature"]}'))["status"] == "invalid"
    decision = route(context, routing('{"kind":"topic","topics":["name"]}'))
    assert decision == {"kind": "topic", "topics": ["name"], "status": "matched"}
    assert literal_answer(context, decision) == "मेरा नाम Alex है।"
    for value in (
        "I am a doctor",
        '{"topics":["name"]}',
        '{"kind":"topic","topics":["name","name"]}',
        '{"kind":"nonsense","topics":[]}',
        '{"kind":"topic","topics":[],"extra":"x"}',
    ):
        assert route(context, routing(value))["status"] == "invalid", value
    invalid = authored_event(context, route(context, routing("junk")), routing("junk", total_ms=4))
    assert invalid["answer_source"] == "routing_invalid" and invalid["text"] == context["clarification"]


def test_everyday_kinds_answer_in_character_without_a_second_call():
    doc = expanded_document()
    context = patient_context(doc, "en", "hmm")
    context["budget"] = {}
    for kind, expected in (
        ("backchannel", "Yes, doctor, I am listening."),
        ("command", "I will try to do that, doctor."),
        ("boundary", "I would rather not answer that, doctor."),
    ):
        decision = route(context, routing(json.dumps({"kind": kind, "topics": []})))
        assert decision["topics"] == [] and decision["status"] == kind
        event = authored_event(context, decision, routing("x", total_ms=7))
        assert expected in event["text"] and event["answer_source"] == "case_" + REPLY_FOR[kind]
    # An unanticipated question still degrades to the in-character clarification line.
    unknown = authored_event(context, route(context, routing('{"kind":"unknown","topics":[]}')), routing("x"))
    assert unknown["answer_source"] == "case_clarification"
    assert unknown["text"] == "Sorry, doctor, I'm not sure. Please ask about my symptoms or medical history."


@pytest.mark.parametrize("language", ["en", "hi"])
def test_custom_clarifications_are_not_rewritten_or_truncated(language):
    doc = expanded_document()
    # Even a stock prefix with additional authored wording is a custom reply.
    suffix = " Please ask a different question." if language == "en" else " कृपया कोई और सवाल पूछिए।"
    doc["dialogue"]["clarification"][language] += suffix
    expected = doc["dialogue"]["clarification"][language]
    context = patient_context(doc, language, "?")
    context["budget"] = {}
    event = authored_event(context, route(context, routing("invalid")), routing("invalid"))
    assert event["text"] == expected and event["answer_source"] == "routing_invalid"


def test_everyday_topics_are_routable_and_carry_authored_background():
    doc = expanded_document()
    context = patient_context(doc, "en", "what did you eat yesterday?")
    context["budget"] = {}
    for topic in ("diet_meals", "sleep", "bowel_bladder", "mood_stress", "vaccination"):
        assert topic in context["answers"], topic
        assert topic + "|" in context["system"]
    decision = route(context, routing('{"kind":"topic","topics":["medications"]}'))
    messages, source = voice_messages(context, decision, [{"role": "user", "content": "any tablets?"}])
    system = messages[0]["content"]
    # The routed section's authored history reaches the spoken prompt; instructor content never does.
    assert "cough syrup" in system and "cough syrup" in source
    # Volunteered identity only: age is on_question, so it waits for its own topic to be routed.
    assert "name Alex" in system and "age in years" not in system
    assert doc["instructor"]["notes"] not in system and doc["instructor"]["objectives"][0] not in system
    assert messages[-1] == {"role": "user", "content": "any tablets?"}
    # An unrelated routed topic pulls no history section.
    _, narrow = voice_messages(context, route(context, routing('{"kind":"topic","topics":["sleep"]}')), [])
    assert "cough syrup" not in narrow


def test_spoken_answer_guard_rejects_invented_numbers_and_truncation():
    doc = expanded_document()
    context = patient_context(doc, "en", "what are your medicines?")
    context["budget"] = {}
    decision = route(context, routing('{"kind":"topic","topics":["medications"]}'))
    _, source = voice_messages(context, decision, [])
    literal = literal_answer(context, decision)
    kept = patient_event(context, decision, routing("r"), routing("I took some cough syrup."), source)
    assert kept["text"] == "I took some cough syrup." and kept["answer_source"] == "patient_voice"
    for bad in ("I take 500 mg twice a day.", "x" * 901, "   "):
        fallback = patient_event(context, decision, routing("r"), routing(bad), source)
        assert fallback["text"] == literal and fallback["answer_source"] == "scripted_case"
    truncated = patient_event(
        context, decision, routing("r"), {"text": "I took", "finish_reason": "length"}, source
    )
    assert truncated["text"] == literal and truncated["answer_source"] == "scripted_case"
    # Numbers already present in the authored facts stay allowed, in either digit form.
    context["language"] = "hi"
    hindi = route(context, routing('{"kind":"topic","topics":["age"]}'))
    _, hindi_source = voice_messages(context, hindi, [])
    spoken = patient_event(context, hindi, routing("r"), routing("मैं ३५ साल का हूँ।"), hindi_source)
    assert spoken["answer_source"] == "patient_voice"


def test_bounded_history_keeps_the_current_message_and_whole_exchanges():
    """The message being answered is never a candidate for trimming."""
    conversation = [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
        {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "now"},
    ]
    # None leaves the caller's conversation exactly as it is.
    assert bounded_history(conversation, None) == conversation
    # 0 answers the current message with no earlier context at all.
    assert bounded_history(conversation, 0) == conversation[-1:]
    # A cap that would start the history on a reply drops that reply instead of sending
    # an answer to a question the model cannot see.
    assert bounded_history(conversation, 1) == conversation[-1:]
    assert bounded_history(conversation, 2) == conversation[2:]
    assert bounded_history(conversation, 10) == conversation
    # A conversation that is only the current message is never touched.
    assert bounded_history(conversation[-1:], 0) == conversation[-1:]


class Recorder:
    """A runner that replies from a script and records what each call was allowed to spend."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    async def complete(self, messages, max_tokens):
        self.calls.append({"messages": messages, "max_tokens": max_tokens})
        return self.replies[len(self.calls) - 1]

    async def native_json(self, method, path, payload=None):  # pragma: no cover - remote fit only
        raise AssertionError("These turns supply their own prompt fitting")


async def unfitted(_runner, messages, max_tokens):
    """The prompts under test are already bounded; record the budget without a model call."""
    return messages, {"reserved_output_tokens": max_tokens, "method": "test"}


def test_turn_budget_caps_each_call_and_never_exceeds_the_connection():
    """Routing and speaking are budgeted separately, and configuration cannot overrun the model."""
    # Defaults: a native server needs its own small split, a remote one may reason inside
    # the completion allowance and keeps it whole.
    assert turn_budget(1024, True) == (ROUTING_TOKENS, VOICE_TOKENS)
    assert turn_budget(1024, False) == (1024, 1024)
    # Configured caps apply to the routing call without touching the spoken one.
    assert turn_budget(1024, False, routing_cap=512) == (512, 1024)
    assert turn_budget(1024, True, routing_cap=96, voice_cap=160) == (96, 160)
    # The connection's own maximum is always the ceiling, however it is configured.
    assert turn_budget(100, False, routing_cap=512) == (100, 100)
    assert turn_budget(64, True, routing_cap=512, voice_cap=512) == (64, 64)
    # One repaired routing attempt gets double the routing allowance, so a truncated object has
    # room without reserving a spoken answer's worth of tokens to emit about fifteen.
    assert repair_budget(*turn_budget(1024, True, routing_cap=75, voice_cap=256)) == 150
    assert repair_budget(*turn_budget(4096, False, routing_cap=512)) == 1024
    # The spoken allowance is the ceiling, and it is already clamped to the connection.
    assert repair_budget(*turn_budget(64, True, routing_cap=75, voice_cap=256)) == 64
    assert repair_budget(*turn_budget(1024, True, routing_cap=75, voice_cap=100)) == 100
    # A connection configured to speak in fewer tokens than it routes in cannot shrink the retry.
    assert repair_budget(*turn_budget(4096, False, routing_cap=512, voice_cap=384)) == 512


def test_routing_prompt_stays_inside_the_local_context_budget():
    for row in json.loads(
        (Path(__file__).parents[1] / "migrations/versions/0014_patient_case_templates.json").read_text(
            encoding="utf-8"
        )
    ):
        document = row["document"]
        assert len(document["dialogue"]["topics"]) == 32
        prompt = patient_context(document, "en", "hello")["system"]
        size = len(prompt.encode("utf-8"))
        # Two budgets, written out rather than folded into one byte count, because they
        # bind differently and a future prompt change should fail against the real one.
        #
        # Local: llama.cpp tokenises natively inside a 2048-token window. Three bytes per
        # token is pessimistic for this mixed English/Devanagari prompt - measured against
        # the shipped case it was 938 tokens for 3972 bytes, about 4.2 bytes per token -
        # and the routing allowance and safety margin still have to fit beside it.
        assert size / 3 + ROUTING_TOKENS + 64 <= 2048, row["code"]
        # A repaired attempt keeps the whole index, adds its rule and is allowed the larger
        # spoken output, so it is the widest routing prompt a turn can send.
        repair = size + len(("\n" + REPAIR_RULE).encode("utf-8"))
        assert repair / 3 + repair_budget(ROUTING_TOKENS, VOICE_TOKENS) + 64 <= 2048, row["code"]
        # The spoken and deflection prompts share the same window. The spoken one is measured
        # against the three largest authored answers, because that is what a routed triple
        # carries; the deflection one carries labels only and is much smaller.
        context = patient_context(document, "hi", "?")
        widest = sorted(context["answers"], key=lambda t: len(context["answers"][t]["hi"]))[-3:]
        spoken, _ = voice_messages(
            context, route(context, routing(json.dumps({"kind": "topic", "topics": widest}))), []
        )
        for prompt in (spoken[0]["content"], deflection_messages(context, [])[0][0]["content"]):
            assert len(prompt.encode("utf-8")) / 3 + VOICE_TOKENS + 64 <= 2048, row["code"]
        # Remote: fit_patient_prompt deliberately never claims an exact remote count and
        # estimates one token per byte plus 32 per message. That is roughly four times the
        # real cost, so it is the prompt, a full history and the routing allowance that
        # set the smallest remote context a 32-topic case can run on.
        assert size + 13 * 32 + 512 + 64 <= 8192, row["code"]


async def test_context_budget_trims_pairs_and_preserves_mandatory_facts():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        data = json.loads(request.content) if request.content else {}
        if request.url.path == "/props":
            return httpx.Response(200, json={"default_generation_settings": {"n_ctx": 2048}})
        if request.url.path == "/apply-template":
            return httpx.Response(200, json={"prompt": "".join(m["content"] for m in data["messages"])})
        return httpx.Response(200, json={"tokens": [1] * len(data["content"])})

    client = LLMClient(10)
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    params = {
        "base_url": "http://127.0.0.1:8787",
        "key": "fixture",
        "provider": "local_llama_cpp",
        "max_tokens": 128,
        "messages": [
            {"role": "system", "content": "MANDATORY"},
            {"role": "user", "content": "x" * 2000},
            {"role": "assistant", "content": "old"},
            {"role": "user", "content": "current"},
        ],
    }
    try:
        messages, budget = await fit_patient_prompt(
            client,
            params,
            Settings.model_construct(patient_local_context_tokens=2048, patient_remote_context_tokens=None),
        )
        assert [m["content"] for m in messages] == ["MANDATORY", "current"]
        assert budget["history_pairs_dropped"] == 1 and budget["method"] == "native_tokenizer"
        params["messages"] = [
            {"role": "system", "content": "x" * 2000},
            {"role": "user", "content": "current"},
        ]
        with pytest.raises(AppError, match="required patient context"):
            await fit_patient_prompt(
                client,
                params,
                Settings.model_construct(
                    patient_local_context_tokens=2048, patient_remote_context_tokens=None
                ),
            )
        params["provider"] = "openai"
        with pytest.raises(AppError, match="remote model context"):
            await fit_patient_prompt(
                client,
                params,
                Settings.model_construct(
                    patient_local_context_tokens=2048, patient_remote_context_tokens=None
                ),
            )
        _, budget = await fit_patient_prompt(
            client,
            params,
            Settings.model_construct(patient_local_context_tokens=2048, patient_remote_context_tokens=4096),
        )
        assert budget["method"] == "utf8_upper_estimate"
    finally:
        await client.close()


def test_patient_llm_json_sse_revision_and_no_raw_routing(llm, monkeypatch):
    p, t, _, org, base, _, body, model = llm
    p.settings.patient_remote_context_tokens = 8192
    practice_base, save_body, saved = setup(p, t, org)
    captured = []
    output_limits = []

    async def budget(client, params, settings, **kw):
        captured.append(params["messages"])
        return params["messages"], {
            "prompt_tokens": 800,
            "reserved_output_tokens": params["max_tokens"],
            "safety_margin_tokens": 128,
        }

    monkeypatch.setattr("pms_api.modules.llm.fit_patient_prompt", budget)

    async def events(**params):
        model.calls += 1
        output_limits.append(params["max_tokens"])
        speaking = "CASE FACTS" in params["messages"][0]["content"]
        yield {"type": "delta", "text": "SPOKEN-CHUNK" if speaking else "RAW-PRIVATE-ROUTING"}
        yield {
            "type": "done",
            "text": "My name is Alex and I am 35."
            if speaking
            else '{"kind":"topic","topics":["name","age"]}',
            "finish_reason": "stop",
            "usage": {},
            "total_ms": 12,
        }

    monkeypatch.setattr(model, "events", events)
    body.update(practice_id=saved["id"], practice_revision=1, language="en")
    body["conversation_id"] = start_for_completion(p, t, org, body)
    answer = p.call("POST", base + "/completions", t, json=body)
    # Routing selects the topics; the spoken call rephrases only their authored facts.
    assert answer["text"] == "My name is Alex and I am 35."
    assert answer["answer_source"] == "patient_conversation" and answer["topics"] == []
    assert answer["context"]["practice_revision"] == 1
    assert answer["context"]["conversation"]["prompt_tokens"] == 800
    assert len(captured) == 1
    assert "My name is Alex." in captured[0][0]["content"]
    response = p.client.post(
        "/api/v1" + base + "/completions",
        headers=p.headers(t),
        json={**body, "stream": True, "request_key": str(uuid4())},
    )
    # Neither call's raw provider deltas reach the caller: the answer is released once, after the guard.
    assert "RAW-PRIVATE-ROUTING" not in response.text and "SPOKEN-CHUNK" not in response.text
    assert "My name is Alex and I am 35." in response.text
    assert "event: delta" in response.text and "event: done" in response.text
    p.call("PUT", practice_base + "/selection", t, json={**save_body, "expected_revision": 1})
    p.call("POST", base + "/completions", t, expected=409, json=body)
    assert model.calls == 2
    # A remote model keeps the connection's full allowance for each of the two calls; the
    # tighter native split is exercised where a local model actually runs, in human-test.
    assert output_limits == [100, 100]


def test_patient_setup_change_during_generation_blocks_answer(llm, monkeypatch):
    p, t, _, org, base, _, body, model = llm
    p.settings.patient_remote_context_tokens = 8192
    practice_base, save_body, saved = setup(p, t, org)

    async def budget(client, params, settings, **kw):
        return params["messages"], {
            "prompt_tokens": 800,
            "reserved_output_tokens": params["max_tokens"],
            "safety_margin_tokens": 128,
        }

    monkeypatch.setattr("pms_api.modules.llm.fit_patient_prompt", budget)

    async def events(**params):
        model.calls += 1
        yield {"type": "delta", "text": "MUST-NOT-LEAK"}
        await asyncio.sleep(1)
        yield {"type": "done", "text": "My name is Alex.", "finish_reason": "stop"}

    monkeypatch.setattr(model, "events", events)
    body.update(practice_id=saved["id"], practice_revision=1, language="en", stream=True)
    body["conversation_id"] = start_for_completion(p, t, org, body)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            p.client.post, "/api/v1" + base + "/completions", headers=p.headers(t), json=body
        )
        deadline = time.monotonic() + 5
        while not model.calls and time.monotonic() < deadline:
            time.sleep(0.01)
        p.call("PUT", practice_base + "/selection", t, json={**save_body, "expected_revision": 1})
        response = future.result()
    assert "MUST-NOT-LEAK" not in response.text and "patient_setup_changed" in response.text
    assert p.sql("SELECT status FROM device_platform.llm_requests") == [("failed",)]


@pytest.mark.parametrize("provider", ["openai", "openai_compatible"])
def test_remote_patient_context_keeps_provider_output_budget_and_protocol(llm, provider):
    p, token, _, org, base, _, body, _ = llm
    _, _, saved = setup(p, token, org)
    url = "https://api.openai.com/v1" if provider == "openai" else "https://gateway.example/v1"
    p.settings.llm_allowed_base_urls = [url]
    p.settings.external_calls_enabled = True
    p.settings.patient_remote_context_tokens = 8192
    role = "developer" if provider == "openai" else "system"
    connection = p.call(
        "POST",
        base + "/connections",
        token,
        expected=201,
        json={
            "name": "Mock remote patient",
            "provider": provider,
            "base_url": url,
            "model": "explicit-model",
            "max_tokens": 1024,
            "api_key": "fixture-secret",
            "instruction_role": role,
        },
    )
    calls = []

    def handler(request):
        assert request.method == "POST" and request.url.path == "/v1/chat/completions"
        payload = json.loads(request.content)
        calls.append(payload)
        prompt = payload["messages"][0]["content"]
        assert payload["messages"][0]["role"] == role
        speaking = "CASE FACTS" in prompt
        # The spoken call keeps the connection's whole allowance. Routing is capped
        # separately: it emits about fifteen tokens of JSON and the rest of a reasoning
        # model's allowance is deliberation nobody reads, so paying for 1024 of it on
        # every turn is waste. The cap is configuration, not a constant.
        allowance = "max_completion_tokens" if provider == "openai" else "max_tokens"
        assert payload[allowance] == (1024 if speaking else 512)
        # Thinking is left to the provider default unless a model has been measured with
        # it off; nothing here may quietly change how the provider reasons.
        assert "chat_template_kwargs" not in payload
        assert ("My name is Alex" in prompt) is speaking
        reply = "My name is Alex and I am 35." if speaking else '{"kind":"topic","topics":["name","age"]}'
        if payload["stream"]:
            return httpx.Response(
                200,
                content="data: "
                + json.dumps({"choices": [{"delta": {"content": reply}, "finish_reason": "stop"}]})
                + "\n\ndata: [DONE]\n\n",
            )
        return httpx.Response(
            200, json={"choices": [{"message": {"content": reply}, "finish_reason": "stop"}]}
        )

    p.client.app.state.llm = LLMClient(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    body.update(connection_id=connection["id"], practice_id=saved["id"], practice_revision=1, language="en")
    body["conversation_id"] = start_for_completion(p, token, org, body)
    result = p.call("POST", base + "/completions", token, json=body)
    assert (
        result["text"] == "My name is Alex and I am 35." and result["answer_source"] == "patient_conversation"
    )
    for phase, reserved in (("conversation", 1024),):
        assert result["context"][phase]["method"] == "utf8_upper_estimate"
        assert result["context"][phase]["reserved_output_tokens"] == reserved
    response = p.client.post(
        "/api/v1" + base + "/completions",
        headers=p.headers(token),
        json={**body, "stream": True, "request_key": str(uuid4())},
    )
    assert (
        response.status_code == 200
        and "My name is Alex and I am 35." in response.text
        and "event: done" in response.text
    )
    assert len(calls) == 2


def test_general_llm_idempotency_fingerprint_stays_compatible_with_pre_practice_requests(llm):
    p, token, _, _, base, _, body, model = llm
    legacy = Completion.model_validate(body).model_dump(
        mode="json",
        exclude={"stream", "practice_id", "practice_revision", "profile_revision_id", "configuration_hash"},
    )
    expected = token_hash(canonical(legacy), p.settings.token_pepper.get_secret_value())
    p.call("POST", base + "/completions", token, json=body)
    assert p.sql(
        "SELECT fingerprint FROM device_platform.llm_requests WHERE request_key=%s", (body["request_key"],)
    ) == [(expected,)]
    assert p.call("POST", base + "/completions", token, json=body)["cached"]
    assert model.calls == 1


def start_for_completion(p, token, org, body):
    value = p.call(
        "POST",
        f"/organizations/{org}/patient-practice/conversations",
        token,
        json={
            "request_key": str(uuid4()),
            **{k: body[k] for k in ("practice_id", "practice_revision", "connection_id", "language")},
        },
    )
    return value["context"]["conversation_id"]
