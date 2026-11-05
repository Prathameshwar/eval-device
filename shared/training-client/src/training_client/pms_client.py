import asyncio
import json
from uuid import UUID, uuid4

import httpx

from .model_route import interactive_speech


class ClientError(RuntimeError):
    def __init__(self, message, *, code=None, retry_exhausted=False):
        super().__init__(message)
        self.code = code
        self.retry_exhausted = retry_exhausted


BUSY_CODES = frozenset({"llm_busy", "speech_busy", "concurrency_limit"})
# Readiness answers that mean "the probe went unanswered", not "this turn cannot work". They have
# already been retried at the source, and the submission reports its own outcome, so they downgrade
# a readiness check to a warning instead of refusing the operator's question. Deliberately narrow:
# rejected credentials, a missing deployment, a model mismatch and exhausted quota still block.
SOFT_READINESS_CODES = frozenset({"llm_unavailable", "llm_timeout"})
BUSY_DELAYS = (1, 2, 3, 4, 5)


async def retry_busy(
    operation, emit, label, queued, can_retry=lambda: True, *, rounds=1, round_pause_seconds=3
):
    """Only explicit capacity rejections are safe to resubmit; never replay unknown outcomes."""
    retries_per_round, retrying = len(BUSY_DELAYS), False
    retries = retries_per_round * rounds
    try:
        for attempt in range(retries + 1):
            try:
                return await operation()
            except ClientError as error:
                if error.code not in BUSY_CODES or not can_retry():
                    raise
                if attempt == retries:
                    exhausted = (
                        f"{retries} retries" if rounds == 1 else f"{rounds} rounds ({retries} retries)"
                    )
                    raise ClientError(
                        f"{label} is still busy after {exhausted}. "
                        "Start the microphone again or resend the question.",
                        code=error.code,
                        retry_exhausted=True,
                    ) from None
                if not retrying:
                    retrying = True
                    emit("retrying", True)
                round_index, retry_index = divmod(attempt, retries_per_round)
                status = {
                    "label": label,
                    "round": round_index + 1,
                    "rounds": rounds,
                    "retry": retry_index + 1,
                    "retries": retries_per_round,
                }
                if round_index and retry_index == 0:
                    emit(
                        "retry_status",
                        {**status, "phase": "between_rounds", "wait_seconds": round_pause_seconds},
                    )
                    emit(
                        "state",
                        f"{label} busy; {queued} retained. Round {round_index}/{rounds} complete; "
                        f"next round in {round_pause_seconds} s. Listening and speaking paused.",
                    )
                    await asyncio.sleep(round_pause_seconds)
                round_status = f"Round {round_index + 1}/{rounds}. " if rounds > 1 else ""
                delay = BUSY_DELAYS[retry_index]
                emit("retry_status", {**status, "phase": "waiting", "wait_seconds": delay})
                emit(
                    "state",
                    f"{label} busy; {queued} retained. {round_status}"
                    f"Retry {retry_index + 1}/{retries_per_round} in {delay} s. "
                    "Listening and speaking paused.",
                )
                await asyncio.sleep(delay)
                emit("retry_status", {**status, "phase": "submitting", "wait_seconds": 0})
                emit(
                    "state",
                    f"{label}: {round_status}retry {retry_index + 1}/{retries_per_round} in progress; "
                    f"{queued} retained. "
                    "Listening and speaking paused.",
                )
    finally:
        if retrying:
            emit("retrying", False)


