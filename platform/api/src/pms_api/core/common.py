import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, TypeVar
from uuid import UUID


def now() -> datetime:
    return datetime.now(timezone.utc)


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def token_hash(token: str, pepper: str) -> str:
    return hmac.new(pepper.encode(), token.encode(), hashlib.sha256).hexdigest()


def new_token(prefix: str) -> str:
    return prefix + secrets.token_urlsafe(32)


@dataclass
class AppError(Exception):
    status: int
    code: str
    message: str
    details: Any = None


def require(condition: object, code: str, message: str, status: int = 422) -> None:
    if not condition:
        raise AppError(status, code, message)


def json_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: json_values(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_values(v) for v in value]
    if isinstance(value, (UUID, datetime)):
        return str(value)
    return value


T = TypeVar("T")


def required(value: T | None) -> T:
    if value is None:
        raise AppError(404, "not_found", "Record not found")
    return value
