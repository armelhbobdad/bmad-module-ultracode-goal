# Stage 3 — Define Done

Turn the Epic's acceptance criteria into **executable, red-phase acceptance tests** before any production code is written. The output of this stage is a per-story, machine-checkable Definition-of-Done: a generated `atdd-checklist` plus failing (`test.skip`) acceptance tests that Stage 4 will un-skip and drive to green. Run entirely in `{communication_language}`; TEA-produced documents are written in `{document_output_language}`.

This stage runs only after Stage 2 preflight returns green (intervention budget == 0). Preflight has already scaffolded the test framework (`bmad-testarch-framework`) and generated any missing acceptance criteria (`bmad-create-story`), so the framework is present and every in-scope story has *some* ACs by the time you arrive here. This stage hardens that into per-story executable tests.

## Per Epic — Test Design (once)

Run `bmad-testarch-test-design` in **Epic-Level Mode** for the Epic. This is the risk-and-priority backbone the rest of the run reads from. Its job here:

- **Risk matrix** — genuine risks (not features) with unique IDs, classified by category (TECH / SEC / PERF / DATA / BUS / OPS), each scored probability × impact (1–3 each); score ≥6 is high-priority and must carry a mitigation. This is what `bmad-testarch-trace` later resolves the gate against, so it must exist before Execute.
- **Priority classification P0–P3** — P0 = blocks core flow + high risk + no workaround. The gate Stage 5 reads (`gate_eval.py`) keys P0, P1, and overall thresholds to these priorities; those thresholds are hardcoded in TEA and TEA-owned. Do **not** restate or recompute the percentages; just ensure the test-design assigns the priorities honestly.
- **NFR thresholds** — for every NFR in scope, extract the concrete threshold from PRD / architecture / ADRs / epics / stories. Unknown thresholds are marked `UNKNOWN` and converted into a risk, assumption, or deferred item — **never guessed**. In production these feed `bmad-testarch-nfr` at the gate; a missing threshold that should have a value is a deferral candidate, not a fabrication.

Epic-Level Mode is selected by the presence of `sprint-status.yaml` (preflight reports `sprint_status_present`); if test-design prompts for system-vs-epic, choose **epic**. Force **Create** mode if it offers Resume/Validate/Edit — those are interactive and stall an unattended run.

A `CONCERNS`-grade gap in the test plan (e.g. an `UNKNOWN` NFR threshold that does not block any P0 story) appends to `{workflow.deferred_work_path}` and the Epic keeps moving. A genuine red gap — no risk coverage for a P0 flow — is not deferrable; resolve it before proceeding to per-story work.

## Per Story — Create then ATDD

For every **in-scope** story, in sprint order:

1. **`bmad-create-story`** — produce the dedicated story file with full implementation context and *clear, testable* acceptance criteria. If preflight already generated this story, treat the change request as a refinement, not a re-create. Vague ACs are the single most common cause of the next step halting — sharpen them here.

2. **`bmad-testarch-atdd`** — generate the red-phase acceptance test scaffolds for that story. This writes:
   - `atdd-checklist-{story_key}.md` under the TEA test-artifacts directory — the per-story checklist mapping each AC to its planned test(s).
   - The acceptance test files themselves, **every test marked `test.skip()`** (TDD red phase). ATDD verifies this and errors if any generated test is not skipped — that is correct and expected; the tests are *supposed* to fail/skip until Stage 4 implements the feature and un-skips them.

   `bmad-testarch-atdd` **HARD HALTS** if the story lacks clear acceptance criteria or the framework is not configured. Both are preconditions this stage's step 1 and Stage 2 preflight exist to satisfy — if atdd halts anyway, the story's ACs are still too vague: loop back to `bmad-create-story` for that story and re-run atdd. Do not hand a story to Execute with a halted or absent atdd-checklist.

   Force **Create** mode (not Resume/Validate/Edit) for the same unattended reason.

## Exit condition (testable)

Stage 3 is complete, and Stage 4 may begin, when **all three** hold:

- The Epic has a `bmad-testarch-test-design` plan with a populated risk matrix, P0–P3 priorities assigned, and every in-scope NFR threshold either resolved or explicitly marked `UNKNOWN`/deferred.
- **Every in-scope story** has a story file with clear acceptance criteria.
- **Every in-scope story** has a generated `atdd-checklist-{story_key}.md` and red-phase (`test.skip`) acceptance tests on disk.

If any in-scope story is missing its atdd-checklist, this stage is not done — Execute has nothing executable to drive that story to. Record in `.decision-log.md`: the test-design verdict, each story's AC + checklist status, and any deferral appended to `{workflow.deferred_work_path}`.
