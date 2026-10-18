# Roadmap

Future work planned for UltraCode Goal. Items here are **directional, not a promise**; they ship when their trigger conditions are met and the evidence is in hand, not on a timeline. Each item below traces to a known, documented gap in how the module behaves today, not to a wishlist.

---

## Story creation and implementation on `bmad-build`

UCG delegates story creation to `ucg-create-story` and implementation to `ucg-dev-story`, its own copies of BMAD Method's `bmad-create-story` and `bmad-dev-story`. BMAD 6.11 deprecated those two in favour of `bmad-build`, 6.12 made them opt-in shims and v7 removes them, so UCG ships the workflows itself and a run needs no shim. The cost is two workflows UCG now maintains while upstream has frozen them. Moving the delegation onto `bmad-build` remains the direction, and it is a contract change, not a rename:

- `bmad-build` writes `spec-<slug>.md` with a frontmatter status. Its full route writes unnumbered Given/When/Then criteria, and its oneshot route for small changes writes no acceptance criteria at all. The formalize check, by contrast, finds story files by their story-key name and parses numbered acceptance criteria, which Execute also cites by number.
- On its full route, `bmad-build` stops for plan approval unless it is handed a spec already at `ready-for-dev`, `in-progress` or `in-review` (a `done` spec is read as context and planning starts over). It takes the lighter oneshot route only when the change has no intent gaps, nothing irreversible and a small footprint; that route skips plan approval but can still stop for a human, when a review finding needs a fix that is not simple, when review subagents cannot be launched, or when implementation hits a replan trigger that sends it back to the plan checkpoint. Both routes commit inside the skill, where UCG commits at green behind its PreToolUse guard. `bmad-build-auto` is BMAD's unattended variant and carries the same commit question.
- `bmad-build-auto` also requires a clean working tree when it finalizes (and when it starts on a fresh dispatch), while Define-Done leaves every in-scope story's red-phase tests uncommitted until that story goes green. A `done` spec gets only a review pass, so the gate's failing reasons have no way into implementation unless UCG rewrites the spec's status, and a decomposed child would need a spec file of its own, which the decomposition conventions forbid.
- `bmad-build` first ships in BMAD Method 6.11, so the move sets a BMAD minimum and ends support for 6.10 and earlier.

It ships as a major release, after a design pass and a validating run on a real Epic.

## Parallel execution: retired, not promoted

The experimental `--parallel` worktree fan-out was retired rather than promoted: the empirical validation this item used to plan never arrived, and the mode's own limit list (no mid-run input, shared Auto Memory, no heartbeat, no post-commit re-verify) never closed. The flag is still accepted and ignored for compatibility. Any future parallel execution would be a fresh design measured against the sequential spine's guarantees, not a revival of the removed workflow.

## Hook-protocol behavior across Claude Code versions

The `PreToolUse` guard and `Stop` hook implement a documented hook contract, with a defensive exit-code-2 fallback for older clients that honor exit codes but ignore the JSON decision shape. We want explicit verification of the hook protocol's behavior **across the range of installed Claude Code versions**, so the invariant enforcement is known-good wherever UCG is installed, not just on the version it was authored against.

## `/goal` + custom `Stop`-hook interplay

A `Stop` hook fires only when Claude is *already* trying to stop; it **cannot interrupt a `/goal` condition mid-turn**. Today the runaway guard is the conductor reading the budget hook's turn count before each story and each re-loop, a count that advances once per response and so cannot see re-loops inside one response; the in-`/goal`-condition turn cap binds only an operator's own `/goal`, since the conductor cannot start one, and the budget `Stop` hook itself records overruns and warns. Tightening this interplay, so the budget ceiling is less advisory at the hook layer without fighting `/goal`'s own loop, is open work that depends on what the primitives expose.

## Transient-failure retry before a gate `escalate`

When the quality gate cannot be read (a flaky CI run or a transient network failure leaves the gate-decision file unavailable), the gate evaluates to `NOT_EVALUATED` and the story routes straight to `escalate`, a hard stop for the run. That conservative default is correct (a gate that can't be read must never be treated as a pass), but it does not distinguish a *transient, retryable* cause from a genuine "no gate was produced" one. A flake is a wall-clock problem (wait a short interval, re-read, and it clears), not a problem more turns can solve, so the per-story turn loop offers no help.

The planned fix is a **bounded, classified retry tier before `escalate`**: mark an unreadable-gate result as retryable vs. genuinely absent, and on a retryable cause wait a fixed backoff and re-run only the trace + gate evaluation (no new code, no commit) a small, configurable number of times before falling through to today's `escalate` unchanged. This stays deterministic, works on every provider, adds no second stop-authority, and is bounded by the existing per-story budget.

It ships on evidence, not speculation. The trigger is a **first real observed transient `escalate`** in a run, and because the gate already records the full verdict and its reasons on every escalate, that first occurrence is self-diagnosing, so the retry tier is built against a real reproduction rather than an imagined one. Deliberately *not* implemented ahead of that signal.

## Wall-clock budget envelope

The budget guardrail today is **turn count** per story (`max_turns_per_story`); the older `story_token_budget` key is accepted but no-op. There is no per-turn timing signal available, so outside `drive_epic.py`'s per-spawn `--session-timeout` UCG cannot currently enforce a wall-clock envelope ("stop this story after N minutes"). Adding a time-based budget waits on a timing signal the run can actually read.

## Health-check autosubmit telemetry review

The Finalize health-check loop files fingerprint-deduped issues (with approval; headless runs queue locally). Once UCG has real-world runs behind it, we want to **review the autosubmit telemetry** (dedup hit rate, false-positive findings, the friction-vs-bug-vs-gap mix) and tune the loop's submit/queue thresholds from evidence rather than from the initial defaults.
