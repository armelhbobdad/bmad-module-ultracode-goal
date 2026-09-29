# bmad-method-installer + bmad-method-bmm

- **Type:** Configuration Bridge
- **Detection:** constituent-documented-contract (compose-mode; no co-import files)
- **Confidence:** T1 (constituent-documented-contract) [composed]

The installer treats BMM as a built-in module: `findModuleSource()` resolves core → bmm → external → custom; `generateModuleConfigs()` writes BMM's `config.yaml` and the central `config.toml` / `config.user.toml` from `src/bmm-skills/module.yaml` prompts; `mergeModuleHelpCatalogs()` merges `src/bmm-skills/module-help.csv` into `_bmad/_config/bmad-help.csv`; skills in `skill-manifest.csv` are copied into `.claude/skills/<canonicalId>`.

**Convention:** on a fresh v6.12.0 install, BMM's deprecated shims (`bmad-create-story`, `bmad-dev-story`, …) are installed only with `--shims`.

Evidence: [from skill: bmad-method-installer] Pattern Surface rows 5, 12, 13; Key Types (`module-help.csv` columns cite `src/bmm-skills/module-help.csv`); Migration (`--shims`). [from skill: bmad-method-bmm] Pattern Surface rows 2, 19, 20.
