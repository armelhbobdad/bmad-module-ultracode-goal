# TEA config keys, registration and customization

## Contents

- [module.yaml](#moduleyaml)
- [Config keys](#config-keys)
- [module-help.csv rows](#module-helpcsv-rows)
- [bmad-tea agent and menu](#bmad-tea-agent-and-menu)
- [Knowledge index](#knowledge-index)
- [Workflow customize.toml](#workflow-customizetoml)

## module.yaml

- Display name "Test Architect"; not selected by default in the installer. [SRC:src/module.yaml:L2] [SRC:src/module.yaml:L6]
- One agent, `bmad-tea` (Murat), "Master Test Architect and Quality Advisor", team software-development. [SRC:src/module.yaml:L9] [SRC:src/module.yaml:L10] [SRC:src/module.yaml:L11] [SRC:src/module.yaml:L14]
- Core keys (`user_name`, `communication_language`, `document_output_language`, `output_folder`, `project_root`, `project_name`) are inserted by the installer, not declared by TEA. [SRC:src/module.yaml:L16]
- The installer creates `{test_artifacts}` declaratively. [SRC:src/module.yaml:L333]
- Keys used by workflows today: `tea_use_playwright_utils`, `tea_use_pactjs_utils`, `tea_pact_mcp`, `tea_browser_automation`, `tea_execution_mode`, `tea_capability_probe`, `test_stack_type`, `ci_platform`, `test_framework`; everything else is a future placeholder. [SRC:src/module.yaml:L25] [SRC:src/module.yaml:L28]

## Config keys

All workflows read them from `{project-root}/_bmad/tea/config.yaml`. [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L7] [SRC:src/workflows/testarch/bmad-testarch-test-design/workflow.yaml:L7] [SRC:src/workflows/testarch/bmad-testarch-nfr/workflow.yaml:L7] [SRC:src/workflows/testarch/bmad-testarch-atdd/workflow.yaml:L7] [SRC:src/workflows/testarch/bmad-testarch-automate/workflow.yaml:L7]

| Key | Default | Values / notes |
|-----|---------|----------------|
| `test_artifacts` | `{output_folder}/test-artifacts` | Absolute, prefixed with `{project-root}`; root of every TEA output [SRC:src/module.yaml:L31] [SRC:src/module.yaml:L32] [SRC:src/module.yaml:L33] |
| `tea_use_playwright_utils` | `true` | Real boolean; `false` generates from scratch; used by automate, atdd, framework, test-design, test-review, ci [SRC:src/module.yaml:L36] [SRC:src/module.yaml:L35] [SRC:src/module.yaml:L41] [SRC:src/module.yaml:L47] |
| `tea_use_pactjs_utils` | `true` | Binds any Pact suite TEA writes; `false` = raw Pact [SRC:src/module.yaml:L51] [SRC:src/module.yaml:L55] [SRC:src/module.yaml:L61] |
| `tea_pact_mcp` | `"mcp"` | `"mcp"` or `"none"`; broker steps degrade when MCP tools are unreachable [SRC:src/module.yaml:L65] [SRC:src/module.yaml:L66] [SRC:src/module.yaml:L76] |
| `tea_browser_automation` | `"auto"` | `"auto"`, `"cli"` (Playwright CLI only), `"mcp"`, `"none"` [SRC:src/module.yaml:L80] [SRC:src/module.yaml:L87] [SRC:src/module.yaml:L89] [SRC:src/module.yaml:L93] |
| `tea_execution_mode` | `"auto"` | `"auto"`, `"subagent"`, `"agent-team"`, `"sequential"`; auto tries agent-team → subagent → sequential [SRC:src/module.yaml:L97] [SRC:src/module.yaml:L104] [SRC:src/module.yaml:L110] [SRC:src/module.yaml:L280] |
| `tea_capability_probe` | `true` | Probe runtime support and fall back; `false` honours the mode strictly [SRC:src/module.yaml:L113] [SRC:src/module.yaml:L122] |
| `test_stack_type` | `auto` | `frontend`, `backend`, `fullstack`, `mobile`; detection checks mobile first [SRC:src/module.yaml:L139] [SRC:src/module.yaml:L237] |
| `ci_platform` | `auto` | `github-actions`, `gitlab-ci`, `jenkins`, `azure-devops`, `harness`, `circle-ci`, `other`; missing on old installs → `auto` [SRC:src/module.yaml:L159] [SRC:src/module.yaml:L250] |
| `test_framework` | `auto` | `playwright`, `cypress`, `jest`, `vitest`, `pytest`, `junit`, `go-test`, `dotnet-test`, `rspec`, `maestro`, `other` [SRC:src/module.yaml:L191] |
| `risk_threshold` | `"p1"` | Future; `p0`–`p3` [SRC:src/module.yaml:L195] [SRC:src/module.yaml:L198] [SRC:src/module.yaml:L208] |
| `test_design_output`, `test_review_output`, `trace_output` | `test-design`, `test-reviews`, `traceability` | Future output-folder keys, not wired into workflows [SRC:src/module.yaml:L210] [SRC:src/module.yaml:L215] [SRC:src/module.yaml:L219] [SRC:src/module.yaml:L224] |

These are the install-time prompt values; individual workflows declare their own narrower variable lists (for example ci's `workflow.yaml`). [SRC:src/workflows/testarch/bmad-testarch-ci/workflow.yaml:L22] [SRC:src/workflows/testarch/bmad-testarch-ci/workflow.yaml:L25]

Playwright Utils installs `@seontechnologies/playwright-utils` (peer `@playwright/test` ≥ 1.54.1); the remote Pact flow needs `PACT_BROKER_BASE_URL` and `PACT_BROKER_TOKEN`. [SRC:src/module.yaml:L300] [SRC:src/module.yaml:L301] [SRC:src/module.yaml:L315]

## module-help.csv rows

Columns: `module, skill, display-name, menu-code, description, action, args, phase, preceded-by, followed-by, required, output-location, outputs`. [SRC:src/module-help.csv:L1] No TEA workflow is `required`.

| Skill | Code | Phase | Sequence and outputs |
|-------|------|-------|----------------------|
| `bmad-testarch-test-design` | TD | 3-solutioning | Followed by framework; test design document [SRC:src/module-help.csv:L4] |
| `bmad-testarch-framework` | TF | 3-solutioning | After test-design, before ci; framework scaffold [SRC:src/module-help.csv:L5] |
| `bmad-testarch-ci` | CI | 3-solutioning | After framework; ci config [SRC:src/module-help.csv:L6] |
| `bmad-testarch-atdd` | AT | 4-implementation | After `bmad-create-story:create`, before `bmad-dev-story`; atdd-checklist + red-phase tests [SRC:src/module-help.csv:L7] |
| `bmad-testarch-automate` | TA | 4-implementation | After atdd; test suite [SRC:src/module-help.csv:L8] |
| `bmad-testarch-test-review` | RV | 4-implementation | After automate; 0–100 review report [SRC:src/module-help.csv:L9] |
| `bmad-testarch-nfr` | NR | 4-implementation | After automate; nfr report [SRC:src/module-help.csv:L10] |
| `bmad-testarch-trace` | TR | 4-implementation | After test-review; traceability matrix + gate decision [SRC:src/module-help.csv:L11] |

`bmad-teach-me-testing` (TMT, 0-learning) is the ninth row and outside this skill; a `_meta` row points to the module's `llms.txt`. [SRC:src/module-help.csv:L3] [SRC:src/module-help.csv:L2]

## bmad-tea agent and menu

- Invoked when the user asks for Murat or the Test Architect; activation resolves the `agent` block with `resolve_customization.py --key agent`. [SRC:src/agents/bmad-tea/SKILL.md:L3] [SRC:src/agents/bmad-tea/SKILL.md:L23]
- Overrides: `_bmad/custom/{skill-name}.toml` (team) and `_bmad/custom/{skill-name}.user.toml` (personal); scalars override, tables deep-merge, keyed arrays replace/append, other arrays append. [SRC:src/agents/bmad-tea/SKILL.md:L28] [SRC:src/agents/bmad-tea/SKILL.md:L29] [SRC:src/agents/bmad-tea/SKILL.md:L31]
- Loads `{project-root}/_bmad/tea/config.yaml`; a message that clearly maps to one menu item dispatches directly, otherwise the numbered menu is shown; when facts support two or more items it asks one short question (e.g. RV vs TR). [SRC:src/agents/bmad-tea/SKILL.md:L49] [SRC:src/agents/bmad-tea/SKILL.md:L68] [SRC:src/agents/bmad-tea/SKILL.md:L70] [SRC:src/agents/bmad-tea/SKILL.md:L78] [SRC:src/agents/bmad-tea/SKILL.md:L86]
- Menu codes: TMT, TD, TF, CI, AT, TA, RV, NR, TR invoke the matching skills; `GATE` is a prompt that routes optional test-review → optional nfr-assess → trace Phase 2. [SRC:src/agents/bmad-tea/customize.toml:L63] [SRC:src/agents/bmad-tea/customize.toml:L68] [SRC:src/agents/bmad-tea/customize.toml:L73] [SRC:src/agents/bmad-tea/customize.toml:L78] [SRC:src/agents/bmad-tea/customize.toml:L83] [SRC:src/agents/bmad-tea/customize.toml:L88] [SRC:src/agents/bmad-tea/customize.toml:L98] [SRC:src/agents/bmad-tea/customize.toml:L103] [SRC:src/agents/bmad-tea/customize.toml:L108] [SRC:src/agents/bmad-tea/customize.toml:L93]
- Agent `customize.toml` is overwritten on update; name and title are fixed; each menu item has exactly one of `skill` or `prompt`. [SRC:src/agents/bmad-tea/customize.toml:L1] [SRC:src/agents/bmad-tea/customize.toml:L8] [SRC:src/agents/bmad-tea/customize.toml:L57]

## Knowledge index

`tea-index.csv` columns: `id, name, description, tags, tier, fragment_file`; the agent selects fragments from it and loads only those needed. [SRC:src/agents/bmad-tea/resources/tea-index.csv:L1] [SRC:src/agents/bmad-tea/SKILL.md:L113] Tiers include core (e.g. `library-integration-mandate`), extended and specialized (e.g. `pact-mcp`). [SRC:src/agents/bmad-tea/resources/tea-index.csv:L2] [SRC:src/agents/bmad-tea/resources/tea-index.csv:L6] [SRC:src/agents/bmad-tea/resources/tea-index.csv:L43] When test code is written or reviewed the agent loads `library-integration-mandate.md`, plus `playwright-utils-mandate.md` or `pact-mcp.md` according to the config flags. [SRC:src/agents/bmad-tea/SKILL.md:L116] [SRC:src/agents/bmad-tea/SKILL.md:L117] [SRC:src/agents/bmad-tea/SKILL.md:L119]

## Workflow customize.toml

Every workflow ships a `[workflow]` customize surface mirroring the agent's. [SRC:src/workflows/testarch/bmad-testarch-atdd/customize.toml:L4] [SRC:src/workflows/testarch/bmad-testarch-trace/customize.toml:L3]

| Key | Default | Effect |
|-----|---------|--------|
| `activation_steps_prepend` | `[]` | Runs before config load and greeting [SRC:src/workflows/testarch/bmad-testarch-atdd/customize.toml:L14] |
| `activation_steps_append` | `[]` | Runs after greeting, before the workflow [SRC:src/workflows/testarch/bmad-testarch-atdd/customize.toml:L20] |
| `persistent_facts` | `[]` | Literal facts or `file:` globs (lexical order) [SRC:src/workflows/testarch/bmad-testarch-atdd/customize.toml:L30] [SRC:src/workflows/testarch/bmad-testarch-trace/customize.toml:L32] |
| `on_complete` | `""` | Executed at the terminal step in any mode [SRC:src/workflows/testarch/bmad-testarch-atdd/customize.toml:L34] [SRC:src/workflows/testarch/bmad-testarch-atdd/customize.toml:L38] |

Overrides: scalars win, arrays append. [SRC:src/workflows/testarch/bmad-testarch-atdd/customize.toml:L9] Only test-review adds `headless` (skip greeting and menu, run Create), `review_files`, `output_file_override` and `generate_inline_comments`. [SRC:src/workflows/testarch/bmad-testarch-test-review/customize.toml:L46] [SRC:src/workflows/testarch/bmad-testarch-test-review/customize.toml:L40] [SRC:src/workflows/testarch/bmad-testarch-test-review/customize.toml:L53] [SRC:src/workflows/testarch/bmad-testarch-test-review/customize.toml:L56] [SRC:src/workflows/testarch/bmad-testarch-test-review/customize.toml:L66]
