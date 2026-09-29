# Pattern: install, update, quick update and cleanup

## Contents

- [Choosing the action](#choosing-the-action)
- [Install / Modify flow](#install--modify-flow)
- [Quick update](#quick-update)
- [Preserved modules (installed without a source)](#preserved-modules-installed-without-a-source)
- [User files](#user-files)
- [Module folder replacement](#module-folder-replacement)
- [Deprecation shims](#deprecation-shims)
- [removals.txt](#removalstxt)
- [IDE skill install and cleanup](#ide-skill-install-and-cleanup)
- [Uninstall](#uninstall)

## Choosing the action

An existing install is detected when `installer.findBmadDir(directory)` exists; the menu lists **Quick Update** (`quick-update`) first when an install exists and always offers **Modify BMAD Installation** (`update`). [SRC:tools/installer/ui.js:L303] [SRC:tools/installer/ui.js:L317] [SRC:tools/installer/ui.js:L325] `--action` must match an available value; under `--yes` without `--action` the default is `quick-update`, but `--custom-source` or an explicit `--shims`/`--no-shims` forces `update`. [SRC:tools/installer/ui.js:L331] [SRC:tools/installer/ui.js:L345] [SRC:tools/installer/ui.js:L343] The `install` command dispatches `quick-update` to `installer.quickUpdate()` and everything else to `installer.install()`. [SRC:tools/installer/commands/install.js:L117] [SRC:tools/installer/commands/install.js:L124]

## Install / Modify flow

- `--modules` is split on commas; `core` is always prepended. [SRC:tools/installer/ui.js:L393] [SRC:tools/installer/ui.js:L419]
- Modify with `--yes` and no `--modules` selects installed plus default-selected modules; with `--custom-source` and no `--modules`/`--yes` it starts empty. [SRC:tools/installer/ui.js:L401] [SRC:tools/installer/ui.js:L394]
- Before cloning, `_resolveUpdateChannels()` re-applies recorded `pinned`/`next` channels; stable modules accept patch/minor upgrades (under `--yes` majors are refused and frozen with a pin). [SRC:tools/installer/ui.js:L444] [SRC:tools/installer/ui.js:L2152] [SRC:tools/installer/ui.js:L2002] [SRC:tools/installer/ui.js:L2226]
- The returned `update` config carries `modules`, `ides`, `skipIde`, `coreConfig`, `moduleConfigs`, `setOverrides`, `skipPrompts`, `channelOptions`, `installShims` and `_preserveModules`. [SRC:tools/installer/ui.js:L490]
- `Installer.install()` removes deselected modules except core and preserved ones, then `_installAndConfigure()`, `_setupIdes()`, `_restoreUserFiles()`. [SRC:tools/installer/core/installer.js:L98] [SRC:tools/installer/core/installer.js:L197] [SRC:tools/installer/core/installer.js:L127] [SRC:tools/installer/core/installer.js:L139] [SRC:tools/installer/core/installer.js:L145]
- In a normal install, preserved modules are appended to the manifest module list and their files re-tracked. [SRC:tools/installer/core/installer.js:L358] [SRC:tools/installer/core/installer.js:L368]
- Any error logs `Installation failed`, cleans temp backups and rethrows. [SRC:tools/installer/core/installer.js:L171]

## Quick update

- Refuses to run without `_bmad`; maps legacy/aliased codes to canonical ones; external registry modules and custom modules whose source `CustomModuleManager` can find are available; only installed modules with a source are updated. [SRC:tools/installer/core/installer.js:L1392] [SRC:tools/installer/core/installer.js:L1410] [SRC:tools/installer/core/installer.js:L1430] [SRC:tools/installer/core/installer.js:L1445] [SRC:tools/installer/core/installer.js:L1460]
- Held-back major releases require `bmad install` (Modify) with `--pin <module>=<tag>`. [SRC:tools/installer/core/installer.js:L1503]
- The quick-update config from the UI holds only `actionType`, `directory`, `skipPrompts` and `installShims` — no module picker, no module or IDE lists. [SRC:tools/installer/ui.js:L370] [SRC:tools/installer/ui.js:L356]
- Manifests are rebuilt from the existing module list; modules without a source are passed as `_preserveModules` and kept; an aliased module's stale folder is removed after its successor installs. [SRC:tools/installer/core/installer.js:L356] [SRC:tools/installer/core/installer.js:L1561] [SRC:tools/installer/core/installer.js:L1573]

## Preserved modules (installed without a source)

In the Modify flow `_retainUnavailableInstalledModules()` moves an installed non-official module out of the selection into `_preserveModules` only when `findModuleSourceByCode` finds no source, and warns "Retaining … installed module(s) with no available source". [SRC:tools/installer/ui.js:L219] [SRC:tools/installer/ui.js:L430] Preserved modules are never removed, their files stay in the installed-files list, and their `skill-manifest.csv` rows are re-appended. [SRC:tools/installer/core/installer.js:L197] [SRC:tools/installer/core/installer.js:L368] [SRC:tools/installer/core/installer.js:L377] For local-source custom modules the manifest `localPath` is used only if it still exists; installed files are never removed on that path. [SRC:tools/installer/modules/custom-module-manager.js:L774] [SRC:tools/installer/modules/custom-module-manager.js:L819]

## User files

`_prepareUpdateState()` compares current files with `files-manifest.csv`; custom files are backed up to `_bmad-custom-backup-temp` and modified files to `_bmad-modified-backup-temp` in the project root; after install, custom files are copied back and modified files come back as sibling `.bak` files. [SRC:tools/installer/core/installer.js:L639] [SRC:tools/installer/core/installer.js:L682] [SRC:tools/installer/core/installer.js:L694] [SRC:tools/installer/core/installer.js:L590] [SRC:tools/installer/core/installer.js:L610] `_bmad/scripts` is wiped and re-synced from the package on every install. [SRC:tools/installer/core/installer.js:L722] [SRC:tools/installer/core/installer.js:L717]

## Module folder replacement

`OfficialModules.install()` deletes the existing `_bmad/<module>` folder before copying, so installs replace the whole folder. [SRC:tools/installer/modules/official-modules.js:L295] [SRC:tools/installer/modules/official-modules.js:L295] `copyModuleWithFiltering()` skips `sub-modules/`, `*-sidecar` folders and `agents/*.md` marked `localskip="true"`. [SRC:tools/installer/modules/official-modules.js:L563] [SRC:tools/installer/modules/official-modules.js:L571] [SRC:tools/installer/modules/official-modules.js:L598] `syncModule()` (update path) skips files whose installed copy is newer than the source. [SRC:tools/installer/modules/official-modules.js:L789] [SRC:tools/installer/modules/official-modules.js:L807] `createModuleDirectories()` moves a directory when its configured path changed and only the old one exists, warns when both exist, and never moves between parent/child paths; paths escaping the project root are skipped. [SRC:tools/installer/modules/official-modules.js:L747] [SRC:tools/installer/modules/official-modules.js:L764] [SRC:tools/installer/modules/official-modules.js:L730] [SRC:tools/installer/modules/official-modules.js:L697]

## Deprecation shims

- A skill is a shim when its `SKILL.md` frontmatter has `metadata.lifecycle: shim`; installed shims are recognized by a description starting with `deprecated`. [SRC:tools/installer/core/shim-policy.js:L20] [SRC:tools/installer/core/shim-policy.js:L86]
- Preference order: explicit `--shims`/`--no-shims`, then `installation.installShims` from the previous manifest, then (existing install) keep if any available shim is already installed; false when the release ships no shims. [SRC:tools/installer/core/shim-policy.js:L94] [SRC:tools/installer/core/manifest.js:L65] [SRC:tools/installer/core/shim-policy.js:L98] [SRC:tools/installer/core/shim-policy.js:L93]
- `selectShimOutcome()` removes every installed shim unless shims are installed and still shipped; `--no-shims` excludes shim folders from the copy. [SRC:tools/installer/core/shim-policy.js:L107] [SRC:tools/installer/modules/official-modules.js:L553]
- The shim prompt is skipped under `--yes`, with an explicit flag, or without a TTY. [SRC:tools/installer/ui.js:L133] [SRC:tools/installer/ui.js:L136] [SRC:tools/installer/ui.js:L133] [SRC:tools/installer/ui.js:L136]

## removals.txt

Entries are skill directory names (canonical IDs), one per line, `#` for comments. [SRC:removals.txt:L3] [SRC:removals.txt:L4] [SRC:tools/installer/ide/_config-driven.js:L652] The package-level `removals.txt` covers core and bmm; each installed module folder under `_bmad` may carry its own (folders starting with `_` are skipped). [SRC:tools/installer/ide/_config-driven.js:L623] [SRC:tools/installer/ide/_config-driven.js:L631] v6.12.0's list includes `bmad-check-implementation-readiness`. [SRC:removals.txt:L84]

## IDE skill install and cleanup

- One handler per platform in `platform-codes.yaml`; `claude-code` installs to `.claude/skills` (global `~/.claude/skills`). [SRC:tools/installer/ide/manager.js:L63] [SRC:tools/installer/ide/platform-codes.yaml:L63] [SRC:tools/installer/ide/platform-codes.yaml:L64]
- Setup always runs cleanup first; skills come from `skill-manifest.csv` and land in `<target_dir>/<canonicalId>` after the old folder is deleted; `.DS_Store` and `__pycache__` are skipped. [SRC:tools/installer/ide/_config-driven.js:L212] [SRC:tools/installer/ide/_config-driven.js:L420] [SRC:tools/installer/ide/_config-driven.js:L446] [SRC:tools/installer/ide/_config-driven.js:L447] [SRC:tools/installer/ide/_config-driven.js:L452]
- Cleanup removes previously installed skill IDs plus `removals.txt` entries, keeps `bmad-os-*`, and uses prefix ownership only when no removal set exists. [SRC:tools/installer/ide/_config-driven.js:L506] [SRC:tools/installer/ide/_config-driven.js:L790] [SRC:tools/installer/ide/_config-driven.js:L793]
- Platforms sharing a `target_dir` are deduplicated; `ancestor_conflict_check` refuses an install when an ancestor already holds BMAD skills in the same target. [SRC:tools/installer/ide/manager.js:L210] [SRC:tools/installer/ide/_config-driven.js:L202]
- `_cleanupSkillDirs()` removes skill folders listed in the old `skill-manifest.csv` from `_bmad`. [SRC:tools/installer/core/installer.js:L461] [SRC:tools/installer/core/installer.js:L474]
- Pre-6.1.0 installs get exact `rm -rf` hints for stale `.claude/commands` and legacy skill paths. [SRC:tools/installer/core/legacy-warnings.js:L9] [SRC:tools/installer/core/legacy-warnings.js:L16] [SRC:tools/installer/core/legacy-warnings.js:L135]

## Uninstall

`uninstall` removes IDE integrations first and `_bmad` last; with `--yes` it keeps the output folder. [SRC:tools/installer/commands/uninstall.js:L124] [SRC:tools/installer/commands/uninstall.js:L136] [SRC:tools/installer/commands/uninstall.js:L76]
