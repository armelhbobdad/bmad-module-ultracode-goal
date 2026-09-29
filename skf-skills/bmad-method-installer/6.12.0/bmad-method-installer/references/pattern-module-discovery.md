# Pattern: module discovery

## Contents

- [Source lookup order](#source-lookup-order)
- [Built-in modules](#built-in-modules)
- [External (registry) modules](#external-registry-modules)
- [Custom sources](#custom-sources)
- [Plugin resolution strategies](#plugin-resolution-strategies)
- [Finding an installed module's module.yaml](#finding-an-installed-modules-moduleyaml)
- [What counts as an installed module](#what-counts-as-an-installed-module)
- [module.yaml fields the installer reads](#moduleyaml-fields-the-installer-reads)

## Source lookup order

`OfficialModules.findModuleSource()` resolves a module code in this order: `src/core-skills` for `core`, `src/bmm-skills` for `bmm`, then an external official module via `ExternalModuleManager` (with channel options), and finally custom modules already cloned to cache via `CustomModuleManager`. [SRC:tools/installer/modules/official-modules.js:L232] [SRC:tools/installer/modules/official-modules.js:L240] [SRC:tools/installer/modules/official-modules.js:L247] [SRC:tools/installer/modules/official-modules.js:L252] When no source is found, `OfficialModules.install()` throws. [SRC:tools/installer/modules/official-modules.js:L290]

`OfficialModules.listAvailable()` lists only the built-in `core` and `bmm`; everything else comes from the external registry. [SRC:tools/installer/modules/official-modules.js:L108] [SRC:tools/installer/modules/official-modules.js:L117] [SRC:tools/installer/modules/official-modules.js:L126] The installer README says external official modules must be registered in `external-official-modules.yaml` to be discoverable. [SRC:tools/installer/README.md:L5] In code, `ExternalModuleManager` reads `bmad-modules.yaml` at the installer project root. [SRC:tools/installer/modules/external-manager.js:L50]

## Built-in modules

`getModulePath()` maps `core` to `src/core-skills` and other non-bmm names to `src/modules/<name>`. [SRC:tools/installer/project-root.js:L66] [SRC:tools/installer/project-root.js:L71] `getModuleInfo()` expects `module.yaml` at the module root, falling back to a synthesized definition (strategy 5) from a custom resolution. [SRC:tools/installer/modules/official-modules.js:L160] [SRC:tools/installer/modules/official-modules.js:L167]

## External (registry) modules

- Registry entries: git URL from `repository` (or `url`), `module_definition` path, optional `npm_package`, `default_channel` (default `stable`), `marketplace_plugin`, `aliases` for renamed codes; entries without `built_in: true` are external. [SRC:tools/installer/modules/external-manager.js:L123] [SRC:tools/installer/modules/external-manager.js:L124] [SRC:tools/installer/modules/external-manager.js:L130] [SRC:tools/installer/modules/external-manager.js:L132] [SRC:tools/installer/modules/external-manager.js:L135] [SRC:tools/installer/modules/external-manager.js:L138] [SRC:tools/installer/modules/external-manager.js:L142]
- Lookup by code, then aliases. [SRC:tools/installer/modules/external-manager.js:L175]
- Cache: `~/.bmad/cache/external-modules` (override with `BMAD_EXTERNAL_MODULES_CACHE`). [SRC:tools/installer/modules/external-manager.js:L195] [SRC:tools/installer/project-root.js:L80]
- Cloning: stable/pinned use `git clone --depth 1 --branch <tag>`; a `.bmad-channel.json` marker records channel, version and sha; a `package.json` triggers `npm install --omit=dev --legacy-peer-deps`. [SRC:tools/installer/modules/external-manager.js:L423] [SRC:tools/installer/modules/external-manager.js:L446] [SRC:tools/installer/modules/external-manager.js:L460]
- No stable tags → install from `main` with a warning; a missing pinned tag throws; GitHub rate limits suggest `GITHUB_TOKEN`. [SRC:tools/installer/modules/external-manager.js:L333] [SRC:tools/installer/modules/external-manager.js:L346] [SRC:tools/installer/modules/external-manager.js:L326]
- `findExternalModuleSource()` searches `module.yaml` at the registry `module_definition` path, then `skills/` and `src/` (top level and one level deep), then the repo root; with none it throws. Marketplace-plugin modules resolve through `.claude-plugin/marketplace.json`. [SRC:tools/installer/modules/external-manager.js:L540] [SRC:tools/installer/modules/external-manager.js:L547] [SRC:tools/installer/modules/external-manager.js:L567] [SRC:tools/installer/modules/external-manager.js:L582] [SRC:tools/installer/modules/external-manager.js:L530] [SRC:tools/installer/modules/external-manager.js:L611]

## Custom sources

- `--custom-source` accepts comma-separated Git URLs or local paths; every module found is auto-selected. [SRC:tools/installer/commands/install.js:L36] [SRC:tools/installer/ui.js:L1342]
- `parseSource()` accepts `@<ref>` suffixes on URLs (not local paths), `git@host:owner/repo` SSH URLs, and `/tree/<ref>/<subdir>` deep links; `~` expands to home. [SRC:tools/installer/modules/custom-module-manager.js:L99] [SRC:tools/installer/modules/custom-module-manager.js:L118] [SRC:tools/installer/modules/custom-module-manager.js:L125] [SRC:tools/installer/modules/custom-module-manager.js:L171] [SRC:tools/installer/modules/custom-module-manager.js:L258]
- Cache: `~/.bmad/cache/custom-modules/<host>/<owner>/<repo>`, with `.bmad-source.json` (`cloneUrl`, `cacheKey`, `version`, `rawInput`, `sha`) and `.bmad-channel.json` (`pinned` with a ref, else `next`). [SRC:tools/installer/modules/custom-module-manager.js:L364] [SRC:tools/installer/modules/custom-module-manager.js:L382] [SRC:tools/installer/modules/custom-module-manager.js:L536] [SRC:tools/installer/modules/custom-module-manager.js:L550]
- A `.claude-plugin/marketplace.json` at the source root switches to discovery mode; otherwise direct mode treats subfolders holding `SKILL.md` as the skills. [SRC:tools/installer/modules/custom-module-manager.js:L352] [SRC:tools/installer/ui.js:L1215] [SRC:tools/installer/ui.js:L1261]
- A changed requested version deletes and re-clones; a failed refresh keeps the cached copy with a warning. [SRC:tools/installer/modules/custom-module-manager.js:L409] [SRC:tools/installer/modules/custom-module-manager.js:L473]
- Custom modules carry `trustTier: 'unverified'`, and the installer warns that non-local custom sources are unreviewed. [SRC:tools/installer/modules/custom-module-manager.js:L917] [SRC:tools/installer/ui.js:L1205]
- `--list-options` does not list community and custom modules. [SRC:tools/installer/list-options.js:L203]

## Plugin resolution strategies

`PluginResolver` tries, in order: module files (`module.yaml` + `module-help.csv`) at the common parent of all skills; a `*-setup` skill with `assets/module.yaml`; (strategy 3 is not covered by this extraction); standalone skills that each carry module files; and finally a synthesized definition from `marketplace.json` plus `SKILL.md` frontmatter. Skill paths escaping the repo root are dropped. [SRC:tools/installer/modules/plugin-resolver.js:L75] [SRC:tools/installer/modules/plugin-resolver.js:L109] [SRC:tools/installer/modules/plugin-resolver.js:L111] [SRC:tools/installer/modules/plugin-resolver.js:L215] [SRC:tools/installer/modules/plugin-resolver.js:L15] [SRC:tools/installer/modules/plugin-resolver.js:L44] The module code comes from `module.yaml` `code`, else the plugin name; a synthesized module's version is the plugin version or `1.0.0`, and its `module-help.csv` is synthesized one row per skill. [SRC:tools/installer/modules/plugin-resolver.js:L86] [SRC:tools/installer/modules/plugin-resolver.js:L248] [SRC:tools/installer/modules/plugin-resolver.js:L349]

## Finding an installed module's module.yaml

`resolveInstalledModuleYaml()` performs no git or network work. It checks the built-in `getModulePath` location, `*-setup` skills at the repo root / `src/skills/` / `skills/` (BMB `{setup-skill}/assets/module.yaml`), `~/.bmad/cache/community-modules/<name>`, local custom sources in the resolution cache, and `~/.bmad/cache/custom-modules` (matching `code` or `name`). [SRC:tools/installer/project-root.js:L97] [SRC:tools/installer/project-root.js:L103] [SRC:tools/installer/project-root.js:L129] [SRC:tools/installer/project-root.js:L135] [SRC:tools/installer/project-root.js:L162] [SRC:tools/installer/project-root.js:L174] [SRC:tools/installer/project-root.js:L191] [SRC:tools/installer/project-root.js:L201] When `module.yaml` cannot be located, the module's agents are not written to `config.toml`. [SRC:tools/installer/core/manifest-generator.js:L249] [SRC:tools/installer/core/manifest-generator.js:L256]

`discoverOfficialModuleYamls()` (used by `--list-options`) always includes core and bmm, then checks `module.yaml`, `src/module.yaml` and `skills/module.yaml` in each cached external module. [SRC:tools/installer/list-options.js:L57] [SRC:tools/installer/list-options.js:L81] [SRC:tools/installer/list-options.js:L88]

## What counts as an installed module

- `scanInstalledModules()` skips non-directories, dot-folders, `_config` and `render` under `_bmad`, and counts a folder as a module when it has an `agents/` subfolder or a `SKILL.md` anywhere inside. [SRC:tools/installer/core/manifest-generator.js:L762] [SRC:tools/installer/core/manifest-generator.js:L771]
- `generateManifests()` always includes `core` and unions selected, preserved and scanned modules. [SRC:tools/installer/core/manifest-generator.js:L53] [SRC:tools/installer/core/manifest-generator.js:L53]
- `ExistingInstall.detect()` lists modules from `manifest.yaml`, not from a directory scan; module versions come from `<module>/config.yaml` (default `unknown`). [SRC:tools/installer/core/existing-install.js:L85] [SRC:tools/installer/core/existing-install.js:L99]
- In the UI, installed modules that are not core, bmm or registry modules are "installed non-official" and are always kept in the selection without being shown in the picker. [SRC:tools/installer/ui.js:L1031] [SRC:tools/installer/ui.js:L1036]

## module.yaml fields the installer reads

| Field | Effect |
|-------|--------|
| `code` | Module id, install folder and TOML section key (falls back to the module name) [SRC:tools/installer/modules/official-modules.js:L201] [SRC:tools/installer/core/manifest-generator.js:L459] [SRC:tools/installer/core/manifest-generator.js:L560] |
| `version` / `module_version` / `moduleVersion` | Version resolution (after the nearest `package.json`); `getModuleInfo` defaults to `5.0.0` [SRC:tools/installer/modules/version-resolver.js:L244] [SRC:tools/installer/modules/version-resolver.js:L12] [SRC:tools/installer/modules/official-modules.js:L190] |
| `dependencies` | List, default empty [SRC:tools/installer/modules/official-modules.js:L207] |
| `default_selected` | Pre-selection in the picker (missing = false; bmm sets `true`) [SRC:tools/installer/modules/official-modules.js:L208] [SRC:src/bmm-skills/module.yaml:L4] |
| `header` | Display name, else `<CODE> Module` [SRC:tools/installer/modules/official-modules.js:L1068] |
| `<key>: {prompt, default, result, scope, single-select/multi-select, regex}` | Config questions [SRC:tools/installer/core/manifest-generator.js:L462] [SRC:tools/installer/core/manifest-generator.js:L463] [SRC:tools/installer/modules/official-modules.js:L2002] [SRC:tools/installer/modules/official-modules.js:L2021] [SRC:tools/installer/modules/official-modules.js:L2137] |
| `directories` | Folders to create, each a single `{config_key}` reference [SRC:tools/installer/modules/official-modules.js:L659] [SRC:tools/installer/modules/official-modules.js:L671] |
| `agents` | Written to `config.toml` as `[agents.<code>]` with `module` and `team` [SRC:tools/installer/core/manifest-generator.js:L608] [SRC:tools/installer/core/manifest-generator.js:L280] |
| `post-install-notes` | Shown after config collection [SRC:tools/installer/modules/official-modules.js:L2169] [SRC:tools/installer/README.md:L11] |

Metadata keys `code`, `name`, `header`, `subheader`, `default_selected` are not treated as questions. [SRC:tools/installer/modules/official-modules.js:L1043]
