# Stage 5 — Gate

**Goal:** Decide whether a completed story (or, after the last story, the Epic) advances — by a deterministic artifact read, not by judgment. `scripts/gate_eval.py` reads TEA's `gate-decision.json` and returns a routing verdict. You execute the route. Converse in `{communication_language}`; the deferred-work ledger is written in `{document_output_language}`.

This is the completion authority. The `/goal` evaluator only sees the transcript; it cannot read the gate file. Never substitute your own read of "the tests look green" or the evaluator's transcript-only verdict for this script. The JSON is the truth.

## Backfill the gate evidence (production only)

The gate reads artifacts TEA produces. In **production**, before running the gate, generate the evidence in order so the gate has something current to read:

1. `bmad-testarch-automate` — backfill coverage for code that landed during Execute.
2. `bmad-testarch-trace` — (re)build the traceability matrix and write the gate decision.
3. `bmad-testarch-nfr` — audit NFR evidence; produces `nfr-assessment.md`.

`bmad-testarch-test-review` runs in Execute per story; if you do not have a current `test-review.md` for the story, run it now too. In **`--light`**, skip all of the above and run only `bmad-testarch-trace`, then the gate with `--profile light` (trace gate only — no NFR/review AND).

## Run the gate

Production:

```
uv run {skill-root}/scripts/gate_eval.py --trace-output {workflow.trace_output_dir} --profile production --nfr {nfr-assessment.md} --test-review {test-review.md}
```

Light:

```
uv run {skill-root}/scripts/gate_eval.py --trace-output {workflow.trace_output_dir} --profile light
```

Resolve `{nfr-assessment.md}` and `{test-review.md}` to the paths TEA wrote them to (under `{workflow.trace_output_dir}` or the TEA output root); pass the production-only flags only in production. The script reads `gate-decision.json` (resolving its filename from the trace report frontmatter, falling back to the `e2e-trace-summary.json` gate fields when the slim file is absent — that fallback is **not** a failure). It returns JSON:

```json
{"verdict": "advance|defer|reloop|escalate",
 "gate_status": "PASS|CONCERNS|FAIL|WAIVED|NOT_EVALUATED",
 "p0_status": "...", "p1_status": "...", "overall_status": "...",
 "nfr_status": "...", "review_score": 0, "reasons": ["..."]}
```

Do not recompute TEA thresholds or re-judge `gate_status` — read it as given. The script already ANDs the production signals (an `advance` is downgraded to `reloop` if `nfr-assessment.md` overallStatus is FAIL, or `test-review.md` score < 80 or recommendation is Block). Record the full verdict JSON and its `reasons` in `.decision-log.md` for this story.

## Route on the verdict

- **`advance`** (gate_status PASS or WAIVED) → the story passes. Move to the next story; when the last story passes, run the Epic-level trace gate the same way, then proceed to Stage 6 (`references/finalize.md`).

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
