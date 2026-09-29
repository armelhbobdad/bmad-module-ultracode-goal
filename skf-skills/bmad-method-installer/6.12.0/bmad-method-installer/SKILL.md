---
name: bmad-method-installer
description: >
  Module discovery and registration internals of the bmad-method v6.12.0 installer (npx bmad-method
  install): where it finds module.yaml for built-in, external and custom modules, how module-help.csv
  rows are merged into _bmad/_config/bmad-help.csv, how per-module config.yaml and the central
  config.toml / config.user.toml are generated and what a quick update rewrites, plus manifest.yaml,
  skill-manifest.csv, deprecation shims and removals.txt. Use when building or debugging a BMAD module
  that the installer must discover, register, configure, preserve or clean up. Not for the BMM skill
  workflows themselves (see bmad-method-bmm).
---

# bmad-method v6.12.0 installer — module registration contract

## Overview

Reference for the JavaScript installer under `tools/installer/` at tag `v6.12.0` of <https://github.com/bmad-code-org/BMAD-METHOD> (commit `05bfbd46`), compiled at Forge tier **Deep**.

- **Surface:** 39 CommonJS files; 154 names exported through `module.exports` barrels (15 classes, 95 functions, 44 constants), AST-verified (T1); behaviour claims cite verified source lines (T1-low); release notes and open issues add T2 context.
- **Shape:** reference-app — the value is the wiring contract a module must satisfy (where files live, which file names are read, what gets rewritten), not a library to import.
- **Entry point:** `bmad` / `bmad-method` CLI (`tools/installer/bmad-cli.js`) with `install`, `status`, `uninstall` commands. [SRC:tools/installer/bmad-cli.js:L80] [SRC:tools/installer/commands/install.js:L11] [SRC:tools/installer/commands/status.js:L13] [SRC:tools/installer/commands/uninstall.js:L10]

## Quick Start

Non-interactive install into a project, with Claude Code as the tool target:

```bash
npx bmad-method install --yes --directory <project> --modules bmm --tools claude-code
```

`--tools` is required for a fresh `--yes` install; `--modules` is a comma-separated list of module codes; `--yes` accepts every default. [SRC:tools/installer/commands/install.js:L18] [SRC:tools/installer/commands/install.js:L15] [SRC:tools/installer/commands/install.js:L39] [SRC:tools/installer/ide/platform-codes.js:L71] [SRC:tools/installer/ui.js:L752]

What one `install` run does, in order (`Installer.install()`):

1. Normalize input (`Config.build()`), resolve paths (`InstallPaths.create()`), detect an existing install (`ExistingInstall.detect()` on `_bmad`). [SRC:tools/installer/core/installer.js:L49] [SRC:tools/installer/core/installer.js:L50] [SRC:tools/installer/core/installer.js:L52]
2. On an update: remove deselected modules (never core or preserved ones) and back up custom/modified user files. [SRC:tools/installer/core/installer.js:L98] [SRC:tools/installer/core/installer.js:L99] [SRC:tools/installer/core/installer.js:L197]
3. `_installAndConfigure()`: copy each module into `_bmad/<code>`, create declared directories, write per-module `config.yaml`, central `config.toml`/`config.user.toml`, `manifest.yaml`, `skill-manifest.csv`, apply `--set` patches, then merge `bmad-help.csv`. [SRC:tools/installer/core/installer.js:L127] [SRC:tools/installer/core/installer.js:L788] [SRC:tools/installer/core/installer.js:L320] [SRC:tools/installer/core/installer.js:L344] [SRC:tools/installer/core/installer.js:L370] [SRC:tools/installer/core/installer.js:L381] [SRC:tools/installer/core/installer.js:L393]
4. `_setupIdes()`: copy every skill in `skill-manifest.csv` into the tool's skill folder (`.claude/skills/<canonicalId>` for claude-code), cleaning removed IDs first. [SRC:tools/installer/core/installer.js:L139] [SRC:tools/installer/core/installer.js:L436] [SRC:tools/installer/ide/platform-codes.yaml:L63] [SRC:tools/installer/ide/_config-driven.js:L446]
5. Restore backed-up user files (modified ones come back as sibling `.bak` files). [SRC:tools/installer/core/installer.js:L145] [SRC:tools/installer/core/installer.js:L610]

<!-- [MANUAL:additional-notes] -->
<!-- Add custom notes here. This section is preserved during skill updates. -->
<!-- [/MANUAL:additional-notes] -->

## Adoption Steps

