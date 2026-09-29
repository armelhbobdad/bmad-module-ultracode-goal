# Release and issue context (T2)

Temporal context fetched on 2026-09-28 from the upstream repository (releases, CHANGELOG, merged PRs, issues) and indexed as the QMD collection `bmad-method-installer-temporal`. T2-past entries explain how the v6.12.0 installer got here; T2-future entries are issues open at fetch time and may change after v6.12.0.

## Contents

- [Installer changes by release (T2-past)](#installer-changes-by-release-t2-past)
- [Open upstream issues at fetch time (T2-future)](#open-upstream-issues-at-fetch-time-t2-future)

## Installer changes by release (T2-past)

- **v6.12.0** — deprecated shims are opt-in on fresh installs (`--shims` keeps them); Polytoken, Grok and ZCode added as install targets. [QMD:bmad-method-installer-temporal:releases.md]
- **v6.11.0** — config moved to layered TOML and `uv` + Python 3.11 became required for rendered skills; the per-module `_bmad/<module>/config.yaml` still ships; removed skills (`bmad-check-implementation-readiness`, `bmad-agent-tech-writer`, `bmad-index-docs`, `bmad-shard-doc`) were listed in `removals.txt`; the directory prompt no longer installs to an untyped path (#2680); the installer now warns that `bmad-build`/`bmad-build-auto` halt without `uv` (#2704). [QMD:bmad-method-installer-temporal:releases.md]
- **v6.10.0** — `bmad-loop` became an opt-in installer module whose skills sit behind `.claude-plugin/marketplace.json` rather than a plain `module.yaml` folder (#2532). [QMD:bmad-method-installer-temporal:releases.md]
- **v6.9.0** — the installer started checking for `uv`; new targets hermes-agent and CodeWhale. [QMD:bmad-method-installer-temporal:releases.md]
- **v6.8.0** — the installer reads `config.toml` on re-run (`parseCentralToml`), so user-scoped answers are no longer re-prompted; quick-update refreshes stale custom-source caches and keeps the previous clone when `git fetch` fails. [QMD:bmad-method-installer-temporal:releases.md]
- **v6.7.0** — the community modules picker was removed (previously installed community modules are preserved; install them headlessly with `--custom-source`); the remote marketplace registry was retired; registry entries can declare `plugin_name`; `findExternalModuleSource()` throws an actionable error naming the module (#2377). [QMD:bmad-method-installer-temporal:releases.md]
- **v6.6.0** — `project_name` moved from `[modules.bmm]` to `[core]` (auto-migrated); `--set <module>.<key>=<value>` and `--list-options [module]` added for non-interactive config (#2354); malformed `module.yaml` is rejected before crashing (#2348). [QMD:bmad-method-installer-temporal:releases.md]
- **Closed issue #2691** — `generateModuleConfigs` rewrote per-module `config.yaml` on every install although `loadExistingConfig` reads `config.toml` first. [QMD:bmad-method-installer-temporal:issues.md]

## Open upstream issues at fetch time (T2-future)

- **#2978** — reinstall turns list-valued (multi-select) answers into JSON strings in `_bmad/<module>/config.yaml` and `config.toml`; `parseCentralToml` has no array branch. [QMD:bmad-method-installer-temporal:issues.md]
- **#2883** — on a fresh 6.12.0 install, `skill-manifest.csv` paths resolve to nothing and `bmad-help.csv` mixes two phase naming schemes. [QMD:bmad-method-installer-temporal:issues.md]
- **#2869** — `install --action quick-update --yes` fails for locally sourced custom modules ("Source for module … is not available"); `bmadDir` is not forwarded to the source lookup. [QMD:bmad-method-installer-temporal:issues.md]
- **#2907** — custom module version display ignores the version resolved from `marketplace.json`. [QMD:bmad-method-installer-temporal:issues.md]
- **#2841** — no documented way to install the official modules when core comes from the Skills CLI or a plugin. [QMD:bmad-method-installer-temporal:issues.md]
- **#2821** — `resolve_customization.py` silently discards a customization layer on a parse error and exits 0. [QMD:bmad-method-installer-temporal:issues.md]
