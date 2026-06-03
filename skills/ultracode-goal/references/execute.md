# Stage 4 — Execute

Drive each in-scope story from its red-phase acceptance tests (generated in Stage 3) to a green, committed state. This stage **produces and prints evidence**; it does **not** decide completion. The completion verdict belongs to Stage 5 (`scripts/gate_eval.py` reading TEA's `gate-decision.json`) — never the `/goal` transcript evaluator, which can only see what you surface and cannot read the gate file. Run prose in `{communication_language}`.

Two paths. **Sequential `/goal` spine is the DEFAULT.** `--parallel` worktree fan-out is an additive, **EXPERIMENTAL** opt-in. Both share the same hooks and the same Stage 5 gate.

Preconditions (asserted, not assumed): you are on the Epic branch (`{workflow.epic_branch_prefix}…`, off a `{workflow.protected_branches}` branch), PreToolUse + Stop hooks are active in `.claude/settings.local.json`, the allowlist is pre-populated, and every in-scope story has an `atdd-checklist-{story_key}.md` with `test.skip` acceptance tests. If any is false, return to Stage 2.

**On resume, re-enter Execute at the first story whose last logged gate verdict is not advance; advanced stories are not re-run; re-assert (do not rebuild) the Epic branch, hooks, and allowlist before continuing.**

## Default — Sequential `/goal` spine

For each in-scope story, in sprint order, run this loop:

0. **Set the current story** so the PreToolUse hook can locate this story's marker: write the story id to `{workflow.implementation_artifacts}/.current-story` (or export `ULTRACODE_STORY_ID=<story_id>` for the run). The guard reads the story id from `ULTRACODE_STORY_ID`, falling back to that `.current-story` file — without one set, it cannot find the marker and denies every commit.
1. `bmad-create-story` (if not already current) → `bmad-dev-story` implementing the feature and **un-skipping** the story's ATDD acceptance tests (remove `test.skip()`). Before delegating, check the run's `.decision-log.md` for an **Operator notes** entry naming this story (a pre-launch hint like "watch the auth flow in story 3") and surface that note into the `bmad-dev-story` / review context for this story so the operator's last words actually reach the work.
2. Run the tests, lint, and build, and **PRINT the raw output** (pass/fail counts, lint result, build result) into the transcript. This printed evidence is what keeps the run judgeable mid-flight and what the `/goal` driver reads to pace itself — but it is *evidence*, not the gate. **Once all three go green, write the tests-ran marker** `{workflow.implementation_artifacts}/.tests-ran-<story_id>` (mirroring `assets/execute-epic.workflow.js` step 3) — the PreToolUse guard denies the step-4 commit unless this marker exists for the current story, so write it only after a real green run.
3. **Production profile only:** `bmad-testarch-test-review`, then `bmad-code-review`. A `CONCERNS`-grade or non-critical finding appends to `{workflow.deferred_work_path}` and the story proceeds. A **P0 / critical FAIL never defers** — re-loop within the turn budget or escalate.
4. **Commit at green** (one commit per green story). The PreToolUse hook blocks a commit on a protected branch and blocks a commit when no "tests-ran" marker exists for the current story, so step 0 must have set the current story and step 2 must have actually run and written `{workflow.implementation_artifacts}/.tests-ran-<story_id>`.

**Sub-skill halt catch-all.** If any orchestrated sub-skill blocks on interactive input mid-run, treat it as escalate for that story — write the escalation marker and stop; do not answer its prompt blind.

### Authoring the `/goal` condition

Wrap the loop in a single `/goal` whose condition is **under 4000 characters** and encodes the per-story Definition-of-Done as the success criterion, with an explicit escape clause. The condition must:

- State the DoD in checkable terms: ATDD acceptance tests for the story un-skipped and **passing**, lint clean, build green, and (production) test-review + code-review passed — mirroring the printed evidence so the transcript-only evaluator can corroborate it.
- Include the literal escape: **"…or stop after {workflow.max_turns_per_story} turns."** This is the in-condition runaway guard. The `budget_stop.py` Stop hook is belt-and-suspenders — it tracks turns/tokens against `{workflow.max_turns_per_story}` / `{workflow.story_token_budget}` and writes an escalation marker when exceeded — but a Stop hook **cannot force `/goal` to halt mid-condition**, so the turn clause inside the condition is the real bound. State it.
- Make explicit that **passing the condition is not completion** — the authoritative verdict is Stage 5's `gate_eval.py`. The `/goal` condition gets a story to a *plausibly* done, evidence-printed state; the gate decides.

Keep it under the character limit by referencing the story's `atdd-checklist` and printed test output rather than restating ACs verbatim.

After the spine finishes (all stories committed-at-green, or a story hit its turn bound and wrote an escalation marker), proceed to Stage 5 for the deterministic per-story and epic-level gate.

## Experimental — `--parallel` worktree fan-out

Only when the user passed `--parallel`. Invoke the saved dynamic workflow `assets/execute-epic.workflow.js` (registered as `/ultracode-goal-execute`) with:

```
args = {
  epic,                       # Epic id
  stories,                    # in-scope story ids/keys, sprint order
  profile,                    # "production" | "light"
  paths: {
    trace_output:           {workflow.trace_output_dir},
    deferred_work:          {workflow.deferred_work_path},
    implementation_artifacts: {workflow.implementation_artifacts},
    tea_config:             {workflow.tea_config_path},
    skill_root:             {skill-root}   # resolved absolute skill dir; the .js has no
                                           # {skill-root} resolver, so it must arrive pre-resolved
  },
  max_concurrency: {workflow.parallel_max_concurrency}
}
```

Pass `paths.skill_root` as the **resolved** `{skill-root}` (the absolute install dir). The workflow runtime executes the `.js` directly and has no `{skill-root}` resolver, so it substitutes this value into the `gate_eval.py` invocations it emits to each subagent; without it the spawned worktree agent receives a literal `{skill-root}` and must guess the script's path.

Each story runs isolated in its own worktree: `bmad-dev-story` (un-skip ATDD) → run tests/lint/build → (production) `bmad-testarch-test-review` → `bmad-code-review` → commit at green → per-story `gate_eval`. After all stories, an epic-level trace gate. The workflow returns `{ perStory: [{story, verdict, gate_status}], epicGate, deferred: […] }`, which feeds Stage 5/6.

**This path is experimental — be explicit about its limits and do not silently rely on it:**

- **No mid-run input.** The fan-out takes no interactive input once launched; every blocker must be resolved at preflight or not at all. This is why launch requires post-remediation budget == 0.
- **Shared Auto Memory.** Concurrent worktrees write to **one** Auto Memory directory — there is no per-worktree isolation of learned facts; expect interleaving.
- **Under-documented interplay.** The workflow↔skill handoff (how args bind, how subagents inherit the allowlist and hooks) is not fully specified by the platform docs; treat its behavior as empirically validated, not guaranteed.
- **No `run-status.json` heartbeat.** Worktree agents cannot reliably write one shared snapshot (each worktree sees its own copy of `{workflow.implementation_artifacts}`), so this path does not write it — progress is watched via the workflow progress view (`/workflows`) and its run log, and the launch briefing says so.

### Graceful degradation

If dynamic workflows are **unavailable** (wrong Claude Code version, workflows feature off, or the saved command does not resolve), **fall back to the sequential `/goal` spine above** and log a one-line note in `.decision-log.md` recording why `--parallel` degraded. The Epic still ships; it just ships sequentially.

## Record

Log to `.decision-log.md`: the path taken (sequential / parallel / degraded-fallback), per-story turn-budget outcomes, every commit-at-green, every deferral appended to `{workflow.deferred_work_path}`, and any escalation marker. The printed test/lint/build evidence stays in the transcript; the decision log carries the durable account across compaction.

## Run-status heartbeat

As the spine advances — each time you move to a new story, log a gate verdict, or spend a re-loop — write `{workflow.implementation_artifacts}/run-status.json` so an automator (or an anxious human) polling a long/headless run has something structured to read instead of prose. Overwrite it in place; it is a single live snapshot, not an append log:

```json
{"epic": "<epic id>",
 "story": "<current story id>",
 "index": <1-based position of the current story>,
 "total": <in-scope story count>,
 "last_verdict": "<advance|defer|reloop|escalate, or null before the first gate>",
 "reloop_count": <re-loops spent so far this run>,
 "profile": "production|light",
 "updated": "<ISO-8601 timestamp>"}
```

This is the file the Stage 2 launch briefing points the operator at ("where to watch"); Stage 6 (finalize) records the terminal state into it when the run closes.
