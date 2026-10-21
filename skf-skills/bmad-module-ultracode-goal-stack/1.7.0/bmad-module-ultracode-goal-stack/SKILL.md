---
name: bmad-module-ultracode-goal-stack
description: >
  Stack skill for bmad-module-ultracode-goal — 7 libraries with 9 integration patterns,
  composed from tag-pinned skills for BMAD Method v6.12.0 (the installer and BMM skills),
  BMad Builder v2.2.2, TEA v1.27.2, graphify v0.9.92 and IWE 0.28.0, plus the docs-only
  Claude Code skill (pin v2.1.306, recorded for reference). Use when reasoning about how the
  installer discovers, configures and registers BMM, BMad Builder and TEA, where TEA's ATDD
  sits in the BMM story cycle, how deprecated v6 IDs flow through shims, how installed
  skills and TEA's enforcement hook land in Claude Code's .claude/ folder, or how graphify's
  Claude Code install and the IWE plugin's hooks share Claude Code's hook layer with TEA.
  NOT for individual library usage outside this project's conventions.
---

# bmad-module-ultracode-goal Stack Skill

> 7 libraries | 9 integration patterns | Forge tier: Deep | compose-mode (no architecture document; every integration comes from a contract documented in a constituent skill)

## Integration Patterns

Compact form. The full entries, with every `[from skill: …]` evidence line, are in [references/integration-patterns.md](references/integration-patterns.md).

### Cross-Cutting Patterns

