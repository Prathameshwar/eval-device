import asyncio
import json
import socket
import ssl

import httpcore
import httpx
import pytest
from pydantic import ValidationError

from pms_api.core.common import AppError
from pms_api.integrations.llm.client import LLMClient, LLMError, usage
from pms_api.integrations.llm.policy import endpoint
from pms_api.integrations.llm.transport import GuardedTransport, PublicNetwork
from pms_api.modules.llm_schemas import ConnectionCreate


@pytest.mark.parametrize(
    "provider,token_parameter,stream_usage",
    [
        ("openai", "max_completion_tokens", True),
        ("openai_compatible", "max_tokens", False),
        ("openai_compatible", "max_completion_tokens", True),
    ],
)
@pytest.mark.parametrize("streaming", [False, True])
async def test_provider_wire_contract_and_usage(provider, token_parameter, stream_usage, streaming):
    calls = []
    token_usage = {
        "prompt_tokens": 20,
        "completion_tokens": 10,
        "total_tokens": 30,
        "prompt_tokens_details": {"cached_tokens": 4},
        "completion_tokens_details": {"reasoning_tokens": 7},
    }

    def handler(request):
        calls.append(request)
        if streaming:
            events = [
                {
                    "choices": [{"delta": {"role": "assistant", "content": ""}, "finish_reason": None}],
                    "usage": None,
                },
                {"choices": [{"delta": {"content": "Hello"}, "finish_reason": None}], "usage": None},
                {"choices": [{"delta": {}, "finish_reason": "stop"}], "usage": None},
                {"choices": [], "usage": token_usage},
            ]
            if not stream_usage:
                events.pop()
            wire = (
                "".join("data: " + json.dumps(event) + "\r\n\r\n" for event in events)
                + "data: [DONE]\r\n\r\n"
            )
            return httpx.Response(200, content=wire)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Hello"}, "finish_reason": "stop"}],
                "usage": token_usage,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        events = [
            e
            async for e in LLMClient(client=http).events(
                base_url="https://api.openai.com/v1",
                provider=provider,
                model="configured-model",
                key="sk-proj-" + ("x" * 600),
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=1024,
                token_parameter=token_parameter,
                stream_usage=stream_usage,
                streaming=streaming,
                request_id="d5f4ec14-3ab7-44d1-aea6-1b6e7a4c8f25",
            )
        ]
    assert len(calls) == 1
    request = calls[0]
    body = json.loads(request.content)
    assert str(request.url) == "https://api.openai.com/v1/chat/completions"
    assert body[token_parameter] == 1024
    assert ("max_tokens" in body) != ("max_completion_tokens" in body)
    assert not {"temperature", "seed", "chat_template_kwargs"} & body.keys()
    assert ("stream_options" in body) == (streaming and stream_usage)
    assert ("store" in body) == (provider == "openai")
    assert provider != "openai" or body["store"] is False
    assert request.headers["authorization"] == "Bearer sk-proj-" + ("x" * 600)
    assert request.headers["x-client-request-id"] == "d5f4ec14-3ab7-44d1-aea6-1b6e7a4c8f25"
    assert events[-1]["text"] == "Hello"
    assert events[-1]["usage"] == (None if streaming and not stream_usage else token_usage)


@pytest.mark.parametrize(
    "value",
    [
        {"completion_tokens": True},
        {"prompt_tokens": -1},
        {"total_tokens": "10"},
        {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 10},
        {"completion_tokens_details": {"reasoning_tokens": -1}},
        {"completion_tokens_details": {"reasoning_tokens": True}},
        {"prompt_tokens_details": {"cached_tokens": 1000001}},
        {"prompt_tokens_details": []},
    ],
)
def test_invalid_token_usage(value):
    with pytest.raises(LLMError):
        usage(value)


def test_missing_usage_is_unknown_and_reasoning_is_not_added_twice():
    assert usage(None) is None and usage({}) is None
    counts = {
        "prompt_tokens": 7,
        "completion_tokens": 4,
        "total_tokens": 11,
        "completion_tokens_details": {"reasoning_tokens": 3},
    }
    assert usage(counts) == counts


