# bmad-method-installer Reference

**Version:** 6.12.0 (BMAD-METHOD tag `v6.12.0`, commit `05bfbd46`)
**Export count:** 118 exports (source skill metadata)
**Confidence:** T1-low (dominant `confidence_distribution` bin: t1 369, t1_low 438, t2 22, t3 0; forge tier Deep, reference-app)
**Source skill:** `skf-skills/bmad-method-installer/6.12.0/bmad-method-installer`

## Key Exports

| Export | Role | Anchor (from source skill provenance) |
|--------|------|----------------------------------------|
| `Installer.install()` | Phase order of an install/update | `tools/installer/core/installer.js` |
| `Installer.quickUpdate()` | Update installed modules, prompt only for new keys | `tools/installer/core/installer.js` |
| `OfficialModules.findModuleSource()` | Source lookup order core → bmm → external → custom | `tools/installer/modules/official-modules.js` |
| `generateModuleConfigs()` | Per-module `config.yaml` with core keys spread in | `tools/installer/core/installer.js` |
| `writeCentralConfig()` | `config.toml` / `config.user.toml` sections | `tools/installer/core/manifest-generator.js` |
| `mergeModuleHelpCatalogs()` | `module-help.csv` → `_bmad/_config/bmad-help.csv` | `tools/installer/core/installer.js` |
| `resolveInstalledModuleYaml()` | Locating an installed module's `module.yaml` (no network) | `tools/installer/project-root.js` |
| `loadRemovalLists()` | `removals.txt` and stale-skill cleanup | `tools/installer/ide/_config-driven.js` |

## Usage Patterns

- `npx bmad-method install --yes --directory <project> --modules bmm --tools claude-code` — `--tools` is required for a fresh `--yes` install.
- A module is found via `module.yaml`; its `code` names `_bmad/<code>` and `[modules.<code>]`; prompt keys (`scope: user` → `config.user.toml`) become config; `module-help.csv` (13 columns) is merged into `bmad-help.csv`; skills whose `SKILL.md` `name` equals the folder are copied into `.claude/skills/<canonicalId>` for the `claude-code` target.
- v6.12.0: deprecated shims are opt-in on fresh installs (`--shims`), persisted as `installation.installShims` in `manifest.yaml`.
- Modules installed by their own CLI into `_bmad/<code>` are kept as preserved modules when no source resolves.

## Common Imports

Compose-mode: no import statements. The entry point is the `bmad-method` / `bmad` CLI (`npx bmad-method install …`); the exports above are the installer's internal surfaces a module author has to satisfy.
