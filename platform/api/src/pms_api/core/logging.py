"""Structured operational logs; never log headers, bodies, credentials or signed URLs."""

import json
import logging
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    def format(self, record):
        value = {
            "time": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
        }
        try:
            message = json.loads(record.getMessage())
            value.update(message if isinstance(message, dict) else {"event": str(message)})
        except (ValueError, TypeError):
            value["event"] = record.getMessage()
        for key in ("run_id", "error_code", "error_type"):
            if hasattr(record, key):
                value[key] = getattr(record, key)
        return json.dumps(value)


def configure_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    # SDK debug/HTTP logs may expose signed URLs or credentials.
    for name in ("httpx", "httpcore", "botocore", "boto3", "azure", "sqlalchemy.engine"):
        logging.getLogger(name).setLevel(logging.WARNING)
