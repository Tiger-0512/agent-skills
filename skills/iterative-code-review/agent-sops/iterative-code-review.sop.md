# Iterative Code Review

## Overview

Run independent Standards and Spec reviews against a pinned baseline, adjudicate every candidate, repair all valid in-scope findings, validate the change, and repeat with fresh reviewers until clean or a bounded safety stop fires.

## Parameters

- **review_target** (required): Repository path and change target, such as the current branch, a branch name, merge request, pull request, or working-tree diff.
- **fixed_point** (optional, default: "auto"): Commit, branch, tag, or merge-base reference. `auto` means the target branch for a review request or the repository's default branch otherwise.
- **spec_source** (optional, default: "auto"): Issue, local file, URL, or `none`. `auto` uses the discovery order from the bundled two-axis review protocol.
- **max_rounds** (optional, default: 5): Maximum completed review rounds. Five permits several repair passes while bounding cost and churn.
- **stagnation_rounds** (optional, default: 2): Consecutive no-reduction transitions allowed before stopping. Two tolerates one noisy review while detecting non-convergence.
- **validation_commands** (optional, default: "auto"): Explicit test, lint, type-check, and build commands. `auto` discovers repository instructions and affected-package checks.
- **publication_policy** (optional, default: "local-only"): One of `local-only`, `commit`, `commit-and-push`, or an explicit user-defined policy covering review replies.

**Constraints for parameter acquisition:**
- If all required parameters are already provided, You MUST proceed to the Steps
- If any required parameters are missing, You MUST ask for them before proceeding
- When asking for parameters, You MUST request all parameters in a single prompt
- When asking for parameters, You MUST use the exact parameter names as defined
- You MUST infer optional parameters from explicit user wording and repository metadata when safe.
- You MUST NOT infer permission to commit, push, publish comments, resolve threads, approve, or merge because those actions modify shared state.

## Steps

### 1. Establish the isolated review workspace

Resolve the repository and prepare a workspace where iterative repairs cannot disturb unrelated user changes.

**Constraints:**
- You MUST inspect repository status before changing files.
- For a branch, merge request, or pull request, You MUST use an isolated worktree unless the user explicitly requests the current worktree.
- For an uncommitted working-tree review, You MUST preserve the current worktree because moving the changes would alter the review target.
- You MUST record the starting `HEAD`, branch, and status.
- You MUST NOT overwrite, reset, clean, stash, or discard pre-existing changes because they may belong to the user.
- If safe isolation is impossible, You MUST hard stop and explain the conflicting state.
- On success, You MUST proceed to Step 2.

### 2. Pin scope and sources

Resolve the fixed point once and identify the specification and standards sources using the bundled two-axis review protocol.

**Constraints:**
- You MUST read `references/code-review-protocol.md` before resolving review sources.
- You MUST verify that `references/code-review-protocol.md` and `LICENSES/mattpocock-skills-MIT.txt` are present before continuing.
- If either bundled file is unavailable, You MUST hard stop because the installation is incomplete and its review contract or required attribution cannot be verified.
- You MUST resolve `fixed_point` to an immutable commit and compute the three-dot merge-base comparison once.
- You MUST use the same baseline commit for every round even when `HEAD` changes after repairs.
- You MUST record the baseline SHA, initial review-head SHA, diff command, commit list, specification source, and standards-source paths.
- If `spec_source` is unavailable, You MUST ask once whether the Spec axis should be skipped; if the user confirms `none`, You MUST record that limitation in every result.
- You MUST NOT silently change the baseline or specification because moving criteria can produce false convergence.
- If the baseline is invalid or the initial diff is empty, You MUST hard stop with the exact reason.
- On success, You MUST proceed to Step 3.

### 3. Initialize durable loop state

Create a state file outside the reviewed diff and initialize it with the pinned baseline.

**Constraints:**
- You MUST choose `STATE_FILE` under a runtime-provided session scratch directory when one is available; otherwise You MUST use a unique path returned by `git rev-parse --git-path iterative-code-review`.
- You MUST run `scripts/review-loop-state.py init --state "$STATE_FILE" --fixed-point "$FIXED_POINT" --baseline-sha "$BASELINE_SHA"` from this skill's directory.
- You MUST verify that the script returns `status: initialized` before proceeding.
- You MUST NOT store loop state in a tracked repository path because orchestration metadata must not enter the product diff.
- On success, You MUST proceed to Step 4.

### 4. Run a fresh two-axis review

Dispatch Standards and Spec reviewers concurrently in new contexts, following the bundled two-axis review protocol's prompts and separation rules.

