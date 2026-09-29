---
name: bmad-module-ultracode-goal-stack
description: >
  Stack skill for bmad-module-ultracode-goal — 5 libraries with 7 integration patterns,
  composed from tag-pinned skills for BMAD Method v6.12.0 (the installer and BMM skills),
  BMad Builder v2.2.2 and TEA v1.27.2, plus the docs-only Claude Code skill (pin v2.1.283,
  recorded for reference). Use when reasoning about how the
  installer discovers, configures and registers BMM, BMad Builder and TEA, where TEA's ATDD
  sits in the BMM story cycle, how deprecated v6 IDs flow through shims, or how installed
  skills and TEA's enforcement hook land in Claude Code's .claude/ folder. NOT for individual
  library usage outside this project's conventions.
---

# bmad-module-ultracode-goal Stack Skill

> 5 libraries | 7 integration patterns | Forge tier: Deep | compose-mode (no architecture document; every integration comes from a contract documented in a constituent skill)

## Integration Patterns

### Cross-Cutting Patterns

#### Module registration through `module.yaml` + `module-help.csv` (installer, BMM, BMad Builder, TEA)

The installer defines the registration contract, and the three modules ship to it:

- [from skill: bmad-method-installer] A module ships a `module.yaml` the installer can find. Its `code` becomes the module id, the `_bmad/<code>` folder and the `[modules.<code>]` TOML table. Keys with `prompt` become install questions (`scope: user` → `config.user.toml`, otherwise `config.toml`). `module-help.csv` sits at the module root with the 13 canonical columns and is merged into `_bmad/_config/bmad-help.csv` by `mergeModuleHelpCatalogs()`. Every skill is a folder whose `SKILL.md` frontmatter `name` equals the folder name (Adoption Steps 1–5).
- [from skill: bmad-method-bmm] BMM is registered by `src/bmm-skills/module.yaml` (artifact roots `planning_artifacts`, `implementation_artifacts`, `project_knowledge`) and `src/bmm-skills/module-help.csv`, whose `preceded-by` / `followed-by` columns drive catalog order and phase routing for `bmad-help` (Pattern Surface rows 1–2).
- [from skill: bmad-builder] `skills/module.yaml` registers code `bmb` (`default_selected: false`) with two prompt keys, `bmad_builder_output_folder` and `bmad_builder_reports`. `skills/module-help.csv` registers menu codes SB, BA, AA, BW, AW, CW, IM, CM and VM.
- [from skill: tea-testarch] `src/module.yaml` (config prompts) and `src/module-help.csv` (catalogue rows) register TEA. TEA is not selected by default, the installer inserts the core keys, and the installer creates `{test_artifacts}` declaratively. The CSV header carries the same 13 columns the installer's Key Types list.

**Confidence:** T1-low (constituent-documented-contract) [composed] — all four constituents are T1-low.

#### Deprecated v6 shims are opt-in on fresh v6.12.0 installs (BMM, installer, TEA, BMad Builder)

- [from skill: bmad-method-bmm] `bmad-create-story` and `bmad-dev-story` are deprecated (v6.11.0) but retained in full under `v6-shims/`. The official Phase 4 chain is `bmad-sprint-planning` → `bmad-build` → `bmad-code-review`. Deprecated core IDs forward to their replacements, and external module repos (gds, loop, tea, bmb, os-utils) still invoke the core IDs.
- [from skill: bmad-method-installer] v6.12.0: deprecated shims are opt-in on fresh installs; pass `--shims` to keep them. The choice is persisted as `installation.installShims` in `manifest.yaml`.
- [from skill: tea-testarch] TEA's ATDD slot is defined by those shim IDs: after `bmad-create-story:create` and before `bmad-dev-story`.

A fresh `npx bmad-method install` that does not opt in (no `--shims`, and no opt-in at the interactive shim prompt, which `--yes` skips) therefore leaves out both neighbours of TEA's documented ATDD slot. Neither skill says so directly, but BMM says every shim carries `metadata.lifecycle: shim` and the installer treats that marker as a shim, so the core shims bmb calls fall under the same opt-in (inferred).

