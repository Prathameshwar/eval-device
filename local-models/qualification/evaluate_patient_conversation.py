"""Live local evaluation using fictional seed cases; no cloud or application database.

Starts and stops its own model. Records answers for semantic review, not a keyword
score pretending to establish factual accuracy. Timing excludes ASR and TTS.
"""

import argparse
import asyncio
import hashlib
import json
import math
import platform
import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from training_client.local_turn import answer
from local_model_client.native import LocalModel, new_client
from training_contracts.localized_cases import convert_v2, review_localization
from training_contracts.patient_conversation import POLICY_VERSION, RULES

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "platform/api/migrations/versions/0014_patient_case_templates.json"
CATEGORIES = {
    "alex_chest_discomfort": "Cardiology",
    "alex_painful_urination": "Nephrology",
    "alex_dry_cough": "Respiratory Medicine",
}


def live_questions(code):
    return [
        (
            "Hello, how are you doing?",
            "en",
            False,
            "Natural greeting; do not invent wellbeing or new symptoms.",
        ),
        ("What is your name?", "en", False, "Alex."),
        ("Tell me what problem brought you here.", "en", False, "Describe this case's chief complaint."),
        ("How long has that been happening?", "en", True, "Case onset/duration, following the complaint."),
        (
            "What else have you noticed with it?",
            "en",
            True,
            "Relevant associated symptoms and negatives only.",
        ),
        ("Are you suffering from fever?", "en", False, "No fever in these three selected cases."),
        (
            "Do you also have a headache?",
            "en",
            False,
            "Headache is unspecified: express uncertainty, not a positive or negative finding.",
        ),
        (
            "What medicine have you tried for this?",
            "en",
            False,
            "Dry cough: unnamed cough syrup, two nights; other selected cases: currently no medicines, without inventing a past treatment trial.",
        ),
        (
            "Did it help?",
            "en",
            True,
            "Dry cough: little benefit; others: no recorded treatment benefit, do not invent a trial or outcome.",
        ),
        (
            "Does anyone in your family have this same problem?",
            "en",
            False,
            "Same complaint is unknown; father's hypertension is not evidence of it.",
        ),
        ("How old are you?", "en", False, "35."),
        ("IBT?", "en", False, "Ask for clarification, do not guess a medical abbreviation."),
        ("What is the capital of France?", "en", False, "Paris; ordinary general conversation is allowed."),
        ("What is twelve plus eight?", "en", False, "20; do not restrict general numbers to case facts."),
        (
            "Are you sexually active?",
            "en",
            False,
            "Unknown personal history; a legitimate clinical question, not a boundary refusal.",
        ),
    ]


def role_questions(code):
    return [
        ("Hello", "en", False, "A patient greeting; no listener name or offer of assistance."),
        ("Hello.", "en", True, "Remain the manikin; do not address the trainee by the manikin name."),
        ("What is your name?", "en", True, "Self-introduce using only the configured patient identity."),
        (
            "My name is Jordan. What is your name?",
            "en",
            True,
            "Keep trainee Jordan distinct from your own configured identity.",
        ),
        ("Hello again", "en", True, "A patient greeting; do not swap speaker identities."),
    ]


def matrix_questions(code):
    questions = [
        ("Tell me your name.", "Alex"),
        ("How old are you?", "35"),
        ("What symptoms made you come in?", "Chief complaint"),
        ("Since when have you had this problem?", "Case duration"),
        ("Are you allergic to any medicine?", "Case allergy history"),
        ("What work do you do?", "Schoolteacher"),
        ("Do you have a headache as well?", "Unknown headache"),
        ("Which city is France's capital?", "Paris"),
        ("Could you tell me what 12 plus 8 makes?", "20"),
        ("Have you had any fever with this?", "Case-specific fever finding"),
        ("Tell me about medicines you take.", "Case medication history"),
        ("Does your father have any medical conditions?", "Father has high blood pressure"),
        (
            "Does anyone in your family have the same complaint as you?",
            "Only explicit matching family evidence; otherwise unknown",
        ),
        ("Do you smoke?", "No smoking"),
        ("Can you describe what the symptom feels like?", "Case symptom details"),
        ("What time do you usually sleep?", "Around eleven to six; seven hours"),
        ("What did you eat yesterday?", "Usual home-cooked rice, dal, vegetables"),
        ("Are your bowels regular?", "Case bowel history"),
        ("Are you seeing double?", "Unknown; do not invent a positive or negative"),
        ("What is your height and weight?", "175 cm and 75 kg"),
        ("Good morning.", "Natural greeting"),
        (
            "What do people mean by swine flu?",
            "General explanation allowed; do not infer patient's diagnosis or classify as abuse",
        ),
        ("Please tell me your problem.", "Chief complaint, not a physical command"),
        ("Are you sexually active?", "Unknown personal history; clinical question is not harassment"),
    ]
    return [(question, "en", False, expected) for question, expected in questions]


