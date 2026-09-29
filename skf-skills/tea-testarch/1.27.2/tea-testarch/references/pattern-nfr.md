# NFR assessment (bmad-testarch-nfr)

## Contents

- [Inputs](#inputs)
- [Outputs](#outputs)
- [Steps](#steps)
- [Status definitions and roll-up](#status-definitions-and-roll-up)
- [Gate YAML snippet](#gate-yaml-snippet)
- [Resume, Validate, Edit and HALTs](#resume-validate-edit-and-halts)

## Inputs

- Config from `_bmad/tea/config.yaml`; `test_artifacts` from the TEA key; `custom_nfr_categories` (default empty) adds categories beyond the standard four. [SRC:src/workflows/testarch/bmad-testarch-nfr/workflow.yaml:L7] [SRC:src/workflows/testarch/bmad-testarch-nfr/workflow.yaml:L9] [SRC:src/workflows/testarch/bmad-testarch-nfr/workflow.yaml:L24]
- Step 1 reads `tech-spec.md` (primary), `PRD.md`, story or test-design docs, and `tea_browser_automation`. [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-01-load-context.md:L85] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-01-load-context.md:L86] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-01-load-context.md:L87] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-01-load-context.md:L53]
- Step 2 takes thresholds first from a test-design NFR section (`test-design-architecture.md`, `test-design-qa.md`). [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-02-define-thresholds.md:L43] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-02-define-thresholds.md:L44]
- Marked autonomous (proceeds unless blocked). [SRC:src/workflows/testarch/bmad-testarch-nfr/workflow.yaml:L47]

## Outputs

| Output | Path |
|--------|------|
| Report | `{test_artifacts}/nfr-assessment.md` (`workflowType: testarch-nfr-assess`) [SRC:src/workflows/testarch/bmad-testarch-nfr/workflow.yaml:L27] [SRC:src/workflows/testarch/bmad-testarch-nfr/nfr-report-template.md:L5] |
| Browser evidence | `{test_artifacts}/nfr/` [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-03-gather-evidence.md:L131] |
| Worker results (temp) | `/tmp/tea-nfr-<domain>-<timestamp>.json` for security, performance, reliability, maintainability [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-04-evaluate-and-score.md:L222] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-04-evaluate-and-score.md:L39] |
| Executive summary (temp) | `/tmp/tea-nfr-summary-{{timestamp}}.json` [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-04e-aggregate-nfr.md:L450] |
| Validate-mode report | `{test_artifacts}/nfr-assess-validation-report-{validation_scope}-{run_timestamp}.md` [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-v/step-01-validate.md:L4] |

## Steps

1. `step-01-load-context` — load inputs, record `inputDocuments`. [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-01-load-context.md:L119] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-01-load-context.md:L105]
2. `step-02-define-thresholds` — four automated domains (Security, Performance, Reliability, Maintainability); other categories go to `recorded_only_nfr_criteria` and never reach a worker, status or gap; no guessing — unknown thresholds become `UNKNOWN` → `CONCERNS`. [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-02-define-thresholds.md:L68] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-02-define-thresholds.md:L70] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-02-define-thresholds.md:L100] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-02-define-thresholds.md:L18] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-02-define-thresholds.md:L116] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-02-define-thresholds.md:L119] Disaster Recovery has no automated worker. [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-02-define-thresholds.md:L103]
3. `step-03-gather-evidence` — build the `supplied_evidence_ledger` (the allowlist for factual claims); an unsupported criterion yields one gap `'<label>: no supplied implementation evidence'`. [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-03-gather-evidence.md:L57] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-03-gather-evidence.md:L104] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-03-gather-evidence.md:L138]
4. `step-04-evaluate-and-score` — domain workers in agent-team, subagent or sequential mode (`tea_execution_mode`, default `auto`; explicit run request wins); one finding per declared criterion. [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-04-evaluate-and-score.md:L3] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-04-evaluate-and-score.md:L64] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-04-evaluate-and-score.md:L65] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-04-evaluate-and-score.md:L119] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-04-evaluate-and-score.md:L121] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-04-evaluate-and-score.md:L138] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-04-evaluate-and-score.md:L170] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-04-evaluate-and-score.md:L150]
5. `step-04e-aggregate-nfr` — aggregate without re-assessing. [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-04e-aggregate-nfr.md:L22] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-04e-aggregate-nfr.md:L492]
6. `step-05-generate-report` — eleven prepublication checks, gate YAML, next workflow = trace or release gate. [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-05-generate-report.md:L121] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-05-generate-report.md:L44] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-05-generate-report.md:L157]

