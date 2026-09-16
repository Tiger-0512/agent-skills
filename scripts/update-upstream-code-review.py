#!/usr/bin/env python3
# Purpose: track and synchronize the bundled Matt Pocock code-review source.
# Dependencies: Python 3 standard library only; no package installation is required.
# Usage: run check, sync, validate, or mark-reviewed; use --help for details.
"""Manage the pinned upstream source behind the bundled review protocol.

The sync command updates only the upstream snapshot, license, and manifest. It
marks the adaptation pending so a human must reconcile the active protocol and
run mark-reviewed before validation can pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

SCHEMA_VERSION = 1
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class UpdateError(RuntimeError):
    """Raised when upstream synchronization cannot be completed safely."""


def require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise UpdateError(f"{field} must be a non-empty string")
    return value.strip()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise UpdateError(f"manifest does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise UpdateError(f"invalid JSON in {path}: {error}") from error
    except OSError as error:
        raise UpdateError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise UpdateError("manifest root must be an object")
    return value


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except OSError as error:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise UpdateError(f"cannot write {path}: {error}") from error


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    content = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    atomic_write(path, content.encode("utf-8"))


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    try:
        return sha256_bytes(path.read_bytes())
    except OSError as error:
        raise UpdateError(f"cannot hash {path}: {error}") from error


def validate_relative_path(raw_path: Any, field: str) -> str:
    value = require_string(raw_path, field).replace("\\", "/")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise UpdateError(f"{field} must stay within the skill directory")
    return value


def local_path(manifest_path: Path, relative_path: str) -> Path:
    root = manifest_path.resolve().parent
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise UpdateError(f"local path escapes skill directory: {relative_path}")
    return candidate


def normalize_manifest(raw: dict[str, Any]) -> dict[str, Any]:
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise UpdateError(f"schema_version must be {SCHEMA_VERSION}")

    upstream_raw = raw.get("upstream")
    local_raw = raw.get("local")
    adaptation_raw = raw.get("adaptation")
    if not isinstance(upstream_raw, dict):
        raise UpdateError("upstream must be an object")
    if not isinstance(local_raw, dict):
        raise UpdateError("local must be an object")
    if not isinstance(adaptation_raw, dict):
        raise UpdateError("adaptation must be an object")

    repository = require_string(upstream_raw.get("repository"), "upstream.repository")
    if not REPOSITORY_PATTERN.fullmatch(repository):
        raise UpdateError("upstream.repository must use owner/repository format")

    pinned_commit = require_string(
        upstream_raw.get("pinned_commit"), "upstream.pinned_commit"
    ).lower()
    if not COMMIT_PATTERN.fullmatch(pinned_commit):
        raise UpdateError("upstream.pinned_commit must be a 40-character SHA")

    reviewed_commit = require_string(
        adaptation_raw.get("reviewed_commit"), "adaptation.reviewed_commit"
    ).lower()
    if not COMMIT_PATTERN.fullmatch(reviewed_commit):
        raise UpdateError("adaptation.reviewed_commit must be a 40-character SHA")

    status = require_string(adaptation_raw.get("status"), "adaptation.status")
    if status not in {"reviewed", "pending"}:
        raise UpdateError("adaptation.status must be reviewed or pending")

    return {
        "schema_version": SCHEMA_VERSION,
        "upstream": {
            "repository": repository,
            "ref": require_string(upstream_raw.get("ref"), "upstream.ref"),
            "source_path": validate_relative_path(
                upstream_raw.get("source_path"), "upstream.source_path"
            ),
            "license_path": validate_relative_path(
                upstream_raw.get("license_path"), "upstream.license_path"
            ),
            "pinned_commit": pinned_commit,
            "source_sha256": require_string(
                upstream_raw.get("source_sha256"), "upstream.source_sha256"
            ).lower(),
            "license_sha256": require_string(
                upstream_raw.get("license_sha256"), "upstream.license_sha256"
            ).lower(),
        },
        "local": {
            "source_snapshot": validate_relative_path(
                local_raw.get("source_snapshot"), "local.source_snapshot"
            ),
            "license": validate_relative_path(local_raw.get("license"), "local.license"),
            "adapted_protocol": validate_relative_path(
                local_raw.get("adapted_protocol"), "local.adapted_protocol"
            ),
        },
        "adaptation": {
            "status": status,
            "reviewed_commit": reviewed_commit,
            "protocol_sha256": require_string(
                adaptation_raw.get("protocol_sha256"), "adaptation.protocol_sha256"
            ).lower(),
        },
    }


def load_manifest(path: Path) -> dict[str, Any]:
    return normalize_manifest(read_json(path))


def validate_local_state(
    manifest_path: Path,
    manifest: dict[str, Any],
    *,
    require_reviewed: bool,
    allow_protocol_change: bool = False,
) -> dict[str, Any]:
    source_snapshot = local_path(manifest_path, manifest["local"]["source_snapshot"])
    license_path = local_path(manifest_path, manifest["local"]["license"])
    protocol_path = local_path(manifest_path, manifest["local"]["adapted_protocol"])

    actual_source_hash = sha256_file(source_snapshot)
    actual_license_hash = sha256_file(license_path)
    actual_protocol_hash = sha256_file(protocol_path)

    if actual_source_hash != manifest["upstream"]["source_sha256"]:
        raise UpdateError("upstream source snapshot hash does not match the manifest")
    if actual_license_hash != manifest["upstream"]["license_sha256"]:
        raise UpdateError("upstream license hash does not match the manifest")

    adaptation = manifest["adaptation"]
    if adaptation["status"] == "reviewed":
        if adaptation["reviewed_commit"] != manifest["upstream"]["pinned_commit"]:
            raise UpdateError("reviewed adaptation does not match the pinned upstream commit")
        if (
            actual_protocol_hash != adaptation["protocol_sha256"]
            and not allow_protocol_change
        ):
            raise UpdateError("adapted protocol changed without mark-reviewed")
    elif require_reviewed:
        raise UpdateError(
            "upstream adaptation is pending; reconcile the protocol and run mark-reviewed"
        )

    return {
        "status": adaptation["status"],
        "pinned_commit": manifest["upstream"]["pinned_commit"],
        "reviewed_commit": adaptation["reviewed_commit"],
        "source_sha256": actual_source_hash,
        "license_sha256": actual_license_hash,
        "protocol_sha256": actual_protocol_hash,
    }


def request_headers(url: str) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Tiger-0512-agent-skills-upstream-checker",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"
    return headers


def request_bytes(url: str) -> bytes:
    try:
        with urlopen(Request(url, headers=request_headers(url)), timeout=30) as response:
            return response.read()
    except HTTPError as error:
        raise UpdateError(f"GitHub returned HTTP {error.code} for {url}") from error
    except URLError as error:
        raise UpdateError(f"cannot reach GitHub for {url}: {error.reason}") from error


def request_json(url: str) -> Any:
    content = request_bytes(url)
    try:
        return json.loads(content)
    except json.JSONDecodeError as error:
        raise UpdateError(f"GitHub returned invalid JSON for {url}") from error


def latest_source_commit(manifest: dict[str, Any]) -> str:
    upstream = manifest["upstream"]
    repository = quote(upstream["repository"], safe="/")
    query = urlencode(
        {
            "sha": upstream["ref"],
            "path": upstream["source_path"],
            "per_page": 1,
        }
    )
    value = request_json(f"https://api.github.com/repos/{repository}/commits?{query}")
    if not isinstance(value, list) or not value or not isinstance(value[0], dict):
        raise UpdateError("GitHub returned no commit for the upstream source path")
    commit = require_string(value[0].get("sha"), "latest upstream commit").lower()
    if not COMMIT_PATTERN.fullmatch(commit):
        raise UpdateError("GitHub returned an invalid upstream commit SHA")
    return commit


def raw_url(repository: str, commit: str, path: str) -> str:
    encoded_repository = quote(repository, safe="/")
    encoded_path = quote(path, safe="/")
    return f"https://raw.githubusercontent.com/{encoded_repository}/{commit}/{encoded_path}"


def remote_status(manifest: dict[str, Any]) -> dict[str, Any]:
    latest = latest_source_commit(manifest)
    pinned = manifest["upstream"]["pinned_commit"]
    repository = manifest["upstream"]["repository"]
    return {
        "changed": latest != pinned,
        "previous_commit": pinned,
        "upstream_commit": latest,
        "short_sha": latest[:12],
        "compare_url": f"https://github.com/{repository}/compare/{pinned}...{latest}",
    }


def write_github_output(path: Path | None, result: dict[str, Any]) -> None:
    if path is None:
        return
    allowed_keys = {
        "changed",
        "previous_commit",
        "upstream_commit",
        "short_sha",
        "compare_url",
    }
    lines = []
    for key in allowed_keys:
        if key not in result:
            continue
        value = str(result[key]).lower() if isinstance(result[key], bool) else str(result[key])
        if "\n" in value or "\r" in value:
            raise UpdateError(f"unsafe newline in GitHub output field: {key}")
        lines.append(f"{key}={value}")
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    except OSError as error:
        raise UpdateError(f"cannot write GitHub output file: {error}") from error


def command_check(args: argparse.Namespace) -> dict[str, Any]:
    manifest = load_manifest(args.manifest)
    validate_local_state(args.manifest, manifest, require_reviewed=False)
    return remote_status(manifest)


def command_sync(args: argparse.Namespace) -> dict[str, Any]:
    manifest = load_manifest(args.manifest)
    validate_local_state(args.manifest, manifest, require_reviewed=True)
    result = remote_status(manifest)
    if not result["changed"]:
        write_github_output(args.github_output, result)
        return result

    upstream = manifest["upstream"]
    latest = result["upstream_commit"]
    source_content = request_bytes(
        raw_url(upstream["repository"], latest, upstream["source_path"])
    )
    license_content = request_bytes(
        raw_url(upstream["repository"], latest, upstream["license_path"])
    )

    atomic_write(
        local_path(args.manifest, manifest["local"]["source_snapshot"]),
        source_content,
    )
    atomic_write(local_path(args.manifest, manifest["local"]["license"]), license_content)

    upstream["pinned_commit"] = latest
    upstream["source_sha256"] = sha256_bytes(source_content)
    upstream["license_sha256"] = sha256_bytes(license_content)
    manifest["adaptation"]["status"] = "pending"
    atomic_write_json(args.manifest, manifest)
    write_github_output(args.github_output, result)
    return result | {"adaptation_status": "pending"}


def command_validate(args: argparse.Namespace) -> dict[str, Any]:
    manifest = load_manifest(args.manifest)
    return validate_local_state(args.manifest, manifest, require_reviewed=True)


def command_mark_reviewed(args: argparse.Namespace) -> dict[str, Any]:
    manifest = load_manifest(args.manifest)
    validate_local_state(
        args.manifest,
        manifest,
        require_reviewed=False,
        allow_protocol_change=True,
    )
    protocol_path = local_path(args.manifest, manifest["local"]["adapted_protocol"])
    manifest["adaptation"] = {
        "status": "reviewed",
        "reviewed_commit": manifest["upstream"]["pinned_commit"],
        "protocol_sha256": sha256_file(protocol_path),
    }
    atomic_write_json(args.manifest, manifest)
    return {
        "status": "reviewed",
        "reviewed_commit": manifest["adaptation"]["reviewed_commit"],
        "protocol_sha256": manifest["adaptation"]["protocol_sha256"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name, handler in (
        ("check", command_check),
        ("validate", command_validate),
        ("mark-reviewed", command_mark_reviewed),
    ):
        command = subparsers.add_parser(name)
        command.add_argument("--manifest", required=True, type=Path)
        command.set_defaults(handler=handler)

    sync = subparsers.add_parser("sync")
    sync.add_argument("--manifest", required=True, type=Path)
    sync.add_argument("--github-output", type=Path)
    sync.set_defaults(handler=command_sync)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = args.handler(args)
    except UpdateError as error:
        print(json.dumps({"status": "error", "error": str(error)}), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
