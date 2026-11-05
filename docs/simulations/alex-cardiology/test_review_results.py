"""Offline tests of evidence grading; no cloud, database, GUI or microphone."""

import json
import tempfile
import unittest
from pathlib import Path

from review_results import review, safe_error_code, word_error_rate


class EvidenceReviewTests(unittest.TestCase):
    def run_case(self, answer, outcome="answered", error="", attempts=None):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            row = {
                "number": 1,
                "question": "What is your name?",
                "transcript": "What is your name?",
                "answer": answer,
                "outcome": outcome,
                "error": error,
                "attempts": attempts or [],
                "retries": 0,
                "pipeline_seconds": 1.0,
                "wall_seconds": 2.0,
                "metrics": {"finish_reason": "stop"},
            }
            files = {
                "results.json": {
                    "metadata": {"started_at": "2026-09-20T00:00:00Z"},
                    "results": [row],
                },
                "case-snapshot.json": {
                    "patient": {"name": "Alex"},
                    "dialogue": {
                        "topics": [
                            {
                                "id": "name",
                                "answer": {"en": "My name is {patient.name}."},
                            }
                        ]
                    },
                },
                "suite.json": [
                    {
                        "number": 1,
                        "question": row["question"],
                        "expected_topics": ["name"],
                        "answer_checks": [r"\balex\b"],
                    }
                ],
            }
            for filename, value in files.items():
                (folder / filename).write_text(json.dumps(value), encoding="utf-8")
            summary = review(folder)
            result = json.loads((folder / "results.json").read_text(encoding="utf-8"))
            self.assertTrue((folder / "report.md").is_file())
            self.assertTrue((folder / "results.csv").is_file())
            return summary, result["results"][0]

    def test_matching_fact_passes_and_reference_is_resolved(self):
        summary, row = self.run_case("My name is Alex.")
        self.assertEqual(summary["content_checks_passed"], 1)
        self.assertEqual(summary["needs_review"], 0)
        self.assertEqual(row["expected_answers"], ["My name is Alex."])

    def test_wrong_patient_name_needs_review(self):
        summary, row = self.run_case("My name is Robert.")
        self.assertEqual(summary["needs_review"], 1)
        self.assertEqual(row["content_check"], "review")

    def test_unavailable_answer_is_not_graded_as_correct(self):
        summary, row = self.run_case("", outcome="failed", error="PMS: llm_daily_limit")
        self.assertEqual(summary["failed_turns"], 1)
        self.assertEqual(summary["answered"], 0)
        self.assertEqual(row["content_check"], "not_evaluated")

    def test_final_response_quota_overrides_recovered_speech_busy(self):
        attempts = [
            {
                "stage": "speech",
                "request_key": "fixture-1",
                "stored": {"status": "failed", "error_code": "llm_busy"},
            },
            {
                "stage": "speech",
                "request_key": "fixture-2",
                "stored": {"status": "succeeded", "error_code": None},
            },
            {
                "stage": "llm",
                "request_key": "fixture-3",
                "http_status": 429,
                "status_lookup_error": "not_found",
            },
        ]
        summary, row = self.run_case(
            "", outcome="failed", error="PMS: llm_daily_limit", attempts=attempts
        )
        self.assertEqual(summary["failed_turns_by_code"], {"llm_daily_limit": 1})
        self.assertEqual(row["failure_stage"], "response")

    def test_transcription_changes_are_detected(self):
        self.assertEqual(word_error_rate("What is your name?", "WHAT is your name."), 0)
        self.assertEqual(word_error_rate("How old are you?", ""), 1)
        self.assertGreater(word_error_rate("How old are you?", "Where are you?"), 0.25)

    def test_human_readable_quota_message_uses_final_api_code(self):
        for code in ("llm_daily_limit", "llm_daily_request_limit"):
            summary, row = self.run_case(
                "",
                outcome="failed",
                error="Your organization's daily online allowance is reached. It resets at 00:00 UTC.",
                attempts=[
                    {
                        "stage": "speech",
                        "request_key": "speech-fixture",
                        "stored": {"error_code": "llm_busy"},
                    },
                    {
                        "stage": "llm",
                        "request_key": "response-fixture",
                        "http_status": 429,
                        "error_code": code,
                        "status_lookup_error": "not_found",
                    },
                ],
            )
            self.assertEqual(summary["failed_turns_by_code"], {code: 1})
            self.assertEqual(row["failure_stage"], "response")

    def test_only_bounded_error_identifiers_enter_evidence(self):
        for value in (
            None,
            {},
            "https://private.example/key",
            "A" * 100,
            "error\nprivate",
        ):
            self.assertIsNone(safe_error_code(value))
        self.assertEqual(safe_error_code("llm_daily_limit"), "llm_daily_limit")


if __name__ == "__main__":
    unittest.main()
