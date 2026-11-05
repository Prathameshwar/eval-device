"""Explicit live Azure probe; read-only credential lookup, synthetic audio, no retries."""

import argparse
import asyncio
import base64
import json
import os
import re
import sys
import time
import wave
from array import array
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import psycopg
from pms_api.core.config import Settings
from pms_api.integrations.vault import CredentialVault
from psycopg.rows import dict_row
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
HOST = "aiforce-openai.openai.azure.com"
MODEL = "gpt-realtime-whisper"
BASELINE = ROOT / "docs/simulations/alex-cardiology/results/2026-09-20_14-24-53_409810"


def credential():
    state = ROOT / "human-test/.local/demo"
    config = json.loads((state / "config.json").read_text(encoding="utf-8"))
    if config.get("purpose") != "isolated-human-test-v1":
        raise RuntimeError("Expected the isolated demo configuration")
    for name in list(os.environ):
        if name.startswith("PMS_"):
            del os.environ[name]
    settings = Settings(_env_file=state / "pms.env")
    with psycopg.connect(
        host="127.0.0.1",
        port=55444,
        dbname="human_test_demo",
        user="human_api",
        password=config["api_password"],
        connect_timeout=5,
        row_factory=dict_row,
        options="-c default_transaction_read_only=on -c statement_timeout=5000",
    ) as db:
        candidates = db.execute(
            "SELECT id,organization_id,settings,encrypted_credentials,credential_key_id "
            "FROM device_platform.provider_connections WHERE organization_id=%s "
            "AND is_active AND connection_type='azure_openai_whisper'",
            (config["organization_id"],),
        ).fetchall()
    candidates = [
        row
        for row in candidates
        if urlsplit(row["settings"].get("endpoint", "")).hostname == HOST
        and row["settings"].get("model", "whisper") == "whisper"
    ]
    if len(candidates) != 1:
        raise RuntimeError(
            "Expected one active Whisper connection for the supplied Azure resource"
        )
    row = candidates[0]
    return CredentialVault(settings).decrypt(SimpleNamespace(**row))["api_key"]


def pcm24(path):
    with wave.open(str(path), "rb") as wav:
        if (
            wav.getnchannels() != 1
            or wav.getsampwidth() != 2
            or wav.getcomptype() != "NONE"
        ):
            raise ValueError("Expected mono PCM16 input")
        rate = wav.getframerate()
        if rate not in (16000, 24000) or not 0 < wav.getnframes() / rate <= 30:
            raise ValueError("Expected a bounded 16/24 kHz fixture")
        samples = array("h", wav.readframes(wav.getnframes()))
    if sys.byteorder != "little":
        samples.byteswap()
    output = array("h")
    for index in range(round(len(samples) * 24000 / rate)):
        left, fraction = divmod(index * rate, 24000)
        right = min(left + 1, len(samples) - 1)
        output.append(
            round(
                (samples[left] * (24000 - fraction) + samples[right] * fraction) / 24000
            )
        )
    if sys.byteorder != "little":
        output.byteswap()
    return output.tobytes()


def safe_error(error, key):
    return {
        name: str(error[name]).replace(key, "[redacted]")[:600]
        for name in ("code", "type", "message", "param")
        if error.get(name) is not None
    }


async def receive(ws, evidence, key, wanted):
    async with asyncio.timeout(25):
        for _ in range(300):
            event = json.loads(await ws.recv())
            kind = event.get("type", "unknown")
            entry = {
                "type": kind,
                "elapsed_ms": round((time.monotonic() - evidence["_start"]) * 1000),
            }
            if kind in {"session.created", "session.updated"}:
                session = event.get("session", {})
                entry["session_type"] = session.get("type")
                entry["transcription"] = (
                    session.get("audio", {}).get("input", {}).get("transcription")
                )
            if kind.endswith((".delta", ".completed")):
                for name in ("item_id", "delta", "transcript"):
                    if isinstance(event.get(name), str):
                        entry[name] = event[name][:8000]
            if kind == "error" or kind.endswith(".failed"):
                entry["error"] = safe_error(event.get("error", {}), key)
            evidence["events"].append(entry)
            if "error" in entry:
                raise RuntimeError("Provider rejected the event; see redacted evidence")
            if kind in wanted:
                return event
    raise RuntimeError("Too many events without the expected result")


