# UltraCode Goal

Run a BMAD Epic autonomously to a machine-checked Definition-of-Done.

`bmad-module-ultracode-goal` is a BMAD module **for Claude Code** — it composes `/goal`, Auto Mode, Auto Memory, and runtime hooks, so the autonomous run executes nowhere else. It delivers a single Epic end to end without a human in the loop — but only behind a hard preflight gate and a deterministic completion gate. It does not replace the BMAD epic toolbox or the Test Architect (TEA); it conducts them. The skill preflights the Epic to a remediated green light, turns acceptance criteria into executable red-phase tests with TEA, drives every in-scope story to a green commit on an isolated Epic branch, and advances only when `gate_eval.py` reads TEA's `gate-decision.json` as PASS — never on the model's own say-so, and never on the `/goal` transcript evaluator alone. The output is a delivered, gate-passed Epic, a run report, and a deferred-work ledger of anything safely parked for later.

## Documentation

### Why

- [Why UltraCode Goal](why-ultracode-goal.md) — the problem (autonomous runs that "look done" aren't), the three enforcement layers, and when not to use it.

### Try

- [Getting Started](getting-started.md) — prerequisites, install, the first-run walkthrough, and the flags table.
- [How It Works](how-it-works.md) — the six stages narrated, the conditions that route between them, and the headless emit shape.
- [Parallel Mode](parallel-mode.md) — the experimental `--parallel` worktree fan-out and its known limits.

### Reference

- [Architecture](architecture.md) — the conductor model, the three enforcement layers in depth, the file layout, and customization resolution.
- [Gate Model](gate-model.md) — how `gate_eval.py` maps TEA's gate status to a verdict, the thresholds, and the fail-closed contract.
- [Health Check](health-check.md) — the terminal self-improvement reflection: what it sends, the privacy model, and how to disable it.
- [Troubleshooting](troubleshooting.md) — real failure modes and their remediations.
- [Stability](_internal/STABILITY.md) — the 0.x public-contract posture: what is covered by SemVer and what is `@internal`.