def pms_error(value):
    error = value.get("error") if isinstance(value, dict) else None
    code = error.get("code", "pms_unavailable") if isinstance(error, dict) else "pms_unavailable"
    messages = {
        "invalid_device_credential": "Device access was revoked or replaced. Restart Human-test, choose Change connection, and enter a new enrollment token.",
        "device_not_enrolled": "This device needs enrollment. Restart Human-test and choose Change connection.",
        "model_selection_changed": "Model settings changed. Return to Models and reload before asking another question.",
        "device_models_required": "Ask Platform Admin to select models for this device.",
        "model_profile_required": "Ask Platform Admin to select models for this device.",
        "device_inactive": "The registered device is inactive or not enrolled. Ask the tenant administrator to check its status.",
        "profile_has_unpublished_changes": "The device models changed. Reload the assigned models.",
        "external_calls_disabled": "Cloud calls are disabled in PMS. Enable them on the server or choose local models.",
        "speech_disabled": "Cloud transcription is disabled. Enable PMS_SPEECH_ENABLED on the server or choose local speech.",
        "llm_disabled": "Model responses are disabled. Enable PMS_LLM_ENABLED on the server before continuing.",
        "patient_context_limit_required": "Ask Platform Admin to set the LLM context size before using a patient case.",
        "provider_disabled": "The selected provider is disabled in PMS platform settings. Contact the platform administrator.",
        "model_profile_incomplete": "No conversation model is assigned. Ask Platform Admin to configure this device.",
        "interactive_speech_unavailable": "This device has no supported interactive speech model. Use typing, or ask Platform Admin to assign local Whisper or Azure OpenAI Whisper.",
        "llm_connection_inactive": "The assigned conversation model is inactive. Ask Platform Admin to check this device's models.",
        "speech_connection_inactive": "The assigned speech model is inactive. Ask Platform Admin to check this device's models.",
        "speech_submission_unknown": "The transcription outcome is unknown. Use Check last request; audio was not replayed.",
        "llm_transport_unknown": "The response outcome is unknown. Use Check last request before submitting again.",
        "llm_timeout": "The response timed out. Use Check last request before submitting again.",
        "speech_daily_limit": "Daily cloud speech capacity has been reached.",
        "speech_storage_limit": "Speech recording storage is full. Allow retention cleanup or ask the administrator.",
        "llm_invalid_parameters": "The selected model rejected its parameters. Check its PMS model capability settings.",
        "llm_deployment_not_found": "The configured cloud model/deployment was not found. Ask Platform Admin to check its model settings.",
        "llm_credentials_rejected": "The cloud model rejected its credentials. Ask Platform Admin to update the model.",
        "patient_setup_changed": "The setup changed elsewhere. Return to Practice setup and Reload from PMS.",
        "patient_case_changed": "The case was updated. Reload from PMS before saving.",
        "patient_case_inactive": "This patient case is no longer active. Reload and choose another case.",
        "patient_case_mismatch": "The case, specialty or patient profile changed. Reload from PMS.",
        "scenario_unavailable": "This scenario is no longer available. Reload from PMS and choose another published scenario in this app.",
        "scenario_language_unavailable": "This scenario is not ready in the selected language. Reload from PMS and choose an available language in this app.",
        "patient_language_unavailable": "This case or patient profile is incomplete in the selected language. Choose another language or ask your tenant clinical author to complete it.",
        "legacy_patient_setup": "This historical setup uses a global case. Choose an active tenant case and save it before starting a new interview.",
        "patient_context_too_long": "The question is too long for the model with its patient context. Ask a shorter question.",
        "permission_denied": "Your account lacks permission for this operation. Ask your tenant administrator to check your access.",
        "scope_unavailable": "This operation requires organization-wide access. Ask your tenant administrator to check your scope.",
        "invalid_request": "Check the selected case and observation values, then try again.",
        "llm_busy": "The response model is busy.",
        "llm_unavailable": "PMS could not reach the response model's provider. "
        "Ask Platform Admin to check the model settings if this keeps happening.",
        "llm_daily_limit": "Your organization's daily online input/output token allowance is reached. It resets at 00:00 UTC.",
        "llm_daily_request_limit": "Your organization's daily online request allowance is reached. It resets at 00:00 UTC.",
        "version_conflict": "These settings changed elsewhere. Refresh Models before saving.",
        "llm_connection_changed": "The conversation model changed. Reload the assigned models.",
        "speech_connection_changed": "The speech model changed. Reload the assigned models.",
        "connection_unvalidated": "Ask Platform Admin to check the selected model settings.",
        "maintenance_mode": "PMS is in maintenance mode. Model activation is paused.",
    }
    if not isinstance(code, str) or len(code) > 80 or not code.replace("_", "").isalnum():
        code = "pms_unavailable"
    return ClientError(messages.get(code, "PMS: " + code), code=code)


