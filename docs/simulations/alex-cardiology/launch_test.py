"""Launch the existing local demo and an instrumented desktop audio interview."""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUT = None
sys.path.insert(0, str(ROOT / "human-test/scripts"))

from demo import STATE, AlreadyRunning, Demo
from runtime_environment import desktop_environment


def database_snapshot(label):
    import psycopg
    from dotenv import dotenv_values

    config = json.loads((STATE / "config.json").read_text(encoding="utf-8"))
    values = dotenv_values(STATE / "pms.env")
    result = {
        "limits": {
            key: values.get(key, default)
            for key, default in {
                "PMS_LLM_DAILY_REQUESTS": "5000",
                "PMS_LLM_DAILY_TOTAL_TOKENS": "5000000",
                "PMS_LLM_CLOUD_CONCURRENCY": "4",
                "PMS_LLM_TIMEOUT_SECONDS": "120",
                "PMS_SPEECH_DAILY_SECONDS": "3600",
            }.items()
        }
    }
    with psycopg.connect(
        host="127.0.0.1",
        port=55444,
        dbname="human_test_demo",
        user="human_api",
        password=config["api_password"],
        connect_timeout=5,
        options="-c default_transaction_read_only=on -c statement_timeout=5000",
    ) as conn:
        row = conn.execute(
            """SELECT count(*),coalesce(sum(reserved_tokens),0),
            coalesce(sum(coalesce(charged_total_tokens,reserved_total_tokens)),0)
            FROM device_platform.llm_requests WHERE organization_id=%s
            AND reserved_total_tokens>0
            AND created_at >= date_trunc('day',now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'""",
            (config["organization_id"],),
        ).fetchone()
        result["today"] = {
            "llm_requests": row[0],
            "reserved_output_tokens": row[1],
            "charged_or_reserved_total_tokens": row[2],
        }
        result["today_errors"] = conn.execute(
            """SELECT status,error_code,count(*)
            FROM device_platform.llm_requests WHERE organization_id=%s
            AND created_at >= date_trunc('day',now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
            GROUP BY status,error_code ORDER BY status,error_code""",
            (config["organization_id"],),
        ).fetchall()
    (OUT / (label + "-database.json")).write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gap-seconds", type=float, default=1.0)
    parser.add_argument(
        "--mute",
        action="store_true",
        help="Disable answer playback for a faster service-only run",
    )
    args = parser.parse_args()
    if not 0 <= args.gap_seconds <= 60:
        parser.error("gap-seconds must be between zero and sixty")
    OUT = (
        HERE
        / "results"
        / datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d_%H-%M-%S_%f")
    )
    OUT.mkdir(parents=True, exist_ok=False)
    print("Results:", OUT, flush=True)
    demo = Demo(include_video=True, processing_mode="cloud")
    try:
        try:
            values = demo.start()
        except AlreadyRunning:
            demo.reuse_running()
            from dotenv import dotenv_values

            values = dotenv_values(STATE / "human.env")
        if (
            demo.route["audio"]["mode"] != "cloud"
            or demo.route["llm"]["mode"] != "cloud"
        ):
            raise RuntimeError(
                "Saved route is not fully online; no profile was changed"
            )
        database_snapshot("before")
        env = desktop_environment(values)
        env["PYTHONUNBUFFERED"] = "1"
        command = [
            ROOT / "human-test/.venv/Scripts/python.exe",
            "-X",
            "utf8",
            HERE / "run_interview.py",
            "--output",
            OUT,
            "--gap-seconds",
            str(args.gap_seconds),
        ]
        if args.mute:
            command.append("--mute")
        process = demo.launch(command, env)
        last = None
        while process.poll() is None:
            demo.check_children(ignore=process, monitored=True)
            demo.services.monitor()
            progress = OUT / "progress.json"
            if progress.exists():
                try:
                    value = json.loads(progress.read_text(encoding="utf-8"))
                    message = value.get("message")
                    if message != last:
                        print(message, flush=True)
                        last = message
                except (ValueError, OSError):
                    pass
            time.sleep(0.5)
        database_snapshot("after")
        print("Interview process exit:", process.returncode, flush=True)
        if process.returncode not in (0, 2):
            raise RuntimeError(
                "Interview driver failed; inspect its safe diagnostic artifact"
            )
        return process.returncode
    finally:
        demo.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - launcher cleanup owns all services
        print("Live test launcher failed:", type(exc).__name__, flush=True)
        raise SystemExit(1) from None
