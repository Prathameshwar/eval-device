"""Report what a patient case can and cannot be asked, and what its prompts cost.

A topic reaches the router only through the index in the routing prompt. A topic that is
concealed, or that is missing either language's answer, is silently absent from that index: the
model cannot name it, every question about it falls to the clarification line, and the result is
indistinguishable from a model failure. This script makes that visible before a learner finds
it, and reports each prompt against the budget that actually binds it.

    uv run python scripts/audit_patient_index.py                 # shipped seed cases
    uv run python scripts/audit_patient_index.py case.json ...   # exported documents

Exit status is non-zero when a case would overflow a budget, so this is usable as a check.
Reads files only; it does not connect to a database and makes no provider call.
"""

import json
import sys
from pathlib import Path

from training_contracts.patient_turn import (
    DEFLECTION_SUBJECTS,
    REPAIR_RULE,
    ROUTING_TOKENS,
    VOICE_TOKENS,
    deflection_messages,
    patient_context,
    repair_budget,
    route,
    voice_messages,
)
from training_contracts.scenarios import ScenarioDraftV2

VERSIONS = Path(__file__).parents[1] / "migrations/versions"
SEEDS = ("0013", "0014")
# Local is the binding case: llama.cpp tokenises natively inside this window and the whole turn
# shares it. Three bytes per token is pessimistic for a mixed English/Devanagari prompt; the
# shipped case measured about 4.2, so a prompt that passes here has real headroom.
LOCAL_CONTEXT = 2048
LOCAL_BYTES_PER_TOKEN = 3
MARGIN = 64
# Remote is estimated the way fit_patient_prompt estimates it: one token per byte plus 32 per
# message. That is roughly four times the real cost and is deliberately never presented as
# exact, so this reports the smallest remote context a case can be configured with.
REMOTE_MESSAGES = 13
REMOTE_ROUTING_TOKENS = 512


def documents(arguments):
    if arguments:
        for name in arguments:
            value = json.loads(Path(name).read_text(encoding="utf-8"))
            yield name, value["document"] if "document" in value else value
        return
    for migration in SEEDS:
        path = VERSIONS / f"{migration}_patient_case_templates.json"
        if not path.is_file():
            continue
        for row in json.loads(path.read_text(encoding="utf-8")):
            yield f"{migration}/{row.get('code', row.get('title', '?'))}", row["document"]


def unreachable(document):
    """Topics the router can never name, and why. These are authoring faults, not model faults."""
    case = ScenarioDraftV2.model_validate(document)
    reasons = []
    for topic in case.dialogue.topics if case.dialogue else []:
        answer = topic.answer.model_dump(mode="json") if topic.answer else {}
        if topic.disclosure == "never":
            reasons.append((topic.id, "concealed by disclosure"))
        elif not answer.get("en") or not answer.get("hi"):
            missing = [name for name in ("en", "hi") if not answer.get(name)]
            reasons.append((topic.id, "no " + "/".join(missing) + " answer"))
    return reasons


def worst_voice_prompt(context):
    """The largest spoken prompt this case can produce, over every routable topic triple.

    Checking one topic would understate it: three routed topics carry three authored answers
    plus the presentation and history wording their sections add.
    """
    ordered = sorted(context["answers"], key=lambda topic: len(context["answers"][topic]["hi"]), reverse=True)
    worst = 0
    for start in range(0, max(1, len(ordered) - 2)):
        decision = route(
            context, {"text": json.dumps({"kind": "topic", "topics": ordered[start : start + 3]})}
        )
        if not decision["topics"]:
            continue
        messages, _ = voice_messages(context, decision, [])
        worst = max(worst, len(messages[0]["content"].encode("utf-8")))
    return worst


def report(name, document):
    context = patient_context(document, "hi", "?")
    routing_bytes = len(context["system"].encode("utf-8"))
    voice_bytes = worst_voice_prompt(context)
    deflection_bytes = len(deflection_messages(context, [])[0][0]["content"].encode("utf-8"))
    missing = unreachable(document)
    # A repaired attempt keeps the index and adds its rule, but drops the conversation, and it
    # is allowed the larger spoken output. It is the widest routing prompt the turn can send.
    repair_tokens = (routing_bytes + len(("\n" + REPAIR_RULE).encode("utf-8"))) / LOCAL_BYTES_PER_TOKEN
    checks = [
        # name, estimated tokens, the output allowance beside it, the window it must fit
        ("routing/local", routing_bytes / LOCAL_BYTES_PER_TOKEN, ROUTING_TOKENS, LOCAL_CONTEXT),
        ("repair/local", repair_tokens, repair_budget(ROUTING_TOKENS, VOICE_TOKENS), LOCAL_CONTEXT),
        ("voice/local", voice_bytes / LOCAL_BYTES_PER_TOKEN, VOICE_TOKENS, LOCAL_CONTEXT),
        ("deflection/local", deflection_bytes / LOCAL_BYTES_PER_TOKEN, VOICE_TOKENS, LOCAL_CONTEXT),
    ]
    print(f"\n{name}")
    print(f"  routable topics      {len(context['answers'])}")
    print(f"  deflection subjects  {min(DEFLECTION_SUBJECTS, len(context['subjects']))}")
    print(f"  routing prompt       {routing_bytes} bytes")
    print(f"  worst voice prompt   {voice_bytes} bytes")
    failures = []
    for label, tokens, output, window in checks:
        used = tokens + output + MARGIN
        share = round(100 * used / window)
        flag = "OVERFLOW" if used > window else ("tight" if share > 70 else "ok")
        print(
            f"  {label:<20} ~{round(tokens)} tok + {output} out + {MARGIN} = {round(used)}/{window} ({share}%) {flag}"
        )
        if used > window:
            failures.append(f"{name}: {label} needs {round(used)} of {window} tokens")
    smallest = routing_bytes + REMOTE_MESSAGES * 32 + REMOTE_ROUTING_TOKENS + MARGIN
    print(f"  remote context_tokens must be at least {smallest} for a full conversation")
    if missing:
        print(f"  UNASKABLE topics ({len(missing)}):")
        for topic, reason in missing:
            print(f"    - {topic}: {reason}")
    return failures


def main(arguments):
    failures = []
    cases = 0
    for name, document in documents(arguments):
        cases += 1
        failures.extend(report(name, document))
    if not cases:
        print("No case documents found; pass exported document paths as arguments.")
        return 1
    print()
    if failures:
        for failure in failures:
            print("FAIL " + failure)
        return 1
    print(f"{cases} case(s) fit every prompt budget.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
