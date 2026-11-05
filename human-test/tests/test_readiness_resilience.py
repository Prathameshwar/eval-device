"""A readiness probe must not be the single point of failure for a spoken question.

Pressing Start microphone checks that speech and the response model are reachable. Those checks
are probes, not the turn: they are retried where they are made, and an unanswered one downgrades
to a warning so the question is still captured and submitted. Answers that cannot change with a
second attempt - rejected credentials, a missing deployment, exhausted quota - still stop the
question before any audio is recorded.

A submission is a different matter and is never resent on an unknown outcome; `test_busy_retry`
holds that line.
"""

import httpx
import pytest
from local_model_client import native as local_llm
from local_model_client.native import LocalModel
from test_cloud_models import route, settings
from training_client.controller import Controller
from training_client.pms_client import BUSY_CODES, SOFT_READINESS_CODES, ClientError, pms_error

PORT = 8787


def failure(code, status=503):
    return httpx.Response(status, json={"error": {"code": code}})


async def controller_for(handler, events, llm="cloud"):
    controller = Controller(settings(), lambda *event: events.append(event))
    controller.use_models(route(llm=llm))
    await controller.pms.http.aclose()
    controller.pms.http = httpx.AsyncClient(
        base_url="http://127.0.0.1", transport=httpx.MockTransport(handler)
    )
    return controller


def responder(status_response, speech=None):
    """Serve the three calls preflight makes, letting a test dictate the readiness answers."""
    seen = []

    def handler(request):
        seen.append(request.url.path)
        if request.url.path.endswith("/model-config"):
            return httpx.Response(200, json=route())
        if request.url.path.endswith("/speech/status"):
            return speech if speech is not None else httpx.Response(200, json={"ready": True})
        if request.url.path.endswith("/status"):
            return status_response
        raise AssertionError(f"unexpected call to {request.url.path}")

    return handler, seen


def probes(seen):
    return [path for path in seen if "/models/" in path and path.endswith("/status")]


def announced(events):
    return next(value for kind, value in events if kind == "ready")


async def test_device_without_speech_does_not_probe_or_record_audio():
    selected = route()
    selected["audio"]["enabled"] = False
    seen = []

    def handler(request):
        seen.append(request.url.path)
        if request.url.path.endswith("/model-config"):
            return httpx.Response(200, json=selected)
        if "/models/" in request.url.path:
            return httpx.Response(200, json={"ready": True})
        raise AssertionError("Unexpected speech call")

    controller = await controller_for(handler, [])
    controller.use_models(selected)
    try:
        with pytest.raises(ClientError, match="Use typing"):
            await controller.preflight()
        assert not any("/speech/" in path for path in seen)
        with pytest.raises(ClientError, match="no interactive speech model"):
            await controller.turn([])
    finally:
        await controller.close()


# --- The taxonomy itself ----------------------------------------------------------------


def test_the_soft_set_stays_narrow_and_does_not_overlap_busy():
    assert SOFT_READINESS_CODES == {"llm_unavailable", "llm_timeout"}
    assert not SOFT_READINESS_CODES & BUSY_CODES


def test_an_unreachable_provider_now_reads_as_a_sentence_not_a_bare_code():
    error = pms_error({"error": {"code": "llm_unavailable"}})
    assert "PMS: llm_unavailable" not in str(error)
    assert "could not reach" in str(error) and error.code == "llm_unavailable"


# --- Degrading instead of refusing ------------------------------------------------------


@pytest.mark.parametrize("code", sorted(SOFT_READINESS_CODES))
async def test_an_unanswered_response_check_warns_and_still_allows_the_question(code):
    events = []
    handler, seen = responder(failure(code))
    controller = await controller_for(handler, events)
    try:
        await controller.preflight()  # Must not raise: the question is still worth asking.
    finally:
        await controller.close()
    message = announced(events)
    assert "Unverified" in message and "the response model" in message
    assert "will still be sent" in message and "readiness check after" in message
    assert probes(seen)


