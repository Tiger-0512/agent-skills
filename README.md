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

## Prerequisite

This skill composes [Matt Pocock's `code-review` skill](https://www.skills.sh/mattpocock/skills/code-review). The upstream skill is not bundled in this repository.

Install and configure the prerequisite first:

```bash
npx skills@latest add mattpocock/skills --skill code-review
```

Then run `/setup-matt-pocock-skills` once in each repository where you want issue-tracker and specification discovery.

## Install

After installing the prerequisite:

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

## One-command installation with a skills.sh Pack

After this repository is public and `iterative-code-review` has appeared on skills.sh:

1. Open [Create pack](https://skills.sh/packs/create) and sign in with Vercel.
2. Add [Matt Pocock's `code-review`](https://www.skills.sh/mattpocock/skills/code-review).
3. Add `Tiger-0512/agent-skills@iterative-code-review`.
4. Create the pack and add its generated install command to this README.

Pack users will install both skills with one command:

```bash
npx skills add https://skills.sh/p/<pack-id>
```

Packs are unlisted rather than access-controlled. Do not add secrets or credentials.

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

This repository's `iterative-code-review` orchestration is designed to compose Matt Pocock's independently distributed [`code-review`](https://github.com/mattpocock/skills/tree/main/skills/engineering/code-review) skill. No upstream files are bundled here. Matt Pocock's repository is distributed under the [MIT License](https://github.com/mattpocock/skills/blob/main/LICENSE).

## License

The original content in this repository is licensed under the MIT License. See [LICENSE](LICENSE).
