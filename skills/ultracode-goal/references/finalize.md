# Stage 6 — Finalize

**Goal:** Make the run pay off for the next one. Capture what was learned to the right durable store, optionally run a retrospective, audit the decision log, produce a run report, and surface the deferred-work ledger. This is the terminal stage — reached after the Epic-level gate advanced, when a story escalated and the run is `blocked`, or when the run completed its in-scope *strict subset* of a deliberately-partial Epic without an Epic-level gate (a **`partial-complete`** outcome — attended only; headless's in-scope is every not-`done` story, so a successful headless run always finishes the Epic and emits `complete`). Converse in `{communication_language}`; the run report and ledger are written in `{document_output_language}`.

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
- Turns consumed vs `{workflow.max_turns_per_story}`.
- Learnings captured and where they went (memory vs CLAUDE.md).
- A pointer to the deferred-work ledger and its open-item count.
- Cross-Session Recall: consulted / wrote / skipped, plus the outbox tombstone count when the drain ran.

## Gate trail

Write the per-story evidence trail as **`gate-trail.md`, a peer of `run-report.md`** in the run folder — the same folder that holds `.decision-log.md`, never `{workflow.implementation_artifacts}`. Where the run report is prose you compose, this one is synthesized by script from artifacts the run already wrote, so a reader can audit a green Epic without re-running it. Every story gets a section whose table traces five columns: acceptance criterion → planned test → result → gate verdict → commit.

```
uv run {skill-root}/scripts/gate_trail.py --run-dir <this run's folder> --profile <light|production> --impl-artifacts {workflow.implementation_artifacts} --trace-output <the trace artifacts dir> --story <id>… --repo {project-root}
```

**The run's in-scope story ids are required, not optional.** Pass `--story` once per in-scope story **in sprint order** — the order is what turns the recorded baselines into commit ranges (each story's range ends at the next story's baseline, and at `HEAD` for the last one). The script prints the path it wrote; name that path in the run report.

Naming no story (or a blank id) is refused: the script exits `2` with a usage line and writes nothing, rather than rendering a well-formed trail of zero sections that traces nothing and then gets named in the run report as delivered evidence. This does not contradict the fail-soft property below — `--story` is an **argument, not one of the sources**: an absent source is evidence the trail reports as `n/a`, while an absent story list is a malformed invocation, and there is nothing to render fail-soft *about*. That refusal is an **invocation error, not a gate verdict** — the same lane a missing `--run-dir` or `--profile` already occupies. It is never an escalation and never a reason to block a run that reached this stage: re-issue the command with the ids (you already hold them, in sprint order), **and either way continue through the remaining finalize steps** — the terminal `run-status.json` write, the headless emit and the health check must still run.

Two properties are load-bearing, so do not "improve" them:

- **It renders verdicts, it never forms one.** The verdict cell is the verdict the run already recorded, or the gate artifact's `gate_status` mapped through the gate's own table. The production AND ran once, when the gate decided; re-running it here would be a second, later judgment on the same story. A story whose verdict was not `advance` is shown as it was decided — never quietly green.
- **It fails soft.** Every source is optional: a missing or unreadable checklist, trace report, gate file or baseline renders `n/a` in its cell and the trail continues. This is the opposite of the gate, which fails closed, and deliberately so — the trail has no authority, and failing closed here would turn a reporting bug into a blocked run. Under `--light` there is no acceptance checklist by design, so those sections synthesize from the hand-authored trace report and gate decision instead.

**Optional diff viewer — detect, then degrade to silence.** The trail's commit column names a sha per story and the run report names the Epic branch, but neither opens a diff. When `hunk` is detected on PATH (`which hunk`), the run report may point at what it already names: `hunk show <commit>` for one story's commit, `hunk diff <epic-branch>` for the run as a whole, so a reader auditing the evidence can open a diff without reconstructing the range by hand. Absent `hunk`, print nothing — no suggestion and no warning that it is missing, and both surfaces read exactly as they did before. It is a render affordance and nothing else: do not add it to `{workflow.allowlist_commands}`, do not add a preflight check for it, and never let it reach a machine surface — not the gate verdict JSON, not the headless envelope, not the terminal `run-status.json`. Those are parsed by callers that will not have it installed.

## Cross-Session Recall write (optional)

Read `{workflow.implementation_artifacts}/.mem-state.json`. Act only on its latched state.

**Present + `schema_ok` + recall `on`** — write this run's summary, draining first so nothing parked in a prior crash is lost:

1. **Drain the outbox** — replay each spilled payload with **one** `save_observation` attempt apiece:

   ```
   uv run {skill-root}/scripts/mem_observation.py drain --impl-artifacts {workflow.implementation_artifacts}
   ```

2. **Build this run's payload** — epic, run-id (the one minted at Stage 1, `epic-<id>-<UTC yyyymmddThhmmssZ>`, reused verbatim — the outbox filename derives from it), gate-status, verdict, project, the deferred-work path, any root causes by taxonomy class, and the mechanical `recurred` yes/no for each Stage 1 advisory consumed:

   ```
   uv run {skill-root}/scripts/mem_observation.py build --impl-artifacts {workflow.implementation_artifacts} --epic <id> --run-id <run-id> --gate-status <status> --verdict <advance|blocked> --project <name> --deferred {workflow.deferred_work_path} [--root-cause class=<taxonomy>,path=<artifact>]… [--advisory sig=<s>,recurred=<yes|no|unknown>]…
   ```

3. **One `save_observation`** with that payload. On any MCP error, do **not** retry — pipe the payload to `mem_observation.py spill`, log `WARN mem-write-deferred` to `.decision-log.md`, and continue. The run report always lands; the memory write is best-effort.

**Present but recall `off`** — print the one-line notice and write nothing: *claude-mem detected — Cross-Session Recall is off; this run consulted no memory and wrote none. Enable with `cross_session_recall = "on"`.*

**Always, both paths** — **remove** `{workflow.implementation_artifacts}/.mem-state.json` as part of close-out. No active run means the hook stops gating claude-mem; an orphaned latch would deny the user's own usage between runs.

## Record the terminal run-status

Execute maintains the heartbeat `{workflow.implementation_artifacts}/run-status.json` as the spine advances (shape: `{epic, story, index, total, last_verdict, last_reasons, reloop_count, stories, budget_used, profile, updated}`). At close, write its **terminal** state — the final story/index, the `last_verdict` (`advance` when the Epic completed, the escalating story's verdict when blocked, or the last in-scope story's `advance` for a `partial-complete` run — a deliberate strict subset of the Epic delivered with no Epic-level gate), and a fresh `updated` timestamp — so a poller reading the file after the run sees the settled outcome, not a stale mid-run snapshot. **Write the whole shape, not a subset.** This write overwrites the file, so a narrower object silently strips keys a poller was reading mid-run: carry `last_reasons`, `stories` and `budget_used` through from the last heartbeat rather than dropping them off the artifact at the moment the run settles.

## Surface the deferred-work ledger

Show the user **this run's Epic heading** from the ledger at `{workflow.deferred_work_path}` — the open items under that one heading, their severity and suggested actions — so nothing parked during the run is invisible at handoff. The ledger holds one heading per Epic across runs; do not surface other Epics' parked work. If the file (or this Epic's heading) does not exist, say so plainly: nothing was deferred this run.

## Epic-complete hook

This hook fires **only when the Epic-level gate verdict was `advance`** (a `complete` run). On a `blocked` run — a story escalated and the Epic never advanced — skip this step entirely; a "notify success" command must not fire on a blocked Epic.

When the Epic advanced, run: `python3 {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --key workflow.on_epic_complete`

If the resolved `{workflow.on_epic_complete}` is non-empty, follow it as the final terminal instruction (a prompt to run or a shell command) before exiting.

## Escalation hook

The mirror of the epic-complete hook at the opposite terminal. This hook fires **only on a `blocked` run** — a story escalated and the Epic never advanced — and never on a clean advance, so an operator who walked away learns that the run stopped being able to make progress on its own.

Execute may already have pinged when it first observed the escalation marker, so this site is deduped against that same run-scoped marker, `{workflow.implementation_artifacts}/.on-escalation-fired-<run-id>`, **check-then-write**, at that byte-identical path — `<run-id>` is the run id minted at Stage 1, carried forward verbatim. If the marker is already present, skip silently: the other fire site already pinged for this run. If it is absent, run: `python3 {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --key workflow.on_escalation`

When the resolved `{workflow.on_escalation}` is non-empty, follow it as an instruction (a prompt to run or a shell command), stating alongside it **the escalating story id** and the path to that story's typed `escalation-<story_id>.json` sidecar as the context it carries, and only then write the fired-marker. A resolved-empty value is a silent no-op — nothing fires and no fired-marker is written — so an empty hook can never suppress a later real one.

This is a side effect on the way out, never a gate on the exit: a hook that errors, hangs or is missing must not change the emitted JSON, the status, or the run-status already recorded. Under `--parallel` this is the only reachable fire site, since the fan-out's worktree agents each see their own `{workflow.implementation_artifacts}`; that is sufficient, because Finalize always runs in the conductor.

## Headless output

In headless (`-H`), build the final JSON **through the `scripts/headless_envelope.py` adapter** — never hand-composed here — run the Workflow health check (below) in its unattended queue-only mode, then emit the JSON and stop. `status` is `complete` when the Epic-level gate advanced, or `blocked` when a story escalated, and the adapter has one entry point per shape:

```
build_complete_envelope(<path to this run's .decision-log.md>, report=<run-report.md path or None>, deferred_work=<{workflow.deferred_work_path} or None>, impl_artifacts={workflow.implementation_artifacts})
build_headless_envelope(<blocker list>, <path to this run's .decision-log.md>, impl_artifacts={workflow.implementation_artifacts})
```

**Both emits are also written to `{workflow.implementation_artifacts}/run-result.json` by `scripts/headless_envelope.py` itself, which is the writer of that file** — so an automator reads a file at a pinned path instead of scraping the transcript for the terminal verdict. The adapter serializes once and hands the same string to both sinks, so the file is byte-identical to what you emit on stdout: print exactly what it produced, do not re-serialize the dict yourself. The write is best-effort and never a gate on the exit — if it fails, the adapter logs `WARN run-result-write-failed` to `.decision-log.md` and the run still emits.

Three constraints on that file:

- **Headless only.** An attended run writes no `run-result.json`. An operator who found a stale one from an attended run would read it as a headless terminal, so do not "helpfully" write it in both modes.
- **Path-pinned and overwrite-in-place**, exactly like `run-status.json`: a second run against the same `{workflow.implementation_artifacts}` overwrites the first run's result.
- **No `--parallel` trust claim.** The fan-out's worktree agents each see their own `{workflow.implementation_artifacts}`, so there is no single `run-result.json` an automator can read for a fan-out run — the same scope note that binds `.baseline-<story>`, `run-status.json` and the escalation sidecars.

The emitted object is the **same five-canonical-key shape every headless exit point honors** (Stage 1 first-touch / already-done blocks, Stage 2 preflight block, and this Stage 6 final emit): the five keys `status`/`skill`/`decision_log`/`report`/`deferred_work` are **always present** (`report` and `deferred_work` `null` when not produced), so a caller parsing them never raises a KeyError. A **complete** emit is those five; a **blocked** exit appends a sixth, `reason` (the one-line cause):

```json
{"status": "complete",
 "skill": "ultracode-goal",
 "decision_log": "<path to this run's .decision-log.md>",
 "report": "<path to run-report.md, or null>",
 "deferred_work": "<path to {workflow.deferred_work_path}, or null>"}
```

A blocked exit (a story escalated) emits the same five keys plus `reason`, with `report`/`deferred_work` `null` — the shape `references/preflight.md` and the `scripts/headless_envelope.py` adapter build (one shared envelope definition), and it lands in the same `run-result.json` the complete emit does.

## Workflow health check (terminal)

After the run-status is settled and (in headless) the JSON is composed but **before** the final emit/exit, load `references/health-check.md`, read it fully, and execute it. This is the true terminal step for every run that reached Stage 6 — both a `complete` run and a `blocked` (escalated) run, since the workflow drove real work either way and genuine friction is observable. In headless it runs in its unattended queue-only mode and **never blocks the emit**; see that file's routing rules. Do not perform any other action between this section and executing the health check.
