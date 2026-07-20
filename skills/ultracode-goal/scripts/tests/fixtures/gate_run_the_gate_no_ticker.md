## Run the gate

Production:

```
uv run {skill-root}/scripts/gate_eval.py --trace-output {workflow.trace_output_dir} --story <story_id> --profile production --nfr {nfr-assessment.md} --test-review {test-review.md}
```

Light:

```
uv run {skill-root}/scripts/gate_eval.py --trace-output {workflow.trace_output_dir} --story <story_id> --profile light
```

Resolve `{nfr-assessment.md}` and `{test-review.md}` to the paths TEA wrote them to (under `{workflow.trace_output_dir}` or the TEA output root); pass the production-only flags only in production. The script reads `gate-decision.json` (resolving its filename from the trace report frontmatter, falling back to the `e2e-trace-summary.json` gate fields when the slim file is absent — that fallback is **not** a failure).

**`--story` in a shared multi-story trace dir.** When every story in a multi-story Epic writes a per-story-named trace report + gate decision (`trace-<id>.md`, `gate-decision-<id>.json`) into the **one** shared `{workflow.trace_output_dir}`, an unscoped read resolves the first/oldest story's gate — a false verdict for every later story. Pass `--story <story_id>` (the id of the story you are gating) so resolution is scoped to that story's artifacts; matching is on id components (`11-6` == `11.6` == `11_6`) anchored to the trailing components, so epic id `1` resolves `trace-1` and never the child story `1-1`'s report. For the **epic-level** gate after the last story, pass the epic's own id the same way (it resolves the epic's `trace-<epic>` report, not any child story). **`--story` fails closed on a genuine no-match — this is a behaviour change.** It used to fall back to the unscoped read whenever nothing matched, which meant a story that wrote *no* artifacts at all silently reported a NEIGHBOURING story's gate as its own: an unevaluated story could read `PASS`/`advance`. Now the fallback depends on how the directory is **named**. If any trace report or gate-decision file there carries a trailing numeric id in its name (`trace-2-1.md`, `gate-decision-4.json` — i.e. the dir is per-story-named), a `--story` that matches nothing means that story is genuinely absent, and the read returns `gate_status: NOT_EVALUATED` -> `escalate`, with a reason naming the story. If instead every candidate is generically named (`trace.md`, `gate-decision.json`), the directory holds one story's artifacts and the documented unscoped fallback still applies, so passing `--story` against a single-story dir resolves exactly as before. `--story` remains optional; omit it only when `{workflow.trace_output_dir}` provably holds a single story's artifacts. If you were relying on the old silent fallback in a per-story-named dir, you will now get an `escalate` instead of a verdict — which is the point: it surfaces a story whose gate was never produced. The experimental `--parallel` workflow (`assets/execute-epic.workflow.js`) shares one `trace_output` across its worktree agents too, so it now passes `--story` per story automatically. If your TEA build does not name artifacts per story, isolate the current story's `trace-*.md` + `gate-decision*.json` into a fresh dir and point `--trace-output` there instead. It returns JSON:

```json
{"verdict": "advance|defer|reloop|escalate",
 "gate_status": "PASS|CONCERNS|FAIL|WAIVED|NOT_EVALUATED",
 "p0_status": "...", "p1_status": "...", "overall_status": "...",
 "nfr_status": "...", "review_score": 0, "reasons": ["..."]}
```

Do not recompute TEA thresholds or re-judge `gate_status` — read it as given. The script already ANDs the production signals (an `advance` is downgraded to `reloop` if `nfr-assessment.md` overallStatus is FAIL, or `test-review.md` score < 80 or recommendation is Block). Record the full verdict JSON and its `reasons` in `.decision-log.md` for this story.

