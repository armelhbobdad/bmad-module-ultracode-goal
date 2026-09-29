# bmad-method-installer (constituent)

- **Version:** 6.12.0 (BMAD-METHOD tag `v6.12.0`, commit `05bfbd46`)
- **Export count:** 118 (source skill metadata)
- **Confidence:** T1 (source skill: Deep, reference-app)
- **Source skill:** `skf-skills/bmad-method-installer/6.12.0/bmad-method-installer`

## Key exports used in this stack

| Export | Role | Anchor (from source skill provenance) |
|--------|------|----------------------------------------|
| `Installer.install()` | Phase order of an install/update | `tools/installer/core/installer.js` |
| `Installer.quickUpdate()` | Update installed modules, prompt only for new keys | `tools/installer/core/installer.js` |
| `OfficialModules.findModuleSource()` | Source lookup order core → bmm → external → custom | `tools/installer/modules/official-modules.js` |
| `generateModuleConfigs()` | Per-module `config.yaml` with core keys spread in | `tools/installer/core/installer.js` |
| `mergeModuleHelpCatalogs()` | `module-help.csv` → `_bmad/_config/bmad-help.csv` | `tools/installer/core/installer.js` |
| `resolveInstalledModuleYaml()` | Locating an installed module's `module.yaml` (no network) | `tools/installer/project-root.js` |
| `loadRemovalLists()` | `removals.txt` and stale-skill cleanup | `tools/installer/ide/_config-driven.js` |

## Usage patterns (from source skill)

- `npx bmad-method install --yes --directory <project> --modules bmm --tools claude-code` — `--tools` is required for a fresh `--yes` install.
- A module is found via `module.yaml`; its `code` names `_bmad/<code>` and `[modules.<code>]`; prompt keys (`scope: user` → `config.user.toml`) become config; `module-help.csv` (13 columns) is merged into `bmad-help.csv`; skills whose `SKILL.md` `name` equals the folder are copied into `.claude/skills`.
- Modules installed by their own CLI into `_bmad/<code>` are kept as preserved modules when no source resolves.
