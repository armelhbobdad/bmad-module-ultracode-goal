## Headless output

In headless (`-H`), compose the final JSON, run the Workflow health check (below) in its unattended queue-only mode, then emit the JSON and stop. `status` is `complete` when the Epic-level gate advanced, or `blocked` when a story escalated. This is the **same five-canonical-key shape every headless exit point honors** (Stage 1 first-touch / already-done blocks, Stage 2 preflight block, and this Stage 6 final emit): the five keys `status`/`skill`/`decision_log`/`report`/`deferred_work` are **always present** (`report` and `deferred_work` `null` when not produced), so a caller parsing them never raises a KeyError. A **complete** emit is those five; a **blocked** exit appends a sixth, `reason` (the one-line cause):

```json
{"status": "complete",
 "skill": "ultracode-goal",
 "decision_log": "<path to this run's .decision-log.md>",
 "report": "<path to run-report.md, or null>",
 "deferred_work": "<path to {workflow.deferred_work_path}, or null>"}
```

A blocked exit (a story escalated) emits the same five keys plus `reason`, with `report`/`deferred_work` `null` — the shape `references/preflight.md` and the `scripts/headless_envelope.py` adapter build (one shared envelope definition).

