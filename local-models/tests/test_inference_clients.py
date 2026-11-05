# ruff: noqa: E402 - standalone central manager test imports
"""Inference credentials, model pinning and inspection privacy across the real gateway."""

import secrets
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
import pytest

LOCAL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOCAL))
sys.path.insert(0, str(LOCAL / "client/src"))
from local_model_client.connection import Connection, ConnectionError, validate_capabilities
from local_model_client.llm import LocalModel
from training_contracts.patient_turn import TurnError

from service.errors import ManagerError
from service.http_server import JsonServer
from service.worker import Llm, Recognition


@pytest.fixture
def server():
    requests = []
    operator, client = secrets.token_urlsafe(48), secrets.token_urlsafe(48)

    def dispatch(method, path, payload, query):
        requests.append((method, path, payload))
        return {"ok": True}

    server = JsonServer(("127.0.0.1", 0), operator, dispatch, client_key=client)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, operator, client, requests
    server.shutdown()
    server.server_close()
    thread.join(3)


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/v1/status"),
        ("GET", "/v1/logs"),
        ("GET", "/v1/operations/fixture"),
        ("POST", "/v1/actions/start"),
        ("POST", "/v1/actions/stop"),
        ("POST", "/v1/actions/download"),
        ("POST", "/v1/actions/provision"),
        ("POST", "/v1/shutdown"),
    ],
)
def test_inference_credential_cannot_manage_or_inspect_logs(server, method, path):
    service, operator, client, requests = server
    with httpx.Client(trust_env=False) as http:
        result = http.request(
            method,
            f"http://127.0.0.1:{service.server_port}" + path,
            headers={"Authorization": "Bearer " + client},
            **({"json": {}} if method == "POST" else {}),
        )
    assert result.status_code == 403 and result.json()["code"] == "permission_denied"
    assert not requests


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/v1/capabilities"),
        ("POST", "/v1/infer/llm"),
        ("POST", "/v1/infer/asr"),
        ("POST", "/v1/infer/tts"),
        ("POST", "/v1/llm/inspect"),
    ],
)
def test_inference_credential_has_only_the_supported_data_routes(server, method, path):
    service, operator, client, requests = server
    with httpx.Client(trust_env=False) as http:
        response = http.request(
            method,
            f"http://127.0.0.1:{service.server_port}" + path,
            headers={"Authorization": "Bearer " + client},
            **({"json": {}} if method == "POST" else {}),
        )
    assert response.status_code == 200 and len(requests) == 1


def adapter():
    value = Llm.__new__(Llm)
    value.server = SimpleNamespace(profile={"alias": "qwen3-1.7b-local"}, key="private-native-key")
    value.settings = {"port": 18888, "max_tokens": 128, "request_timeout_seconds": 30}
    return value


def test_llm_service_pins_model_and_caps_output_before_native_call():
    value = adapter()
    with patch("service.worker.call") as call:
        for payload in (
            {"messages": [{"role": "user", "content": "Hello"}], "model": "different"},
            {"messages": [{"role": "user", "content": "Hello"}], "max_tokens": 129},
        ):
            with pytest.raises(ManagerError):
                value.infer(payload)
        call.assert_not_called()


def test_bounded_selection_grammar_and_parameters_reach_native_once():
    value = adapter()
    with patch("service.worker.call", return_value={"choices": []}) as call:
        value.infer(
            {
                "model": "qwen3-1.7b-local",
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 16,
                "grammar": 'root ::= "hello"',
            }
        )
        assert call.call_count == 1
        payload = call.call_args.args[4]
        assert payload["stream"] is False and payload["temperature"] == 0
        assert payload["max_tokens"] == 16 and payload["grammar"] == 'root ::= "hello"'


@pytest.mark.parametrize(
    "operation,payload",
    [
        ("shutdown", {}),
        ("props", {}),
        ("tokenize", {"content": "x", "add_special": True, "parse_special": True}),
        ("apply-template", {"messages": [], "chat_template_kwargs": {"enable_thinking": False}}),
    ],
)
def test_inspection_cannot_execute_control_or_unbounded_native_routes(operation, payload):
    with patch("service.worker.call") as call:
        with pytest.raises(ManagerError):
            adapter().inspect({"model": "qwen3-1.7b-local", "operation": operation, "payload": payload})
        call.assert_not_called()


def test_recognition_model_switch_is_rejected_without_decoding_or_engine_use():
    value = Recognition.__new__(Recognition)
    value.model_id = "large-v3"
    value.engine = Mock()
    with pytest.raises(ManagerError) as error:
        value.infer({"model": "small", "language": "en", "wav_base64": "private-invalid-audio"})
    assert error.value.code == "model_mismatch"
    value.engine.transcribe.assert_not_called()


@pytest.mark.parametrize(
    "value",
    [
        {},
        {"version": 1, "revision": 0, "models": [{"id": "x", "name": "x", "capability": []}], "services": {}},
        {"version": 1, "revision": 0, "models": [None], "services": {}},
        {
            "version": 1,
            "revision": 0,
            "models": [],
            "services": {"asr": {"ready": "true", "state": "Ready", "model_id": "large-v3"}},
        },
    ],
)
def test_malformed_capabilities_cannot_enable_models_or_crash_ui(value):
    with pytest.raises(ConnectionError):
        validate_capabilities(value)


@pytest.mark.asyncio
async def test_unknown_llm_outcome_is_not_replayed_or_exposed():
    calls = []

    def fail(request):
        calls.append(request)
        raise httpx.ReadTimeout("private key and prompt")

    async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as client:
        model = LocalModel(8790, "fixture-client-key", "qwen3-1.7b-local", context_cap=2048, client=client)
        with pytest.raises(TurnError) as error:
            await model.complete([{"role": "user", "content": "fictional input"}], 16)
    assert len(calls) == 1 and error.value.code == "llm_unavailable"
    assert "private" not in str(error.value)


def test_client_disconnect_has_no_service_shutdown(server):
    service, _, key, requests = server
    connection = Connection(port=service.server_port, key=key)
    assert connection.request("GET", "/v1/capabilities")["ok"]
    del connection
    replacement = Connection(port=service.server_port, key=key)
    assert replacement.request("GET", "/v1/capabilities")["ok"]
    assert [path for _, path, _ in requests] == ["/v1/capabilities", "/v1/capabilities"]


def test_malformed_error_code_is_sanitized_and_not_retried():
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(503, json={"code": [], "message": "private diagnostic"})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        connection = Connection(key="fixture-client-key", client=client)
        with pytest.raises(ConnectionError) as error:
            connection.request("POST", "/v1/infer/tts", {"text": "Fictional test"})
    assert error.value.code == "unavailable" and len(calls) == 1
    assert "private" not in str(error.value)
