#!/usr/bin/env python3
# Purpose: deterministically classify PR/MR response candidates and deduplicate handled events.
# Usage: review-monitor-state.py {init|classify|record} --help
# Errors: exits 1 with a JSON error that names the invalid field or inaccessible path.
"""Classify PR/MR review-response candidates and persist processed event fingerprints.

Usage:
    review-monitor-state.py init --state PATH --target-user LOGIN
    review-monitor-state.py classify --state PATH --snapshot PATH --output PATH
    review-monitor-state.py record --state PATH --result PATH

The script stores provider metadata only. Review bodies and other sensitive content
must remain in the provider and are intentionally absent from the state schema.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
HUMAN_UPDATE_KINDS = frozenset(
    {
        "review",
        "change_request",
        "approval",
        "comment",
        "review_comment",
        "review_thread",
        "thread_reply",
        "thread_resolution",
        "commit",
        "push",
    }
)
RECORDABLE_OUTCOMES = frozenset({"remediated", "no-action"})


class StateError(ValueError):
    """Raised when an input or state file violates the documented contract."""


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StateError(f"{label} does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise StateError(f"{label} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise StateError(f"{label} must contain a JSON object: {path}")
    return value


def _write_object(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _login(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StateError(f"{field} must be a non-empty string")
    return value.strip()


def _timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise StateError(f"{field} must be a non-empty RFC3339 timestamp")
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise StateError(f"{field} is not a valid RFC3339 timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise StateError(f"{field} must include a timezone: {value}")
    return parsed.astimezone(timezone.utc)


def _state_key(provider: Any, repository: Any, number: Any) -> str:
    provider_value = _login(provider, "provider").casefold()
    repository_value = _login(repository, "repository")
    if not isinstance(number, (str, int)) or isinstance(number, bool) or not str(number).strip():
        raise StateError("number must be a non-empty string or integer")
    return f"{provider_value}|{repository_value}|{number}"


def _load_state(path: Path) -> dict[str, Any]:
    state = _read_object(path, "state file")
    if state.get("schema_version") != SCHEMA_VERSION:
        raise StateError(
            f"state schema_version must be {SCHEMA_VERSION}, got {state.get('schema_version')!r}"
        )
    _login(state.get("target_user"), "state.target_user")
    if not isinstance(state.get("processed"), dict):
        raise StateError("state.processed must be a JSON object")
    return state


def init_state(path: Path, target_user: str) -> str:
    normalized_user = _login(target_user, "target_user")
    if path.exists():
        state = _load_state(path)
        if state["target_user"].casefold() != normalized_user.casefold():
            raise StateError(
                "existing state target_user does not match requested target_user: "
                f"{state['target_user']!r} != {normalized_user!r}"
            )
        return "resumed"
    _write_object(
        path,
        {
            "schema_version": SCHEMA_VERSION,
            "target_user": normalized_user,
            "processed": {},
        },
    )
    return "initialized"


def _latest_human_update(activities: Any, context: str) -> dict[str, Any] | None:
    if not isinstance(activities, list):
        raise StateError(f"{context}.activities must be a JSON array")
    candidates: list[tuple[datetime, str, dict[str, Any]]] = []
    for index, event in enumerate(activities):
        if not isinstance(event, dict):
            raise StateError(f"{context}.activities[{index}] must be a JSON object")
        kind = str(event.get("kind", "")).strip().casefold()
        automated = event.get("automated")
        if not isinstance(automated, bool):
            raise StateError(f"{context}.activities[{index}].automated must be a boolean")
        if automated or kind not in HUMAN_UPDATE_KINDS:
            continue
        event_id = _login(event.get("id"), f"{context}.activities[{index}].id")
        _login(event.get("actor"), f"{context}.activities[{index}].actor")
        created_at = _timestamp(
            event.get("created_at"), f"{context}.activities[{index}].created_at"
        )
        normalized_event = dict(event)
        normalized_event["kind"] = kind
        candidates.append((created_at, event_id, normalized_event))
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], item[1]))[2]


def classify_snapshot(snapshot: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    pull_requests = snapshot.get("pull_requests")
    if not isinstance(pull_requests, list):
        raise StateError("snapshot.pull_requests must be a JSON array")

    target_user = state["target_user"]
    processed = state["processed"]
    output: list[dict[str, Any]] = []
    counts = {
        "total": len(pull_requests),
        "authored_open": 0,
        "latest_by_target_user": 0,
        "already_processed": 0,
        "candidates": 0,
    }

    for index, review in enumerate(pull_requests):
        context = f"snapshot.pull_requests[{index}]"
        if not isinstance(review, dict):
            raise StateError(f"{context} must be a JSON object")
        if str(review.get("state", "")).strip().casefold() != "open":
            continue
        author = _login(review.get("author"), f"{context}.author")
        if author.casefold() != target_user.casefold():
            continue
        counts["authored_open"] += 1

        latest_event = _latest_human_update(review.get("activities"), context)
        if latest_event is None:
            continue
        if _login(latest_event.get("actor"), f"{context}.latest.actor").casefold() == target_user.casefold():
            counts["latest_by_target_user"] += 1
            continue

        repository = _login(review.get("repository"), f"{context}.repository")
        key = _state_key(review.get("provider"), repository, review.get("number"))
        prior = processed.get(key)
        if (
            isinstance(prior, dict)
            and prior.get("event_id") == latest_event["id"]
            and prior.get("event_kind") == latest_event["kind"]
        ):
            counts["already_processed"] += 1
            continue

        candidate = {
            "provider": _login(review.get("provider"), f"{context}.provider").casefold(),
            "repository": repository,
            "source_repository": _login(
                review.get("source_repository") or repository,
                f"{context}.source_repository",
            ),
            "number": review.get("number"),
            "url": _login(review.get("url"), f"{context}.url"),
            "author": author,
            "source_branch": _login(review.get("source_branch"), f"{context}.source_branch"),
            "target_branch": _login(review.get("target_branch"), f"{context}.target_branch"),
            "head_sha": _login(review.get("head_sha"), f"{context}.head_sha"),
            "latest_event": latest_event,
        }
        output.append(candidate)

    output.sort(key=lambda item: (item["provider"], item["repository"], str(item["number"])))
    counts["candidates"] = len(output)
    return {
        "schema_version": SCHEMA_VERSION,
        "target_user": target_user,
        "counts": counts,
        "candidates": output,
    }


def record_result(state_path: Path, result: dict[str, Any]) -> str:
    state = _load_state(state_path)
    result_target_user = _login(result.get("target_user"), "result.target_user")
    if result_target_user.casefold() != state["target_user"].casefold():
        raise StateError(
            "result target_user does not match state target_user: "
            f"{result_target_user!r} != {state['target_user']!r}"
        )
    outcome = _login(result.get("outcome"), "result.outcome").casefold()
    if outcome not in RECORDABLE_OUTCOMES:
        raise StateError(
            "result.outcome must be remediated or no-action before it can be recorded"
        )
    key = _state_key(result.get("provider"), result.get("repository"), result.get("number"))
    event_id = _login(result.get("event_id"), "result.event_id")
    event_kind = _login(result.get("event_kind"), "result.event_kind").casefold()
    if event_kind not in HUMAN_UPDATE_KINDS:
        raise StateError(f"result.event_kind is not an allowed human update kind: {event_kind}")
    event_created_at = _login(result.get("event_created_at"), "result.event_created_at")
    _timestamp(event_created_at, "result.event_created_at")

    state["processed"][key] = {
        "event_id": event_id,
        "event_kind": event_kind,
        "event_created_at": event_created_at,
        "outcome": outcome,
        "head_sha": str(result.get("head_after") or result.get("head_before") or ""),
        "commit_sha": str(result.get("commit_sha") or ""),
        "comment_url": str(result.get("comment_url") or ""),
        "recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    _write_object(state_path, state)
    return key


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create or resume monitor state")
    init_parser.add_argument("--state", required=True, type=Path)
    init_parser.add_argument("--target-user", required=True)

    classify_parser = subparsers.add_parser("classify", help="Select unprocessed candidates")
    classify_parser.add_argument("--state", required=True, type=Path)
    classify_parser.add_argument("--snapshot", required=True, type=Path)
    classify_parser.add_argument("--output", required=True, type=Path)

    record_parser = subparsers.add_parser("record", help="Record a terminal worker result")
    record_parser.add_argument("--state", required=True, type=Path)
    record_parser.add_argument("--result", required=True, type=Path)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        if args.command == "init":
            status = init_state(args.state, args.target_user)
            payload = {"status": status, "state": str(args.state)}
        elif args.command == "classify":
            state = _load_state(args.state)
            snapshot = _read_object(args.snapshot, "snapshot file")
            payload = classify_snapshot(snapshot, state)
            _write_object(args.output, payload)
            payload = {
                "status": "classified",
                "output": str(args.output),
                "counts": payload["counts"],
            }
        else:
            result = _read_object(args.result, "result file")
            key = record_result(args.state, result)
            payload = {"status": "recorded", "key": key}
    except StateError as exc:
        print(json.dumps({"status": "error", "error": f"Error: {exc}"}, sort_keys=True))
        return 1
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