**Confidence:** T1-low (constituent-documented-contract) [composed] — all constituents involved are T1-low.

#### `.claude/` as the landing zone (installer, TEA, Claude Code)

- [from skill: bmad-method-installer] With `--tools claude-code`, `_setupIdes()` copies every skill in `skill-manifest.csv` into `.claude/skills/<canonicalId>` (global target `~/.claude/skills`).
- [from skill: tea-testarch] `bmad-testarch-framework` copies `tea-enforce.cjs` to `.claude/hooks/tea-enforce.cjs` and merges `PreToolUse`, `PostToolUse` and `Stop` entries into the existing `.claude/settings.json`.
- [from skill: cc-primitives] `.claude/skills/<name>/SKILL.md` is the project skill location. `hooks` live in `~/.claude/settings.json`, `.claude/settings.json`, `.claude/settings.local.json` and skill or agent frontmatter, and entries merge across levels.

**Confidence:** T3 (constituent-documented-contract) [composed] — weakest constituent tier (cc-primitives, T3).

### Library Pair Integrations

#### bmad-method-installer + bmad-method-bmm

**Type:** Configuration Bridge
**Detection:** constituent-documented-contract — documented by both sides: bmad-method-installer (Pattern Surface, Quick Start) and bmad-method-bmm (Architecture at a Glance, "Installer")
**Pattern:** BMM is a built-in module. `OfficialModules.findModuleSource()` resolves core → bmm (`src/bmm-skills`) → external → custom. `generateModuleConfigs()` writes BMM's per-module `_bmad/bmm/config.yaml` with core keys spread in, and `writeCentralConfig()` writes its `module.yaml` answers to `[modules.bmm]` in `_bmad/config.toml` (user-scope answers go to `config.user.toml`). `mergeModuleHelpCatalogs()` merges BMM's `module-help.csv` from its module root into `_bmad/_config/bmad-help.csv`, and `_setupIdes()` copies every skill in `skill-manifest.csv` into `.claude/skills/<canonicalId>`. BMM skills are discovered recursively and installed under their own `name`, so `v6-shims/` nesting does not change the installed path. On a fresh v6.12.0 install, BMM's deprecated shims (`bmad-create-story`, `bmad-dev-story`, …) are opt-in: pass `--shims` to keep them (the installer's shim prompt is skipped under `--yes`, with an explicit flag, or without a TTY).
**Evidence:**
- [from skill: bmad-method-installer] Pattern Surface rows 5 (`findModuleSource()`: "Source lookup order core → bmm → external → custom"), 11 (`writeCentralConfig()`), 12 (`generateModuleConfigs()`: "Per-module `config.yaml` with core keys spread in") and 13 (`mergeModuleHelpCatalogs()`); Quick Start step 4 (`_setupIdes()`); Migration & Deprecation Warnings ("v6.12.0: deprecated shims are opt-in on fresh installs — pass `--shims` to keep them").
- [from skill: bmad-method-bmm] Architecture at a Glance ("**Installer** — skills are discovered recursively and installed under their own `name`; folder nesting does not change the installed path."); Pattern Surface rows 1–2; Migration & Deprecation Warnings (`--shims`).
**Key files:** `tools/installer/modules/official-modules.js`, `tools/installer/core/installer.js`, `tools/installer/core/manifest-generator.js`, `src/bmm-skills/module.yaml`, `src/bmm-skills/module-help.csv`
**Confidence:** T1-low (constituent-documented-contract) [composed]

#### bmad-method-installer + bmad-builder