1. **Ship a `module.yaml` the installer can find.** Built-ins live in `src/core-skills` and `src/bmm-skills`; external registry modules are cloned to `~/.bmad/cache/external-modules` and searched at the registry `module_definition` path, then `skills/` and `src/` (one level deep), then the repo root; custom sources are cloned to `~/.bmad/cache/custom-modules`. [SRC:tools/installer/modules/official-modules.js:L232] [SRC:tools/installer/modules/official-modules.js:L240] [SRC:tools/installer/modules/external-manager.js:L195] [SRC:tools/installer/modules/external-manager.js:L540] [SRC:tools/installer/modules/external-manager.js:L547] [SRC:tools/installer/modules/external-manager.js:L567] [SRC:tools/installer/modules/custom-module-manager.js:L364]
2. **Give it a `code`.** `module.yaml` `code` becomes the module id, the `_bmad/<code>` folder and the `[modules.<code>]` TOML table. [SRC:tools/installer/modules/official-modules.js:L201] [SRC:tools/installer/modules/official-modules.js:L404] [SRC:tools/installer/core/manifest-generator.js:L568]
3. **Declare config prompts as keys whose value has `prompt`.** `scope: user` routes answers to `config.user.toml`; everything else goes to `config.toml`. `result` templates render `{value}`. [SRC:tools/installer/core/manifest-generator.js:L462] [SRC:tools/installer/core/manifest-generator.js:L463] [SRC:tools/installer/core/manifest-generator.js:L429] [SRC:tools/installer/modules/official-modules.js:L1446]
4. **Put `module-help.csv` at the module root** with the 13 canonical columns; rows under 12 columns are dropped. [SRC:tools/installer/core/installer.js:L1136] [SRC:tools/installer/modules/module-help-schema.js:L11] [SRC:tools/installer/core/installer.js:L1161]
5. **Make every skill a folder with `SKILL.md` whose frontmatter `name` equals the folder name** — mismatches are skipped from `skill-manifest.csv`, and skills not in that CSV are never copied into `.claude/skills`. [SRC:tools/installer/core/manifest-generator.js:L131] [SRC:tools/installer/core/manifest-generator.js:L223] [SRC:tools/installer/ide/_config-driven.js:L420]
6. **If your module is installed by its own CLI into `_bmad/<code>`,** `bmad install` still counts it: any `_bmad` subfolder with `SKILL.md` or `agents/` is a module; with no resolvable source it is kept as a preserved module, its files and skill-manifest rows re-appended. [SRC:tools/installer/core/manifest-generator.js:L771] [SRC:tools/installer/ui.js:L1031] [SRC:tools/installer/ui.js:L1036] [SRC:tools/installer/ui.js:L430] [SRC:tools/installer/core/installer.js:L1561] [SRC:tools/installer/core/installer.js:L368] [SRC:tools/installer/core/installer.js:L377]
7. **Retire skills with `removals.txt`** (one canonical ID per line, `#` comments) in the module root; the IDE cleanup deletes those IDs. [SRC:tools/installer/ide/_config-driven.js:L631] [SRC:tools/installer/ide/_config-driven.js:L631] [SRC:tools/installer/ide/_config-driven.js:L652] [SRC:removals.txt:L4]

## Pattern Surface

