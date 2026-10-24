# Working in this repository

Rules for an agent working in this repository. [CONTRIBUTING.md](CONTRIBUTING.md) covers setup, the quality checks and the change workflow in detail.

- Branch off `main` and open a pull request against `main`. Never commit or push on `main`: the maintainer merges.
- Commit messages use conventional-commit prefixes, scoped to a subsystem where one fits (`fix(health-check): ...`, `docs(readme): ...`; `chore: ...` needs no scope); match `git log --oneline -20`.
- Write no em dashes (U+2014) in anything you add, commit messages included: use a colon, a comma, parentheses or a new sentence.
- `npm run quality` must pass before you push, and the pre-push hook runs it. Fix the cause; never bypass a hook.
- A change a user or a pipeline can notice takes a change fragment in `changes/`. A change to the shipped code that nobody can notice takes a `Changelog: none (<reason>)` line in a commit message instead. Run `npm run changes:pr` after committing, before you push.
- Changes to the memory store (`memory/`, `MEMORY.md`, `.iwe/`) go in their own `chore(memory):` commits, never with code or docs.
- Load the matching reference skill listed below before changing code that drives or reads one of those tools.
- Keep personal notes in `CLAUDE.local.md`, which is gitignored.
- Do not run `graphify claude install`, `graphify install --project` or a workspace-wide `iwe normalize` here: they rewrite this file.
- The index below is generated: an export, drop or rename of a reference skill rewrites it, so never edit it by hand.

