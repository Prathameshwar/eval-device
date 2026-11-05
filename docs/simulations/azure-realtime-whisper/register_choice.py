"""Register a separate, audited Realtime speech choice in the isolated demo; keep the active profile."""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
from dotenv import dotenv_values
from pms_api.core.config import Settings
from pms_api.integrations.llm.client import LLMClient
from pms_api.integrations.whisper_cloud import transcribe
from pms_api.main import create_app
from probe import BASELINE, HOST, MODEL, credential

ROOT = Path(__file__).resolve().parents[3]
NAME = "Azure GPT Realtime Whisper"


async def run(verify_audio, evidence):
    state = ROOT / "human-test/.local/demo"
    config = json.loads((state / "config.json").read_text(encoding="utf-8"))
    if config.get("purpose") != "isolated-human-test-v1":
        raise RuntimeError("Expected isolated demo")
    for name in list(os.environ):
        if name.startswith("PMS_"):
            del os.environ[name]
    settings = Settings(_env_file=state / "pms.env")
    values = dotenv_values(state / "human.env")
    token = values.get("HUMAN_PMS_TOKEN")
    if not token:
        raise RuntimeError("Start the demo once to create the private operator session")
    app = create_app(settings)
    base = f"/api/v1/organizations/{config['organization_id']}"
    endpoint = f"https://{HOST}/openai/v1"
    realtime_settings = {"endpoint": endpoint, "deployment": MODEL, "model": MODEL}
    key = credential()
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://demo.local",
            headers={"Authorization": "Bearer " + token},
        ) as api,
    ):

        async def call(method, path, **kwargs):
            response = await api.request(method, base + path, **kwargs)
            if response.status_code not in {200, 201}:
                evidence["failed_http_status"] = response.status_code
                raise RuntimeError(
                    f"PMS configuration request failed: HTTP {response.status_code}"
                )
            return response.json()

        async def load_connection(connection_id):
            cursor = None
            for _ in range(20):
                page = await call(
                    "GET",
                    "/connections",
                    params={"limit": 100, **({"cursor": cursor} if cursor else {})},
                )
                found = next(
                    (row for row in page["items"] if row["id"] == connection_id),
                    None,
                )
                if found:
                    return found
                cursor = page.get("next_cursor")
                if not cursor:
                    break
            raise RuntimeError(
                "Speech connection was not found in the bounded connection list"
            )

        options = await call("GET", "/model-options")
        before = await call("GET", "/model-config")
        existing = next((row for row in options["speech"] if row["name"] == NAME), None)
        if existing:
            row = await load_connection(existing["id"])
            if row["settings"] != realtime_settings:
                raise RuntimeError(
                    "Existing choice has different settings; no overwrite performed"
                )
            evidence["connection_created"] = False
        else:
            row = await call(
                "POST",
                "/connections",
                json={
                    "name": NAME,
                    "provider": "azure",
                    "connection_type": "azure_openai_whisper",
                    "auth_mode": "api_key",
                    "settings": realtime_settings,
                    "credentials": {"api_key": key},
                },
            )
            evidence["connection_created"] = True
        evidence["connection_id"] = row["id"]
        validated = await call(
            "POST",
            f"/connections/{row['id']}/validate",
            json={"operation": "audio.transcribe", "sample": False},
        )
        validation = validated["validation_results"]["audio.transcribe"]
        evidence["validation_status"] = validation["status"]
        if validation["status"] != "valid":
            raise RuntimeError("Realtime session validation did not succeed")
        choices = await call("GET", "/model-options")
        evidence["speech_choices"] = [
            {k: row[k] for k in ("name", "model")} for row in choices["speech"]
        ]
        after = await call("GET", "/model-config")
        evidence["active_profile_unchanged"] = (
            before["configuration_hash"] == after["configuration_hash"]
        )
        if not evidence["active_profile_unchanged"]:
            raise RuntimeError(
                "Active selection changed concurrently; review the current selection"
            )
        if verify_audio:
            originals = []
            for choice in choices["speech"]:
                candidate = await load_connection(choice["id"])
                if (
                    candidate["settings"].get("model", "whisper") == "whisper"
                    and candidate["settings"].get("endpoint") == endpoint
                ):
                    originals.append(candidate)
            if len(originals) != 1:
                raise RuntimeError(
                    "Expected one original Whisper choice on the same Azure resource"
                )
            old = originals[0]
            evidence["audio_checks"] = checks = []
            client = LLMClient(settings.provider_timeout_seconds)
            try:
                for model_settings, numbers in (
                    (old["settings"], (1,)),
                    (realtime_settings, (1, 2, 3)),
                ):
                    for number in numbers:
                        expected = {
                            1: "What's your name?",
                            2: "How old are you?",
                            3: "What do you do for work?",
                        }[number]
                        sample = next(BASELINE.rglob(f"q{number:02d}*.wav"))
                        check = {
                            "model": model_settings.get("model", "whisper"),
                            "question": expected,
                        }
                        checks.append(check)
                        started = time.monotonic()
                        try:
                            result = await transcribe(
                                client,
                                settings,
                                SimpleNamespace(settings=model_settings),
                                key,
                                sample.read_bytes(),
                                "en",
                                uuid4(),
                            )
                            check.update(
                                status="succeeded",
                                transcript=result["text"],
                                match=re.sub(r"\W", "", result["text"].lower())
                                == re.sub(r"\W", "", expected.lower()),
                            )
                        except Exception as error:  # noqa: BLE001 - redact all provider exceptions
                            check.update(
                                status="failed",
                                code=getattr(error, "code", type(error).__name__),
                            )
                        check["elapsed_ms"] = round((time.monotonic() - started) * 1000)
            finally:
                await client.close()
            if not all(row.get("match") for row in checks):
                raise RuntimeError(
                    "At least one live adapter audio check failed; see the saved result"
                )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify-audio",
        action="store_true",
        help="Also send four short synthetic clips to the production adapters",
    )
    args = parser.parse_args()
    output = (
        Path(__file__).parent
        / "results"
        / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    )
    output.mkdir(parents=True)
    evidence = {
        "passed": False,
        "active_profile_changed_by_script": False,
        "audio_via": "production adapters; separate provider verification, not PMS usage",
    }
    try:
        asyncio.run(run(args.verify_audio, evidence))
        evidence["passed"] = True
    except Exception as error:  # noqa: BLE001 - private credentials require redacted diagnostics
        # Never print provider messages, URLs, tokens, keys or exception tracebacks.
        evidence["error_type"] = type(error).__name__
    finally:
        (output / "registration.json").write_text(
            json.dumps(evidence, indent=2), encoding="utf-8"
        )
    print(json.dumps(evidence, indent=2))
    print(output / "registration.json")
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    raise SystemExit(main())