@pytest.mark.parametrize("streaming", [False, True])
async def test_inconsistent_optional_usage_preserves_completed_answer(streaming):
    counts = {
        "prompt_tokens": 750,
        "completion_tokens": 366,
        "total_tokens": 1116,
        "completion_tokens_details": {"reasoning_tokens": 394},
        "prompt_tokens_details": {"cached_tokens": 751},
    }
    answer = (
        "\u092e\u0947\u0930\u093e \u0928\u093e\u092e \u090f\u0932\u0947\u0915\u094d\u0938 \u0939\u0948\u0964"
    )

    def handler(request):
        if streaming:
            events = [
                {"choices": [{"delta": {"content": answer}, "finish_reason": "stop"}]},
                {"choices": [], "usage": counts},
            ]
            return httpx.Response(
                200, content="".join("data: " + json.dumps(e) + "\n\n" for e in events) + "data: [DONE]\n\n"
            )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": answer}, "finish_reason": "stop"}],
                "usage": counts,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        events = [
            event
            async for event in LLMClient(client=http).events(
                base_url="https://fixture.example/v1",
                provider="openai_compatible",
                model="nemotron",
                key="fixture",
                messages=[{"role": "user", "content": "Name?"}],
                max_tokens=1024,
                streaming=streaming,
            )
        ]
    assert events[-1]["text"] == answer
    assert events[-1]["usage"] == {"prompt_tokens": 750, "completion_tokens": 366, "total_tokens": 1116}


@pytest.mark.parametrize(
    "content,reason,refusal,code",
    [
        ("", "length", None, "llm_output_limit"),
        ("  ", "stop", None, "llm_empty_response"),
        ("", "stop", "sensitive refusal content", "llm_refused"),
        ("hidden", "content_filter", None, "llm_content_filtered"),
    ],
)
@pytest.mark.parametrize("streaming", [False, True])
async def test_filtered_refused_or_empty_output_is_not_a_success(content, reason, refusal, code, streaming):
    choice = {
        "delta" if streaming else "message": {"content": content, "refusal": refusal},
        "finish_reason": reason,
    }
    wire = "data: " + json.dumps({"choices": [choice]}) + "\n\ndata: [DONE]\n\n"

    def handler(request):
        return (
            httpx.Response(200, content=wire)
            if streaming
            else httpx.Response(200, json={"choices": [choice]})
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(LLMError) as error:
            _ = [
                e
                async for e in LLMClient(client=http).events(
                    "https://api.openai.com/v1",
                    "test-model",
                    "test-key",
                    [],
                    100,
                    streaming=streaming,
                    provider="openai",
                    token_parameter="max_completion_tokens",
                )
            ]
    assert error.value.code == code and "sensitive" not in str(error.value)


@pytest.mark.parametrize(
    "url",
    [
        "https://user:secret@gateway.example/v1",
        "https://gateway.example/v1?key=secret",
        "https://gateway.example/v1#fragment",
        "https://gateway.example/%2e%2e",
        "https://gateway.example/a/../v1",
        "https://gateway.example\\@127.0.0.1/v1",
        "https://127.0.0.1/v1",
        "https://169.254.169.254/v1",
        "https://10.0.0.1/v1",
        "https://224.0.0.1/v1",
        "\x00https://gateway.example/v1",
        "http://gateway.example/v1",
        "http://127.0.0.1:8000/v1",
        "https://gateway.example/v1\n",
        "https://gateway.example:99999/v1",
    ],
)
def test_untrusted_endpoints_rejected_even_if_allowlisted(url):
    with pytest.raises(AppError):
        endpoint(url, [8787], "openai_compatible", [url])


def test_allowlist_and_openai_host_are_exact():
    url = "https://gateway.example/custom/v1"
    assert endpoint(url + "/", [8787], "openai_compatible", [url]) == url
    # A platform-executed call never dials the machine it runs on, whatever the allowlist says.
    with pytest.raises(AppError):
        endpoint("http://127.0.0.1:8787/v1", [8787], "openai_compatible", ["http://127.0.0.1:8787/v1"])
    with pytest.raises(AppError):
        endpoint(url, [8787], "openai_compatible", [])
    with pytest.raises(AppError):
        endpoint(url, [8787], "openai", [url])


@pytest.mark.parametrize(
    "overrides",
    [
        {"provider": "openai"},
        {"provider": "openai_compatible", "model": "explicit"},
        {"max_tokens": 513},
        {"api_key": "secret\r\nInjected:value"},
        {"api_key": "a secret"},
        {"api_key": "secret\x00"},
        {"api_key": "secret\u00e9"},
        {"api_key": ""},
        {"provider": "openai", "model": "explicit", "token_parameter": "max_tokens"},
    ],
)
def test_provider_and_key_validation(overrides):
    with pytest.raises(ValidationError):
        ConnectionCreate(
            name="fixture",
            api_key=overrides.get("api_key", "key"),
            **{k: v for k, v in overrides.items() if k != "api_key"},
        )


def test_long_openai_key_and_protocol_defaults():
    c = ConnectionCreate(
        name="fixture", api_key="sk-proj-" + ("x" * 600), provider="openai", model="explicit"
    )
    assert c.base_url == "https://api.openai.com/v1" and c.token_parameter == "max_completion_tokens"
    assert "xxxx" not in repr(c)


@pytest.mark.parametrize(
    "addresses",
    [
        ["127.0.0.1"],
        ["224.0.0.1"],
        ["10.1.1.1"],
        ["169.254.169.254"],
        ["::1"],
        ["fd00::1"],
        ["8.8.8.8", "192.168.1.1"],
        [],
    ],
)
async def test_dns_private_and_mixed_answers_never_connect(monkeypatch, addresses):
    async def resolve(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, 443)) for a in addresses]

    monkeypatch.setattr("anyio.getaddrinfo", resolve)
    network = PublicNetwork()

    async def forbidden(*args, **kwargs):
        pytest.fail("Private address must not be connected")

    monkeypatch.setattr(network.backend, "connect_tcp", forbidden)
    with pytest.raises(httpcore.ConnectError):
        await network.connect_tcp("gateway.example", 443, timeout=1)


