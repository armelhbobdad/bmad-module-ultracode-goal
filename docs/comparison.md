---
title: UCG vs bmad-auto
description: An honest, side-by-side comparison of UltraCode Goal and bmad-code-org's bmad-auto orchestrator, including where bmad-auto is the better choice and which to reach for when.
---

Both UltraCode Goal (UCG) and [bmad-auto](https://github.com/bmad-code-org/bmad-auto) automate the BMAD implementation phase without a babysitter. They are siblings, not clones: they make opposite bets on where the control loop lives and how completion is judged. This page compares them honestly, including the places where bmad-auto is the better tool.

Snapshot: UCG v0.4.0 and bmad-auto v0.7.4, both as of 2026-06-28. Both projects are young and moving fast, so treat every line below as a point-in-time reading and verify the current state for yourself (links at the bottom).

## The one difference everything else follows from

bmad-auto puts the control loop in **plain Python, outside the agent**. A deterministic orchestrator picks the next story, spawns a fresh, disposable coding-agent session (over tmux) for each step, watches structured hook events the session writes, and decides retries, gates, and completion in code. No LLM sits in the control loop.

UCG puts the control loop **inside Claude Code**. The run is a Claude Code skill that composes `/goal`, Auto Mode, runtime hooks, and dynamic workflows. The per-story loop is paced by Claude Code's `/goal` evaluator (an LLM), while the binding completion verdict is a deterministic script (`gate_eval.py`) that reads the Test Architect's gate artifact.

The consequence cascades: bmad-auto is a tool you run beside any supported agent; UCG is a capability that lives within one specific agent.

## At a glance

| Dimension | bmad-auto | UltraCode Goal (UCG) |
|---|---|---|
| Runtime | External Python process plus tmux; Linux, macOS, or WSL | A skill inside Claude Code; no external process, no tmux |
| Control loop | Deterministic Python, no LLM in the loop | LLM-paced `/goal` spine with a deterministic completion gate |
| Agent / CLI | claude, codex, gemini, copilot (mix per stage) | Claude Code only |
| Scope | Implementation phase: `ready-for-dev` stories through dev, review, verify, commit | Whole Epic: planning-readiness preflight, ATDD test generation, execute, TEA gate, finalize |
| Completion authority | On-disk artifact checks plus your test and lint commands | TEA quality gate (`gate-decision.json`: P0/P1/overall, NFR, test-review) read by `gate_eval.py` |
| Test strategy | Your `[verify].commands` plus adversarial review hunters | ATDD: acceptance criteria become executable red-phase tests driven to green; TEA traceability |
| Pre-launch gate | `validate` (config, git, tmux, CLI, hooks) | `validate` plus a semantic scan that refuses to launch on an undecided product or architecture decision |
| Observability | Rich Textual TUI: dashboard, attach to live sessions, journal, token totals | Files: `.decision-log.md`, a `run-status.json` heartbeat, a transcript ticker, the `/workflows` view |
| Deferred work | A triage-and-execute **sweep** engine plus a decisions workflow | An append-only ledger surfaced at finalize; no execute engine |
| Escalation | Typed (CRITICAL / PREFERENCE) plus an interactive resolve agent | An escalate verdict and a blocked headless envelope; resume from the decision log |
| Isolation | Opt-in git worktree per story or bundle, merged back locally | Sequential by default; an experimental `--parallel` worktree fan-out |
| Extensibility | A plugin system plus a Unity game-engine plugin | `customize.toml` knobs and planning-shaping fragments |
| Self-improvement | Not shipped | A health check that files deduplicated GitHub issues about its own friction |
| Maturity | First-party (bmad-code-org); v0.7.4; rich docs; CI + test suite | Community module; v0.4.0; docs site; CI + test suite |
| License | MIT | MIT |

## Where bmad-auto is stronger

This is a genuinely strong tool; pretending otherwise would make this page useless.

1. **A deterministic control loop.** Story selection, retry budgets, gates, and completion checks are ordinary Python, so they are debuggable, reproducible, and cost no tokens. UCG's `/goal` pacing is LLM-driven and only its final completion gate is deterministic. If you want zero LLM judgment in the orchestration itself, bmad-auto is the cleaner model.
2. **Agent portability.** It drives claude, codex, gemini, or GitHub Copilot CLI, and can run dev on one model and review on another via per-stage profiles. UCG is deliberately Claude Code only.
3. **Observability and control.** A live Textual TUI gives you a runs dashboard, a sprint tree, the deferred-work ledger, per-story token totals, attach-to-session, and a policy editor. UCG's window into a run is files and the transcript.
4. **A deferred-work engine, not just a ledger.** `bmad-auto sweep` triages the ledger against the real code, bundles cohesive work, executes it, and has a decisions workflow for the human calls. UCG appends to a ledger and surfaces it at the end; acting on it is manual.
5. **Extensibility and reach.** A real plugin system (observe, veto, mutate the cycle) and a Unity game-engine integration. UCG exposes configuration knobs, not a plugin API.
6. **Operational maturity.** Disk reclamation (clean and archive, retention windows, worktree teardown), cost-weighted token budgets that discount cache reads, an adapter-authoring path for new CLIs, and the backing of the bmad-code-org org.

## Where UCG is stronger

1. **Completion gated on formal traceability, not on build-and-review alone.** UCG's completion authority is the Test Architect's gate: a traceability matrix that holds acceptance criteria to hard thresholds (P0 = 100%, P1 >= 90%, overall >= 80%), ANDed in production with an NFR assessment and a test-review score. bmad-auto's gate is strict but differently shaped: your test and lint commands, a non-empty diff, an independent baseline-commit check, the spec marked done, and two adversarial review hunters. What UCG adds is the requirement that every acceptance criterion is demonstrably traced to a passing test at those thresholds, which bmad-auto does not compute.
2. **ATDD-first.** UCG turns each story's acceptance criteria into executable, red-phase (`test.skip`) tests before any code is written, then drives them to green. The acceptance tests are a first-class generated artifact, not a by-product. bmad-auto relies on the dev skill's own implementation plus the test commands you supply.
3. **A planning-readiness gate that can refuse to launch.** UCG's preflight hands a read of the PRD, architecture, and stories to a throwaway subagent that hunts undecided product or architecture decisions, PRD-versus-architecture contradictions, and an undefinable "done". Any such RED stops the run rather than letting an unattended agent guess. bmad-auto's preflight is mechanical (config, git, tmux, CLI, hooks); it assumes the sprint's stories are already ready to build.
4. **No moving parts outside the agent.** UCG is a skill: no external daemon, no tmux, no separate process to attach to. For a Claude Code user that is a smaller operational surface, and it is also exactly why UCG cannot run anywhere else.
5. **A self-improvement loop.** UCG's finalize step can file deduplicated GitHub issues about friction in its own workflow, so the tool reports its own rough edges.

## What they share

- A deterministic completion authority the model cannot talk its way past: bmad-auto's on-disk artifact and command checks plus its baseline-commit "lie detector"; UCG's TEA gate read.
- Fresh-context review separated from implementation, to kill self-review anchoring bias.
- Adversarial review passes, bounded so they cannot oscillate forever.
- Optional git worktree isolation.
- Resumable runs and per-story token budgets.
- `sprint-status.yaml` as planning truth, owned by the BMAD skills; both build on BMAD-METHOD.

## Which to reach for

Choose **bmad-auto** if you use codex, gemini, or GitHub Copilot CLI (or want to mix models per stage), you want a code-only orchestrator you can step through and debug, you want a live dashboard and attach-to-session control, you have a backlog of deferred work to triage and sweep, you need plugin extensibility or game-engine support, or you want the tool published under the bmad-code-org org.

Choose **UCG** if you are on Claude Code, you want completion judged by the Test Architect's traceability thresholds (every acceptance criterion traced to a passing test) rather than by build-and-review checks, you want acceptance criteria compiled into executable tests up front, you want a run that refuses to start while a product or architecture decision is still undecided, or you want a single skill with no external process to operate.

They are not mutually exclusive. Both read the same `sprint-status.yaml` and BMAD artifacts, so you can plan and gate an Epic UCG's way and grind a deferred-work backlog bmad-auto's way in the same project.

## Verify this yourself

Both tools change weekly, so re-check before you rely on anything above:

- bmad-auto: its [README](https://github.com/bmad-code-org/bmad-auto), [docs/FEATURES.md](https://github.com/bmad-code-org/bmad-auto/blob/main/docs/FEATURES.md), and [docs/ROADMAP.md](https://github.com/bmad-code-org/bmad-auto/blob/main/docs/ROADMAP.md).
- UCG: [How It Works](how-it-works.md) and the [Gate Model](gate-model.md).

This snapshot was taken on 2026-06-28 against bmad-auto v0.7.4 and UCG v0.4.0.
