"""Run a patient turn on this machine when PMS publishes a local model route.

PMS stays authoritative for the case, the persona, the language and the model selection: the
route and the published case document both come from it. Only the inference happens here, so
with a local model no prompt, transcript or answer is sent to the platform. The routing and
disclosure guards are the shared ones, so a local answer is built exactly as a cloud answer.
"""

from datetime import UTC, datetime
from uuid import uuid4

from local_model_client.llm import LocalModel, message_for
from training_contracts import fingerprint
from training_contracts.conversation.context import ConversationContext
from training_contracts.languages import get_pack
from training_contracts.patient_conversation import (
    HISTORY_MESSAGES,
    OUTPUT_TOKENS,
    conversation_context,
    conversation_history,
    fit_conversation_prompt,
    output_budget,
    resolved_language,
    run_conversation,
)
from training_contracts.patient_turn import TurnError

from .pms_client import ClientError

ROLES = frozenset({"system", "developer", "user"})
INVALID = "Invalid PMS model configuration for local execution; reload Models"


def runs_locally(route):
    """A local model is reachable only from the machine it runs on, so the caller executes it."""
    llm = route.get("llm") if isinstance(route, dict) else None
    return isinstance(llm, dict) and llm.get("mode") == "local" and llm.get("execution") == "caller"


def local_model(route, settings, *, client=None):
    """Build the model client from the published route; the key never comes from PMS."""
    llm = route["llm"]
    key = settings.local_models_key.get_secret_value()
    if settings.inference_url:
        # Native tokenizer budgets are cached by connection identity, including the remote host.
        key = "remote:" + settings.inference_url + ":" + str(settings.inference_host_id)
    if not key and not settings.inference_url:
        raise ClientError(
            "Start the assigned service in Manage Local Models and reconnect Human-test.",
            code="llm_local_key_missing",
        )
    port, model, cap = settings.local_models_port, llm.get("model"), llm.get("local_context_tokens")
    if (
        type(port) is not int
        or not 1 <= port <= 65535
        or not isinstance(model, str)
        or not 1 <= len(model) <= 200
        or type(cap) is not int
        or not 512 <= cap <= 1048576
        or type(llm.get("max_tokens")) is not int
        or not 1 <= llm["max_tokens"] <= 100000
        or llm.get("instruction_role") not in ROLES
        or not isinstance(llm.get("system_prompt"), str)
    ):
        raise ClientError(INVALID, code="llm_local_route_invalid")
    return LocalModel(port, key, model, context_cap=cap, timeout=settings.timeout_seconds, client=client)


async def health(model):
    """Readiness for a local model: the server answers and is serving the published model."""
    try:
        await model.health()
    except TurnError as error:
        raise ClientError(message_for(error.code), code=error.code) from None


def validate_result(event):
    text = event.get("text")
    if not isinstance(text, str) or not text.strip() or len(text.encode()) > 32000:
        raise ClientError("The local model produced an unusable answer. Ask the question again.")
    return event


def turn_event(route, practice, event, *, turn_key=None, occurred_at=None):
    """Counts, timings and the authored routing outcome. No prompt or answer text is included."""
    usage = event.get("usage") or {}
    return {
        "turn_key": str(turn_key or uuid4()),
        "profile_revision_id": route["profile_revision_id"],
        "configuration_hash": route["configuration_hash"],
        "connection_id": route["llm"]["connection_id"],
        "connection_revision": route["llm"]["connection_revision"],
        "practice_id": str(practice["practice_id"]) if practice else None,
        "practice_revision": practice["practice_revision"] if practice else None,
        "practice_snapshot_hash": fingerprint(practice["document"]) if practice else None,
        "language": event["language"],
        "answer_source": event.get("answer_source", "plain_completion"),
        **(
            {
                "context_ref": {
                    key: event[key]
                    for key in (
                        "conversation_id",
                        "language_pack_version",
                        "language_pack_hash",
                        "compiler_version",
                        "prompt_hash",
                    )
                }
            }
            if event.get("conversation_id")
            else {}
        ),
        **({"policy_version": event["policy_version"]} if event.get("policy_version") else {}),
        "routing_status": event.get("routing_status"),
        "kind": event.get("kind"),
        "topics": event.get("topics", []),
        "provider_calls": event.get("provider_calls", 1),
        "finish_reason": event["finish_reason"],
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "first_token_ms": event.get("first_token_ms"),
        "total_ms": event.get("total_ms") or 0,
        "occurred_at": occurred_at or datetime.now(UTC).isoformat(),
    }


async def answer(model, route, practice, messages, language, emit, *, diagnostic=False):
    """One local turn. Returns the same event shape the platform returns for a cloud turn."""
    llm = route["llm"]
    try:
        messages = conversation_history(messages, llm.get("history_messages", HISTORY_MESSAGES))
        resolved = resolved_language(language, messages[-1]["content"])
        if practice is None:
            # No patient is selected, so there is no case to route against: one plain turn.
            event = await model.complete(
                [
                    {
                        "role": llm["instruction_role"],
                        "content": llm["system_prompt"] + "\nReply in " + get_pack(language).name + ".",
                    },
                    *messages,
                ],
                llm["max_tokens"],
            )
        else:
            interview = practice.get("conversation")
            if interview:
                pinned = ConversationContext.model_validate(interview["context"])
                pinned.validate_pack()
                if (
                    pinned.language != resolved
                    or pinned.execution != "caller"
                    or str(pinned.practice_id) != str(practice["practice_id"])
                    or pinned.practice_revision != practice["practice_revision"]
                    or pinned.case_snapshot_hash != fingerprint(practice["document"])
                    or str(pinned.connection_id) != str(llm["connection_id"])
                    or pinned.connection_revision != llm["connection_revision"]
                    or pinned.configuration_hash != route["configuration_hash"]
                    or pinned.expires_at <= datetime.now(UTC)
                    or interview["status"] != "active"
                ):
                    raise ClientError(
                        "Conversation changed; reload the practice setup", code="conversation_context_changed"
                    )
                context = dict(interview["snapshot"])
                context["conversation_id"] = str(pinned.conversation_id)
            elif diagnostic:
                # Explicit evaluation harness only; no runtime request enables this.
                context = conversation_context(practice["document"], resolved, messages[-1]["content"])
            else:
                raise ClientError("Start a patient conversation first", code="conversation_required")
            maximum = output_budget(llm["max_tokens"], llm.get("conversation_tokens", OUTPUT_TOKENS))
            prompt = [{"role": llm["instruction_role"], "content": context["system"]}, *messages]
            prompt, budget = await fit_conversation_prompt(model, prompt, maximum, context=context)
            context["budget"] = {
                "conversation": budget,
                "practice_id": str(practice["practice_id"]),
                "practice_revision": practice["practice_revision"],
                "snapshot_hash": fingerprint(practice["document"]),
            }
            event = await run_conversation(model, context, prompt, maximum)
    except TurnError as error:
        raise ClientError(message_for(error.code), code=error.code) from None
    except (KeyError, TypeError, ValueError, AssertionError):
        raise ClientError(INVALID, code="llm_local_route_invalid") from None
    validate_result(event)
    event["language"] = resolved
    # The platform streams one delta before done for a patient turn; keep the display identical.
    emit("answer_delta", event["text"])
    emit("answer", event["text"])
    return event
