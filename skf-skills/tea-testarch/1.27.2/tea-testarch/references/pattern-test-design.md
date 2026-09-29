# Test design (bmad-testarch-test-design)

## Contents

- [Inputs](#inputs)
- [Mode detection](#mode-detection)
- [Outputs](#outputs)
- [Steps](#steps)
- [Risk scoring and priorities](#risk-scoring-and-priorities)
- [Resume, Validate, Edit](#resume-validate-edit)

## Inputs

- Config from `{project-root}/_bmad/tea/config.yaml` via `config_source`; `test_artifacts` from the TEA key. [SRC:src/workflows/testarch/bmad-testarch-test-design/workflow.yaml:L7] [SRC:src/workflows/testarch/bmad-testarch-test-design/workflow.yaml:L9]
- `design_level` (default `full`; `targeted`, `minimal`), `mode` (auto-detect; `system-level` or `epic-level`), `test_stack_type` (default `auto`). [SRC:src/workflows/testarch/bmad-testarch-test-design/workflow.yaml:L26] [SRC:src/workflows/testarch/bmad-testarch-test-design/workflow.yaml:L27] [SRC:src/workflows/testarch/bmad-testarch-test-design/workflow.yaml:L28]
- Step 2 reads `tea_use_playwright_utils`, `tea_browser_automation` and `test_stack_type`. [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-02-load-context.md:L44] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-02-load-context.md:L47] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-02-load-context.md:L48]
- System-level needs a PRD with functional and non-functional requirements; epic-level needs epic/story requirements with acceptance criteria. [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-01-detect-mode.md:L78] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-01-detect-mode.md:L84]
- Epic-level loads prior system-level outputs when present and never widens to other epics. [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-02-load-context.md:L91] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-02-load-context.md:L84]
- The workflow is marked autonomous: it proceeds without user input unless blocked. [SRC:src/workflows/testarch/bmad-testarch-test-design/workflow.yaml:L76]

## Mode detection

| Signal | Mode |
|--------|------|
| PRD + ADR, no epics/stories | System-level (Phase 3 testability review) [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-01-detect-mode.md:L53] [SRC:src/workflows/testarch/bmad-testarch-test-design/instructions.md:L13] |
| Epic + stories, no PRD/ADR | Epic-level (Phase 4 per-epic plan) [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-01-detect-mode.md:L54] [SRC:src/workflows/testarch/bmad-testarch-test-design/instructions.md:L14] |
| Both present | System-level first [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-01-detect-mode.md:L55] |
| Intent unclear and `{implementation_artifacts}/sprint-status.yaml` exists | Epic-level [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-01-detect-mode.md:L65] |
| Still ambiguous | Ask and HALT [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-01-detect-mode.md:L70] |

System-level sets `run_key` `system`; epic-level sets `epic-{epic_num}` (a title slug when the epic has no number); an unresolved `epic_num` lists candidates and halts. [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-01-detect-mode.md:L108] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-01-detect-mode.md:L118] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-01-detect-mode.md:L120] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-01-detect-mode.md:L116]

## Outputs

| Mode | File |
|------|------|
| System-level (architecture audience) | `{test_artifacts}/test-design-architecture.md` [SRC:src/workflows/testarch/bmad-testarch-test-design/workflow.yaml:L37] |
| System-level (QA audience) | `{test_artifacts}/test-design-qa.md` [SRC:src/workflows/testarch/bmad-testarch-test-design/workflow.yaml:L43] |
| System-level handoff | `{test_artifacts}/test-design/{project_name}-handoff.md`, consumed by BMAD create-epics-and-stories [SRC:src/workflows/testarch/bmad-testarch-test-design/workflow.yaml:L49] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-05-generate-output.md:L159] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-05-generate-output.md:L167] |
| Epic-level | `{test_artifacts}/test-design-epic-{epic_num}.md` [SRC:src/workflows/testarch/bmad-testarch-test-design/workflow.yaml:L56] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-05-generate-output.md:L4] |
| Progress checkpoint | `{test_artifacts}/test-design-progress-{run_key}.md` [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-01-detect-mode.md:L6] [SRC:src/workflows/testarch/bmad-testarch-test-design/SKILL.md:L87] |
| Validate-mode report | `{test_artifacts}/test-design-validation-report-{validation_scope}-{run_timestamp}.md` [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-v/step-01-validate.md:L4] |

