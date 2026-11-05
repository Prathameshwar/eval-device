import asyncio
import json

import httpx
import pytest
from test_cloud_models import frames, route, settings
from training_client.controller import Controller
from training_client.pms_client import ClientError, pms_error

from human_test.config import Settings


@pytest.mark.parametrize("code", ["llm_daily_limit", "llm_daily_request_limit"])
def test_daily_organization_limits_are_actionable_and_not_busy_retries(code):
    from training_client.pms_client import BUSY_CODES

    error = pms_error({"error": {"code": code}})
    assert code not in BUSY_CODES
    assert "organization" in str(error) and "00:00 UTC" in str(error)


async def client(handler, events):
    controller = Controller(settings(), lambda *event: events.append(event))
    controller.use_models(route())
    await controller.pms.http.aclose()
    controller.pms.http = httpx.AsyncClient(
        base_url="http://127.0.0.1", transport=httpx.MockTransport(handler)
    )
    return controller


def speech_ok(request):
    return httpx.Response(
        200,
        json={
            "request_key": request.url.params["request_key"],
            "status": "succeeded",
            "recording_status": "saved",
            "result": {"text": "What is your name?"},
        },
    )


def answer_ok(payload):
    result = {
        "type": "done",
        "request_key": payload["request_key"],
        "status": "succeeded",
        "text": "My name is Alex.",
        "finish_reason": "stop",
    }
    if payload["stream"]:
        return httpx.Response(200, content="data: " + json.dumps(result) + "\n\n")
    return httpx.Response(200, json=result)


@pytest.mark.parametrize(
    "stage,streaming", [("speech", True), ("response", True), ("response", False), ("both", True)]
)
async def test_busy_keeps_one_utterance_and_retries_only_rejected_stage(monkeypatch, stage, streaming):
    events, delays, audio_calls, answer_calls = [], [], [], []
    captured, closed = [], []

    async def sleep(delay):
        assert captured == [True] and closed == [True], "capture must close before every retry"
        assert controller.busy and not controller.history
        assert not any(kind == "speak" for kind, _ in events)
        with pytest.raises(ClientError, match="already active"):
            await controller.text_turn("Do not replace the queued question")
        assert f"in {delay} s" in events[-1][1]
        delays.append(delay)

    monkeypatch.setattr("training_client.pms_client.asyncio.sleep", sleep)

    def handler(request):
        if request.url.path.endswith("/speech/transcriptions"):
            audio_calls.append(request)
            assert closed == [True], "microphone still open during upload"
            if stage in {"speech", "both"} and len(audio_calls) <= 5:
                code = ("speech_busy", "concurrency_limit", "llm_busy")[(len(audio_calls) - 1) % 3]
                return httpx.Response(429, json={"error": {"code": code}})
            return speech_ok(request)
        payload = json.loads(request.content)
        answer_calls.append(payload)
        if stage in {"response", "both"} and len(answer_calls) <= 5:
            if streaming and len(answer_calls) > 1:
                return httpx.Response(200, content='data: {"type":"error","code":"llm_busy"}\n\n')
            return httpx.Response(429, json={"error": {"code": "llm_busy"}})
        return answer_ok(payload)

    controller = await client(handler, events)
    controller.settings.streaming = streaming

    async def capture():
        captured.append(True)
        try:
            async for frame in frames():
                yield frame
        finally:
            closed.append(True)

    try:
        result = await controller.turn(capture())
        assert result["answer"] == "My name is Alex."
        stages = 2 if stage == "both" else 1
        assert captured == closed == [True] and delays == [1, 2, 3, 4, 5] * stages
        assert len(audio_calls) == (6 if stage in {"speech", "both"} else 1)
        assert len(answer_calls) == (6 if stage in {"response", "both"} else 1)
        assert len({request.content for request in audio_calls}) == 1
        assert len({str(request.url.params["request_key"]) for request in audio_calls}) == len(audio_calls)
        assert len({body["request_key"] for body in answer_calls}) == len(answer_calls)
        assert all(body["messages"] == answer_calls[0]["messages"] for body in answer_calls)
        assert len(controller.history) == 2 and not controller.busy
        assert len([event for event in events if event[0] == "speak"]) == 1
        states = [value for kind, value in events if kind == "state" and "retained" in value]
        assert len(states) == 10 * stages
        assert all("Listening and speaking paused" in value for value in states)
        assert sum("in progress" in value for value in states) == 5 * stages
        assert [value for kind, value in events if kind == "retrying"] == [True, False] * stages
    finally:
        await controller.close()


