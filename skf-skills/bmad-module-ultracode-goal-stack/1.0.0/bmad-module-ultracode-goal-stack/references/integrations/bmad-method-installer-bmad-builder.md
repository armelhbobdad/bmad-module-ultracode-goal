# bmad-method-installer + bmad-builder

- **Type:** Configuration Bridge
- **Detection:** constituent-documented-contract (compose-mode; no co-import files)
- **Confidence:** T1-low (constituent-documented-contract) [composed]

BMad Builder (code `bmb`) is an external module. The installer clones external registry modules to `~/.bmad/cache/external-modules` and searches for `module.yaml` at the registry `module_definition` path, then `skills/` and `src/` (one level deep), then the repo root; BMad Builder keeps `skills/module.yaml`. Offline, `resolveInstalledModuleYaml()` also checks `*-setup` skills under `skills/` (BMB `{setup-skill}/assets/module.yaml`). The two `bmb` prompt keys land in `[modules.bmb]` of `_bmad/config.toml`; `skills/module-help.csv` rows are merged into `bmad-help.csv`.

**Convention:** `bmad-bmb-setup` (SB) is BMad Builder's own configure path — it writes `config.yaml` and `config.user.yaml` into `{project-root}/_bmad`.

Evidence: [from skill: bmad-method-installer] Adoption Steps 1–4; `references/pattern-module-discovery.md` (BMB setup-skill layout). [from skill: bmad-builder] Configuration table; Usage Patterns row SB.
