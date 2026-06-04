# Stage 6 — Finalize

**Goal:** Make the run pay off for the next one. Capture what was learned to the right durable store, optionally run a retrospective, audit the decision log, produce a run report, and surface the deferred-work ledger. This is the terminal stage — reached after the Epic-level gate advanced, or when a story escalated and the run is `blocked`. Converse in `{communication_language}`; the run report and ledger are written in `{document_output_language}`.

## Capture to Auto Memory — deliberately

Auto Memory is passive by default; drive it on purpose so the learnings land in the right place and the next run starts sharper. Decide each learning's home:

- **Machine-local learnings** (this repo's build quirks, a flaky-test workaround, a path that differs from convention, a TEA config gotcha) → tell the session to **`remember X`** so it persists to Auto Memory. Keep `MEMORY.md` terse — a short index that points to per-topic files; put the detail in the topic file, not the index.
- **Team standards** (a convention every contributor and future run should follow — a lint rule, a commit-message shape, a forbidden pattern) → write to `{project-root}/CLAUDE.md` or `{project-root}/.claude/rules`, not to machine-local memory. CLAUDE.md is context the whole team and every agent inherits; Auto Memory is yours alone.

The split matters: a team standard buried in machine-local memory never reaches the team, and a machine-local quirk in CLAUDE.md pollutes shared context. Route each learning by who needs it.

## Optional retrospective (`--retro`)

Interactive runs **offer** the retrospective at Epic close (skip it by default if the user declines); headless runs it **only when `--retro` was passed**. When run, `bmad-retrospective` covers the Epic, and its lessons feed back through the capture step above — durable conclusions go to memory or CLAUDE.md by the same machine-local-vs-team split. It is additive, not required to close the run. A retrospective re-uses the Stage 1 filtered recall (its recurrence counts) — it never makes a fresh MCP call.

## Decision-log audit

Walk every entry in this run's `.decision-log.md` (scope, preflight verdict, each gate verdict, each deferral, every assumption). Each must resolve to one of three: **captured in the run report** (a primary decision or outcome the user takes away), **captured in the addendum** (a parked alternative or rejected option that needs a home but not the report), or **explicitly marked process noise** (set aside, not silently dropped). End with a shared accounting of how the run's reasoning was handled — not a one-sided polish.

## Run report

Produce a report (write it as a peer of `.decision-log.md` in the run folder, e.g. `run-report.md`) covering:

- Epic and profile (production / `--light`), branch off `{workflow.epic_branch_prefix}`, sequential vs `--parallel`.
- Per-story outcome: gate_status and verdict (advance / defer / reloop / escalate), and any re-loops spent against budget.
- The Epic-level gate result.
- Budget consumed vs `{workflow.max_turns_per_story}` / `{workflow.story_token_budget}`.
- Learnings captured and where they went (memory vs CLAUDE.md).
- A pointer to the deferred-work ledger and its open-item count.
- Cross-Session Recall: consulted / wrote / skipped, plus the outbox tombstone count when the drain ran.

## Cross-Session Recall write (optional)

Read `{workflow.implementation_artifacts}/.mem-state.json`. Act only on its latched state.

**Present + `schema_ok` + recall `on`** — write this run's summary, draining first so nothing parked in a prior crash is lost:

1. **Drain the outbox** — replay each spilled payload with **one** `save_observation` attempt apiece:

   ```
   uv run {skill-root}/scripts/mem_observation.py drain --impl-artifacts {workflow.implementation_artifacts}
   ```

2. **Build this run's payload** — epic, run-id, gate-status, verdict, project, the deferred-work path, any root causes by taxonomy class, and the mechanical `recurred` yes/no for each Stage 1 advisory consumed:

   ```
   uv run {skill-root}/scripts/mem_observation.py build --impl-artifacts {workflow.implementation_artifacts} --epic <id> --run-id <run-id> --gate-status <status> --verdict <advance|blocked> --project <name> --deferred {workflow.deferred_work_path} [--root-cause class=<taxonomy>,path=<artifact>]… [--advisory sig=<s>,recurred=<yes|no|unknown>]…
   ```

3. **One `save_observation`** with that payload. On any MCP error, do **not** retry — pipe the payload to `mem_observation.py spill`, log `WARN mem-write-deferred` to `.decision-log.md`, and continue. The run report always lands; the memory write is best-effort.

**Present but recall `off`** — print the one-line notice and write nothing: *claude-mem detected — Cross-Session Recall is off; this run consulted no memory and wrote none. Enable with `cross_session_recall = "on"`.*

**Always, both paths** — **remove** `{workflow.implementation_artifacts}/.mem-state.json` as part of close-out. No active run means the hook stops gating claude-mem; an orphaned latch would deny the user's own usage between runs.

## Record the terminal run-status

Execute maintains the heartbeat `{workflow.implementation_artifacts}/run-status.json` as the spine advances (shape: `{epic, story, index, total, last_verdict, reloop_count, profile, updated}`). At close, write its **terminal** state — the final story/index, the Epic-level `last_verdict` (`advance` when complete, the escalating story's verdict when blocked), and a fresh `updated` timestamp — so a poller reading the file after the run sees the settled outcome, not a stale mid-run snapshot.

## Surface the deferred-work ledger

Show the user **this run's Epic heading** from the ledger at `{workflow.deferred_work_path}` — the open items under that one heading, their severity and suggested actions — so nothing parked during the run is invisible at handoff. The ledger holds one heading per Epic across runs; do not surface other Epics' parked work. If the file (or this Epic's heading) does not exist, say so plainly: nothing was deferred this run.

## Epic-complete hook

This hook fires **only when the Epic-level gate verdict was `advance`** (a `complete` run). On a `blocked` run — a story escalated and the Epic never advanced — skip this step entirely; a "notify success" command must not fire on a blocked Epic.

When the Epic advanced, run: `python3 {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --key workflow.on_epic_complete`

If the resolved `{workflow.on_epic_complete}` is non-empty, follow it as the final terminal instruction (a prompt to run or a shell command) before exiting.

## Headless output

In headless (`-H`), compose the final JSON, run the Workflow health check (below) in its unattended queue-only mode, then emit the JSON and stop. `status` is `complete` when the Epic-level gate advanced, or `blocked` when a story escalated. This is the **same five-key shape every headless exit point honors** (Stage 1 first-touch / already-done blocks, Stage 2 preflight block, and this Stage 6 final emit): all five keys are **always present**, with `report` and `deferred_work` set to `null` when not produced, and `reason` carrying a one-line cause only when `blocked` (`null` otherwise). An early `blocked` exit that produced no report still emits `"report": null` — never a missing key — so a caller parsing the documented shape never raises a KeyError:

```json
{"status": "complete|blocked",
 "skill": "ultracode-goal",
 "decision_log": "<path to this run's .decision-log.md>",
 "report": "<path to run-report.md, or null>",
 "deferred_work": "<path to {workflow.deferred_work_path}, or null>",
 "reason": "<one line when blocked, else null>"}
```

## Workflow health check (terminal)

After the run-status is settled and (in headless) the JSON is composed but **before** the final emit/exit, load `references/health-check.md`, read it fully, and execute it. This is the true terminal step for every run that reached Stage 6 — both a `complete` run and a `blocked` (escalated) run, since the workflow drove real work either way and genuine friction is observable. In headless it runs in its unattended queue-only mode and **never blocks the emit**; see that file's routing rules. Do not perform any other action between this section and executing the health check.
