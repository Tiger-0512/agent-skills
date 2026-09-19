import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "review-monitor-state.py"
SPEC = importlib.util.spec_from_file_location("review_monitor_state", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ReviewMonitorStateTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.state_path = self.root / "state.json"
        MODULE.init_state(self.state_path, "alice")

    def state(self):
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    @staticmethod
    def review(activities, **overrides):
        value = {
            "provider": "github",
            "repository": "acme/widgets",
            "number": 42,
            "url": "https://github.example/acme/widgets/pull/42",
            "state": "open",
            "author": "alice",
            "source_branch": "alice/fix-widget",
            "target_branch": "main",
            "head_sha": "0123456789abcdef",
            "activities": activities,
        }
        value.update(overrides)
        return value

    @staticmethod
    def event(event_id, actor, created_at, kind="review_comment", automated=False):
        return {
            "id": event_id,
            "kind": kind,
            "actor": actor,
            "created_at": created_at,
            "automated": automated,
        }

    def test_external_latest_event_is_candidate_then_recorded_event_is_deduplicated(self):
        external = self.event("event-2", "bob", "2026-09-19T10:01:00Z")
        snapshot = {
            "pull_requests": [
                self.review(
                    [
                        self.event("event-1", "alice", "2026-09-19T10:00:00Z"),
                        external,
                    ]
                )
            ]
        }

        classified = MODULE.classify_snapshot(snapshot, self.state())
        self.assertEqual(1, classified["counts"]["candidates"])
        self.assertEqual("event-2", classified["candidates"][0]["latest_event"]["id"])
        self.assertEqual("acme/widgets", classified["candidates"][0]["source_repository"])

        MODULE.record_result(
            self.state_path,
            {
                "provider": "github",
                "repository": "acme/widgets",
                "target_user": "alice",
                "number": 42,
                "event_id": "event-2",
                "event_kind": "review_comment",
                "event_created_at": "2026-09-19T10:01:00Z",
                "outcome": "remediated",
                "head_before": "0123456789abcdef",
                "head_after": "fedcba9876543210",
                "commit_sha": "fedcba9876543210",
                "comment_url": "https://github.example/acme/widgets/pull/42#comment-1",
            },
        )

        classified_again = MODULE.classify_snapshot(snapshot, self.state())
        self.assertEqual(0, classified_again["counts"]["candidates"])
        self.assertEqual(1, classified_again["counts"]["already_processed"])

        different_kind_snapshot = {
            "pull_requests": [
                self.review(
                    [
                        self.event(
                            "event-2",
                            "bob",
                            "2026-09-19T10:02:00Z",
                            kind="comment",
                        )
                    ]
                )
            ]
        }
        classified_different_kind = MODULE.classify_snapshot(
            different_kind_snapshot, self.state()
        )
        self.assertEqual(1, classified_different_kind["counts"]["candidates"])

    def test_target_user_latest_event_does_not_need_response(self):
        snapshot = {
            "pull_requests": [
                self.review(
                    [
                        self.event("event-1", "bob", "2026-09-19T10:00:00Z"),
                        self.event("event-2", "ALICE", "2026-09-19T10:01:00+00:00"),
                    ]
                )
            ]
        }

        classified = MODULE.classify_snapshot(snapshot, self.state())
        self.assertEqual(0, classified["counts"]["candidates"])
        self.assertEqual(1, classified["counts"]["latest_by_target_user"])

    def test_automated_and_system_events_do_not_override_latest_human_update(self):
        snapshot = {
            "pull_requests": [
                self.review(
                    [
                        self.event("event-1", "bob", "2026-09-19T10:00:00Z"),
                        self.event(
                            "event-2",
                            "ci-bot",
                            "2026-09-19T10:02:00Z",
                            kind="comment",
                            automated=True,
                        ),
                        self.event(
                            "event-3",
                            "system",
                            "2026-09-19T10:03:00Z",
                            kind="pipeline",
                        ),
                    ]
                )
            ]
        }

        classified = MODULE.classify_snapshot(snapshot, self.state())
        self.assertEqual(1, classified["counts"]["candidates"])
        self.assertEqual("event-1", classified["candidates"][0]["latest_event"]["id"])

    def test_closed_and_other_author_reviews_are_excluded(self):
        snapshot = {
            "pull_requests": [
                self.review(
                    [self.event("event-1", "bob", "2026-09-19T10:00:00Z")],
                    state="closed",
                ),
                self.review(
                    [self.event("event-2", "bob", "2026-09-19T10:01:00Z")],
                    number=43,
                    author="carol",
                ),
            ]
        }

        classified = MODULE.classify_snapshot(snapshot, self.state())
        self.assertEqual(0, classified["counts"]["authored_open"])
        self.assertEqual(0, classified["counts"]["candidates"])

    def test_timezone_is_required_for_stable_event_ordering(self):
        snapshot = {
            "pull_requests": [
                self.review([self.event("event-1", "bob", "2026-09-19T10:00:00")])
            ]
        }

        with self.assertRaisesRegex(MODULE.StateError, "must include a timezone"):
            MODULE.classify_snapshot(snapshot, self.state())

    def test_existing_state_rejects_a_different_target_user(self):
        with self.assertRaisesRegex(MODULE.StateError, "does not match"):
            MODULE.init_state(self.state_path, "bob")

    def test_non_terminal_outcome_cannot_be_recorded(self):
        with self.assertRaisesRegex(MODULE.StateError, "remediated or no-action"):
            MODULE.record_result(
                self.state_path,
                {
                    "provider": "github",
                    "repository": "acme/widgets",
                    "target_user": "alice",
                    "number": 42,
                    "event_id": "event-2",
                    "event_created_at": "2026-09-19T10:01:00Z",
                    "outcome": "failed",
                },
            )

    def test_result_for_a_different_target_user_cannot_be_recorded(self):
        with self.assertRaisesRegex(MODULE.StateError, "result target_user does not match"):
            MODULE.record_result(
                self.state_path,
                {
                    "provider": "github",
                    "repository": "acme/widgets",
                    "target_user": "bob",
                    "number": 42,
                    "event_id": "event-2",
                    "event_created_at": "2026-09-19T10:01:00Z",
                    "outcome": "no-action",
                },
            )

    def test_automated_marker_must_be_boolean(self):
        invalid_event = self.event("event-1", "bob", "2026-09-19T10:00:00Z")
        invalid_event["automated"] = "false"
        snapshot = {"pull_requests": [self.review([invalid_event])]}

        with self.assertRaisesRegex(MODULE.StateError, "automated must be a boolean"):
            MODULE.classify_snapshot(snapshot, self.state())


if __name__ == "__main__":
    unittest.main()
