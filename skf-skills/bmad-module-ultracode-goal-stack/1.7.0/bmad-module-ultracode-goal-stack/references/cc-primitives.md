# cc-primitives Reference

**Version:** 2.1.306 (docs-only; pin `v2.1.306` = anthropics/claude-code commit `d014fc0f`, recorded for reference; docs fetched 2026-10-21)
**Export count:** 699 exports (documented entries listed in source skill metadata)
**Confidence:** T3 (dominant `confidence_distribution` bin: t1 0, t1_low 0, t2 0, t3 699; every claim cites an official docs page)
**Source skill:** `skf-skills/cc-primitives/2.1.306/cc-primitives`

## Key Exports

| Export | Where / how | Key facts used in this stack |
|--------|-------------|------------------------------|
| Hooks | `hooks` key in `~/.claude/settings.json`, `.claude/settings.json`, `.claude/settings.local.json`, skill/agent frontmatter | event → matcher group → handlers; entries merge across levels |
| `PreToolUse` | tool events, matcher on `tool_name` | `permissionDecision` allow/deny/ask/defer; exit 2 = deny, holds even in `bypassPermissions` |
| `Stop` / `SubagentStop` | `Stop`: no matcher; `SubagentStop`: matcher on agent type (`agent_type`; same values as `SubagentStart`) | `decision: block` + `reason`, or exit 2; check `stop_hook_active`; 8-consecutive-block cap |
| Skills | `.claude/skills/<name>/SKILL.md` | frontmatter optional (`name` defaults to the directory name); same-named skills: enterprise > personal > project |
| Headless | `claude -p` / `--print` | `--bare` skips auto-discovery of hooks and skills |
| `/goal` | slash command | session-scoped prompt-based Stop hook |
| `SessionStart` / `PostToolUse` | hook events | `SessionStart` fires when a session begins or resumes and cannot be blocked; `PostToolUse` fires after a tool call succeeds, a failed call fires `PostToolUseFailure` instead, and `EndConversation` calls skip both `PreToolUse` and `PostToolUse`; all matching hooks run in parallel |
| `additionalContext` | inside `hookSpecificOutput` (needs `hookEventName`) | top level is ignored; wrapped in a system reminder; capped at 10,000 characters |
| Plugins | `.claude-plugin/plugin.json`, default `hooks/hooks.json` | plugin hooks merge with `hooks/hooks.json`; install with `/plugin install <plugin>@<marketplace>`; a skill folder that is also a plugin needs `/reload-plugins` after `hooks/` changes |
| `CLAUDE.md` | `~/.claude/CLAUDE.md`, `./CLAUDE.md` or `./.claude/CLAUDE.md` | loaded at launch as context, not enforced configuration; by default (v2.1.277+, Project instructions = `claude-md-or-agents-md`), `AGENTS.md` is read only when no `CLAUDE.md`, `.claude/CLAUDE.md` or `CLAUDE.local.md` exists in the working directory or above it; `~/.claude/CLAUDE.md`, managed CLAUDE.md and `.claude/rules/` don't count and load alongside AGENTS.md; the default can be changed under Project instructions in `/config` |

## Usage Patterns

- Block a tool call before it runs: a `command` hook under `hooks.PreToolUse[]` that prints `hookSpecificOutput.permissionDecision: "deny"` or exits 2 with the reason on stderr.
- Keep Claude working until checks pass: a `Stop` hook returning `{"decision":"block","reason":…}` or exiting 2, guarded by `stop_hook_active`.
- Hook exit codes: `0` success (silence is not approval), `2` blocking error on events that can block (stderr becomes the reason), other codes non-blocking when stdout is plain text, empty or invalid JSON (valid stdout JSON still decides as at exit 0); with `onFailure: "block"` (v2.1.295+, `command` or `http` hooks; no effect on `Stop`, `SubagentStop`, `TaskCompleted`, `TeammateIdle` or async hooks) a run that exits with any other code counts as a failure and does what exit 2 does on that event.
- Ship a workflow as a skill: `.claude/skills/<name>/SKILL.md` with `description` frontmatter, invoked as `/<name>`.
- Add context after a tool call: a `PostToolUse` hook prints `{"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "..."}}` at exit 0.
- Ship hooks with a plugin: the plugin's `hooks/hooks.json` is loaded with the plugin, and its hooks also fire inside subagents.

## Common Imports

Compose-mode: no import statements. Claude Code primitives are configuration (settings files, skill folders, hook commands) and CLI flags, not importable APIs.
