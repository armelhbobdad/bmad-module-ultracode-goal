# Stage 5 — Gate

**Goal:** Decide whether a completed story (or, after the last story, the Epic) advances — by a deterministic artifact read, not by judgment. `scripts/gate_eval.py` reads TEA's `gate-decision.json` and returns a routing verdict. You execute the route. Converse in `{communication_language}`; the deferred-work ledger is written in `{document_output_language}`.

This is the completion authority. The `/goal` evaluator only sees the transcript; it cannot read the gate file. Never substitute your own read of "the tests look green" or the evaluator's transcript-only verdict for this script. The JSON is the truth.

## Backfill the gate evidence (production only)

The gate reads artifacts TEA produces. In **production**, before running the gate, make the evidence current. **The only ordering constraint is `bmad-testarch-automate` → `bmad-testarch-trace`** — trace reads the coverage automate backfills, so that pair runs in series:

1. `bmad-testarch-automate` — backfill coverage for code that landed during Execute, **then**
2. `bmad-testarch-trace` — (re)build the traceability matrix and write the gate decision.

`bmad-testarch-nfr` (produces `nfr-assessment.md`) and `bmad-testarch-test-review` are independent — of each other *and* of the automate→trace chain — so run them in any order, or concurrently with it; `gate_eval.py` consumes all three artifacts without caring how they were produced. (`bmad-testarch-test-review` normally runs in Execute per story — run it here only if you lack a current `test-review.md` for the story.) In **`--light`**, skip all of the above and run only `bmad-testarch-trace`, then the gate with `--profile light` (trace gate only — no NFR/review AND).

## Non-web stack (web-only TEA chain): author the deterministic trace artifacts

When the module's TEA chain is web-only, `bmad-testarch-trace` cannot run on a non-web stack and so cannot emit the binding gate decision. Do **not** reverse-engineer a prior run's leftover artifacts — author the two files to the exact shape `scripts/gate_eval.py` reads; every other field in real TEA output (`target`, `links`/`trace_report_path`, `rationale`, `schema_version`) is decoration the reader never touches. Name both for the story (`trace-<id>.md`, `gate-decision-<id>.json`) so `--story <id>` scoping resolves them in a shared `--trace-output` dir.

**`trace-<id>.md`** — only the frontmatter is read (the body is human prose). The resolver needs exactly two keys:

```yaml
---
workflowType: testarch-trace              # must be 'testarch-trace' or 'trace', else the report is skipped
gateDecisionFile: gate-decision-<id>.json # the slim file to read; relative to --trace-output (absolute honored)
---
```

**`gate-decision-<id>.json`** — the slim file the hint points at. `gate_eval.py` reads only these four keys; `gate_status` alone drives the `--light` verdict (PASS/WAIVED → advance, CONCERNS → defer, FAIL → reloop, NOT_EVALUATED → escalate), the other three are passed through into the verdict JSON / `.decision-log.md`:

```json
{ "gate_status": "PASS", "p0_status": "MET", "p1_status": "MET", "overall_status": "MET" }
```

Write a PASS only when the story is demonstrably done to its profile's Definition-of-Done (under `--light`: acceptance criteria satisfied with lint and build green; under production the bar is higher — also un-skipped passing acceptance tests plus test-review/code-review, per the profile note below — see `references/define-done.md`); a non-green story is `reloop`/`escalate`, never a hand-authored PASS (see the INVARIANT in "Route on the verdict"). `p0_status`/`p1_status`/`overall_status` are passthrough-only here — they do not drive the `--light` verdict, so write them to reflect reality, never to dress up a non-green story. If you instead write the always-present `e2e-trace-summary.json`, the reader takes its top-level `gate_status` and the nested `gate_criteria.{p0_status,p1_status,overall_status}` — the same fields one level down.

**Which profile's gate you then run.** The hand-authored trace decision above is the same file for either profile; only what you AND onto it differs. Under **`--light`** it *is* the whole gate — run `gate_eval.py --profile light` (below) and stop. Under **production** — the legitimate case when an operator scopes foundational, non-web packages to the full chain — the production ANDs still apply. TEA's *browser* generators are what a non-web stack cannot run as-is: ATDD in Stage 3 and the automate→trace pair here. So the story's acceptance tests are authored and driven in the stack's own harness (the Vitest case) and reach the production Definition-of-Done un-skipped and passing, and you hand-author the trace decision above in place of automate→trace. `bmad-testarch-nfr` and `bmad-testarch-test-review` are independent of that browser pair (see "Backfill the gate evidence" above), so still produce `nfr-assessment.md` and `test-review.md` the normal way and run `gate_eval.py --profile production --story <story_id> --nfr … --test-review …`. Pass **both** flags: `gate_eval.py` fail-closes a `--nfr`/`--test-review` path that is given-but-missing, but a flag you simply *omit* is silently skipped and its AND quietly dropped — so omitting them on a production run inflates the gate by losing a signal, the same dishonesty the hand-authored-PASS rule forbids. If a signal genuinely cannot be produced on the stack either, that is a CONCERNS/`defer` or a `reloop`, never a dropped flag. A stack that cannot meet the production acceptance-test bar at all belongs under `--light` (see the framework fitness caveat in `references/preflight.md`), not a hand-waved production PASS. The honesty bar is unchanged: a PASS requires full AC coverage by passing tests, never to dodge an AND.

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

