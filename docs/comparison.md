---
title: UCG vs bmad-loop
description: An honest, side-by-side comparison of UltraCode Goal and bmad-code-org's bmad-loop orchestrator (formerly bmad-auto), including where bmad-loop is the better choice and which to reach for when.
---

Both UltraCode Goal (UCG) and [bmad-loop](https://github.com/bmad-code-org/bmad-loop) (formerly bmad-auto; renamed at v0.8.0) automate the BMAD implementation phase without a babysitter. They are siblings, not clones: they make opposite bets on where the control loop lives and how completion is judged. This page compares them honestly, including the places where bmad-loop is the better tool.

Snapshot: UCG v0.5.1 and bmad-loop v0.8.1, both as of 2026-07-12, both released versions. Both projects are young and moving fast. bmad-loop's main branch already carries substantial unreleased work, including a stories.yaml planning mode with per-story human checkpoints, escalation recovery via patch restore, selectable multiplexer backends, an additional adversarial review pass, and integrity fixes to its verify gate. Treat every line below as a point-in-time reading and verify the current state for yourself (links at the bottom).

## The one difference everything else follows from

bmad-loop puts the control loop in **plain Python, outside the agent**. A deterministic orchestrator picks the next story, spawns a fresh, disposable coding-agent session (over tmux) for each step, watches structured hook events the session writes, and decides retries, gates, and completion in code. No LLM sits in the control loop.

UCG puts the control loop **inside Claude Code**. The run is a Claude Code skill that composes `/goal`, Auto Mode, runtime hooks, and dynamic workflows. The per-story loop is paced by Claude Code's `/goal` evaluator (an LLM), while the binding completion verdict is a deterministic script (`gate_eval.py`) that reads the Test Architect's (TEA) gate artifact.

The consequence cascades: bmad-loop is a tool you run beside any supported agent; UCG is a capability that lives within one specific agent.

## At a glance

| Dimension | bmad-loop | UltraCode Goal (UCG) |
|---|---|---|
| Runtime | External Python process plus tmux; Linux, macOS, or WSL (native Windows is planned) | A skill inside Claude Code; no external process, no tmux; runs anywhere Claude Code runs |
| Control loop | Deterministic Python, no LLM in the loop | LLM-paced `/goal` spine with a deterministic completion gate |
| Agent / CLI | claude, codex, gemini, copilot (mix per stage) | Claude Code only |
| Scope | Implementation phase: `backlog` and `ready-for-dev` stories through dev, review, verify, commit | Whole Epic: planning-readiness preflight, ATDD (acceptance-test-driven development) test generation, execute, TEA gate, finalize |
| Completion authority | Checks on the spec and result artifacts, a proof-of-work diff, and your test and lint commands; opt-in TEA gate steps via a bundled plugin (advisory by default) | TEA quality gate: `gate-decision.json` (P0/P1/overall), combined in the default profile with NFR and test-review artifacts, read fail-closed by `gate_eval.py` |
| Test strategy | Your `[verify].commands` plus adversarial review hunters; opt-in TEA test-design and ATDD workflows via the bundled plugin | ATDD: acceptance criteria become executable red-phase tests driven to green; TEA traceability |
| Pre-launch gate | `validate` (config, sprint-status, git, multiplexer, CLI, hooks, base skills) | A mechanical preflight script plus a readiness check and a semantic scan that refuse to launch on an undecided product or architecture decision |
| Observability | A live terminal dashboard (built with Textual): runs table, attach to live sessions, journal, cost-weighted token totals | Files: `.decision-log.md`, a `run-status.json` heartbeat, a transcript ticker, the `/workflows` view |
| Deferred work | A triage-and-execute **sweep** engine plus a decisions workflow | An append-only ledger surfaced at finalize; no execute engine |
| Escalation | Typed (CRITICAL / PREFERENCE) plus an interactive resolve agent | An escalate verdict and a machine-readable blocked report (the headless envelope); resume from the decision log |
| Isolation | In place by default; opt-in git worktree per story or bundle, merged back locally | None by default (stories run sequentially in one session); an experimental `--parallel` mode fans stories out into git worktrees |
| Extensibility | A plugin system (observe, veto, mutate) with bundled TEA and Unity plugins | `customize.toml` knobs and planning-shaping fragments |
| Self-improvement | Not shipped | A health check that files deduplicated GitHub issues about its own friction |
| Maturity | First-party (bmad-code-org); v0.8.1; rich docs; CI + test suite | Community module; v0.5.1; docs site; CI + test suite |
| License | MIT | MIT |

## Where bmad-loop is stronger

This is a genuinely strong tool; pretending otherwise would make this page useless.

1. **A deterministic control loop.** Story selection, retry budgets, gates, and completion checks are ordinary Python, so they are debuggable, reproducible, and cost no tokens. UCG's `/goal` pacing is LLM-driven; its deterministic pieces (the per-story and epic-level gate reads, the preflight scripts, the commit-guard and budget hooks) bound the loop rather than run it. If you want zero LLM judgment in the orchestration itself, bmad-loop is the cleaner model.
2. **Agent portability.** It drives claude, codex, gemini, or GitHub Copilot CLI, and can run dev on one model and review on another via per-stage profiles. UCG is deliberately Claude Code only.
3. **Observability and control.** A live terminal UI (built with Textual) gives you a runs dashboard, a sprint tree, the deferred-work ledger, per-story token totals, attach-to-session, and a policy editor. UCG's window into a run is files and the transcript.
4. **A deferred-work engine, not just a ledger.** `bmad-loop sweep` triages the ledger against the real code, bundles cohesive work, executes it, and has a decisions workflow for the human calls. UCG appends to a ledger and surfaces it at the end; acting on it is manual.
5. **Extensibility and reach.** It has a real plugin system (observe, veto, mutate the cycle) with bundled plugins: a TEA plugin that can add Test Architect workflows to its pipeline, and a Unity game-engine integration. UCG exposes configuration knobs, not a plugin API.
6. **Operational maturity.** It ships disk reclamation (clean and archive, retention windows, worktree teardown), cost-weighted token budgets that discount cache reads, and an adapter-authoring path for new CLIs, and it carries the backing of the bmad-code-org org.

## Where UCG is stronger

1. **The TEA gate is the default, binding completion authority, not an opt-in layer.** UCG's completion authority is the Test Architect's gate: a traceability matrix that holds acceptance criteria to hard thresholds (P0 coverage at 100%, P1 at 90% or above, overall at 80% or above). UCG's default profile combines that verdict with an NFR (non-functional requirements) assessment and a test-review score, and `gate_eval.py` reads the result fail-closed: a missing or unreadable signal downgrades the verdict, never upgrades it. Since v0.5.0 the default sequential path also re-runs the full test, lint, and build suite on each story's committed HEAD before advancing, so a story that is green pre-commit but red once its new files are tracked cannot slip through to the gate.

   bmad-loop can reach similar territory, but differently. Its default gate is checks on the spec and result artifacts, a proof-of-work diff (the commit must contain real changes since the story's baseline), and your test and lint commands; its bundled TEA plugin can add trace, NFR, and test-review steps before every commit. That plugin is opt-in, its gate steps ship advisory (non-blocking), and they fail open when an artifact is missing or unparseable. One point-in-time caveat on that side: at v0.8.1, bmad-loop's independent baseline-commit cross-check could not actually fire, because it read a spec key the dev skill does not write; a fix has already landed on main, and this is exactly the kind of drift the snapshot warning above is about. If you want acceptance-criterion-to-test traceability enforced by default, fail-closed, with nothing to configure, that is UCG's defining bet.
2. **ATDD-first.** UCG turns each story's acceptance criteria into executable acceptance tests (scaffolded as red-phase `test.skip` placeholders) before any code is written, then un-skips them and drives them to green. The acceptance tests are a first-class generated artifact, not a by-product. One scope note: TEA's ATDD generator targets web and E2E stacks; on a non-web stack UCG's preflight steers the run to `--light`, where the story's acceptance criteria (not generated tests) are the trace oracle, or you author the acceptance tests in the stack's own harness. bmad-loop's default pipeline relies on whatever tests the dev skill writes while implementing, plus the test commands you supply; TEA test generation exists there only as an opt-in plugin step that runs after dev, not as the default path.
3. **A planning-readiness gate that can refuse to launch.** UCG's preflight hands the PRD, the architecture, and the stories to a throwaway subagent that hunts for undecided product or architecture decisions, contradictions between the PRD and the architecture, and any story whose "done" cannot be pinned down. The scan grades what it finds, and any RED verdict stops the run rather than letting an unattended agent guess. That scan is itself LLM judgment, the very thing bmad-loop keeps out of its loop; the difference is that it can only block a launch, never pass one. bmad-loop's preflight is mechanical (config, sprint-status, git, multiplexer, CLI, hooks, skill presence); it assumes the sprint's stories are already ready to build.
4. **No moving parts outside the agent.** UCG is a skill: no external daemon, no tmux, no separate process to attach to. For a Claude Code user that is a smaller operational surface, and it is also exactly why UCG cannot run anywhere else.
5. **A self-improvement loop.** UCG's finalize step can file deduplicated GitHub issues about friction in its own workflow, so the tool reports its own rough edges.

## What they share

- A deterministic completion authority the model cannot talk its way past: bmad-loop's artifact, diff, and command checks; UCG's TEA gate read (on UCG's non-web `--light` path the trace artifacts are agent-authored under strict honesty rules, so the guarantee there is procedural rather than mechanical).
- Fresh-context review separated from implementation, to kill self-review anchoring bias.
- Adversarial review passes, bounded so they cannot oscillate forever.
- Optional git worktree isolation.
- Resumable runs with a per-story budget: bmad-loop's is a cost-weighted token ceiling that discounts cache reads; UCG's is a turn cap, encoded in the `/goal` condition and enforced at the gate (a re-loop that would exceed the budget escalates instead).
- `sprint-status.yaml` as planning truth, owned by the BMAD skills; both build on BMAD-METHOD.

## Which to reach for

Choose **bmad-loop** if you use codex, gemini, or GitHub Copilot CLI (or want to mix models per stage), you want a code-only orchestrator you can step through and debug, you want a live dashboard and attach-to-session control, you have a backlog of deferred work to triage and sweep, you need plugin extensibility or game-engine support, or you prefer a first-party tool maintained under the bmad-code-org org.

Choose **UCG** if you are on Claude Code and any of these fit: you want the Test Architect's gate as the default, binding, fail-closed completion authority (every P0 criterion traced to a passing test, with P1 at 90% or above and overall at 80% or above) rather than an opt-in layer; you want acceptance criteria compiled into executable tests up front; you want a run that refuses to start while a product or architecture decision is still undecided; or you want a single skill with no external process to operate.

They are not mutually exclusive. Both read the same `sprint-status.yaml` and BMAD artifacts, so you can plan and gate an Epic UCG's way and grind a deferred-work backlog bmad-loop's way in the same project.

## Verify this yourself

Both tools change weekly, so re-check before you rely on anything above:

- bmad-loop: its [README](https://github.com/bmad-code-org/bmad-loop), [docs/FEATURES.md](https://github.com/bmad-code-org/bmad-loop/blob/main/docs/FEATURES.md), and [docs/ROADMAP.md](https://github.com/bmad-code-org/bmad-loop/blob/main/docs/ROADMAP.md).
- UCG: [How It Works](how-it-works.md) and the [Gate Model](gate-model.md).

This snapshot was re-cut on 2026-07-12 against bmad-loop v0.8.1 (released 2026-07-05) and UCG v0.5.1; the previous snapshot (2026-06-28, bmad-auto v0.7.4 and UCG v0.4.0) predates the rename.
