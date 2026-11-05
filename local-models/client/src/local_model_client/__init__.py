"""Inference-only client. Never installs, provisions or starts model services."""

from .connection import Connection, ConnectionError, catalogue, client_key, configure

__all__ = ["Connection", "ConnectionError", "client_key", "configure", "catalogue"]
