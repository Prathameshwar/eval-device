"""Opt-in local Qwen patient pipeline benchmark using fictional seed cases.

Run using the Human-test client environment: uv run --project human-test python local-models/qualification/benchmark_patient_latency.py.
A local model runs on this laptop and PMS is never on its data path, so this measures the
same path the desktop app takes: prompt budgeting + routing + validated answer. Excludes
PMS, Whisper and playback. Starts and stops its own model server; refuses an existing
local-LLM instance. No cloud calls, application database or patient recordings.
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from uuid import uuid4

import training_client.local_turn as local_turn
from local_model_client.native import LocalModel, new_client

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = (
    ("What is your name?", "en", "name"),
    ("When did your cough start?", "en", "duration"),
    ("What medicines have you taken?", "en", "medications"),
    ("आपकी उम्र कितनी है?", "hi", "age"),
    ("आपको खांसी कब से है?", "hi", "duration"),
    ("आपने कौन सी दवा ली है?", "hi", "medications"),
)
CONTEXT_TOKENS = 2048


def scenario(options, server):
    rows = json.loads(
        (ROOT / "platform/api/migrations/versions/0014_patient_case_templates.json").read_text(
            encoding="utf-8"
        )
    )
    document = next(row["document"] for row in rows if row["code"] == "alex_dry_cough")
    # The shape PMS publishes for a local profile, with fictional identifiers: this script
    # measures the model, not the platform, so it does not call PMS for the route.
    route = {
        "profile_id": str(uuid4()),
        "profile_revision_id": str(uuid4()),
        "configuration_hash": "0" * 64,
        "llm": {
            "mode": "local",
            "execution": "caller",
            "provider": "local_llama_cpp",
            "model": server.profile["alias"],
            "connection_id": str(uuid4()),
            "connection_revision": 1,
            "model_options": {"patient_answer_mode": "generated"},
            "max_tokens": 100,
            "instruction_role": "system",
            "system_prompt": "You are a helpful assistant.",
            "local_port": options.port,
            "local_context_tokens": CONTEXT_TOKENS,
        },
    }
    practice = {"practice_id": str(uuid4()), "practice_revision": 1, "document": document}
    return route, practice


async def measure(server, options):
    route, practice = scenario(options, server)
    client = new_client(180)
    model = LocalModel(
        options.port, server.key, server.profile["alias"], context_cap=CONTEXT_TOKENS, client=client
    )
    results = []
    try:
        await local_turn.health(model)
        for repeat in range(options.rounds):
            for question, language, expected in QUESTIONS:
                started = time.perf_counter()
                event = await local_turn.answer(
                    model,
                    route,
                    practice,
                    [{"role": "user", "content": question}],
                    language,
                    lambda *a: None,
                    diagnostic=True,
                )
                results.append(
                    {
                        "question": question,
                        "language": language,
                        "repeat": repeat,
                        "answer_source": event["answer_source"],
                        "kind": event["kind"],
                        "topics": event["topics"],
                        "provider_calls": event["provider_calls"],
                        "routing_ms": event.get("routing_ms"),
                        "voice_ms": event.get("voice_ms"),
                        "total_ms": event["total_ms"],
                        "context": event["context"],
                        "usage": event.get("usage"),
                        "wall_ms": round((time.perf_counter() - started) * 1000),
                        "expected_topic": expected,
                        "topic_correct": None,
                        # The recorded turn carries no prompt or answer text, as PMS receives it.
                        "record": local_turn.turn_event(route, practice, event),
                    }
                )
                print(
                    f"Round {repeat + 1}, {language}/{expected}: {results[-1]['wall_ms']} ms, "
                    f"{event['provider_calls']} calls, topic correct={results[-1]['topic_correct']}",
                    flush=True,
                )
    finally:
        await client.aclose()
    return results


def main():
    # Reuse installation verification, private credentials and owned-process cleanup.
    sys.path.insert(0, str(ROOT / "local-models/scripts"))
    from common import MODEL_NAMES, config
    from run import Server

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=MODEL_NAMES, default="qwen3-4b")
    parser.add_argument("--cpu", action="store_true")
    parser.add_argument(
        "--gpu-layers",
        type=int,
        choices=range(1, 100),
        default=20,
        metavar="1..99",
        help="GPU layers (default: 20)",
    )
    parser.add_argument("--threads", type=int, choices=range(1, 33), default=6, metavar="1..32")
    parser.add_argument("--cache-mib", type=int, choices=range(0, 1025), default=256, metavar="0..1024")
    parser.add_argument("--rounds", type=int, choices=range(1, 6), default=2)
    parser.add_argument("--port", type=int, default=18787)
    parser.add_argument("--output", type=Path)
    options = parser.parse_args()
    if not 1024 <= options.port <= 65535:
        parser.error("port must be 1024..65535")
    native = config()
    native.update(
        model=options.model,
        gpu_enabled=not options.cpu,
        gpu_layers=options.gpu_layers,
        cpu_threads=options.threads,
        prompt_cache_mib=options.cache_mib,
        port=options.port,
        context_size=CONTEXT_TOKENS,
    )
    with Server(native) as server:
        results = asyncio.run(measure(server, options))
        evidence = {
            "settings": {
                key: native[key]
                for key in (
                    "model",
                    "gpu_enabled",
                    "gpu_layers",
                    "cpu_threads",
                    "prompt_cache_mib",
                    "context_size",
                )
            },
            "server": server.metrics,
            "results": results,
        }
    if options.output:
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Manual semantic review of fictional answers is required; topic timing is not a quality score.")


if __name__ == "__main__":
    main()
