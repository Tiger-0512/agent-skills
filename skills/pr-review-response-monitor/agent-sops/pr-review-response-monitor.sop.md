# PR Review Response Monitor

## Overview

Immediately scan one repository for open PRs/MRs authored by a specified user, process unhandled external review updates with one isolated worker per review, notify the chat, and continue a bounded periodic monitor.

## Table of Contents

- [Parameters](#parameters)
- [Steps](#steps)
- [Normalized Snapshot Contract](#normalized-snapshot-contract)
- [Examples](#examples)
- [Troubleshooting](#troubleshooting)

## Parameters

- **repository** (required): Repository HTTPS URL, provider `owner/name` identifier, or absolute local checkout path for exactly one GitHub or GitLab repository.
- **target_user** (required): Exact provider login of the PR/MR author whose pending review responses should be handled.
- **interval_seconds** (optional, default: 600): Delay between completed scans. Ten minutes balances review responsiveness with provider API load; values below 60 are invalid.
- **max_cycles** (optional, default: 48): Maximum scan cycles. At the default interval this bounds an unchanged monitor to roughly eight hours.
- **max_runtime_seconds** (optional, default: 28800): Maximum wall-clock runtime, also eight hours; the first exhausted bound stops the monitor.
- **max_concurrency** (optional, default: 4): Maximum simultaneous review workers. Four provides useful parallelism without an aggressive provider request burst.
- **provider** (optional, default: "auto"): `github`, `gitlab`, or `auto` inferred from repository metadata.
- **validation_commands** (optional, default: "auto"): Explicit repository test, lint, type-check, and build commands, or `auto` to discover repository instructions.
- **publication_policy** (optional, default: "commit-push-comment"): Authorized actions. This SOP accepts only `commit-push-comment`; use another workflow when publication is not authorized.

**Constraints for parameter acquisition:**
- If all required parameters are already provided, You MUST proceed to the Steps
- If any required parameters are missing, You MUST ask for them before proceeding
- When asking for parameters, You MUST request all parameters in a single prompt
- When asking for parameters, You MUST use the exact parameter names as defined
- You MUST infer `provider` from an unambiguous URL, remote, or checkout before asking the user.
- You MUST NOT infer `target_user` from a display name because display names are not stable provider identities.
- You MUST treat invocation of this remediation monitor as authorization for `publication_policy`; if the request does not explicitly authorize commit, push, and provider comments, You MUST stop because this SOP's publication contract is incomplete.

## Steps

### 1. Establish scope, authority, and durable state

Resolve the repository and provider, verify access, inspect local status, and initialize state before the immediate scan.

**Constraints:**
- You MUST read the parent skill's Security Guardrails and the bundled worker contract before proceeding.
- You MUST verify that the repository identity, default branch, remote, and exact `target_user` login are unambiguous.
- You MUST inspect the current checkout without modifying, stashing, cleaning, or resetting it because unrelated work may belong to the user.
- You MUST verify least-privilege authenticated read access plus permission to push only review source branches and post review comments.
- You MUST stop on missing or expired authentication and report the provider's remediation because bypassing authentication would violate repository access controls.
- You MUST choose a unique `STATE_FILE` in runtime-provided scratch storage; when scratch storage is unavailable, You MUST use an untracked path under `git rev-parse --git-path pr-review-response-monitor`.
- You MUST initialize or resume state with `scripts/review-monitor-state.py init` and verify its target user matches `target_user`.
- You MUST record the monitoring goal, bounds, state path, repository, and next action in the runtime's durable session ledger when one is available.
- On success, You MUST proceed to Step 2.

### 2. Fetch and normalize complete provider activity

Fetch all open PRs/MRs authored by `target_user` and their complete review-relevant human activity into `SNAPSHOT_FILE`.

**Constraints:**
- You MUST use the provider's authenticated API or official CLI and paginate every collection that can truncate results.
- You MUST fetch actor identities and event timestamps for reviews, change requests, approvals, comments, thread changes, commits, and pushes.
- You MUST preserve the base `repository` and the writable `source_repository`; for a same-repository review, You MUST set both to the same identifier.
- You MUST normalize the result to the Normalized Snapshot Contract below and write it to `SNAPSHOT_FILE` outside the product diff.
- You MUST retain event IDs and metadata but omit review bodies because the classifier needs identity and ordering, not durable copies of potentially sensitive text.
- You MUST NOT use a PR/MR `updated_at` field alone because it does not prove who performed the latest human update.
- You MUST exclude automated, bot, pipeline, label, milestone, mergeability, and other system-only events because they do not imply an author response.
- If fetching fails transiently, You SHOULD retry once; if it still fails, You MUST leave state unchanged and proceed to Step 9 with a blocked result.
- On success, You MUST proceed to Step 3.

### 3. Select unprocessed reviews needing a response

Run the deterministic classifier to identify candidates whose latest human review update came from someone other than `target_user`.

**Constraints:**
- You MUST run `scripts/review-monitor-state.py classify --state "$STATE_FILE" --snapshot "$SNAPSHOT_FILE" --output "$CANDIDATES_FILE"` from the skill directory.
- You MUST verify the command succeeds and the output target user matches `target_user`.
- You MUST use the candidate list exactly as produced; You MUST NOT add reviews based on intuition because that bypasses the documented definition and deduplication state.
- If the candidate list is empty, You MUST proceed to Step 10 without emitting a routine chat notification.
- If candidates exist, You MUST proceed to Step 4.

### 4. Plan isolated and race-safe execution

Prepare one isolated worktree and one unique result path per candidate, while detecting source-branch collisions.

**Constraints:**
- You MUST verify each candidate source branch in its `source_repository` is writable, is not the base repository's protected/default branch, and still points to the snapshot `head_sha`.
- You MUST create or reuse a distinct isolated worktree at the assigned head SHA for each `(source_repository, source_branch)` pair; You MUST NOT edit the user's current checkout because parallel repair could overwrite unrelated work.
- If the source branch is already checked out elsewhere, You MUST create a uniquely named temporary local worker branch at the assigned SHA and preserve the explicit source branch as the push destination.
- You MUST assign each candidate a unique absolute `RESULT_FILE` path and pass literal paths to its worker.
- You MUST run candidates on distinct `(source_repository, source_branch)` pairs in parallel up to `max_concurrency`.
- You MUST queue candidates sharing the same source repository and source branch serially because parallel pushes to one remote ref would race and invalidate review context.
- If safe isolation is impossible, You MUST create a blocked result and proceed to Step 7 for that candidate.
- On success, You MUST proceed to Step 5.

### 5. Dispatch one worker per candidate

Dispatch all currently runnable candidates as one parallel batch, one isolated subagent for each PR/MR.

**Constraints:**
- You MUST use the runtime's supported subagent dispatcher and create exactly one worker task per candidate.
- You MUST instruct each worker to read `references/review-worker-contract.md`, inspect only its assigned review, use its assigned worktree, and write only its assigned `RESULT_FILE`.
- You MUST pass the review URL, provider, base repository, source repository, number, target user, source branch, target branch, snapshot head SHA, latest event kind, latest event ID and actor, validation policy, worktree path, and result path.
- You MUST keep worker prompts concise and pass structured inputs through files when the runtime supports them.
- You MUST NOT perform delegated review or repair work in the orchestrator because duplicate actors could create conflicting commits and comments.
- You MUST wait for every worker in the batch to reach a terminal result before proceeding to Step 6.

### 6. Collect and validate worker results

Validate every `RESULT_FILE` against the worker contract and preserve partial successes.

**Constraints:**
- You MUST require one terminal outcome per candidate: `remediated`, `no-action`, `stale`, `blocked`, or `failed`.
- You MUST verify that review identity, `event_kind`, and `event_id` match the dispatched candidate.
- For `remediated`, You MUST verify a commit SHA, explicit push success, provider comment URL, and validation evidence are present.
- For `no-action`, You MUST verify the worker supplied a concrete adjudication rationale and did not create an empty commit.
- For malformed or missing output, You SHOULD retry that worker once with the validation error; after one failed retry, You MUST classify it as `failed`.
- You MUST retain successful outputs when another worker fails because independent PR/MR results remain valid.
- On completion, You MUST proceed to Step 7.

### 7. Record only safely completed events

Update deduplication state sequentially after all parallel workers have stopped writing results.

**Constraints:**
- For each `remediated` or `no-action` result, You MUST run `scripts/review-monitor-state.py record --state "$STATE_FILE" --result "$RESULT_FILE"` and verify `status` is `recorded`.
- You MUST serialize state writes because concurrent atomic replacements could lose another worker's record.
- You MUST NOT record `stale`, `blocked`, or `failed` events because a later cycle must be able to retry or inspect their replacement event.
- You MUST update the durable session ledger with completed review URLs, terminal outcomes, and the next monitoring action when a ledger is available.
- On completion, You MUST proceed to Step 8.

### 8. Notify the chat after review handling

⚠️ MANDATORY OUTPUT STEP — tell the user what happened before returning to monitoring.

**Constraints:**
- You MUST emit one concise chat notification after every non-empty worker batch.
- You MUST list each PR/MR as a full clickable URL, the external actor or reviewer handle, outcome, commit SHA when present, push status, provider comment URL when present, validation summary, and any user action still required.
- You MUST explicitly identify reviews that need the user to follow up with a reviewer.
- You MUST distinguish code publication, provider comment publication, and reviewer-thread resolution because one does not prove the others.
- You MUST report `stale`, `blocked`, and `failed` results without claiming completion.
- You MUST NOT include review bodies, secrets, or sensitive data because the chat notification is an additional disclosure surface.
- On completion, You MUST proceed to Step 10.

### 9. Report a cycle-level blocker

Report a provider, authentication, state, or monitoring failure that prevented candidate processing.

**Constraints:**
- You MUST identify the failed stage, affected repository, retry performed, and safe remediation.
- You MUST leave state unchanged so an unprocessed event cannot be silently skipped.
- You MUST stop immediately for authentication or authorization failures because repeated polling will not repair credentials.
- For other transient failures within the configured bounds, You MAY proceed to Step 10 after reporting once.
- Otherwise, this step terminates the SOP without claiming success.

### 10. Continue or stop the bounded monitor

Return to periodic monitoring only after the current cycle's workers and required notification are complete.

**Constraints:**
- You MUST stop when `max_cycles` or `max_runtime_seconds` is exhausted and report totals for scans, handled reviews, no-action reviews, stale results, and failures.
- If a user stop is observed, You MUST stop the monitor and report the last completed cycle.
- If bounds remain, You MUST use the runtime's finite recurring monitor facility to schedule Step 2 after `interval_seconds`, preserving the same parameters and state path.
- You MUST set the monitor to wake even when generic review comments cannot be represented by a provider status gate.
- You MUST include the full cycle instructions, termination conditions, and required chat notification in the recurring monitor message.
- You MUST NOT emulate missing monitor support with an unbounded sleep loop because it cannot survive interruption or provide reliable user control.
- If monitor arming is asynchronous, You MUST end the current turn after requesting it and verify applied monitor state on the next wake.
- On the next scheduled wake, You MUST return to Step 2.

## Normalized Snapshot Contract

```json
{
  "pull_requests": [
    {
      "provider": "github",
      "repository": "acme/widgets",
      "source_repository": "alice/widgets-fork",
      "number": 42,
      "url": "https://github.example/acme/widgets/pull/42",
      "state": "open",
      "author": "alice",
      "source_branch": "alice/fix-widget",
      "target_branch": "main",
      "head_sha": "0123456789abcdef",
      "activities": [
        {
          "id": "review-9001",
          "kind": "change_request",
          "actor": "bob",
          "created_at": "2026-09-19T10:00:00Z",
          "automated": false
        }
      ]
    }
  ]
}
```

Allowed human activity kinds are `review`, `change_request`, `approval`, `comment`, `review_comment`, `review_thread`, `thread_reply`, `thread_resolution`, `commit`, and `push`.

## Examples

### Monitor one GitLab repository

**Input:**
- `repository`: `https://gitlab.example/acme/widgets`
- `target_user`: `alice`
- `interval_seconds`: `600`
- `max_cycles`: `48`
- `publication_policy`: `commit-push-comment`

**Expected behavior:** The first scan runs immediately. Matching MRs on distinct source branches are repaired in parallel, each result is validated and announced in chat, and the next scan is scheduled ten minutes after the completed cycle.

## Troubleshooting

### The provider shows a recent update but no candidate appears

Verify that the provider activity was normalized as an allowed human kind with a stable actor, event ID, and timezone-qualified timestamp. System events and updates by `target_user` intentionally do not qualify.

### The same review is selected repeatedly

Check that a terminal `remediated` or `no-action` result was recorded and that later snapshots preserve the provider event ID. Do not edit the state file manually because that bypasses schema and target-user checks.

### A source branch changed during repair

Keep the worker result as `stale`, publish nothing, and let the next cycle re-fetch the new head and latest review event.

### Authentication expires

Stop the monitor and ask the user to restore provider authentication. Do not request credentials in chat or switch to a broader account.