| # | File | Surface | Purpose |
|---|------|---------|---------|
| 1 | `tools/installer/commands/install.js` | `--modules`, `--tools`, `--yes`, `--action`, `--set`, `--custom-source`, `--shims` | Non-interactive install contract [SRC:tools/installer/commands/install.js:L15] [SRC:tools/installer/commands/install.js:L18] [SRC:tools/installer/commands/install.js:L31] [SRC:tools/installer/commands/install.js:L23] [SRC:tools/installer/commands/install.js:L36] [SRC:tools/installer/commands/install.js:L37] |
| 2 | `tools/installer/ui.js` | `UI.promptInstall()` action menu | `quick-update` vs `update` (Modify) vs `install` [SRC:tools/installer/ui.js:L317] [SRC:tools/installer/ui.js:L325] [SRC:tools/installer/ui.js:L345] |
| 3 | `tools/installer/core/installer.js` | `Installer.install()` | Phase order of an install/update [SRC:tools/installer/core/installer.js:L49] [SRC:tools/installer/core/installer.js:L127] [SRC:tools/installer/core/installer.js:L139] |
| 4 | `tools/installer/core/installer.js` | `Installer.quickUpdate()` | Update installed modules, prompt only for new keys [SRC:tools/installer/core/installer.js:L1392] [SRC:tools/installer/core/installer.js:L1460] [SRC:tools/installer/core/installer.js:L1524] |
| 5 | `tools/installer/modules/official-modules.js` | `findModuleSource()` | Source lookup order core → bmm → external → custom [SRC:tools/installer/modules/official-modules.js:L232] [SRC:tools/installer/modules/official-modules.js:L240] [SRC:tools/installer/modules/official-modules.js:L247] [SRC:tools/installer/modules/official-modules.js:L252] |
| 6 | `tools/installer/modules/external-manager.js` | `findExternalModuleSource()` | Where an external module's `module.yaml` is searched [SRC:tools/installer/modules/external-manager.js:L540] [SRC:tools/installer/modules/external-manager.js:L547] [SRC:tools/installer/modules/external-manager.js:L567] [SRC:tools/installer/modules/external-manager.js:L582] |
| 7 | `tools/installer/modules/custom-module-manager.js` | `resolveSource()` / `cloneRepo()` | Custom Git/local sources, marketplace discovery [SRC:tools/installer/modules/custom-module-manager.js:L352] [SRC:tools/installer/modules/custom-module-manager.js:L364] [SRC:tools/installer/modules/custom-module-manager.js:L409] |
| 8 | `tools/installer/project-root.js` | `resolveInstalledModuleYaml()` | Locating an installed module's `module.yaml` (no network) [SRC:tools/installer/project-root.js:L97] [SRC:tools/installer/project-root.js:L103] [SRC:tools/installer/project-root.js:L162] [SRC:tools/installer/project-root.js:L191] |
| 9 | `tools/installer/core/manifest-generator.js` | `scanInstalledModules()` | What counts as an installed module [SRC:tools/installer/core/manifest-generator.js:L762] [SRC:tools/installer/core/manifest-generator.js:L771] |
| 10 | `tools/installer/core/manifest-generator.js` | `collectSkills()` | `SKILL.md` discovery → canonical IDs [SRC:tools/installer/core/manifest-generator.js:L121] [SRC:tools/installer/core/manifest-generator.js:L131] [SRC:tools/installer/core/manifest-generator.js:L145] [SRC:tools/installer/core/manifest-generator.js:L223] |
| 11 | `tools/installer/core/manifest-generator.js` | `writeCentralConfig()` | `config.toml` / `config.user.toml` sections [SRC:tools/installer/core/manifest-generator.js:L435] [SRC:tools/installer/core/manifest-generator.js:L436] [SRC:tools/installer/core/manifest-generator.js:L568] [SRC:tools/installer/core/manifest-generator.js:L608] |
| 12 | `tools/installer/core/installer.js` | `generateModuleConfigs()` | Per-module `config.yaml` with core keys spread in [SRC:tools/installer/core/installer.js:L1019] [SRC:tools/installer/core/installer.js:L1030] [SRC:tools/installer/core/installer.js:L1050] |
| 13 | `tools/installer/core/installer.js` | `mergeModuleHelpCatalogs()` | `module-help.csv` → `_bmad/_config/bmad-help.csv` [SRC:tools/installer/core/installer.js:L1136] [SRC:tools/installer/core/installer.js:L1185] [SRC:tools/installer/core/installer.js:L1203] |
| 14 | `tools/installer/core/manifest-generator.js` | `writeMainManifest()` | `_bmad/_config/manifest.yaml` fields [SRC:tools/installer/core/manifest-generator.js:L302] [SRC:tools/installer/core/manifest-generator.js:L346] [SRC:tools/installer/core/manifest-generator.js:L350] [SRC:tools/installer/core/manifest-generator.js:L375] |
| 15 | `tools/installer/core/manifest-generator.js` | `writeSkillManifest()` / `writeFilesManifest()` | `skill-manifest.csv`, `files-manifest.csv` [SRC:tools/installer/core/manifest-generator.js:L407] [SRC:tools/installer/core/manifest-generator.js:L410] [SRC:tools/installer/core/manifest-generator.js:L688] [SRC:tools/installer/core/manifest-generator.js:L691] |
| 16 | `tools/installer/set-overrides.js` | `applySetOverrides()` | `--set module.key=value` TOML patches [SRC:tools/installer/set-overrides.js:L114] [SRC:tools/installer/set-overrides.js:L262] [SRC:tools/installer/set-overrides.js:L312] |
| 17 | `tools/installer/core/shim-policy.js` | `isShimSkill()`, `inferShimPreference()` | Deprecated shim keep/remove decision [SRC:tools/installer/core/shim-policy.js:L20] [SRC:tools/installer/core/shim-policy.js:L94] [SRC:tools/installer/core/shim-policy.js:L107] |
| 18 | `tools/installer/ide/_config-driven.js` | `loadRemovalLists()` / `cleanupTarget()` | `removals.txt` and stale-skill cleanup [SRC:tools/installer/ide/_config-driven.js:L623] [SRC:tools/installer/ide/_config-driven.js:L631] [SRC:tools/installer/ide/_config-driven.js:L793] |
| 19 | `tools/installer/ide/platform-codes.yaml` | `claude-code` target | `.claude/skills` install folder [SRC:tools/installer/ide/platform-codes.yaml:L63] [SRC:tools/installer/ide/platform-codes.yaml:L64] |
| 20 | `removals.txt` | skill-ID list | Retired/renamed BMAD skill IDs [SRC:removals.txt:L3] [SRC:removals.txt:L4] [SRC:removals.txt:L84] |

