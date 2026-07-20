# Security Policy

## Supported Versions

UCG is pre-1.0. Security fixes land on the latest `0.x` release only. There is no long-term support branch yet; upgrade to the newest published version before reporting a vulnerability.

| Version | Supported          |
| ------- | ------------------ |
| latest `0.x` | yes           |
| older `0.x`  | no, upgrade first |

## Reporting a Vulnerability

**Do not open a public issue for a security problem.** Report it privately through GitHub's [private vulnerability reporting](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/report-privately) on this repository: open a draft Security Advisory from the **Security** tab.

UCG is maintained in spare hours. Expect an acknowledgement within a few days, not within hours. We'll confirm the report, agree on a disclosure timeline, and credit you in the advisory unless you ask otherwise.

## Hook Security

UCG installs Claude Code hooks at preflight so that a set of invariants is enforced by the runtime rather than left to the model's memory (which is context, not enforcement). This section is the full account of what that means.

**What UCG installs:**

- A **`PreToolUse` guard** that validates story markers and git state before a tool runs. It enforces six invariants:
  1. denies a `git commit`/`git push` on a protected branch;
  2. denies a `git commit` until a "tests-ran" marker exists for the current story;
  3. denies a `git commit` unless that marker's `baseline=<sha>` matches the SHA the story recorded at start (so a marker replayed from an earlier code state is rejected);
  4. denies a `git commit` while the staged index is empty, or while the staged-index probe cannot answer;
  5. when the guard is armed with `ULTRACODE_TEST_ARTIFACTS`, denies a `git commit` while the staged content of any acceptance-test file the story's atdd-checklist enumerates still contains `test.skip(`;
  6. while a UCG run is active, denies any claude-mem MCP call or filesystem reach into `.claude-mem` unless the Cross-Session Recall latch is green. Outside a run, your own claude-mem usage is never touched.

  Read the failure behavior before you rely on any of these. Invariants 2, 3, 4, and 6 fail **closed**: an unreadable marker, an unanswerable staged-index probe, or a non-green latch denies rather than waving the call through. The other two make no decision when their input is unavailable. Invariant 1 fails **open**: if `git rev-parse` cannot report a branch (git missing, or the 10s timeout), there is no branch to match against the protected list and the command proceeds. Invariant 5 is simply out of scope when `ULTRACODE_TEST_ARTIFACTS` is unset, emitting an advisory note and never a deny, so that hooks armed by a run predating the un-skip proof do not brick commits over a checklist that run never wrote; within scope it fails closed.
- A **`Stop` hook** that tracks the per-story turn budget and surfaces an escalation when the run overruns `max_turns_per_story`. This hook records the overrun and lets the stop proceed; it never blocks.

**Where they live:** in your **machine-local, gitignored `.claude/settings.local.json`**, auto-merged at preflight. They are never written to a committed file and never travel with the repo.

**What they execute:** the hooks run, via `uv run`, two zero-dependency PEP 723 Python scripts shipped inside the skill:

- `skills/ultracode-goal/scripts/hooks/guard_pretooluse.py`
- `skills/ultracode-goal/scripts/hooks/budget_stop.py`

Both declare `dependencies = []`. They read a JSON event on stdin, inspect git/local state, and emit a JSON decision: no network calls, no third-party packages.

**How to inspect them:** read the two scripts. They are plain Python with a documented hook contract in their module docstrings. The guard's docstring enumerates the six invariants above; confirm for yourself that it only ever denies a tool call and never mutates your repo, and that the only thing the budget hook does is count turns.

**How to remove them:** delete the corresponding `PreToolUse` and `Stop` hook entries from `.claude/settings.local.json`. Because the file is machine-local and gitignored, nothing else in your repo depends on them.

## Secrets

The UCG module never requires you to provide secrets. It does not read, store, or transmit credentials as part of its own operation. In a **headless** run, a secret the run cannot resolve is treated as a **red blocker** that halts the run, never as an interactive prompt and never as a value the conductor invents to keep moving.