class PMSClient:
    def __init__(self, settings):
        self.assigned_session_id = None
        self.settings = settings
        self.http = httpx.AsyncClient(
            base_url=settings.pms_url.rstrip("/"),
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(connect=3, read=settings.timeout_seconds, write=5, pool=2),
            headers={"Authorization": "Bearer " + settings.pms_token.get_secret_value()},
        )
        self.base = f"/api/v1/organizations/{settings.organization_id}/llm"
        self.last_request = None
        self.practice = None
        self.practice_document = None
        self.model_route = None
        self.conversation = None
        self.conversation_start_key = None
        self.conversation_start_payload = None
        self.last_speech_request = None
        # A later successful question must not erase an unresolved submission's lookup key.
        self.recovery_request = None
        self._capture_limit = settings.max_question_seconds
        self.organization_base = f"/api/v1/organizations/{settings.organization_id}"
        self.practice_base = f"/api/v1/organizations/{settings.organization_id}/patient-practice"

    async def local_history(self, limit=10):
        return await self.json("GET", self.base + "/local-conversation-turns", params={"limit": limit})

    async def catalog(self):
        return await self.json("GET", self.practice_base + "/catalog")

    async def model_config(self, profile_id=None):
        # A bound desktop always follows its device's current assignment. Its saved
        # profile ID is only a stale snapshot and must not pin a former assignment.
        params = (
            {"device_id": str(self.settings.device_id)}
            if self.settings.device_id
            else {"profile_id": str(profile_id)}
            if profile_id
            else {}
        )
        return await self.json("GET", self.organization_base + "/model-config", params=params)

    async def check_route(self, route):
        """Check the assigned models without changing the active desktop route."""
        self.validate_route(route)
        ready = await self.json("GET", self.base + f"/models/{route['llm']['connection_id']}/status")
        expected = "declared" if route["llm"]["mode"] == "local" else "ready"
        if ready.get("status") != expected or ready.get("revision") != route["llm"]["connection_revision"]:
            raise ClientError("The conversation model changed. Reload the assigned models.")
        if interactive_speech(route) and route["audio"]["mode"] == "cloud":
            await self.json(
                "GET", self.organization_base + "/speech/status", params={"profile_id": route["profile_id"]}
            )
        current = await self.model_config(route["profile_id"])
        if current["configuration_hash"] != route["configuration_hash"]:
            raise ClientError("The assigned models changed during the check. Reload them.")

    @staticmethod
    def validate_route(route):
        cloud_speech = interactive_speech(route) and route["audio"]["mode"] == "cloud"
        remote = cloud_speech or route["llm"].get("requires_external", route["llm"]["mode"] == "cloud")
        if remote and not route["cloud_allowed"]:
            raise pms_error({"error": {"code": "external_calls_disabled"}})
        if route.get("maintenance_mode"):
            raise pms_error({"error": {"code": "maintenance_mode"}})
        if route.get("llm_enabled") is False:
            raise pms_error({"error": {"code": "llm_disabled"}})
        if cloud_speech and route.get("speech_enabled") is False:
            raise pms_error({"error": {"code": "speech_disabled"}})
        if (cloud_speech or route["llm"].get("provider") == "azure_openai") and route.get(
            "azure_enabled"
        ) is False:
            raise pms_error({"error": {"code": "provider_disabled"}})

    def use_models(self, route):

        try:
            self.validate_route(route)
            profile_id = UUID(route["profile_id"])
            connection_id = UUID(route["llm"]["connection_id"])
            audio_mode, audio_model, seconds = (
                route["audio"][key] for key in ("mode", "model", "max_seconds")
            )
            if (
                audio_mode not in {"local", "cloud"}
                or not isinstance(audio_model, str)
                or not 1 <= len(audio_model) <= 100
                or type(seconds) is not int
                or not 1 <= seconds <= 3600
            ):
                raise ValueError()
            capture_limit = min(self._capture_limit, seconds)
        except (KeyError, TypeError, ValueError):
            raise ClientError("Invalid PMS model configuration; previous selection retained") from None
        self.model_route = route
        self.settings.processing_profile_id = profile_id
        self.settings.connection_id = connection_id
        self.settings.audio_mode = audio_mode
        self.settings.audio_model = audio_model
        self.settings.speech_input_enabled = interactive_speech(route)
        self.settings.max_question_seconds = capture_limit

    async def speech_status(self):
        return await self.json(
            "GET",
            self.organization_base + "/speech/status",
            params={"profile_id": str(self.settings.processing_profile_id)},
        )

    async def case(self, template_id):
        return await self.json("GET", self.practice_base + "/cases/" + template_id)

    async def scenario_options(self):
        result = await self.json("GET", self.practice_base + "/scenario-options")
        cursor = result.get("next_cursor")
        while cursor:
            page = await self.json("GET", self.practice_base + "/scenario-options", params={"cursor": cursor})
            result["items"].extend(page["items"])
            cursor = page.get("next_cursor")
        return result

    async def selection(self):
        selected = (await self.json("GET", self.practice_base + "/scenario-selection"))["selection"]
        if selected:
            return selected
        try:
            return (await self.json("GET", self.practice_base + "/selection"))["selection"]
        except ClientError as exc:
            if exc.code != "permission_denied":
                raise
            return None

    async def save_selection(self, payload):
        return (await self.json("PUT", self.practice_base + "/selection", json=payload))["selection"]

    async def save_scenario_selection(self, payload):
        return (await self.json("PUT", self.practice_base + "/scenario-selection", json=payload))["selection"]

    def validate_selection(self, selection):
        if selection.get("legacy"):
            raise pms_error({"error": {"code": "legacy_patient_setup"}})
        if selection["language"] not in self.settings.language_choices:
            raise ClientError(
                "This speech model does not support the saved language; choose a supported language"
            )
        document = selection.get("document")
        if not isinstance(document, dict) or not document:
            raise ClientError("This practice setup has no case document. Reload from PMS.")

    def use_selection(self, selection):
        self.validate_selection(selection)
        document = selection["document"]
        self.practice = {"practice_id": selection["id"], "practice_revision": selection["revision"]}
        # `practice` is sent to PMS verbatim; the document is kept only for a local turn, which
        # builds the patient prompt on this machine from the case PMS published.
        self.practice_document = document
        self.conversation = None
        self.conversation_start_key = None
        self.conversation_start_payload = None
        self.settings.language = selection["language"]
        self.last_request = None

    @property
    def practice_case(self):
        """Everything a local turn needs to reproduce the platform's patient context."""
        if not self.practice or not self.practice_document:
            return None
        return {**self.practice, "document": self.practice_document, "conversation": self.conversation}

    async def ensure_conversation(self, input_source="text"):
        from datetime import UTC, datetime

        from training_contracts import fingerprint
        from training_contracts.conversation.context import ConversationContext

        if not self.practice:
            return None
        if self.conversation is None:
            self.conversation_start_key = self.conversation_start_key or str(uuid4())
            payload = {
                "request_key": self.conversation_start_key,
                **({"assigned_session_id": self.assigned_session_id} if self.assigned_session_id else {}),
                **self.practice,
                "connection_id": str(self.settings.connection_id),
                "language": self.settings.language,
                "input_mode": input_source,
                "output_mode": "speech" if self.settings.speaker_output else "text",
                "department_id": str(self.settings.department_id) if self.settings.department_id else None,
                **(
                    {
                        "profile_revision_id": self.model_route["profile_revision_id"],
                        "configuration_hash": self.model_route["configuration_hash"],
                    }
                    if self.model_route
                    else {}
                ),
            }
            # Starting a context performs no inference. A transport retry retains this
            # idempotency key; it cannot create another interview or model submission.
            if self.conversation_start_payload is None:
                self.conversation_start_payload = payload
            # An uncertain start retains its complete request, including input/output
            # mode. Toggling playback or switching to typing must not reuse its key
            # with a different body and trigger an idempotency conflict.
            value = await self.json(
                "POST", self.practice_base + "/conversations", json=self.conversation_start_payload
            )
            context = ConversationContext.model_validate(value["context"])
            context.validate_pack()
            if (
                value["status"] != "active"
                or context.language != self.settings.language
                or str(context.practice_id) != str(self.practice["practice_id"])
                or context.practice_revision != self.practice["practice_revision"]
                or context.case_snapshot_hash != fingerprint(self.practice_document)
                or str(context.organization_id) != str(self.settings.organization_id)
                or str(context.connection_id) != str(self.settings.connection_id)
            ):
                raise ClientError("Patient conversation configuration changed; reload setup")
            self.conversation = value
        else:
            # Recheck current permissions/lifecycle before local inference. This GET carries
            # no question or answer and never submits a generation or retries one.
            value = await self.json(
                "GET",
                self.practice_base + "/conversations/" + self.conversation["context"]["conversation_id"],
            )
            if value["status"] != "active" or value["context"] != self.conversation["context"]:
                raise ClientError(
                    "Patient conversation changed; start a new interview", code="conversation_closed"
                )
        context = ConversationContext.model_validate(self.conversation["context"])
        if context.expires_at <= datetime.now(UTC):
            raise ClientError("Conversation expired; start a new interview", code="conversation_closed")
        context.validate_pack()
        callback = getattr(self, "on_conversation", None)
        if callback:
            callback(self.conversation)
        return self.conversation

    async def close_conversation(self, identity):
        return await self.json("POST", self.practice_base + "/conversations/" + identity + "/close")

    async def close(self):
        await self.http.aclose()

    async def json(self, method, path, *, expected=200, **kwargs):
        async with asyncio.timeout(self.settings.timeout_seconds):
            async with self.http.stream(method, path, **kwargs) as response:
                data = bytearray()
                async for block in response.aiter_bytes():
                    data.extend(block)
                    if len(data) > 131072:
                        raise ClientError("PMS response limit exceeded")
                value = json.loads(data)
                if response.status_code != expected:
                    raise pms_error(value)
                if not isinstance(value, dict):
                    raise ClientError("Invalid PMS response")
                return value

    async def preflight(self):
        return await self.json("GET", self.base + f"/models/{self.settings.connection_id}/status")

    async def record_local_turn(self, payload):
        """Metadata for a turn this machine executed; PMS was not on its data path."""
        return await self.json(
            "POST",
            self.base + "/local-turns",
            json={
                **payload,
                "department_id": str(self.settings.department_id) if self.settings.department_id else None,
            },
        )

    async def status(self, request_key=None):
        request_key = request_key or self.last_request
        if not request_key:
            raise ClientError("No submitted request")
        return await self.json("GET", self.base + "/requests/" + request_key)

    async def speech_request_status(self, request_key=None):
        request_key = request_key or self.last_speech_request
        if not request_key:
            raise ClientError("No submitted speech request")
        return await self.json("GET", self.organization_base + "/speech/requests/" + request_key)

    async def answer(self, messages, emit):
        delivered = False

        def observe(kind, value):
            nonlocal delivered
            if kind in {"answer_delta", "answer"} and value:
                delivered = True
            emit(kind, value)

        try:
            return await retry_busy(
                lambda: self._answer_once(messages, observe),
                emit,
                "Response model",
                "question",
                can_retry=lambda: not delivered,
            )
        except (httpx.HTTPError, TimeoutError):
            self.recovery_request = ("answer", self.last_request)
            raise ClientError(
                "Response connection interrupted; use Check last request before submitting again"
            ) from None
        except (ClientError, ValueError) as error:
            if delivered or not isinstance(error, ClientError) or error.code not in BUSY_CODES:
                self.recovery_request = ("answer", self.last_request)
            raise

    async def _answer_once(self, messages, emit):
        # Each attempt follows a definitive rejection. Never reuse a failed
        # provider request's key, which correctly returns its saved failure.
        self.last_request = str(uuid4())
        payload = {
            "request_key": self.last_request,
            "connection_id": str(self.settings.connection_id),
            "department_id": str(self.settings.department_id) if self.settings.department_id else None,
            "messages": messages[-1:] if self.conversation else messages,
            "stream": self.settings.streaming,
            "language": self.settings.language,
            **(self.practice or {}),
            **(
                {"conversation_id": self.conversation["context"]["conversation_id"]}
                if self.conversation
                else {}
            ),
            **(
                {
                    "profile_revision_id": self.model_route["profile_revision_id"],
                    "configuration_hash": self.model_route["configuration_hash"],
                }
                if self.model_route
                else {}
            ),
        }
        if not self.settings.streaming:
            result = await self.json("POST", self.base + "/completions", json=payload)
            self.validate_done(result)
            emit("answer", result["text"])
            return result
        received = 0
        buffer = bytearray()
        async with asyncio.timeout(self.settings.timeout_seconds):
            async with self.http.stream("POST", self.base + "/completions", json=payload) as response:
                if response.status_code != 200:
                    data = bytearray()
                    async for block in response.aiter_bytes():
                        data.extend(block)
                        if len(data) > 16384:
                            raise ClientError("PMS rejected the request")
                    try:
                        value = json.loads(data)
                    except ValueError:
                        value = {}
                    raise pms_error(value)
                async for block in response.aiter_bytes():
                    received += len(block)
                    if received > 1048576:
                        raise ClientError("PMS stream limit exceeded")
                    buffer.extend(block)
                    while b"\n" in buffer:
                        line, _, rest = buffer.partition(b"\n")
                        buffer = bytearray(rest)
                        if len(line) > 65536:
                            raise ClientError("PMS event limit exceeded")
                        if not line.startswith(b"data:"):
                            continue
                        event = json.loads(line[5:].strip())
                        if not isinstance(event, dict):
                            raise ClientError("Invalid PMS event")
                        if event.get("type") == "delta":
                            value = event.get("text")
                            if not isinstance(value, str):
                                raise ClientError("Invalid PMS text")
                            emit("answer_delta", value)
                        elif event.get("type") == "error":
                            raise pms_error({"error": {"code": event.get("code", "unknown")}})
                        elif event.get("type") == "done":
                            self.validate_done(event)
                            emit("answer", event["text"])
                            return event
                    if len(buffer) > 65536:
                        raise ClientError("PMS event limit exceeded")
        raise ClientError("PMS connection ended before completion; use Check request, not automatic replay")

    def validate_done(self, result):
        if (
            result.get("request_key") != self.last_request
            or result.get("status") != "succeeded"
            or not isinstance(result.get("text"), str)
            or not result["text"].strip()
            or len(result["text"].encode()) > 32000
            or result.get("finish_reason") not in ("stop", "length")
        ):
            raise ClientError("Invalid or incomplete PMS result")
