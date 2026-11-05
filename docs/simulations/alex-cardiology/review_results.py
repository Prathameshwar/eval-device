"""Offline, conservative content checks for a recorded live interview; no model calls."""

import argparse
import csv
import json
import re
import statistics
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


def safe_error_code(value):
    return (
        value
        if isinstance(value, str) and re.fullmatch(r"[a-z_]{1,80}", value)
        else None
    )


def attempt_error_code(attempt):
    return safe_error_code(attempt.get("error_code")) or safe_error_code(
        (attempt.get("stored") or {}).get("error_code")
    )


def tokens(text):
    return re.findall(
        r"[a-z0-9]+", text.lower().replace("what's", "what is").replace("’", "'")
    )


def word_error_rate(expected, actual):
    expected, actual = tokens(expected), tokens(actual)
    row = list(range(len(actual) + 1))
    for i, word in enumerate(expected, 1):
        following = [i]
        for j, observed in enumerate(actual, 1):
            following.append(
                min(following[-1] + 1, row[j] + 1, row[j - 1] + (word != observed))
            )
        row = following
    return round(row[-1] / max(1, len(expected)), 4)


def expected_answers(document, topics):
    def substitute(match):
        value = document
        for part in match.group(1).split("."):
            value = value[part]
        return str(value)

    return [
        re.sub(r"\{([^}]+)\}", substitute, topic["answer"]["en"])
        for topic in document["dialogue"]["topics"]
        if topic["id"] in topics
    ]


def review(folder):
    folder = Path(folder)
    data = json.loads((folder / "results.json").read_text(encoding="utf-8"))
    document = json.loads((folder / "case-snapshot.json").read_text(encoding="utf-8"))
    specification = json.loads((folder / "suite.json").read_text(encoding="utf-8"))
    errors = Counter()
    failures = Counter()
    stages = Counter()
    for row, spec in zip(data["results"], specification, strict=True):
        row["expected_answers"] = expected_answers(document, spec["expected_topics"])
        row["transcript_word_error_rate"] = word_error_rate(
            row["question"], row["transcript"]
        )
        for attempt in row["attempts"]:
            code = attempt_error_code(attempt)
            if code:
                errors[code] += 1
        if row["error"]:
            errors[row["error"]] += 1
        if row["outcome"] != "answered":
            stage = (
                "preflight"
                if not row.get("audio_entered_pipeline", True)
                else "speech"
                if not row["transcript"]
                else "response"
            )
            row["failure_stage"] = stage
            stages[stage] += 1
            code = next(
                (
                    attempt_error_code(a)
                    for a in reversed(row["attempts"])
                    if attempt_error_code(a)
                ),
                None,
            )
            match = re.search(r"PMS: ([a-z_]+)", row["error"])
            row["failure_code"] = match.group(1) if match else code or row["error"]
            failures[row["failure_code"]] += 1
            row["content_check"] = "not_evaluated"
            row["missing_content_checks"] = []
        else:
            row["missing_content_checks"] = [
                pattern
                for pattern in spec["answer_checks"]
                if not re.search(pattern, row["answer"], flags=re.IGNORECASE)
            ]
            row["content_check"] = "review" if row["missing_content_checks"] else "pass"
        row["asr_check"] = (
            "pass"
            if row["transcript"] and row["transcript_word_error_rate"] <= 0.25
            else "review"
        )
        row["needs_review"] = row["outcome"] == "answered" and (
            row["content_check"] != "pass"
            or row["asr_check"] != "pass"
            or row.get("metrics", {}).get("finish_reason") != "stop"
        )
    rows = data["results"]
    successful = [r for r in rows if r["outcome"] == "answered"]
    summary = {
        "questions_attempted": len(rows),
        "answered": len(successful),
        "failed_turns": len(rows) - len(successful),
        "needs_review": sum(r["needs_review"] for r in rows),
        "content_checks_passed": sum(r["content_check"] == "pass" for r in rows),
        "retry_count": sum(r["retries"] for r in rows),
        "speech_attempts": sum(
            a["stage"] == "speech" for r in rows for a in r["attempts"]
        ),
        "llm_attempts": sum(a["stage"] == "llm" for r in rows for a in r["attempts"]),
        "errors": dict(errors),
        "failed_turns_by_code": dict(failures),
        "failed_turns_by_stage": dict(stages),
        "median_pipeline_seconds": round(
            statistics.median(r["pipeline_seconds"] for r in rows), 3
        ),
        "max_pipeline_seconds": max(r["pipeline_seconds"] for r in rows),
        "check_limit": "Content checks are scenario-specific regex checks, not a clinical or complete semantic judgment. Review full answers against the stored facts.",
    }
    data["summary"] = summary
    (folder / "results.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (folder / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    fields = [
        "number",
        "question",
        "transcript",
        "answer",
        "outcome",
        "content_check",
        "asr_check",
        "error",
        "retries",
        "pipeline_seconds",
        "wall_seconds",
        "transcript_word_error_rate",
    ]
    with (folder / "results.csv").open("w", newline="", encoding="utf-8-sig") as output:
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ")

    report = [
        "# Alex: live 25-question audio interview",
        "",
        f"Started: {data['metadata']['started_at']}",
        f"Completed: {data['metadata'].get('completed_at', 'incomplete')}",
        "",
        f"**{len(rows)} attempted; {len(successful)} answered; {summary['failed_turns']} failed; {summary['retry_count']} retries.**",
        f"Automated content checks passed: {summary['content_checks_passed']}; answered turns needing review: {summary['needs_review']}.",
        "",
        "Real cloud ASR/LLM through the production desktop and PMS. Generated spoken questions replace the physical microphone. One conversation uses the app's existing rolling history. No quota, retry or model configuration is changed by this test.",
        "",
        "| # | Question | Transcript | Answer / error | Content check | Retries | Pipeline seconds |",
        "|---|---|---|---|---|---:|---:|",
    ]
    for row in rows:
        report.append(
            "| "
            + " | ".join(
                cell(x)
                for x in (
                    row["number"],
                    row["question"],
                    row["transcript"],
                    row["answer"] or row["error"],
                    row["content_check"],
                    row["retries"],
                    row["pipeline_seconds"],
                )
            )
            + " |"
        )
    report += ["", "## Per-question reference and diagnostics", ""]
    for row in rows:
        report += [
            f"### {row['number']}. {row['question']}",
            "",
            f"Expected facts: {' '.join(row['expected_answers'])}",
            "",
            f"Recognized: {row['transcript'] or '(no transcript)'}",
            "",
            f"Response: {row['answer'] or '(no answer)'}",
            "",
            f"Error: {row['error'] or '(none)'}; content check: {row['content_check']}; transcript WER: {row['transcript_word_error_rate']}.",
            "",
        ]
        for attempt in row["attempts"]:
            stored = attempt.get("stored") or {}
            report.append(
                f"- {attempt['stage']}: HTTP {attempt.get('http_status')}, stored status {stored.get('status')}, code {attempt_error_code(attempt) or attempt.get('status_lookup_error') or 'none'}, request `{attempt['request_key']}`"
            )
        report.append("")
    report += [
        "## Limits",
        "",
        summary["check_limit"],
        "",
        "Physical microphone, room acoustics, accents, voice-activity detection, hardware overflow and overlapping user speech are outside this WAV-input run. Sequential questions wait for the active request and answer playback; this is not simultaneous load testing.",
    ]
    (folder / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    result = review(args.folder)
    print(json.dumps(result, indent=2))
    raise SystemExit(2 if result["failed_turns"] or result["needs_review"] else 0)
