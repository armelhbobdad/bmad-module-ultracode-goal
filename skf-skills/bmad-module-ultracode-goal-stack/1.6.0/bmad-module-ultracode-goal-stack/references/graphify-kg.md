# graphify-kg Reference

**Version:** 0.9.92 (Graphify-Labs/graphify tag `v0.9.92`, commit `86c57be8`; PyPI `graphifyy`, console scripts `graphify` and `graphify-mcp`)
**Export count:** 0 exports in source skill metadata (its `exports` list is empty; the skill documents 14 Pattern Surface rows and its provenance map holds 77 AST-verified definitions)
**Confidence:** T1 (dominant `confidence_distribution` bin: t1 77, t1_low 0, t2 0, t3 0; forge tier Deep, reference-app)
**Source skill:** `skf-skills/graphify-kg/0.9.92/graphify-kg`

## Key Exports

| Export | Where | Key facts used in this stack |
|--------|-------|------------------------------|
| `graphify update .` | `dispatch_command("update")` (`graphify/cli.py`) → `_rebuild_code()` (`graphify/watch.py`) | full code-layer rebuild, no LLM; exit 0 updated or unchanged, 1 refused or failed, 2 bad arguments; `--force` or `GRAPHIFY_FORCE=1` overrides the shrink guard |
| `to_json()` | `graphify/export.py` | graph.json writer |
| `backup_if_protected()` | `graphify/export.py` | dated backups of graph.json and the other protected artifacts |
| `claude_install()` | `graphify/install.py` | `## graphify` section in `./CLAUDE.md`; two `PreToolUse` guards in `./.claude/settings.json` |
| `claude_uninstall()` | `graphify/install.py` | removes the graphify skill tree (bare call: the user-global `~/.claude/skills/graphify/`; `project_dir`/`project=True`: the project skill), strips the `## graphify` section from CLAUDE.md, CLAUDE.local.md and .claude/CLAUDE.local.md, and strips the graphify `PreToolUse` hooks from .claude/settings.json and settings.local.json |
| `hook-guard search` / `hook-guard read` | `graphify/cli.py` | reads the tool call JSON on stdin, prints a JSON nudge or nothing, always exits 0; strict mode denies through `permissionDecision: deny` |

## Usage Patterns

- Finalize refresh (`skills/ultracode-goal/references/finalize.md`; mode `refresh` only, when `graphify` is on PATH and `graphify-out/graph.json` exists): from `{project-root}`, run `GRAPHIFY_NO_AUTO_REFRESH=1 timeout 300 graphify update .`, the assignment first, with no other flags or variables. The assignment turns off graphify's pre-command housekeeping (`_refresh_stale_skills()` and `_refresh_v1_opencode_plugins()` in `graphify/__main__.py`: re-copying its stale installed skill files after an upgrade, replacing an outdated graphify OpenCode plugin or dropping its stale `opencode.json` entry under `.opencode/`), so the refresh writes only `graphify-out/` (or wherever `GRAPHIFY_OUT` points); after a graphify upgrade it still prints graphify's stale-skill warning, which Finalize does not act on. Any non-zero exit, timeout or refusal to execute is logged as one `WARN graphify-refresh-failed` line in `.decision-log.md` and never retried. To allowlist the refresh, allowlist the whole line: Claude Code does not match an allow rule past a leading assignment of a variable it does not know. graphify-kg's generic shell form is `timeout 300 graphify update . || echo "graphify-refresh-failed: $?"`.
- A refusal leaves graph.json as it was and prints a `[graphify] WARNING: ... Refusing to overwrite` line on stderr; re-run with `--force` only when the loss is intended.
- `graphify claude install` writes the `## graphify` section and the two `PreToolUse` guards. `graphify claude uninstall` strips the `## graphify` section from `CLAUDE.md`, `CLAUDE.local.md` and `.claude/CLAUDE.local.md`, and the graphify hooks from `.claude/settings.json` and `.claude/settings.local.json`. Without `--project` it also deletes the user-global skill `~/.claude/skills/graphify/`. With `--project` it removes the project skill instead and strips the `# graphify` registration from `./.claude/CLAUDE.md`. No uninstaller removes the `# graphify` registration in `~/.claude/CLAUDE.md`.
- `graphify install` (user scope) copies the skill to `~/.claude/skills/graphify/` and registers it under `# graphify` in `~/.claude/CLAUDE.md`.

## Common Imports

Compose-mode: no import statements. graphify is used here as a CLI (`graphify`, `graphify-mcp`) and through the Claude Code configuration it writes, not as an imported Python API.