async def evaluate(server, options, evidence):
    rows = json.loads(CASES.read_text(encoding="utf-8"))
    async with new_client(120) as client:
        model = LocalModel(
            options.port,
            server.key,
            server.profile["alias"],
            context_cap=options.context,
            client=client,
            enable_thinking=options.thinking,
        )
        await model.health()
        route = {
            "llm": {
                "max_tokens": options.tokens,
                "conversation_tokens": options.tokens,
                "history_messages": 12,
                "instruction_role": "system",
                "system_prompt": "Patient interview",
            }
        }
        for row in rows:
            if options.suite != "matrix" and row["code"] not in CATEGORIES:
                continue
            questions = (
                matrix_questions
                if options.suite == "matrix"
                else role_questions
                if options.suite == "roles"
                else live_questions
            )(row["code"])
            document = convert_v2(row["document"])
            if options.persona_name:
                document["patient"]["name"] = options.persona_name
            document = review_localization(document, "en")
            if options.suite == "baseline":
                questions = [questions[i] for i in (2, 5, 6, 11, 12)]
            history = []
            practice = {"practice_id": str(uuid4()), "practice_revision": 1, "document": document}
            for index, (question, language, followup, expected) in enumerate(questions):
                if not followup:
                    history = []
                messages = [*history, {"role": "user", "content": question}]
                result = {
                    "case": row["code"],
                    "category": CATEGORIES.get(row["code"]),
                    "question": question,
                    "language": language,
                    "expected_meaning": expected,
                    "followup": followup,
                    "index": index + 1,
                }
                started = time.perf_counter()
                try:
                    if options.suite == "baseline":
                        from training_contracts.patient_turn import (
                            fit_patient_prompt,
                            patient_context,
                            run_patient_turn,
                        )

                        context = patient_context(row["document"], language, question)
                        context.update(answer_mode="authored", deflection_mode="authored")
                        prompt, budget = await fit_patient_prompt(
                            model, [{"role": "system", "content": context["system"]}, *messages], 75
                        )
                        context["budget"] = {"routing": budget}
                        event = await run_patient_turn(model, context, prompt, 75, 256)
                    else:
                        event = await answer(
                            model, route, practice, messages, language, lambda *args: None, diagnostic=True
                        )
                    result.update(
                        answer=event["text"],
                        prompt_hash=event.get("prompt_hash"),
                        language_pack_version=event.get("language_pack_version"),
                        language_pack_hash=event.get("language_pack_hash"),
                        compiler_version=event.get("compiler_version"),
                        provider_calls=event["provider_calls"],
                        usage=event.get("usage"),
                        context=event.get("context"),
                        first_token_ms=event.get("first_token_ms"),
                        finish_reason=event["finish_reason"],
                    )
                    history = [*messages, {"role": "assistant", "content": event["text"]}]
                except Exception as error:
                    result["error"] = getattr(error, "code", type(error).__name__)
                    history = []
                result["accepted_text_ms"] = round((time.perf_counter() - started) * 1000)
                evidence["results"].append(result)
                save(options, evidence)
                print(
                    json.dumps(
                        {
                            k: result.get(k)
                            for k in ("case", "index", "accepted_text_ms", "provider_calls", "error")
                        }
                    ),
                    flush=True,
                )
                if options.limit and len(evidence["results"]) >= options.limit:
                    return


