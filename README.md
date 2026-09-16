# Agent Skills by Tiger-0512

Reusable skills for software engineering agents.

## Standards-Spec Review Loop

`standards-spec-review-loop` repeatedly runs independent Standards and Spec reviews, adjudicates every candidate finding, repairs valid in-scope findings, validates the change, and starts a fresh review round. It succeeds only when both axes have no valid findings and final validation passes.

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
npx skills@latest add Tiger-0512/agent-skills --skill standards-spec-review-loop
```

This skill was previously published as `iterative-code-review`. The repository now exposes only `standards-spec-review-loop`; existing users should install the new slug.

## Usage

Invoke the installed skill by name or ask your agent to use it:

```text
Use standards-spec-review-loop to review and fix this branch until no valid findings remain.
Fixed point: origin/main
```

Default safety bounds are five completed review rounds and two consecutive no-reduction transitions. The skill stops without claiming convergence if a bound fires, validation remains broken, a finding needs a user decision, or the repository changes unexpectedly.

## Bundled review protocol

The two-axis review protocol is adapted from [Matt Pocock's `code-review` skill](https://www.skills.sh/mattpocock/skills/code-review) at the source file's upstream commit [`5c89081d4bbeb3d039a42093653f90bb698d780e`](https://github.com/mattpocock/skills/commit/5c89081d4bbeb3d039a42093653f90bb698d780e).

The adapted protocol and required attribution are shipped inside `standards-spec-review-loop`, so users do not need to install or configure another skill. The bundled upstream-derived material remains available under Matt Pocock's MIT License; see `skills/standards-spec-review-loop/LICENSES/mattpocock-skills-MIT.txt`.

## Upstream updates

`.github/workflows/update-upstream-code-review.yml` checks the upstream source after changes reach `main`, once a week, and on manual dispatch. When it detects a newer source commit, it updates the pinned snapshot and manifest on an automation branch and opens a **Draft PR**.

The generated PR deliberately sets `adaptation.status` to `pending`. A human must review the upstream comparison, reconcile relevant changes into the active protocol, and run:

```bash
python3 scripts/update-upstream-code-review.py mark-reviewed \
  --manifest skills/standards-spec-review-loop/upstream-code-review.json
```

`Validate` rejects a pending adaptation, so the update cannot reach a merge-ready state without this review. The workflow never enables auto-merge.

For Draft PR creation, repository Actions settings must allow read/write workflow permissions and GitHub Actions to create pull requests.

## Validation

Run the deterministic state-checker and upstream-maintenance tests:

```bash
python3 scripts/update-upstream-code-review.py validate \
  --manifest skills/standards-spec-review-loop/upstream-code-review.json

python3 -m unittest discover -s tests -v

python3 -m unittest discover \
  -s skills/standards-spec-review-loop/tests -v

python3 -m py_compile \
  scripts/update-upstream-code-review.py \
  skills/standards-spec-review-loop/scripts/review-loop-state.py
```

The implementation uses only the Python standard library.

## Attribution

This repository's two-axis review protocol is adapted from Matt Pocock's [`code-review`](https://github.com/mattpocock/skills/tree/main/skills/engineering/code-review) skill, distributed under the [MIT License](https://github.com/mattpocock/skills/blob/main/LICENSE). The iterative orchestration, adjudication model, convergence state checker, and safety stops are original additions in this repository.

## License

Original content in this repository is licensed under the MIT License. See [LICENSE](LICENSE). Upstream-derived material retains its original notice in `skills/standards-spec-review-loop/LICENSES/mattpocock-skills-MIT.txt`.