@pytest.mark.parametrize("stage", ["speech", "response"])
async def test_busy_exhausts_stage_retry_policy_then_releases_turn(monkeypatch, stage):
    calls, delays, events = [], [], []

    async def sleep(delay):
        delays.append(delay)

    monkeypatch.setattr("training_client.pms_client.asyncio.sleep", sleep)

    def handler(request):
        if stage == "response" and request.url.path.endswith("/speech/transcriptions"):
            return speech_ok(request)
        calls.append(request)
        return httpx.Response(
            429, json={"error": {"code": "speech_busy" if stage == "speech" else "llm_busy"}}
        )

    controller = await client(handler, events)
    try:
        exhausted = r"10 rounds \(50 retries\)" if stage == "speech" else "5 retries"
        with pytest.raises(ClientError, match="still busy after " + exhausted):
            await controller.turn(frames())
        assert len(calls) == (51 if stage == "speech" else 6)
        expected_delays = [1, 2, 3, 4, 5]
        if stage == "speech":
            expected_delays += [3, 1, 2, 3, 4, 5] * 9
        assert delays == expected_delays
        states = [value for kind, value in events if kind == "state"]
        assert sum("Retry " in value for value in states) == (50 if stage == "speech" else 5)
        assert sum("next round in 3 s" in value for value in states) == (9 if stage == "speech" else 0)
        progress = [value for kind, value in events if kind == "retry_status"]
        assert sum(value["phase"] == "waiting" for value in progress) == len(calls) - 1
        assert sum(value["phase"] == "submitting" for value in progress) == len(calls) - 1
        pauses = [value for value in progress if value["phase"] == "between_rounds"]
        assert [value["round"] for value in pauses] == (list(range(2, 11)) if stage == "speech" else [])
        assert all(value["wait_seconds"] == 3 for value in pauses)
        assert progress[-1]["round"] == (10 if stage == "speech" else 1)
        assert progress[-1]["retry"] == 5
        assert not controller.busy and not controller.history
        assert [value for kind, value in events if kind == "retrying"] == [True, False]
        assert not any(kind == "speak" for kind, _ in events)
    finally:
        await controller.close()


@pytest.mark.parametrize(
    "code",
    [
        "llm_credentials_rejected",
        "speech_daily_limit",
        "llm_daily_limit",
        "llm_daily_request_limit",
        "llm_transport_unknown",
        "speech_submission_unknown",
        "llm_unavailable",
        "model_selection_changed",
    ],
)
@pytest.mark.parametrize("busy_before", [0, 6])
async def test_non_busy_errors_never_retry(monkeypatch, code, busy_before):
    calls = []

    async def sleep(delay):
        pass

    monkeypatch.setattr("training_client.pms_client.asyncio.sleep", sleep)

    def handler(request):
        calls.append(request)
        if len(calls) <= busy_before:
            return httpx.Response(429, json={"error": {"code": "speech_busy"}})
        return httpx.Response(503, json={"error": {"code": code}})

    controller = await client(handler, [])
    try:
        with pytest.raises(ClientError):
            await controller.turn(frames())
        assert len(calls) == busy_before + 1
    finally:
        await controller.close()


async def test_busy_after_partial_response_never_replays():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            content='data: {"type":"delta","text":"partial"}\n\ndata: {"type":"error","code":"llm_busy"}\n\n',
        )

    controller = await client(handler, [])
    try:
        with pytest.raises(ClientError):
            await controller.text_turn("Hello")
        assert len(calls) == 1 and not controller.history
    finally:
        await controller.close()


@pytest.mark.parametrize("streaming", [False, True])
async def test_response_timeout_keeps_recovery_key_and_never_replays(streaming):
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("fixture timeout")

    controller = await client(handler, [])
    controller.settings.streaming = streaming
    try:
        with pytest.raises(ClientError, match="Check last request"):
            await controller.text_turn("Hello")
        assert len(calls) == 1 and controller.pms.last_request
        assert not controller.history and not controller.busy
    finally:
        await controller.close()