**`--story` in a shared multi-story trace dir.** When every story in a multi-story Epic writes a per-story-named trace report + gate decision (`trace-<id>.md`, `gate-decision-<id>.json`) into the **one** shared `{workflow.trace_output_dir}`, an unscoped read resolves the first/oldest story's gate — a false verdict for every later story. Pass `--story <story_id>` (the id of the story you are gating) so resolution is scoped to that story's artifacts; matching is on id components (`11-6` == `11.6` == `11_6`) anchored to the trailing components, so epic id `1` resolves `trace-1` and never the child story `1-1`'s report. For the **epic-level** gate after the last story, pass the epic's own id the same way (it resolves the epic's `trace-<epic>` report, not any child story). `--story` is optional and backward-compatible: a no-match falls back to the unscoped read, so omit it only when `{workflow.trace_output_dir}` provably holds a single story's artifacts. The experimental `--parallel` workflow (`assets/execute-epic.workflow.js`) shares one `trace_output` across its worktree agents too, so it now passes `--story` per story automatically. If your TEA build does not name artifacts per story, isolate the current story's `trace-*.md` + `gate-decision*.json` into a fresh dir and point `--trace-output` there instead. It returns JSON:

```json
{"verdict": "advance|defer|reloop|escalate",
 "gate_status": "PASS|CONCERNS|FAIL|WAIVED|NOT_EVALUATED",
 "p0_status": "...", "p1_status": "...", "overall_status": "...",
 "nfr_status": "...", "review_score": 0, "reasons": ["..."]}
```

Do not recompute TEA thresholds or re-judge `gate_status` — read it as given. The script already ANDs the production signals (an `advance` is downgraded to `reloop` if `nfr-assessment.md` overallStatus is FAIL, or `test-review.md` score < 80 or recommendation is Block). Record the full verdict JSON and its `reasons` in `.decision-log.md` for this story.

## Route on the verdict

- **`advance`** (gate_status PASS or WAIVED) → the story passes. Move to the next story. When **every story of the Epic is `done`**, run the Epic-level trace gate the same way, then proceed to Stage 6 (`references/finalize.md`). **Partial-by-design exception:** if this run delivered only a deliberate *strict subset* of the Epic's stories (in-scope ⊊ Epic — e.g. a conditional / evidence-gated Epic where the operator scoped a subset; this is distinct from ingest-and-scope.md's already-`done`-skipping, which still ends with every story `done`) — do **not** author an Epic-level gate: a PASS would misrepresent an incomplete Epic as complete. Record the per-story advance(s) and proceed to Stage 6 with the Epic left in its partial / conditional state (the `partial-complete` terminal outcome — see `references/finalize.md`).

- **`defer`** (gate_status CONCERNS, or non-critical code-review / NFR findings that did not flip the gate) → append the open items to the ledger at `{workflow.deferred_work_path}` using the schema below, then **advance** anyway. The Epic keeps moving; the parked work is visible.

- **`reloop`** (gate_status FAIL, or a production signal downgraded an advance) → run `bmad-correct-course` to diagnose and adjust, then re-run the story (back through Execute, `references/execute.md`) — **within the remaining turn/token budget**. Re-run the gate after. If the re-loop would exceed `{workflow.max_turns_per_story}` or `{workflow.story_token_budget}`, treat it as `escalate` instead.

- **`escalate`** (gate_status NOT_EVALUATED — the gate could not be read — or budget exhausted on a FAIL) → **stop.** Do not advance, do not defer the failing item. Record the reason and the verdict JSON in `.decision-log.md`. In an attended run, surface the blocker to the user. In headless, this is a `blocked` outcome — emit the JSON in Stage 6 (`references/finalize.md`).

**INVARIANT — a P0/critical FAIL never defers.** A failing gate (or a P0/P1/overall threshold miss) is `reloop` or `escalate`, never `defer`. Only non-gate-blocking work (CONCERNS, non-critical findings, parked decisions) is allowed onto the ledger. If you find yourself about to write a FAIL or a critical finding to the ledger, you are violating the gate — re-loop within budget or escalate instead.

If any orchestrated sub-skill blocks on interactive input mid-run, treat it as `escalate` for that story — write the escalation marker and stop; do not answer its prompt blind.

## Deferred-work ledger schema

Append to `{workflow.deferred_work_path}` (create on first use). One heading per Epic, then a row per parked item; `status` is `open` at write time:

```markdown
# Deferred Work — <epic>

| id | source | severity | story | reason | suggested_action | status |
|----|--------|----------|-------|--------|------------------|--------|
| d1 | gate | low | <story-id> | <why parked> | <what to do later> | open |
```

- `source` ∈ `gate` (CONCERNS), `code-review` (non-critical finding), `nfr` (non-FAIL finding), `decision` (parked decision).
- `severity` ∈ `low`, `med`, `high`. A `high` that maps to a gate FAIL or a P0/critical finding does **not** belong here — re-loop or escalate it.
- `id` is unique within the Epic heading (append `d2`, `d3`, … ); never rewrite existing rows.
