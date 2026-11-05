"""Native 25-question qualification; fictional fixture, isolated server, no PMS/cloud."""

# ruff: noqa: E402 - standalone CLI adds the existing native runtime scripts before imports.

import argparse
import asyncio
import json
import math
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "local-models/scripts"))
sys.path.insert(0, str(ROOT / "local-models/client/src"))
import common
import run
from local_model_client.native import LocalModel, new_client
from training_contracts.conversation.background import restore_starter_background
from training_contracts.conversation.engine import fit_conversation_prompt, run_conversation
from training_contracts.conversation.prompt import conversation_context
from training_contracts.localized_cases import review_localization


class RecordingLocalModel(LocalModel):
    """Only the fictional qualification fixture records raw evidence envelopes."""

    async def complete(self, messages, max_tokens):
        self.last_completion = await super().complete(messages, max_tokens)
        return self.last_completion


async def exercise(server, task, rounds, history_mode, matrix_path, background_fixture=None):
    rows = json.loads(
        (ROOT / "platform/api/migrations/versions/0014_patient_case_templates.json").read_text(
            encoding="utf-8"
        )
    )
    source = next(row["document"] for row in rows if row["code"] == "alex_chest_discomfort")
    document = restore_starter_background(source)
    if background_fixture:
        document["background"] = json.loads(background_fixture.read_text(encoding="utf-8"))
    document = review_localization(document, "en")
    context = conversation_context(document, "en", "", seed="qualification-session")
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    if not 20 <= len(matrix["questions"]) <= 25:
        raise ValueError("Qualification requires 20 to 25 questions")
    (task / "fixture.json").write_text(json.dumps(document, indent=2), encoding="utf-8")
    (task / "system.txt").write_text(context["system"], encoding="utf-8")
    results = []
    async with new_client(120) as client:
        model = RecordingLocalModel(
            17887, server.key, server.profile["alias"], context_cap=2048, client=client
        )
        for round_number in range(1, rounds + 1):
            history = []
            for index, probe in enumerate(matrix["questions"]):
                active_history = (
                    history[-4:] if history_mode == "rolling" and probe.get("history") != "empty" else []
                )
                started = time.perf_counter()
                item = {
                    "round": round_number,
                    "index": index + 1,
                    **probe,
                    "history_pairs": len(active_history) // 2,
                }
                model.last_completion = None
                try:
                    messages, budget = await fit_conversation_prompt(
                        model,
                        [
                            {"role": "system", "content": context["system"]},
                            *active_history,
                            {"role": "user", "content": probe["question"]},
                        ],
                        128,
                        context=context,
                    )
                    preparation_ms = (time.perf_counter() - started) * 1000
                    event = await run_conversation(model, context, messages, 128)
                    item.update(
                        answer=event["text"],
                        budget=budget,
                        preparation_ms=round(preparation_ms, 2),
                        first_token_ms=event["first_token_ms"],
                        usage=event["usage"],
                        provider_calls=event["provider_calls"],
                        raw_reply=model.last_completion["text"],
                    )
                    history.extend(
                        [
                            {"role": "user", "content": probe["question"]},
                            {"role": "assistant", "content": event["text"]},
                        ]
                    )
                    history = history[-4:]
                except Exception as error:
                    item["error"] = getattr(error, "code", type(error).__name__)
                    if model.last_completion:
                        item["raw_reply"] = model.last_completion["text"]
                item["total_ms"] = round((time.perf_counter() - started) * 1000, 2)
                results.append(item)
                # Incremental evidence survives a failed later turn without replaying it.
                (task / "answers.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
                print(
                    f"Round {round_number}, question {index + 1}/{len(matrix['questions'])}: {item.get('answer', item.get('error'))} "
                    f"({item['total_ms']} ms)",
                    flush=True,
                )
    warm = [item for item in results if item["index"] > 1 and "answer" in item]
    values = sorted(item["total_ms"] for item in warm)
    summary = {
        "model": server.profile["name"],
        "context_tokens": 2048,
        "gpu_layers": server.settings["gpu_layers"],
        "cpu_threads": server.settings["cpu_threads"],
        "offloaded_layers": server.metrics["offloaded_layers"],
        "model_layers": server.metrics["total_layers"],
        "history_mode": history_mode,
        "rounds": rounds,
        "compiler_version": context["compiler_version"],
        "answers": len([item for item in results if "answer" in item]),
        "errors": len([item for item in results if "error" in item]),
        "warm_samples": len(values),
        "warm_p50_ms": statistics.median(values) if values else None,
        "warm_p95_ms": values[max(0, math.ceil(len(values) * 0.95) - 1)] if values else None,
        "prompt_tokens_mean": statistics.mean(item["budget"]["prompt_tokens"] for item in warm)
        if warm
        else None,
        "preparation_mean_ms": statistics.mean(item["preparation_ms"] for item in warm) if warm else None,
        "one_generation_per_answer": all(item["provider_calls"] == 1 for item in warm),
        "prompt_tokens_max": max((item["budget"]["prompt_tokens"] for item in warm), default=None),
        "all_fitted_prompts_within_context": all(
            item["budget"]["prompt_tokens"] + 128 + 128 <= 2048 for item in results if "budget" in item
        ),
        "model_startup_seconds": round(server.metrics["startup_seconds"], 2),
        "first_answer_ms": results[0]["total_ms"] if results else None,
        "max_answer_ms": max((item["total_ms"] for item in results), default=None),
        "prompt_modes": {
            mode: sum(item.get("budget", {}).get("prompt_mode") == mode for item in results)
            for mode in (
                "grounded_patient",
                "patient_measurement",
                "standalone_lifestyle",
                "standalone_general",
                "standalone_greeting",
                "standalone_clarification",
            )
        },
    }
    (task / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    table = [
        "# Native local-model answers",
        "",
        "Actual generated answers for the fictional starter, "
        "with two recent dialogue pairs when rolling history is enabled.",
        "",
        "| # | Question | Answer | Complete answer (s) |",
        "| --- | --- | --- | --- |",
    ]
    for item in results:
        if item["round"] != 1:
            continue
        question = item["question"].replace("|", "\\|").replace("\n", " ")
        answer = item.get("answer", item.get("error", "")).replace("|", "\\|").replace("\n", " ")
        table.append(f"| {item['index']} | {question} | {answer} | {item['total_ms'] / 1000:.2f} |")
    (task / "answers.md").write_text("\n".join(table) + "\n", encoding="utf-8")
    print(json.dumps(summary), flush=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rounds", type=int, choices=range(1, 6), default=1)
    parser.add_argument("--history", choices=("isolated", "rolling"), default="isolated")
    parser.add_argument(
        "--matrix", type=Path, default=Path(__file__).with_name("qualification-questions.json")
    )
    parser.add_argument("--additional-matrix", type=Path)
    parser.add_argument("--background-fixture", type=Path)
    parser.add_argument(
        "--gpu-layers", type=int, choices=range(1, 100), default=20, help="GPU layers (default: 20)"
    )
    parser.add_argument("--threads", type=int, choices=range(1, 33))
    args = parser.parse_args()
    task = args.output.resolve()
    task.mkdir(parents=True, exist_ok=False)
    common.STATE = task / "native-state"
    common.STATE.mkdir()
    run.STATE = common.STATE
    settings = common.config()
    settings.update(
        port=17887, gpu_enabled=True, gpu_layers=args.gpu_layers, max_tokens=128, context_size=2048
    )
    if args.threads is not None:
        settings["cpu_threads"] = args.threads

    async def suites(server):
        await exercise(server, task, args.rounds, args.history, args.matrix, args.background_fixture)
        if args.additional_matrix:
            heldout = task / "heldout"
            heldout.mkdir()
            print("Starting additional question matrix on the same resident model", flush=True)
            await exercise(
                server, heldout, args.rounds, args.history, args.additional_matrix, args.background_fixture
            )

    with run.Server(settings) as server:
        asyncio.run(suites(server))


if __name__ == "__main__":
    main()
