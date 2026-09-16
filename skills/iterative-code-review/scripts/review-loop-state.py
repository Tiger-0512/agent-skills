#!/usr/bin/env python3
# Purpose: validate iterative review rounds and decide convergence deterministically.
# Dependencies: Python 3 standard library only; no package installation is required.
# Usage: run with the init, add-round, or status subcommand; use --help for details.
"""Validate iterative code-review rounds and decide convergence.

Required packages: none (Python standard library only).
Installation: no additional installation is required.

Usage:
  review-loop-state.py init --state FILE --fixed-point REF --baseline-sha SHA
  review-loop-state.py add-round --state FILE --round-file FILE \
      --max-rounds 5 --stagnation-rounds 2
  review-loop-state.py status --state FILE \
      --max-rounds 5 --stagnation-rounds 2
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sys
import tempfile
from typing import Any

SCHEMA_VERSION = 1
ALLOWED_AXES = {"standards", "spec"}
ALLOWED_SEVERITIES = {"critical", "high", "medium", "low"}
ALLOWED_DISPOSITIONS = {"actionable", "rejected", "deferred"}
ALLOWED_REPAIR_STATUSES = {"fixed", "unfixed", "not-attempted", "not-applicable"}
ALLOWED_VALIDATION_STATUSES = {"passed", "failed", "not-run"}


class StateError(ValueError):
    """Raised when a state or round file violates the contract."""


def require_nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StateError(f"{field} must be a non-empty string")
    return value.strip()


def require_positive_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise StateError(f"{field} must be an integer greater than zero")
    return value


def positive_int_argument(raw_value: str) -> int:
    """Parse a positive integer for argparse with a user-facing error."""
    try:
        value = int(raw_value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer greater than zero") from error
    if value < 1:
        raise argparse.ArgumentTypeError("must be an integer greater than zero")
    return value


def read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError as error:
        raise StateError(f"file does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise StateError(f"invalid JSON in {path}: {error}") from error
    except OSError as error:
        raise StateError(f"cannot read {path}: {error}") from error

    if not isinstance(value, dict):
        raise StateError(f"top-level JSON value in {path} must be an object")
    return value


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except OSError as error:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise StateError(f"cannot write {path}: {error}") from error


def normalize_repository_path(raw_path: Any, field: str) -> str:
    path = require_nonempty_string(raw_path, field).replace("\\", "/")
    normalized = str(PurePosixPath(path))
    if normalized == ".":
        raise StateError(f"{field} must identify a file")
    return normalized


def finding_fingerprint(finding: dict[str, Any]) -> str:
    identity = {
        "axis": finding["axis"],
        "file": finding["file"],
        "symbol": finding["symbol"].casefold(),
        "rule": finding["rule"].casefold(),
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:20]


def normalize_finding(raw: Any, index: int) -> dict[str, Any]:
    prefix = f"findings[{index}]"
    if not isinstance(raw, dict):
        raise StateError(f"{prefix} must be an object")

    axis = require_nonempty_string(raw.get("axis"), f"{prefix}.axis").lower()
    if axis not in ALLOWED_AXES:
        raise StateError(f"{prefix}.axis must be one of {sorted(ALLOWED_AXES)}")

    severity = require_nonempty_string(raw.get("severity"), f"{prefix}.severity").lower()
    if severity not in ALLOWED_SEVERITIES:
        raise StateError(
            f"{prefix}.severity must be one of {sorted(ALLOWED_SEVERITIES)}"
        )

    disposition = require_nonempty_string(
        raw.get("disposition"), f"{prefix}.disposition"
    ).lower()
    if disposition not in ALLOWED_DISPOSITIONS:
        raise StateError(
            f"{prefix}.disposition must be one of {sorted(ALLOWED_DISPOSITIONS)}"
        )

    repair_status = require_nonempty_string(
        raw.get("repair_status"), f"{prefix}.repair_status"
    ).lower()
    if repair_status not in ALLOWED_REPAIR_STATUSES:
        raise StateError(
            f"{prefix}.repair_status must be one of {sorted(ALLOWED_REPAIR_STATUSES)}"
        )
    if disposition == "actionable" and repair_status == "not-applicable":
        raise StateError(
            f"{prefix}.repair_status cannot be not-applicable for actionable findings"
        )
    if disposition != "actionable" and repair_status != "not-applicable":
        raise StateError(
            f"{prefix}.repair_status must be not-applicable for {disposition} findings"
        )

    finding = {
        "axis": axis,
        "file": normalize_repository_path(raw.get("file"), f"{prefix}.file"),
        "symbol": require_nonempty_string(raw.get("symbol"), f"{prefix}.symbol"),
        "rule": require_nonempty_string(raw.get("rule"), f"{prefix}.rule"),
        "severity": severity,
        "summary": require_nonempty_string(raw.get("summary"), f"{prefix}.summary"),
        "disposition": disposition,
        "rationale": require_nonempty_string(raw.get("rationale"), f"{prefix}.rationale"),
        "repair_status": repair_status,
    }

    repair_summary = raw.get("repair_summary")
    if repair_status == "fixed":
        finding["repair_summary"] = require_nonempty_string(
            repair_summary, f"{prefix}.repair_summary"
        )
    elif repair_summary is not None:
        finding["repair_summary"] = require_nonempty_string(
            repair_summary, f"{prefix}.repair_summary"
        )

    finding["fingerprint"] = finding_fingerprint(finding)
    return finding


def normalize_validation(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise StateError("validation must be an object")

    status = require_nonempty_string(raw.get("status"), "validation.status").lower()
    if status not in ALLOWED_VALIDATION_STATUSES:
        raise StateError(
            f"validation.status must be one of {sorted(ALLOWED_VALIDATION_STATUSES)}"
        )

    commands = raw.get("commands")
    if not isinstance(commands, list) or any(
        not isinstance(command, str) or not command.strip() for command in commands
    ):
        raise StateError("validation.commands must be an array of non-empty strings")
    if status == "passed" and not commands:
        raise StateError(
            "validation.commands cannot be empty when validation.status is passed"
        )

    return {
        "status": status,
        "commands": [command.strip() for command in commands],
        "summary": require_nonempty_string(raw.get("summary"), "validation.summary"),
    }


def normalize_round(raw: dict[str, Any], expected_round: int) -> dict[str, Any]:
    round_number = require_positive_int(raw.get("round"), "round")
    if round_number != expected_round:
        raise StateError(f"round must be {expected_round}, got {round_number}")

    findings_raw = raw.get("findings")
    if not isinstance(findings_raw, list):
        raise StateError("findings must be an array")

    findings = [normalize_finding(item, index) for index, item in enumerate(findings_raw)]
    fingerprints = [finding["fingerprint"] for finding in findings]
    if len(fingerprints) != len(set(fingerprints)):
        raise StateError(
            "findings contain duplicate identities; combine duplicate reviewer candidates before appending"
        )

    return {
        "round": round_number,
        "reviewed_head": require_nonempty_string(
            raw.get("reviewed_head"), "reviewed_head"
        ),
        "findings": findings,
        "validation": normalize_validation(raw.get("validation")),
    }


def validate_state(raw: dict[str, Any]) -> dict[str, Any]:
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise StateError(f"schema_version must be {SCHEMA_VERSION}")

    rounds = raw.get("rounds")
    if not isinstance(rounds, list):
        raise StateError("rounds must be an array")

    state = {
        "schema_version": SCHEMA_VERSION,
        "fixed_point": require_nonempty_string(raw.get("fixed_point"), "fixed_point"),
        "baseline_sha": require_nonempty_string(raw.get("baseline_sha"), "baseline_sha"),
        "rounds": [],
    }
    for expected_round, round_raw in enumerate(rounds, start=1):
        if not isinstance(round_raw, dict):
            raise StateError(f"rounds[{expected_round - 1}] must be an object")
        state["rounds"].append(normalize_round(round_raw, expected_round))
    return state


def actionable_fingerprints(round_entry: dict[str, Any]) -> set[str]:
    return {
        finding["fingerprint"]
        for finding in round_entry["findings"]
        if finding["disposition"] == "actionable"
    }


def round_counts(round_entry: dict[str, Any]) -> dict[str, int]:
    counts = {
        "standards": 0,
        "spec": 0,
        "actionable": 0,
        "rejected": 0,
        "deferred": 0,
    }
    for finding in round_entry["findings"]:
        counts[finding["axis"]] += 1
        counts[finding["disposition"]] += 1
    return counts


def no_reduction_transitions(rounds: list[dict[str, Any]]) -> int:
    transitions = 0
    for index in range(len(rounds) - 1, 0, -1):
        current_count = len(actionable_fingerprints(rounds[index]))
        previous_count = len(actionable_fingerprints(rounds[index - 1]))
        if current_count >= previous_count:
            transitions += 1
        else:
            break
    return transitions


def repeated_set_distance(rounds: list[dict[str, Any]]) -> int | None:
    if len(rounds) < 2:
        return None
    current = actionable_fingerprints(rounds[-1])
    if not current:
        return None
    for distance, prior in enumerate(reversed(rounds[:-1]), start=1):
        if actionable_fingerprints(prior) == current:
            return distance
    return None


def decide(
    state: dict[str, Any], max_rounds: int, stagnation_rounds: int
) -> dict[str, Any]:
    rounds = state["rounds"]
    if not rounds:
        return {
            "decision": "continue",
            "reason": "no_rounds_recorded",
            "rounds_completed": 0,
        }

    latest = rounds[-1]
    counts = round_counts(latest)
    unresolved = [
        finding["fingerprint"]
        for finding in latest["findings"]
        if finding["disposition"] == "actionable"
        and finding["repair_status"] != "fixed"
    ]

    result: dict[str, Any] = {
        "rounds_completed": len(rounds),
        "latest_counts": counts,
        "validation_status": latest["validation"]["status"],
    }

    if counts["deferred"]:
        return result | {"decision": "stop", "reason": "deferred_findings"}
    if unresolved:
        return result | {
            "decision": "stop",
            "reason": "unresolved_actionable_findings",
            "fingerprints": unresolved,
        }
    if latest["validation"]["status"] == "failed":
        return result | {"decision": "stop", "reason": "validation_failed"}
    if latest["validation"]["status"] != "passed":
        return result | {"decision": "stop", "reason": "validation_required"}
    if counts["actionable"] == 0:
        return result | {
            "decision": "success",
            "reason": "clean_review_and_validation",
        }
    if len(rounds) >= max_rounds:
        return result | {"decision": "stop", "reason": "maximum_rounds_reached"}

    repeat_distance = repeated_set_distance(rounds)
    if repeat_distance is not None and repeat_distance <= stagnation_rounds:
        return result | {
            "decision": "stop",
            "reason": "repeated_finding_set",
            "cycle_distance": repeat_distance,
        }

    stagnant = no_reduction_transitions(rounds)
    if stagnant >= stagnation_rounds:
        return result | {
            "decision": "stop",
            "reason": "no_finding_reduction",
            "no_reduction_transitions": stagnant,
        }

    return result | {
        "decision": "continue",
        "reason": "repairs_require_fresh_review",
    }


def command_init(args: argparse.Namespace) -> dict[str, Any]:
    if args.state.exists():
        raise StateError(f"state file already exists: {args.state}")
    state = {
        "schema_version": SCHEMA_VERSION,
        "fixed_point": require_nonempty_string(args.fixed_point, "fixed_point"),
        "baseline_sha": require_nonempty_string(args.baseline_sha, "baseline_sha"),
        "rounds": [],
    }
    write_json_atomic(args.state, state)
    return {"status": "initialized", "state": str(args.state)}


def command_add_round(args: argparse.Namespace) -> dict[str, Any]:
    state = validate_state(read_json(args.state))
    round_raw = read_json(args.round_file)
    round_entry = normalize_round(round_raw, len(state["rounds"]) + 1)
    state["rounds"].append(round_entry)
    write_json_atomic(args.state, state)
    return decide(state, args.max_rounds, args.stagnation_rounds)


def command_status(args: argparse.Namespace) -> dict[str, Any]:
    state = validate_state(read_json(args.state))
    return decide(state, args.max_rounds, args.stagnation_rounds)


def add_decision_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state", type=Path, required=True, help="Path to loop state JSON")
    parser.add_argument(
        "--max-rounds",
        type=positive_int_argument,
        default=5,
        help="Maximum completed rounds (default: 5)",
    )
    parser.add_argument(
        "--stagnation-rounds",
        type=positive_int_argument,
        default=2,
        help="No-reduction transitions tolerated (default: 2)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a new loop state file")
    init_parser.add_argument("--state", type=Path, required=True, help="State JSON path")
    init_parser.add_argument("--fixed-point", required=True, help="Original fixed-point ref")
    init_parser.add_argument(
        "--baseline-sha",
        required=True,
        help="Resolved immutable baseline SHA",
    )
    init_parser.set_defaults(handler=command_init)

    add_parser = subparsers.add_parser("add-round", help="Validate and append one round")
    add_decision_arguments(add_parser)
    add_parser.add_argument(
        "--round-file",
        type=Path,
        required=True,
        help="Completed round JSON",
    )
    add_parser.set_defaults(handler=command_add_round)

    status_parser = subparsers.add_parser("status", help="Recompute the current decision")
    add_decision_arguments(status_parser)
    status_parser.set_defaults(handler=command_status)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        result = args.handler(args)
    except StateError as error:
        print(
            json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 1

    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
