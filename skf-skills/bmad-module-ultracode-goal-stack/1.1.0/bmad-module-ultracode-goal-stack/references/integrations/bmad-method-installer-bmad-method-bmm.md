# bmad-method-installer + bmad-method-bmm Integration

**Type:** Configuration Bridge
**Co-import files:** 0 (compose-mode; no codebase — the contract is documented in a constituent skill)
**Detection:** constituent-documented-contract (`detection_method: constituent_documented_contract`) — documented by bmad-method-installer and bmad-method-bmm (both sides document the crossing)
**Confidence:** T1-low (constituent-documented-contract) [composed] — weaker of bmad-method-installer (T1-low) and bmad-method-bmm (T1-low)

## Integration Pattern

BMM is a built-in module of the installer. `OfficialModules.findModuleSource()` resolves core → bmm (`src/bmm-skills`) → external → custom. `generateModuleConfigs()` writes BMM's per-module `_bmad/bmm/config.yaml` (core keys spread in). `writeCentralConfig()` writes BMM's `module.yaml` prompt answers into `[modules.bmm]` of `_bmad/config.toml` (user-scope answers go to `config.user.toml`). `mergeModuleHelpCatalogs()` merges BMM's `module-help.csv` from its module root into `_bmad/_config/bmad-help.csv`. `_setupIdes()` copies every skill in `skill-manifest.csv` into `.claude/skills/<canonicalId>`. On the BMM side, skills are discovered recursively and installed under their own `name`, so `v6-shims/` nesting does not change the install path. On a fresh v6.12.0 install, BMM's deprecated shims (`bmad-create-story`, `bmad-dev-story`, ...) are opt-in: pass `--shims` to keep them (the installer's shim prompt is skipped under `--yes`, with an explicit flag, or without a TTY).

## Key Files

Upstream source files behind the cited lines (from the constituents' `[SRC:…]` tags):

- `tools/installer/modules/official-modules.js`
- `tools/installer/modules/external-manager.js`
- `tools/installer/modules/custom-module-manager.js`
- `tools/installer/modules/module-help-schema.js`
- `tools/installer/core/installer.js`
- `tools/installer/core/manifest-generator.js`
- `tools/installer/core/manifest.js`
- `tools/installer/commands/install.js`
- `tools/installer/ide/platform-codes.yaml`
- `tools/installer/ide/_config-driven.js`
- `src/bmm-skills/module.yaml`
- `src/bmm-skills/module-help.csv`
- `src/bmm-skills/v6-shims/README.md`
- `src/bmm-skills/v6-shims/bmad-create-story/SKILL.md`
- `src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md`
- `src/core-skills/v6-shims/README.md`
- `src/core-skills/module.yaml`

## Usage Convention

Install BMM with `npx bmad-method install --yes --directory <project> --modules bmm --tools claude-code`, and add `--shims` on a fresh v6.12.0 install if anything still invokes `bmad-create-story` or `bmad-dev-story` by name. Treat `[modules.bmm]` in `_bmad/config.toml` and `_bmad/bmm/config.yaml` as installer-generated: edit `src/bmm-skills/module.yaml` / `module-help.csv` upstream, or use `--set bmm.<key>=<value>` (values are written verbatim, so pass `{project-root}` explicitly).

## Evidence

Verbatim citations from the constituent skills (file relative to the skill root, nearest heading, line):

- [from skill: bmad-method-installer] `SKILL.md` — ## Pattern Surface, L63: "Source lookup order core → bmm → external → custom"
- [from skill: bmad-method-installer] `SKILL.md` — ## Adoption Steps, L47: "Built-ins live in `src/core-skills` and `src/bmm-skills`"
- [from skill: bmad-method-installer] `references/pattern-module-discovery.md` — ## Source lookup order, L16: "`src/core-skills` for `core`, `src/bmm-skills` for `bmm`, then an external official module via `ExternalModuleManager`"
- [from skill: bmad-method-installer] `SKILL.md` — ## Pattern Surface, L70: "`generateModuleConfigs()` | Per-module `config.yaml` with core keys spread in"
- [from skill: bmad-method-installer] `SKILL.md` — ## Pattern Surface, L69: "`writeCentralConfig()` | `config.toml` / `config.user.toml` sections"
- [from skill: bmad-method-installer] `references/pattern-config-generation.md` — ## Central config.toml and config.user.toml, L34: "`writeCentralConfig()` writes team-scope answers to `_bmad/config.toml` and user-scope answers to `_bmad/config.user.toml`"
- [from skill: bmad-method-installer] `references/pattern-config-generation.md` — ## Question rendering, L26: "The bmm module shows the pattern: path-style items render `result: "{project-root}/{value}"`"
- [from skill: bmad-method-installer] `SKILL.md` — ## Pattern Surface, L71: "`mergeModuleHelpCatalogs()` | `module-help.csv` → `_bmad/_config/bmad-help.csv`"
- [from skill: bmad-method-installer] `references/pattern-manifests-and-help.md` — ## bmad-help.csv merge, L40: "every other module contributes `module-help.csv` from its module root"
- [from skill: bmad-method-installer] `SKILL.md` — ## Key Types, L164: "output-location, outputs`. [SRC:src/bmm-skills/module-help.csv:L1]"
- [from skill: bmad-method-installer] `SKILL.md` — ## Key Types, L166: "`source` is `built-in` (core, bmm), `external` (registry) or `custom`"
- [from skill: bmad-method-installer] `SKILL.md` — ## Quick Start, L38: "copy every skill in `skill-manifest.csv` into the tool's skill folder (`.claude/skills/<canonicalId>` for claude-code)"
- [from skill: bmad-method-installer] `SKILL.md` — ## Migration & Deprecation Warnings, L82: "v6.12.0: deprecated shims are opt-in on fresh installs — pass `--shims` to keep them"
- [from skill: bmad-method-installer] `context-snippet.md` — (no heading; gotchas line), L6: "shims need --shims on fresh v6.12.0 installs"
- [from skill: bmad-method-installer] `references/pattern-release-context.md` — ## Installer changes by release (T2-past), L13: "the installer now warns that `bmad-build`/`bmad-build-auto` halt without `uv` (#2704)"
- [from skill: bmad-method-bmm] `SKILL.md` — ## Architecture at a Glance, L178: "**Installer** — skills are discovered recursively and installed under their own `name`; folder nesting does not change the installed path."
- [from skill: bmad-method-bmm] `SKILL.md` — ## Migration & Deprecation Warnings, L82: "v6.12.0: deprecated shims are opt-in on fresh installs (`--shims` keeps them)"
- [from skill: bmad-method-bmm] `context-snippet.md` — (no heading; gotchas line), L6: "create-story/dev-story are deprecated shims, opt-in via --shims on fresh v6.12.0 installs"
- [from skill: bmad-method-bmm] `references/pattern-release-context.md` — ## v6.12.0 breaking changes (T2-past), L15: "Deprecated shims are opt-in on fresh installs; pass `--shims` to keep them."
- [from skill: bmad-method-bmm] `SKILL.md` — ## Pattern Surface, L57: "`src/bmm-skills/module.yaml` | `planning_artifacts`, `implementation_artifacts`, `project_knowledge` | Artifact roots every skill resolves"
- [from skill: bmad-method-bmm] `SKILL.md` — ## Pattern Surface, L58: "`src/bmm-skills/module-help.csv` | `preceded-by` / `followed-by` columns | Catalog order and phase routing for `bmad-help`"
- [from skill: bmad-method-bmm] `SKILL.md` — ## Pattern Surface, L75: "`v6-shims/README.md` (bmm + core) | shim → replacement table | Deprecated ID forwarding"
- [from skill: bmad-method-bmm] `SKILL.md` — ## Pattern Surface, L76: "full legacy workflows | Retained v6 story loop"
- [from skill: bmad-method-bmm] `SKILL.md` — ## Migration & Deprecation Warnings, L81: "`bmad-create-story` and `bmad-dev-story` are deprecated (v6.11.0, #2637, #2641) but retained in full in `v6-shims/`"
- [from skill: bmad-method-installer] `references/pattern-config-generation.md` — ## --set overrides, L45: "Values are written verbatim with no `result:` template rendering, so `{project-root}` must be passed explicitly."
