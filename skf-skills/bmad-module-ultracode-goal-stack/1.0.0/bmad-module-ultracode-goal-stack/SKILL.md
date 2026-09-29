---
name: bmad-module-ultracode-goal-stack
description: >
  Stack skill for bmad-module-ultracode-goal — 3 libraries with 3 integration patterns,
  composed from version-pinned skills for BMAD Method v6.12.0 (BMM skills and the installer)
  and BMad Builder v2.2.2. Use when reasoning about how a BMAD module is discovered,
  configured and registered by the installer next to BMM and BMad Builder, or how deprecated
  core IDs flow through the v6 shims. NOT for: individual library usage outside this
  project's conventions.
---

# bmad-module-ultracode-goal Stack Skill

> 3 libraries | 3 integration patterns | Forge tier: Deep | compose-mode (no architecture document; integrations come from contracts documented in the constituent skills)

## Integration Patterns

### Cross-Cutting Patterns

#### Module registration through `module.yaml` + `module-help.csv` (all 3 libraries)

The installer defines the registration contract every module follows, and both other constituents ship to it:

- [from skill: bmad-method-installer] a module ships a `module.yaml` the installer can find, whose `code` becomes the module id and `_bmad/<code>` folder; config keys whose value has `prompt` become install prompts (`scope: user` → `config.user.toml`, otherwise `config.toml`; `result` renders `{value}`); `module-help.csv` sits at the module root with 13 columns and is merged into `_bmad/_config/bmad-help.csv` (`mergeModuleHelpCatalogs()`).
- [from skill: bmad-method-bmm] BMM is registered by `src/bmm-skills/module.yaml` and `src/bmm-skills/module-help.csv`, whose `preceded-by` / `followed-by` columns drive catalog order and phase routing for `bmad-help`.
- [from skill: bmad-builder] BMad Builder is registered by `skills/module.yaml` (code `bmb`, keys `bmad_builder_output_folder` and `bmad_builder_reports`, each with `prompt` / `default` / `result: "{project-root}/{value}"`) and `skills/module-help.csv` (menu codes SB, BA, AA, BW, AW, CW, IM, CM, VM).

**Confidence:** T1-low (constituent-documented-contract) [composed] — weakest constituent tier (bmad-builder, Quick).

### Library Pair Integrations

#### bmad-method-installer + bmad-method-bmm

**Type:** Configuration Bridge
**Pattern:** BMM is a built-in module. The installer resolves module sources in the order core → bmm → external → custom (`OfficialModules.findModuleSource()`), writes BMM's per-module `config.yaml` plus the central `config.toml` / `config.user.toml` from its `module.yaml` prompts, merges `src/bmm-skills/module-help.csv` into `_bmad/_config/bmad-help.csv`, and copies every skill listed in `skill-manifest.csv` into `.claude/skills/<canonicalId>`. On a fresh v6.12.0 install, BMM's deprecated shims (`bmad-create-story`, `bmad-dev-story`, …) are only installed with `--shims`.
**Evidence:**
- [from skill: bmad-method-installer] `findModuleSource()` (Pattern Surface row 5), `generateModuleConfigs()` (row 12), `mergeModuleHelpCatalogs()` (row 13); Key Types cite `src/bmm-skills/module-help.csv` for the 13 columns; Migration notes `--shims` opt-in for v6.12.0.
- [from skill: bmad-method-bmm] `src/bmm-skills/module-help.csv` (Pattern Surface row 2); `bmad-create-story` and `bmad-dev-story` retained in full under `v6-shims/` (rows 19–20).
**Key files:** `tools/installer/modules/official-modules.js`, `tools/installer/core/installer.js`, `src/bmm-skills/module.yaml`, `src/bmm-skills/module-help.csv`
**Confidence:** T1 (constituent-documented-contract) [composed]

#### bmad-method-installer + bmad-builder

**Type:** Configuration Bridge
**Pattern:** BMad Builder is an external module (code `bmb`). For external registry modules the installer clones to `~/.bmad/cache/external-modules` and searches for `module.yaml` at the registry `module_definition` path, then `skills/` and `src/` (one level deep), then the repo root — BMad Builder keeps its `module.yaml` at `skills/module.yaml`. Offline, `resolveInstalledModuleYaml()` also checks `*-setup` skills under `skills/` (BMB `{setup-skill}/assets/module.yaml`). Its two prompt keys land in `_bmad/config.toml` under `[modules.bmb]`, and its `module-help.csv` rows are merged into `bmad-help.csv`. BMad Builder's own `bmad-bmb-setup` (menu SB) writes `config.yaml` and `config.user.yaml` into `{project-root}/_bmad`.
**Evidence:**
- [from skill: bmad-method-installer] Adoption Steps 1–4; `references/pattern-module-discovery.md` ("BMB `{setup-skill}/assets/module.yaml`").
- [from skill: bmad-builder] Configuration table (`bmad_builder_output_folder`, `bmad_builder_reports`); Usage Patterns row SB (`bmad-bmb-setup` : configure → `config.yaml and config.user.yaml` → `{project-root}/_bmad`).
**Key files:** `tools/installer/modules/external-manager.js`, `tools/installer/project-root.js`, `skills/module.yaml`, `skills/module-help.csv`
**Confidence:** T1-low (constituent-documented-contract) [composed]

#### bmad-method-bmm + bmad-builder