## Migration & Deprecation Warnings

- v6.12.0: deprecated shims are opt-in on fresh installs — pass `--shims` to keep them; the choice is persisted as `installation.installShims` in `manifest.yaml`. [QMD:bmad-method-installer-temporal:releases.md] [SRC:tools/installer/commands/install.js:L37] [SRC:tools/installer/core/manifest-generator.js:L384]
- v6.11.0: config moved to layered TOML (`_bmad/config.toml` → `config.user.toml` → `custom/config.toml` → `custom/config.user.toml`); the per-module `config.yaml` still ships; `uv` became required for rendered skills. [QMD:bmad-method-installer-temporal:releases.md] [SRC:tools/installer/core/uv-check.js:L179] [SRC:tools/installer/core/uv-check.js:L181]
- Open upstream issue #2978: reinstall turns multi-select config answers into JSON strings because `parseCentralToml` only reads scalar values. [QMD:bmad-method-installer-temporal:issues.md] [SRC:tools/installer/modules/official-modules.js:L2236]
- Open upstream issue #2869: `--action quick-update` fails for locally sourced custom modules. [QMD:bmad-method-installer-temporal:issues.md]
- Open upstream issue #2883: generated `skill-manifest.csv` paths and `bmad-help.csv` phase names are inconsistent on a fresh 6.12.0 install. [QMD:bmad-method-installer-temporal:issues.md]

See Full API Reference for migration details (`references/pattern-release-context.md`).

## CORRECTION

**Source:** _bmad-output/.skf-stage/bmad-method-installer/provenance-map.json
**Pattern:** deprecated
**Affected:** install --shims
**Detail:** "description": "install --shims opts in to installing deprecated compatibility shim skills when selected modules provide them.",

## CORRECTION

**Source:** _bmad-output/.skf-stage/bmad-method-installer/provenance-map.json
**Pattern:** deprecated
**Affected:** install --shims
**Detail:** "quote": "['--shims', 'Install deprecated compatibility shim skills when the selected modules provide them'],"

## CORRECTION

**Source:** _bmad-output/.skf-stage/bmad-method-installer/provenance-map.json
**Pattern:** deprecated
**Affected:** install --no-shims
**Detail:** "description": "install --no-shims opts out of installing deprecated compatibility shim skills.",

## CORRECTION

**Source:** _bmad-output/.skf-stage/bmad-method-installer/provenance-map.json
**Pattern:** deprecated
**Affected:** install --no-shims
**Detail:** "quote": "['--no-shims', 'Do not install deprecated compatibility shim skills'],"

## CORRECTION

**Source:** _bmad-output/.skf-stage/bmad-method-installer/provenance-map.json
**Pattern:** deprecated
**Affected:** readInstalledShims
**Detail:** "description": "readInstalledShims identifies installed shims by a description starting with 'deprecated', since the manifest has no lifecycle column.",

## CORRECTION

**Source:** _bmad-output/.skf-stage/bmad-method-installer/provenance-map.json
**Pattern:** deprecated
**Affected:** readInstalledShims
**Detail:** "quote": "if (!record.canonicalId || !/^\\s*deprecated\\b/i.test(record.description || '')) continue;"

## CORRECTION

**Source:** _bmad-output/.skf-stage/bmad-method-installer/provenance-map.json
**Pattern:** was removed
**Affected:** removals.txt
**Detail:** "description": "Each removals.txt entry is a skill directory name (canonicalId) that was removed or renamed.",

## CORRECTION

