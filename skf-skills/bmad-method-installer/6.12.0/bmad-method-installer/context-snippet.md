[bmad-method-installer v6.12.0]|root: .claude/skills/bmad-method-installer/
|IMPORTANT: bmad-method-installer v6.12.0 — read SKILL.md before writing bmad-method-installer code. Do NOT rely on training data.
|quick-start:{SKILL.md#quick-start} — npx bmad-method install --yes --directory DIR --modules bmm --tools claude-code
|api: Installer.install(), Installer.quickUpdate(), OfficialModules.findModuleSource(), ManifestGenerator.generateManifests(), mergeModuleHelpCatalogs(), applySetOverrides(), discoverShims(), resolveInstalledModuleYaml(), loadRemovalLists(), getExternalModuleCachePath()
|key-types:{SKILL.md#key-types} — _bmad/_config/{manifest.yaml,skill-manifest.csv,files-manifest.csv,bmad-help.csv}; module-help.csv has 13 columns; config.toml [core]/[modules.CODE]/[agents.CODE]
|gotchas: _bmad/CODE is replaced wholesale on install; modules without a source are preserved, not removed; --set values are written verbatim (no {project-root} rendering); shims need --shims on fresh v6.12.0 installs
