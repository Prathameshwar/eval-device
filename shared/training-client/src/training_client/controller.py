import asyncio
import time
from datetime import UTC, datetime
from uuid import uuid4

import httpx
from local_model_client import llm as local_llm
from training_contracts.languages import get_pack

from . import audio_client, cloud_audio, local_turn
from .conversation_history import HistoryRecorder, MetricsReporter, merge_history
from .input_filter import InputFilter, InputFilterError
from .model_route import interactive_speech
from .performance import PlaybackGate, TurnTiming
from .pms_client import BUSY_CODES, SOFT_READINESS_CODES, ClientError, PMSClient, retry_busy
from .speech import patient_gender


def heard(text):
    """Does recognized speech contain words/numbers instead of only noise or punctuation?

    Any letter or digit in any script counts, preserving genuine short questions.
    """
    return any(character.isalnum() for character in text)


class Controller:
    def __init__(self, settings, emit, *, inference=None):
        settings.require_credentials()
        self.settings, self.emit = settings, emit
        self.inference = inference or audio_client.connection(settings)
        self.input_filter = InputFilter(settings.resolve_path(settings.input_ignore_file))
        self.pms = PMSClient(settings)
        if getattr(self.inference, "remote", False):
            self.inference.context = lambda: (
                self.pms.conversation["context"]["conversation_id"] if self.pms.conversation else None
            )
        self.history = []
        self._conversation_generation = 0
        self._closing_tasks = set()
        self.busy = False
        self.voice_gender = "male"
        self._preflight_at = 0.0
        self.performance = None
        self._local_http = None
        self.conversation_id, self.sequence = str(uuid4()), 0
        self.sync = None
        if settings.session_sync_enabled and settings.device_id:
            from .session_sync import SessionSync

            self.sync = SessionSync(settings, emit)
            self.pms.on_conversation = self.sync.activate
        self.recorder = None
        self.metrics_reporter = MetricsReporter(self.pms.record_local_turn, lambda k, v: self.emit(k, v))
        if settings.history_enabled:
            try:
                self.recorder = HistoryRecorder(settings, lambda k, v: self.emit(k, v))
                self.recorder.busy = lambda: self.busy or bool(self.sync and self.sync.active_work)
            except (ValueError, KeyError, IndexError, TypeError):
                self.emit("history_status", {"status": "not_saved", "turn_key": None})

    async def refresh_local_models(self):
        """Refresh inference metadata; an unavailable optional TTS service leaves text usable."""
        from local_model_client import ConnectionError, client_key
        from pydantic import SecretStr

        connection = self.inference
        info = None
        key = connection.key
        try:
            info = connection.remember(await connection.async_request("GET", "/v1/capabilities"))
            if not getattr(connection, "remote", False):
                key = key or await asyncio.to_thread(client_key, connection.state)
                self.settings.local_models_key = SecretStr(key)
                connection.key = key
        except ConnectionError:
            connection.clear_capabilities()
        self.settings.local_models_capabilities = info or {}
        self.emit("local_models_metadata", None)
        return info is not None

    def local_model(self):
        """A model published as local runs on this machine, so this app executes the turn."""
        if self._local_http is None:
            self._local_http = local_llm.new_client(self.settings.timeout_seconds)
        model = local_turn.local_model(self.pms.model_route, self.settings, client=self._local_http)
        if getattr(self.inference, "remote", False):
            model.connection = self.inference
        return model

    def runs_locally(self):
        return bool(self.pms.model_route) and local_turn.runs_locally(self.pms.model_route)

    def speech_available(self):
        return interactive_speech(self.pms.model_route)

    async def preflight(self):
        if not self.speech_available():
            raise ClientError(
                "This device has no supported interactive speech model. Use typing or ask Platform Admin to assign local Whisper / Azure OpenAI Whisper."
            )
        if self.settings.language not in self.settings.language_choices:
            required = (
                ", ".join(get_pack(code).name for code in self.settings.language_choices)
                or "an installed supported language"
            )
            raise ClientError(
                f"This speech model requires {required}. Return to Practice setup and save {required}."
            )
        if self.settings.use_pms_models:
            route = await self.pms.model_config(self.settings.processing_profile_id)
            if (
                self.pms.model_route
                and route["configuration_hash"] != self.pms.model_route["configuration_hash"]
            ):
                raise ClientError("Model configuration changed. Return to setup and reload before recording.")
            self.pms.use_models(route)
            if not self.speech_available():
                raise ClientError(
                    "Speech recognition is unavailable. Use typing or reload the device models."
                )
            if self.settings.language not in self.settings.language_choices:
                required = (
                    ", ".join(get_pack(code).name for code in self.settings.language_choices)
                    or "an installed supported language"
                )
                raise ClientError(
                    f"This speech model requires {required}. Return to Practice setup and save {required}."
                )
        # Current authenticated profile is still checked above on every question.
        # Actual ASR streams and local inference validate their accepted model;
        # only redundant technical readiness probes are cached.
        if self._preflight_at and time.monotonic() - self._preflight_at < 15:
            return
        speech_enabled = self.speech_available()
        if (
            speech_enabled
            and self.settings.audio_mode == "local"
            and not self.settings.local_models_key.get_secret_value()
            and not getattr(self.inference, "remote", False)
        ):
            raise ClientError("Connect to Manage Local Models for local speech")
        # Validate local execution before creating any probe coroutines. A missing
        # key or malformed route must not leave unawaited speech checks behind.
        local = self.runs_locally()
        model = self.local_model() if local else None
        speech_check = (
            (
                self.pms.speech_status()
                if self.settings.audio_mode == "cloud"
                else audio_client.preflight(self.settings, inference=self.inference)
            )
            if speech_enabled
            else None
        )
        busy = False
        unproven = []

        async def readiness(check, label, cloud):
            """Run one readiness probe and classify its answer.

            Each leg is timed and named separately: the original intermittent failure could not be
            attributed to a provider, so a warning that says which check went unanswered and how
            long it waited is the difference between a diagnosable report and a bare code.
            """
            nonlocal busy
            began = time.monotonic()
            try:
                await check
            except ClientError as error:
                if cloud and error.code in BUSY_CODES:
                    # The authenticated route is already loaded. Capture the bounded
                    # utterance; admission will enforce capacity and all current policy.
                    busy = True
                    return
                if error.code in SOFT_READINESS_CODES:
                    # A probe is not the turn. It was already retried where it was made, and the
                    # submission reports its own outcome, so an unanswered check downgrades to a
                    # warning rather than discarding a question the operator is about to ask.
                    unproven.append((label, time.monotonic() - began))
                    return
                raise

        # A local model is never dialled by PMS, so its readiness is checked here.
        checks = [
            *(
                [readiness(speech_check, "speech", self.settings.audio_mode == "cloud")]
                if speech_check is not None
                else []
            ),
            readiness(
                local_turn.health(model) if local else self.pms.preflight(),
                "the response model",
                bool(self.pms.model_route and self.pms.model_route["llm"]["mode"] == "cloud"),
            ),
        ]
        tasks = [asyncio.create_task(check) for check in checks]
        try:
            await asyncio.gather(*tasks)
        finally:
            # A hard failure or operator cancellation ends every probe before the
            # next operation can begin or close the shared HTTP clients.
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        if unproven:
            waited = max(seconds for _, seconds in unproven)
            self.emit(
                "ready",
                f"Unverified: {' and '.join(label for label, _ in unproven)} did not answer a "
                f"readiness check after {waited:.1f} s. The question will still be sent and will "
                "report its own result.",
            )
        else:
            self.emit(
                "ready",
                "Models busy; captured questions will queue and retry"
                if busy
                else "ASR connected | PMS ready | LLM "
                + ("running on this laptop" if local else "connected"),
            )
        # Only a proven pair is worth caching. A degraded check is repeated on the next question,
        # so a provider that comes back is noticed instead of being assumed bad for 15 seconds.
        if not unproven:
            self._preflight_at = time.monotonic()

    def use_models(self, route):
        if self.busy:
            raise ClientError("Finish or cancel the current question before changing models")
        self.pms.use_models(route)
        self._preflight_at = 0.0
        self.reset()

    def reset(self):
        if self.busy:
            raise ClientError("Cancel the current question before reset")
        self.history = []
        self._conversation_generation += 1
        if self.sync:
            self.sync.end()
        previous = self.pms.conversation
        self.pms.conversation = None
        self.pms.conversation_start_key = None
        self.pms.conversation_start_payload = None
        if previous:

            async def finish():
                try:
                    await self.pms.close_conversation(previous["context"]["conversation_id"])
                except (ClientError, httpx.HTTPError, TimeoutError):
                    pass  # Closed locally; the server's bounded context expires independently.

            task = asyncio.create_task(finish())
            self._closing_tasks.add(task)
            task.add_done_callback(self._closing_tasks.discard)
        self.conversation_id, self.sequence = str(uuid4()), 0
        self.pms.last_request = None
        self.pms.last_speech_request = None
        self.pms.recovery_request = None

    def use_selection(self, selection):
        if self.busy:
            raise ClientError("Cancel the current question before changing the practice setup")
        self.pms.validate_selection(selection)
        self.reset()
        self.pms.use_selection(selection)
        self.voice_gender = patient_gender(selection)

    async def turn(self, frames, *, record_audio=True):
        if not self.speech_available():
            raise ClientError(
                "This device has no interactive speech model. Use typing or select local Whisper / Azure OpenAI Whisper in Configure model."
            )
        if self.busy:
            raise ClientError("A question is already active")
        self.busy = True
        if self.sync:
            self.sync.busy(True)
        generation = self._conversation_generation
        started = time.monotonic()
        timing = self.performance or TurnTiming()
        self.performance = timing
        timing.mark("worker")
        timing.mark("request")
        try:
            await self.pms.ensure_conversation("speech")
            if generation != self._conversation_generation:
                raise asyncio.CancelledError()
            if self.sync and record_audio:
                frames = self.record_frames(frames, self.sync.current)
            self.emit("new_turn", "")
            self.emit("state", "Listening")
            transcript = (
                await cloud_audio.transcribe(self.settings, self.pms, frames, self.emit)
                if self.settings.audio_mode == "cloud"
                else await audio_client.transcribe(self.settings, frames, self.emit, inference=self.inference)
            )
            if generation != self._conversation_generation:
                raise asyncio.CancelledError()
            timing.mark("transcript")
            return await self.respond(transcript, started)
        finally:
            try:
                await frames.aclose()
            finally:
                self.busy = False
                if self.sync:
                    self.sync.busy(False)
                self.performance = None

    async def text_turn(self, text):
        if self.busy:
            raise ClientError("A question is already active")
        text = text.strip()
        if not text or len(text) > 8000:
            raise ClientError("Enter a question of 1 to 8,000 characters")
        self.busy = True
        if self.sync:
            self.sync.busy(True)
        self.performance = self.performance or TurnTiming("text")
        self.performance.mark("worker")
        self.performance.mark("transcript")
        try:
            self.emit("new_turn", "")
            self.emit("transcript", text)
            return await self.respond(
                {"text": text, "asr_finalize_ms": 0}, time.monotonic(), input_source="text"
            )
        finally:
            self.busy = False
            if self.sync:
                self.sync.busy(False)
            self.performance = None

    async def record_frames(self, frames, sid):
        stream = str(uuid4())
        self.sync.audio_start(sid, stream)
        try:
            async for frame in frames:
                self.sync.audio(sid, stream, frame)
                yield frame
        finally:
            self.sync.audio_end(sid, stream)
            await frames.aclose()

    async def local_answer(self, messages, emit):
        """Inference stays local; optional archival cannot recover or replay inference."""
        self.pms.last_request = None
        model = self.local_model()
        delivered = False

        def observe(kind, value):
            nonlocal delivered
            if kind in {"answer_delta", "answer"} and value:
                delivered = True
            emit(kind, value)

        return await retry_busy(
            lambda: local_turn.answer(
                model,
                self.pms.model_route,
                self.pms.practice_case,
                messages,
                self.settings.language,
                observe,
            ),
            emit,
            "Local model",
            "question",
            can_retry=lambda: not delivered,
        )

    def ignore_input(self, transcript, started):
        metrics = {
            "asr_finalize_ms": transcript["asr_finalize_ms"],
            "llm_first_token_ms": None,
            "llm_total_ms": None,
            "pms_roundtrip_ms": None,
            "pms_first_content_ms": None,
            "turn_ms": round((time.monotonic() - started) * 1000),
            "request_key": None,
            "finish_reason": None,
            "provider_calls": 0,
        }
        self.emit("input_ignored", {"text": transcript["text"], "generation": self._conversation_generation})
        self.emit("metrics", metrics)
        return {"transcript": transcript["text"], "answer": None, "ignored": True, "metrics": metrics}

    async def respond(self, transcript, started, input_source="speech"):
        if len(transcript["text"]) > 8000:
            raise ClientError("The recognized question is too long; ask a shorter question")
        # Empty recognition is not an invitation to ask for clarification. This also
        # precedes the editable dictionary, which controls fillers rather than silence.
        if not transcript["text"].strip() or (input_source == "speech" and not heard(transcript["text"])):
            return self.ignore_input(transcript, started)
        try:
            if self.input_filter.ignores(transcript["text"], self.settings.language):
                return self.ignore_input(transcript, started)
        except InputFilterError as error:
            raise ClientError(str(error), code="input_ignore_configuration") from None
        generation = self._conversation_generation
        conversation = await self.pms.ensure_conversation(input_source)
        if conversation:
            self.conversation_id = conversation["context"]["conversation_id"]
        if generation != self._conversation_generation:
            raise asyncio.CancelledError()
        messages = [*self.history, {"role": "user", "content": transcript["text"]}]
        while len(messages) > 1 and (len(messages) > 13 or sum(len(m["content"]) for m in messages) > 16000):
            del messages[:2]
        self.emit("answer", "")
        self.emit("state", "Answering")
        llm_started = time.monotonic()
        timing = self.performance or TurnTiming(input_source)
        timing.mark("model_start")
        first_content = None

        def response_event(kind, value):
            nonlocal first_content
            if kind == "answer_delta" and value and first_content is None:
                first_content = round((time.monotonic() - llm_started) * 1000)
            if generation == self._conversation_generation:
                self.emit(kind, value)

        local = self.runs_locally()
        turn_key, occurred_at = str(uuid4()), datetime.now(UTC).isoformat()
        record = self.archive_context(transcript, input_source, turn_key, occurred_at) if local else None
        archive_id = self.sync.current if self.sync else None
        archive_turn = {
            "turn_key": turn_key,
            "occurred_at": occurred_at,
            "input_text": transcript["text"],
            "input_source": input_source,
            "execution": "local" if local else "cloud",
        }
        try:
            result = (
                await self.local_answer(messages, response_event)
                if local
                else await self.pms.answer(messages, response_event)
            )
        except asyncio.CancelledError:
            self.archive_finish(record, "cancelled")
            if self.sync:
                self.sync.turn(archive_id, {**archive_turn, "outcome": "cancelled", "response_text": None})
            raise
        except Exception:
            self.archive_finish(record, "failed")
            if self.sync:
                self.sync.turn(archive_id, {**archive_turn, "outcome": "failed", "response_text": None})
            raise
        if generation != self._conversation_generation:
            raise asyncio.CancelledError()
        timing.mark("answer")
        speech = {
            "text": get_pack(self.settings.language).spoken_text(result["text"]),
            "language": self.settings.language,
            "gender": self.voice_gender,
            "generation": self._conversation_generation,
            "archive_id": archive_id,
            "performance": timing,
        }
        if self.sync:
            gate = PlaybackGate()
            timing.mark("save_start")
            delivery_error = None
            try:
                self.emit("prepare_speech", {**speech, "gate": gate})
            except Exception as error:
                # A full/failed UI queue cannot discard a model result. Persist
                # first and propagate the display failure without releasing audio.
                delivery_error = error
            saved = False
            try:
                saved = await self.sync.save_turn(
                    archive_id, {**archive_turn, "outcome": "completed", "response_text": result["text"]}
                )
            finally:
                gate.resolve(saved and delivery_error is None)
            if not saved:
                self.archive_finish(record, "completed", result)
                raise ClientError(
                    "Answer displayed; local result save did not complete. Audio was withheld. Check sync before continuing."
                )
            timing.mark("saved")
            if delivery_error is not None:
                self.archive_finish(record, "completed", result)
                raise delivery_error
        self.history = [*messages, {"role": "assistant", "content": result["text"]}]
        # Only a genuine new answer is spoken; recovered results are displayed silently.
        if not self.sync:
            self.emit("speak", speech)
        metrics = {
            "asr_finalize_ms": transcript["asr_finalize_ms"],
            "llm_first_token_ms": result.get("first_token_ms"),
            "llm_total_ms": result.get("total_ms"),
            "pms_roundtrip_ms": round((time.monotonic() - llm_started) * 1000),
            "pms_first_content_ms": first_content,
            "turn_ms": round((time.monotonic() - started) * 1000),
            "request_key": self.pms.last_request,
            "finish_reason": result["finish_reason"],
        }
        self.emit("metrics", metrics)
        self.emit(
            "state",
            "Preparing audio"
            if self.settings.speaker_output
            else "Complete"
            if result["finish_reason"] == "stop"
            else "Complete (output limit reached)",
        )
        if local:
            event = local_turn.turn_event(
                self.pms.model_route,
                self.pms.practice_case,
                result,
                turn_key=turn_key,
                occurred_at=occurred_at,
            )
            event["department_id"] = str(self.settings.department_id) if self.settings.department_id else None
            if not self.archive_finish(record, "completed", result, event):
                self.metrics_reporter.enqueue(event)
        return {"transcript": transcript["text"], "answer": result["text"], "metrics": metrics}

    def archive_context(self, transcript, source, key, occurred_at):
        if not self.recorder:
            return None
        self.sequence += 1
        route, practice = self.pms.model_route, self.pms.practice_case
        return {
            "turn_key": key,
            "conversation_id": self.conversation_id,
            "sequence": self.sequence,
            **(
                {
                    "context_ref": {
                        key: self.pms.conversation["context"][key]
                        for key in (
                            "conversation_id",
                            "language_pack_version",
                            "language_pack_hash",
                            "compiler_version",
                        )
                    }
                }
                if self.pms.conversation
                else {}
            ),
            "department_id": str(self.settings.department_id) if self.settings.department_id else None,
            "profile_revision_id": route["profile_revision_id"],
            "configuration_hash": route["configuration_hash"],
            "connection_id": route["llm"]["connection_id"],
            "connection_revision": route["llm"]["connection_revision"],
            "model": route["llm"]["model"],
            "practice_id": str(practice["practice_id"]) if practice else None,
            "practice_revision": practice["practice_revision"] if practice else None,
            "practice_snapshot_hash": local_turn.fingerprint(practice["document"]) if practice else None,
            "language": local_turn.resolved_language(self.settings.language, transcript["text"]),
            "input_source": source,
            "audio_mode": self.settings.audio_mode if source == "speech" else "none",
            "input_text": transcript["text"],
            "occurred_at": occurred_at,
            "timings": {
                "asr_finalize_ms": transcript["asr_finalize_ms"],
                "total_ms": 0,
                "first_token_ms": None,
            },
        }

    def archive_finish(self, record, outcome, result=None, metrics=None):
        if record is None or self.recorder is None:
            return False
        result = result or {}
        value = {
            **record,
            "completed_at": datetime.now(UTC).isoformat(),
            **(
                {"context_ref": {**record["context_ref"], "prompt_hash": result.get("prompt_hash")}}
                if record.get("context_ref")
                else {}
            ),
            "outcome": outcome,
            "response_text": result.get("text"),
            "answer_source": result.get("answer_source", "plain_completion")
            if outcome == "completed"
            else None,
            **({"policy_version": result["policy_version"]} if result.get("policy_version") else {}),
            "finish_reason": result.get("finish_reason"),
            "timings": {
                **record["timings"],
                "total_ms": result.get("total_ms") or 0,
                "first_token_ms": result.get("first_token_ms"),
            },
        }
        return self.recorder.enqueue(value, metrics)

    async def history_items(self):
        pending = self.recorder.pending() if self.recorder else []
        failures = self.recorder.failures if self.recorder else 0
        note = f" ({failures} history save failures)" if failures else ""
        try:
            remote = await self.pms.local_history()
            return {
                "items": merge_history(remote["items"], pending),
                "message": "Latest completed local exchanges" + note,
            }
        except (ClientError, httpx.HTTPError, ValueError, KeyError):
            return {
                "items": merge_history([], pending),
                "message": "PMS history unavailable; local pending records" + note,
            }

    async def record_local_turn(self, result):
        try:
            await self.pms.record_local_turn(
                local_turn.turn_event(self.pms.model_route, self.pms.practice_case, result)
            )
        except (ClientError, httpx.HTTPError, OSError, TimeoutError, ValueError, KeyError, TypeError):
            self.emit("state", "Answer delivered; PMS did not record this local turn's metrics")

    async def close(self):
        async def finish_conversations():
            tasks = list(self._closing_tasks)
            if self.pms.conversation:
                tasks.append(
                    asyncio.create_task(
                        self.pms.close_conversation(self.pms.conversation["context"]["conversation_id"])
                    )
                )
            if tasks:
                try:
                    # Server contexts expire independently. An unavailable API must
                    # not consume the desktop's shutdown budget before disk flush.
                    async with asyncio.timeout(1):
                        await asyncio.gather(*tasks, return_exceptions=True)
                except TimeoutError:
                    pass

        try:
            results = await asyncio.gather(
                finish_conversations(),
                self.metrics_reporter.close(),
                *([self.sync.close()] if self.sync else []),
                *([self.recorder.close()] if self.recorder else []),
                return_exceptions=True,
            )
            failures = [result for result in results if isinstance(result, BaseException)]
            if failures:
                raise RuntimeError("Client shutdown did not finish saving local state") from failures[0]
        finally:
            try:
                if self._local_http is not None:
                    await self._local_http.aclose()
            finally:
                await self.pms.close()
