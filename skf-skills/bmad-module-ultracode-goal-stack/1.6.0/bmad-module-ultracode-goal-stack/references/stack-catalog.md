# bmad-module-ultracode-goal Stack — Library Catalog

> Reference index + per-library summaries extracted from SKILL.md to keep the
> capstone under the body-size budget. See SKILL.md for integration patterns.

## Library Reference Index

| Library | Export Count | Key Exports | Confidence | Reference |
|---------|--------------|-------------|------------|-----------|
| bmad-method-installer | 118 | `Installer.install()`, `OfficialModules.findModuleSource()`, `generateModuleConfigs()`, `mergeModuleHelpCatalogs()`, `resolveInstalledModuleYaml()` | T1-low | [ref](bmad-method-installer.md) |
| cc-primitives | 16 | hooks (`PreToolUse`, `PostToolUse`, `SessionStart`, `Stop`), skills, plugins, settings, CLAUDE.md, `claude -p`, `/goal` | T3 | [ref](cc-primitives.md) |
| bmad-method-bmm | 37 | `bmad-sprint-planning`, `bmad-build`, `bmad-build-auto`, `bmad-code-review`, `bmad-create-story` / `bmad-dev-story` (shims) | T1-low | [ref](bmad-method-bmm.md) |
| tea-testarch | 9 | `bmad-testarch-framework`, `bmad-testarch-atdd`, `bmad-testarch-test-review`, `bmad-testarch-trace`, `bmad-tea` | T1-low | [ref](tea-testarch.md) |
| bmad-builder | 5 | `bmad-agent-builder`, `bmad-workflow-builder`, `bmad-module-builder`, `bmad-eval-runner`, `bmad-bmb-setup` | T1-low | [ref](bmad-builder.md) |
| graphify-kg | 0 (14 Pattern Surface rows) | `graphify update .`, `dispatch_command("update")`, `to_json()`, `claude_install()`, `hook-guard search` / `hook-guard read` | T1 | [ref](graphify-kg.md) |
| iwe-kg | 0 (22 Pattern Surface rows) | `iwe internal claude hook session-start`, `iwe internal claude hook post-tool`, `load_config()`, `enable_memory()`, `post_tool_report()` | T1-low | [ref](iwe-kg.md) |

## Per-Library Summaries

### bmad-method-installer
**Role in stack:** The `bmad` / `bmad-method` CLI (v6.12.0) that discovers, configures and registers every module (BMM built in; BMad Builder and TEA through their `module.yaml` and `module-help.csv`) and copies installed skills into `.claude/skills/<canonicalId>` for the `claude-code` target.
**Key exports used:** `Installer.install()`, `Installer.quickUpdate()`, `OfficialModules.findModuleSource()`, `generateModuleConfigs()`, `writeCentralConfig()`, `mergeModuleHelpCatalogs()`, `resolveInstalledModuleYaml()`, `loadRemovalLists()`
**Usage pattern:** `npx bmad-method install --yes --directory <project> --modules bmm --tools claude-code`; module authors satisfy the Adoption Steps (module.yaml, code, prompts, module-help.csv, SKILL.md name = folder, preserved modules, removals.txt); `--shims` keeps deprecated shims on a fresh v6.12.0 install.
**Confidence:** T1-low (source skill: Deep, reference-app; dominant bin t1_low)

### cc-primitives
**Role in stack:** The Claude Code v2.1.283 primitives the stack lands in: the `.claude/skills/` project skill layout, hooks registered in `.claude/settings.json` or a plugin's `hooks/hooks.json`, CLAUDE.md, and headless `claude -p`.
**Key exports used:** hooks (`PreToolUse`, `PostToolUse`, `SessionStart`, `Stop`, exit codes, `hookSpecificOutput.additionalContext`), skills (`.claude/skills/<name>/SKILL.md`, precedence), plugins (`hooks/hooks.json`, `/plugin install`), settings files, CLAUDE.md, `claude -p` / `--bare`, `/goal`
**Usage pattern:** A `PreToolUse` command hook denies a tool call with `permissionDecision: "deny"` or exit 2; a `Stop` hook blocks with `decision: "block"` or exit 2, guarded by `stop_hook_active`; a `PostToolUse` hook adds context through `hookSpecificOutput.additionalContext`; `SessionStart` cannot be blocked; project skills live at `.claude/skills/<name>/SKILL.md`; CLAUDE.md is context, not enforcement.
**Confidence:** T3 (source skill: docs-only, every claim cites an official docs page; dominant bin t3)

