"""Repeatable storage-overhead benchmark with synthetic inference and HTTP, never cloud calls."""

import argparse
import asyncio
import base64
import importlib.util
import json
import statistics
import tempfile
import time
import tracemalloc
from pathlib import Path
from uuid import uuid4

import httpx
import training_client.controller as controller_module
from training_client.conversation_history import HistoryRecorder
from training_client.history_outbox import Outbox

from human_test.config import Settings


def distribution(values):
    ordered = sorted(values)
    return {
        "p50_ms": round(statistics.median(ordered), 3),
        "p95_ms": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))], 3),
        "p99_ms": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.99))], 3),
    }


async def measure(mode, samples, baseline=None):
    issuer, subject = "benchmark", "fictional-operator"
    claims = base64.urlsafe_b64encode(json.dumps({"iss": issuer, "sub": subject}).encode()).decode()
    statuses, enqueue_times, durations, delivery = [], [], [], []

    class SlowOutbox(Outbox):
        def put(self, *args, **kwargs):
            time.sleep(0.04)
            return super().put(*args, **kwargs)

    with tempfile.TemporaryDirectory(prefix="history-benchmark-") as folder:
        settings = Settings(
            _env_file=None,
            history_enabled=mode not in {"disabled", "before"},
            history_dir=Path(folder),
            organization_id=uuid4(),
            connection_id=uuid4(),
            pms_token="header." + claims + ".signature",
        )

        def handler(request):
            if mode == "unavailable":
                return httpx.Response(503)
            if request.url.path.endswith("/identity"):
                return httpx.Response(
                    200,
                    json={
                        "issuer": issuer,
                        "subject": subject,
                        "organization_id": str(settings.organization_id),
                    },
                )
            data = json.loads(request.content)
            return httpx.Response(200, json={"turn_key": data["turn_key"]})

        def factory(value, emit):
            worker = HistoryRecorder(
                value,
                emit,
                transport=httpx.MockTransport(handler),
                outbox_factory=SlowOutbox if mode == "slow_disk" else Outbox,
            )
            enqueue = worker.enqueue

            def timed(*args):
                began = time.perf_counter()
                result = enqueue(*args)
                enqueue_times.append((time.perf_counter() - began) * 1000)
                return result

            worker.enqueue = timed
            return worker

        original = controller_module.HistoryRecorder
        controller_module.HistoryRecorder = factory
        began = 0.0

        def emit(kind, value):
            if kind == "speak":
                delivery.append((time.perf_counter() - began) * 1000)
            if kind == "history_status":
                statuses.append(value["status"])

        cls = baseline if mode == "before" else controller_module.Controller
        controller = cls(settings, emit)
        controller_module.HistoryRecorder = original
        controller.pms.model_route = {
            "profile_revision_id": str(uuid4()),
            "configuration_hash": "c" * 64,
            "llm": {
                "mode": "local",
                "execution": "caller",
                "model": "synthetic-benchmark",
                "connection_id": str(settings.connection_id),
                "connection_revision": 1,
            },
        }

        async def answer(*args):
            await asyncio.sleep(0.02)
            return {
                "text": "Fictional benchmark answer.",
                "language": "en",
                "finish_reason": "stop",
                "total_ms": 20,
                "usage": None,
                "answer_source": "plain_completion",
            }

        async def metrics(*args):
            await asyncio.sleep(0.05)

        controller.local_answer = answer
        if mode == "before":
            controller.record_local_turn = metrics
        else:
            controller.metrics_reporter.send = metrics
        tracemalloc.start()
        cpu = time.process_time()
        try:
            if getattr(controller, "recorder", None):
                await asyncio.to_thread(controller.recorder.ready.wait, 5)
            for _ in range(samples):
                began = time.perf_counter()
                await controller.text_turn("Fictional benchmark question?")
                durations.append((time.perf_counter() - began) * 1000)
            cpu_ms = (time.process_time() - cpu) * 1000
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
            await controller.close()
        result = {
            "turn_return": distribution(durations),
            "answer_delivery": distribution(delivery),
            "cpu_ms": round(cpu_ms, 2),
            "python_peak_bytes": peak,
            "not_saved": statuses.count("not_saved"),
            "flush_incomplete": statuses.count("flush_incomplete"),
        }
        if enqueue_times:
            result["enqueue"] = distribution(enqueue_times)
        return result


async def run(args):
    baseline = None
    if args.baseline:
        spec = importlib.util.spec_from_file_location("human_test._history_baseline", args.baseline)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        baseline = module.Controller
    modes = (["before"] if baseline else []) + ["disabled", "saved", "unavailable", "slow_disk"]
    results = {
        "verification": "synthetic inference (20 ms) and metrics (50 ms); no model/provider calls",
        "samples_per_mode": args.samples,
    }
    for mode in modes:
        results[mode] = await measure(mode, args.samples, baseline)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    arguments = parser.parse_args()
    if not 20 <= arguments.samples <= 500:
        parser.error("samples must be between 20 and 500")
    asyncio.run(run(arguments))