System-level uses the architecture and QA templates, epic-level uses `test-design-template.md`; template `workflowType` is `testarch-test-design` (handoff: `testarch-test-design-handoff`). [SRC:src/workflows/testarch/bmad-testarch-test-design/workflow.yaml:L20] [SRC:src/workflows/testarch/bmad-testarch-test-design/test-design-architecture-template.md:L8] [SRC:src/workflows/testarch/bmad-testarch-test-design/test-design-handoff-template.md:L4]

## Steps

1. `step-01-detect-mode` — resolve mode and `run_key`, write checkpoint frontmatter `stepsCompleted: ['step-01-detect-mode']`. [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-01-detect-mode.md:L161]
2. `step-02-load-context` — load artifacts and required knowledge fragments (`adr-quality-readiness-checklist.md` system-level, `probability-impact.md` epic-level); records `inputDocuments`. [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-02-load-context.md:L140] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-02-load-context.md:L149] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-02-load-context.md:L217]
3. `step-03-risk-and-testability` — ASRs marked ACTIONABLE or FYI; risks scored. [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-03-risk-and-testability.md:L54]
4. `step-04-coverage-plan` — priorities, execution tiers, estimates, quality gates. [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-04-coverage-plan.md:L48] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-04-coverage-plan.md:L79] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-04-coverage-plan.md:L89]
5. `step-05-generate-output` — write documents (parallel system-level documents when `tea_execution_mode` resolves to agent-team or subagent), fix missing checklist criteria, set `workflowStatus: completed`, run `on_complete`. [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-05-generate-output.md:L46] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-05-generate-output.md:L47] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-05-generate-output.md:L90] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-05-generate-output.md:L102] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-05-generate-output.md:L115] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-05-generate-output.md:L151] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-05-generate-output.md:L216] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-05-generate-output.md:L237]

## Risk scoring and priorities

- Categories `TECH`, `SEC`, `PERF`, `DATA`, `BUS`, `OPS`; Probability 1–3 × Impact 1–3; score ≥ 6 is high. [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-03-risk-and-testability.md:L65] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-03-risk-and-testability.md:L66] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-03-risk-and-testability.md:L67] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-03-risk-and-testability.md:L68]
- Missing NFR thresholds become `UNKNOWN` clarifications or risks, never guesses; the final NFR PASS/CONCERNS/FAIL belongs to nfr-assess. [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-03-risk-and-testability.md:L79] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-03-risk-and-testability.md:L83]
- P0 critical business/security/data/compliance impact, P1 core frequent behaviour, P2 secondary, P3 rare/cosmetic; risk score is supporting evidence only. [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-04-coverage-plan.md:L55] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-04-coverage-plan.md:L56] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-04-coverage-plan.md:L57] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-04-coverage-plan.md:L58] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-04-coverage-plan.md:L52]
- Coverage rows cite the exact Risk ID; step-4 gates require a P1 pass rate ≥ 95%. [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-04-coverage-plan.md:L48] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-04-coverage-plan.md:L102]

## Resume, Validate, Edit

- Menu routes: Create → `steps-c/step-01-detect-mode.md`, Resume → `steps-c/step-01b-resume.md`, Validate → `steps-v/step-01-validate.md`, Edit → `steps-e/step-01-assess.md`. [SRC:src/workflows/testarch/bmad-testarch-test-design/SKILL.md:L63] [SRC:src/workflows/testarch/bmad-testarch-test-design/SKILL.md:L82] [SRC:src/workflows/testarch/bmad-testarch-test-design/SKILL.md:L83] [SRC:src/workflows/testarch/bmad-testarch-test-design/SKILL.md:L84] [SRC:src/workflows/testarch/bmad-testarch-test-design/SKILL.md:L85]
- Resume scans `test-design-progress-*.md` plus the legacy `test-design-progress.md`; halts with no candidates, on a `runKey` mismatch, with several unnamed candidates, or on a completed checkpoint. [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-01b-resume.md:L5] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-01b-resume.md:L6] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-01b-resume.md:L47] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-01b-resume.md:L70] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-01b-resume.md:L53] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-01b-resume.md:L102]
- Step 1 halts on an in-progress checkpoint until the user chooses resume or restart. [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-01-detect-mode.md:L141]
- Validate never overwrites a report and records PASS/WARN/FAIL per section; Edit applies only explicitly requested edits. [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-v/step-01-validate.md:L29] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-v/step-01-validate.md:L64] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-e/step-02-apply-edit.md:L25]
