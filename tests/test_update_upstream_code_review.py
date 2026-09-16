"""Tests for the upstream code-review update automation.

Required packages: none (Python standard library only).
Run with: python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "update-upstream-code-review.py"
SPEC = importlib.util.spec_from_file_location("update_upstream_code_review", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
update_upstream = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(update_upstream)


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class UpstreamUpdateTests(unittest.TestCase):
    def setUp(self) -> None:
        scratch = os.environ.get("KIROCREW_SCRATCH")
        self.temporary_directory = tempfile.TemporaryDirectory(dir=scratch)
        self.root = Path(self.temporary_directory.name)
        self.source = self.root / "upstream/source.md"
        self.license = self.root / "LICENSES/upstream.txt"
        self.protocol = self.root / "references/protocol.md"
        self.manifest_path = self.root / "upstream.json"
        self.source.parent.mkdir(parents=True)
        self.license.parent.mkdir(parents=True)
        self.protocol.parent.mkdir(parents=True)
        self.source.write_bytes(b"source-v1\n")
        self.license.write_bytes(b"license-v1\n")
        self.protocol.write_bytes(b"protocol-v1\n")
        self.commit = "a" * 40
        self.write_manifest()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_manifest(
        self,
        *,
        status: str = "reviewed",
        pinned_commit: str | None = None,
        reviewed_commit: str | None = None,
        protocol_hash: str | None = None,
    ) -> None:
        pinned = pinned_commit or self.commit
        reviewed = reviewed_commit or self.commit
        manifest = {
            "schema_version": 1,
            "upstream": {
                "repository": "owner/repository",
                "ref": "main",
                "source_path": "skills/code-review/SKILL.md",
                "license_path": "LICENSE",
                "pinned_commit": pinned,
                "source_sha256": digest(self.source.read_bytes()),
                "license_sha256": digest(self.license.read_bytes()),
            },
            "local": {
                "source_snapshot": "upstream/source.md",
                "license": "LICENSES/upstream.txt",
                "adapted_protocol": "references/protocol.md",
            },
            "adaptation": {
                "status": status,
                "reviewed_commit": reviewed,
                "protocol_sha256": protocol_hash or digest(self.protocol.read_bytes()),
            },
        }
        self.manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )

    def load(self) -> dict[str, object]:
        return update_upstream.load_manifest(self.manifest_path)

    def test_reviewed_manifest_validates(self) -> None:
        result = update_upstream.validate_local_state(
            self.manifest_path,
            self.load(),
            require_reviewed=True,
        )

        self.assertEqual("reviewed", result["status"])
        self.assertEqual(self.commit, result["reviewed_commit"])

    def test_protocol_change_requires_mark_reviewed(self) -> None:
        self.protocol.write_bytes(b"protocol-v2\n")

        with self.assertRaisesRegex(update_upstream.UpdateError, "without mark-reviewed"):
            update_upstream.validate_local_state(
                self.manifest_path,
                self.load(),
                require_reviewed=True,
            )

        result = update_upstream.command_mark_reviewed(
            argparse.Namespace(manifest=self.manifest_path)
        )
        validated = update_upstream.validate_local_state(
            self.manifest_path,
            self.load(),
            require_reviewed=True,
        )
        self.assertEqual(digest(b"protocol-v2\n"), result["protocol_sha256"])
        self.assertEqual("reviewed", validated["status"])

    def test_pending_adaptation_fails_required_validation(self) -> None:
        self.write_manifest(
            status="pending",
            pinned_commit="b" * 40,
            reviewed_commit=self.commit,
        )

        with self.assertRaisesRegex(update_upstream.UpdateError, "adaptation is pending"):
            update_upstream.validate_local_state(
                self.manifest_path,
                self.load(),
                require_reviewed=True,
            )

    def test_mark_reviewed_records_current_protocol_and_commit(self) -> None:
        new_commit = "b" * 40
        self.write_manifest(
            status="pending",
            pinned_commit=new_commit,
            reviewed_commit=self.commit,
        )
        self.protocol.write_bytes(b"protocol-v2\n")

        result = update_upstream.command_mark_reviewed(
            argparse.Namespace(manifest=self.manifest_path)
        )
        updated = self.load()

        self.assertEqual("reviewed", result["status"])
        self.assertEqual(new_commit, updated["adaptation"]["reviewed_commit"])
        self.assertEqual(
            digest(b"protocol-v2\n"),
            updated["adaptation"]["protocol_sha256"],
        )

    def test_sync_updates_snapshot_and_marks_adaptation_pending(self) -> None:
        latest_commit = "b" * 40
        github_output = self.root / "github-output.txt"

        def response(url: str) -> bytes:
            if url.endswith("/LICENSE"):
                return b"license-v2\n"
            return b"source-v2\n"

        with (
            mock.patch.object(update_upstream, "latest_source_commit", return_value=latest_commit),
            mock.patch.object(update_upstream, "request_bytes", side_effect=response),
        ):
            result = update_upstream.command_sync(
                argparse.Namespace(
                    manifest=self.manifest_path,
                    github_output=github_output,
                )
            )

        updated = self.load()
        self.assertTrue(result["changed"])
        self.assertEqual(b"source-v2\n", self.source.read_bytes())
        self.assertEqual(b"license-v2\n", self.license.read_bytes())
        self.assertEqual(latest_commit, updated["upstream"]["pinned_commit"])
        self.assertEqual("pending", updated["adaptation"]["status"])
        self.assertIn("changed=true", github_output.read_text(encoding="utf-8"))

    def test_sync_is_noop_when_upstream_commit_matches(self) -> None:
        with mock.patch.object(
            update_upstream,
            "latest_source_commit",
            return_value=self.commit,
        ):
            result = update_upstream.command_sync(
                argparse.Namespace(manifest=self.manifest_path, github_output=None)
            )

        self.assertFalse(result["changed"])
        self.assertEqual("reviewed", self.load()["adaptation"]["status"])

    def test_token_is_only_sent_to_github_api(self) -> None:
        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "secret-token"}, clear=False):
            api_headers = update_upstream.request_headers(
                "https://api.github.com/repos/owner/repository/commits"
            )
            raw_headers = update_upstream.request_headers(
                "https://raw.githubusercontent.com/owner/repository/commit/file"
            )

        self.assertEqual("Bearer secret-token", api_headers["Authorization"])
        self.assertNotIn("Authorization", raw_headers)


if __name__ == "__main__":
    unittest.main()
