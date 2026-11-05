"""Connect to assigned running services; never install/start/stop an engine."""

import json
import time

import httpx
from local_model_client import Connection, ConnectionError, client_key
from runtime_environment import desktop_environment as desktop_environment
from runtime_environment import provider_free_environment as provider_free_environment
from startup import ReadinessFailure, message, phase
from training_client.model_route import interactive_speech


def required_services(route):
    return {
        "audio": interactive_speech(route) and route["audio"]["mode"] == "local",
        "llm": route["llm"]["mode"] == "local",
    }


def validate_local_route(route):
    if route["llm"]["mode"] == "local" and route["llm"].get("execution") != "caller":
        raise RuntimeError("Assigned local LLM must use caller execution; check its platform assignment")


def capture_language(route):
    from training_contracts.languages import DEFAULT_REGISTRY
    from training_contracts.languages.speech_models import recognition_languages

    available = {pack.language for pack in DEFAULT_REGISTRY.all()}
    declared = (
        recognition_languages(route["audio"]["model"])
        if interactive_speech(route) and route["audio"]["mode"] == "local"
        else available
    )
    choices = sorted(available.intersection(declared))
    language = route["audio"].get("language", "en") if interactive_speech(route) else "en"
    if language == "auto":
        # Historical media profiles may use Auto; conversation startup selects
        # explicit English until the user saves an installed case language.
        language = "en"
    if language not in choices:
        raise RuntimeError("Selected speech language has no installed conversation pack or model support")
    return language


def check_enablement(route):
    cloud_speech = interactive_speech(route) and route["audio"]["mode"] == "cloud"
    remote = cloud_speech or route["llm"].get("requires_external", route["mode"] != "local")
    if remote and not route["cloud_allowed"]:
        raise RuntimeError(
            "Assigned device models use cloud services; enable PMS_EXTERNAL_CALLS_ENABLED on the central API and restart that API"
        )
    if not route.get("llm_enabled", True):
        raise RuntimeError(
            "PMS LLM is disabled; enable PMS_LLM_ENABLED on the central API and restart that API"
        )
    if cloud_speech and not route.get("speech_enabled", True):
        raise RuntimeError(
            "Cloud speech is disabled; enable PMS_SPEECH_ENABLED on the central API and restart that API"
        )
    if (cloud_speech or route["llm"].get("provider") == "azure_openai") and not route.get(
        "azure_enabled", True
    ):
        raise RuntimeError(
            "Azure is disabled in PMS platform settings; a platform administrator must enable it"
        )
    if route.get("maintenance_mode"):
        raise RuntimeError("PMS maintenance mode is enabled; new model requests are paused")


def start(demo):
    from demo import STATE, env_file
    from external_pms import platform_call, published_route, report_local_models
    from startup import wait_ready

    demo.load_config()
    with phase("Check platform availability"):
        wait_ready(
            demo.pms_ready, 15, "Existing platform API", cancelled=getattr(demo.services, "cancelled", None)
        )
    demo.services.watch("PMS API", demo.pms_ready)
    settings = demo.external_settings
    connection = Connection(state=settings.local_models_state_dir, port=settings.local_models_port)
    info = None
    try:
        info = connection.capabilities()
    except ConnectionError:
        pass
    if info and settings.device_token:
        with phase("Report central verified model inventory"):
            report_local_models(demo, info)
    route = published_route(demo, lambda method, path, body=None: platform_call(demo, method, path, body))
    demo.route, demo.processing_mode = route, route["mode"]
    check_enablement(route)
    validate_local_route(route)
    local = required_services(route)
    for capability, needed, model in (
        ("llm", local["llm"], route["llm"]["model"]),
        ("asr", local["audio"], route["audio"]["model"]),
    ):
        if needed:
            with phase("Connect to central " + capability):
                try:
                    connection.require(capability, model)
                    info = connection.capabilities()
                except ConnectionError as error:
                    raise RuntimeError(
                        str(error)
                        + ". Start the assigned services in Manage Local Models. For a separate installation, set HUMAN_LOCAL_MODELS_STATE_DIR in human-test/.env."
                    ) from None
    demo.audio_model = route["audio"]["model"]
    demo.audio_device = (
        (info or {}).get("services", {}).get("asr", {}).get("device", "cpu") if local["audio"] else "cloud"
    )
    demo.human = {
        "HUMAN_DESKTOP_PREPARED": "true",
        "HUMAN_HISTORY_ENABLED": str(settings.history_enabled).lower(),
        "HUMAN_HISTORY_DIR": str(STATE / "conversation-outbox"),
        "HUMAN_USE_PMS_MODELS": "true",
        "HUMAN_PROCESSING_PROFILE_ID": route["profile_id"],
        "HUMAN_PMS_URL": demo.pms_url,
        "HUMAN_PMS_TOKEN": demo.token,
        "HUMAN_ORGANIZATION_ID": demo.config["organization_id"],
        "HUMAN_CONNECTION_ID": route["llm"]["connection_id"],
        "HUMAN_AUDIO_MODE": route["audio"]["mode"],
        "HUMAN_SPEECH_INPUT_ENABLED": str(interactive_speech(route)).lower(),
        "HUMAN_AUDIO_MODEL": route["audio"]["model"],
        "HUMAN_AUDIO_DEVICE": demo.audio_device if local["audio"] else "cpu",
        "HUMAN_LANGUAGE": capture_language(route),
        "HUMAN_LOCAL_MODELS_PORT": str(settings.local_models_port),
        "HUMAN_LOCAL_MODELS_CAPABILITIES": json.dumps(info or {}),
    }
    if settings.local_models_state_dir:
        demo.human["HUMAN_LOCAL_MODELS_STATE_DIR"] = str(settings.local_models_state_dir)
    if info:
        demo.human["HUMAN_LOCAL_MODELS_KEY"] = connection.key or client_key(connection.state)
    if settings.department_id:
        demo.human["HUMAN_DEPARTMENT_ID"] = str(settings.department_id)
    if settings.device_id:
        demo.human["HUMAN_DEVICE_ID"] = str(settings.device_id)
    env_file(STATE / "human.env", demo.human)
    access_ready = verify_with_retries(demo)
    demo.status("ready")
    if access_ready:
        message("READY", "Connected to assigned models; service ownership remains with Manage Local Models")
    return demo.human


