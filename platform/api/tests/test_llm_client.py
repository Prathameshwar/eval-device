import asyncio
import json

import httpx
import pytest

from pms_api.core.common import AppError
from pms_api.integrations.llm.client import LLMClient, LLMError, endpoint

ARGS = {
    "base_url": "http://127.0.0.1:8787",
    "model": "qwen3-4b-local",
    "key": "private-fixture",
    "messages": [{"role": "user", "content": "hello"}],
    "max_tokens": 32,
}


async def test_stream_response_closes_suspended_generator_on_disconnect():
    from pms_api.modules.llm import LLMStreamingResponse

    first_sent = asyncio.Event()
    closed = []

    async def content():
        try:
            yield "data: first\n\n"
            await asyncio.sleep(60)
        finally:
            import anyio

            with anyio.CancelScope(shield=True):
                await asyncio.sleep(0.01)
                closed.append(True)

    async def send(message):
        if message["type"] == "http.response.body":
            first_sent.set()

    async def receive():
        await first_sent.wait()
        return {"type": "http.disconnect"}

    async with asyncio.timeout(2):
        await LLMStreamingResponse(content())(
            {"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send
        )
    assert closed == [True]


class Chunks(httpx.AsyncByteStream):
    def __init__(self, chunks, delay=0):
        self.chunks, self.delay, self.closed = chunks, delay, False

    async def __aiter__(self):
        for chunk in self.chunks:
            await asyncio.sleep(self.delay)
            yield chunk

    async def aclose(self):
        self.closed = True


def wire(text="hello", finish="stop"):
    return (
        "data: "
        + json.dumps({"choices": [{"delta": {"content": text}, "finish_reason": finish}]}, ensure_ascii=False)
        + "\n\ndata: [DONE]\n\n"
    ).encode()


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://localhost:8787",
        "http://127.0.0.1:8000",
        "http://user@127.0.0.1:8787",
        "http://127.0.0.1:8787/?key=x",
        "http://127.0.0.1:8787/v1",
        "http://127.0.0.1:8787#x",
    ],
)
def test_endpoint_allowlist(url):
    with pytest.raises(AppError):
        endpoint(url, [8787])


async def test_json_and_split_unicode_sse():
    answer = "\u0928\u092e\u0938\u094d\u0924\u0947"
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        if body["stream"]:
            data = wire(answer)
            return httpx.Response(200, stream=Chunks([bytes([b]) for b in data]))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": answer}, "finish_reason": "stop"}],
                "usage": {"completion_tokens": 3},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = LLMClient(client=http)
        result = await client.complete(**ARGS)
        events = [x async for x in client.stream(**ARGS)]
    assert result["text"] == events[-1]["text"] == answer
    assert events[0]["type"] == "delta" and events[-1]["type"] == "done"
    assert not calls[0]["stream"] and calls[1]["stream"]
    assert all(not c["chat_template_kwargs"]["enable_thinking"] for c in calls)


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"data: [DONE]\n",
        b"data: []\n",
        b'data: {"choices":null}\n',
        b"data: " + b"x" * 65537,
        b'data: {"choices":[{"delta":{"content":123}}]}\n',
    ],
    ids=["empty", "done-without-finish", "array", "null-choices", "oversized", "non-text"],
)
async def test_invalid_or_truncated_sse_never_retried(data):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, stream=Chunks([data]))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(LLMError):
            _ = [x async for x in LLMClient(client=http).stream(**ARGS)]
    assert len(calls) == 1


@pytest.mark.parametrize("status", [307, 401, 429, 500])
async def test_failure_and_redirect_do_not_replay(status):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(
            status, headers={"Location": "http://example.invalid"}, content=b"secret-provider-error"
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(LLMError) as error:
            await LLMClient(client=http).complete(**ARGS)
    assert len(calls) == 1 and "secret" not in str(error.value)


async def test_deadline_closes_slow_stream():
    body = Chunks([b":"] * 50, 0.02)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=body))
    ) as http:
        with pytest.raises(LLMError) as error:
            _ = [e async for e in LLMClient(timeout=0.1, client=http).stream(**ARGS)]
    assert error.value.code == "llm_timeout" and body.closed


async def test_cancel_closes_upstream():
    body = Chunks([b":"] * 50, 0.02)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=body))
    ) as http:

        async def consume():
            return [e async for e in LLMClient(client=http).stream(**ARGS)]

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert body.closed


@pytest.mark.parametrize(
    "provider,disable,expected",
    [
        # A local server always renders with thinking off; the flag is not its business.
        ("local_llama_cpp", False, {"enable_thinking": False}),
        ("local_llama_cpp", True, {"enable_thinking": False}),
        # A remote provider is left at its own default unless the model has been measured
        # with thinking off. Switching it on is one explicit, provider-generic key.
        ("openai_compatible", False, None),
        ("openai_compatible", True, {"enable_thinking": False}),
        ("azure_openai", True, {"enable_thinking": False}),
    ],
)
async def test_thinking_control_is_explicit_and_provider_generic(provider, disable, expected):
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = LLMClient(client=http)
        await client.complete(**{**ARGS, "provider": provider, "disable_thinking": disable})
    assert calls[0].get("chat_template_kwargs") == expected