async def test_an_unanswered_speech_check_is_named_in_the_warning():
    events = []
    handler, _ = responder(httpx.Response(200, json={"ready": True}), speech=failure("llm_unavailable"))
    controller = await controller_for(handler, events)
    try:
        await controller.preflight()
    finally:
        await controller.close()
    message = announced(events)
    assert "speech" in message and "the response model" not in message


async def test_both_checks_unanswered_names_both():
    events = []
    handler, _ = responder(failure("llm_unavailable"), speech=failure("llm_unavailable"))
    controller = await controller_for(handler, events)
    try:
        await controller.preflight()
    finally:
        await controller.close()
    assert "speech and the response model" in announced(events)


async def test_a_degraded_check_is_not_cached_so_recovery_is_noticed():
    """A proven pair is cached for 15 s. Caching a failure would keep claiming trouble after the
    provider came back, and would stop the next question from re-checking."""
    events = []
    handler, seen = responder(failure("llm_unavailable"))
    controller = await controller_for(handler, events)
    try:
        await controller.preflight()
        assert controller._preflight_at == 0.0
        await controller.preflight()
    finally:
        await controller.close()
    assert len(probes(seen)) == 2


async def test_a_proven_pair_is_cached_and_not_probed_again():
    events = []
    handler, seen = responder(httpx.Response(200, json={"ready": True}))
    controller = await controller_for(handler, events)
    try:
        await controller.preflight()
        assert controller._preflight_at > 0
        await controller.preflight()
    finally:
        await controller.close()
    assert len(probes(seen)) == 1


# --- Answers that must still stop the question ------------------------------------------


@pytest.mark.parametrize(
    "code",
    [
        "llm_credentials_rejected",
        "llm_deployment_not_found",
        "llm_model_mismatch",
        "llm_daily_limit",
        "llm_disabled",
    ],
)
async def test_a_decided_failure_still_refuses_before_any_audio_is_recorded(code):
    """Capturing a question against a rejected key or an exhausted quota only wastes it."""
    events = []
    handler, _ = responder(failure(code))
    controller = await controller_for(handler, events)
    try:
        with pytest.raises(ClientError) as error:
            await controller.preflight()
    finally:
        await controller.close()
    assert error.value.code == code
    assert controller._preflight_at == 0.0


# --- The local model server -------------------------------------------------------------


def model_list(model="qwen3-4b-local"):
    return httpx.Response(200, json={"data": [{"id": model}]})


def local_model(handler):
    return LocalModel(
        PORT,
        "laptop-model-key",
        "qwen3-4b-local",
        context_cap=4096,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


async def test_a_local_server_still_loading_its_weights_is_given_another_chance():
    """A multi-billion-parameter model can be slow to answer its catalogue while it loads."""
    attempts = []

    def handler(request):
        attempts.append(request)
        if len(attempts) < 3:
            raise httpx.ConnectError("not up yet")
        return model_list()

    model = local_model(handler)
    try:
        await model.health()
    finally:
        await model.client.aclose()
    assert len(attempts) == 3


@pytest.mark.parametrize(
    "response,code",
    [
        (httpx.Response(401), "llm_credentials_rejected"),
        (model_list("a-different-model"), "llm_model_mismatch"),
    ],
)
async def test_a_decided_local_answer_is_never_asked_twice(response, code):
    attempts = []

    def handler(request):
        attempts.append(request)
        return response

    model = local_model(handler)
    try:
        with pytest.raises(Exception) as error:
            await model.health()
    finally:
        await model.client.aclose()
    assert error.value.code == code and len(attempts) == 1


async def test_an_exhausted_local_probe_reports_the_transient_code():
    attempts = []

    def handler(request):
        attempts.append(request)
        raise httpx.ConnectError("no server")

    model = local_model(handler)
    try:
        with pytest.raises(Exception) as error:
            await model.health()
    finally:
        await model.client.aclose()
    assert error.value.code == "llm_unavailable"
    assert len(attempts) == local_llm.HEALTH_ATTEMPTS
