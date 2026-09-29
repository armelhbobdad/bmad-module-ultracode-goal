# Release context (T2)

Temporal context from the upstream changelog, GitHub releases, merged PRs and issues, fetched for v1.27.2. Items under "Upcoming" were merged on `main` **after** the v1.27.2 tag and are not in this skill's source.

## Contents

- [Upcoming (after v1.27.2)](#upcoming-after-v1272)
- [v1.27.2](#v1272)
- [v1.27.1](#v1271)
- [v1.27.0](#v1270)
- [v1.26.0](#v1260)
- [Issues](#issues)

## Upcoming (after v1.27.2)

- **Breaking: output paths (PR #236, closes #228).** Every workflow writes under its own folder in `{test_artifacts}` (`test-design/`, `atdd/`, `automate/`, `test-review/`, `nfr/`, `trace/`, `ci/`, `framework/`), and per-scope files carry a `run_key` (`system`, `epic-{epic_num}`, `story-{story_key}`, trace's `release-{slug}` / `hotfix-{slug}`, `target-{slug}`). Trace writes `trace/traceability-matrix-{run_key}.md`, `trace/e2e-trace-summary-{run_key}.json` and `trace/gate-decision-{run_key}.json`. Workflows read another workflow's output from its folder first, then from the old root; completed flat files are never moved. [QMD:tea-testarch-temporal:changelog.md] [QMD:tea-testarch-temporal:prs.md]
  - In v1.27.2 the gate file is the flat `{test_artifacts}/gate-decision.json`. [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L44] The changelog records that a trace run for epic 16 replaced epic 15's `gate-decision.json` and `e2e-trace-summary.json` on 1.27.2. [QMD:tea-testarch-temporal:changelog.md]
- **Removed keys:** the future output-folder keys `test_design_output`, `test_review_output` and `trace_output` leave `module.yaml`; install no longer prompts for them. They are unused placeholders in v1.27.2. [SRC:src/module.yaml:L210] [QMD:tea-testarch-temporal:changelog.md]
- **New workflow:** Evaluate (`bmad-testarch-evaluate`, menu code `EV`) becomes TEA's tenth workflow, in a lean skill shape (`SKILL.md`, `customize.toml`, `references/`, `assets/`, no `workflow.yaml`), with the `tea-evaluate` CLI. [QMD:tea-testarch-temporal:changelog.md]
- **`{project-root}` resolution (PR #240):** skills resolve `{project-root}` as the nearest folder containing `_bmad/`, walking up from the working directory, so agents started in a worktree or subfolder find the right install. [QMD:tea-testarch-temporal:prs.md]

## v1.27.2

Released 2026-09-18. [QMD:tea-testarch-temporal:releases.md]

- Trace evaluation repeats the resolved run-metadata contract in its prompt and validates required paths, empty URL fields, inventory counts, UI heuristic states and explicit unknown handling during preflight.
- Test-design grounds risks in supplied epic evidence, keeps risk registers in scope and requires exact risk IDs with admitted test levels in coverage plans (see [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-04-coverage-plan.md:L48]).
- NFR audits build one supplied-evidence ledger, bind every observation to a stable criterion ID and give unsupported criteria one fixed structured gap (see [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-03-gather-evidence.md:L57] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-03-gather-evidence.md:L104]).
- Fragment selection follows one closed selection contract across the eight evaluated workflows.
- `bmad-tea` asks one focused question when the supplied facts support several workflows (see [SRC:src/agents/bmad-tea/SKILL.md:L78]).
- ATDD red-phase generation preserves supplied criterion ids, assigns stable ids to unnamed criteria and emits one red-phase leaf per criterion (see [SRC:src/workflows/testarch/bmad-testarch-atdd/steps-c/step-01-preflight-and-context.md:L76] [SRC:src/workflows/testarch/bmad-testarch-atdd/steps-c/step-01-preflight-and-context.md:L78] [SRC:src/workflows/testarch/bmad-testarch-atdd/steps-c/step-04a-subagent-api-failing.md:L143]).

## v1.27.1

Released 2026-09-17: bounded retries for live probes, and the first complete live `eval:all` run recorded (automate, ci, test-review and framework met every threshold; atdd, nfr, test-design and trace recorded quality findings). [QMD:tea-testarch-temporal:releases.md]

## v1.27.0

The NFR gate artifact declares the four domain statuses: the template's Gate YAML snippet gained the `audited_domains` block, `nfr-status-definitions.md` states the domain-status rule, step 4E computes it and step 5 writes it (see [SRC:src/workflows/testarch/bmad-testarch-nfr/nfr-report-template.md:L411] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/nfr-status-definitions.md:L32]). [QMD:tea-testarch-temporal:changelog.md]

## v1.26.0

Released 2026-09-09. [QMD:tea-testarch-temporal:releases.md]

- Test-review's four quality workers can run in parallel; `tea_execution_mode` and `tea_capability_probe` resolve through CLI flags, then `_bmad/tea/config.yaml`, then `src/module.yaml`.
- The review report carries an `**Execution Mode**:` line and the verdict JSON an `executionMode` field (see [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-04-generate-report.md:L47]); the CLI mints a `tea_run_id` used as the worker-path timestamp (see [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03-quality-evaluation.md:L53]).
- Module defaults corrected in help text: `--use-pactjs-utils` defaults to `true` and `--pact-mcp` to `"mcp"` (see [SRC:src/module.yaml:L55] [SRC:src/module.yaml:L66]).

## Issues

All 25 fetched issues are closed. Relevant history: #228 (scope-aware output names; closed by PR #236 after v1.27.2), #140 (validate reports overwrote each other — v1.27.2 names them `{validation_scope}-{run_timestamp}` and never overwrites [SRC:src/workflows/testarch/bmad-testarch-trace/steps-v/step-01-validate.md:L4] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-v/step-01-validate.md:L29]), #128 (test-design checkpoint clobbered across epics — v1.27.2 uses `test-design-progress-{run_key}.md` [SRC:src/workflows/testarch/bmad-testarch-test-design/SKILL.md:L87]). [QMD:tea-testarch-temporal:issues.md]
