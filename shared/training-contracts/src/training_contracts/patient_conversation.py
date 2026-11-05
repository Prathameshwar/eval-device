"""Public shared conversation API; implementation lives in the conversation package."""

from training_contracts.conversation.case_projection import canonical_text, case_facts
from training_contracts.conversation.engine import (
    OUTPUT_TOKENS,
    SAFETY_MARGIN,
    accepted_reply,
    accepted_text,
    fit_conversation_prompt,
    output_budget,
    run_conversation,
)
from training_contracts.conversation.prompt import (
    COMPILER_VERSION,
    HISTORY_MESSAGES,
    POLICY_VERSION,
    RULES,
    conversation_context,
    conversation_history,
)
from training_contracts.conversation.question_scope import select_messages
from training_contracts.languages import get_pack

__all__ = [
    "COMPILER_VERSION",
    "HISTORY_MESSAGES",
    "POLICY_VERSION",
    "RULES",
    "OUTPUT_TOKENS",
    "SAFETY_MARGIN",
    "accepted_text",
    "accepted_reply",
    "canonical_text",
    "case_facts",
    "conversation_context",
    "conversation_history",
    "fit_conversation_prompt",
    "output_budget",
    "resolved_language",
    "run_conversation",
    "select_messages",
]


def resolved_language(language, question=None):
    return get_pack(language).language