### bmad-method-bmm
**Role in stack:** The BMAD Method v6.12.0 planning and delivery skills an orchestrator drives, plus the v6 deprecation shims mapped to their replacements.
**Key exports used:** `bmad-sprint-planning`, `bmad-build`, `bmad-build-auto`, `bmad-code-review`, `bmad-retrospective`, `bmad-correct-course`, v6 shims (`bmad-create-story`, `bmad-dev-story`, …)
**Usage pattern:** Phase 4 chain `bmad-sprint-planning` → `bmad-build` → `bmad-code-review` (retrospective optional at epic end), sequenced in `module-help.csv` for `bmad-help`; the legacy story loop (`bmad-create-story` → `bmad-dev-story`) survives as shims and is where TEA's ATDD slot sits.
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

### graphify-kg
**Role in stack:** graphify v0.9.92 (PyPI `graphifyy`), the knowledge-graph CLI whose skill covers the UltraCode Goal Finalize refresh (`graphify update .`) and graphify's Claude Code wiring (`graphify install`, `graphify claude install`). None of the four BMAD constituents names graphify, so it meets the stack only through Claude Code.
**Key exports used:** `graphify update .` (`dispatch_command("update")` → `_rebuild_code()`), `to_json()`, `backup_if_protected()`, `claude_install()`, `claude_uninstall()`, `hook-guard search` / `hook-guard read`
**Usage pattern:** Finalize runs `GRAPHIFY_NO_AUTO_REFRESH=1 timeout 300 graphify update .` from `{project-root}` with no other flags or variables (the assignment turns off graphify's housekeeping outside `graphify-out/`; an allow rule must name the whole line) and logs any non-zero exit, timeout or refusal as one `WARN graphify-refresh-failed` line in `.decision-log.md` (graphify-kg's generic shell form is `timeout 300 graphify update . || echo "graphify-refresh-failed: $?"`, without the assignment): exit 0 updated or unchanged, 1 refused or failed, 2 bad arguments; a refusal leaves graph.json as it was, and `--force` is for an intended loss only. `graphify claude install` writes the `## graphify` section of `./CLAUDE.md` and two `PreToolUse` guards in `./.claude/settings.json`.
**Confidence:** T1 (source skill: Deep, reference-app; dominant bin t1, 77 AST-verified definitions)

### iwe-kg
**Role in stack:** IWE 0.28.0, the markdown knowledge-graph tooling behind this repository's IWE workspace and memory (`iwe`, `iwes`, `iwec`), and the IWE Claude Code plugin's `SessionStart` and `PostToolUse` hooks. None of the four BMAD constituents names IWE, so it meets the stack only through Claude Code.
**Key exports used:** `iwe internal claude hook session-start`, `iwe internal claude hook post-tool`, `load_config()`, `enable_memory()`, `enter_memory_store()`, `render_memory_index()`, `post_tool_report()`, `write_agent_instructions()` / `register_mcp()`
**Usage pattern:** Read and write the workspace through `iwe` from the folder holding `.iwe/config.toml` (`find` / `retrieve`; `update` and `delete` with `--dry-run`, `--expect` and `--strict`; `create` with `--strict` and the `--if-exists` collision policy, since `create` and `new` have no `--dry-run`). Memory is on when the config loads and a `MEMORY` document exists; the plugin hooks then print the `<iwe-memory>` index at session start and report schema problems after writes through `additionalContext`.
**Confidence:** T1-low (source skill: Deep, reference-app; dominant bin t1_low: t1 90, t1_low 138, t2 0, t3 14)
