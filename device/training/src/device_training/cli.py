import argparse
import os
import secrets
import subprocess
from pathlib import Path

import uvicorn
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from training_contracts.privacy import no_link, private_directory


def keys(directory):
    directory = directory.absolute()
    for parent in (*reversed(directory.parents), directory):
        if parent.exists():
            no_link(parent)
    directory.mkdir(parents=True, exist_ok=True)
    if list(directory.iterdir()):
        raise ValueError("key directory must be new and empty")
    private_directory(directory)
    key = Ed25519PrivateKey.generate()
    (directory / "training-private.pem").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
    (directory / "training-public.pem").write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    (directory / "model.key").write_text(secrets.token_urlsafe(48), encoding="ascii")


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    key = commands.add_parser("keys")
    key.add_argument("--directory", type=Path, required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8767)
    serve.add_argument("--cert", type=Path)
    serve.add_argument("--key", type=Path)
    model = commands.add_parser("model")
    model.add_argument("--executable", type=Path, required=True)
    model.add_argument("--model", type=Path, required=True)
    model.add_argument("--key-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "keys":
            keys(args.directory)
            print(
                "Private signing/model keys and a public verification key created. Keep private keys on the laptop/platform only."
            )
        elif args.command == "serve":
            if bool(args.cert) != bool(args.key) or (args.host not in {"127.0.0.1", "::1"} and not args.cert):
                raise ValueError("Wi-Fi requires a TLS certificate and key")
            from .app import create_app

            uvicorn.run(
                create_app(),
                host=args.host,
                port=args.port,
                ssl_certfile=str(args.cert) if args.cert else None,
                ssl_keyfile=str(args.key) if args.key else None,
                access_log=False,
                proxy_headers=False,
                ws_max_size=524308,
                ws_max_queue=4,
                limit_concurrency=32,
            )
        else:
            for path in (args.executable, args.model, args.key_file):
                no_link(path)
            if not 32 <= len(args.key_file.read_text().strip()) <= 256:
                raise ValueError("invalid model key")
            command = [
                str(args.executable.resolve()),
                "--model",
                str(args.model.resolve()),
                "--alias",
                "qwen3-1.7b",
                "--host",
                "127.0.0.1",
                "--port",
                "8780",
                "--ctx-size",
                "4096",
                "--threads",
                "4",
                "--threads-batch",
                "4",
                "--parallel",
                "1",
                "--jinja",
                "--no-webui",
                "--api-key-file",
                str(args.key_file.resolve()),
                "--cors-origins",
                "http://model.invalid",
                "--no-cors-credentials",
                "--log-disable",
            ]
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=0x08000000 if os.name == "nt" else 0,
            )
            try:
                print(
                    "Local model service starting on loopback port 8780; weights remain loaded until stopped."
                )
                if process.wait():
                    raise RuntimeError("model_service_failed")
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
    except KeyboardInterrupt:
        pass
    except Exception:
        parser.exit(
            1,
            "Training service failed. Check private configuration and service status; sensitive values are not logged.\n",
        )
