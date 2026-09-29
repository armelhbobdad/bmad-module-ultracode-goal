# Test review (bmad-testarch-test-review)

## Contents

- [Inputs](#inputs)
- [Outputs](#outputs)
- [Steps](#steps)
- [Scoring](#scoring)
- [Recommendation](#recommendation)
- [Criteria registry](#criteria-registry)
- [Workers and execution mode](#workers-and-execution-mode)
- [Modes and HALTs](#modes-and-halts)

## Inputs

| Variable | Default | Meaning |
|----------|---------|---------|
| `test_dir` | `{project-root}/tests` | Root test directory [SRC:src/workflows/testarch/bmad-testarch-test-review/workflow.yaml:L23] |
| `review_scope` | `single` | `single`, `directory`, `suite` [SRC:src/workflows/testarch/bmad-testarch-test-review/workflow.yaml:L24] |
| `test_stack_type` | `auto` | `frontend`, `backend`, `fullstack`, `mobile` [SRC:src/workflows/testarch/bmad-testarch-test-review/workflow.yaml:L25] |
| `headless` | `false` | Skip greeting and menu, run Create, never prompt [SRC:src/workflows/testarch/bmad-testarch-test-review/workflow.yaml:L28] [SRC:src/workflows/testarch/bmad-testarch-test-review/SKILL.md:L73] |
| `review_files` | empty | Authoritative comma-separated review set; overrides discovery [SRC:src/workflows/testarch/bmad-testarch-test-review/workflow.yaml:L29] |
| `context_files` | empty | Read-only context (story, PRD, test design, changed source), never scored [SRC:src/workflows/testarch/bmad-testarch-test-review/workflow.yaml:L30] |
| `output_file_override` | empty | Replaces the report path for every step [SRC:src/workflows/testarch/bmad-testarch-test-review/workflow.yaml:L31] [SRC:src/workflows/testarch/bmad-testarch-test-review/instructions.md:L37] |
| `generate_inline_comments` | `false` | Write `// TODO (TEA Review)` comments at violations [SRC:src/workflows/testarch/bmad-testarch-test-review/workflow.yaml:L32] [SRC:src/workflows/testarch/bmad-testarch-test-review/checklist.md:L300] |

Config comes from `_bmad/tea/config.yaml` (`test_artifacts`, `tea_execution_mode`, `tea_capability_probe`, plus the Playwright/Pact/browser flags that choose knowledge fragments). [SRC:src/workflows/testarch/bmad-testarch-test-review/workflow.yaml:L7] [SRC:src/workflows/testarch/bmad-testarch-test-review/workflow.yaml:L9] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03-quality-evaluation.md:L89] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03-quality-evaluation.md:L90] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-01-load-context.md:L72] Headless runs take `tea_run_id` from the caller as the run timestamp and never hunt for documents outside `context_files`. [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03-quality-evaluation.md:L53] [SRC:src/workflows/testarch/bmad-testarch-test-review/SKILL.md:L77]

## Outputs

| Output | Path |
|--------|------|
| Report | `{test_artifacts}/test-review.md` (`workflowType: testarch-test-review`) [SRC:src/workflows/testarch/bmad-testarch-test-review/workflow.yaml:L35] [SRC:src/workflows/testarch/bmad-testarch-test-review/test-review-template.md:L5] |
| Worker results (temp) | `/tmp/tea-test-review-{dimension}-{timestamp}.json` [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03-quality-evaluation.md:L267] |
| Aggregate (temp) | `/tmp/tea-test-review-summary-{timestamp}.json` [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03f-aggregate-scores.md:L376] |
| Validate-mode report | `{test_artifacts}/test-review-validation-report-{validation_scope}-{run_timestamp}.md` [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-v/step-01-validate.md:L4] |

Machine-read report parts: the `Execution Mode` line (resolved mode, never `auto`), the Quality Score Breakdown ledger (exact line form) and the Reviewed Files manifest; missing expected files go in "Excluded From Review Set". [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-04-generate-report.md:L47] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-04-generate-report.md:L61] [SRC:src/workflows/testarch/bmad-testarch-test-review/test-review-template.md:L470] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-02-discover-tests.md:L40]

## Steps

`step-01-load-context` → `step-02-discover-tests` (convention baseline) → `step-03-quality-evaluation` (workers) → `step-03f-aggregate-scores` → `step-04-generate-report`. [SRC:src/workflows/testarch/bmad-testarch-test-review/SKILL.md:L94] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-01-load-context.md:L4] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-02-discover-tests.md:L4] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-02-discover-tests.md:L178] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03-quality-evaluation.md:L4] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03f-aggregate-scores.md:L4] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-04-generate-report.md:L39] Each step appends its name to `stepsCompleted` once. [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-01-load-context.md:L172] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03f-aggregate-scores.md:L421]

## Scoring