@pytest.mark.parametrize("stage,busy_before", [("speech", 1), ("response", 1), ("speech", 6)])
async def test_timeout_after_a_busy_retry_stops_and_retains_latest_recovery_key(
    monkeypatch, stage, busy_before
):
    calls, events, delays = [], [], []

    async def sleep(delay):
        delays.append(delay)

    monkeypatch.setattr("training_client.pms_client.asyncio.sleep", sleep)

    def handler(request):
        if stage == "response" and request.url.path.endswith("/speech/transcriptions"):
            return speech_ok(request)
        calls.append(request)
        if len(calls) <= busy_before:
            return httpx.Response(429, json={"error": {"code": "llm_busy"}})
        raise httpx.ReadTimeout("fixture timeout")

    controller = await client(handler, events)
    try:
        with pytest.raises(ClientError, match="[Cc]heck last request"):
            await controller.turn(frames())
        assert len(calls) == busy_before + 1
        assert delays == ([1] if busy_before == 1 else [1, 2, 3, 4, 5, 3, 1])
        key = (
            calls[-1].url.params["request_key"]
            if stage == "speech"
            else json.loads(calls[-1].content)["request_key"]
        )
        assert key == (
            controller.pms.last_speech_request if stage == "speech" else controller.pms.last_request
        )
        assert [value for kind, value in events if kind == "retrying"] == [True, False]
        assert not controller.busy and not controller.history
        assert not any(kind == "speak" for kind, _ in events)
    finally:
        await controller.close()


@pytest.mark.parametrize("busy_count", [0, 1, 2, 3, 4])
async def test_retries_stop_immediately_when_the_model_recovers(monkeypatch, busy_count):
    calls, delays, events = [], [], []

    async def sleep(delay):
        delays.append(delay)

    monkeypatch.setattr("training_client.pms_client.asyncio.sleep", sleep)

    def handler(request):
        payload = json.loads(request.content)
        calls.append(payload)
        if len(calls) <= busy_count:
            return httpx.Response(429, json={"error": {"code": "llm_busy"}})
        return answer_ok(payload)

    controller = await client(handler, events)
    try:
        await controller.text_turn("What is your name?")
        assert len(calls) == busy_count + 1 and delays == list(range(1, busy_count + 1))
        assert len(controller.history) == 2
        assert sum(kind == "speak" for kind, _ in events) == 1
        assert [value for kind, value in events if kind == "retrying"] == (
            [True, False] if busy_count else []
        )
    finally:
        await controller.close()


@pytest.mark.parametrize("cancel_at", [1, 2, 3, 4, 5])
async def test_pause_during_backoff_cancels_without_another_submission(monkeypatch, cancel_at):
    sleeping, calls, events = asyncio.Event(), [], []

    async def sleep(delay):
        if delay == cancel_at:
            sleeping.set()
            await asyncio.Event().wait()

    monkeypatch.setattr("training_client.pms_client.asyncio.sleep", sleep)

    def handler(request):
        calls.append(request)
        return httpx.Response(429, json={"error": {"code": "speech_busy"}})

    controller = await client(handler, events)
    task = asyncio.create_task(controller.turn(frames()))
    try:
        await asyncio.wait_for(sleeping.wait(), 2)
        assert controller.busy
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(calls) == cancel_at and not controller.busy
        assert [value for kind, value in events if kind == "retrying"] == [True, False]
        assert not any(kind == "speak" for kind, _ in events)
    finally:
        await controller.close()


async def test_cloud_readiness_busy_allows_capture_but_auth_failure_does_not(monkeypatch):
    events = []
    controller = await client(lambda request: httpx.Response(500), events)
    selected = controller.pms.model_route

    async def config(*args):
        return selected

    async def busy():
        raise pms_error({"error": {"code": "llm_busy"}})

    async def denied():
        raise pms_error({"error": {"code": "llm_credentials_rejected"}})

    monkeypatch.setattr(controller.pms, "model_config", config)
    monkeypatch.setattr(controller.pms, "speech_status", busy)
    monkeypatch.setattr(controller.pms, "preflight", busy)
    try:
        await controller.preflight()
        assert any(kind == "ready" and "queue" in value for kind, value in events)
        controller._preflight_at = 0
        monkeypatch.setattr(controller.pms, "preflight", denied)
        with pytest.raises(ClientError):
            await controller.preflight()
    finally:
        await controller.close()