Full entries: [references/integration-patterns.md](references/integration-patterns.md#cross-cutting-patterns).

#### Module registration through `module.yaml` + `module-help.csv` (installer, BMM, BMad Builder, TEA)

- **Installer:** a module's `module.yaml` `code` becomes the module id, `_bmad/<code>` and `[modules.<code>]`; `prompt` keys become install questions (`scope: user` → `config.user.toml`, otherwise `config.toml`); the module-root `module-help.csv` (13 columns) is merged into `_bmad/_config/bmad-help.csv` by `mergeModuleHelpCatalogs()`. The pinned v6.12.0 `parseSkillMd()` skips a skill whose `SKILL.md` `name` differs from its folder name or whose `description` is not a non-empty string.
- **BMM:** `src/bmm-skills/module.yaml`, `src/bmm-skills/module-help.csv` (`preceded-by` / `followed-by` drive `bmad-help` routing).
- **BMad Builder:** `skills/module.yaml` (code `bmb`, `default_selected: false`), `skills/module-help.csv` (menu codes SB, BA, AA, BW, AW, CW, IM, CM, VM).
- **TEA:** `src/module.yaml`, `src/module-help.csv`; not selected by default; the installer inserts the core keys and creates `{test_artifacts}` declaratively.

**Confidence:** T1-low (constituent-documented-contract) [composed]

#### Deprecated v6 shims are opt-in on fresh v6.12.0 installs (BMM, installer, TEA, BMad Builder)

- **BMM:** `bmad-create-story` and `bmad-dev-story` are deprecated (v6.11.0) but retained in full under `v6-shims/`; the official Phase 4 chain is `bmad-sprint-planning` → `bmad-build` → `bmad-code-review`; external module repos (gds, loop, tea, bmb, os-utils) still invoke the core IDs.
- **Installer:** v6.12.0: deprecated shims are opt-in on fresh installs (`--shims`, persisted as `installation.installShims` in `manifest.yaml`).
- **TEA:** the ATDD slot sits after `bmad-create-story:create` and before `bmad-dev-story`.
- **BMad Builder:** the `bmb` that BMM's list names.

So a fresh install that does not opt in (no `--shims`, and no opt-in at the interactive shim prompt, which `--yes` skips) leaves out both neighbours of TEA's ATDD slot, and the core shims that bmb and TEA call fall under the same opt-in (inferred).

**Confidence:** T1-low (constituent-documented-contract) [composed]

#### `.claude/` as the landing zone (installer, TEA, Claude Code)

- **Installer:** with `--tools claude-code`, `_setupIdes()` copies every skill in `skill-manifest.csv` into `.claude/skills/<canonicalId>` (global target `~/.claude/skills`).
- **TEA:** `bmad-testarch-framework` copies `tea-enforce.cjs` to `.claude/hooks/tea-enforce.cjs` and merges `PreToolUse`, `PostToolUse` and `Stop` entries into the existing `.claude/settings.json`.
- **Claude Code:** `.claude/skills/<name>/SKILL.md` is the project skill location; `hooks` live in `~/.claude/settings.json`, `.claude/settings.json`, `.claude/settings.local.json` and skill or agent frontmatter, and entries merge across levels.

**Confidence:** T3 (constituent-documented-contract) [composed]

#### Three hook owners on one Claude Code hook layer (TEA, graphify, IWE, Claude Code)

- **TEA** (`.claude/settings.json`): `PreToolUse` (matcher `Write|Edit|MultiEdit`), `PostToolUse` (matcher `Write|Edit|MultiEdit|Bash`) and `Stop`; the hook blocks with exit 2.
- **graphify** (`./.claude/settings.json`): `PreToolUse` matcher `Bash|Grep` runs `{exe} hook-guard search`, matcher `Read|Glob` runs `{exe} hook-guard read`, each with `"timeout": 10`; the guard always exits 0.
- **IWE** (plugin `hooks/hooks.json`, 20 s timeouts): `SessionStart` (matcher `startup|resume|clear|compact|fork`) and `PostToolUse` (matcher `Write|Edit|MultiEdit|Bash`); both succeed silently when `iwe` is not on `PATH`.
- **Claude Code:** a matcher made only of letters, digits, `_`, `-`, spaces, commas and pipes is an exact string or list matched against `tool_name`; all matching hooks run in parallel.

So a successful `Write`, `Edit`, `MultiEdit` or `Bash` call runs TEA's and IWE's `PostToolUse` hooks side by side, while TEA's and graphify's `PreToolUse` tool lists share no tool (both inferred from the matcher strings). Only TEA's hook blocks through its exit code: graphify's guard denies only in strict mode, through `permissionDecision: "deny"`, IWE's PostToolUse command always ends in success, and `SessionStart` cannot be blocked.

**Confidence:** T3 (constituent-documented-contract) [composed]

### Library Pair Integrations

#### bmad-method-installer + bmad-method-bmm

**Type:** Configuration Bridge
**Pattern:** BMM is a built-in module: `OfficialModules.findModuleSource()` resolves core → bmm (`src/bmm-skills`) → external → custom, `generateModuleConfigs()` writes `_bmad/bmm/config.yaml` with core keys spread in, `writeCentralConfig()` writes `[modules.bmm]` in `_bmad/config.toml`, and `mergeModuleHelpCatalogs()` merges BMM's `module-help.csv` into `_bmad/_config/bmad-help.csv`. BMM skills are installed under their own `name`, so `v6-shims/` nesting does not change the installed path.
**Key files:** `tools/installer/modules/official-modules.js`, `tools/installer/core/installer.js`, `src/bmm-skills/module.yaml`
**Confidence:** T1-low (constituent-documented-contract) [composed]
**Refs:** [pair](references/integrations/bmad-method-installer-bmad-method-bmm.md) · [full](references/integration-patterns.md#bmad-method-installer--bmad-method-bmm)

#### bmad-method-installer + bmad-builder

**Type:** Configuration Bridge
**Pattern:** BMad Builder (code `bmb`) keeps `module.yaml` and `module-help.csv` under `skills/`, which the installer's `module.yaml` search covers, and `code: bmb` becomes `_bmad/bmb` and `[modules.bmb]`. On an installer-managed project `bmad-bmb-setup` (SB) is a migration, not a parallel configure path (pinned bmad-builder v2.2.2 source; neither constituent documents it): it reads the installer's `_bmad/bmb/config.yaml` and `_bmad/core/config.yaml` as legacy defaults and removes `_bmad/bmb`, `_bmad/core` and `_bmad/_config` with the installer's manifests and `bmad-help.csv`.
**Key files:** `tools/installer/modules/external-manager.js`, `tools/installer/project-root.js`, `skills/module.yaml`
**Confidence:** T1-low (constituent-documented-contract) [composed]
**Refs:** [pair](references/integrations/bmad-method-installer-bmad-builder.md) · [full](references/integration-patterns.md#bmad-method-installer--bmad-builder)

#### bmad-method-bmm + bmad-builder

**Type:** Adapter/Wrapper
**Pattern:** The BMM skill catalogues the 6 core shims under `src/core-skills/v6-shims/` and records that external module repos, including `bmb`, still invoke the core IDs, so where shims are installed a BMad Builder call on an old core ID goes through the shim. In the other direction, when the real ask is an agent, BMM's `bmad-architecture` invokes BMad Builder's `bmad-workflow-builder` instead, if the BMad Builder module is installed.
**Key files:** `src/core-skills/v6-shims/README.md`, `src/bmm-skills/plan/bmad-architecture/SKILL.md`, `skills/module.yaml`
**Confidence:** T1-low (constituent-documented-contract) [composed]
**Refs:** [pair](references/integrations/bmad-method-bmm-bmad-builder.md) · [full](references/integration-patterns.md#bmad-method-bmm--bmad-builder)

#### tea-testarch + bmad-method-bmm

**Type:** Middleware Chain
**Pattern:** TEA's `module-help.csv` puts `bmad-testarch-atdd` (AT, phase `4-implementation`) after `bmad-create-story:create` and before `bmad-dev-story`, with automate (TA) next; ATDD reads the story from `{story_file}` and writes `{test_artifacts}/atdd-checklist-{story_key}.md` and red-phase `test.skip()` scaffolds. No TEA workflow is `required` and create-story's completion lists dev-story next, so the AT step runs only when an orchestrator or the user invokes it (inferred); TEA v1.27.2's skill never mentions `bmad-build`.
**Key files:** `src/module-help.csv` (TEA), `src/workflows/testarch/bmad-testarch-atdd/workflow.yaml`, `src/bmm-skills/v6-shims/bmad-create-story/SKILL.md`
**Confidence:** T1-low (constituent-documented-contract) [composed]
**Refs:** [pair](references/integrations/tea-testarch-bmad-method-bmm.md) · [full](references/integration-patterns.md#tea-testarch--bmad-method-bmm)

#### tea-testarch + bmad-method-installer

**Type:** Configuration Bridge
**Pattern:** TEA registers through `src/module.yaml` and `src/module-help.csv`; the installer inserts the core keys, and every TEA workflow reads `{project-root}/_bmad/tea/config.yaml`. `copyModuleWithFiltering()` does not copy a module's root `module.yaml`, so `_bmad/tea/` has none after install (inferred), and the headless `tea-test-review` CLI, after CLI flags and `_bmad/tea/config.yaml`, reads no file (pinned v1.27.2 source; tea-testarch says `module.yaml`) and falls back to `MODULE_DEFAULTS` (`tea_execution_mode: 'auto'`, `tea_capability_probe: true`), which TEA's tests keep equal to `src/module.yaml`.
**Key files:** `src/module.yaml` (TEA), `src/module-help.csv` (TEA), `tools/installer/core/installer.js`
**Confidence:** T1-low (constituent-documented-contract) [composed]
**Refs:** [pair](references/integrations/tea-testarch-bmad-method-installer.md) · [full](references/integration-patterns.md#tea-testarch--bmad-method-installer)

#### tea-testarch + cc-primitives

**Type:** Event Handler
**Pattern:** `bmad-testarch-framework` copies `tea-enforce.cjs` byte-for-byte to `.claude/hooks/tea-enforce.cjs` and merges its `PreToolUse` (`--pre`), `PostToolUse` (`--post`) and `Stop` (`--stop`) entries into the existing `.claude/settings.json`; on Cursor, Windsurf and Codex it skips the hook. The script blocks patterns such as `.only`, `waitForTimeout` and `Thread.sleep` with exit 2 (on `PreToolUse` a deny, which holds even in `bypassPermissions`) and fails open with exit 0 on a malformed payload, an unreadable config or an internal error. The pinned v1.27.2 script returns 0 without sweeping when `stop_hook_active` is true, so `--stop` never blocks twice in a row.
**Key files:** `src/workflows/testarch/bmad-testarch-framework/steps-c/step-04-docs-and-scripts.md`, `src/workflows/testarch/bmad-testarch-framework/resources/hooks/tea-enforce.cjs`
**Confidence:** T3 (constituent-documented-contract) [composed]
**Refs:** [pair](references/integrations/tea-testarch-cc-primitives.md) · [full](references/integration-patterns.md#tea-testarch--cc-primitives)

#### cc-primitives + bmad-method-installer

**Type:** Configuration Bridge
**Pattern:** With `--tools claude-code`, `_setupIdes()` copies every skill in `skill-manifest.csv` into `.claude/skills/<canonicalId>`, the project skill location cc-primitives documents. The installer skips any `SKILL.md` that lacks `---` frontmatter at the very start, a non-empty string `name` equal to the folder name, or a non-empty string `description` (pinned v6.12.0 `parseSkillMd()`), while Claude Code treats every frontmatter field as optional. The v6.12.0 `claude-code` entry in `platform-codes.yaml` does not set `ancestor_conflict_check`, so a claude-code install skips that check.
**Key files:** `tools/installer/core/installer.js`, `tools/installer/ide/platform-codes.yaml`, `tools/installer/core/manifest-generator.js`
**Confidence:** T3 (constituent-documented-contract) [composed]
**Refs:** [pair](references/integrations/cc-primitives-bmad-method-installer.md) · [full](references/integration-patterns.md#cc-primitives--bmad-method-installer)

#### graphify-kg + cc-primitives

**Type:** Event Handler
**Pattern:** `graphify claude install` puts a `## graphify` section into `./CLAUDE.md` and, every time, its two `PreToolUse` guards into `./.claude/settings.json`, stripping graphify's earlier entries, keeping every other hook and refusing a `settings.json` that is not a JSON object (exit 1). The guard always exits 0; with `--strict` (or `GRAPHIFY_HOOK_STRICT`) it denies at most one raw Read of an indexed, non-stale in-project file per session through `hookSpecificOutput.permissionDecision: "deny"`. `./CLAUDE.md` is context, not enforced configuration.
**Key files:** `graphify/install.py`, `graphify/cli.py`, `graphify/always_on/claude-md.md`
**Confidence:** T3 (constituent-documented-contract) [composed]
**Refs:** [pair](references/integrations/graphify-kg-cc-primitives.md) · [full](references/integration-patterns.md#graphify-kg--cc-primitives)

#### iwe-kg + cc-primitives

**Type:** Event Handler
**Pattern:** The IWE plugin (`iwe-org/skills` 0.14.0: `/plugin marketplace add iwe-org/skills`, then `/plugin install iwe@iwe-org`) registers its hooks in `hooks/hooks.json`: `iwe internal claude hook session-start` prints the `<iwe-memory>` block or nothing, and `iwe internal claude hook post-tool` prints one JSON line with `hookSpecificOutput.additionalContext`, or nothing; both print nothing without a `MEMORY` document. Claude Code adds a SessionStart hook's plain-text stdout (on exit 0) to Claude's context (per the hooks page cc-primitives cites), so the block reaches Claude on documented behaviour from both sides; under `claude -p --bare` the hooks of an IWE plugin installed with `/plugin install` do not run.
**Key files:** `hooks/hooks.json` (iwe-org/skills), `crates/iwe/src/internal/claude/hook/post_tool.rs`, `crates/iwe/src/internal/claude/hook/store.rs`
**Confidence:** T3 (constituent-documented-contract) [composed]
**Refs:** [pair](references/integrations/iwe-kg-cc-primitives.md) · [full](references/integration-patterns.md#iwe-kg--cc-primitives)

### Hub Library Connections

- **bmad-method-installer** (4: bmad-method-bmm, bmad-builder, tea-testarch, cc-primitives): the registration and install hub.
- **cc-primitives** (4: tea-testarch, bmad-method-installer, graphify-kg, iwe-kg): the host layer.
- **bmad-method-bmm** (3: bmad-method-installer, bmad-builder, tea-testarch): the story loop and the BMM shims.
- **tea-testarch** (3: bmad-method-bmm, bmad-method-installer, cc-primitives): the quality gate.

## Library Catalog

7 libraries indexed in [references/stack-catalog.md](references/stack-catalog.md) — reference-index table + per-library summaries. Load it for a specific library's exports or role.

## Conventions

- **One registration contract.** A module is a folder with `module.yaml` (`code`, prompt keys) and a 13-column `module-help.csv`; every skill is a folder whose `SKILL.md` frontmatter `name` equals the folder name, with a non-empty `description` (the pinned v6.12.0 `parseSkillMd()` skips a skill without one). [from skill: bmad-method-installer]
- **Configuration is installer output.** Answers land in `_bmad/config.toml` (team) or `_bmad/config.user.toml` (`scope: user`), and per-module `_bmad/<code>/config.yaml` is still generated; TEA workflows read `_bmad/tea/config.yaml`. `_bmad/<code>` is replaced wholesale on install, so set string values with `--set <module>.<key>=<value>` instead of editing generated files. `--set` writes every value as a quoted string, so change boolean keys such as TEA's `tea_use_playwright_utils`, `tea_use_pactjs_utils` and `tea_capability_probe` through the installer's prompts in an interactive re-install instead. [from skill: bmad-method-installer] [from skill: tea-testarch]
- **Help routing is data-driven.** `preceded-by` / `followed-by` columns in each module's `module-help.csv` define skill sequences: the BMM Phase 4 chain, TEA's TD → TF → CI and AT → TA → RV → TR (NR after TA), and bmb's BA → AA, BW → AW and IM → CM → VM. [from skill: bmad-method-bmm] [from skill: tea-testarch] [from skill: bmad-builder]
- **Place ATDD by story state.** Run `bmad-testarch-atdd` once the story is `ready-for-dev` and before implementation starts; on the legacy loop that is between `bmad-create-story` and `bmad-dev-story`, which needs shims opted in (`--shims`, or the interactive shim prompt) on a fresh v6.12.0 install. TEA v1.27.2 documents only that placement; neither skill documents placing ATDD inside a `bmad-build` run. Neither skill documents BMM invoking ATDD or removing `test.skip()` (TEA leaves that to the developer), and test-review row C1 (CRITICAL) fires on skipped tests, so the orchestrator must invoke ATDD itself, and run test-review only after the developer removes `test.skip()`. [from skill: tea-testarch] [from skill: bmad-method-bmm] [from skill: bmad-method-installer]
- **Add hooks beside TEA's, never over them.** A settings file has one `hooks` object; add new events as sibling keys and keep TEA's three entries. Rely on the `PreToolUse` exit 2 to stop a write, and treat a `Stop` exit 2 as a single re-prompt: a hook avoids loops by checking `stop_hook_active`, and Claude Code overrides a hook after 8 consecutive blocks. Neither skill says whether `tea-enforce.cjs --stop` checks it, but the pinned v1.27.2 script returns 0 without sweeping when `stop_hook_active` is true, so it never blocks twice in a row. `claude -p --bare` skips auto-discovery of hooks, so TEA's project hooks do not load there. [from skill: cc-primitives] [from skill: tea-testarch]
- **Name equals folder, always.** Author every module skill as `<canonicalId>/SKILL.md` with frontmatter on line 1, a string `name` equal to the folder and a non-empty string `description`: Claude Code would load it without, but the installer would drop it. Treat `.claude/skills/<canonicalId>` as installer output and change skills at the module source. [from skill: bmad-method-installer] [from skill: cc-primitives]
- **Keep each hook owner's entries separate.** `.claude/settings.json` holds TEA's three `tea-enforce.cjs` entries and, after `graphify claude install`, graphify's two `PreToolUse` guards; IWE's hooks stay in its plugin's `hooks/hooks.json`. Re-run `graphify claude install` to refresh graphify's entries (it replaces only its own), and keep `settings.json` a JSON object, which graphify otherwise refuses to modify (exit 1). Count only on TEA's exit 2 to stop a tool call: graphify's guard always exits 0, and IWE's PostToolUse command always ends in success. [from skill: tea-testarch] [from skill: graphify-kg] [from skill: iwe-kg] [from skill: cc-primitives]
- **Start Claude Code at the workspace root.** IWE's hooks and skills use the session's working directory verbatim, and every `iwe` command that loads `.iwe/config.toml` reads it from the current directory only; graphify's read guard nudges only for targets inside the project (`CLAUDE_PROJECT_DIR` or the cwd), and `CLAUDE_PROJECT_DIR` is the session start root. [from skill: iwe-kg] [from skill: graphify-kg] [from skill: cc-primitives]

## Constituents

| Skill | Version | Source | Forge tier | Confidence tier |
|-------|---------|--------|------------|-----------------|
| bmad-method-installer | 6.12.0 | https://github.com/bmad-code-org/BMAD-METHOD @ v6.12.0 | Deep | T1-low |
| bmad-method-bmm | 6.12.0 | https://github.com/bmad-code-org/BMAD-METHOD @ v6.12.0 | Deep | T1-low |
| bmad-builder | 2.2.2 | https://github.com/bmad-code-org/bmad-builder @ v2.2.2 | Quick | T1-low |
| tea-testarch | 1.27.2 | https://github.com/bmad-code-org/bmad-method-test-architecture-enterprise @ v1.27.2 | Deep | T1-low |
| cc-primitives | 2.1.306 | https://code.claude.com/docs (docs-only, fetched 2026-10-21; pin v2.1.306) | Deep | T3 |
| graphify-kg | 0.9.92 | https://github.com/Graphify-Labs/graphify @ v0.9.92 | Deep | T1 |
| iwe-kg | 0.28.0 | https://github.com/iwe-org/iwe @ iwe-v0.28.0 (plugin wiring: iwe-org/skills 0.14.0) | Deep | T1-low |

Each constituent's confidence tier is the dominant bin of its `metadata.json` `confidence_distribution` (ties go to the weaker tier). Each integration takes the weaker tier of its pair, so every link involving cc-primitives is T3.