async def probe(query, key, samples):
    evidence = {"query": query, "events": [], "samples": [], "_start": time.monotonic()}
    try:
        async with connect(
            f"wss://{HOST}/openai/v1/realtime?{query}",
            additional_headers={"api-key": key},
            proxy=None,
            open_timeout=15,
            close_timeout=5,
            max_size=1024 * 1024,
            max_queue=32,
        ) as ws:
            evidence["websocket_connected"] = True
            await ws.send(
                json.dumps(
                    {
                        "type": "session.update",
                        "session": {
                            "type": "transcription",
                            "audio": {
                                "input": {
                                    "format": {"type": "audio/pcm", "rate": 24000},
                                    "turn_detection": None,
                                    "transcription": {
                                        "model": MODEL,
                                        "language": "en",
                                        "delay": "low",
                                    },
                                }
                            },
                        },
                    }
                )
            )
            await receive(ws, evidence, key, {"session.updated"})
            evidence["session_configured"] = True
            for number, expected, pcm in samples:
                record = {
                    "number": number,
                    "expected": expected,
                    "audio_seconds": round(len(pcm) / 48000, 3),
                }
                evidence["samples"].append(record)
                start = time.monotonic()
                offset = len(evidence["events"])
                result_task = asyncio.create_task(
                    receive(
                        ws,
                        evidence,
                        key,
                        {"conversation.item.input_audio_transcription.completed"},
                    )
                )
                try:
                    for position in range(0, len(pcm), 4800):
                        await ws.send(
                            json.dumps(
                                {
                                    "type": "input_audio_buffer.append",
                                    "audio": base64.b64encode(
                                        pcm[position : position + 4800]
                                    ).decode("ascii"),
                                }
                            )
                        )
                        await asyncio.sleep(min(4800, len(pcm) - position) / 48000)
                    record["audio_sent_ms"] = round((time.monotonic() - start) * 1000)
                    await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
                    committed = time.monotonic()
                    final = await result_task
                    record["final_after_commit_ms"] = round(
                        (time.monotonic() - committed) * 1000
                    )
                    record["transcript"] = final.get("transcript", "")[:8000]
                    normalize = lambda value: re.sub(
                        r"[^a-z0-9]+", "", value.casefold()
                    )
                    record["matches_expected"] = normalize(
                        record["transcript"]
                    ) == normalize(expected)
                    deltas = [
                        row
                        for row in evidence["events"][offset:]
                        if row["type"].endswith(".delta")
                    ]
                    if deltas:
                        record["first_delta_ms"] = round(
                            deltas[0]["elapsed_ms"]
                            - (start - evidence["_start"]) * 1000
                        )
                    print(json.dumps(record), flush=True)
                finally:
                    if not result_task.done():
                        result_task.cancel()
                    await asyncio.gather(result_task, return_exceptions=True)
            evidence["status"] = "succeeded"
    except InvalidStatus as error:
        evidence["status"] = "handshake_rejected"
        evidence["http_status"] = error.response.status_code
        try:
            body = json.loads(error.response.body)
            evidence["error"] = safe_error(body.get("error", body), key)
        except (ValueError, TypeError, AttributeError):
            pass
    except Exception as error:  # noqa: BLE001 - Keep credentials out of exception traces.
        evidence["status"] = "failed"
        evidence["exception_type"] = type(error).__name__
    evidence["elapsed_ms"] = round((time.monotonic() - evidence.pop("_start")) * 1000)
    return evidence


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configure-only", action="store_true")
    args = parser.parse_args()
    output = HERE / "results" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    output.mkdir(parents=True)
    key = credential()
    questions = json.loads(
        (ROOT / "docs/simulations/alex-cardiology/questions.json").read_text(
            encoding="utf-8"
        )
    )
    samples = (
        []
        if args.configure_only
        else [
            (
                q["number"],
                q["question"],
                pcm24(BASELINE / "inputs" / f"q{q['number']:02d}.wav"),
            )
            for q in questions[:3]
        ]
    )
    report = {
        "model": MODEL,
        "host": HOST,
        "credential_source": "existing encrypted Whisper connection",
        "probes": [],
    }
    # The supplied URL is checked without sending audio. The documented intent
    # flow is a separate compatibility check, not a replay of an uncertain turn.
    for query, audio in [(f"model={MODEL}", []), ("intent=transcription", samples)]:
        result = await probe(query, key, audio)
        report["probes"].append(result)
        (output / "result.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "query": query,
                    "status": result["status"],
                    "http_status": result.get("http_status"),
                }
            ),
            flush=True,
        )
    print("Evidence: " + str(output / "result.json"))
    verified = report["probes"][-1]
    return (
        0
        if verified["status"] == "succeeded"
        and all(sample.get("matches_expected") for sample in verified["samples"])
        else 2
    )


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as error:  # noqa: BLE001 - Never print credentials through a traceback.
        print("Probe stopped safely: " + type(error).__name__, file=sys.stderr)
        raise SystemExit(1) from None