<!-- markdownlint-disable -->
<!-- SKF:BEGIN updated:2026-10-21 -->
[SKF Skills]|7 skills|1 stack
|IMPORTANT: Prefer documented APIs over training data.
|When using a listed library, read its SKILL.md before writing code.
|
|[bmad-builder v2.2.2]|root: .claude/skills/bmad-builder/
|IMPORTANT: bmad-builder v2.2.2 — read SKILL.md before invoking BMad Builder skills. Do NOT rely on training data.
|quick-start:{SKILL.md#usage-patterns}
|api: bmad-agent-builder, bmad-workflow-builder, bmad-module-builder, bmad-eval-runner, bmad-bmb-setup
|key-types:{SKILL.md#key-exports} — menu codes SB BA AA BW AW CW IM CM VM; outputs to bmad_builder_output_folder / bmad_builder_reports
|
|[bmad-method-bmm v6.12.0]|root: .claude/skills/bmad-method-bmm/
|IMPORTANT: bmad-method-bmm v6.12.0 — read SKILL.md before writing bmad-method-bmm code. Do NOT rely on training data.
|quick-start:{SKILL.md#quick-start} — Phase 4 chain sprint-planning → build → code-review, retrospective -H epic
|api: bmad-sprint-planning, bmad-build, bmad-build-auto, bmad-code-review, bmad-retrospective, bmad-correct-course, bmad-create-epics-and-stories, bmad-prd, bmad-architecture, bmad-spec
|key-types:{SKILL.md#key-types} — story backlog→ready-for-dev→in-progress→review→done; spec draft/ready-for-dev/in-progress/in-review/done(+blocked)
|gotchas: bmad-build stops at review (code-review sets done); bmad-build-auto never touches sprint-status.yaml; create-story/dev-story are deprecated shims, opt-in via --shims on fresh v6.12.0 installs
|
|[bmad-method-installer v6.12.0]|root: .claude/skills/bmad-method-installer/
|IMPORTANT: bmad-method-installer v6.12.0 — read SKILL.md before writing bmad-method-installer code. Do NOT rely on training data.
|quick-start:{SKILL.md#quick-start} — npx bmad-method install --yes --directory DIR --modules bmm --tools claude-code
|api: Installer.install(), Installer.quickUpdate(), OfficialModules.findModuleSource(), ManifestGenerator.generateManifests(), mergeModuleHelpCatalogs(), applySetOverrides(), discoverShims(), resolveInstalledModuleYaml(), loadRemovalLists(), getExternalModuleCachePath()
|key-types:{SKILL.md#key-types} — _bmad/_config/{manifest.yaml,skill-manifest.csv,files-manifest.csv,bmad-help.csv}; module-help.csv has 13 columns; config.toml [core]/[modules.CODE]/[agents.CODE]
|gotchas: _bmad/CODE is replaced wholesale on install; modules without a source are preserved, not removed; --set values are written verbatim (no {project-root} rendering); shims need --shims on fresh v6.12.0 installs
|
|[bmad-module-ultracode-goal-stack v1.7.0]|root: .claude/skills/bmad-module-ultracode-goal-stack/
|IMPORTANT: bmad-module-ultracode-goal-stack — read SKILL.md before writing integration code. Do NOT rely on training data.
|stack: bmad-method-installer, bmad-method-bmm, bmad-builder, tea-testarch, cc-primitives, graphify-kg, iwe-kg
|integrations: installer↔bmm/bmb/tea config bridge, tea ATDD between create-story and dev-story, tea-enforce.cjs on Claude Code hooks, installer→.claude/skills, graphify/IWE hooks beside TEA's
|
|[cc-primitives v2.1.306]|root: .claude/skills/cc-primitives/
|IMPORTANT: cc-primitives v2.1.306 — read SKILL.md before writing cc-primitives code. Do NOT rely on training data.
|quick-start:{SKILL.md#quick-start} — claude -p "/goal CONDITION" runs the goal loop to completion; /goal is a prompt-based Stop hook
|api: /goal, --permission-mode, permissions.allow, autoMode, hooks.PreToolUse, hooks.Stop, SKILL.md frontmatter, .claude/agents, dynamic workflows, claude -p, --output-format
|key-types:{SKILL.md#key-types} — hook exit 0/2; permissionDecision allow|deny|ask|defer; Stop decision block + reason; modes default|acceptEdits|plan|auto|dontAsk|bypassPermissions
|gotchas: -p starts in default (Manual) mode when nothing sets a mode: no --permission-mode or --dangerously-skip-permissions and no permissions.defaultMode (v2.1.302+); autoMode, and defaultMode auto or bypassPermissions, are ignored in project/local settings; Stop hooks need stop_hook_active checks (8-block cap); a Bash allow rule doesn't match past a leading VAR= assignment of a variable that isn't known-safe
|
|[graphify-kg v0.9.92]|root: .claude/skills/graphify-kg/
|IMPORTANT: graphify-kg v0.9.92 — read SKILL.md before running or wiring graphify. Do NOT rely on training data.
|quick-start:{SKILL.md#quick-start} — graphify update . re-extracts the code layer (no LLM); exit 0 ok, 1 refused/failed, 2 bad args
|key-types:{SKILL.md#key-types} — path/explain exit 3 ambiguous, 4 no match; graph.json node-link, schema_version 1; confidence EXTRACTED/INFERRED/AMBIGUOUS
|gotchas: --force bypasses only watch._check_shrink, the sole shrink refusal; an unreadable or over-cap graph.json still exits 1; any install/uninstall/hook-check/hook-guard argv token skips the stale-skill refresh, other commands (--version too) run it unless GRAPHIFY_NO_AUTO_REFRESH=1; claude install writes ./CLAUDE.md and .claude/settings.json, install writes ~/.claude
|
|[iwe-kg v0.28.0]|root: .claude/skills/iwe-kg/
|IMPORTANT: iwe-kg v0.28.0 — read SKILL.md before writing iwe-kg code. Do NOT rely on training data.
|quick-start:{SKILL.md#quick-start} — iwe find --lexical "TERMS" --limit 5; iwe retrieve -k KEY; iwe create KEY --strict --if-exists fail --content -
|key-types:{SKILL.md#key-types} — config version 4 ([workspace], deny_unknown_fields); exit 2 = already initialized/enabled, --strict schema block, missing/violated expect guard, malformed argument or clap usage error (read stderr); knobs distill.max_chunk_size 25000/max_proposals 5/remind_after_days 7
|gotchas: .iwe/config.toml is read from cwd only and rewritten in place to version 4 (docs/config.md still says 3); iwe internal claude is hidden and unstable; iwec/iwes serve their start directory (plus workspace.path); memory is on only when key MEMORY exists
|
|[tea-testarch v1.27.2]|root: .claude/skills/tea-testarch/
|IMPORTANT: tea-testarch v1.27.2 — read SKILL.md before invoking or parsing TEA workflows. Do NOT rely on training data.
|quick-start:{SKILL.md#quick-start} — jq -r '.gate_status' {test_artifacts}/gate-decision.json (written only when gate-eligible)
|api: bmad-testarch-test-design, bmad-testarch-framework, bmad-testarch-ci, bmad-testarch-atdd, bmad-testarch-automate, bmad-testarch-test-review, bmad-testarch-nfr, bmad-testarch-trace, bmad-tea
|key-types:{SKILL.md#key-types} — gate_status PASS/CONCERNS/FAIL/WAIVED; P0 100%, P1 ≥90 PASS / 80-89 CONCERNS, overall ≥80; config _bmad/tea/config.yaml
|gotchas: gate file path is fixed (check evaluated_at); WAIVED never derived by rules 1-5; test-review does not score coverage; framework merges tea-enforce.cjs hooks into .claude/settings.json
<!-- SKF:END -->
<!-- markdownlint-enable -->