def save(options, evidence):
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    sys.path.insert(0, str(ROOT / "local-models/scripts"))
    from common import MODEL_NAMES, config
    from run import Server

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("live", "matrix", "baseline", "roles"), default="live")
    parser.add_argument("--model", choices=MODEL_NAMES)
    parser.add_argument(
        "--attach", action="store_true", help="Use an already running local server; do not start or stop it"
    )
    parser.add_argument(
        "--persona-name", help="Override only the fictional fixture's configured manikin identity"
    )
    parser.add_argument("--cpu", action="store_true")
    parser.add_argument("--thinking", action="store_true")
    parser.add_argument("--tokens", type=int, default=256)
    parser.add_argument("--thinking-budget", type=int, default=128)
    parser.add_argument("--port", type=int, default=18789)
    parser.add_argument("--context", type=int, default=2048)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    native = config()
    if options.model:
        native["model"] = options.model
    native.update(port=options.port, context_size=options.context, max_tokens=options.tokens)
    if options.cpu:
        native["gpu_enabled"] = False
    evidence = {
        "suite": options.suite,
        "policy": POLICY_VERSION,
        "shared_rules_sha256": hashlib.sha256(RULES.encode()).hexdigest(),
        "platform": platform.platform(),
        "settings": {
            key: native[key]
            for key in (
                "model",
                "gpu_enabled",
                "gpu_layers",
                "cpu_threads",
                "context_size",
                "prompt_cache_mib",
                "max_tokens",
            )
        },
        "persona_name_override": options.persona_name,
        "thinking": options.thinking,
        "thinking_budget": options.thinking_budget if options.thinking else 0,
        "scope": "Live local model, fictional cases, typed input; excludes ASR and TTS; semantic review required",
        "results": [],
    }

    class EvaluationServer(Server):
        def arguments(self, executable, key_path):
            args = super().arguments(executable, key_path)
            if options.thinking:
                args[args.index("--reasoning") + 1] = "on"
                args[args.index("--chat-template-kwargs") + 1] = json.dumps({"enable_thinking": True})
                args.extend(
                    ["--reasoning-format", "deepseek", "--reasoning-budget", str(options.thinking_budget)]
                )
            return args

    from common import model_profile

    profile = model_profile(native)
    with profile["path"].open("rb") as artifact:
        evidence["model_artifact"] = {
            "filename": profile["path"].name,
            "sha256": hashlib.file_digest(artifact, "sha256").hexdigest(),
        }
    if options.attach:
        if options.thinking:
            parser.error("An attached server's reasoning settings cannot be changed")
        from common import no_link

        key_path = ROOT / "local-models/.state/api-key.txt"
        no_link(key_path)
        key = key_path.read_text(encoding="utf-8").strip()
        if not key:
            raise RuntimeError("Local model key is missing")
        server = SimpleNamespace(key=key, profile=profile)
        evidence["server"] = {
            "ownership": "external",
            "port": options.port,
            "runtime_settings": "not_measured",
        }
        # Config describes this evaluation's requested limits, not a claim about GPU layers
        # on a server this harness did not launch.
        for key in ("gpu_enabled", "gpu_layers", "cpu_threads", "prompt_cache_mib"):
            evidence["settings"].pop(key, None)
        asyncio.run(evaluate(server, options, evidence))
    else:
        with EvaluationServer(native) as server:
            evidence["server"] = server.metrics
            asyncio.run(evaluate(server, options, evidence))
    timings = sorted(r["accepted_text_ms"] for r in evidence["results"])
    if timings:
        evidence["timings"] = {
            "count": len(timings),
            "median_ms": statistics.median(timings),
            "p95_ms": timings[math.ceil(len(timings) * 0.95) - 1],
            "max_ms": max(timings),
            "percentile_method": "nearest_rank_all_attempts",
        }
    save(options, evidence)
    if any("error" in row for row in evidence["results"]):
        raise SystemExit("Some generations failed; inspect the saved evidence")


if __name__ == "__main__":
    main()
