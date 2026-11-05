"""Operator CLI for the detached manager; Windows service registration is queued."""

import argparse
import json
import sys

from desktop.manager_client import Client
from service.errors import ManagerError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("connect", "status", "shutdown"))
    args = parser.parse_args()
    client = Client()
    try:
        if args.command == "connect":
            result = client.connect()
        elif args.command == "shutdown":
            result = client.request("POST", "/v1/shutdown", {})
        else:
            result = client.request("GET", "/v1/status")
        print(json.dumps(result, indent=2))
    except ManagerError as error:
        print(error.message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
