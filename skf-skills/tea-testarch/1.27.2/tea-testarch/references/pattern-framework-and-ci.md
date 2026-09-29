# Framework and CI (bmad-testarch-framework, bmad-testarch-ci)

## Contents

- [Framework inputs and preflight](#framework-inputs-and-preflight)
- [Framework selection](#framework-selection)
- [Scaffolded files](#scaffolded-files)
- [tea-enforce.cjs write-time hook](#tea-enforcecjs-write-time-hook)
- [CI inputs and platform detection](#ci-inputs-and-platform-detection)
- [Generated pipeline files](#generated-pipeline-files)
- [CI quality gates](#ci-quality-gates)
- [Modes and HALTs](#modes-and-halts)

## Framework inputs and preflight

- `config_source` `{project-root}/_bmad/tea/config.yaml`; `test_dir` `{project-root}/tests`; `use_typescript` `true`; `framework_preference` `auto` (`playwright`, `cypress`). [SRC:src/workflows/testarch/bmad-testarch-framework/workflow.yaml:L7] [SRC:src/workflows/testarch/bmad-testarch-framework/workflow.yaml:L22] [SRC:src/workflows/testarch/bmad-testarch-framework/workflow.yaml:L23] [SRC:src/workflows/testarch/bmad-testarch-framework/workflow.yaml:L24]
- Stack detection checks mobile first (React Native/Expo), then fullstack, frontend or backend. [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-01-preflight.md:L49] [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-01-preflight.md:L50]
- Preflight HALTs when an E2E config (`playwright.config.*`, `cypress.config.*`, `cypress.json`) or a conflicting framework suite already exists. [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-01-preflight.md:L64] [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-01-preflight.md:L74] [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-01-preflight.md:L78]

## Framework selection

Browser → Playwright unless there is a strong reason for Cypress; Python backend → pytest; mobile → Maestro; fullstack → a browser framework plus a backend one; a non-`auto` `test_framework` config overrides the logic. [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-02-select-framework.md:L44] [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-02-select-framework.md:L63] [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-02-select-framework.md:L72] [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-02-select-framework.md:L86] [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-02-select-framework.md:L88]

## Scaffolded files

| File | Notes |
|------|-------|
| `{test_dir}/README.md` | `default_output_file`, the main deliverable [SRC:src/workflows/testarch/bmad-testarch-framework/workflow.yaml:L28] |
| `{test_artifacts}/framework-setup-progress.md` | Create-mode progress file [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-01-preflight.md:L5] [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-04-docs-and-scripts.md:L6] |
| `playwright.config.ts` / `cypress.config.ts` | Timeouts 15 s action, 30 s navigation, 60 s test; traces on failure/retry, screenshots and video on failure [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-03-scaffold-framework.md:L175] [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-03-scaffold-framework.md:L177] [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-03-scaffold-framework.md:L179] |
| `{test_dir}/support/fixtures/` | Fixture folder [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-03-scaffold-framework.md:L124] |
| `{test_dir}/support/merged-fixtures.ts` | Sole `test` import when Playwright Utils is on [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-03-scaffold-framework.md:L310] |
| `.env.example` | `TEST_ENV`, `BASE_URL`, `API_URL` [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-03-scaffold-framework.md:L209] |
| `tests/conftest.py` + `unit`, `integration`, `api` | pytest backends [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-03-scaffold-framework.md:L132] |
| `test:e2e` script | e.g. `npx playwright test` [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-04-docs-and-scripts.md:L58] |

Playwright Utils is installed only after confirmation (declining falls back to the disabled branch); Pact scaffolding sits behind a relevance gate. [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-03-scaffold-framework.md:L261] [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-03-scaffold-framework.md:L269] [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-03-scaffold-framework.md:L154] The scaffold step reads `tea_execution_mode`. [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-03-scaffold-framework.md:L57]

## tea-enforce.cjs write-time hook

- Installed when the platform supports tool hooks (Claude Code via `.claude/settings.json`); skipped on Cursor, Windsurf and Codex, where test-review remains the enforcement path. [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-04-docs-and-scripts.md:L87] [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-04-docs-and-scripts.md:L87]
- Copied byte-for-byte to `.claude/hooks/tea-enforce.cjs`; `.tea/enforce-config.json` holds the stack's globs and `hookSha256`. [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-04-docs-and-scripts.md:L91] [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-04-docs-and-scripts.md:L97] [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-04-docs-and-scripts.md:L114]
- Registration is merged into an existing `.claude/settings.json`, never overwriting it: `PreToolUse` matcher `Write|Edit|MultiEdit`, `PostToolUse` matcher `Write|Edit|MultiEdit|Bash`, `Stop` runs `node $CLAUDE_PROJECT_DIR/.claude/hooks/tea-enforce.cjs --stop`. [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-04-docs-and-scripts.md:L137] [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-04-docs-and-scripts.md:L144] [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-04-docs-and-scripts.md:L150] [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-04-docs-and-scripts.md:L156]
- Blocks patterns such as `.only`, `waitForTimeout`, `Thread.sleep` (exit 2, stderr to the agent); modes `--pre` (default), `--post`, `--stop`. [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-04-docs-and-scripts.md:L85] [SRC:src/workflows/testarch/bmad-testarch-framework/resources/hooks/tea-enforce.cjs:L73] [SRC:src/workflows/testarch/bmad-testarch-framework/resources/hooks/tea-enforce.cjs:L1025]
- Fails open (malformed payload, unreadable config, internal error → exit 0); an invalid config disables enforcement for that call; with no config a broad default applies. [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-04-docs-and-scripts.md:L169] [SRC:src/workflows/testarch/bmad-testarch-framework/resources/hooks/tea-enforce.cjs:L842] [SRC:src/workflows/testarch/bmad-testarch-framework/resources/hooks/tea-enforce.cjs:L89]
- Rules come from test-review's `criteria-registry.md`; Playwright `testGlobs` = `{test_dir}/**/*.spec.{ts,js}`; k6 scripts are excluded from H1. [SRC:src/workflows/testarch/bmad-testarch-framework/resources/hooks/tea-enforce.cjs:L82] [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-04-docs-and-scripts.md:L120] [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-04-docs-and-scripts.md:L131]

## CI inputs and platform detection

- ci's own `workflow.yaml` variables: `ci_platform` `auto` (`github-actions`, `gitlab-ci`, `circle-ci`, `jenkins`, `azure-devops`, `harness`), `test_stack_type` `auto`, `test_framework` `auto` (`playwright`, `cypress`, `jest`, `vitest`). [SRC:src/workflows/testarch/bmad-testarch-ci/workflow.yaml:L22] [SRC:src/workflows/testarch/bmad-testarch-ci/workflow.yaml:L24] [SRC:src/workflows/testarch/bmad-testarch-ci/workflow.yaml:L25] The module-level config prompts offer wider value sets (for example `ci_platform: other`); see `pattern-config-and-registration.md`. [SRC:src/module.yaml:L159] [SRC:src/module.yaml:L191]
- Detection: a non-`auto` config wins; existing `.github/workflows/*.yml` → github-actions (update or replace asked); else the git remote (github.com / gitlab.com); else github-actions. [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-01-preflight.md:L134] [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-01-preflight.md:L102] [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-01-preflight.md:L108] [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-01-preflight.md:L109] [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-01-preflight.md:L110]
- An undeterminable stack defaults to fullstack. [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-01-preflight.md:L61]

## Generated pipeline files

| Platform | File | Template |
|----------|------|----------|
| github-actions | `.github/workflows/test.yml` | `github-actions-template.yaml` [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-02-generate-pipeline.md:L112] [SRC:src/workflows/testarch/bmad-testarch-ci/workflow.yaml:L28] |
| gitlab-ci | `.gitlab-ci.yml` | `gitlab-ci-template.yaml` [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-02-generate-pipeline.md:L113] |
| jenkins | `Jenkinsfile` | `jenkins-pipeline-template.groovy` [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-02-generate-pipeline.md:L114] |
| azure-devops | `azure-pipelines.yml` | `azure-pipelines-template.yaml` [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-02-generate-pipeline.md:L115] |
| harness | `.harness/pipeline.yaml` | `harness-pipeline-template.yaml` [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-02-generate-pipeline.md:L116] |
| circle-ci | `.circleci/config.yml` | none (first principles) [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-02-generate-pipeline.md:L117] |

Progress: `{test_artifacts}/ci-pipeline-progress.md`; the checklist also expects `docs/ci-secrets-checklist.md`. [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-01-preflight.md:L5] [SRC:src/workflows/testarch/bmad-testarch-ci/checklist.md:L106] Untrusted `${{ inputs.* }}` / `${{ github.event.* }}` go through `env:` intermediaries. [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-02-generate-pipeline.md:L125]

## CI quality gates

- Parallel sharded test stage (4 shards by default); HTML report, JUnit XML, traces/videos on failure; artifacts uploaded only on failure, 30-day retention. [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-02-generate-pipeline.md:L166] [SRC:src/workflows/testarch/bmad-testarch-ci/checklist.md:L57] [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-02-generate-pipeline.md:L177] [SRC:src/workflows/testarch/bmad-testarch-ci/checklist.md:L81] [SRC:src/workflows/testarch/bmad-testarch-ci/checklist.md:L83]
- Burn-in (10 iterations) for flaky tests: on by default for frontend/fullstack, off for backend unless asked, new/changed flows only for mobile; `runBurnIn` replaces `--only-changed` with Playwright Utils. [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-03-configure-quality-gates.md:L49] [SRC:src/workflows/testarch/bmad-testarch-ci/checklist.md:L65] [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-03-configure-quality-gates.md:L70] [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-03-configure-quality-gates.md:L71] [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-03-configure-quality-gates.md:L72] [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-01-preflight.md:L132] [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-03-configure-quality-gates.md:L56]
- The gate must be able to fail: `continue-on-error` only on artifact collection; executed vs discovered test counts are compared. [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-03-configure-quality-gates.md:L74] [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-03-configure-quality-gates.md:L74]
- P0 100% pass, P1 ≥ 95%; fail on critical failures; traceability or nfr-assess output can be required before release. [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-03-configure-quality-gates.md:L105] [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-03-configure-quality-gates.md:L106] [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-03-configure-quality-gates.md:L107]
- Contract testing: `PACT_BROKER_BASE_URL` / `PACT_BROKER_TOKEN` secrets, `npm run test:pact:consumer` as its own step, `can-i-deploy` (with `--retry-while-unknown=10 --retry-interval=30`) before staging/production. [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-02-generate-pipeline.md:L257] [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-02-generate-pipeline.md:L225] [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-02-generate-pipeline.md:L239] [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-03-configure-quality-gates.md:L120] [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-01-preflight.md:L133]
- GitHub Actions template: weekly burn-in Sundays 02:00 UTC, burn-in only on PRs or schedule. [SRC:src/workflows/testarch/bmad-testarch-ci/github-actions-template.yaml:L22] [SRC:src/workflows/testarch/bmad-testarch-ci/github-actions-template.yaml:L128]

## Modes and HALTs

- Framework: Resume, Validate, Edit; resume counts 5 steps and halts with no progress or when already complete; step 5 validates against `checklist.md`; the checklist recommends ci next. [SRC:src/workflows/testarch/bmad-testarch-framework/SKILL.md:L83] [SRC:src/workflows/testarch/bmad-testarch-framework/SKILL.md:L84] [SRC:src/workflows/testarch/bmad-testarch-framework/SKILL.md:L85] [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-01b-resume.md:L71] [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-01b-resume.md:L48] [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-01b-resume.md:L89] [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-05-validate-and-summary.md:L39] [SRC:src/workflows/testarch/bmad-testarch-framework/checklist.md:L302]
- CI HALTs: not a Git repository, no framework config ("Run framework workflow first"), failing local test run, no progress on resume. [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-01-preflight.md:L44] [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-01-preflight.md:L81] [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-01-preflight.md:L94] [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-01b-resume.md:L48]
- Validate reports: `{test_artifacts}/framework-validation-report-…md`, `{test_artifacts}/ci-validation-report-…md` (with a script-injection scan); never overwritten. [SRC:src/workflows/testarch/bmad-testarch-framework/steps-v/step-01-validate.md:L4] [SRC:src/workflows/testarch/bmad-testarch-framework/steps-v/step-01-validate.md:L29] [SRC:src/workflows/testarch/bmad-testarch-ci/steps-v/step-01-validate.md:L4] [SRC:src/workflows/testarch/bmad-testarch-ci/steps-v/step-01-validate.md:L64]