**Type:** Configuration Bridge
**Detection:** constituent-documented-contract — documented by bmad-method-installer (`references/pattern-module-discovery.md`, "Finding an installed module's module.yaml"); bmad-builder mentions the installer only to scope it out ("Not for the BMAD Method BMM workflows or the installer.")
**Pattern:** BMad Builder (module code `bmb`, `default_selected: false`) keeps `module.yaml` and `module-help.csv` under `skills/`. The installer's `module.yaml` search covers that folder. For external registry clones it tries the registry `module_definition` path, then `skills/` and `src/` (one level deep), then the repo root, and `--list-options` checks `skills/module.yaml` in each cached external module. Offline, `resolveInstalledModuleYaml()` also checks `*-setup` skills for the BMB `{setup-skill}/assets/module.yaml` layout. Once found, `code: bmb` becomes `_bmad/bmb` and `[modules.bmb]`. The two prompt keys (`bmad_builder_output_folder`, `bmad_builder_reports`) go to `config.toml` unless a key declares `scope: user`, and `skills/module-help.csv` rows are merged into `bmad-help.csv`. BMad Builder's own `bmad-bmb-setup` (SB) is a separate configure path: it writes `config.yaml` and `config.user.yaml` into `{project-root}/_bmad`. Neither skill says how `bmb` reaches the installer: a registry entry, a marketplace plugin resolved through `.claude-plugin/marketplace.json`, or `--custom-source`.
**Evidence:**
- [from skill: bmad-method-installer] `references/pattern-module-discovery.md` ("`*-setup` skills at the repo root / `src/skills/` / `skills/` (BMB `{setup-skill}/assets/module.yaml`)"); Adoption Steps 1–4.
- [from skill: bmad-builder] Description (`skills/module.yaml` registers code `bmb`, `default_selected: false`); Configuration table (`bmad_builder_output_folder`, `bmad_builder_reports`); Usage Patterns row SB (`bmad-bmb-setup` : configure → `config.yaml` and `config.user.yaml` → `{project-root}/_bmad`).
**Key files:** `tools/installer/modules/external-manager.js`, `tools/installer/project-root.js`, `tools/installer/list-options.js`, `skills/module.yaml`, `skills/module-help.csv`
**Confidence:** T1-low (constituent-documented-contract) [composed]

#### bmad-method-bmm + bmad-builder

**Type:** Adapter/Wrapper
**Detection:** constituent-documented-contract — documented by bmad-method-bmm (`references/pattern-v6-shims.md`, "Core shim map"; `references/pattern-planning.md`, "bmad-architecture")
**Pattern:** BMAD v6 keeps deprecated core IDs as shims that forward to their replacements, for example `bmad-review-adversarial-general` → the `bmad-review` adversarial lens. The BMM skill catalogues the 6 core shims under `src/core-skills/v6-shims/` and records that external module repos, including `bmb`, still invoke the core IDs. Where shims are installed, a BMad Builder call on an old core ID goes through the shim rather than straight to the replacement. In the other direction, BMM's `bmad-architecture` sends misrouted asks to BMad Builder's `bmad-workflow-builder`.
**Evidence:**
- [from skill: bmad-method-bmm] `references/pattern-v6-shims.md`: "External module repos (gds, loop, tea, bmb, os-utils) still invoke the core IDs." and the core shim → replacement table; `references/pattern-planning.md`: "misrouted asks go to `bmad-prd`, `bmad-ux`, `bmad-spec`, `bmad-create-epics-and-stories` or `bmad-workflow-builder`."
- [from skill: bmad-builder] Description (module code `bmb`); Key Exports (`bmad-workflow-builder`: "Builds, edits, and analyzes workflows and skills.").
**Key files:** `src/core-skills/v6-shims/README.md`, `src/bmm-skills/plan/bmad-architecture/SKILL.md`, `skills/module.yaml`
**Confidence:** T1-low (constituent-documented-contract) [composed]

#### tea-testarch + bmad-method-bmm