class CloudReadinessFailure(ReadinessFailure):
    """A cloud probe was unavailable; authenticated submissions still enforce policy."""


def model_access(client, url, label, headers, cloud):
    # Parse only bounded status data. Never log raw provider bodies or exception text.
    try:
        # PMS defaults to two five-second probes plus backoff; don't cut off its second attempt.
        with client.stream("GET", url, headers=headers, timeout=15) as response:
            raw = bytearray()
            for block in response.iter_bytes():
                raw.extend(block)
                if len(raw) > 131072:
                    raise RuntimeError(f"{label}: invalid readiness response")
            try:
                value = json.loads(raw)
            except (ValueError, RecursionError):
                value = {}
            if not isinstance(value, dict):
                value = {}
            if response.status_code == 200:
                if not value:
                    raise RuntimeError(f"{label}: invalid readiness response")
                return value
            error = value.get("error")
            code = error.get("code") if isinstance(error, dict) else None
            if not isinstance(code, str):
                code = None
            # The allowlist preserves policy/configuration failures even when they use HTTP 503.
            temporary = code in {
                "llm_busy",
                "speech_busy",
                "concurrency_limit",
                "llm_unavailable",
                "llm_timeout",
            }
            safe = (
                code
                if temporary
                or code
                in {
                    "llm_credentials_rejected",
                    "llm_deployment_not_found",
                    "llm_invalid_parameters",
                    "llm_model_mismatch",
                    "llm_endpoint_invalid",
                    "external_calls_disabled",
                    "provider_disabled",
                    "speech_disabled",
                    "llm_disabled",
                    "maintenance_mode",
                    "permission_denied",
                    "model_selection_changed",
                    "connection_unvalidated",
                    "invalid_token",
                }
                else "request_rejected"
            )
            detail = f"{label}: HTTP {response.status_code} ({safe})"
            if temporary and response.status_code in {429, 500, 502, 503, 504}:
                raise (CloudReadinessFailure if cloud else ReadinessFailure)(detail)
            raise RuntimeError(detail + "; check PMS credentials, model settings and enablement")
    except (httpx.HTTPError, OSError):
        raise (CloudReadinessFailure if cloud else ReadinessFailure)(
            f"{label}: readiness connection timed out or failed"
        ) from None


def verify(demo):
    from demo import checked_json

    org = demo.config["organization_id"]
    headers = {"Authorization": "Bearer " + demo.token}
    base = demo.pms_url + f"/api/v1/organizations/{org}"
    route = demo.route
    if (
        checked_json(demo.http, base + "/patient-practice/scenario-options", "Practice access", headers)
        is None
    ):
        raise ReadinessFailure("PMS practice setup is not ready")
    probes = [
        (
            "Response model",
            f"/llm/models/{route['llm']['connection_id']}/status",
            route["llm"]["model"],
            route["llm"]["mode"] == "cloud",
        )
    ]
    if interactive_speech(route) and route["audio"]["mode"] == "cloud":
        probes.append(
            (
                "Cloud speech",
                f"/speech/status?profile_id={route['profile_id']}",
                route["audio"]["model"],
                True,
            )
        )
    unavailable = []
    for label, path, expected, cloud in probes:
        try:
            data = model_access(demo.http, base + path, label, headers, cloud)
            if data.get("model") != expected:
                raise RuntimeError(f"{label}: configured model changed; reload the PMS selection")
        except CloudReadinessFailure as error:
            unavailable.append(str(error))
    if unavailable:
        raise CloudReadinessFailure("; ".join(unavailable))


def verify_with_retries(demo):
    """Read-only access checks may retry; this never repeats model inference."""
    for attempt in range(1, 6):
        try:
            demo.verify_patient_access()
            return True
        except (ReadinessFailure, httpx.HTTPError, OSError) as error:
            detail = str(error) if isinstance(error, ReadinessFailure) else "PMS readiness connection failed"
            if attempt == 5:
                if isinstance(error, CloudReadinessFailure):
                    message(
                        "WARN",
                        detail
                        + ". Opening with cloud readiness unverified; questions retain their access checks and retry policy.",
                    )
                    return False
                raise RuntimeError("PMS model access failed after 5 attempts: " + detail) from None
            message(
                "RETRY",
                f"Model access check {attempt}/5 failed: {detail}; retrying in {2 ** (attempt - 1)} seconds",
            )
            time.sleep(2 ** (attempt - 1))