async def test_transport_loads_system_roots_without_disabling_tls(monkeypatch):
    contexts = []
    original = ssl.SSLContext.load_default_certs

    def load_roots(context, purpose=ssl.Purpose.SERVER_AUTH):
        original(context, purpose)
        contexts.append(context)

    monkeypatch.setattr(ssl.SSLContext, "load_default_certs", load_roots)
    transport = GuardedTransport()
    try:
        assert len(contexts) == 1
        assert contexts[0].verify_mode == ssl.CERT_REQUIRED
        assert contexts[0].check_hostname
        assert contexts[0].cert_store_stats()["x509_ca"] > 0
    finally:
        await transport.aclose()


async def test_dns_is_pinned_but_tls_sni_and_pool_keep_original_host(monkeypatch):
    resolved, connected, tls = [], [], []

    async def resolve(host, *args, **kwargs):
        resolved.append(host)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]

    monkeypatch.setattr("anyio.getaddrinfo", resolve)

    class Stream(httpcore.AsyncNetworkStream):
        async def read(self, max_bytes, timeout=None):
            return b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok"

        async def write(self, buffer, timeout=None):
            pass

        async def aclose(self):
            pass

        async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
            assert ssl_context.verify_mode == ssl.CERT_REQUIRED and ssl_context.check_hostname
            tls.append(server_hostname)
            return self

        def get_extra_info(self, info):
            return False if info == "is_readable" else None

    async def connect(self, host, *args, **kwargs):
        connected.append(host)
        return Stream()

    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", connect)
    async with httpx.AsyncClient(transport=GuardedTransport()) as client:
        for host in ["first.example", "second.example", "first.example"]:
            response = await client.get("https://" + host + "/v1")
            assert response.text == "ok"
    assert resolved == tls == ["first.example", "second.example"]
    assert connected == ["8.8.8.8", "8.8.8.8"]


async def test_dns_deadline_is_bounded(monkeypatch):
    async def resolve(*args, **kwargs):
        await asyncio.sleep(10)

    monkeypatch.setattr("anyio.getaddrinfo", resolve)
    with pytest.raises(httpcore.ConnectTimeout):
        await PublicNetwork().connect_tcp("slow.example", 443, timeout=0.02)


async def test_openai_health_checks_selected_model_without_fetching_whole_catalog():
    def handler(request):
        assert str(request.url) == "https://api.openai.com/v1/models/explicit-model"
        return httpx.Response(200, json={"id": "explicit-model"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await LLMClient(client=http).health(
            "https://api.openai.com/v1", "explicit-model", "private-key", provider="openai"
        )


@pytest.mark.parametrize(
    "provider,size,allowed",
    [
        ("azure_openai", 70000, True),
        ("azure_openai", 1048576, True),
        ("azure_openai", 1048577, False),
        ("openai_compatible", 70000, False),
    ],
)
async def test_large_azure_catalog_has_separate_bounded_limit(provider, size, allowed):
    body = json.dumps({"data": [{"id": "fixture", "metadata": ""}]}).encode()
    body = body.replace(b'"metadata": ""', b'"metadata": "' + b"x" * (size - len(body)) + b'"')
    assert len(body) == size
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(200, content=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        client = LLMClient(client=http)
        if allowed:
            await client.health("https://fixture.openai.azure.com/openai/v1", "fixture", "key", provider)
        else:
            with pytest.raises(LLMError) as error:
                await client.health("https://fixture.openai.azure.com/openai/v1", "fixture", "key", provider)
            assert error.value.code == "llm_response_limit"
    assert len(seen) == 1 and seen[0].method == "GET"


async def test_azure_completion_keeps_normal_response_limit():
    response = {"choices": [{"message": {"content": "x" * 70000}, "finish_reason": "stop"}]}
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=response))
    ) as http:
        with pytest.raises(LLMError) as error:
            async for _ in LLMClient(client=http).events(
                "https://fixture.openai.azure.com/openai/v1",
                "fixture",
                "key",
                [{"role": "user", "content": "fixture"}],
                1024,
                streaming=False,
                provider="azure_openai",
            ):
                pass
        assert error.value.code == "llm_response_limit"


