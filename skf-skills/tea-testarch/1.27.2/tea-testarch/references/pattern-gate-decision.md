# Trace and the gate decision (bmad-testarch-trace)

## Contents

- [Inputs](#inputs)
- [Outputs](#outputs)
- [Steps and modes](#steps-and-modes)
- [Gate eligibility](#gate-eligibility)
- [Decision rules](#decision-rules)
- [Overlays that tighten a PASS](#overlays-that-tighten-a-pass)
- [Waivers](#waivers)
- [gate-decision.json contract](#gate-decisionjson-contract)
- [e2e-trace-summary.json](#e2e-trace-summaryjson)
- [HALT conditions](#halt-conditions)

## Inputs

Every variable resolves from `{project-root}/_bmad/tea/config.yaml` or from `workflow.yaml` defaults. [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L7]

| Variable | Default | Meaning |
|----------|---------|---------|
| `test_artifacts` | TEA config key | Root for every trace output [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L9] |
| `project_name` | core config | Emitted as `repo` in both JSON outputs [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L11] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L615] |
| `test_dir` | `{project-root}/tests` | Where tests are discovered [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L25] |
| `live_results_input` | `{test_artifacts}/live-verification-results.json` | Optional recorded runtime verification, counted as `live` evidence [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L27] |
| `waiver_register_input` | `{test_artifacts}/gate-waivers.md` | Optional human-authored waiver register; validated, never applied [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L28] [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L85] |
| `coverage_levels` | `e2e,api,component,unit,live` | Test levels traced [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L31] |
| `gate_type` | `story` | `story`, `epic`, `release` or `hotfix` [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L32] |
| `decision_mode` | `deterministic` | `deterministic` (rule-based) or `manual` (team decision) [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L33] |
| `collection_mode` | `contract_static` | also `inventory_only`, `runtime_manifest`, `deferred_shared`, `waived`, `restricted`, `inaccessible` [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L34] |
| `allow_gate` | `true` | Emit `gate_status` and `gate-decision.json` only when gate-eligible [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L35] |
| `coverage_basis` | `auto` | Step 1 must persist a concrete basis [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L36] |
| `summary_confidence` | `auto` | Step 1 must persist a concrete value [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L37] |

Live results count as coverage only with a unique id, a known `requirement_id`, status `pass` and a `source_sha` equal to the traced commit; a different major `schema_version` makes the file unreadable. [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L80] [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L74] Under `collection_mode: runtime_manifest` test discovery is skipped and a missing or unreadable results file makes `collection_status` `INACCESSIBLE`. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-02-discover-tests.md:L40] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-02-discover-tests.md:L193]

## Outputs

| Output | Path |
|--------|------|
| Traceability report | `default_output_file` = `{test_artifacts}/traceability-matrix.md` [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L42] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L808] |
| Machine summary | `e2e_trace_summary_output` = `{test_artifacts}/e2e-trace-summary.json` [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L43] |
| Gate signal | `gate_decision_output` = `{test_artifacts}/gate-decision.json` [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L44] |
| Phase 1 matrix (temp) | `/tmp/tea-trace-coverage-matrix-{{timestamp}}.json` [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-04-analyze-gaps.md:L6] |
| Validate-mode report | `{test_artifacts}/trace-validation-report-{validation_scope}-{run_timestamp}.md` [SRC:src/workflows/testarch/bmad-testarch-trace/steps-v/step-01-validate.md:L4] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-v/step-01-validate.md:L29] |

## Steps and modes

1. `step-01-load-context` — resolve the coverage oracle, load knowledge, gather artifacts; oracle order is formal requirements → contract/spec artifacts → external pointers → synthetic journeys. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-01-load-context.md:L3] [SRC:src/workflows/testarch/bmad-testarch-trace/SKILL.md:L87]
2. `step-02-discover-tests` — catalogue tests by level. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-02-discover-tests.md:L3]
3. `step-03-map-criteria` — map oracle items to tests; per-item coverage is `FULL`, `PARTIAL`, `NONE`, `UNIT-ONLY` or `INTEGRATION-ONLY`. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-03-map-criteria.md:L3] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-03-map-criteria.md:L43]
4. `step-04-analyze-gaps` — Phase 1 only (no gate decision); marks the matrix `PHASE_1_COMPLETE` and records `tempCoverageMatrixPath` in frontmatter. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-04-analyze-gaps.md:L24] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-04-analyze-gaps.md:L607] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-04-analyze-gaps.md:L691]
5. `step-05-gate-decision` — apply the gate logic and write every output; final step. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L3] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L808]

