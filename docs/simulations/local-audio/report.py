"""Export recorded simulation outcomes, never fabricate or replace model answers."""

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from statistics import median

from training_contracts.patient_turn import patient_context

ROOT = Path(__file__).resolve().parents[3]


def normalize(text):
    return " ".join(re.sub(r"[^\w\s]", " ", text.casefold()).split())


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def timing(values):
    values = [v / 1000 for v in values if v is not None]
    if not values:
        return "not available"
    return f"{min(values):.3f}-{max(values):.3f} s; median {median(values):.3f} s"


def export(source, destination):
    result = json.loads(source.read_text(encoding="utf-8"))
    planned = json.loads(source.with_name("questions.json").read_text(encoding="utf-8"))
    cases = {
        row["code"]: row["document"]
        for row in json.loads(
            (
                ROOT
                / "platform/api/migrations/versions/0014_patient_case_templates.json"
            ).read_text(encoding="utf-8")
        )
    }
    rows = []
    for turn in result["turns"]:
        outcomes = turn["results"]
        outcome = outcomes[0] if len(outcomes) == 1 else {}
        metrics = outcome.get("metrics", {})
        events = outcome.get("local_metrics", [])
        topics = [topic for event in events for topic in event["topics"]]
        context = patient_context(cases[turn["case"]], "en", turn["question"])
        expected = " ".join(
            context["answers"][topic]["en"] for topic in turn["expected_topics"]
        )
        if not turn["expected_topics"]:
            expected = context["clarification"]
        transcript = " / ".join(o.get("transcript", "") for o in outcomes)
        answer = " / ".join(o.get("answer", o.get("error", "")) for o in outcomes)
        transcript_match = len(outcomes) == 1 and normalize(transcript) == normalize(
            turn["question"]
        )
        authored_match = bool(answer) and (
            all(
                context["answers"][topic]["en"] in answer
                for topic in turn["expected_topics"]
            )
            if turn["expected_topics"]
            else answer == expected
        )
        notes = []
        if len(outcomes) != 1:
            notes.append(f"Expected one captured turn; got {len(outcomes)}")
        if outcome.get("error"):
            notes.append(outcome["error"])
        if not transcript_match:
            notes.append("Transcript differs; inspect intended and recognized question")
        if not turn["topic_match"]:
            notes.append("Selected topic differs from the prepared expectation")
        if not authored_match:
            notes.append("Answer does not contain the expected authored response")
        if not notes:
            notes.append("Matched prepared topic and authored answer")
        rows.append(
            {
                "number": turn["number"],
                "category": turn["category"],
                "case": turn["case"],
                "case_title": cases[turn["case"]]["title"],
                "condition": turn["condition"],
                "question": turn["question"],
                "transcript": transcript,
                "actual_answer": answer,
                "expected_topics": ", ".join(turn["expected_topics"])
                or "clarification",
                "selected_topics": ", ".join(topics)
                or ", ".join(e.get("kind", "") for e in events),
                "routing_status": ", ".join(
                    e.get("routing_status", "") for e in events
                ),
                "answer_source": ", ".join(e.get("answer_source", "") for e in events),
                "provider_calls": sum(e.get("provider_calls", 0) for e in events),
                "expected_authored_answer": expected,
                "topic_match": turn["topic_match"],
                "transcript_match": transcript_match,
                "expected_answer_present": authored_match,
                "asr_finalize_ms": metrics.get("asr_finalize_ms"),
                "answer_stage_ms": metrics.get("pms_roundtrip_ms"),
                "elapsed_seconds": turn["elapsed_seconds"],
                "ui_state": outcome.get("ui_state", ""),
                "dropped_blocks": sum(
                    o.get("quality", {}).get("dropped_blocks", 0) for o in outcomes
                ),
                "status_blocks": sum(
                    o.get("quality", {}).get("status_blocks", 0) for o in outcomes
                ),
                "notes": "; ".join(notes),
            }
        )
    if not rows:
        raise ValueError("No completed simulation turns to report")
    destination.parent.mkdir(parents=True, exist_ok=True)
    csv_path = destination.with_suffix(".csv")
    with csv_path.open("w", newline="", encoding="utf-8-sig") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "recorded": len(rows),
        "planned": len(planned)
        if all("case" in row for row in planned)
        else len(planned) * 2,
        "topic_matches": sum(row["topic_match"] for row in rows),
        "transcript_matches": sum(row["transcript_match"] for row in rows),
        "expected_answers_present": sum(row["expected_answer_present"] for row in rows),
        "categories": dict(Counter(row["category"] for row in rows)),
        "cases": dict(Counter(row["case"] for row in rows)),
        "conditions": dict(Counter(row["condition"] for row in rows)),
        "ui_errors": result["ui_errors"],
        "dropped_blocks": sum(row["dropped_blocks"] for row in rows),
        "status_blocks": sum(row["status_blocks"] for row in rows),
        "not_complete": [
            row["number"] for row in rows if row["ui_state"] != "Complete"
        ],
        "topic_misses": [row["number"] for row in rows if not row["topic_match"]],
    }
    lines = [
        "# Local audio: 50 questions and recorded answers",
        "",
        (
            "These are actual captured answers from the local simulation on 2026-09-21. "
            "Expected topics were prepared before execution and are used only for evaluation. "
            "They are never passed to the model or application as hints."
        ),
        "",
        (
            f"Recorded **{summary['recorded']}/{summary['planned']}** planned turns; "
            f"**{summary['transcript_matches']}** transcripts match after ignoring punctuation and case; "
            f"**{summary['topic_matches']}** selections match the expected topic set."
        ),
        "",
        (
            f"Models/settings: `{json.dumps(result['models'], sort_keys=True)}`. "
            "Authored mode means Qwen selects topics and the application returns existing case text. "
            "The answer column does not claim freely generated Qwen prose. "
            "History is capped at one previous user/assistant pair with this profile; context fitting "
            "can reduce it further. Case selection resets history between cases."
        ),
        "",
        result["boundary"]
        + ". Physical microphone, room acoustics, speakers, cloud services and "
        "database persistence are outside this verification. The patient cases are fictional fixtures.",
        "",
        (
            "Audio conditions: 30% speech amplitude for quiet inputs; deterministic background noise "
            "at 180 PCM16 RMS for noisy inputs; an added 350 ms gap between two synthesized segments "
            "for paused inputs. All other questions use clean generated speech."
        ),
        "",
        "Post-capture transcription: "
        + timing([row["asr_finalize_ms"] for row in rows])
        + ".",
        "",
        "Local answer stage: " + timing([row["answer_stage_ms"] for row in rows]) + ".",
        "",
        (
            f"UI callback errors: {len(summary['ui_errors'])}; dropped audio blocks: "
            f"{summary['dropped_blocks']}; device status blocks: {summary['status_blocks']}; "
            f"idle-silence submissions: {result.get('idle_silence_submissions', 'not recorded')}; "
            f"input stream opens/closes: {result.get('input_stream_opens', '?')}/"
            f"{result.get('input_stream_closes', '?')}."
        ),
        "",
        (
            f"[Spreadsheet-friendly CSV with transcripts, expectations and timings]({csv_path.name}). "
            "A topic match is an interview-routing check, not a clinical approval. Repeated answers "
            "are preserved exactly; authored mode returns an entire topic answer even for a narrow question."
        ),
        "",
    ]
    for code in summary["cases"]:
        selected = [row for row in rows if row["case"] == code]
        heading = f"{selected[0]['category']}: {selected[0]['case_title']}"
        lines.extend(
            [
                f"## {heading}",
                "",
                "| # | Question | Actual answer | Audio | Topic check |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for row in selected:
            verdict = (
                "Match"
                if row["topic_match"]
                else (
                    f"MISMATCH: {row['selected_topics']} (expected {row['expected_topics']})"
                )
            )
            lines.append(
                "| "
                + " | ".join(
                    cell(value)
                    for value in (
                        row["number"],
                        row["question"],
                        row["actual_answer"],
                        row["condition"],
                        verdict,
                    )
                )
                + " |"
            )
        lines.append("")
    lines.extend(["## Items requiring review", ""])
    flagged = [
        row for row in rows if not row["topic_match"] or not row["transcript_match"]
    ]
    if not flagged:
        lines.append("No mismatches in this run.")
    for row in flagged:
        lines.extend(
            [
                (
                    f"- **Question {row['number']}**: {row['notes']}. "
                    f"Transcript: {row['transcript']!r}. "
                    f"Expected case answer: {row['expected_authored_answer']}"
                ),
            ]
        )
    lines.extend(["", "## Empty recognition and recovery", ""])
    for stress in result["stress"]:
        lines.append(
            f"- `{stress['name']}`: {stress['result'].get('answer', '')} "
            f"UI: {stress.get('ui_state')}; queued UI events: {stress.get('pending_ui_events')}."
        )
    lines.extend(
        [
            "",
            "Raw evidence: `" + str(source.relative_to(ROOT)).replace("\\", "/") + "`; "
            "the same directory contains prepared questions, generated WAV inputs and service logs. "
            "Raw evidence stays in the ignored artifact directory.",
            "",
        ]
    )
    destination.write_text("\n".join(lines), encoding="utf-8")
    source.with_name("summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    export(args.source.resolve(), args.destination.resolve())