- 0–100 quality score; **coverage is not scored** — coverage gates belong to trace. [SRC:src/workflows/testarch/bmad-testarch-test-review/instructions.md:L10] [SRC:src/workflows/testarch/bmad-testarch-test-review/instructions.md:L12]
- Deduction ledger, not a weighted average: CRITICAL −10, HIGH −5, MEDIUM −2, LOW −1; six bonus categories worth 0 or 5; raw = 100 − deductions + bonus, clamped 0–100. [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03f-aggregate-scores.md:L22] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03f-aggregate-scores.md:L149] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03f-aggregate-scores.md:L152] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03f-aggregate-scores.md:L173]
- Severity caps: CRITICAL ≤ 69, HIGH ≤ 79, MEDIUM ≤ 89, LOW ≤ 99. [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03f-aggregate-scores.md:L180]
- Grades: A 90–100, B 80–89, C 70–79, D 60–69, F < 60. [SRC:src/workflows/testarch/bmad-testarch-test-review/checklist.md:L239] [SRC:src/workflows/testarch/bmad-testarch-test-review/checklist.md:L240] [SRC:src/workflows/testarch/bmad-testarch-test-review/checklist.md:L241] [SRC:src/workflows/testarch/bmad-testarch-test-review/checklist.md:L242] [SRC:src/workflows/testarch/bmad-testarch-test-review/checklist.md:L243]

## Recommendation

`Approve | Approve with Comments | Request Changes | Block`: any CRITICAL → Block; any HIGH → Request Changes; score < 70 → Request Changes; remaining MEDIUM/LOW with score ≥ 70 → Approve with Comments; else Approve. [SRC:src/workflows/testarch/bmad-testarch-test-review/test-review-template.md:L28] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03f-aggregate-scores.md:L222] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03f-aggregate-scores.md:L223] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03f-aggregate-scores.md:L224] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03f-aggregate-scores.md:L225] The same value goes into Executive Summary and Decision; the CLI rejects a report where they differ. [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03f-aggregate-scores.md:L260]

## Criteria registry

- Severity is fixed by the registry row; a closed gate reports `PASS (n/a)` and never deducts. [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/criteria-registry.md:L18] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/criteria-registry.md:L25]
- Examples: C1 disabled test (CRITICAL), C4 no assertion (CRITICAL), H1 hard wait (HIGH), H5 file > 1000 lines (HIGH). [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/criteria-registry.md:L138] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/criteria-registry.md:L141] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/criteria-registry.md:L150] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/criteria-registry.md:L154]
- Conventions: established (≥ 50% of ≥ 4 sampled files) deducts at row severity; emerging deducts one step lower (floor LOW); absent never deducts. [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/criteria-registry.md:L85] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/criteria-registry.md:L86] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/criteria-registry.md:L87]
- Criterion shows FAIL when a CRITICAL/HIGH row fired, WARN for MEDIUM/LOW only; unscorable files are listed, not scored. [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/criteria-registry.md:L235] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/criteria-registry.md:L234] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/criteria-registry.md:L30]
- Rows M9/L9 need `playwrightUtilsActive` (flag and installed package). [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/criteria-registry.md:L45]

## Workers and execution mode

Four workers — determinism, isolation, maintainability, performance (3E) — resolved by `tea_execution_mode` (explicit run request first; auto = agent-team → subagent → sequential; probing off = strict, error if unexecutable). [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03-quality-evaluation.md:L267] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03-quality-evaluation.md:L233] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03-quality-evaluation.md:L177] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03-quality-evaluation.md:L158] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03-quality-evaluation.md:L181] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03-quality-evaluation.md:L215] Determinism owns every CRITICAL row except C5, and also H1 (hard waits, which performance must not emit); isolation owns H4. [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03a-subagent-determinism.md:L43] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03e-subagent-performance.md:L25] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03b-subagent-isolation.md:L40] A failing worker writes `success: false`; aggregation deduplicates by file, location and row. [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03a-subagent-determinism.md:L311] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03f-aggregate-scores.md:L103]

## Modes and HALTs

- Create, Resume, Validate, Edit; Resume after `step-03f-aggregate-scores` continues at step 4. [SRC:src/workflows/testarch/bmad-testarch-test-review/SKILL.md:L88] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-01b-resume.md:L77]
- HALTs: no test files (step 2), failed or missing worker output (step 3), missing timestamp or unregistered violation (3F), no output / unknown `lastStep` (Resume). [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-02-discover-tests.md:L54] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03-quality-evaluation.md:L319] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03-quality-evaluation.md:L272] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03f-aggregate-scores.md:L43] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03f-aggregate-scores.md:L84] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-01b-resume.md:L46] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-01b-resume.md:L82]
- Validate never overwrites a report; `on_complete` runs at completion. [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-v/step-01-validate.md:L29] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-04-generate-report.md:L134]
- Context cannot waive violations (`Context Waivers Applied` stays 0); `Context Basis` is `none`, `pr_diff` or `pr_diff_truncated`. [SRC:src/workflows/testarch/bmad-testarch-test-review/test-review-template.md:L41] [SRC:src/workflows/testarch/bmad-testarch-test-review/test-review-template.md:L39]
