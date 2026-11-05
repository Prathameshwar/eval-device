import argparse
import asyncio
import getpass
import json
import sys
from pathlib import Path

from training_client.connection import PairingClient

from .config import load, private_dir
from .control import send
from .diagnostics import audio_devices, inspect
from .service import Service


def main():
    parser = argparse.ArgumentParser(description="Headless patient training device")
    parser.add_argument("--config", type=Path, default=Path("/etc/pi-test/config.toml"))
    commands = parser.add_subparsers(dest="command", required=True)
    for command in (
        "serve",
        "status",
        "doctor",
        "audio-devices",
        "scenarios",
        "listen",
        "pause",
        "finish",
        "camera-start",
        "camera-stop",
        "camera-stream",
        "camera-process",
        "probe",
        "result",
        "resume",
        "send-now",
        "reload",
        "config-check",
        "processing-requests",
        "inference-requests",
        "shutdown",
    ):
        commands.add_parser(command)
    begin = commands.add_parser("begin")
    begin.add_argument("--scenario")
    status = commands.add_parser("inference-status")
    status.add_argument("--request-id", required=True)
    processing = commands.add_parser("processing-status")
    processing.add_argument("--run-id", required=True)
    commands.add_parser("text", help="Read one question from standard input")
    enroll = commands.add_parser("enroll")
    enroll.add_argument("--device", required=True)
    args = parser.parse_args()
    try:
        settings = load(args.config, credentials=args.command != "enroll")
        if args.command == "serve":
            asyncio.run(Service(settings).run())
            return
        if args.command == "enroll":
            private_dir(settings.app_root)
            client = PairingClient(settings.pms_url, path=settings.app_root / "connection.json")
            try:
                client.pair(args.device, getpass.getpass("Enrollment token: "))
            finally:
                client.close()
            print("Enrollment saved. Restart the service to load this identity.")
            return
        if args.command == "config-check":
            result = {"valid": True, "capture_on_boot": False}
        elif args.command == "doctor":
            result = inspect(settings)
        elif args.command == "audio-devices":
            result = audio_devices()
        else:
            request = {"command": args.command}
            if args.command == "begin" and args.scenario:
                request["scenario"] = args.scenario
            if args.command == "inference-status":
                request["request_id"] = args.request_id
            if args.command == "processing-status":
                request["run_id"] = args.run_id
            if args.command == "text":
                # Include a possible terminal CRLF and one overflow character.
                text = sys.stdin.read(8003).removesuffix("\n").removesuffix("\r")
                if len(text) > 8000:
                    raise ValueError("Question exceeds 8,000 characters")
                request["text"] = text.strip()
            result = asyncio.run(send(settings.control_dir, request))
        print(json.dumps(result, indent=2))
        if isinstance(result, dict) and result.get("ok") is False:
            raise SystemExit(1)
    except (Exception, KeyboardInterrupt) as error:
        print(
            "Command failed: " + type(error).__name__ + ". Check configuration and service status.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
