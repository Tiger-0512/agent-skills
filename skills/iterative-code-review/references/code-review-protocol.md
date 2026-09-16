# Bundled Two-Axis Code Review Protocol

Adapted from Matt Pocock's [`code-review`](https://github.com/mattpocock/skills/tree/main/skills/engineering/code-review) skill at commit [`959a8e9f1edc3adbe2f7e3054bb6fbefa6696260`](https://github.com/mattpocock/skills/commit/959a8e9f1edc3adbe2f7e3054bb6fbefa6696260).

Copyright (c) 2026 Matt Pocock. Adapted and redistributed under the MIT License. The complete notice is in `../LICENSES/mattpocock-skills-MIT.txt`.

## Contents

- [Review contract](#review-contract)
- [Pin the fixed point](#pin-the-fixed-point)
- [Find the specification](#find-the-specification)
- [Find the standards](#find-the-standards)
- [Standards smell baseline](#standards-smell-baseline)
- [Run independent reviewers](#run-independent-reviewers)
- [Output contract](#output-contract)

## Review Contract

Review the diff between `HEAD` and one fixed point along two independent axes:

- **Standards:** whether the change follows documented repository standards and the heuristic smell baseline below.
- **Spec:** whether the change faithfully implements its originating issue or specification without missing behavior or scope creep.

The axes MUST run in separate, fresh reviewer contexts so conclusions from one cannot bias the other. Repository standards override the heuristic smell baseline.

## Pin the Fixed Point

Resolve the user-provided commit, branch, tag, or merge-base reference before review. If none was provided, ask for it or infer the target branch from explicit pull-request or merge-request metadata.

Record these commands once:

```bash
git rev-parse <fixed-point>
git diff <fixed-point>...HEAD
git log <fixed-point>..HEAD --oneline
```

The resolved baseline commit MUST remain unchanged across iterative rounds. A missing reference or empty initial diff is a hard stop.

## Find the Specification

Look for the originating specification in this order:

1. Issue or review references in commit messages, such as `#123`, `Closes #45`, or `!67`, using repository-supported issue-tracker tools.
2. A specification path or URL supplied by the user.
3. A matching file under `docs/`, `specs/`, or `.scratch/`.
4. A direct question to the user.

If the user confirms that no specification exists, skip the Spec reviewer and report that only Standards convergence can be established. Do not silently invent requirements.

## Find the Standards

Collect repository documents that govern the changed code, such as `AGENTS.md`, `CONTRIBUTING.md`, `CODING_STANDARDS.md`, language-specific guides, and scoped instruction files.

Skip checks already enforced deterministically by formatter, compiler, linter, or type checker. Those belong in validation rather than judgment review.

## Standards Smell Baseline

Treat every smell below as a judgment heuristic, never as an automatic violation:

- **Mysterious Name:** A name does not reveal what a function, variable, or type does. Prefer a precise domain name; if none fits, re-examine the design.
- **Duplicated Code:** Multiple changed locations implement the same logic shape. Extract the shared behavior when doing so creates a clearer seam.
- **Feature Envy:** A method works mainly with another object's data. Consider moving behavior closer to the data it uses.
- **Data Clumps:** The same fields or parameters repeatedly travel together. Consider introducing a cohesive type.
- **Primitive Obsession:** A primitive stands in for a domain concept with invariants or behavior. Consider a small domain type.
- **Repeated Switches:** The same conditional dispatch recurs for the same variants. Centralize dispatch or use polymorphism where clearer.
- **Shotgun Surgery:** One logical change requires scattered edits. Gather behavior that changes together behind a deeper module.
- **Divergent Change:** One module changes for several unrelated reasons. Separate responsibilities along stable seams.
- **Speculative Generality:** New abstraction or configurability has no current requirement. Remove or inline it until a real need exists.
- **Message Chains:** Callers navigate deep object graphs. Hide traversal behind an intention-revealing operation.
- **Middle Man:** A type or function mostly forwards calls without adding a useful abstraction. Call the real target or deepen the intermediary.
- **Refused Bequest:** A subtype ignores substantial inherited behavior. Prefer composition or a narrower interface.

A documented repository rule always wins over this baseline. A reviewer MUST label smell findings as judgment calls and cite the changed hunk.

## Run Independent Reviewers

Run Standards and Spec reviewers concurrently when a specification exists. Each reviewer receives the pinned diff command, current commit list, and current review-head SHA, but MUST NOT receive findings from previous rounds.

### Standards Reviewer Brief

Provide the standards-source paths and the complete smell baseline above. Require the reviewer to:

- Cite each documented-standard violation by source file and rule.
- Name each possible smell and quote or locate the relevant hunk.
- Distinguish hard documented rules from heuristic judgments.
- Suppress heuristics that conflict with repository guidance.
- Skip issues deterministic tooling already enforces.
- Report no finding when evidence is insufficient.

### Spec Reviewer Brief

Provide the specification path or fetched content. Require the reviewer to:

- Identify missing or partially implemented requirements.
- Identify unrequested behavior or scope creep.
- Identify requirements that appear implemented incorrectly.
- Quote the requirement supporting every finding.
- Report no finding when evidence is insufficient.

Reviewers MUST NOT edit files. Review and repair are separate roles.

## Output Contract

Keep Standards and Spec candidates separate. For every candidate report:

- file and symbol or hunk
- cited rule or requirement
- severity
- evidence
- concise summary

Do not merge or rank one axis against the other. A change can satisfy the specification while violating standards, or satisfy standards while implementing the wrong behavior. The iterative SOP adjudicates candidates, performs repairs, validates them, and starts a fresh independent review round.
