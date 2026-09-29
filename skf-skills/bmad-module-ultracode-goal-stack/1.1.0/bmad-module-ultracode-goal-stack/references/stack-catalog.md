# bmad-module-ultracode-goal Stack — Library Catalog

> Reference index + per-library summaries extracted from SKILL.md to keep the
> capstone under the body-size budget. See SKILL.md for integration patterns.

## Library Reference Index

| Library | Export Count | Key Exports | Confidence | Reference |
|---------|--------------|-------------|------------|-----------|
| bmad-method-installer | 118 | `Installer.install()`, `OfficialModules.findModuleSource()`, `generateModuleConfigs()`, `mergeModuleHelpCatalogs()`, `resolveInstalledModuleYaml()` | T1-low | [ref](bmad-method-installer.md) |
| bmad-method-bmm | 37 | `bmad-sprint-planning`, `bmad-build`, `bmad-build-auto`, `bmad-code-review`, `bmad-create-story` / `bmad-dev-story` (shims) | T1-low | [ref](bmad-method-bmm.md) |
| tea-testarch | 9 | `bmad-testarch-framework`, `bmad-testarch-atdd`, `bmad-testarch-test-review`, `bmad-testarch-trace`, `bmad-tea` | T1-low | [ref](tea-testarch.md) |
| bmad-builder | 5 | `bmad-agent-builder`, `bmad-workflow-builder`, `bmad-module-builder`, `bmad-eval-runner`, `bmad-bmb-setup` | T1-low | [ref](bmad-builder.md) |
| cc-primitives | 16 | hooks (`PreToolUse`, `PostToolUse`, `Stop`), skills, settings, `claude -p`, `/goal` | T3 | [ref](cc-primitives.md) |

## Per-Library Summaries

### bmad-method-installer
**Role in stack:** The `bmad` / `bmad-method` CLI (v6.12.0) that discovers, configures and registers every module (BMM built in; BMad Builder and TEA through their `module.yaml` and `module-help.csv`) and copies installed skills into `.claude/skills/<canonicalId>` for the `claude-code` target.
**Key exports used:** `Installer.install()`, `Installer.quickUpdate()`, `OfficialModules.findModuleSource()`, `generateModuleConfigs()`, `writeCentralConfig()`, `mergeModuleHelpCatalogs()`, `resolveInstalledModuleYaml()`, `loadRemovalLists()`
**Usage pattern:** `npx bmad-method install --yes --directory <project> --modules bmm --tools claude-code`; module authors satisfy the Adoption Steps (module.yaml, code, prompts, module-help.csv, SKILL.md name = folder, preserved modules, removals.txt); `--shims` keeps deprecated shims on a fresh v6.12.0 install.
**Confidence:** T1-low (source skill: Deep, reference-app; dominant bin t1_low)

### bmad-method-bmm
**Role in stack:** The BMAD Method v6.12.0 planning and delivery skills an orchestrator drives, plus the v6 deprecation shims mapped to their replacements.
**Key exports used:** `bmad-sprint-planning`, `bmad-build`, `bmad-build-auto`, `bmad-code-review`, `bmad-retrospective`, `bmad-correct-course`, v6 shims (`bmad-create-story`, `bmad-dev-story`, …)
**Usage pattern:** Phase 4 chain `bmad-sprint-planning` → `bmad-build` → `bmad-code-review` (retrospective optional at epic end), routed through `module-help.csv`; the legacy story loop (`bmad-create-story` → `bmad-dev-story`) survives as shims and is where TEA's ATDD slot sits.
**Confidence:** T1-low (source skill: Deep, reference-app; dominant bin t1_low)

### tea-testarch
**Role in stack:** TEA v1.27.2, the quality gate: eight `bmad-testarch-*` workflows and the `bmad-tea` agent, configured through `_bmad/tea/config.yaml`, with `gate-decision.json` from `bmad-testarch-trace` as the gate signal.
**Key exports used:** `bmad-testarch-test-design` (TD), `bmad-testarch-framework` (TF), `bmad-testarch-ci` (CI), `bmad-testarch-atdd` (AT), `bmad-testarch-automate` (TA), `bmad-testarch-test-review` (RV), `bmad-testarch-nfr` (NR), `bmad-testarch-trace` (TR), `bmad-tea`
**Usage pattern:** Once per project TD → TF → CI; per story AT (after `bmad-create-story:create`, before `bmad-dev-story`) → TA, then RV and NR, then TR; read `gate_status` from `{test_artifacts}/gate-decision.json` and check `evaluated_at`. On Claude Code, TF installs the `tea-enforce.cjs` hook.
**Confidence:** T1-low (source skill: Deep, reference-app; dominant bin t1_low)

### bmad-builder
**Role in stack:** The BMad Builder v2.2.2 module (code `bmb`) whose skills build, analyze, convert, scaffold and validate agents, workflows and modules.
**Key exports used:** `bmad-agent-builder` (BA/AA), `bmad-workflow-builder` (BW/AW/CW), `bmad-module-builder` (IM/CM/VM), `bmad-eval-runner`, `bmad-bmb-setup` (SB)
**Usage pattern:** Build → quality analysis (BA → AA, BW → AW); ideate → create → validate a module (IM → CM → VM); outputs go to `bmad_builder_output_folder` (default `{project-root}/skills`) and reports to `bmad_builder_reports` (default `{project-root}/skills/reports`).
**Confidence:** T1-low (source skill: Quick, best-effort; dominant bin t1_low)

### cc-primitives
**Role in stack:** The Claude Code v2.1.283 primitives the stack lands in: the `.claude/skills/` project skill layout, hooks registered in `.claude/settings.json`, and headless `claude -p`.
**Key exports used:** hooks (`PreToolUse`, `PostToolUse`, `Stop`, exit codes), skills (`.claude/skills/<name>/SKILL.md`, precedence), settings files, `claude -p` / `--bare`, `/goal`
**Usage pattern:** A `PreToolUse` command hook denies a tool call with `permissionDecision: "deny"` or exit 2; a `Stop` hook blocks with `decision: "block"` or exit 2, guarded by `stop_hook_active`; project skills live at `.claude/skills/<name>/SKILL.md`.
**Confidence:** T3 (source skill: docs-only, every claim cites an official docs page; dominant bin t3)
