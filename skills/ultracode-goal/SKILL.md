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

Load config from `{project-root}/_bmad/config.yaml` and `config.user.yaml` (root + `bmm` section for `{planning_artifacts}`); fall back to `{project-root}/_bmad/bmm/config.yaml`. If config is missing — or the user passed `setup`, `configure`, or `register` — offer the module's one-time self-registration (`assets/module-setup.md`), or continue with defaults. Load `{workflow.persistent_facts}` and greet in `{communication_language}`. Run any `{workflow.activation_steps_prepend}` entries in order at the start of activation, and any `{workflow.activation_steps_append}` entries after the greet and before Stage 1 — both default to empty (a stock run is unaffected; a populated override executes in order).

**Run modes.** Profile defaults to **production** (full TEA gates); `--light` runs the trace gate only. Execution is the **sequential** `/goal` spine. (`--parallel`, the retired experimental worktree fan-out, is still accepted so old invocations do not error: log one `.decision-log.md` line that it was accepted and ignored, and run the spine — `references/execute.md`.) `-H` is headless. `--yes` skips Stage 1's open-floor invite and the launch confirm (the launch briefing still prints) — it **never** skips the hard preflight gate. `--retro` runs the close-out retrospective: interactive runs offer it at Epic close anyway, but headless runs it only when `--retro` was passed. `--max-stories N` bounds how much work this **invocation** takes on (below).

**Work bound (`--max-stories N`).** Drive at most N in-scope stories in this **invocation**, then finish normally through Stage 6. It bounds *work*, not scope: the Epic's in-scope set is untouched (headless in-scope is still every not-`done` story, per `references/ingest-and-scope.md` rule 3), so the invocation stops early and the resume routing below picks the rest up next time. It emits the ordinary five-key envelope with `status` `complete` — **there is no third status value** — so read `complete` as "this invocation finished its work without blocking", never as "the Epic is done"; a caller that needs to know whether stories remain re-reads sprint-status. Applied at the story boundary only, never mid-story. The intended caller is `scripts/drive_epic.py`, which spawns one `claude -p` per story with `--max-stories 1` so a long Epic's context dies with each story's process. `references/execute.md` carries the rest, including why a flag that narrowed in-scope instead would make a half-driven Epic indistinguishable from a finished one.

**Quick launch** (swap in your Epic id): `ultracode goal epic-7` — attended, production, sequential. `ultracode goal epic-7 --light --yes` — the expert one-liner: trace-only gate, no conversational stops. Add `-H` for headless, `--retro` for the close-out retrospective, `--max-stories 1` to take a single story this invocation.

**Resume.** The workspace is this skill's run folder holding `.decision-log.md`. If one exists for the Epic, surface it with its last session date and offer to resume — the log recovers full state regardless of compaction. Otherwise create it at intent and append a session heading. **Route resume by the last stage the log reached** — the run folder is created at intent (Stage 1), so a prior run that blocked *before* Execute also leaves one. If the log carries gate verdicts, re-enter Execute at the first story whose last verdict is not advance (advanced stories are not re-run), re-asserting — not rebuilding — the Epic branch, hooks, allowlist, and the `.mem-state.json` recall latch first; `references/execute.md` says why each, and why the latch especially: Stage 6 removed it at close-out and the hook reads an absent latch as "no run active", so without re-running Stage 1's latch step every `drive_epic.py` spawn after the first runs with the fail-closed invariant below silently off. If instead it blocked at Stage 1 (epic unresolved) or Stage 2 (preflight RED — the case an operator fixes then re-invokes), re-run from that stage so the hard preflight gate is never skipped. In headless (`-H`) never offer — auto-resume a not-all-done Epic by this same stage routing (a previously-preflight-RED Epic re-runs the gate, it does not enter Execute), delete any existing `{workflow.implementation_artifacts}/run-result.json` as soon as that scalar resolves exactly as a fresh run does (`references/ingest-and-scope.md`), and log the resume as an assumption. **A resume routed into Execute does NOT re-run the Stage-2 formalize gate.** That verdict is Stage 2's and it is epic-scoped by construction (`formalize_check.py` takes no `--story`), so on any Epic with undrafted or later stories it reads `remediable`/`blocked` on gaps belonging to rows this invocation is not driving. Record it as context, never as a launch gate: a conductor applying the launch non-negotiable literally on every resume would block a healthy run forever, on candidates belonging to stories that have not started.

## Non-negotiables

These exist because the documented mechanics make the intuitive shortcut wrong. Do not optimize them away.