@pytest.mark.parametrize("busy_count,rounds,pause", [(6, 10, 3), (50, 10, 3), (10, 2, 7)])
async def test_speech_recovers_in_later_round_without_recapture(monkeypatch, busy_count, rounds, pause):
    calls, delays, events, captured, closed = [], [], [], [], []

    async def sleep(delay):
        assert captured == closed == [True]
        assert controller.busy and not controller.history
        assert [value for kind, value in events if kind == "retrying"] == [True]
        assert not any(kind == "speak" for kind, _ in events)
        delays.append(delay)

    monkeypatch.setattr("training_client.pms_client.asyncio.sleep", sleep)

    def handler(request):
        if request.url.path.endswith("/speech/transcriptions"):
            calls.append(request)
            if len(calls) <= busy_count:
                return httpx.Response(429, json={"error": {"code": "speech_busy"}})
            return speech_ok(request)
        return answer_ok(json.loads(request.content))

    async def capture():
        captured.append(True)
        try:
            async for frame in frames():
                yield frame
        finally:
            closed.append(True)

    controller = await client(handler, events)
    controller.settings.speech_retry_rounds = rounds
    controller.settings.speech_retry_round_pause_seconds = pause
    try:
        result = await controller.turn(capture())
        assert result["answer"] == "My name is Alex."
        assert len(calls) == busy_count + 1 and captured == closed == [True]
        assert len({request.content for request in calls}) == 1
        assert len({request.url.params["request_key"] for request in calls}) == len(calls)
        assert len({str(request.url.params.remove("request_key")) for request in calls}) == 1
        expected_delays = [1, 2, 3, 4, 5]
        expected_delays += [pause, 1] if busy_count == 6 else [pause, 1, 2, 3, 4, 5] * (rounds - 1)
        assert delays == expected_delays
        states = [value for kind, value in events if kind == "state"]
        assert sum("Retry " in value for value in states) == busy_count
        final_round = 2 if busy_count == 6 else rounds
        final_retry = 1 if busy_count == 6 else 5
        assert any(
            f"Round {final_round}/{rounds}. retry {final_retry}/5 in progress" in value for value in states
        )
        assert [value for kind, value in events if kind == "retrying"] == [True, False]
        assert len(controller.history) == 2 and not controller.busy
        assert sum(kind == "speak" for kind, _ in events) == 1
    finally:
        await controller.close()


@pytest.mark.parametrize("cancel_at_sleep,expected_calls", [(6, 6), (7, 6), (59, 50)])
async def test_cancel_between_or_within_later_speech_rounds(monkeypatch, cancel_at_sleep, expected_calls):
    sleeping, calls, events, delays = asyncio.Event(), [], [], []

    async def sleep(delay):
        delays.append(delay)
        if len(delays) == cancel_at_sleep:
            if cancel_at_sleep == 6:
                assert delay == 3 and "next round in 3 s" in events[-1][1]
            sleeping.set()
            await asyncio.Event().wait()

    monkeypatch.setattr("training_client.pms_client.asyncio.sleep", sleep)

    def handler(request):
        calls.append(request)
        return httpx.Response(429, json={"error": {"code": "speech_busy"}})

    controller = await client(handler, events)
    task = asyncio.create_task(controller.turn(frames()))
    try:
        await asyncio.wait_for(sleeping.wait(), 5)
        assert controller.busy
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(calls) == expected_calls and not controller.busy
        assert not controller.history and not any(kind == "speak" for kind, _ in events)
        assert [value for kind, value in events if kind == "retrying"] == [True, False]
    finally:
        task.cancel()
        await controller.close()


def test_speech_retry_settings_defaults_and_environment(monkeypatch):
    monkeypatch.delenv("HUMAN_SPEECH_RETRY_ROUNDS", raising=False)
    monkeypatch.delenv("HUMAN_SPEECH_RETRY_ROUND_PAUSE_SECONDS", raising=False)
    configured = Settings(_env_file=None)
    assert configured.speech_retry_rounds == 10
    assert configured.speech_retry_round_pause_seconds == 3
    monkeypatch.setenv("HUMAN_SPEECH_RETRY_ROUNDS", "2")
    monkeypatch.setenv("HUMAN_SPEECH_RETRY_ROUND_PAUSE_SECONDS", "7")
    configured = Settings(_env_file=None)
    assert configured.speech_retry_rounds == 2
    assert configured.speech_retry_round_pause_seconds == 7


@pytest.mark.parametrize(
    "overrides",
    [
        {"speech_retry_rounds": 0},
        {"speech_retry_rounds": 11},
        {"speech_retry_round_pause_seconds": -1},
        {"speech_retry_round_pause_seconds": 61},
    ],
)
def test_speech_retry_settings_are_bounded(overrides):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(_env_file=None, **overrides)