Each step saves `stepsCompleted`, `lastStep` and `lastSaved` frontmatter; the report's `workflowType` is `testarch-trace`. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-01-load-context.md:L135] [SRC:src/workflows/testarch/bmad-testarch-trace/trace-template.md:L5] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L869] The mode menu offers Create, Resume, Validate and Edit; Create starts at `steps-c/step-01-load-context.md`, Resume at `steps-c/step-01b-resume.md`. [SRC:src/workflows/testarch/bmad-testarch-trace/SKILL.md:L75] [SRC:src/workflows/testarch/bmad-testarch-trace/SKILL.md:L82] [SRC:src/workflows/testarch/bmad-testarch-trace/SKILL.md:L83] [SRC:src/workflows/testarch/bmad-testarch-trace/SKILL.md:L84] [SRC:src/workflows/testarch/bmad-testarch-trace/SKILL.md:L85] Resume after `step-04-analyze-gaps` goes to step 5; after `step-05-gate-decision` it reports "All steps completed" and halts. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-01b-resume.md:L76] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-01b-resume.md:L77]

Step 4 reads `tea_execution_mode` (default `auto`: agent-team, else subagent, else sequential) and, when parallel, splits gap classification, heuristics/live roll-up and coverage statistics across workers A, B and C. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-04-analyze-gaps.md:L59] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-04-analyze-gaps.md:L103] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-04-analyze-gaps.md:L742]

## Gate eligibility

- A run is gate-eligible only when `allow_gate` is true **and** the normalised `collection_status` is `COLLECTED`. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L262]
- `gateDecision` starts as `NOT_EVALUATED` and is overwritten only for gate-eligible runs; otherwise the rationale says the gate was skipped and names `allow_gate` and `collection_status`. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L264] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L268]
- An unresolved `allow_gate` placeholder defaults to `true`; with no explicit status, `collection_mode: waived` maps to `WAIVED` (restricted, inaccessible and deferred_shared map similarly); with no mapping the status falls back to `COLLECTED`. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L249] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L254] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L259]

## Decision rules

Rules 1–5 are an if / else-if chain evaluated in order, so the first match wins; the decision is deterministic. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L278] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L914]

| Rule | Condition | Decision |
|------|-----------|----------|
| 1 | P0 coverage < 100% | `FAIL` [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L271] |
| 2 | Overall coverage < 80% | `FAIL` [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L277] |
| 3 | Effective P1 coverage < 80% | `FAIL` [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L282] |
| 4 | Effective P1 ≥ 90% (P0 100%, overall ≥ 80%) | `PASS` [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L289] |
| 5 | Effective P1 80–89% (P0 100%, overall ≥ 80%) | `CONCERNS` [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L296] |

- No P1 requirements → effective P1 coverage is 100. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L98]
- Percentages are `round(covered/total*100)`; a priority with zero criteria counts as 100%. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-04-analyze-gaps.md:L465]
- Critical gaps = every P0 criterion whose coverage is not `FULL`. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-04-analyze-gaps.md:L138]
- Rule 6 (manual waiver) is deliberately not computed, and `WAIVED` is never derived from coverage or any other step-5 input. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L304] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L305]

## Overlays that tighten a PASS

- **Oracle confidence:** with a synthetic oracle (`oracle.synthetic` true, or basis `synthetic_requirements` / `user_journeys`), a `PASS` becomes `CONCERNS` unless effective oracle confidence is `high`. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L314] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L127]
- **Live evidence:** if any requirement is covered only by live verification, a `PASS` or `CONCERNS` becomes `CONCERNS`; the live-only count takes the larger of the re-derived and reported values. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L331] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L182] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L914]

## Waivers

