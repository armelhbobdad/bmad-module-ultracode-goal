# Stage 5 — Gate

**Goal:** Decide whether a completed story (or, after the last story, the Epic) advances — by a deterministic artifact read, not by judgment. `scripts/gate_eval.py` reads TEA's `gate-decision.json` and returns a routing verdict. You execute the route. Converse in `{communication_language}`; the deferred-work ledger is written in `{document_output_language}`.

This is the completion authority. The `/goal` evaluator only sees the transcript; it cannot read the gate file. Never substitute your own read of "the tests look green" or the evaluator's transcript-only verdict for this script. The JSON is the truth.

## Backfill the gate evidence (production only)

The gate reads artifacts TEA produces. In **production**, before running the gate, make the evidence current. **The only ordering constraint is `bmad-testarch-automate` → `bmad-testarch-trace`** — trace reads the coverage automate backfills, so that pair runs in series:

1. `bmad-testarch-automate` — backfill coverage for code that landed during Execute, **then**
2. `bmad-testarch-trace` — (re)build the traceability matrix and write the gate decision.

`bmad-testarch-nfr` (produces `nfr-assessment.md`) and `bmad-testarch-test-review` are independent — of each other *and* of the automate→trace chain — so run them in any order, or concurrently with it; `gate_eval.py` consumes all three artifacts without caring how they were produced. (`bmad-testarch-test-review` normally runs in Execute per story — run it here only if you lack a current `test-review.md` for the story.) In **`--light`**, skip all of the above and run only `bmad-testarch-trace`, then the gate with `--profile light` (trace gate only — no NFR/review AND).

## Non-web stack (web-only TEA chain): author the deterministic trace artifacts

When the module's TEA chain is web-only, `bmad-testarch-trace` cannot run on a non-web stack and so cannot emit the binding gate decision. Do **not** reverse-engineer a prior run's leftover artifacts — author the two files to the exact shape `scripts/gate_eval.py` reads; every other field in real TEA output (`target`, `links`/`trace_report_path`, `rationale`, `schema_version`) is decoration the reader never touches. **Name all four for the story** — `trace-<id>.md`, `gate-decision-<id>.json`, and on the production path `nfr-assessment-<id>.md` and `test-review-<id>.md`. The first pair must be per-story because `--story <id>` scoping resolves them by name in a shared `--trace-output` dir. The second pair binds nothing mechanically (the `--nfr` / `--test-review` flags take an explicit path), which is exactly why it needs stating: unnamed, each story's NFR and review overwrite the last one's in that shared directory, and the audit trail keeps only whichever story finished most recently.

**`trace-<id>.md`** — only the frontmatter is read (the body is human prose). The resolver needs exactly two keys:

```yaml
---
workflowType: testarch-trace              # must be 'testarch-trace' or 'trace', else the report is skipped
gateDecisionFile: gate-decision-<id>.json # the slim file to read; a bare filename in --trace-output
---
```