**Source:** _bmad-output/.skf-stage/bmad-method-installer/provenance-map.json
**Pattern:** was removed
**Affected:** removals.txt
**Detail:** "quote": "# Each entry is a skill directory name (canonicalId) that was removed or renamed."

## CORRECTION

**Source:** _bmad-output/.skf-stage/bmad-method-installer/provenance-map.json
**Pattern:** deprecated
**Affected:** UI.promptInstall quick-update
**Detail:** "description": "The quick-update path shows no module picker; promptInstall only runs _warnDeprecatedModules over existingInstall.moduleIds.",

## CORRECTION

**Source:** _bmad-output/.skf-stage/bmad-method-installer/SKILL.md
**Pattern:** deprecated
**Affected:** Pattern Surface row 17 (shim-policy.js)
**Detail:** | 17 | `tools/installer/core/shim-policy.js` | `isShimSkill()`, `inferShimPreference()` | Deprecated shim keep/remove decision [SRC:tools/installer/core/shim-policy.js:L20] [SRC:tools/installer/core/shim-policy.js:L94] [SRC:tools/installer/core/shim-policy.js:L107] |

## Key Types

**`_bmad/_config/` catalogues:** `manifest.yaml`, `skill-manifest.csv` (`canonicalId,name,description,module,path`, all values double-quoted), `files-manifest.csv` (`type,name,module,path,hash`), `bmad-help.csv` (merged). [SRC:tools/installer/core/install-paths.js:L55] [SRC:tools/installer/core/manifest-generator.js:L410] [SRC:tools/installer/core/manifest-generator.js:L408] [SRC:tools/installer/core/manifest-generator.js:L691] [SRC:tools/installer/core/install-paths.js:L67]

**`module-help.csv` columns (13):** `module, skill, display-name, menu-code, description, action, args, phase, preceded-by, followed-by, required, output-location, outputs`. [SRC:src/bmm-skills/module-help.csv:L1] [SRC:tools/installer/modules/module-help-schema.js:L11]

**`manifest.yaml` module entry:** `name`, `version`, `installDate`, `source`, `npmPackage`, `repoUrl`, `channel`, `sha`, optional `localPath`; `source` is `built-in` (core, bmm), `external` (registry) or `custom`. [SRC:tools/installer/core/manifest-generator.js:L346] [SRC:tools/installer/core/manifest-generator.js:L347] [SRC:tools/installer/core/manifest-generator.js:L348] [SRC:tools/installer/core/manifest-generator.js:L350] [SRC:tools/installer/core/manifest-generator.js:L356] [SRC:tools/installer/core/manifest-generator.js:L361] [SRC:tools/installer/core/manifest.js:L289] [SRC:tools/installer/core/manifest.js:L311] [SRC:tools/installer/core/manifest.js:L334]

**Channels:** `stable` (highest pure-semver tag), `next` (main HEAD), `pinned` (`--pin CODE=TAG`); precedence `--pin` > `--next=CODE` > `--channel` > registry default > `stable`. [SRC:tools/installer/modules/channel-plan.js:L13] [SRC:tools/installer/modules/channel-resolver.js:L9] [SRC:tools/installer/modules/channel-resolver.js:L151] [SRC:tools/installer/modules/channel-plan.js:L114]

**Action types:** `install` (fresh), `update` (Modify), `quick-update`. [SRC:tools/installer/commands/install.js:L31] [SRC:tools/installer/ui.js:L317] [SRC:tools/installer/ui.js:L325]

**Config TOML sections:** `[core]`, `[modules.<code>]`, `[agents.<code>]`. [SRC:tools/installer/set-overrides.js:L114] [SRC:tools/installer/core/manifest-generator.js:L568] [SRC:tools/installer/core/manifest-generator.js:L608]

## Architecture at a Glance

