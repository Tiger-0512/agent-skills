# Agent Skills by Tiger-0512

Reusable skills for software engineering agents.

## Iterative Code Review

`iterative-code-review` repeatedly runs independent Standards and Spec reviews, adjudicates every candidate finding, repairs valid in-scope findings, validates the change, and starts a fresh review round. It succeeds only when both axes have no valid findings and final validation passes.

### Features

- Pins one immutable review baseline across all rounds
- Keeps Standards and Spec reviews independent
- Separates candidate findings from adjudicated findings
- Requires targeted validation after every repair round
- Detects repeated findings, no-progress cycles, and maximum-round exhaustion
- Does not commit, push, publish comments, approve, or merge without explicit authorization
- Includes its review protocol, so no prerequisite skill or paid Pack is required

## Install

```bash
npx skills@latest add Tiger-0512/agent-skills --skill iterative-code-review
```

## Usage

Invoke the installed skill by name or ask your agent to use it:

```text
Use iterative-code-review to review and fix this branch until no valid findings remain.
Fixed point: origin/main
```

Default safety bounds are five completed review rounds and two consecutive no-reduction transitions. The skill stops without claiming convergence if a bound fires, validation remains broken, a finding needs a user decision, or the repository changes unexpectedly.

## Bundled review protocol

The two-axis review protocol is adapted from [Matt Pocock's `code-review` skill](https://www.skills.sh/mattpocock/skills/code-review) at upstream commit [`959a8e9f1edc3adbe2f7e3054bb6fbefa6696260`](https://github.com/mattpocock/skills/commit/959a8e9f1edc3adbe2f7e3054bb6fbefa6696260).

The adapted protocol and required attribution are shipped inside `iterative-code-review`, so users do not need to install or configure another skill. The bundled upstream-derived material remains available under Matt Pocock's MIT License; see `skills/iterative-code-review/LICENSES/mattpocock-skills-MIT.txt`.

## Validation

Run the deterministic state-checker tests:

```bash
python3 -m unittest discover \
  -s skills/iterative-code-review/tests -v

python3 -m py_compile \
  skills/iterative-code-review/scripts/review-loop-state.py
```

The implementation uses only the Python standard library.

## Attribution

This repository's two-axis review protocol is adapted from Matt Pocock's [`code-review`](https://github.com/mattpocock/skills/tree/main/skills/engineering/code-review) skill, distributed under the [MIT License](https://github.com/mattpocock/skills/blob/main/LICENSE). The iterative orchestration, adjudication model, convergence state checker, and safety stops are original additions in this repository.

## License

Original content in this repository is licensed under the MIT License. See [LICENSE](LICENSE). Upstream-derived material retains its original notice in `skills/iterative-code-review/LICENSES/mattpocock-skills-MIT.txt`.
