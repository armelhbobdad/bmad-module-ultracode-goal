# bmad-method-installer + bmad-builder Integration

**Type:** Configuration Bridge
**Co-import files:** 0 (compose-mode; no codebase — the contract is documented in a constituent skill)
**Detection:** constituent-documented-contract (`detection_method: constituent_documented_contract`) — documented by bmad-method-installer (`references/pattern-module-discovery.md`); bmad-builder mentions the installer only to scope it out
**Confidence:** T1-low (constituent-documented-contract) [composed] — weaker of bmad-method-installer (T1-low) and bmad-builder (T1-low)

## Integration Pattern

BMad Builder (module code `bmb`, `default_selected: false`) keeps `module.yaml` and `module-help.csv` under `skills/`. The installer's module-yaml search covers `skills/` (external registry clones: the `module_definition` path, then `skills/` and `src/` one level deep, then the repo root; `--list-options` also checks `skills/module.yaml`). Offline, `resolveInstalledModuleYaml()` checks `*-setup` skills for the BMB `{setup-skill}/assets/module.yaml` layout. Once found, `code: bmb` becomes `_bmad/bmb` and `[modules.bmb]`. The two prompt keys (`bmad_builder_output_folder`, `bmad_builder_reports`) go to `config.toml` unless a key declares `scope: user`. `skills/module-help.csv` rows are merged into `_bmad/_config/bmad-help.csv`. Separately, BMad Builder's own `bmad-bmb-setup` (SB) writes `config.yaml` and `config.user.yaml` into `{project-root}/_bmad` and ships `merge-help-csv.py`.

## Key Files

Upstream source files behind the cited lines (from the constituents' `[SRC:…]` tags):

- `tools/installer/modules/external-manager.js`
- `tools/installer/modules/official-modules.js`
- `tools/installer/modules/custom-module-manager.js`
- `tools/installer/modules/module-help-schema.js`
- `tools/installer/project-root.js`
- `tools/installer/core/installer.js`
- `tools/installer/core/manifest-generator.js`
- `tools/installer/list-options.js`
- `tools/installer/README.md`
- `skills/module.yaml`
- `skills/module-help.csv`

## Usage Convention

Let the installer own discovery and registration of `bmb` (`module.yaml` under `skills/`, code `bmb`, `[modules.bmb]`, help rows merged into `bmad-help.csv`). Use `bmad-bmb-setup` (SB, `-H` headless) as BMad Builder's own configure path, and do not assume the installer reads the `config.user.yaml` that SB writes. Prefer `--set bmb.<key>=<value>` for installer-managed values.

## Evidence

Verbatim citations from the constituent skills (file relative to the skill root, nearest heading, line):

- [from skill: bmad-method-installer] `references/pattern-module-discovery.md` — ## Finding an installed module's module.yaml, L49: "`*-setup` skills at the repo root / `src/skills/` / `skills/` (BMB `{setup-skill}/assets/module.yaml`)"
- [from skill: bmad-method-installer] `SKILL.md` — ## Adoption Steps, L47: "external registry modules are cloned to `~/.bmad/cache/external-modules` and searched at the registry `module_definition` path, then `skills/` and `src/` (one level deep), then the repo root"
- [from skill: bmad-method-installer] `SKILL.md` — ## Adoption Steps, L48: "`module.yaml` `code` becomes the module id, the `_bmad/<code>` folder and the `[modules.<code>]` TOML table."
- [from skill: bmad-method-installer] `SKILL.md` — ## Adoption Steps, L49: "`scope: user` routes answers to `config.user.toml`; everything else goes to `config.toml`."
- [from skill: bmad-method-installer] `SKILL.md` — ## Adoption Steps, L50: "**Put `module-help.csv` at the module root** with the 13 canonical columns; rows under 12 columns are dropped."
- [from skill: bmad-method-installer] `references/pattern-module-discovery.md` — ## Source lookup order, L18: "`OfficialModules.listAvailable()` lists only the built-in `core` and `bmm`; everything else comes from the external registry."
- [from skill: bmad-method-installer] `references/pattern-module-discovery.md` — ## External (registry) modules, L31: "Marketplace-plugin modules resolve through `.claude-plugin/marketplace.json`."
- [from skill: bmad-method-installer] `references/pattern-module-discovery.md` — ## Finding an installed module's module.yaml, L51: "checks `module.yaml`, `src/module.yaml` and `skills/module.yaml` in each cached external module"
- [from skill: bmad-method-installer] `references/pattern-config-generation.md` — ## Central config.toml and config.user.toml, L37: "modules without a known prompt schema have all answers written as team scope"
- [from skill: bmad-builder] `SKILL.md` — ## Description, L27: "`skills/module.yaml` registers the module as code `bmb`"
- [from skill: bmad-builder] `SKILL.md` — ## Description, L27: "`default_selected: false`"
- [from skill: bmad-builder] `SKILL.md` — ## Description, L27: "The npm package publishes `skills/`, `.claude-plugin/` and `CHANGELOG.md`"
- [from skill: bmad-builder] `SKILL.md` — ## Description, L25: "distributed through the BMad Marketplace or any compliant marketplace"
- [from skill: bmad-builder] `SKILL.md` — ## Configuration, L61: "`skills/module.yaml` prompts for two keys:"
- [from skill: bmad-builder] `SKILL.md` — ## Configuration, L65: "| `bmad_builder_output_folder` | Where should your custom output (agent, workflow, module config) be saved?"
- [from skill: bmad-builder] `SKILL.md` — ## Configuration, L66: "| `bmad_builder_reports` | Output for Evals, Test, Quality and Planning Reports?"
- [from skill: bmad-builder] `SKILL.md` — ## Usage Patterns, L43: "Capabilities registered in `skills/module-help.csv` (all phase `anytime`, none required):"
- [from skill: bmad-builder] `SKILL.md` — ## Usage Patterns, L47: "| SB | `bmad-bmb-setup` : configure | `-H` headless; inline values skip prompts | `config.yaml` and `config.user.yaml` → `{project-root}/_bmad` |"
- [from skill: bmad-builder] `SKILL.md` — ## Usage Patterns, L54: "| CM | `bmad-module-builder` : create-module | `-H`; `path` (skills folder or single SKILL.md) | setup skill → `bmad_builder_output_folder` |"
- [from skill: bmad-builder] `SKILL.md` — ## Scripts & Assets, L70: "`bmad-bmb-setup/scripts/merge-help-csv.py`"
- [from skill: bmad-builder] `SKILL.md` — (frontmatter description), L9: "Not for the BMAD Method BMM workflows or the installer."