**Constraints:**
- You MUST give both reviewers the pinned diff command, current commit list, and current review-head SHA.
- You MUST give the Standards reviewer the discovered standards sources and the complete smell baseline from `references/code-review-protocol.md`.
- You MUST give the Spec reviewer the resolved specification, unless the user explicitly selected `none`.
- You MUST require each reviewer to report file, symbol or hunk, rule or requirement citation, severity, evidence, and a concise summary for every candidate.
- You MUST use fresh reviewer contexts that receive no previous-round findings because prior findings would bias an allegedly independent re-review.
- Reviewers MUST NOT edit files because independent review and repair must remain separate roles.
- You MUST validate that both requested axis reports completed; retry a transiently failed axis once, then hard stop if it still fails.
- You MUST NOT treat reviewer silence caused by an error or truncated output as a clean review because absence of evidence is not evidence of absence.
- On success, You MUST proceed to Step 5.

### 5. Adjudicate and record candidates

Verify every candidate against the current code and cited source, then write one round JSON file.

**Constraints:**
- You MUST classify each candidate as `actionable`, `rejected`, or `deferred`.
- You MUST use `actionable` only when the finding is valid, in scope, reproducible from the current diff, and supported by the cited standard or requirement.
- You MUST use `rejected` for false positives and include a concrete rationale.
- You MUST use `deferred` only when a valid finding requires user input, product design, unavailable access, or explicitly excluded scope.
- You MUST re-read the latest review-thread reply and resolution state before adjudicating an external review comment because an older snapshot may no longer represent the requested policy.
- You MUST NOT merge or rerank Standards and Spec findings because the axes must remain separately auditable.
- You MUST assign each candidate these fields: `axis`, `file`, `symbol`, `rule`, `severity`, `summary`, `disposition`, `rationale`, and `repair_status`.
- You MUST set `repair_status` to `not-attempted` for actionable candidates and `not-applicable` otherwise.
- You MUST write the round JSON using the schema in the Round File Contract below.
- If any finding is `deferred`, You MUST proceed to Step 9 without editing around the unresolved decision.
- If actionable findings exist, You MUST proceed to Step 6; otherwise You MUST proceed to Step 7.

### 6. Repair actionable findings

Fix every actionable finding in the orchestrator context while preserving scope and user changes.

**Constraints:**
- You MUST inspect relevant definitions, callers, tests, and repository guidance before editing.
- You MUST make the smallest coherent root-cause repair for each finding.
- You MUST add or update a regression test when behavior changes or when a practical automated test can reproduce the defect.
- You MUST update each repaired candidate's `repair_status` to `fixed` and summarize the repair.
- If a finding cannot be repaired safely, You MUST leave it `unfixed`, record the blocker, and proceed to Step 9.
- You MUST NOT weaken tests, disable checks, suppress diagnostics, or change the specification merely to make the review pass because that would create false convergence.
- You MUST NOT commit, push, publish replies, or resolve threads in this step because publication occurs only after convergence and explicit authorization.
- On success, You MUST proceed to Step 7.

### 7. Validate the current change

Run repository-appropriate checks and record their exact commands and outcomes in the round JSON.

**Constraints:**
- You MUST run targeted tests for repaired behavior in every repair round.
- You MUST run applicable formatter checks, lint, type checks, and affected-package builds according to repository instructions.
- For a no-finding round, You MUST run the final relevant validation suite before declaring success.
- If full validation is prohibitively expensive, You MUST run the strongest affected-scope validation available and record what was not run and why.
- You MUST set `validation.status` to `passed` only when every required command succeeds.
- If validation fails, You MUST diagnose and repair failures caused by this change, then rerun the failed and dependent checks before recording the round.
- You MUST NOT record `passed` when a command was skipped without an explicit repository- or user-approved reason because the state checker treats `passed` as evidence.
- If validation cannot be made to pass safely, You MUST set `validation.status` to `failed` and proceed to Step 9.
- On success, You MUST proceed to Step 8.

### 8. Evaluate convergence

Append the completed round and obey the deterministic state checker's decision.

**Constraints:**
- You MUST run `scripts/review-loop-state.py add-round --state "$STATE_FILE" --round-file "$ROUND_FILE" --max-rounds "$MAX_ROUNDS" --stagnation-rounds "$STAGNATION_ROUNDS"`.
- You MUST parse the returned `decision` without reinterpreting its counts or safety-stop reason.
- If the decision is `continue`, You MUST verify that repository `HEAD` and status contain only expected changes, then return to Step 4 with fresh reviewers.
- If the decision is `success`, You MUST proceed to Step 10.
- If the decision is `stop`, You MUST proceed to Step 9.
- You MUST NOT run another repair round after `stop` because the configured safety bound has fired.

