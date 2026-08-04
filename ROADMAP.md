# Roadmap

Future work planned for UltraCode Goal. Items here are **directional, not a promise**; they ship when their trigger conditions are met and the evidence is in hand, not on a timeline. Each item below traces to a known, documented gap in how the module behaves today, not to a wishlist.

---

## Parallel execution: retired, not promoted

The experimental `--parallel` worktree fan-out was retired rather than promoted: the empirical validation this item used to plan never arrived, and the mode's own limit list (no mid-run input, shared Auto Memory, no heartbeat, no post-commit re-verify) never closed. The flag is still accepted and ignored for compatibility. Any future parallel execution would be a fresh design measured against the sequential spine's guarantees, not a revival of the removed workflow.

## Hook-protocol behavior across Claude Code versions

The `PreToolUse` guard and `Stop` hook implement a documented hook contract, with a defensive exit-code-2 fallback for older clients that honor exit codes but ignore the JSON decision shape. We want explicit verification of the hook protocol's behavior **across the range of installed Claude Code versions**, so the invariant enforcement is known-good wherever UCG is installed, not just on the version it was authored against.

## `/goal` + custom `Stop`-hook interplay

A `Stop` hook fires only when Claude is *already* trying to stop; it **cannot interrupt a `/goal` condition mid-turn**. Today the in-`/goal`-condition turn cap is the primary runaway guard, and the budget `Stop` hook is a defensive third layer that records overruns and warns. Tightening this interplay, so the budget ceiling is less advisory at the hook layer without fighting `/goal`'s own loop, is open work that depends on what the primitives expose.

## Transient-failure retry before a gate `escalate`

When the quality gate cannot be read (a flaky CI run or a transient network failure leaves the gate-decision file unavailable), the gate evaluates to `NOT_EVALUATED` and the story routes straight to `escalate`, a hard stop for the run. That conservative default is correct (a gate that can't be read must never be treated as a pass), but it does not distinguish a *transient, retryable* cause from a genuine "no gate was produced" one. A flake is a wall-clock problem (wait a short interval, re-read, and it clears), not a problem more turns can solve, so the per-story turn loop offers no help.

The planned fix is a **bounded, classified retry tier before `escalate`**: mark an unreadable-gate result as retryable vs. genuinely absent, and on a retryable cause wait a fixed backoff and re-run only the trace + gate evaluation (no new code, no commit) a small, configurable number of times before falling through to today's `escalate` unchanged. This stays deterministic, works on every provider, adds no second stop-authority, and is bounded by the existing per-story budget.

It ships on evidence, not speculation. The trigger is a **first real observed transient `escalate`** in a run, and because the gate already records the full verdict and its reasons on every escalate, that first occurrence is self-diagnosing, so the retry tier is built against a real reproduction rather than an imagined one. Deliberately *not* implemented ahead of that signal.

## Wall-clock budget envelope

The budget guardrail today is **turn count** per story (`max_turns_per_story`); the older `story_token_budget` key is accepted but no-op. There is no per-turn timing signal available, so UCG cannot currently enforce a wall-clock envelope ("stop this story after N minutes"). Adding a time-based budget waits on a timing signal the run can actually read.

## Health-check autosubmit telemetry review

The Finalize health-check loop files fingerprint-deduped issues (with approval; headless runs queue locally). Once UCG has real-world runs behind it, we want to **review the autosubmit telemetry** (dedup hit rate, false-positive findings, the friction-vs-bug-vs-gap mix) and tune the loop's submit/queue thresholds from evidence rather than from the initial defaults.
