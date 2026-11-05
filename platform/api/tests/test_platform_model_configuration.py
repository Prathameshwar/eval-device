import json
from types import SimpleNamespace

import httpx
import pytest

from pms_api.core.common import AppError
from pms_api.integrations.llm.client import LLMClient, LLMError
from pms_api.integrations.llm.policy import endpoint
from pms_api.modules.platform_models import (
    cloud_endpoint,
    key_value,
)


def test_cloud_endpoint_is_allowlisted_and_key_is_header_safe():
    settings = SimpleNamespace(
        llm_allowed_ports=[8787],
        llm_allowed_base_urls=["https://api.openai.com/v1", "https://api.anthropic.com/v1"],
    )
    assert (
        cloud_endpoint("anthropic", "https://api.anthropic.com/v1", settings)
        == "https://api.anthropic.com/v1"
    )
    for value in ("http://api.anthropic.com/v1", "https://attacker.example/v1"):
        with pytest.raises(AppError):
            endpoint(value, [], "anthropic", settings.llm_allowed_base_urls)
    from pydantic import SecretStr

    with pytest.raises(AppError):
        key_value(SecretStr("bad\nkey"))


@pytest.mark.parametrize("streaming", [False, True])
async def test_anthropic_native_messages_contract(streaming):
    calls = []

    def handler(request):
        calls.append(request)
        if streaming:
            events = [
                {"type": "message_start", "message": {"usage": {"input_tokens": 8, "output_tokens": 1}}},
                {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "OK"}},
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn"},
                    "usage": {"output_tokens": 2},
                },
                {"type": "message_stop"},
            ]
            return httpx.Response(
                200, content="".join("data: " + json.dumps(item) + "\n\n" for item in events)
            )
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "OK"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 8, "output_tokens": 2},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        events = [
            item
            async for item in LLMClient(client=http).events(
                base_url="https://api.anthropic.com/v1",
                provider="anthropic",
                model="claude-test",
                key="secret",
                max_tokens=64,
                streaming=streaming,
                messages=[{"role": "system", "content": "Be brief"}, {"role": "user", "content": "Hi"}],
            )
        ]
    assert len(calls) == 1
    assert str(calls[0].url) == "https://api.anthropic.com/v1/messages"
    assert calls[0].headers["x-api-key"] == "secret"
    assert calls[0].headers["anthropic-version"] == "2023-06-01"
    assert "authorization" not in calls[0].headers
    payload = json.loads(calls[0].content)
    assert payload["system"] == "Be brief"
    assert payload["messages"] == [{"role": "user", "content": "Hi"}]
    assert payload["max_tokens"] == 64 and payload["stream"] == streaming
    assert events[-1]["text"] == "OK"
    assert events[-1]["usage"] == {"prompt_tokens": 8, "completion_tokens": 2, "total_tokens": 10}


async def test_anthropic_submission_error_is_not_replayed():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(529, json={"error": {"type": "overloaded_error"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(LLMError) as failure:
            await LLMClient(client=http).complete(
                base_url="https://api.anthropic.com/v1",
                provider="anthropic",
                model="claude-test",
                key="secret",
                max_tokens=64,
                messages=[{"role": "user", "content": "Hi"}],
            )
    assert failure.value.code == "llm_busy" and len(calls) == 1
