import argparse
import tomllib
from pathlib import Path

import uvicorn

from .app import Settings, create_app


def main():
    parser = argparse.ArgumentParser(description="TLS inference gateway; never exposes manager operations")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--cert", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8791)
    args = parser.parse_args()
    with args.config.open("rb") as source:
        settings = Settings(**tomllib.load(source))
    uvicorn.run(
        create_app(settings),
        host=args.bind,
        port=args.port,
        ssl_certfile=str(args.cert),
        ssl_keyfile=str(args.key),
        access_log=False,
        ws_max_size=1100000,
        ws_max_queue=4,
        limit_concurrency=32,
        timeout_keep_alive=5,
        timeout_graceful_shutdown=10,
    )


if __name__ == "__main__":
    main()
