# cc-primitives Reference

**Version:** 2.1.283 (docs-only; pin `v2.1.283` = anthropics/claude-code commit `7779afb1`, recorded for reference; docs fetched 2026-09-28)
**Export count:** 16 exports (primitives listed in source skill metadata; 624 documented entries)
**Confidence:** T3 (dominant `confidence_distribution` bin: t1 0, t1_low 0, t2 0, t3 624; every claim cites an official docs page)
**Source skill:** `skf-skills/cc-primitives/2.1.283/cc-primitives`

## Key Exports

| Export | Where / how | Key facts used in this stack |
|--------|-------------|------------------------------|
| Hooks | `hooks` key in `~/.claude/settings.json`, `.claude/settings.json`, `.claude/settings.local.json`, skill/agent frontmatter | event → matcher group → handlers; entries merge across levels |
| `PreToolUse` | tool events, matcher on `tool_name` | `permissionDecision` allow/deny/ask/defer; exit 2 = deny, holds even in `bypassPermissions` |
| `Stop` / `SubagentStop` | no matcher | `decision: block` + `reason`, or exit 2; check `stop_hook_active`; 8-consecutive-block cap |
| Skills | `.claude/skills/<name>/SKILL.md` | frontmatter optional (`name` defaults to the directory name); same-named skills: enterprise > personal > project |
| Headless | `claude -p` / `--print` | `--bare` skips auto-discovery of hooks and skills |
| `/goal` | slash command | session-scoped prompt-based Stop hook |

## Usage Patterns

- Block a tool call before it runs: a `command` hook under `hooks.PreToolUse[]` that prints `hookSpecificOutput.permissionDecision: "deny"` or exits 2 with the reason on stderr.
- Keep Claude working until checks pass: a `Stop` hook returning `{"decision":"block","reason":…}` or exiting 2, guarded by `stop_hook_active`.
- Hook exit codes: `0` success (silence is not approval), `2` blocking error (stderr becomes the reason), other codes non-blocking.
- Ship a workflow as a skill: `.claude/skills/<name>/SKILL.md` with `description` frontmatter, invoked as `/<name>`.

## Common Imports

Compose-mode: no import statements. Claude Code primitives are configuration (settings files, skill folders, hook commands) and CLI flags, not importable APIs.