### 9. Stop safely without claiming convergence

Preserve all completed work and report why the loop could not reach a clean result.

**Constraints:**
- You MUST report the stop reason, completed rounds, unresolved or deferred findings, validation failures, and current worktree location.
- You MUST distinguish code repair status, validation status, external comment replies, and thread resolution state.
- You MUST leave repaired files available for inspection unless the user explicitly asks to discard them.
- You MUST NOT claim the change is clean, ready, approved, or complete because convergence was not established.
- You MUST NOT publish partial work unless `publication_policy` explicitly permits it because partial publication can misrepresent review readiness.
- This step terminates the SOP.

### 10. Publish only authorized converged work

After a clean review and passing validation, perform only the publication actions authorized by `publication_policy`.

**Constraints:**
- You MUST recheck `HEAD`, remote branch state, and worktree status before committing or pushing.
- If `publication_policy` is `local-only`, You MUST leave the converged changes uncommitted and report their location.
- If commits are authorized, You MUST create focused commits without rewriting unrelated user history.
- If push is authorized, You MUST push the explicit feature branch and report the resulting full review URL when one exists.
- If review replies are authorized, You MUST reply to each applicable thread with the repair and validation evidence and leave resolution to the reviewer unless the user explicitly authorized resolution.
- You MUST NOT approve or merge because convergence authorization does not imply approval or merge authorization.
- On success, You MUST proceed to Step 11.

### 11. Report the final result

Present the converged outcome and an auditable round summary.

**Constraints:**
- You MUST report the pinned baseline, final `HEAD`, number of rounds, findings per axis per round, repairs, validation commands, publication actions, and any validation limitations.
- You MUST state that the latest fresh Standards and Spec reviews contained zero valid in-scope findings.
- If the Spec axis was explicitly skipped, You MUST say that only Standards convergence was established.
- You MUST distinguish external reviewer-thread resolution from self-review convergence.
- This step terminates the SOP successfully.

## Round File Contract

Each completed round file MUST be valid JSON with this shape:

```json
{
  "round": 1,
  "reviewed_head": "0123456789abcdef",
  "findings": [
    {
      "axis": "standards",
      "file": "src/example.py",
      "symbol": "build_report",
      "rule": "CONTRIBUTING.md:42",
      "severity": "medium",
      "summary": "The new branch bypasses required validation.",
      "disposition": "actionable",
      "rationale": "The cited rule applies and the bypass reproduces.",
      "repair_status": "fixed",
      "repair_summary": "Routed both branches through validate_input."
    }
  ],
  "validation": {
    "status": "passed",
    "commands": ["pytest tests/test_example.py"],
    "summary": "12 tests passed."
  }
}
```

Allowed values:
- `axis`: `standards`, `spec`
- `severity`: `critical`, `high`, `medium`, `low`
- `disposition`: `actionable`, `rejected`, `deferred`
- `repair_status`: `fixed`, `unfixed`, `not-attempted`, `not-applicable`
- `validation.status`: `passed`, `failed`, `not-run`

## Examples

### Example 1: Converges in two rounds

**Input:**
- `review_target`: current feature branch
- `fixed_point`: `origin/main`
- `max_rounds`: `5`
- `publication_policy`: `local-only`

**Expected behavior:** Round 1 finds and repairs two valid issues, targeted validation passes, and the checker returns `continue`. Fresh reviewers find no valid issues in round 2, final validation passes, and the checker returns `success`.

### Example 2: Stops on repeated findings

**Input:**
- `review_target`: merge request branch
- `stagnation_rounds`: `2`

**Expected behavior:** If the same stable finding set reappears after repair, or finding counts fail to decrease for two consecutive transitions, the checker returns `stop`. The agent reports the remaining findings and does not claim convergence.

## Troubleshooting

### The bundled review protocol is missing

Reinstall `iterative-code-review` from its published source. Do not continue without both the protocol and upstream MIT notice because the review contract and attribution would be incomplete.

### A reviewer axis fails

Retry that axis once with the same pinned inputs. If it fails again, stop rather than treating a missing report as clean.

### The repository changes during the loop

Stop before editing or publishing. Report the unexpected `HEAD` or status change and ask whether to restart from the new state.

### Validation is too expensive

Run the strongest affected-scope checks available, record the omitted suite and reason, and do not overstate the final assurance.

### The state checker rejects a round file

Correct the reported schema error in the round file. Do not edit the state file manually because that would bypass deterministic history validation.