**The hint is bounded, and a hint it refuses is not fatal.** `gateDecisionFile` must name a file sitting **directly in `--trace-output`**: a bare filename, never a subdirectory, never a `..` path and never an absolute path (a hint that resolves outside the artifact directory is ignored, because a gate read from outside the directory the run was pointed at is not this run's gate). When the hint carries a story id it must be **this** story's; when it carries none, it is honoured only where no other story's artifact is present. A refused hint does not fail the story on its own: resolution continues to `gate-decision-<story_id>.json` and then to the same fail-closed rule an artifact-less story gets.

**`gate-decision-<id>.json`** — the slim file the hint points at. `gate_eval.py` reads only these four keys; `gate_status` alone drives the `--light` verdict (PASS/WAIVED → advance, CONCERNS → defer, FAIL → reloop, NOT_EVALUATED → escalate), the other three are passed through into the verdict JSON / `.decision-log.md`:

```json
{ "gate_status": "PASS", "p0_status": "MET", "p1_status": "MET", "overall_status": "MET" }
```

Write a PASS only when the story is demonstrably done to its profile's Definition-of-Done (under `--light`: acceptance criteria satisfied with lint and build green; under production the bar is higher — also un-skipped passing acceptance tests plus test-review/code-review, per the profile note below — see `references/define-done.md`); a non-green story is `reloop`/`escalate`, never a hand-authored PASS (see the INVARIANT in "Route on the verdict"). `p0_status`/`p1_status`/`overall_status` are passthrough-only here — they do not drive the `--light` verdict, so write them to reflect reality, never to dress up a non-green story. If you instead write the always-present `e2e-trace-summary.json`, the reader takes its top-level `gate_status` and the nested `gate_criteria.{p0_status,p1_status,overall_status}` — the same fields one level down.

**Which profile's gate you then run.** The hand-authored trace decision above is the same file for either profile; only what you AND onto it differs. Under **`--light`** it *is* the whole gate — run `gate_eval.py --profile light` (below) and stop. Under **production** — the legitimate case when an operator scopes foundational, non-web packages to the full chain — the production ANDs still apply. TEA's *browser* generators are what a non-web stack cannot run as-is: ATDD in Stage 3 and the automate→trace pair here. So the story's acceptance tests are authored and driven in the stack's own harness (the Vitest case) and reach the production Definition-of-Done un-skipped and passing, and you hand-author the trace decision above in place of automate→trace.

**A production story on this path owes five deliverables.** (A `--light` story owes two of them — items 1 and 5: the trace decision *is* its whole gate, and provenance is logged whichever profile you land in.) Each is independently checkable and each has been independently dropped by a run that complied with the rest — so they are numbered rather than prosed, and a production story is done with this section only when all five exist:

1. **The hand-authored trace decision** — the two files above, in place of automate→trace.
2. **The red phase is established BY HAND, and it must still be established.** Where ATDD cannot generate the `test.skip()` scaffold: author the acceptance cases with real assertions and RUN them before the first implementation edit — the window this rule governs closes in Stage 4, which is why `references/execute.md` step 1 states the same obligation where the first-edit decision is actually made. This section otherwise rules the artifacts thoroughly and the acceptance-test BAR ("un-skipped and passing") while saying nothing about how un-skipped is reached from a red start — so a run that skipped the red phase entirely satisfies every other sentence here. **A case nobody ever saw fail is not evidence**, and a hand-authored PASS resting on one is the same dishonesty the hand-authored-PASS rule above forbids.
3. **Capture that run's raw output to a file** under `{workflow.implementation_artifacts}`. An independent deliverable, not a detail of item 2: the capture is what makes the red phase auditable after the fact, and it cannot be honestly re-made once the implementation lands — a run that ran the red phase and read the result but captured nothing holds strictly weaker evidence than this item asks for, and a labelled transcription is the most it can honestly write.
4. **The red count recorded in the trace report, with a one-line justification for every case that was already green.** Where a shared acceptance file accumulates already-shipped siblings' cases, those green-by-design cases may be justified as one line naming that class rather than case-by-case — the per-case justification owed is for THIS story's cases that never went red.
5. **`gate-provenance: hand-authored`, logged per story** exactly as "Run the gate" below requires — a run that takes this branch on every row produces an Epic whose every verdict rests on a file the run wrote for itself, and nothing else in the artifacts would say so.

`bmad-testarch-nfr` and `bmad-testarch-test-review` are independent of that browser pair (see "Backfill the gate evidence" above), so still produce `nfr-assessment.md` and `test-review.md` the normal way and run `gate_eval.py --profile production --story <story_id> --nfr <…/nfr-assessment-<story_id>.md> --test-review <…/test-review-<story_id>.md>`. Pass **both** flags. `gate_eval.py` fail-closes a `--nfr`/`--test-review` path that is given-but-missing **and one you simply omit**: an omitted flag on a per-story production gate is itself a failing signal, with a reason naming the flag. That is deliberate — a forgotten flag used to be skipped in silence, so the AND never ran, the field rendered `null`, and the verdict was computed without it, which bought a *higher* verdict than supplying a failing artifact would have. If a signal genuinely cannot be produced on the stack, that is a CONCERNS/`defer` or a `reloop`, never a dropped flag. The one legitimate omission is the epic roll-up, which declares itself with `--epic-level` (see "Route on the verdict") rather than by leaving the flags off. A stack that cannot meet the production acceptance-test bar at all belongs under `--light` (see the framework fitness caveat in `references/preflight.md`), not a hand-waved production PASS. The honesty bar is unchanged: a PASS requires full AC coverage by passing tests, never to dodge an AND.

**The epic-level roll-up needs the same hand-authoring, named for the EPIC.** Everything above is written per story, and on this stack TEA never runs — so nothing ever writes the epic's own `trace-<epic>.md`, while the epic-level gate below presumes it exists: `--story <epic_id>` in a per-story-named directory resolves nothing and fail-closes a completed Epic to `escalate`. When every story is `done`, hand-author the same two files named for the epic id — `trace-<epic>.md`, its frontmatter pointing at `gate-decision-<epic>.json` — with a `gate_status` that honestly summarises the per-story record: a PASS only when every story advanced, never a roll-up dressed over a story that did not. It takes no NFR and no test-review; the roll-up declares that omission with `--epic-level`, per "Route on the verdict" below.

**Hand-authored `nfr-assessment.md` and `test-review.md` shapes (production path only).** `gate_eval.py` scans these two files with the *same* parser it uses on real TEA output, so a hand- or agent-authored file must carry the exact fields below — otherwise the scanner reads the signal as *not found* and, under the fail-closed contract, treats it as **failing**, spuriously downgrading an `advance` to `reloop`. (Under `--light` neither file is read, so this whole block is production-only.) Only the named field is parsed; everything else is human prose.

`nfr-assessment.md` — the reader needs one field:

```markdown
**Overall Status:** PASS
```

`PASS` | `CONCERNS` | `FAIL` | `NOT_ASSESSED` (the key may also be written `overallStatus:`). A `FAIL`, a `NOT_ASSESSED`, or a status the scanner cannot find all downgrade `advance`→`reloop`. `NOT_ASSESSED` is listed because TEA emits it and the scanner recognises it: it parses cleanly, so it never reaches the cannot-find branch, and it means the NFRs were never evaluated — strictly weaker evidence than a file the reader cannot parse, which already fails closed. Write it honestly rather than reaching for `CONCERNS` to keep a story moving; `CONCERNS` is a `defer` and claims the NFRs *were* assessed.

`test-review.md` — the reader needs two fields:

```markdown
**Quality Score**: 89/100
**Recommendation**: Approve
```

The score **must** carry the `/100` denominator: a bare `score: 89` matches nothing, is read as *not found*, and fail-closes to `reloop` — always write it as `N/100` (a `Quality Score` label or a bare `score` both parse, but only with `/100`). `Recommendation` ∈ `Approve` | `Approve with Comments` | `Request Changes` | `Block`; a `Block`, or a score `< 80`, downgrades `advance`→`reloop`.

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

**`--story` in a shared multi-story trace dir.** When every story in a multi-story Epic writes a per-story-named trace report + gate decision (`trace-<id>.md`, `gate-decision-<id>.json`) into the **one** shared `{workflow.trace_output_dir}`, an unscoped read resolves the first/oldest story's gate — a false verdict for every later story. Pass `--story <story_id>` (the id of the story you are gating) so resolution is scoped to that story's artifacts; matching is on id components (`11-6` == `11.6` == `11_6`) anchored to the trailing components, so epic id `1` resolves `trace-1` and never the child story `1-1`'s report. **`<story_id>` is ONE string, used byte-identically in three places:** the story's `sprint-status.yaml` key, the `<id>` in the artifact filenames above (`trace-<id>.md`, `gate-decision-<id>.json`, and the same `<id>` in the per-story NFR and test-review names the non-web section below pins), and this `--story` argument. Copy the key verbatim, whether it is bare (`4-2`) or carries a kebab title slug (`4-2-<kebab-title>`); do not abbreviate it to its number when invoking, and do not expand it when naming. When TEA authored the files, take the id portion of the stem it actually wrote and pass that. **A mismatch fails in both directions**: `--story 4-2-<kebab-title>` resolves `gate-decision-4-2-<kebab-title>.json` and *not* `gate-decision-4-2.json`, and `--story 4-2` resolves neither. The tolerance is deliberately no wider than this — matching is anchored to the trailing components on purpose, because a prefix match would let epic id `4` resolve `trace-4-2-<kebab-title>.md` and hand the epic roll-up a child story's verdict, which is the fail-open the anchor exists to close. **Recognise the symptom:** a spelling mismatch surfaces as `gate_status: NOT_EVALUATED` -> `escalate`, worded identically to a story that genuinely wrote nothing, so before treating that `escalate` as a real block, list `{workflow.trace_output_dir}` and compare the exact stem. For the **epic-level** gate after the last story, pass the epic's own id the same way (it resolves the epic's `trace-<epic>` report, not any child story). **`--story` fails closed on a genuine no-match — this is a behaviour change.** It used to fall back to the unscoped read whenever nothing matched, which meant a story that wrote *no* artifacts at all silently reported a NEIGHBOURING story's gate as its own: an unevaluated story could read `PASS`/`advance`. Now the fallback depends on how the directory is **named**. If any trace report or gate-decision file there carries a trailing numeric id in its name (`trace-2-1.md`, `gate-decision-4.json` — i.e. the dir is per-story-named), a `--story` that matches nothing means that story is genuinely absent, and the read returns `gate_status: NOT_EVALUATED` -> `escalate`, with a reason naming the story. If instead every candidate is generically named (`trace.md`, `gate-decision.json`), the directory holds one story's artifacts and the documented unscoped fallback still applies, so passing `--story` against a single-story dir resolves exactly as before. `--story` remains optional; omit it only when `{workflow.trace_output_dir}` provably holds a single story's artifacts. If you were relying on the old silent fallback in a per-story-named dir, you will now get an `escalate` instead of a verdict — which is the point: it surfaces a story whose gate was never produced. If your TEA build does not name artifacts per story, isolate the current story's `trace-*.md` + `gate-decision*.json` into a fresh dir and point `--trace-output` there instead. It returns JSON:

```json
{"verdict": "advance|defer|reloop|escalate",
 "gate_status": "PASS|CONCERNS|FAIL|WAIVED|NOT_EVALUATED",
 "p0_status": "...", "p1_status": "...", "overall_status": "...",
 "nfr_status": "...", "review_score": 0, "reasons": ["..."]}
```

Do not recompute TEA thresholds or re-judge `gate_status` — read it as given. The script already ANDs the production signals (an `advance` is downgraded to `reloop` if `nfr-assessment.md` overallStatus is FAIL, or `test-review.md` score < 80 or recommendation is Block). Record the full verdict JSON and its `reasons` in `.decision-log.md` for this story.

**Record who authored the artifacts the verdict rests on.** Alongside that JSON, log one line naming the provenance of this story's `trace-<id>.md` / `gate-decision-<id>.json`: **`gate-provenance: tea`** when `bmad-testarch-trace` wrote them, or **`gate-provenance: hand-authored`** when the non-web section above did. This is not bookkeeping. The module's central non-negotiable is that completion is decided by a script reading TEA's artifact rather than by the model's judgment, and on the hand-authored path the model *writes the file the gate then reads* — a defensible substitution the non-web section sanctions, but one that is otherwise **indistinguishable** in the decision log and the run report from a verdict grounded in a TEA-authored gate. An Epic can run to completion entirely on the hand-authored path, story after story, with nothing anywhere recording that it did. Provenance is what keeps "the JSON is the truth" honest about *whose* JSON it was; it changes no verdict and gates nothing.

**Attended runs also print the verdict, once.** In an attended run, immediately after `gate_eval.py` returns and alongside the `.decision-log.md` record above, print **exactly one** transcript line for this story — `story 4-2 — gate_status PASS — verdict advance` — carrying the story id, the `gate_status`, and the routing verdict. The line fires at the moment the verdict is formed, not on the heartbeat cadence: **one line per story, per gate evaluation**, so a watching human sees every story's completion decision without opening a file, and a re-looped story prints its own line for its second evaluation rather than restating the first. Skip this print in headless (`-H`): there the artifacts and `run-result.json` are the interface, and transcript prose has no reader. The line is **additive to the `.decision-log.md` record and never a substitute for it** — the recorded JSON is the completion evidence, a transcript line is not, and a reader who treats the line as the record has lost the `reasons`.

## Route on the verdict

- **`advance`** (gate_status PASS or WAIVED) → the story passes. **Sync the story's row in `sprint-status.yaml` to `done` before moving on** — set `development_status[<story_id>]` to `done`, preserving the file's comments and key order, and log the transition in `.decision-log.md`. This write is the run's own, not a sub-skill's: `bmad-dev-story` leaves the row at `review`, and `bmad-code-review` (production only — it does not run under `--light` at all) writes `done` **only** when nothing was left as an action item, so a story that legitimately `defer`s a non-critical finding is left at `in-progress`. Every downstream reader keys on `done` — Stage 1's in-scope rule (`references/ingest-and-scope.md` rule 3), the Epic-level trigger in this very sentence, and `scripts/drive_epic.py`'s progress check — so an advanced story whose row still says `review` is an advanced story the next reader re-drives, and an Epic whose last story advanced without this write never satisfies the Epic-level condition below. Sync it here, at the one place the authoritative verdict is known. Then move to the next story. When **every story of the Epic is `done`**, run the Epic-level **trace** gate: pass the epic's own id via `--story` (scoped per the `--story` note above), **add `--epic-level`**, and read its `gate_status` **only**. TEA produces NFR and test-review **per story, not per epic**, so there is no epic-level aggregate to AND, and every story's own production gate already ANDed its signals before reaching `done`; the epic roll-up is a pure trace read.

```
uv run {skill-root}/scripts/gate_eval.py --trace-output {workflow.trace_output_dir} --story <epic_id> --profile production --epic-level
```

**Declare the omission; do not imply it.** `--epic-level` is what makes the skipped ANDs correct rather than the signal-dropping the per-story gate forbids in "Run the gate". The two used to be the same input — leaving the flags off — so a forgotten flag on a story gate was indistinguishable from a legitimate epic roll-up, and the story gate silently advanced on a signal nobody read. Without the flag, `--profile production` now treats an absent `--nfr`/`--test-review` as failing. Passing an epic-level `--test-review`/`--nfr` path that no aggregate writes is the mirror mistake: it gets "test-review file … not found; treated as failing" and spuriously downgrades an epic PASS to `reloop`. Under `--profile light` the flag is a no-op, since that profile runs no ANDs at all. Then proceed to Stage 6 (`references/finalize.md`). **Partial-by-design exception:** if this run delivered only a deliberate *strict subset* of the Epic's stories (in-scope ⊊ Epic — e.g. a conditional / evidence-gated Epic where the operator scoped a subset; this is distinct from ingest-and-scope.md's already-`done`-skipping, which still ends with every story `done`) — do **not** author an Epic-level gate: a PASS would misrepresent an incomplete Epic as complete. Record the per-story advance(s) and proceed to Stage 6 with the Epic left in its partial / conditional state (the `partial-complete` terminal outcome — see `references/finalize.md`).

- **`defer`** (gate_status CONCERNS, or non-critical code-review / NFR findings that did not flip the gate) → append the open items to the ledger at `{workflow.deferred_work_path}` using the schema below, then **advance** anyway. The Epic keeps moving; the parked work is visible.

- **`reloop`** (gate_status FAIL, or a production signal downgraded an advance) → run `bmad-correct-course` to diagnose and adjust, then re-run the story (back through Execute, `references/execute.md`) — **within the remaining turn budget**. Re-run the gate after. If the re-loop would exceed `{workflow.max_turns_per_story}`, treat it as `escalate` instead.

- **`escalate`** (gate_status NOT_EVALUATED — the gate could not be read — or budget exhausted on a FAIL) → **stop.** Do not advance, do not defer the failing item. Record the reason and the verdict JSON in `.decision-log.md`, and write the typed escalation sidecar `{workflow.implementation_artifacts}/escalation-<story_id>.json` (shape in `references/execute.md`, under "Escalation sidecar") so the pending decision is readable without the transcript. In an attended run, surface the blocker to the user. In headless, this is a `blocked` outcome — emit the JSON in Stage 6 (`references/finalize.md`).

**INVARIANT — a P0/critical FAIL never defers.** A failing gate (or a P0/P1/overall threshold miss) is `reloop` or `escalate`, never `defer`. Only non-gate-blocking work (CONCERNS, non-critical findings, parked decisions) is allowed onto the ledger. If you find yourself about to write a FAIL or a critical finding to the ledger, you are violating the gate — re-loop within budget or escalate instead.

If any orchestrated sub-skill blocks on interactive input mid-run, treat it as `escalate` for that story — write the typed escalation sidecar `{workflow.implementation_artifacts}/escalation-<story_id>.json` and stop; do not answer its prompt blind.

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
