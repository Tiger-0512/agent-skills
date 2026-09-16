---
name: standards-spec-review-loop
description: "Repeatedly review, adjudicate, fix, and validate a code change until fresh Standards and Spec reviews find no valid in-scope findings. Use when the user asks for iterative self-review, review-fix-review loops, or remediation until clean; not for review-only requests."
version: 2.0.0
tags: [skill, code-review, remediation, convergence]
---

# Standards-Spec Review Loop

## Overview

This skill drives a bounded review → adjudicate → repair → validate → fresh-review loop. It includes an adapted two-axis Standards and Spec review protocol and succeeds only when both axes have zero valid in-scope findings and final validation passes.

## Usage

Use this skill when:
- The user asks to repeat review and fixes until the change is clean.
- One review pass may miss defects exposed by earlier repairs.
- A branch, merge request, pull request, or working-tree diff needs convergent self-review.

Do not use this skill for review-only requests, or when the user forbids code changes.

## Core Concepts

- **Pinned baseline:** Every round compares against the same resolved merge-base so the review scope cannot drift.
- **Fresh review:** Each round uses new, independent Standards and Spec reviewer contexts that do not receive prior findings.
- **Adjudicated finding:** A candidate becomes actionable only after the orchestrator verifies it against the current code and source rule or requirement.
- **Convergence:** Success requires zero actionable or deferred findings plus passing validation.
- **Bounded execution:** Maximum-round, repeated-finding, no-progress, cycle, and external-change guards prevent runaway repair loops.

## Bundled Review Protocol

You **MUST** read [references/code-review-protocol.md](references/code-review-protocol.md) before starting. It defines fixed-point resolution, specification and standards discovery, the smell baseline, independent reviewer prompts, and the two-axis output contract.

The protocol is adapted from Matt Pocock's `code-review` skill under the MIT License. The required upstream notice is included in [LICENSES/mattpocock-skills-MIT.txt](LICENSES/mattpocock-skills-MIT.txt).

You **MUST NOT** substitute a different review procedure because doing so would change the documented Standards and Spec contract.

## Workflow

After reading the bundled review protocol, You **MUST** read and execute [agent-sops/standards-spec-review-loop.sop.md](agent-sops/standards-spec-review-loop.sop.md).

You **MUST NOT** replace the two independent review axes with one combined reviewer because shared context allows one axis to mask the other.

## State Checker

`scripts/review-loop-state.py` validates and persists each completed round, computes stable finding fingerprints, and returns one decision: `continue`, `success`, or `stop`.

```bash
python3 scripts/review-loop-state.py init \
  --state "$STATE_FILE" --fixed-point "$FIXED_POINT" --baseline-sha "$BASELINE_SHA"

python3 scripts/review-loop-state.py add-round \
  --state "$STATE_FILE" --round-file "$ROUND_FILE" \
  --max-rounds 5 --stagnation-rounds 2
```

The script uses only the Python standard library. The SOP defines the round-file contract and how to act on each decision.

## Example

**Request:** “Review this branch, fix every valid finding, and repeat until clean.”

**Expected behavior:** Pin the target branch merge-base, run independent Standards and Spec reviews, fix adjudicated findings, validate the repairs, and repeat with fresh reviewers. Finish only on a clean review plus passing final checks, or report the exact safety stop and remaining findings.

## Quick Reference

| Situation | Required outcome |
|---|---|
| Bundled review protocol or license notice is missing | Stop because the installation is incomplete |
| Both axes have no valid findings and validation passes | `success` |
| Repairs and validation pass, but the round found valid issues | `continue` with fresh reviewers |
| A safety bound, deferred finding, failed repair, or external change blocks progress | `stop` with evidence |
| Commit, push, review reply, or thread resolution is requested | Perform only the explicitly authorized publication actions |
