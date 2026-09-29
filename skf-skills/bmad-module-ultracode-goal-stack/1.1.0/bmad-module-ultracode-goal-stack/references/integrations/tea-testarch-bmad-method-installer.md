# tea-testarch + bmad-method-installer Integration

**Type:** Configuration Bridge
**Co-import files:** 0 (compose-mode; no codebase — the contract is documented in a constituent skill)
**Detection:** constituent-documented-contract (`detection_method: constituent_documented_contract`) — documented by tea-testarch (`references/pattern-config-and-registration.md`, Architecture at a Glance); the installer skill never names TEA
**Confidence:** T1-low (constituent-documented-contract) [composed] — weaker of tea-testarch (T1-low) and bmad-method-installer (T1-low)

## Integration Pattern

TEA registers with the installer through two files: `src/module.yaml` for its config prompts and `src/module-help.csv` for its catalogue rows (tea-testarch SKILL.md, Architecture at a Glance). These are the two module-root files the installer's Adoption Steps ask for (steps 1 and 4). The installer also requires each skill to be a folder whose SKILL.md `name` equals the folder name (step 5).

The installer turns module.yaml `code` into the `_bmad/<code>` folder and the `[modules.<code>]` table. It treats keys that carry `prompt` as config questions, and it expects a 13-column module-help.csv at the module root (installer SKILL.md, Adoption Steps).

TEA's own docs describe what the installer does for it (tea-testarch references/pattern-config-and-registration.md, module.yaml):
- TEA is not selected by default, which is consistent with the installer's `default_selected` "missing = false" rule.
- The installer inserts the core keys; TEA does not declare them.
- The installer creates `{test_artifacts}` declaratively.

The installer's generic contract never names TEA, but it is consistent with this. It spreads core values into every non-core module's `config.yaml` and creates the folders listed under `directories`. It also merges each non-core module's module-help.csv from its module root into `_bmad/_config/bmad-help.csv`. TEA's module-help.csv header lists the same 13 columns, in the same order, as the installer's Key Types.

Every TEA workflow reads its config from `{project-root}/_bmad/tea/config.yaml`. `tea_execution_mode` and `tea_capability_probe` are the exception: they resolve through CLI flags first, then that file, then `module.yaml`. Assuming the module code is `tea` (inferred from that path), this is the per-module file the installer regenerates on every install and update. Installer v6.12.0 still ships that file alongside the layered TOML introduced in v6.11.0.

TEA workflows treat a `ci_platform` that is missing on old installs as `auto`. Separately, a quick update treats a prompted key that is absent from the existing config as new, and prompts for it (silent mode applies its default). Neither skill links these two behaviours.

## Key Files

