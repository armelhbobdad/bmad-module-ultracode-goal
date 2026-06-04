# Security Policy

## Supported Versions

UCG is pre-1.0. Security fixes land on the latest `0.x` release only. There is no long-term support branch yet; upgrade to the newest published version before reporting a vulnerability.

| Version | Supported          |
| ------- | ------------------ |
| latest `0.x` | yes           |
| older `0.x`  | no — upgrade first |

## Reporting a Vulnerability

**Do not open a public issue for a security problem.** Report it privately through GitHub's [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability) on this repository — open a draft Security Advisory from the **Security** tab.

UCG is maintained in spare hours. Expect an acknowledgement within a few days, not within hours. We'll confirm the report, agree on a disclosure timeline, and credit you in the advisory unless you ask otherwise.

## Hook Security

UCG installs Claude Code hooks at preflight so that two invariants are enforced by the runtime rather than left to the model's memory (which is context, not enforcement). This section is the full account of what that means.

**What UCG installs:**

- A **`PreToolUse` guard** that validates story markers and git state before a tool runs — it denies a `git commit`/`git push` on a protected branch, and denies a `git commit` until a "tests-ran" marker exists for the current story.
- A **`Stop` hook** that tracks the per-story turn and token budget and surfaces an escalation when the run overruns `max_turns_per_story` / `story_token_budget`. This hook records the overrun and lets the stop proceed; it never blocks.

**Where they live:** in your **machine-local, gitignored `.claude/settings.local.json`**, auto-merged at preflight. They are never written to a committed file and never travel with the repo.

**What they execute:** the hooks run, via `uv run`, two zero-dependency PEP 723 Python scripts shipped inside the skill:

- `skills/ultracode-goal/scripts/hooks/guard_pretooluse.py`
- `skills/ultracode-goal/scripts/hooks/budget_stop.py`

Both declare `dependencies = []`. They read a JSON event on stdin, inspect git/local state, and emit a JSON decision — no network calls, no third-party packages.

**How to inspect them:** read the two scripts. They are plain Python with a documented hook contract in their module docstrings. Confirm for yourself that the only thing the guard does is deny commits on protected branches and before tests, and the only thing the budget hook does is count turns and tokens.

**How to remove them:** delete the corresponding `PreToolUse` and `Stop` hook entries from `.claude/settings.local.json`. Because the file is machine-local and gitignored, nothing else in your repo depends on them.

## Secrets

The UCG module never requires you to provide secrets. It does not read, store, or transmit credentials as part of its own operation. In a **headless** run, a secret the run cannot resolve is treated as a **red blocker** that halts the run — never as an interactive prompt and never as a value the conductor invents to keep moving.
