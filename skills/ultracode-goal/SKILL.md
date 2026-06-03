---
name: ultracode-goal
description: Runs a BMAD Epic autonomously to a machine-checked Definition-of-Done. Use when the user requests to 'run an epic autonomously', 'execute this epic', 'ultracode goal', or 'autonomously deliver the epic'.
---

# UltraCode Goal

## Overview

This skill autonomously delivers a BMAD Epic to a **machine-checked** Definition-of-Done. Act as an autonomous delivery conductor — a staff engineer who also owns the release gate. It preflights the Epic to a hard, *remediated* green light, turns acceptance criteria into executable tests with the Test Architect (TEA), drives the stories to completion, and advances only when TEA's deterministic quality gate reads PASS — capturing what it learns to Auto Memory so the next run is sharper. Your output is a delivered, gate-passed Epic, a run report, and a deferred-work ledger of anything safely parked for later.

Module `bmad-module-ultracode-goal`. It orchestrates the installed BMAD epic toolbox (`bmad-sprint-planning`, `bmad-create-story`, `bmad-check-implementation-readiness`, `bmad-dev-story`, `bmad-code-review`, `bmad-correct-course`, `bmad-sprint-status`, `bmad-retrospective`) and the TEA gates (`bmad-testarch-framework`, `-ci`, `-test-design`, `-atdd`, `-automate`, `-test-review`, `-nfr`, `-trace`). It composes Claude Code primitives — `/goal`, Auto Mode, Auto Memory, hooks, git/worktree isolation — it is a conductor over them, not a replacement for them.

## Conventions

- Bare paths (e.g. `references/preflight.md`) resolve from the skill root.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## On Activation

### Step 1: Resolve the Workflow Block

Run: `python3 {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --key workflow`

If it fails, resolve the `workflow` block yourself by reading these three files in base → team → user order (scalars override, tables deep-merge, arrays append): `{skill-root}/customize.toml`, `{project-root}/_bmad/custom/{skill-name}.toml`, `{project-root}/_bmad/custom/{skill-name}.user.toml`. Read every customized value below as `{workflow.<name>}`.

Load config from `{project-root}/_bmad/config.yaml` and `config.user.yaml` (root + `bmm` section for `{planning_artifacts}`); fall back to `{project-root}/_bmad/bmm/config.yaml`. If config is missing, note that `bmad-bmb-setup` is available and continue with defaults. Load `{workflow.persistent_facts}` and greet in `{communication_language}`.

**Run modes.** Profile defaults to **production** (full TEA gates); `--light` runs the trace gate only. Execution defaults to the **sequential** `/goal` spine; `--parallel` opts into the experimental worktree fan-out. `-H` is headless. `--yes` skips Stage 1's open-floor invite and the launch confirm (the launch briefing still prints) — it **never** skips the hard preflight gate. `--retro` runs the close-out retrospective: interactive runs offer it at Epic close anyway, but headless runs it only when `--retro` was passed.

**Resume.** The workspace is this skill's run folder holding `.decision-log.md`. If one exists for the Epic, surface it with its last session date and offer to resume — the log recovers full state regardless of compaction. Otherwise create it at intent and append a session heading. On resume, re-enter Execute at the first story whose last logged gate verdict is not advance; advanced stories are not re-run; re-assert (do not rebuild) the Epic branch, hooks, and allowlist before continuing.

## Non-negotiables

These exist because the documented mechanics make the intuitive shortcut wrong. Do not optimize them away.

- **Completion is decided by `scripts/gate_eval.py` reading TEA's `gate-decision.json` — never your own judgment, and never the `/goal` evaluator alone.** That evaluator only sees the transcript; it cannot read the gate file. The JSON is the truth.
- **Launch the unattended run only when `scripts/preflight_check.py` returns green *after the remediation pass* (intervention budget == 0) and ultracode + Auto Mode are on.** Under `--parallel`, the fan-out takes no mid-run input — every gate is resolved before launch or not at all.
- **Only non-gate-blocking work defers** to `{workflow.deferred_work_path}`, and the Epic keeps moving; a P0/critical FAIL never defers — it re-loops within budget or escalates.
- **Rollback is git** — Epic branch off `{workflow.epic_branch_prefix}`, one commit per green story, worktree isolation. `/rewind` checkpoints miss Bash changes; do not rely on them.
- **Invariants live in PreToolUse hooks**, auto-merged into `.claude/settings.local.json` at preflight — not in memory, which is context, not enforcement.

## Stages

| # | Stage | Purpose | Location |
|---|-------|---------|----------|
| 1 | Ingest & Scope | Resolve the Epic + artifacts; confirm profile (production default / `--light`) | `references/ingest-and-scope.md` |
| 2 | Preflight | Auto-remediate ambers, then hard-gate on red; git branch, hooks, allowlist | `references/preflight.md` |
| 3 | Define Done | TEA test-design + per-story ATDD → executable acceptance tests | `references/define-done.md` |
| 4 | Execute | Sequential `/goal` spine (default) or `--parallel` worktree fan-out | `references/execute.md` |
| 5 | Gate | `gate_eval.py` verdict → advance / defer / reloop / escalate | `references/gate.md` |
| 6 | Finalize | Auto Memory capture, optional retrospective, decision-log audit, report | `references/finalize.md` |

Run the stages in order; each routes by the testable conditions stated in its file. The decision log is canonical memory — record scope, the preflight verdict, every gate outcome, and every deferral as you go.

## Headless

With `-H`, run non-interactively: infer scope, default to **production** (unless `--light`), never prompt — a secret that cannot be resolved becomes a red blocker, not a question — and let `.decision-log.md` absorb every assumption.

**One emit shape, every exit point.** Whether the run completes (Stage 6), or blocks early at ingest (Stage 1, e.g. epic unresolved), at preflight (Stage 2), or at a story escalation (Stage 6), emit this exact object — all five keys always present, `null` when that artifact was not produced, and `reason` carrying a one-line cause **only** when blocked:

```json
{"status": "complete|blocked",
 "skill": "ultracode-goal",
 "decision_log": "<path to this run's .decision-log.md>",
 "report": "<path to run-report.md, or null>",
 "deferred_work": "<path to {workflow.deferred_work_path}, or null>",
 "reason": "<one line, present only when blocked>"}
```

An automator parses one schema regardless of where the run stopped; a blocked-before-report exit returns `report` and `deferred_work` as `null` rather than omitting them.
