# Pattern: manifests and the help catalog

## Contents

- [The _config folder](#the-_config-folder)
- [manifest.yaml](#manifestyaml)
- [skill-manifest.csv](#skill-manifestcsv)
- [files-manifest.csv](#files-manifestcsv)
- [bmad-help.csv merge](#bmad-helpcsv-merge)
- [Skill sidecar manifests and ownership](#skill-sidecar-manifests-and-ownership)

## The _config folder

`generateManifests()` writes into `_bmad/_config/` (created if missing): `manifest.yaml`, `skill-manifest.csv`, `files-manifest.csv`, plus the central TOML configs; it throws when `options.ides` is absent. [SRC:tools/installer/core/manifest-generator.js:L42] [SRC:tools/installer/core/manifest-generator.js:L88] [SRC:tools/installer/core/manifest-generator.js:L89] [SRC:tools/installer/core/manifest-generator.js:L688] [SRC:tools/installer/core/manifest-generator.js:L86] [SRC:tools/installer/core/manifest-generator.js:L65] `InstallPaths` defines `bmadDir = <projectRoot>/_bmad`, `configDir = _bmad/_config`, `customDir = _bmad/custom`, `manifestFile = _bmad/_config/manifest.yaml`, `helpCatalog = _config/bmad-help.csv`, `moduleConfig = _bmad/<name>/config.yaml`; `isUpdate` is set when `_bmad` exists. [SRC:tools/installer/core/install-paths.js:L18] [SRC:tools/installer/core/install-paths.js:L21] [SRC:tools/installer/core/install-paths.js:L24] [SRC:tools/installer/core/install-paths.js:L55] [SRC:tools/installer/core/install-paths.js:L67] [SRC:tools/installer/core/install-paths.js:L73] [SRC:tools/installer/core/install-paths.js:L19] `BMAD_FOLDER_NAME` is `_bmad`. [SRC:tools/installer/ide/shared/path-utils.js:L21]

## manifest.yaml

- `installation.installDate` is preserved from an existing manifest; `installation.version` is the installer's package version; `ides` lists the selected tools; `installation.installShims` is written only when shims are available. [SRC:tools/installer/core/manifest-generator.js:L314] [SRC:tools/installer/core/manifest-generator.js:L375] [SRC:tools/installer/core/manifest-generator.js:L380] [SRC:tools/installer/core/manifest-generator.js:L384]
- Each module entry: `name`, `version` (fresh from `Manifest.getModuleVersionInfo`), `installDate` (kept or now), `source`, `npmPackage`, `repoUrl`, `channel`/`sha` (fresh, else existing), optional `localPath`. [SRC:tools/installer/core/manifest-generator.js:L340] [SRC:tools/installer/core/manifest-generator.js:L346] [SRC:tools/installer/core/manifest-generator.js:L347] [SRC:tools/installer/core/manifest-generator.js:L348] [SRC:tools/installer/core/manifest-generator.js:L350] [SRC:tools/installer/core/manifest-generator.js:L356] [SRC:tools/installer/core/manifest-generator.js:L361]
- `source`: `built-in` for core and bmm; `external` for registry modules (install-time version wins over on-disk); `custom` for `CustomModuleManager` modules, whose version is the clone ref, else `main`, and channel `pinned` with a ref, else `next`. [SRC:tools/installer/core/manifest.js:L289] [SRC:tools/installer/core/manifest.js:L311] [SRC:tools/installer/core/manifest.js:L310] [SRC:tools/installer/core/manifest.js:L334] [SRC:tools/installer/core/manifest.js:L333] [SRC:tools/installer/core/manifest.js:L338]
- `Manifest.read()` flattens modules to names and exposes `modulesDetailed`; `addModule()` defaults `source` to `unknown` and keeps the old version when none is given. [SRC:tools/installer/core/manifest.js:L103] [SRC:tools/installer/core/manifest.js:L115] [SRC:tools/installer/core/manifest.js:L196] [SRC:tools/installer/core/manifest.js:L212]
- `status` / `checkForUpdates()` compare the installed version with npm (skipping modules without `npmPackage`). [SRC:tools/installer/commands/status.js:L46] [SRC:tools/installer/core/manifest.js:L412] [SRC:tools/installer/core/manifest.js:L424]

## skill-manifest.csv

- `collectSkills()` walks `_bmad/<module>` recursively, skipping `.`- and `_`-prefixed folders; a folder with `SKILL.md` is a skill and is not descended further. [SRC:tools/installer/core/manifest-generator.js:L118] [SRC:tools/installer/core/manifest-generator.js:L121] [SRC:tools/installer/core/manifest-generator.js:L131] [SRC:tools/installer/core/manifest-generator.js:L170]
- `SKILL.md` needs `---` frontmatter at the very start with a string `name` equal to the folder name; otherwise the skill is skipped. [SRC:tools/installer/core/manifest-generator.js:L207] [SRC:tools/installer/core/manifest-generator.js:L214] [SRC:tools/installer/core/manifest-generator.js:L223]
- `canonicalId` is the folder name; `path` is `_bmad/<module>/<relativePath>/SKILL.md`. [SRC:tools/installer/core/manifest-generator.js:L145] [SRC:tools/installer/core/manifest-generator.js:L141]
- Header `canonicalId,name,description,module,path`; every value double-quoted. [SRC:tools/installer/core/manifest-generator.js:L410] [SRC:tools/installer/core/manifest-generator.js:L408]
- On update, rows of preserved modules are re-appended after regeneration. [SRC:tools/installer/core/installer.js:L377] [SRC:tools/installer/core/installer.js:L547]

## files-manifest.csv

Header `type,name,module,path,hash`. [SRC:tools/installer/core/manifest-generator.js:L691] Update logic compares current files to it: absent files are custom, hash mismatches are modified; `_memory`/`memory` subtrees are never reported. [SRC:tools/installer/core/installer.js:L639] [SRC:tools/installer/core/installer.js:L978] [SRC:tools/installer/core/installer.js:L987] [SRC:tools/installer/core/installer.js:L901]

## bmad-help.csv merge

`Installer.mergeModuleHelpCatalogs()` runs as the last configuration step:

1. Core rows come from the package's `src/core-skills`; every other module contributes `module-help.csv` from its module root (skipping `_config`, `_memory`, `memory`, `docs`, `scripts`, `custom`, `render`). [SRC:tools/installer/core/installer.js:L393] [SRC:tools/installer/core/installer.js:L1120] [SRC:tools/installer/core/installer.js:L1136] [SRC:tools/installer/core/installer.js:L1116]
2. Blank and `#` lines are skipped; a `module,`-prefixed header row is skipped and only warned about when it differs from `MODULE_HELP_CSV_HEADER`. [SRC:tools/installer/core/installer.js:L1141] [SRC:tools/installer/core/installer.js:L1148] [SRC:tools/installer/core/installer.js:L1152]
3. Rows with fewer than 12 columns are dropped; the rest are padded or truncated to 13. [SRC:tools/installer/core/installer.js:L1161] [SRC:tools/installer/core/installer.js:L1161]
4. An empty `module` column is filled with the module's name (except core). [SRC:tools/installer/core/installer.js:L1169]
5. Rows are sorted by module, then phase (column index 7), keeping authored order within a phase, and written to `_bmad/_config/bmad-help.csv`. [SRC:tools/installer/core/installer.js:L1185] [SRC:tools/installer/core/installer.js:L1111] [SRC:tools/installer/core/installer.js:L1203]

For marketplace-plugin modules, `_copyResolvedSkills()` places `module-help.csv` at the module root (copied for strategies 1–4, synthesized for strategy 5). [SRC:tools/installer/modules/official-modules.js:L383] [SRC:tools/installer/modules/official-modules.js:L386] [SRC:tools/installer/modules/official-modules.js:L390]

## Skill sidecar manifests and ownership

`loadSkillManifest()` reads an optional `bmad-skill-manifest.yaml` sidecar; a top-level `canonicalId` or `type` makes it one entry for the whole folder. [SRC:tools/installer/ide/shared/skill-manifest.js:L13] [SRC:tools/installer/ide/shared/skill-manifest.js:L19] `getInstalledCanonicalIds()` reads canonical IDs from `skill-manifest.csv`; `isBmadOwnedEntry()` never claims `bmad-os-*`, uses the manifest set when available, and falls back to the legacy `bmad` prefix only without a manifest. [SRC:tools/installer/ide/shared/installed-skills.js:L18] [SRC:tools/installer/ide/shared/installed-skills.js:L45] [SRC:tools/installer/ide/shared/installed-skills.js:L46] [SRC:tools/installer/ide/shared/installed-skills.js:L47]
