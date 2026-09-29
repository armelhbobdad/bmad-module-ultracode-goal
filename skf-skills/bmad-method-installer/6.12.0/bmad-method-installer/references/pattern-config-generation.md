# Pattern: config generation

## Contents

- [Answer collection](#answer-collection)
- [Question rendering](#question-rendering)
- [Per-module config.yaml](#per-module-configyaml)
- [Central config.toml and config.user.toml](#central-configtoml-and-configusertoml)
- [--set overrides](#--set-overrides)
- [Reading existing config on re-run](#reading-existing-config-on-re-run)
- [Quick update and config](#quick-update-and-config)

## Answer collection

- `collectModuleConfigs()` parses `--set` early (values are applied later as a TOML patch), drops overrides for modules outside the install set with a warning, and seeds core from `--user-name`, `--communication-language`, `--document-output-language`, `--output-folder` or `--set core.*`. [SRC:tools/installer/ui.js:L900] [SRC:tools/installer/ui.js:L906] [SRC:tools/installer/ui.js:L918] [SRC:tools/installer/ui.js:L927] [SRC:tools/installer/ui.js:L936]
- `--yes` core defaults: `user_name` = capitalized OS username, `project_name` = directory basename, both languages `English`, `output_folder` = `_bmad-output`; applied only when no existing core config was found. [SRC:tools/installer/ui.js:L964] [SRC:tools/installer/ui.js:L968] [SRC:tools/installer/ui.js:L985]
- Merge order for core with CLI options: defaults, then existing config, then CLI/`--set`, last wins. [SRC:tools/installer/ui.js:L971]
- `OfficialModules.collectAllConfigurations()` always prepends core, offers an Express Setup vs Customize gateway for non-core modules, and receives `skipPrompts` = `--yes`. [SRC:tools/installer/modules/official-modules.js:L1111] [SRC:tools/installer/modules/official-modules.js:L1138] [SRC:tools/installer/ui.js:L1007]
- With `skipPrompts`, each question's non-function default is applied; when accepting defaults, questions without a default are still prompted. [SRC:tools/installer/modules/official-modules.js:L1598] [SRC:tools/installer/modules/official-modules.js:L1628]
- Items with `result` but no `prompt` are static values; only the computed result value per key is stored under `collectedConfig[<module>]`. [SRC:tools/installer/modules/official-modules.js:L1574] [SRC:tools/installer/modules/official-modules.js:L1739]

## Question rendering

`buildQuestion()` names each question `<module>_<key>`, replaces `{directory_name}` in defaults, renders `single-select` as a list, `multi-select` as checkboxes (choices are `{label, value}` objects), a boolean default as a confirm, validates with `regex`, and reuses an installed value as the default for non-list questions. [SRC:tools/installer/modules/official-modules.js:L1943] [SRC:tools/installer/modules/official-modules.js:L1970] [SRC:tools/installer/modules/official-modules.js:L2002] [SRC:tools/installer/modules/official-modules.js:L2005] [SRC:tools/installer/modules/official-modules.js:L2021] [SRC:tools/installer/modules/official-modules.js:L2046] [SRC:tools/installer/modules/official-modules.js:L2137] [SRC:tools/installer/modules/official-modules.js:L2097] `processResultTemplate()` substitutes `{value}`; a result template that is exactly `{value}` keeps raw booleans/numbers; `{project-root}`, `{value}` and `{directory_name}` placeholders are left untouched by `replacePlaceholders()`. [SRC:tools/installer/modules/official-modules.js:L1446] [SRC:tools/installer/modules/official-modules.js:L1682] [SRC:tools/installer/modules/official-modules.js:L1814]

The bmm module shows the pattern: path-style items render `result: "{project-root}/{value}"`, and bmm declares no pre-created directories. [SRC:src/bmm-skills/module.yaml:L31] [SRC:src/bmm-skills/module.yaml:L43] Core defaults `project_name` to `{directory_name}`. [SRC:src/core-skills/module.yaml:L16]

## Per-module config.yaml

`Installer.generateModuleConfigs()` treats every `_bmad` subfolder except `_config`, `_memory`, `memory`, `docs`, `scripts`, `custom` and `render` as a module and writes `config.yaml` inside it, spreading core values into every non-core module config. [SRC:tools/installer/core/installer.js:L1019] [SRC:tools/installer/core/installer.js:L1030] [SRC:tools/installer/core/installer.js:L1050] `copyModuleWithFiltering()` does not copy a module's root `config.yaml` (it is generated) nor its root `module.yaml` (install-time only). [SRC:tools/installer/modules/official-modules.js:L582] [SRC:tools/installer/modules/official-modules.js:L577] `detectCustomFiles()` skips `config.yaml` because it is regenerated on each install/update. [SRC:tools/installer/core/installer.js:L972]

## Central config.toml and config.user.toml

- `writeCentralConfig()` writes team-scope answers to `_bmad/config.toml` and user-scope answers to `_bmad/config.user.toml`, and never touches `_bmad/custom/config.toml` / `config.user.toml`; `ensureCustomConfigStubs()` creates those stubs but never overwrites them. [SRC:tools/installer/core/manifest-generator.js:L435] [SRC:tools/installer/core/manifest-generator.js:L436] [SRC:tools/installer/core/manifest-generator.js:L431] [SRC:tools/installer/core/manifest-generator.js:L95] [SRC:tools/installer/core/manifest-generator.js:L662]
- Scope is `user` only for prompts declaring `scope: user`. [SRC:tools/installer/core/manifest-generator.js:L463]
- Sections: `[core]`, `[modules.<code>]` (code from `module.yaml`, else module name), `[agents.<code>]` with `module` and `team`. [SRC:tools/installer/set-overrides.js:L114] [SRC:tools/installer/core/manifest-generator.js:L568] [SRC:tools/installer/core/manifest-generator.js:L560] [SRC:tools/installer/core/manifest-generator.js:L608]
- For non-core modules, keys belonging to the core schema are removed; modules without a known prompt schema have all answers written as team scope. [SRC:tools/installer/core/manifest-generator.js:L492] [SRC:tools/installer/core/manifest-generator.js:L565]
- `_installSharedScripts()` seeds `_bmad/custom/.gitignore` with `*.user.toml`. [SRC:tools/installer/core/installer.js:L734]

## --set overrides

- Syntax `<module>.<key>=<value>`, repeatable; split on the first `=` then the first `.`; the value keeps surrounding whitespace; `__proto__`/`prototype`/`constructor` are rejected; later entries win. [SRC:tools/installer/commands/install.js:L23] [SRC:tools/installer/set-overrides.js:L39] [SRC:tools/installer/set-overrides.js:L47] [SRC:tools/installer/set-overrides.js:L23] [SRC:tools/installer/set-overrides.js:L80]
- Validated before any network or filesystem work (malformed → exit 1); no schema validation of keys. [SRC:tools/installer/commands/install.js:L95] [SRC:tools/installer/set-overrides.js:L15]
- Applied after `generateManifests()` has written the TOML files; `core` → `[core]`, others → `[modules.<code>]`; routed to `config.user.toml` if that file already owns the key, else `config.toml`; also patched into `_bmad/<module>/config.yaml`; skipped when that module's `config.yaml` does not exist. [SRC:tools/installer/core/installer.js:L381] [SRC:tools/installer/set-overrides.js:L114] [SRC:tools/installer/set-overrides.js:L262] [SRC:tools/installer/set-overrides.js:L312] [SRC:tools/installer/set-overrides.js:L250]
- Values are written verbatim with no `result:` template rendering, so `{project-root}` must be passed explicitly. [SRC:tools/installer/set-overrides.js:L8]
- `upsertTomlKey()` appends a missing section at EOF and replaces an existing key in place, preserving trailing comments. [SRC:tools/installer/set-overrides.js:L151] [SRC:tools/installer/set-overrides.js:L177]

## Reading existing config on re-run

`OfficialModules.loadExistingConfig()` reads `config.toml` and `config.user.toml` first (user-scoped keys such as `user_name` avoid a re-prompt) and falls back to legacy `<module>/config.yaml` files only when no TOML values were found. [SRC:tools/installer/modules/official-modules.js:L933] [SRC:tools/installer/modules/official-modules.js:L930] [SRC:tools/installer/modules/official-modules.js:L955] [SRC:tools/installer/modules/official-modules.js:L964] `parseCentralToml()` reads only `[core]` and `[modules.<code>]` scalar values and ignores `[agents.*]`. [SRC:tools/installer/modules/official-modules.js:L2236] Core keys found in legacy module configs are hoisted under core without overwriting. [SRC:tools/installer/modules/official-modules.js:L1029]

## Quick update and config

`Installer.quickUpdate()` loads existing configs and prompts only for new fields via `collectModuleConfigQuick()`; a key is new only when it has a prompt and is absent from the existing config; silent mode uses defaults; the existing module config is the starting point. [SRC:tools/installer/core/installer.js:L1524] [SRC:tools/installer/modules/official-modules.js:L1296] [SRC:tools/installer/modules/official-modules.js:L1369] [SRC:tools/installer/modules/official-modules.js:L1393] `--set` overrides are forwarded into the install config. [SRC:tools/installer/core/installer.js:L1557]