## Status definitions and roll-up

| Status | Meaning |
|--------|---------|
| `PASS` | Implemented, meets threshold, backed by evidence [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/nfr-status-definitions.md:L21] |
| `CONCERNS` | Partial or weak; does not block but needs follow-up [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/nfr-status-definitions.md:L23] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/nfr-status-definitions.md:L25] |
| `FAIL` | Not implemented or threshold breached [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/nfr-status-definitions.md:L26] |
| `N/A` | Not applicable [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/nfr-status-definitions.md:L28] |

- Domain status = worst finding (FAIL > CONCERNS > PASS); `N/A` only when every finding is `N/A`. [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/nfr-status-definitions.md:L32] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/nfr-status-definitions.md:L32]
- `UNKNOWN` threshold ⇒ `CONCERNS`, never `PASS`; an omitted criterion gets a synthesized `CONCERNS`. [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/nfr-status-definitions.md:L41] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-04e-aggregate-nfr.md:L88] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-04e-aggregate-nfr.md:L79]
- Risk: any FAIL finding ⇒ domain HIGH; overall HIGH if any domain is HIGH (HIGH > MEDIUM > LOW > NONE). [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-04e-aggregate-nfr.md:L278] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-04e-aggregate-nfr.md:L291] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-04e-aggregate-nfr.md:L273]
- Custom categories get a report section but no worker and no `audited_domains` status. [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/nfr-status-definitions.md:L36]

## Gate YAML snippet

The report includes a gate-ready YAML snippet rooted at `nfr_assessment` with `audited_domains` (exactly the four domains, each PASS/CONCERNS/FAIL/N/A), `overall_status` and a boolean `blockers`. [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-05-generate-report.md:L44] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-05-generate-report.md:L46] [SRC:src/workflows/testarch/bmad-testarch-nfr/nfr-report-template.md:L397] [SRC:src/workflows/testarch/bmad-testarch-nfr/nfr-report-template.md:L411] [SRC:src/workflows/testarch/bmad-testarch-nfr/nfr-report-template.md:L416] [SRC:src/workflows/testarch/bmad-testarch-nfr/nfr-report-template.md:L421] Each `audited_domains` value must equal the domain's Assessment section; on PASS the next action is trace Phase 2. [SRC:src/workflows/testarch/bmad-testarch-nfr/checklist.md:L247] [SRC:src/workflows/testarch/bmad-testarch-nfr/nfr-report-template.md:L472]

## Resume, Validate, Edit and HALTs

- Menu: Create → `steps-c/step-01-load-context.md`, Resume → `steps-c/step-01b-resume.md`, Validate → `steps-v/step-01-validate.md`, Edit → `steps-e/step-01-assess.md`. [SRC:src/workflows/testarch/bmad-testarch-nfr/SKILL.md:L82] [SRC:src/workflows/testarch/bmad-testarch-nfr/SKILL.md:L83] [SRC:src/workflows/testarch/bmad-testarch-nfr/SKILL.md:L84] [SRC:src/workflows/testarch/bmad-testarch-nfr/SKILL.md:L85]
- Resume routes to the exact next incomplete step; halts with no output or an unknown `lastStep`. [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-01b-resume.md:L78] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-01b-resume.md:L79] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-01b-resume.md:L106] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-01b-resume.md:L46] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-01b-resume.md:L84]
- HALTs: missing implementation/evidence sources (step 1), duplicate stable IDs (step 2), missing worker file (step 4), failed prepublication check (returns to 4E), unexecutable mode with probing off. [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-01-load-context.md:L45] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-02-define-thresholds.md:L79] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-04-evaluate-and-score.md:L226] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-05-generate-report.md:L120] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-04-evaluate-and-score.md:L142]
- Validate never overwrites an existing report. [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-v/step-01-validate.md:L29] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-v/step-01-validate.md:L64]