**Type:** Middleware Chain
**Detection:** constituent-documented-contract — documented by tea-testarch (Adoption Steps; `references/pattern-config-and-registration.md`, "module-help.csv rows"; `references/pattern-atdd-and-automate.md`, "ATDD inputs and prerequisites"); BMM's skill scopes TEA out
**Pattern:** TEA's `module-help.csv` row puts `bmad-testarch-atdd` (AT, phase `4-implementation`) after `bmad-create-story:create` and before `bmad-dev-story`, with automate (TA) next. The story file is the artifact passed along the chain. ATDD needs an approved story with clear acceptance criteria and reads it from `{story_file}`; for BMM stories `story_key` is the filename without `.md`. BMM's `bmad-create-story` writes `{implementation_artifacts}/{{story_key}}.md` with `Status: ready-for-dev`, and `bmad-dev-story` takes an explicit `{{story_path}}` or else the first `ready-for-dev` story. ATDD writes `{test_artifacts}/atdd-checklist-{story_key}.md` and red-phase scaffolds that carry `test.skip()`. When the story file is writable it adds an `### ATDD Artifacts` subsection under `## Dev Notes` (a failed update does not fail the run), and it finishes by recommending dev-story, then automate. No TEA workflow is `required`, and create-story's completion points straight to dev-story, so the AT step runs only when an orchestrator or the user invokes it (inferred). In BMM 6.12.0 both neighbours of the AT slot are deprecated shims, retained in full but opt-in via `--shims` on fresh installs and dropped from `bmad-help`. TEA v1.27.2's skill never mentions `bmad-build`, the official Phase 4 implementation skill.
**Evidence:**
- [from skill: tea-testarch] Adoption Steps ("**Per story:** atdd (AT) after `bmad-create-story:create` and before `bmad-dev-story`, then automate (TA)."); `references/pattern-config-and-registration.md` ("No TEA workflow is `required`." and the AT row); `references/pattern-atdd-and-automate.md` ("for BMM stories `story_key` is the filename without `.md`", the `### ATDD Artifacts` subsection, "Scaffolds carry `test.skip()` in every execution mode").
- [from skill: bmad-method-bmm] `references/pattern-v6-shims.md` (create-story writes `{implementation_artifacts}/{{story_key}}.md` with `Status: ready-for-dev`; dev-story takes "the first story with status `ready-for-dev`"; both "Retained in full"); `references/pattern-release-context.md` (both deprecated in v6.11.0, dropped from `bmad-help`); Quick Start (Phase 4 chain).
**Key files:** `src/module-help.csv` (TEA), `src/workflows/testarch/bmad-testarch-atdd/workflow.yaml`, `src/workflows/testarch/bmad-testarch-atdd/steps-c/step-04-generate-tests.md`, `src/bmm-skills/v6-shims/bmad-create-story/SKILL.md`, `src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md`
**Confidence:** T1-low (constituent-documented-contract) [composed]

#### tea-testarch + bmad-method-installer

**Type:** Configuration Bridge
**Detection:** constituent-documented-contract — documented by tea-testarch (`references/pattern-config-and-registration.md`, "module.yaml"; Architecture at a Glance, "Registration"); the installer skill never names TEA
**Pattern:** TEA registers through `src/module.yaml` (config prompts) and `src/module-help.csv` (catalogue rows), the two module-root files the installer's Adoption Steps ask for. TEA's docs describe what the installer does for it. TEA is not selected by default. The installer inserts the core keys (`user_name`, `communication_language`, `document_output_language`, `output_folder`, `project_root`, `project_name`); TEA does not declare them. The installer also creates `{test_artifacts}` declaratively. The installer's generic contract is consistent with this: `_installAndConfigure()` copies each module into `_bmad/<code>`, creates declared directories and writes the per-module `config.yaml` with core keys spread in, and each non-core module's `module-help.csv` is merged into `_bmad/_config/bmad-help.csv`. TEA's CSV header lists the same 13 columns, in the same order, as the installer's Key Types. Every TEA workflow reads `{project-root}/_bmad/tea/config.yaml`, except that `tea_execution_mode` and `tea_capability_probe` resolve through CLI flags first, then that file, then `module.yaml`. Neither skill says how TEA reaches the installer (registry entry, `--custom-source` or preserved module). TEA's `module.yaml` at `src/module.yaml` falls inside the installer's `src/` search, but that is inferred.
**Evidence:**
- [from skill: tea-testarch] `references/pattern-config-and-registration.md` ("not selected by default in the installer", "are inserted by the installer, not declared by TEA", "The installer creates `{test_artifacts}` declaratively.", "All workflows read them from `{project-root}/_bmad/tea/config.yaml`."); Architecture at a Glance ("**Registration:** `src/module.yaml` (config prompts) and `src/module-help.csv` (catalogue rows)."); Migration & Deprecation Warnings (execution-mode resolution order).
- [from skill: bmad-method-installer] Adoption Steps 1–4; Quick Start step 3 (`_installAndConfigure()`); Key Types (`module-help.csv` columns (13)); Pattern Surface row 13 (`module-help.csv` → `_bmad/_config/bmad-help.csv`).
**Key files:** `src/module.yaml` (TEA), `src/module-help.csv` (TEA), `tools/installer/core/installer.js`, `tools/installer/modules/module-help-schema.js`, `tools/installer/modules/external-manager.js`
**Confidence:** T1-low (constituent-documented-contract) [composed]

