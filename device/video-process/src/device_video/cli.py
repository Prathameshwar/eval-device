import argparse
import json
import logging
import secrets
from pathlib import Path

import uvicorn

from .config import Settings
from .privacy import no_link, private_directory


def init_local() -> None:
    path = Path(".env")
    for parent in reversed(path.absolute().parents):
        no_link(parent)
    # Exclusively create, restrict access before writing any credential bytes.
    with path.open("x", encoding="utf-8") as target:
        private_directory(path)
        target.write(
            "# Private local video client credentials; do not commit or log.\n"
            f"VIDEO_CLIENT_TOKENS='{json.dumps({'pi-1': secrets.token_urlsafe(32)})}'\n"
            "VIDEO_HOST=127.0.0.1\nVIDEO_PORT=8766\n"
            "VIDEO_RECORDING_DIR=.recordings\nVIDEO_RECORDING_MAX_BYTES=1000000000\n"
            "VIDEO_RETENTION_HOURS=168\nVIDEO_MAX_WIDTH=1280\nVIDEO_MAX_HEIGHT=720\n"
            "VIDEO_MAX_FPS=15\nVIDEO_SEGMENT_SECONDS=2\n"
            "# Wi-Fi requires a trusted TLS certificate and key before binding 0.0.0.0.\n"
            "# VIDEO_TLS_CERT=path/to/server-cert.pem\n# VIDEO_TLS_KEY=path/to/server-key.pem\n"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Standalone video recording and offline frame extraction")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-local", help="create private credentials without overwriting .env")
    commands.add_parser("serve", help="run the standalone receive-and-record API")
    extract = commands.add_parser(
        "extract-frames", help="extract JPEGs offline; stop the recording API first"
    )
    extract.add_argument("--recording-id", required=True)
    extract.add_argument("--output", type=Path, required=True)
    extract.add_argument("--every", type=int, default=10, help="select every Nth frame")
    extract.add_argument("--max-frames", type=int, default=1000)
    extract.add_argument("--max-bytes", type=int, default=268435456)
    args = parser.parse_args()
    if args.command == "init-local":
        try:
            init_local()
        except FileExistsError:
            parser.exit(1, ".env already exists; it was not overwritten.\n")
        except Exception:
            parser.exit(1, "Could not create private settings. Check directory permissions.\n")
        print("Created private .env; client token was not printed. No model is needed.")
        return
    try:
        settings = Settings()
    except ValueError:
        parser.exit(1, "Invalid VIDEO_* settings; check .env and README.\n")
    if args.command == "extract-frames":
        from .extract import extract_frames

        try:
            result = extract_frames(
                settings,
                args.recording_id,
                args.output,
                every=args.every,
                max_frames=args.max_frames,
                max_bytes=args.max_bytes,
            )
        except Exception:
            parser.exit(1, "Extraction failed. Stop the API, check recording integrity, limits and paths.\n")
        print(json.dumps(result))
        return
    from .app import create_app

    # Suppress connection/access logs: untrusted request URLs can contain private text.
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        workers=1,
        ws="websockets",
        ws_max_size=settings.max_frame_bytes + 20,
        ws_max_queue=2,
        ws_per_message_deflate=False,
        proxy_headers=False,
        access_log=False,
        log_level="warning",
        timeout_graceful_shutdown=10,
        ssl_certfile=str(settings.tls_cert) if settings.tls_cert else None,
        ssl_keyfile=str(settings.tls_key) if settings.tls_key else None,
    )


if __name__ == "__main__":
    main()