A waiver is a human override of a `FAIL`; the workflow never grants or applies one and keeps the Rules 1–5 decision. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L346] Filed waivers are checked against seven ids (`WAIVER_CHECK_IDS`), including `fail_only`, `not_security` (auth criteria count as security) and `contract_complete` (reason, approver and role, dates, monitoring and remediation plan). [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L357] [SRC:src/workflows/testarch/bmad-testarch-trace/checklist.md:L589] [SRC:src/workflows/testarch/bmad-testarch-trace/checklist.md:L594] [SRC:src/workflows/testarch/bmad-testarch-trace/checklist.md:L595] A waived criterion stays in `critical_gaps` and in every coverage percentage. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L384] The report's Waiver Register Review states that no waiver changed the decision. [SRC:src/workflows/testarch/bmad-testarch-trace/trace-template.md:L447]

## gate-decision.json contract

Written only when the run is gate-eligible and `gateDecision` is one of `PASS`, `CONCERNS`, `FAIL`, `WAIVED`; otherwise the file is not written. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L748] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L747] It is a slim subset of the summary with its own `schema_version` `0.1.0`, written as 2-space-indented JSON to `{gate_decision_output}`. [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L67] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L742] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L764]

| Field | Value |
|-------|-------|
| `schema_version` | `'0.1.0'` [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L750] |
| `evaluated_at` | summary `snapshot_at` (ISO-8601 from `new Date().toISOString()`) [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L751] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L619] |
| `repo` | `project_name`, or `''` when unresolved [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L752] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L615] |
| `target` | Phase 1 `trace_target`, else `{type: gate_type, id: null, label: null}` [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L753] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L626] |
| `collection_status` | copied from the summary [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L754] |
| `gate_basis` | `priority_thresholds` when gate-eligible, else `none` [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L755] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L610] |
| `gate_status` | the derived decision [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L756] |
| `rationale` | string from the decision tree and overlays [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L757] |
| `p0_status` | `MET` only at P0 = 100, else `NOT_MET` [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L758] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L727] |
| `p1_status` | `MET` ≥ 90, `PARTIAL` ≥ 80, else `NOT_MET` [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L759] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L731] |
| `overall_status` | `MET` ≥ 80, else `NOT_MET` [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L760] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L734] |
| `critical_open` | count of Phase 1 `gap_analysis.critical_gaps` [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L761] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L678] |
| `links` | `trace_report_path` = the report path; `trace_report_url`, `artifact_url`, `journey_evidence_url` empty until a CI runner fills them [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L762] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L709] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L710] |

The validation checklist requires `evaluated_at`, `gate_basis`, `gate_status`, `rationale` and the per-criterion status fields. [SRC:src/workflows/testarch/bmad-testarch-trace/checklist.md:L205]

## e2e-trace-summary.json

Always emitted by Phase 2; gate fields only for gate-eligible runs. [SRC:src/workflows/testarch/bmad-testarch-trace/checklist.md:L256] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L722]

- `schema_version` `0.3.0` (0.2.0 added `live_evidence` and `by_level.live`; 0.3.0 added `waivers`). [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L618]
- Top level: `collection_mode`, `collection_status`, `inventory_basis`, `gate_basis`, `decision_mode`, `evaluator`, `confidence`, `source_sha` (live evidence sha → git HEAD → `GITHUB_SHA` → empty). [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L623] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L628] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L603]
- `gate_status` (`PASS | CONCERNS | FAIL | WAIVED`) and `gate_criteria` (`p0_coverage_required '100%'`, `p1_coverage_target '90%'`, `p1_coverage_minimum '80%'`, `overall_coverage_minimum '80%'` with actuals and statuses). [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L52] [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L59]
- `coverage.by_level` (`e2e`, `api`, `component`, `unit`, `live`, `other`), `tests`, `risk_summary`, `heuristics`, `live_evidence`. [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L53] [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L54] [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L55] [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L56] [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L57]
- `waivers` only when a register was found; it never touches `gate_status`. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L718] [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L60]
- `rejected_evidence` always present; unknown runtime values are the literal `unknown`. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L705] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L482]

## HALT conditions

- Step 1: none of the four oracle types resolves. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-01-load-context.md:L92]
- Step 5: `tempCoverageMatrixPath` missing, matrix not `PHASE_1_COMPLETE`, or `priority_breakdown` lacks P0–P3. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L45] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L68] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L90]
- Resume: no output document, or an unknown `lastStep`. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-01b-resume.md:L48] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-01b-resume.md:L79]