- **CLI & front end** — `bmad-cli.js`, `commands/{install,status,uninstall}.js`, `ui.js`, `prompts.js`. [SRC:tools/installer/bmad-cli.js:L80] [SRC:tools/installer/ui.js:L237]
- **Core pipeline** — `core/installer.js`, `core/manifest-generator.js`, `core/manifest.js`, `core/config.js`, `core/install-paths.js`, `core/existing-install.js`. [SRC:tools/installer/core/installer.js:L49] [SRC:tools/installer/core/manifest-generator.js:L53] [SRC:tools/installer/core/manifest.js:L26] [SRC:tools/installer/core/config.js:L21] [SRC:tools/installer/core/install-paths.js:L18] [SRC:tools/installer/core/existing-install.js:L46]
- **Module sources** — `modules/official-modules.js` (built-ins + dispatch), `modules/external-manager.js` (registry clones), `modules/custom-module-manager.js` + `modules/plugin-resolver.js` (custom Git/local sources, `.claude-plugin/marketplace.json`), channel/version resolvers. [SRC:tools/installer/modules/official-modules.js:L108] [SRC:tools/installer/modules/external-manager.js:L50] [SRC:tools/installer/modules/custom-module-manager.js:L352] [SRC:tools/installer/modules/plugin-resolver.js:L15] [SRC:tools/installer/modules/version-resolver.js:L12]
- **Policies** — `core/shim-policy.js`, `core/legacy-warnings.js`, `core/uv-check.js`, `set-overrides.js`. [SRC:tools/installer/core/shim-policy.js:L20] [SRC:tools/installer/core/legacy-warnings.js:L9] [SRC:tools/installer/core/uv-check.js:L17] [SRC:tools/installer/set-overrides.js:L39]
- **IDE install** — `ide/manager.js`, `ide/_config-driven.js`, `ide/platform-codes.yaml`, `ide/shared/*`. [SRC:tools/installer/ide/manager.js:L63] [SRC:tools/installer/ide/_config-driven.js:L212] [SRC:tools/installer/ide/platform-codes.yaml:L63] [SRC:tools/installer/ide/shared/installed-skills.js:L18]

## CLI

| Command | Key flags |
|---------|-----------|
| `install` | `--directory`, `--modules`, `--tools`, `--list-tools`, `--set <module>.<key>=<value>` (repeatable), `--list-options [module]`, `--action install\|update\|quick-update`, `--user-name`, `--communication-language`, `--document-output-language`, `--output-folder`, `--custom-source`, `--shims`/`--no-shims`, `-y/--yes`, `--channel`, `--all-stable`, `--all-next`, `--next <code>`, `--pin CODE=TAG`, `-d/--debug` [SRC:tools/installer/commands/install.js:L14] [SRC:tools/installer/commands/install.js:L15] [SRC:tools/installer/commands/install.js:L18] [SRC:tools/installer/commands/install.js:L20] [SRC:tools/installer/commands/install.js:L23] [SRC:tools/installer/commands/install.js:L29] [SRC:tools/installer/commands/install.js:L31] [SRC:tools/installer/commands/install.js:L32] [SRC:tools/installer/commands/install.js:L33] [SRC:tools/installer/commands/install.js:L35] [SRC:tools/installer/commands/install.js:L36] [SRC:tools/installer/commands/install.js:L37] [SRC:tools/installer/commands/install.js:L38] [SRC:tools/installer/commands/install.js:L39] [SRC:tools/installer/commands/install.js:L42] [SRC:tools/installer/commands/install.js:L44] [SRC:tools/installer/commands/install.js:L45] [SRC:tools/installer/commands/install.js:L46] [SRC:tools/installer/commands/install.js:L49] [SRC:tools/installer/commands/install.js:L85] |
| `status` | none — shows installed modules, versions and available updates [SRC:tools/installer/commands/status.js:L13] [SRC:tools/installer/commands/status.js:L46] |
| `uninstall` | `-y/--yes`, `--directory` — removes IDE integrations first, `_bmad` last [SRC:tools/installer/commands/uninstall.js:L12] [SRC:tools/installer/commands/uninstall.js:L20] [SRC:tools/installer/commands/uninstall.js:L124] [SRC:tools/installer/commands/uninstall.js:L136] |

<!-- [MANUAL:cli-notes] -->
<!-- Add custom notes here. This section is preserved during skill updates. -->
<!-- [/MANUAL:cli-notes] -->

## Full API Reference

Pattern-oriented reference files (Tier 2):

- `references/pattern-module-discovery.md` — built-in, external, custom and plugin sources; caches; `resolveInstalledModuleYaml`; what counts as an installed module.
- `references/pattern-config-generation.md` — `module.yaml` prompt schema, answer collection, `config.yaml`, `config.toml`/`config.user.toml`, `--set`, quick-update config.
- `references/pattern-manifests-and-help.md` — `manifest.yaml`, `skill-manifest.csv`, `files-manifest.csv`, `bmad-help.csv` merge.
- `references/pattern-update-and-cleanup.md` — install/update/quick-update flows, preserved modules, user-file backup, shims, `removals.txt`, IDE skill install and cleanup.
- `references/api-exports.md` — every `module.exports` name with its AST-verified definition line.
- `references/pattern-release-context.md` — release notes and open issues (T2).