#### tea-testarch + cc-primitives

**Type:** Event Handler
**Detection:** constituent-documented-contract — documented by tea-testarch (Gotchas, "Framework edits `.claude/settings.json`"; `references/pattern-framework-and-ci.md`, "tea-enforce.cjs write-time hook")
**Pattern:** `bmad-testarch-framework` installs `tea-enforce.cjs` when the platform supports tool hooks (Claude Code via `.claude/settings.json`); on Cursor, Windsurf and Codex it skips the hook and test-review remains the enforcement path. It copies the script byte-for-byte to `.claude/hooks/tea-enforce.cjs`, writes `.tea/enforce-config.json` (the stack's globs and `hookSha256`), and merges three entries into the existing `.claude/settings.json` without overwriting it: `PreToolUse` with matcher `Write|Edit|MultiEdit`, `PostToolUse` with matcher `Write|Edit|MultiEdit|Bash`, and `Stop` running `node $CLAUDE_PROJECT_DIR/.claude/hooks/tea-enforce.cjs --stop`. The script blocks patterns such as `.only`, `waitForTimeout` and `Thread.sleep` with exit 2 and stderr to the agent, and fails open: a malformed payload, an unreadable config or an internal error gives exit 0. On the Claude Code side, exit 2 is a blocking error whose stderr becomes the reason. On `PreToolUse`, exit 2 equals deny, and a deny holds even in `bypassPermissions`. On `Stop` it prevents stopping, so Claude keeps working, bounded by the 8-consecutive-block cap (cc-primitives tells Stop hooks to check `stop_hook_active`; neither skill says `tea-enforce.cjs` does). cc-primitives marks only `PreToolUse` as able to block a tool call ("before the call") and documents no PostToolUse control, so a `PostToolUse` exit 2 cannot be relied on to undo a write that already happened (inferred). Exit 0 is success to Claude Code, so TEA's fail-open path disables enforcement for that call, and any exit-0 stderr goes only to Claude Code's debug log (inferred: no visible signal).
**Evidence:**
- [from skill: tea-testarch] Gotchas ("On Claude Code it merges `PreToolUse`, `PostToolUse` and `Stop` entries for `.claude/hooks/tea-enforce.cjs` into the existing file, and the hook blocks writes with exit 2."); `references/pattern-framework-and-ci.md` (install condition, byte-for-byte copy, matcher list, "exit 2, stderr to the agent", fail-open rules).
- [from skill: cc-primitives] Key Types ("`2` = blocking error (stderr becomes the reason, and JSON `allow` cannot override it)"); `references/hooks.md` (Events: `PreToolUse` "before the call; can block"; PreToolUse control: "Exit 2 equals deny."; Stop and SubagentStop control: `stop_hook_active`, eight consecutive continuations); Common Workflows ("A deny holds even in `bypassPermissions`.").
**Key files:** `src/workflows/testarch/bmad-testarch-framework/steps-c/step-04-docs-and-scripts.md`, `src/workflows/testarch/bmad-testarch-framework/resources/hooks/tea-enforce.cjs`
**Confidence:** T3 (constituent-documented-contract) [composed] — weaker of the pair (cc-primitives, T3)

#### cc-primitives + bmad-method-installer

**Type:** Configuration Bridge
**Detection:** constituent-documented-contract — documented by bmad-method-installer (Quick Start, "with Claude Code as the tool target"; Pattern Surface row 19; `references/pattern-update-and-cleanup.md`, "IDE skill install and cleanup")
**Pattern:** Run with `--tools claude-code`, the installer's `_setupIdes()` phase copies every skill in `skill-manifest.csv` into `.claude/skills/<canonicalId>`. Cleanup runs first: it deletes the old folder, previously installed IDs and `removals.txt` entries, and keeps `bmad-os-*`. That target is the project skill location cc-primitives documents, `.claude/skills/<name>/SKILL.md`, which Claude Code loads from the start directory up to the repo root. The two sides differ in strictness. The installer skips any `SKILL.md` without `---` frontmatter at the very start and a string `name` equal to the folder name, so that skill never reaches `.claude/skills`. Claude Code treats every frontmatter field as optional and defaults `name` to the directory name. The installer also lists a global claude-code target (`~/.claude/skills`) and refuses to install when an ancestor already holds BMAD skills in the same target. cc-primitives documents `~/.claude/skills` as the personal scope, and a personal skill beats a same-named project skill.
**Evidence:**
- [from skill: bmad-method-installer] Quick Start (`npx bmad-method install --yes --directory <project> --modules bmm --tools claude-code`; step 4 "copy every skill in `skill-manifest.csv` into the tool's skill folder (`.claude/skills/<canonicalId>` for claude-code)"); Adoption Steps step 5; Pattern Surface row 19 (`platform-codes.yaml`, `.claude/skills` install folder); `references/pattern-update-and-cleanup.md` ("`claude-code` installs to `.claude/skills` (global `~/.claude/skills`)", cleanup, `ancestor_conflict_check`); `references/pattern-manifests-and-help.md` (frontmatter and `name` rule).
- [from skill: cc-primitives] Key API Summary (Skills: `.claude/skills/<name>/SKILL.md`); `references/skills-and-plugins.md` (skill locations and precedence, "Same-named skills: enterprise > personal > project"; optional frontmatter, `name` defaults to the directory name).
**Key files:** `tools/installer/core/installer.js`, `tools/installer/ide/platform-codes.yaml`, `tools/installer/ide/_config-driven.js`, `tools/installer/core/manifest-generator.js`
**Confidence:** T3 (constituent-documented-contract) [composed] — weaker of the pair (cc-primitives, T3)

### Hub Library Connections

- **bmad-method-installer** (4 partners: bmad-method-bmm, bmad-builder, tea-testarch, cc-primitives) — the registration and install hub. It resolves and configures every module (BMM built in; BMad Builder and TEA through their `module.yaml` and `module-help.csv`) and, with `--tools claude-code`, copies every skill in `skill-manifest.csv` into Claude Code's `.claude/skills/` (global `~/.claude/skills`).
- **bmad-method-bmm** (3 partners: bmad-method-installer, bmad-builder, tea-testarch) — owns the story loop and the BMM shims (`bmad-create-story`, `bmad-dev-story`) that TEA's ATDD slot names; its skill also catalogues the core shims under `src/core-skills/v6-shims/` that bmb's old core-ID calls go through.
- **tea-testarch** (3 partners: bmad-method-bmm, bmad-method-installer, cc-primitives) — the quality gate. It slots ATDD into the BMM story cycle, registers through the installer, and enforces test hygiene through Claude Code hooks.

## Library Catalog

5 libraries indexed in [references/stack-catalog.md](references/stack-catalog.md) — reference-index table + per-library summaries. Load it for a specific library's exports or role.

## Conventions

- **One registration contract.** A module is a folder with `module.yaml` (`code`, prompt keys) and a 13-column `module-help.csv`; every skill is a folder whose `SKILL.md` frontmatter `name` equals the folder name. [from skill: bmad-method-installer]
- **Configuration is installer output.** Answers land in `_bmad/config.toml` (team) or `_bmad/config.user.toml` (`scope: user`), and per-module `_bmad/<code>/config.yaml` is still generated; TEA workflows read `_bmad/tea/config.yaml`. `_bmad/<code>` is replaced wholesale on install, so set values with `--set <module>.<key>=<value>` instead of editing generated files. [from skill: bmad-method-installer] [from skill: tea-testarch]
- **Help routing is data-driven.** `preceded-by` / `followed-by` columns in each module's `module-help.csv` define skill sequences: the BMM Phase 4 chain, TEA's TD → TF → CI and AT → TA → RV → TR (NR after TA), and bmb's BA → AA, BW → AW and IM → CM → VM. [from skill: bmad-method-bmm] [from skill: tea-testarch] [from skill: bmad-builder]
- **Place ATDD by story state.** Run `bmad-testarch-atdd` once the story is `ready-for-dev` and before implementation starts; on the legacy loop that is between `bmad-create-story` and `bmad-dev-story`, which needs shims opted in (`--shims`, or the interactive shim prompt) on a fresh v6.12.0 install. TEA v1.27.2 documents only that placement; neither skill documents placing ATDD inside a `bmad-build` run. Neither skill documents BMM invoking ATDD or removing `test.skip()` (TEA leaves that to the developer), and test-review row C1 (CRITICAL) fires on skipped tests, so the orchestrator must invoke ATDD itself, and run test-review only after the developer removes `test.skip()`. [from skill: tea-testarch] [from skill: bmad-method-bmm]
- **Add hooks beside TEA's, never over them.** A settings file has one `hooks` object; add new events as sibling keys and keep TEA's three entries. Rely on the `PreToolUse` exit 2 to stop a write, and treat a `Stop` exit 2 as a re-prompt that Claude Code overrides after 8 consecutive blocks (a hook avoids loops only by checking `stop_hook_active`; neither skill says whether `tea-enforce.cjs --stop` does). `claude -p --bare` skips auto-discovery of hooks, so TEA's project hooks do not load there. [from skill: cc-primitives] [from skill: tea-testarch]
- **Name equals folder, always.** Author every module skill as `<canonicalId>/SKILL.md` with frontmatter on line 1 and a string `name` equal to the folder: Claude Code would load it without, but the installer would drop it. Treat `.claude/skills/<canonicalId>` as installer output and change skills at the module source. [from skill: bmad-method-installer] [from skill: cc-primitives]

## Constituents

| Skill | Version | Source | Forge tier | Confidence tier |
|-------|---------|--------|------------|-----------------|
| bmad-method-installer | 6.12.0 | https://github.com/bmad-code-org/BMAD-METHOD @ v6.12.0 | Deep | T1-low |
| bmad-method-bmm | 6.12.0 | https://github.com/bmad-code-org/BMAD-METHOD @ v6.12.0 | Deep | T1-low |
| bmad-builder | 2.2.2 | https://github.com/bmad-code-org/bmad-builder @ v2.2.2 | Quick | T1-low |
| tea-testarch | 1.27.2 | https://github.com/bmad-code-org/bmad-method-test-architecture-enterprise @ v1.27.2 | Deep | T1-low |
| cc-primitives | 2.1.283 | https://code.claude.com/docs (docs-only, fetched 2026-09-28; pin v2.1.283) | Deep | T3 |

Each constituent's confidence tier is the dominant bin of its `metadata.json` `confidence_distribution` (ties go to the weaker tier). Each integration takes the weaker tier of its pair, so every link involving cc-primitives is T3.