Upstream source files behind the cited lines (from the constituents' `[SRC:…]` tags):

- `src/module.yaml`
- `src/module-help.csv`
- `src/workflows/testarch/bmad-testarch-trace/workflow.yaml`
- `src/workflows/testarch/bmad-testarch-test-design/workflow.yaml`
- `src/workflows/testarch/bmad-testarch-nfr/workflow.yaml`
- `src/workflows/testarch/bmad-testarch-atdd/workflow.yaml`
- `src/workflows/testarch/bmad-testarch-automate/workflow.yaml`
- `src/workflows/testarch/bmad-testarch-test-review/steps-c/step-04-generate-report.md`
- `tools/installer/modules/official-modules.js`
- `tools/installer/modules/external-manager.js`
- `tools/installer/modules/custom-module-manager.js`
- `tools/installer/core/manifest-generator.js`
- `tools/installer/core/installer.js`
- `tools/installer/modules/module-help-schema.js`
- `tools/installer/core/uv-check.js`
- `tools/installer/set-overrides.js`
- `tools/installer/ui.js`
- `tools/installer/README.md`
- `src/bmm-skills/module.yaml`

## Usage Convention

Treat `_bmad/tea/config.yaml` as installer output: `_bmad/<code>` is replaced wholesale on install, so change TEA settings on a re-install with `--set <module>.<key>=<value>` (the module code `tea` is inferred from the `_bmad/tea/` path) rather than hand-editing the YAML. `--set` values are written verbatim, so pass `test_artifacts` as an absolute path prefixed with `{project-root}`, which TEA expects. Default a `ci_platform` missing on an old install to `auto`, as TEA does.

## Evidence

Verbatim citations from the constituent skills (file relative to the skill root, nearest heading, line):

- [from skill: tea-testarch] `references/pattern-config-and-registration.md` — ## module.yaml, L14: "Display name "Test Architect"; not selected by default in the installer."
- [from skill: tea-testarch] `references/pattern-config-and-registration.md` — ## module.yaml, L16: "Core keys (`user_name`, `communication_language`, `document_output_language`, `output_folder`, `project_root`, `project_name`) are inserted by the installer, not declared by TEA."
- [from skill: tea-testarch] `references/pattern-config-and-registration.md` — ## module.yaml, L17: "The installer creates `{test_artifacts}` declaratively."
- [from skill: tea-testarch] `references/pattern-config-and-registration.md` — ## Config keys, L22: "All workflows read them from `{project-root}/_bmad/tea/config.yaml`."
- [from skill: tea-testarch] `references/pattern-config-and-registration.md` — ## Config keys, L26: "Absolute, prefixed with `{project-root}`; root of every TEA output"
- [from skill: tea-testarch] `references/pattern-config-and-registration.md` — ## Config keys, L34: "missing on old installs → `auto`"
- [from skill: tea-testarch] `references/pattern-config-and-registration.md` — ## module-help.csv rows, L45: "Columns: `module, skill, display-name, menu-code, description, action, args, phase, preceded-by, followed-by, required, output-location, outputs`."
- [from skill: tea-testarch] `SKILL.md` — ## Architecture at a Glance, L187: "**Registration:** `src/module.yaml` (config prompts) and `src/module-help.csv` (catalogue rows)."
- [from skill: tea-testarch] `SKILL.md` — ## Migration & Deprecation Warnings, L97: "`tea_execution_mode` and `tea_capability_probe` resolve through CLI flags, then `_bmad/tea/config.yaml`, then `module.yaml`."
- [from skill: bmad-method-installer] `SKILL.md` — ## Key Types, L164: "**`module-help.csv` columns (13):** `module, skill, display-name, menu-code, description, action, args, phase, preceded-by, followed-by, required, output-location, outputs`."
- [from skill: bmad-method-installer] `references/pattern-manifests-and-help.md` — ## bmad-help.csv merge, L44: "written to `_bmad/_config/bmad-help.csv`"
- [from skill: bmad-method-installer] `SKILL.md` — ## Pattern Surface, L71: "`module-help.csv` → `_bmad/_config/bmad-help.csv`"
- [from skill: bmad-method-installer] `references/pattern-config-generation.md` — ## Quick update and config, L54: "silent mode uses defaults"
- [from skill: bmad-method-installer] `references/pattern-config-generation.md` — ## --set overrides, L44: "routed to `config.user.toml` if that file already owns the key, else `config.toml`"
- [from skill: bmad-method-installer] `references/pattern-config-generation.md` — ## --set overrides, L42: "Syntax `<module>.<key>=<value>`, repeatable"
- [from skill: bmad-method-installer] `SKILL.md` — ## Quick Start, L31: "`--modules` is a comma-separated list of module codes"
- [from skill: bmad-method-installer] `context-snippet.md` — (no heading; gotchas line), L6: "_bmad/CODE is replaced wholesale on install"
- [from skill: bmad-method-installer] `references/pattern-config-generation.md` — ## Per-module config.yaml, L30: "`copyModuleWithFiltering()` does not copy a module's root `config.yaml` (it is generated) nor its root `module.yaml` (install-time only)."
- [from skill: bmad-method-installer] `references/pattern-module-discovery.md` — ## External (registry) modules, L31: "`findExternalModuleSource()` searches `module.yaml` at the registry `module_definition` path, then `skills/` and `src/` (top level and one level deep), then the repo root"
- [from skill: bmad-method-installer] `references/pattern-module-discovery.md` — ## Finding an installed module's module.yaml, L51: "then checks `module.yaml`, `src/module.yaml` and `skills/module.yaml` in each cached external module"
- [from skill: tea-testarch] `references/pattern-release-context.md` — ## Upcoming (after v1.27.2), L18: "leave `module.yaml`; install no longer prompts for them."
- [from skill: tea-testarch] `context-snippet.md` — (no heading; key-types line), L5: "config _bmad/tea/config.yaml"
- [from skill: bmad-method-installer] `SKILL.md` — ## Adoption Steps, L47: "external registry modules are cloned to `~/.bmad/cache/external-modules` and searched at the registry `module_definition` path, then `skills/` and `src/` (one level deep), then the repo root"
- [from skill: bmad-method-installer] `SKILL.md` — ## Adoption Steps, L48: "`module.yaml` `code` becomes the module id, the `_bmad/<code>` folder and the `[modules.<code>]` TOML table."
- [from skill: bmad-method-installer] `SKILL.md` — ## Adoption Steps, L49: "**Declare config prompts as keys whose value has `prompt`.**"
- [from skill: bmad-method-installer] `SKILL.md` — ## Adoption Steps, L50: "**Put `module-help.csv` at the module root** with the 13 canonical columns; rows under 12 columns are dropped."
- [from skill: bmad-method-installer] `SKILL.md` — ## Migration & Deprecation Warnings, L83: "the per-module `config.yaml` still ships"
- [from skill: bmad-method-installer] `references/pattern-module-discovery.md` — ## Source lookup order, L18: "`OfficialModules.listAvailable()` lists only the built-in `core` and `bmm`; everything else comes from the external registry."
- [from skill: bmad-method-installer] `references/pattern-module-discovery.md` — ## Source lookup order, L18: "The installer README says external official modules must be registered in `external-official-modules.yaml` to be discoverable."
- [from skill: bmad-method-installer] `references/pattern-module-discovery.md` — ## Source lookup order, L18: "In code, `ExternalModuleManager` reads `bmad-modules.yaml` at the installer project root."
- [from skill: bmad-method-installer] `references/pattern-module-discovery.md` — ## module.yaml fields the installer reads, L67: "Pre-selection in the picker (missing = false; bmm sets `true`)"
- [from skill: bmad-method-installer] `references/pattern-module-discovery.md` — ## module.yaml fields the installer reads, L70: "Folders to create, each a single `{config_key}` reference"
- [from skill: bmad-method-installer] `references/pattern-config-generation.md` — ## Per-module config.yaml, L30: "writes `config.yaml` inside it, spreading core values into every non-core module config."
- [from skill: bmad-method-installer] `references/pattern-config-generation.md` — ## Per-module config.yaml, L30: "`detectCustomFiles()` skips `config.yaml` because it is regenerated on each install/update."
- [from skill: bmad-method-installer] `references/pattern-config-generation.md` — ## Answer collection, L15: "drops overrides for modules outside the install set with a warning"
- [from skill: bmad-method-installer] `references/pattern-config-generation.md` — ## --set overrides, L44: "also patched into `_bmad/<module>/config.yaml`; skipped when that module's `config.yaml` does not exist."
- [from skill: bmad-method-installer] `references/pattern-config-generation.md` — ## --set overrides, L45: "Values are written verbatim with no `result:` template rendering, so `{project-root}` must be passed explicitly."
- [from skill: bmad-method-installer] `references/pattern-config-generation.md` — ## Reading existing config on re-run, L50: "reads `config.toml` and `config.user.toml` first (user-scoped keys such as `user_name` avoid a re-prompt) and falls back to legacy `<module>/config.yaml` files only when no TOML values were found."
- [from skill: bmad-method-installer] `references/pattern-config-generation.md` — ## Quick update and config, L54: "prompts only for new fields via `collectModuleConfigQuick()`; a key is new only when it has a prompt and is absent from the existing config"
- [from skill: bmad-method-installer] `references/pattern-manifests-and-help.md` — ## bmad-help.csv merge, L40: "every other module contributes `module-help.csv` from its module root"
