<div align="center">

<img src="docs/assets/ucg-logo.svg" alt="UltraCode Goal — six stage nodes orbiting a deterministic gate whose verdict reads PASS" width="190"/>

# UltraCode Goal (UCG)

**Run a BMAD Epic autonomously to a machine-checked Definition-of-Done.**

[![Requires Claude Code](https://img.shields.io/badge/requires-Claude%20Code-D97757?logo=claude&logoColor=white)](https://www.anthropic.com/claude-code)
[![Quality & Validation](https://github.com/armelhbobdad/bmad-module-ultracode-goal/actions/workflows/quality.yaml/badge.svg)](https://github.com/armelhbobdad/bmad-module-ultracode-goal/actions/workflows/quality.yaml)
[![npm](https://img.shields.io/npm/v/bmad-module-ultracode-goal)](https://www.npmjs.com/package/bmad-module-ultracode-goal)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![BMAD Module](https://img.shields.io/badge/BMAD-module-blue)](https://github.com/bmad-code-org/BMAD-METHOD)
[![Python Version](https://img.shields.io/badge/python-%3E%3D3.10-blue?logo=python&logoColor=white)](https://www.python.org)
[![uv](https://img.shields.io/badge/uv-package%20manager-blueviolet?logo=uv)](https://docs.astral.sh/uv/)
[![Docs](https://img.shields.io/badge/docs-online-green)](https://armelhbobdad.github.io/bmad-module-ultracode-goal/)
[![GitHub stars](https://img.shields.io/github/stars/armelhbobdad/bmad-module-ultracode-goal?style=social)](https://github.com/armelhbobdad/bmad-module-ultracode-goal/stargazers)

**Built for [Claude Code](https://www.anthropic.com/claude-code) — and only Claude Code.** UCG composes `/goal`, Auto Mode, Auto Memory, and runtime hooks, which exist nowhere else. Other editors can hold the skill files; the autonomous run itself requires Claude Code.

_UCG is a standalone [BMAD](https://github.com/bmad-code-org/BMAD-METHOD) module that delivers a BMAD Epic end to end without a babysitter. It preflights to a remediated green light, turns acceptance criteria into executable tests with the Test Architect (TEA), and advances a story only when a deterministic script reads `PASS` from TEA's gate artifact — not when the model decides it feels done._

**If UCG shipped an epic while you slept, give it a ⭐ — it helps others find this tool.**

</div>

---

## The Problem

You hand an agent an epic and tell it to "build until done." It runs, it commits, it declares victory. At review time you discover "done" meant "the model felt done." There are four reasons this keeps happening, and each one is a mechanic, not a vibe:

- **The `/goal` evaluator only sees the transcript.** It cannot open the gate artifact TEA wrote to disk. So the thing deciding completion is reading a story _about_ the work, not the verdict _on_ the work.
- **A model grading its own output is the fox auditing the henhouse.** Self-assessment is the weakest possible signal for a release gate, and it is exactly the signal you get by default.
- **`/rewind` checkpoints miss Bash changes.** Rollback you cannot trust is rollback you do not have.
- **Memory is context, not enforcement.** Telling the agent "never commit on `main`" in a prompt is a suggestion. An invariant has to be a hook the runtime _executes_, or it is not an invariant.

UCG exists because the documented mechanics make the intuitive shortcut wrong.

## Before vs After

**Before** — you babysit an epic story-by-story, approving each step, or you let an agent run unattended and find out at review time that its definition of "done" was its own opinion of its own work.

**After** — the preflight hard-gates the epic to a remediated green light before anything launches. TEA turns each story's acceptance criteria into red-phase tests. The run advances only when `gate_eval.py` reads `PASS` from TEA's deterministic `gate-decision.json`. Completion is a fact on disk, not a feeling in the transcript.

That verdict is a small, real JSON object. Here is the actual output of `gate_eval.py` reading a passing gate file (`--profile light`):

```json
{
  "verdict": "advance",
  "gate_status": "PASS",
  "p0_status": "100%",
  "p1_status": "95%",
  "overall_status": "88%",
  "nfr_status": null,
  "review_score": null,
  "reasons": [
    "gate read from gate-decision.json",
    "gate_status PASS -> advance"
  ]
}
```

The `gate_status` comes straight from TEA's artifact — `gate_eval.py` never re-derives the thresholds; it reads the status as given and maps it to a `verdict` (`PASS`/`WAIVED` → `advance`, `CONCERNS` → `defer`, `FAIL` → `reloop`, `NOT_EVALUATED` → `escalate`). Under `--profile production` the same run additionally ANDs two signals — `nfr_status` and `review_score` populate, and any failure downgrades an otherwise-`advance` verdict to `reloop`. The contract is fail-closed: a missing or unparseable signal counts as a _failing_ one, so prose drift degrades to a conservative re-loop, never a silent false-advance.

## Install

Requires [Claude Code](https://www.anthropic.com/claude-code) (the runtime UCG conducts — see above), [Node.js](https://nodejs.org/) >= 22, [Python](https://www.python.org/) >= 3.10, [uv](https://docs.astral.sh/uv/) (Python package runner), plus `git` and `gh` on PATH.

```bash
npx bmad-module-ultracode-goal install
```

You'll be prompted for a project name, your IDEs, and whether to install the learning material.

> **Hook security:** UCG installs `PreToolUse`/`Stop` hooks into your machine-local, gitignored `.claude/settings.local.json` at preflight — never into a committed file. They run zero-dependency Python scripts shipped in the skill. See [SECURITY.md](SECURITY.md) for exactly what they execute and how to remove them.

UCG is also available through the Claude plugin marketplace as an alternative to the npx installer — see [Getting Started](./docs/getting-started.md) for that path.

## Quick Start

Invoke the skill in natural language — "run this epic autonomously," "execute this epic," or `ultracode goal`. The conductor ingests the epic, preflights, defines done with TEA, executes, gates, and finalizes. Flags shape the run:

- `--light` — run the **trace gate only** (the production default runs the full TEA gate set).
- `--parallel` — opt into the **experimental** worktree fan-out instead of the sequential `/goal` spine.
- `--yes` — skip Stage 1's open-floor invite and the launch confirm. It **never** skips the hard preflight gate.
- `-H` — headless: run non-interactively and emit the five-key status JSON at every exit point.
- `--retro` — run the close-out retrospective (interactive runs offer it anyway; headless runs it only when this flag is passed).

See [How It Works](./docs/how-it-works.md) for the full stage-by-stage walkthrough and headless contract.

## Who Is This For?

- **Claude Code users running BMAD Epics** who want unattended delivery backed by a real gate, not an optimistic transcript.
- **Anyone burned by "the agent said it was done"** and who wants completion decided by a file on disk they can read themselves.
- **Engineers who want rollback they can trust** — every green story is one git commit on an isolated epic branch, not a `/rewind` checkpoint that misses Bash changes.

## How UCG Compares

A skeptical reader is probably already running one of these. Here is the honest contrast:

|                            | **UltraCode Goal**                                   | Hand-driven `/goal` per story        | Plain Auto Mode                  | CI-only gating                       |
| -------------------------- | ---------------------------------------------------- | ------------------------------------ | -------------------------------- | ------------------------------------ |
| Completion authority       | `gate_eval.py` reads TEA's `gate-decision.json`      | you, story by story                  | the model's self-assessment      | CI, but only after the agent stops   |
| Preflight autonomy gate    | hard-gate to remediated green (intervention budget 0)| ad hoc, per story                    | none                             | none — CI runs post-hoc              |
| Invariants enforcement     | `PreToolUse` hooks in `settings.local.json`          | your attention                       | prompt text (context, not a gate)| CI checks, after the fact            |
| Rollback                   | git: epic branch, one commit per green story         | manual                               | `/rewind` (misses Bash changes)  | revert after merge                   |
| Knowledge capture          | Auto Memory + CLAUDE.md split at Finalize            | none structured                      | none structured                  | none                                 |

The alternatives aren't bad — they solve different problems. **UCG solves exactly one: advancing an epic only when a deterministic script confirms the gate passed, and giving you the verdict JSON to check it yourself.**

## How It Works

UCG runs six stages in order, each routing by the testable conditions stated in its reference file:

1. **Ingest & Scope** — resolve the epic and its artifacts; confirm the profile (production default / `--light`).
2. **Preflight** — auto-remediate ambers, then hard-gate on red; create the git branch, merge hooks, populate the allowlist.
3. **Define Done** — TEA test-design plus per-story ATDD turn acceptance criteria into executable, red-phase tests.
4. **Execute** — the sequential `/goal` spine (default) or the `--parallel` worktree fan-out.
5. **Gate** — `gate_eval.py` reads TEA's verdict and routes: advance / defer / reloop / escalate.
6. **Finalize** — Auto Memory capture, optional retrospective, decision-log audit, run report.

The run is a straight line until the gate, which branches — and a `reloop` sends the story back through Execute within budget, while an unresolved blocker stops the run rather than guessing:

```mermaid
flowchart TD
    I["Stage 1 Ingest and Scope"] --> P{"Stage 2 Preflight hard gate"}
    P -->|"red blocker"| STOP["STOP / blocked"]
    P -->|"budget 0, green"| D["Stage 3 Define Done"]
    D --> X["Stage 4 Execute"]
    X --> G{"Stage 5 gate_eval.py reads TEA verdict"}
    G -->|"advance, PASS or WAIVED"| F["Stage 6 Finalize"]
    G -->|"defer, CONCERNS"| L["Ledger then advance"]
    L --> F
    G -->|"reloop, FAIL or signal downgrade"| X
    G -->|"escalate, NOT_EVALUATED or budget out"| STOP
    classDef gate fill:#6366F1,stroke:#4F46E5,color:#fff
    class P,G gate
```

Three enforcement layers keep the autonomy honest:

- **Hooks are the invariants** — `PreToolUse` guards (no commit on a protected branch; no commit before tests ran for the story) live in `settings.local.json`, where the runtime enforces them, not in memory.
- **`gate_eval.py` is the completion truth** — advancement is decided by reading TEA's gate file, never by the conductor's judgment and never by the `/goal` evaluator alone.
- **The Stop hook plus the turn cap are the budget** — the in-`/goal`-condition turn cap is the primary runaway guard; the `Stop` hook is a defensive third layer that records overruns against `max_turns_per_story` / `story_token_budget`.

## Verifying

You don't have to take the gate's word for it. The deterministic pieces ship with a test suite, and you can run the evaluator on a real artifact yourself.

Run the Python suite (72 tests across the preflight, gate, hook, and fingerprint scripts):

```bash
uv run --with pytest pytest skills/ultracode-goal/scripts/tests/ -v
```

Then inspect any `gate-decision.json` TEA wrote and evaluate it directly:

```bash
uv run skills/ultracode-goal/scripts/gate_eval.py \
  --trace-output path/to/traceability \
  --profile light
```

The JSON it prints is the same object UCG routes on — `verdict`, `gate_status`, and the `reasons` trail that explains how it got there. Nothing is hidden behind the model.

## Help UCG Improve

Every run that reaches Finalize ends with a self-improvement check. When it finds a defect in its own stage references, it can file a GitHub issue — deduplicated by a deterministic fingerprint so re-reporting is safe — with your approval. Headless runs queue findings to a machine-local cache instead of filing live. The fingerprint is install-mode-invariant, so the same defect maps to the same issue whether it surfaced in a dev checkout or an installed tree. **Please let runs finish through Finalize**, or [open an issue](https://github.com/armelhbobdad/bmad-module-ultracode-goal/issues/new/choose) directly. If UCG saved you an afternoon of babysitting, a ⭐ helps others find it.

## Learn More

The docs are organized into three buckets — **Why** (start here), **Try** (do stuff), and **Reference** (look things up):

**Why**

- **[Why UltraCode Goal](./docs/why-ultracode-goal.md)** — the problem, the three enforcement layers, and when not to use it.

**Try**

- **[Getting Started](./docs/getting-started.md)** — install, prerequisites, the flags, and your first autonomous run.
- **[How It Works](./docs/how-it-works.md)** — the six stages, their routing conditions, and the headless five-key emit.
- **[Parallel Mode](./docs/parallel-mode.md)** — the experimental worktree fan-out and its known limits.

**Reference**

- **[Architecture](./docs/architecture.md)** — the conductor model, enforcement layers in depth, and `customize.toml` resolution.
- **[Gate Model](./docs/gate-model.md)** — how `gate_eval.py` maps `gate_status` to a verdict, and the production AND-signals.
- **[Health Check](./docs/health-check.md)** — the terminal self-improvement loop: what it sends, privacy, and how to disable it.
- **[Troubleshooting](./docs/troubleshooting.md)** — real failure modes and their remediations.

## Acknowledgements

UCG is a conductor over primitives it does not replace. It builds on:

| Tool                                                                   | Role in UCG                                                                    |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| [BMAD Method](https://github.com/bmad-code-org/BMAD-METHOD)            | The epic toolbox UCG orchestrates (sprint planning, story creation, dev, review) |
| [TEA Test Architect](https://github.com/bmad-code-org/BMAD-METHOD)     | Machine-checked quality gates — test-design, ATDD, NFR, trace; the gate artifact |
| [Claude Code](https://www.anthropic.com/claude-code)                   | `/goal`, Auto Mode, Auto Memory, hooks, and git worktrees — the primitives UCG composes |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Changelog

Past releases are documented in [CHANGELOG.md](CHANGELOG.md).

## License

MIT License — see [LICENSE](LICENSE) for details.

---

**UltraCode Goal (UCG)** — A standalone [BMAD](https://github.com/bmad-code-org/BMAD-METHOD) module for autonomous epic delivery.

See [CONTRIBUTORS.md](CONTRIBUTORS.md) for contributor information.
