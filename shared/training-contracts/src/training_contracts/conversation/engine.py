"""One generation, explicit completion acceptance, and actual-model prompt fitting."""

import json
import re
import time

from training_contracts import fingerprint
from training_contracts.patient_turn import TurnError, fit_patient_prompt

from .prompt import POLICY_VERSION
from .question_scope import measurement_subjects, prompt_mode, select_messages

OUTPUT_TOKENS = 128
SAFETY_MARGIN = 128


def output_budget(max_tokens, cap=OUTPUT_TOKENS):
    if type(max_tokens) is not int or max_tokens < 16:
        raise ValueError("Invalid model output allowance")
    if cap is not None and (type(cap) is not int or cap < 16):
        raise ValueError("Invalid conversation output allowance")
    return min(max_tokens, cap) if cap is not None else max_tokens


async def fit_conversation_prompt(runner, messages, max_tokens, *, context=None):
    original_count = len(messages)
    if context is not None:
        messages = select_messages(context, messages)
    messages, budget = await fit_patient_prompt(runner, messages, max_tokens, margin=SAFETY_MARGIN)
    if context is not None:
        mode = prompt_mode(context, messages)
        budget["prompt_mode"] = mode
        budget["history_pairs_omitted_for_scope"] = (original_count - len(messages)) // 2 - budget.get(
            "history_pairs_dropped", 0
        )
    return messages, budget


def accepted_text(event):
    if event.get("finish_reason") == "length":
        raise TurnError("llm_output_limit", 422)
    if event.get("finish_reason") != "stop":
        raise TurnError("llm_incomplete")
    text = event.get("text")
    if not isinstance(text, str) or not text.strip():
        raise TurnError("llm_empty_response")
    text = text.strip()
    if len(text) > 1600 or len(text.encode("utf-8")) > 6400:
        raise TurnError("llm_response_limit")
    if (
        "\x00" in text
        or re.search(r"</?(?:think|analysis)>|<\|(?:im_start|im_end|analysis)\|>", text, re.I)
        or text.startswith(("{", "[", "```"))
        or re.match(r"(?:analysis|reasoning|assistant|patient)\s*:", text, re.I)
    ):
        raise TurnError("llm_invalid_response")
    return text


def accepted_reply(event, context, messages):
    """Speak frozen source text; a model never rewrites a personal/clinical claim."""
    if (
        context.get("reply_format") != "fact-selection-v1"
        or not messages
        or "\nSOURCE:\n" not in messages[0].get("content", "")
    ):
        return accepted_text(event)
    if event.get("finish_reason") != "stop":
        return accepted_text(event)
    raw = event.get("text")
    if not isinstance(raw, str) or not raw.strip() or len(raw) > 1600:
        raise TurnError("llm_invalid_response")
    try:
        reply = json.loads(raw)
        selected = json.loads(messages[0]["content"].split("\nSOURCE:\n", 1)[1].split("\nEND SOURCE.", 1)[0])
        if not isinstance(selected, dict) or any(
            fact != context["fact_sources"][key]
            and fact
            != {
                "subject": context["fact_sources"][key]["subject"],
                "text": context["fact_sources"][key]["text"],
            }
            for key, fact in selected.items()
        ):
            raise ValueError("Unpinned source view")
        # Accept old complete views and compact views, then restore metadata solely from the snapshot.
        selected = {key: context["fact_sources"][key] for key in selected}
        if (
            not isinstance(reply, list)
            or len(reply) > 4
            or any(not isinstance(key, str) for key in reply)
            or len(set(reply)) != len(reply)
        ):
            raise ValueError("Invalid fact selection")
        special = set(reply).intersection({"unknown", "clarify", "boundary"})
        facts = [key for key in reply if key not in special]
        if len(facts) > 3 or len(special) > 1:
            raise ValueError("Invalid fact selection")
        if not selected and not special.intersection({"clarify", "boundary"}):
            # No evidence exists for this exact subject, even if a small model invents an ID.
            # This is a known absence, not a repair generation or an unsupported denial.
            return accepted_text({**event, "text": context["unknown_reply"]})
        if any(
            not isinstance(key, str)
            or key not in selected
            or selected[key] != context["fact_sources"].get(key)
            for key in facts
        ) or len(set(facts)) != len(facts):
            raise ValueError("Unknown source")
        if special.intersection({"clarify", "boundary"}):
            if facts:
                raise ValueError("Conflicting reply")
            answer = context["clarification_reply" if "clarify" in special else "boundary_reply"]
        else:
            from .sources import constrained_sources

            _, missing = constrained_sources(selected, messages[-1]["content"])
            if messages[0]["content"].startswith("Prompt scope: patient_measurement."):
                available = {subject for fact in selected.values() for subject in fact["subject"].split("; ")}
                missing = missing or not measurement_subjects(messages[-1]["content"]).issubset(available)
            if not facts and "unknown" in special and missing and len(selected) == 1:
                # Keep a directly relevant known part even when the requested actor/event is absent.
                # The source view is pinned and contains exactly one eligible fact, so no new selection call is needed.
                facts = list(selected)
            answer = " ".join(selected[key]["text"] for key in facts)
            if "unknown" in special or missing or not facts:
                answer = (answer + " " + context["unknown_reply"]).strip()
    except (ValueError, KeyError, TypeError, IndexError):
        raise TurnError("llm_invalid_response") from None
    if len(answer) > 600:
        raise TurnError("llm_response_limit", 422)
    return accepted_text({**event, "text": answer})


async def run_conversation(runner, context, messages, max_tokens):
    """Messages have already been fitted, allowing quota reservation before dispatch."""
    started = time.monotonic()
    event = await runner.complete(messages, max_tokens)
    text = accepted_reply(event, context, messages)
    return {
        "type": "done",
        "text": text,
        "finish_reason": "stop",
        "usage": event.get("usage"),
        "provider_calls": 1,
        "answer_source": "patient_conversation",
        "policy_version": POLICY_VERSION,
        "language": context["language"],
        "routing_status": None,
        "kind": None,
        "topics": [],
        "first_token_ms": event.get("first_token_ms"),
        "total_ms": round((time.monotonic() - started) * 1000),
        "context": context.get("budget", {}),
        "prompt_hash": fingerprint(messages),
        **{
            key: context[key]
            for key in ("conversation_id", "language_pack_version", "language_pack_hash", "compiler_version")
            if key in context
        },
    }