# --- Readiness probe retries ------------------------------------------------------------
#
# A readiness probe is a credentialed GET of the model catalogue: no side effect, not billed as
# inference. So it may be retried, unlike a submission, whose outcome must never be assumed.


def catalog(model="fixture"):
    return httpx.Response(200, json={"data": [{"id": model}]})


async def test_a_transient_probe_failure_is_retried_until_the_provider_answers():
    """One missed window used to refuse the operator's whole question."""
    attempts = []

    def handler(request):
        attempts.append(request)
        if len(attempts) < 3:
            raise httpx.ConnectError("provider unreachable")
        return catalog()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await LLMClient(client=http, health_attempts=3).health("https://api.example/v1", "fixture", "key")
    assert len(attempts) == 3


async def test_exhausted_retries_report_the_transient_code():
    attempts = []

    def handler(request):
        attempts.append(request)
        raise httpx.ConnectError("provider unreachable")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(LLMError) as error:
            await LLMClient(client=http, health_attempts=3).health("https://api.example/v1", "x", "key")
    assert error.value.code == "llm_unavailable" and len(attempts) == 3


async def test_a_provider_server_error_is_transient_and_retried():
    """An unmapped non-200 becomes llm_unavailable, so a 502 from the provider is worth re-asking."""
    attempts = []

    def handler(request):
        attempts.append(request)
        return httpx.Response(502) if len(attempts) == 1 else catalog()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await LLMClient(client=http, health_attempts=3).health("https://api.example/v1", "fixture", "key")
    assert len(attempts) == 2


@pytest.mark.parametrize(
    "response,code",
    [
        (httpx.Response(401), "llm_credentials_rejected"),
        (httpx.Response(403), "llm_credentials_rejected"),
        (httpx.Response(404), "llm_deployment_not_found"),
        (httpx.Response(429), "llm_busy"),
        (httpx.Response(400), "llm_invalid_parameters"),
        (httpx.Response(200, content=b"not-json"), "llm_invalid_response"),
        (catalog("a-different-model"), "llm_model_mismatch"),
    ],
)
async def test_a_decided_answer_is_never_asked_twice(response, code):
    """Repeating these cannot change them, and repeating a 401 can lock a provider account."""
    attempts = []

    def handler(request):
        attempts.append(request)
        return response

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(LLMError) as error:
            await LLMClient(client=http, health_attempts=3).health("https://api.example/v1", "fixture", "key")
    assert error.value.code == code and len(attempts) == 1


async def test_the_whole_probe_is_bounded_even_when_every_attempt_hangs():
    """The operator is waiting to record, so the retries must not become an open-ended stall."""

    async def handler(request):
        await asyncio.sleep(30)
        return catalog()

    client = LLMClient(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        health_timeout=0.05,
        health_attempts=3,
    )
    assert client.health_deadline == pytest.approx(0.05 * 3 + 1.0)
    began = asyncio.get_running_loop().time()
    try:
        with pytest.raises(LLMError) as error:
            await client.health("https://api.example/v1", "fixture", "key")
    finally:
        await client.close()
    assert error.value.code == "llm_unavailable"
    assert asyncio.get_running_loop().time() - began < client.health_deadline + 1


async def test_a_single_attempt_keeps_the_previous_behaviour():
    attempts = []

    def handler(request):
        attempts.append(request)
        raise httpx.ConnectError("down")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(LLMError):
            await LLMClient(client=http, health_attempts=1).health("https://api.example/v1", "x", "key")
    assert len(attempts) == 1


async def test_the_default_probe_retries_once_and_stays_bounded():
    """The probe degrades to a warning rather than refusing a question, so giving up slowly buys
    nothing. One retry fixes a single missed window; the wait before recording stays near ten
    seconds."""
    client = LLMClient()
    try:
        assert client.health_attempts == 2
        assert client.health_deadline == pytest.approx(10.25)
    finally:
        await client.close()
