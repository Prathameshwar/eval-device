"""Bounded local LLM transport shared by PMS JSON and streaming APIs."""

from .client import LLMClient, LLMError

__all__ = ["LLMClient", "LLMError"]