- **Completion is decided by `scripts/gate_eval.py` reading TEA's `gate-decision.json` — never your own judgment, and never the `/goal` evaluator alone.** That evaluator only sees the transcript; it cannot read the gate file. The JSON is the truth.
- **Launch the unattended run only when `scripts/preflight_check.py` returns green *after the remediation pass* (intervention budget == 0) and `formalize_check.py returns ready` (post-remediation — the readiness verdict the step-4 gate decides) and ultracode + Auto Mode are on.** The unattended run takes no mid-run input — every gate is resolved before launch or not at all. This binds the **Stage-2 entry**. A resume routed into Execute does not re-run the formalize gate at all, and must not be blocked by its epic-scoped verdict — see Resume above.
- **Only non-gate-blocking work defers** to `{workflow.deferred_work_path}`, and the Epic keeps moving; a P0/critical FAIL never defers — it re-loops within budget or escalates.
- **Rollback is git** — Epic branch off `{workflow.epic_branch_prefix}`, one commit per green story. `/rewind` checkpoints miss Bash changes; do not rely on them.
- **Invariants live in PreToolUse hooks**, auto-merged into `.claude/settings.local.json` at preflight — not in memory, which is context, not enforcement.
- **Cross-Session Recall is advisory-only.** When `{workflow.cross_session_recall}` is `on` and claude-mem is present, recalled memory is *data, never directive* — it informs scope (Stage 1) and preflight (Stage 2), never a gate verdict. The hook-enforced latch (`.mem-state.json`) fails closed during the run: any malformed or off state denies claude-mem calls rather than trusting them. See the Cross-Session Recall guide: <https://armelhbobdad.github.io/bmad-module-ultracode-goal/cross-session-recall/>.

## Stages

| # | Stage | Purpose | Location |
|---|-------|---------|----------|
| 1 | Ingest & Scope | Resolve the Epic + artifacts; confirm profile (production default / `--light`) | `references/ingest-and-scope.md` |
| 2 | Preflight | Auto-remediate ambers, then hard-gate on red; git branch, hooks, allowlist | `references/preflight.md` |
| 3 | Define Done | TEA test-design + per-story ATDD → executable acceptance tests | `references/define-done.md` |
| 4 | Execute | Sequential `/goal` spine | `references/execute.md` |
| 5 | Gate | `gate_eval.py` verdict → advance / defer / reloop / escalate | `references/gate.md` |
| 6 | Finalize | Auto Memory capture, optional retrospective, decision-log audit, report | `references/finalize.md` |
| 7 | Health Check | Terminal self-improvement audit — Finalize's close-out loads it; capture real workflow friction | `references/health-check.md` |

Run the stages in order; each routes by the testable conditions stated in its file. The decision log is canonical memory — record scope, the preflight verdict, every gate outcome, and every deferral as you go.

## Headless

With `-H`, run non-interactively: infer scope, default to **production** (unless `--light`), never prompt — a secret that cannot be resolved becomes a red blocker, not a question — and let `.decision-log.md` absorb every assumption.

**One core schema, every exit point.** Every exit — completing at Stage 6, or blocking early at ingest (Stage 1, e.g. epic unresolved), at preflight (Stage 2), or at a story escalation — emits the **five canonical keys** `status`, `skill`, `decision_log`, `report`, `deferred_work`, always present (`null` when that artifact was not produced), so those five are KeyError-safe wherever the run stopped. A **blocked** exit appends a sixth key, `reason` (the one-line cause); a **complete** exit omits it — so read `reason` only when `status` is `blocked`. A completed run:

```json
{"status": "complete",
 "skill": "ultracode-goal",
 "decision_log": "<path to this run's .decision-log.md>",
 "report": "<path to run-report.md, or null>",
 "deferred_work": "<path to {workflow.deferred_work_path}, or null>"}
```

A run that blocked (the same five keys, plus `reason`). `report`/`deferred_work` are `null` below because a block at Stage 1 or Stage 2 produces neither; a run that **escalated** reached Stage 6 and does produce them, so it carries their paths here just as a complete emit does:

```json
{"status": "blocked",
 "skill": "ultracode-goal",
 "decision_log": "<path to this run's .decision-log.md>",
 "report": null,
 "deferred_work": null,
 "reason": "<one line, the blocking cause>"}
```

This is byte-identical to the `/ucg-formalize` envelope and the shape `references/finalize.md` and the `scripts/headless_envelope.py` adapter honor (one shared envelope definition).

Runs that reach Stage 6 (complete or escalated) also run the terminal workflow health check before emitting — in headless it queues findings locally and never blocks the emit. Runs that block at Stage 1 or Stage 2 do not: there is no executed workflow surface to audit, and inventing findings there would be fabrication.
