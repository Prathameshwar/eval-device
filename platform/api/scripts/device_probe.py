"""Laptop/Pi HTTP probe. Uses an enrolled device token from the local environment."""

import argparse
import os
from uuid import uuid4

import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://127.0.0.1:8000")
args = parser.parse_args()
token = os.environ["PMS_DEVICE_TOKEN"]
with httpx.Client(base_url=args.url, headers={"Authorization": "Bearer " + token}, timeout=20) as client:
    config = client.get("/api/v1/device/config")
    config.raise_for_status()
    value = config.json()
    print(
        "Configuration received:",
        value["device_id"],
        "active=",
        value["is_active"],
        "language=",
        value.get("effective_language", "en"),
    )
    response = client.post(
        "/api/v1/device/heartbeat",
        json={"boot_id": str(uuid4()), "sequence_number": 0, "metrics": {"uptime_seconds": 0}},
    )
    response.raise_for_status()
    print("Heartbeat accepted. Apply local engines/settings before sending a configuration acknowledgment.")