**Type:** Adapter/Wrapper
**Pattern:** BMAD v6 keeps deprecated core IDs as shims that forward to their replacements (for example `bmad-review-adversarial-general` → the `bmad-review` adversarial lens). The BMM skill records that external module repos — explicitly including `bmb` — still invoke the core IDs, so BMad Builder calls that use an old core ID pass through a v6 shim rather than the replacement skill.
**Evidence:**
- [from skill: bmad-method-bmm] `references/pattern-v6-shims.md`: "External module repos (gds, loop, tea, bmb, os-utils) still invoke the core IDs." and the core shim → replacement table.
- [from skill: bmad-builder] Key Exports: `bmad-agent-builder`, `bmad-workflow-builder`, `bmad-module-builder`, `bmad-eval-runner`, `bmad-bmb-setup` (module code `bmb`).
**Key files:** `src/core-skills/v6-shims/README.md`, `skills/*/SKILL.md` (bmad-builder)
**Confidence:** T1-low (constituent-documented-contract) [composed]

## Library Reference Index

| Library | Export Count | Key Exports | Confidence | Reference |
|---------|--------------|-------------|------------|-----------|
| bmad-method-installer | 118 | `Installer.install()`, `Installer.quickUpdate()`, `OfficialModules.findModuleSource()`, `mergeModuleHelpCatalogs()`, `resolveInstalledModuleYaml()` | T1 | [ref](references/bmad-method-installer.md) |
| bmad-method-bmm | 37 | `bmad-build`, `bmad-build-auto`, `bmad-sprint-planning`, `bmad-code-review`, `bmad-correct-course` | T1 | [ref](references/bmad-method-bmm.md) |
| bmad-builder | 5 | `bmad-agent-builder`, `bmad-workflow-builder`, `bmad-module-builder`, `bmad-eval-runner`, `bmad-bmb-setup` | T1-low | [ref](references/bmad-builder.md) |

## Per-Library Summaries

### bmad-method-installer
**Role in stack:** The `bmad` / `bmad-method` CLI (v6.12.0) that discovers, configures and registers every module, including external modules installed by their own CLI (kept as preserved modules).
**Key exports used:** `Installer.install()`, `Installer.quickUpdate()`, `OfficialModules.findModuleSource()`, `generateModuleConfigs()`, `mergeModuleHelpCatalogs()`, `resolveInstalledModuleYaml()`, `loadRemovalLists()`
**Usage pattern:** `npx bmad-method install --yes --directory <project> --modules bmm --tools claude-code`; module authors satisfy the seven Adoption Steps (module.yaml, code, prompts, module-help.csv, SKILL.md name = folder, preserved modules, removals.txt).
**Confidence:** T1 (source skill: Deep, reference-app)

### bmad-method-bmm
**Role in stack:** The BMAD Method v6.12.0 planning and delivery skills an orchestrator drives, plus the v6 deprecation shims mapped to their replacements.
**Key exports used:** `bmad-sprint-planning`, `bmad-build`, `bmad-build-auto`, `bmad-code-review`, `bmad-retrospective`, `bmad-correct-course`, v6 shims (`bmad-create-story`, `bmad-dev-story`, …)
**Usage pattern:** Phase 4 chain `bmad-sprint-planning` → `bmad-build` → `bmad-code-review` (retrospective optional at epic end), routed through `module-help.csv`.
**Confidence:** T1 (source skill: Deep, reference-app)

### bmad-builder
**Role in stack:** The BMad Builder v2.2.2 module (code `bmb`) whose skills build, analyze, convert, scaffold and validate agents, workflows and modules.
**Key exports used:** `bmad-agent-builder` (BA/AA), `bmad-workflow-builder` (BW/AW/CW), `bmad-module-builder` (IM/CM/VM), `bmad-eval-runner`, `bmad-bmb-setup` (SB)
**Usage pattern:** Build → quality analysis (BA → AA, BW → AW); ideate → create → validate a module (IM → CM → VM); outputs go to `bmad_builder_output_folder` (default `{project-root}/skills`) and reports to `bmad_builder_reports` (default `{project-root}/skills/reports`).
**Confidence:** T1-low (source skill: Quick, best-effort)

## Conventions

- **One registration contract.** A module is a folder with `module.yaml` (`code`, prompt keys) and a 13-column `module-help.csv`; every skill is a folder whose `SKILL.md` frontmatter `name` equals the folder name. [from skill: bmad-method-installer]
- **Configuration lands in `_bmad/`.** Answers go to `_bmad/config.toml` (team) or `_bmad/config.user.toml` (`scope: user`), with per-module `config.yaml` still generated. [from skill: bmad-method-installer]
- **Help routing is data-driven.** `preceded-by` / `followed-by` columns in each module's `module-help.csv` define skill sequences (BMM Phase 4 chain; bmb BA → AA, IM → CM → VM). [from skill: bmad-method-bmm] [from skill: bmad-builder]
- **Deprecated IDs keep working through shims.** Old core and BMM IDs forward to replacements (or, for `bmad-create-story` / `bmad-dev-story`, still run in full); a fresh v6.12.0 install includes them only with `--shims`. [from skill: bmad-method-bmm] [from skill: bmad-method-installer]

## Constituents

| Skill | Version | Source | Tier |
|-------|---------|--------|------|
| bmad-method-installer | 6.12.0 | https://github.com/bmad-code-org/BMAD-METHOD @ v6.12.0 | Deep |
| bmad-method-bmm | 6.12.0 | https://github.com/bmad-code-org/BMAD-METHOD @ v6.12.0 | Deep |
| bmad-builder | 2.2.2 | https://github.com/bmad-code-org/bmad-builder @ v2.2.2 | Quick |

Two campaign targets are not constituents because they failed their test gate: `tea-testarch` (TEA v1.27.2) and `cc-primitives` (Claude Code v2.1.283).
