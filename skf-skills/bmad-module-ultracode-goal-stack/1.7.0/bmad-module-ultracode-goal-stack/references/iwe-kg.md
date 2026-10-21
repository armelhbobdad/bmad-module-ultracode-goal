# iwe-kg Reference

**Version:** 0.28.0 (iwe-org/iwe tag `iwe-v0.28.0`, commit `5edc6d9a`; the plugin wiring is from iwe-org/skills 0.14.0, commit `e3908762`)
**Export count:** 0 exports in source skill metadata (its `exports` list is empty; the skill documents 22 Pattern Surface rows)
**Confidence:** T1-low (dominant `confidence_distribution` bin: t1 90, t1_low 138, t2 0, t3 14; forge tier Deep, reference-app)
**Source skill:** `skf-skills/iwe-kg/0.28.0/iwe-kg`

## Key Exports

| Export | Where | Key facts used in this stack |
|--------|-------|------------------------------|
| `iwe internal claude hook session-start` | plugin `hooks/hooks.json`, `SessionStart` (matcher `startup\|resume\|clear\|compact\|fork`) | prints the `<iwe-memory>` block or nothing |
| `iwe internal claude hook post-tool` | plugin `hooks/hooks.json`, `PostToolUse` (matcher `Write\|Edit\|MultiEdit\|Bash`) | prints one JSON line with `hookSpecificOutput.additionalContext`, or nothing |
| `post_tool_report()` | `crates/iwe/src/internal/claude/hook/post_tool.rs` | schema check, `--strict` nudge, similar-page notice; the file is not rewritten |
| `render_memory_index()` | `crates/iwe/src/internal/claude/hook/index.rs` | the SessionStart `<iwe-memory>` block |
| `enter_memory_store()` | `crates/iwe/src/internal/claude/hook/store.rs` | memory is on iff the config loads and key `MEMORY` exists |
| `enable_memory()` | `crates/iwe/src/internal/claude/enable.rs` | `iwe internal claude enable` writes `MEMORY.md` |
| `load_config()` | `crates/diwe/src/config.rs` | reads `./.iwe/config.toml` from the current directory only and migrates it to version 4 in place |
| `write_agent_instructions()` / `register_mcp()` | `crates/iwe/src/init/agents.rs` | `iwe init` agent artifacts: the `AGENTS.md` section and the `.mcp.json` `iwe` server |

## Usage Patterns

- The plugin (`/plugin marketplace add iwe-org/skills`, then `/plugin install iwe@iwe-org`) adds both hooks; they are no-ops without `iwe` on `PATH` and print nothing without a `MEMORY` document (a run that reaches the store still migrates an older `.iwe/config.toml` in place).
- Write through `iwe`, guarded: preview with `--dry-run`, pin `--expect`, and pass `--strict` so the schema gate runs; the PostToolUse hook reports a write that ran without `--strict` and failed its schema.
- Start Claude Code at the workspace root: hooks and skills use the session's working directory verbatim.
- One allowlist rule covers the memory skills: `Bash(iwe:*)` under `permissions.allow` in `.claude/settings.json`.

## Common Imports

Compose-mode: no import statements. IWE is used here as the `iwe` CLI and the plugin's hook commands, not as an imported Rust crate.
