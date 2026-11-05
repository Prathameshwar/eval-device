"""Isolated native local benchmark: fictional case only, no PMS/cloud calls."""

# ruff: noqa: E402 - standalone CLI adds the existing native runtime scripts before imports.

import argparse
import asyncio
import json
import math
import statistics
import subprocess
import sys
import time
import types
from pathlib import Path

root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(root / "local-models/scripts"))
sys.path.insert(0, str(root / "local-models/client/src"))
import common
import run
from local_model_client.native import LocalModel, new_client
from training_contracts.clinical_cases import simplify_case
from training_contracts.conversation.background import background_text, restore_starter_background
from training_contracts.conversation.engine import fit_conversation_prompt, run_conversation
from training_contracts.conversation.prompt import conversation_context
from training_contracts.languages import get_pack
from training_contracts.localized_cases import review_localization

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--baseline-ref", default="HEAD")
parser.add_argument("--rounds", type=int, choices=range(1, 11), default=4)
parser.add_argument("--quality", action="store_true")
args = parser.parse_args()
task = args.output.resolve()
task.mkdir(parents=True, exist_ok=False)
common.STATE = task / "native-state"
common.STATE.mkdir(exist_ok=True)
run.STATE = common.STATE
settings = common.config()
settings.update(port=17887, gpu_enabled=True, max_tokens=128, context_size=2048)
old_source = subprocess.check_output(
    [
        "git",
        "show",
        args.baseline_ref + ":shared/training-contracts/src/training_contracts/conversation/prompt.py",
    ],
    cwd=root,
).decode()
old_instructions = subprocess.check_output(
    [
        "git",
        "show",
        args.baseline_ref
        + ":shared/training-contracts/src/training_contracts/languages/packs/en/instructions.txt",
    ],
    cwd=root,
).decode()
old = types.ModuleType("baseline_prompt")
old.__package__ = "training_contracts.conversation"
exec(old_source, old.__dict__)


class Registry:
    def get(self, language):
        return get_pack(language).model_copy(update={"instructions": old_instructions})


rows = json.loads(
    (root / "platform/api/migrations/versions/0014_patient_case_templates.json").read_text(encoding="utf-8")
)
source = next(row["document"] for row in rows if row["code"] == "alex_chest_discomfort")
clinical = review_localization(simplify_case(source), "en")
restored = review_localization(restore_starter_background(source), "en")
baseline = old.conversation_context(clinical, "en", "", registry=Registry())
current = conversation_context(restored, "en", "", seed="native-fixture")
baseline["system"] += "\nAdditional authored CASE FACTS:\n" + background_text(current["session_background"])
questions = [
    "What is your name?",
    "What brings you in today?",
    "When did this start?",
    "Does resting help?",
    "What did you eat yesterday?",
    "How do you usually sleep?",
    "What exercise do you do?",
    "What medicine did you try for this pain?",
    "What is the capital of France?",
    "Who do you live with?",
]


async def exercise(server):
    events = []
    async with new_client(120) as client:
        model = LocalModel(17887, server.key, server.profile["alias"], context_cap=2048, client=client)
        for group in range(args.rounds * 2):
            label = ("baseline", "compact", "compact", "baseline")[group % 4]
            context = baseline if label == "baseline" else current
            for index, question in enumerate(questions):
                start = time.perf_counter()
                messages, budget = await fit_conversation_prompt(
                    model,
                    [
                        {"role": "system", "content": context["system"]},
                        {"role": "user", "content": question},
                    ],
                    128,
                    context=context,
                )
                prepared = (time.perf_counter() - start) * 1000
                event = await run_conversation(model, context, messages, 128)
                events.append(
                    {
                        "path": label,
                        "group": group,
                        "index": index,
                        "question": question,
                        "answer": event["text"],
                        "prompt_tokens": budget["prompt_tokens"],
                        "preparation_ms": round(prepared, 2),
                        "first_token_ms": event["first_token_ms"],
                        "total_ms": round((time.perf_counter() - start) * 1000, 2),
                        "usage": event["usage"],
                        "provider_calls": event["provider_calls"],
                    }
                )
                print(f"Native {label} {index + 1}/{len(questions)} complete", flush=True)
    summary = {}
    for label in ("baseline", "compact"):
        group = [value for value in events if value["path"] == label and value["index"] > 0]
        values = sorted(value["total_ms"] for value in group)
        summary[label] = {
            "prompt_tokens_mean": statistics.mean(value["prompt_tokens"] for value in group),
            "warm_samples": len(values),
            "answer_p50_ms": statistics.median(values),
            "answer_p95_ms": values[max(0, math.ceil(len(values) * 0.95) - 1)],
            "preparation_mean_ms": statistics.mean(value["preparation_ms"] for value in group),
        }
    (task / "native-results-final.json").write_text(
        json.dumps({"summary": summary, "events": events}, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary), flush=True)
    if not args.quality:
        return
    matrix = json.loads(
        (root / "docs/simulations/patient-background/question-matrix.json").read_text(encoding="utf-8")
    )
    probes = list(dict.fromkeys(row["question"] for row in matrix["background_questions"] + matrix["checks"]))
    quality = []
    async with new_client(120) as client:
        model = LocalModel(17887, server.key, server.profile["alias"], context_cap=2048, client=client)
        for index, question in enumerate(probes):
            messages, budget = await fit_conversation_prompt(
                model,
                [{"role": "system", "content": current["system"]}, {"role": "user", "content": question}],
                128,
                context=current,
            )
            event = await run_conversation(model, current, messages, 128)
            quality.append(
                {"question": question, "answer": event["text"], "prompt_tokens": budget["prompt_tokens"]}
            )
            print(f"Quality {index + 1}/{len(probes)} complete", flush=True)
    (task / "native-quality.json").write_text(json.dumps(quality, indent=2), encoding="utf-8")
    varied = json.loads(json.dumps(restored))
    varied["background"] = [
        {
            "id": "food_drink",
            "text": {"en": "I eat home-cooked meals.", "hi": "Home meals"},
            "allow_variation": True,
            "choices": [
                {"id": "rice", "text": {"en": "My usual meal is rice and vegetables.", "hi": "Rice"}},
                {"id": "bread", "text": {"en": "My usual meal is bread and vegetables.", "hi": "Bread"}},
            ],
        }
    ]
    varied = review_localization(varied, "en")
    stable = conversation_context(varied, "en", "", seed="native-choice")
    variation_results = []
    async with new_client(120) as client:
        model = LocalModel(17887, server.key, server.profile["alias"], context_cap=2048, client=client)
        for history in (
            [],
            [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hello"}],
            [],
        ):
            question = "What is your usual meal?"
            messages, _ = await fit_conversation_prompt(
                model,
                [
                    {"role": "system", "content": stable["system"]},
                    *history,
                    {"role": "user", "content": question},
                ],
                128,
                context=stable,
            )
            result = await run_conversation(model, stable, messages, 128)
            variation_results.append(result["text"])
    (task / "native-variation.json").write_text(
        json.dumps({"background": stable["session_background"], "answers": variation_results}, indent=2),
        encoding="utf-8",
    )


with run.Server(settings) as server:
    asyncio.run(exercise(server))
