# tea-testarch Reference

**Version:** 1.27.2 (bmad-method-test-architecture-enterprise tag `v1.27.2`, commit `d99ad29c`)
**Export count:** 9 exports (8 workflow skills + the `bmad-tea` agent, source skill metadata)
**Confidence:** T1-low (dominant `confidence_distribution` bin: t1 25, t1_low 724, t2 22, t3 0; forge tier Deep, reference-app)
**Source skill:** `skf-skills/tea-testarch/1.27.2/tea-testarch`

## Key Exports

| Export | Code | Main output (under `{test_artifacts}`) |
|--------|------|----------------------------------------|
| `bmad-testarch-test-design` | TD | `test-design-architecture.md`, `test-design-qa.md`; `test-design-epic-{epic_num}.md` |
| `bmad-testarch-framework` | TF | `{test_dir}/README.md`, framework config, `tea-enforce.cjs` hook |
| `bmad-testarch-ci` | CI | `.github/workflows/test.yml` or the platform equivalent |
| `bmad-testarch-atdd` | AT | `atdd-checklist-{story_key}.md` and red-phase `test.skip()` scaffolds |
| `bmad-testarch-automate` | TA | `automation-summary.md` and `[P0]`–`[P3]` tagged tests |
| `bmad-testarch-test-review` | RV | `test-review.md`, scored 0–100 with a recommendation |
| `bmad-testarch-nfr` | NR | `nfr-assessment.md` with an `nfr_assessment` gate YAML |
| `bmad-testarch-trace` | TR | `traceability-matrix.md`, `e2e-trace-summary.json`, `gate-decision.json` |
| `bmad-tea` agent | — | Menu over the workflows plus `GATE` |

## Usage Patterns

- Every workflow reads `{project-root}/_bmad/tea/config.yaml`; `test_artifacts` defaults to `{output_folder}/test-artifacts`.
- Phase 3, once per project: test-design → framework → ci. Per story: atdd after `bmad-create-story:create` and before `bmad-dev-story`, then automate; test-review and nfr follow automate; trace after test-review.
- Gate signal: `{test_artifacts}/gate-decision.json` from `bmad-testarch-trace` step 5, `gate_status` `PASS` / `CONCERNS` / `FAIL` (`WAIVED` never derived by rules 1–5); written only for gate-eligible runs, so compare `evaluated_at` with the run start.
- On Claude Code, `bmad-testarch-framework` merges `PreToolUse`, `PostToolUse` and `Stop` entries for `.claude/hooks/tea-enforce.cjs` into `.claude/settings.json`; the hook blocks with exit 2.
- After v1.27.2 (breaking, PR #236): outputs move to `{test_artifacts}/<workflow>/` with a `run_key`; the gate file becomes `trace/gate-decision-{run_key}.json`.

## Common Imports

Compose-mode: no import statements. TEA workflows are skills invoked by name; each opens a Create / Resume / Validate / Edit menu, and Create runs without further input unless blocked.
