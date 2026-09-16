"""Tests for the deterministic iterative code-review state checker.

Required packages: none (Python standard library only).
Run with: python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import unittest


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "review-loop-state.py"
SPEC = importlib.util.spec_from_file_location("review_loop_state", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
review_loop_state = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review_loop_state)


def candidate(
    rule: str,
    *,
    disposition: str = "actionable",
    repair_status: str = "fixed",
) -> dict[str, str]:
    value = {
        "axis": "standards",
        "file": "src/example.py",
        "symbol": "build_report",
        "rule": rule,
        "severity": "medium",
        "summary": f"Finding for {rule}",
        "disposition": disposition,
        "rationale": "Verified against the current code.",
        "repair_status": repair_status,
    }
    if repair_status == "fixed":
        value["repair_summary"] = "Fixed the root cause."
    return value


def completed_round(
    number: int,
    findings: list[dict[str, str]],
    *,
    validation_status: str = "passed",
) -> dict[str, object]:
    commands = ["pytest tests/test_example.py"] if validation_status == "passed" else []
    return review_loop_state.normalize_round(
        {
            "round": number,
            "reviewed_head": f"head-{number}",
            "findings": findings,
            "validation": {
                "status": validation_status,
                "commands": commands,
                "summary": "Validation outcome recorded.",
            },
        },
        number,
    )


def state_with(rounds: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": review_loop_state.SCHEMA_VERSION,
        "fixed_point": "origin/main",
        "baseline_sha": "abc123",
        "rounds": rounds,
    }


class DecisionTests(unittest.TestCase):
    def test_repaired_finding_requires_fresh_review(self) -> None:
        first = completed_round(1, [candidate("RULE-A")])

        result = review_loop_state.decide(state_with([first]), 5, 2)

        self.assertEqual("continue", result["decision"])
        self.assertEqual("repairs_require_fresh_review", result["reason"])

    def test_clean_review_and_validation_succeeds(self) -> None:
        first = completed_round(1, [candidate("RULE-A")])
        clean = completed_round(2, [])

        result = review_loop_state.decide(state_with([first, clean]), 5, 2)

        self.assertEqual("success", result["decision"])
        self.assertEqual("clean_review_and_validation", result["reason"])

    def test_repeated_finding_set_stops(self) -> None:
        first = completed_round(1, [candidate("RULE-A")])
        repeated = completed_round(2, [candidate("RULE-A")])

        result = review_loop_state.decide(state_with([first, repeated]), 5, 2)

        self.assertEqual("stop", result["decision"])
        self.assertEqual("repeated_finding_set", result["reason"])

    def test_two_no_reduction_transitions_stop(self) -> None:
        rounds = [
            completed_round(1, [candidate("RULE-A")]),
            completed_round(2, [candidate("RULE-B")]),
            completed_round(3, [candidate("RULE-C")]),
        ]

        result = review_loop_state.decide(state_with(rounds), 5, 2)

        self.assertEqual("stop", result["decision"])
        self.assertEqual("no_finding_reduction", result["reason"])

    def test_deferred_finding_stops(self) -> None:
        deferred = completed_round(
            1,
            [
                candidate(
                    "RULE-D",
                    disposition="deferred",
                    repair_status="not-applicable",
                )
            ],
        )

        result = review_loop_state.decide(state_with([deferred]), 5, 2)

        self.assertEqual("deferred_findings", result["reason"])

    def test_unresolved_actionable_finding_stops(self) -> None:
        unresolved = completed_round(
            1,
            [candidate("RULE-E", repair_status="unfixed")],
        )

        result = review_loop_state.decide(state_with([unresolved]), 5, 2)

        self.assertEqual("unresolved_actionable_findings", result["reason"])

    def test_failed_validation_stops(self) -> None:
        failed = completed_round(1, [], validation_status="failed")

        result = review_loop_state.decide(state_with([failed]), 5, 2)

        self.assertEqual("validation_failed", result["reason"])

    def test_maximum_rounds_stops_before_another_review(self) -> None:
        first = completed_round(1, [candidate("RULE-A")])

        result = review_loop_state.decide(state_with([first]), 1, 2)

        self.assertEqual("maximum_rounds_reached", result["reason"])


class ContractTests(unittest.TestCase):
    def test_duplicate_identity_is_rejected(self) -> None:
        with self.assertRaisesRegex(review_loop_state.StateError, "duplicate identities"):
            completed_round(1, [candidate("RULE-A"), candidate("RULE-A")])

    def test_passed_validation_requires_a_command(self) -> None:
        with self.assertRaisesRegex(review_loop_state.StateError, "cannot be empty"):
            review_loop_state.normalize_round(
                {
                    "round": 1,
                    "reviewed_head": "head-1",
                    "findings": [],
                    "validation": {
                        "status": "passed",
                        "commands": [],
                        "summary": "No command recorded.",
                    },
                },
                1,
            )

    def test_positive_cli_integer_parser(self) -> None:
        self.assertEqual(5, review_loop_state.positive_int_argument("5"))
        with self.assertRaises(argparse.ArgumentTypeError):
            review_loop_state.positive_int_argument("0")
        with self.assertRaises(argparse.ArgumentTypeError):
            review_loop_state.positive_int_argument("not-a-number")


if __name__ == "__main__":
    unittest.main()
