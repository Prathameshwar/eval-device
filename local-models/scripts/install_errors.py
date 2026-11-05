"""Safe installer failure protocol; standard library only, no URLs or exception messages."""

import errno
import json
import re
import ssl
import traceback
import urllib.error
from pathlib import Path

HINTS = {
    "certificate_invalid": "Download certificate verification failed. Check Windows trusted certificates and network inspection settings.",
    "network_unavailable": "The download server could not be reached. Check network access to GitHub and ModelScope, then retry to resume.",
    "http_refused": "The download server refused the request. See the HTTP status in installer.log; check network access and retry.",
    "permission_denied": "Windows denied access to installation files. Use a writable local folder owned by your account.",
    "disk_space": "The installation ran out of disk space. Free space and retry to resume.",
    "asset_integrity_failed": "Downloaded files failed integrity verification. Retry the download; unverified files will not be installed.",
    "install_failed": "Installation did not finish. See installer.log for the failure category and trace.",
}
TRACE = re.compile(
    r"(?:exception=[A-Za-z][A-Za-z0-9_.]{0,79}|at [A-Za-z0-9_.-]{1,100}\.(?:py|pyx):\d{1,8} in [A-Za-z0-9_.<>]{1,80})"
)


def details(error):
    result = {"code": "install_failed", "trace": []}
    seen = set()
    while error is not None and id(error) not in seen and len(seen) < 6:
        seen.add(id(error))
        if getattr(error, "code", None) in HINTS:
            result["code"] = error.code
        kind = re.sub(r"[^A-Za-z0-9_.]", "_", type(error).__name__)[:80]
        result["trace"].append("exception=" + kind)
        for frame in traceback.extract_tb(error.__traceback__)[-12:]:
            name = Path(frame.filename).name
            line = f"at {name}:{frame.lineno} in {frame.name}"
            if TRACE.fullmatch(line):
                result["trace"].append(line)
        for key in ("errno", "winerror"):
            if isinstance(value := getattr(error, key, None), int):
                result[key] = value
        if isinstance(error, ssl.SSLCertVerificationError):
            result["code"] = "certificate_invalid"
        elif isinstance(error, PermissionError):
            result["code"] = "permission_denied"
        elif isinstance(error, OSError) and error.errno == errno.ENOSPC:
            result["code"] = "disk_space"
        elif isinstance(error, urllib.error.HTTPError):
            result.update(code="http_refused", http_status=error.code)
        elif result["code"] == "install_failed" and isinstance(error, (urllib.error.URLError, TimeoutError)):
            result["code"] = "network_unavailable"
        elif isinstance(error, ValueError) and any(
            word in str(error).lower() for word in ("sha-256", "sha256", "integrity")
        ):
            result["code"] = "asset_integrity_failed"
        reason = getattr(error, "reason", None)
        error = reason if isinstance(reason, BaseException) else error.__cause__ or error.__context__
    result["trace"] = result["trace"][-48:]
    return result


def report(error):
    value = details(error)
    # One bounded protocol line must survive pipe chunking on both installer levels.
    while len(json.dumps(value)) > 4000 and value["trace"]:
        value["trace"].pop(0)
    print("INSTALL_DIAGNOSTIC:" + json.dumps(value), flush=True)


def parse(line):
    if not line.startswith("INSTALL_DIAGNOSTIC:") or len(line) > 8192:
        return None
    try:
        value = json.loads(line.removeprefix("INSTALL_DIAGNOSTIC:"))
        if not isinstance(value, dict) or value.get("code") not in HINTS:
            return None
        trace = value.get("trace", [])
        if not isinstance(trace, list):
            return None
        result = {
            "code": value["code"],
            "trace": [item for item in trace[:48] if isinstance(item, str) and TRACE.fullmatch(item)],
        }
        for key in ("errno", "winerror", "http_status", "exit_code"):
            if isinstance(number := value.get(key), int) and abs(number) <= 2**32:
                result[key] = number
        return result
    except (ValueError, TypeError, RecursionError):
        return None
