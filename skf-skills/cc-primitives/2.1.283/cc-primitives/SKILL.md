---
name: cc-primitives
description: >
  Claude Code v2.1.283 primitives that UltraCode Goal composes, from the official docs: /goal, Auto Mode
  and permission modes, Auto Memory, PreToolUse and Stop hooks in settings.local.json, skills, subagents,
  dynamic workflows, headless claude -p and the CLI flags. Use when wiring a BMAD module into Claude Code
  through hooks, settings, skills, subagents or headless runs, or when checking how one of these primitives
  behaves. Not for BMAD skill workflows (see bmad-method-bmm).
---

# Claude Code v2.1.283 — primitives for orchestrating modules

## Overview

Docs-only reference compiled from 13 pages of the official Claude Code documentation (<https://code.claude.com/docs>), fetched 2026-09-28. The docs site is unversioned; the pin `v2.1.283` (anthropics/claude-code, commit `7779afb1`) is recorded for reference. Every claim is T3 and cites its page. The `slash-commands` URL now serves the skills page, because custom slash commands were merged into skills. [EXT:https://code.claude.com/docs/en/skills]

Covered primitives: `/goal`, Auto Mode and permission modes, CLAUDE.md and Auto Memory, settings files and precedence, hooks (`PreToolUse`, `Stop`, and the rest), skills, plugins, subagents, dynamic workflows, and headless `claude -p` with its CLI flags.

## Quick Start

Run a goal unattended in one invocation. The goal loop runs to completion, and stream JSON shows progress while it runs: [EXT:https://code.claude.com/docs/en/goal]

```bash
claude -p "/goal CHANGELOG.md has an entry for every PR merged this week" --output-format stream-json --verbose
```

- `/goal` works as a session-scoped, prompt-based Stop hook. After every turn a small fast model (Haiku by default) checks the condition: `not yet met` keeps Claude working, `met` clears the goal, `impossible` clears it with a failure reason. [EXT:https://code.claude.com/docs/en/goal]
- A goal does not change the permission mode. Pair it with auto mode for unattended goal turns; `-p` runs start in Manual/default unless a mode is passed. [EXT:https://code.claude.com/docs/en/goal] [EXT:https://code.claude.com/docs/en/permission-modes] [EXT:https://code.claude.com/docs/en/headless]
- Bound a goal with a turn or time clause (conditions are capped at 4,000 characters). [EXT:https://code.claude.com/docs/en/goal]

A `Stop` hook blocks the stop with a top-level decision: [EXT:https://code.claude.com/docs/en/hooks]

```json
{
  "decision": "block",
  "reason": "Must be provided when Claude is blocked from stopping"
}
```

<!-- [MANUAL:additional-notes] -->
<!-- Add custom notes here. This section is preserved during skill updates. -->
<!-- [/MANUAL:additional-notes] -->

## Common Workflows

**Block a dangerous command before it runs (PreToolUse):** register a `command` hook under `hooks.PreToolUse[]` with `matcher: "Bash"`. The script reads the JSON on stdin and prints `hookSpecificOutput.permissionDecision: "deny"`, or exits 2 with the reason on stderr. A deny holds even in `bypassPermissions`. [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide]

**Keep Claude working until checks pass (Stop):** return `{"decision":"block","reason":…}` or exit 2. Read `stop_hook_active` to avoid endless loops; after 8 consecutive blocks Claude Code ends the turn anyway (`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` raises the cap). [EXT:https://code.claude.com/docs/en/hooks]

**Run unattended in CI:** use `claude -p "…" --output-format json` and read `result`, `session_id` and cost; pick `--permission-mode auto|dontAsk|acceptEdits`, or `--permission-prompts none` when nobody can answer; resume with `--resume <session-id>`. [EXT:https://code.claude.com/docs/en/headless]

**Ship a workflow as a skill:** write `.claude/skills/<name>/SKILL.md` with `description` frontmatter. Invoke it with `/<name>` (also inside a `-p` prompt), and reach bundled files through `${CLAUDE_SKILL_DIR}`. [EXT:https://code.claude.com/docs/en/skills] [EXT:https://code.claude.com/docs/en/headless]

**Fan work out:** delegate to subagents defined in `.claude/agents/*.md` (or `--agents` JSON), or ask for a dynamic workflow with the keyword `ultracode` (interactive prompts only). [EXT:https://code.claude.com/docs/en/sub-agents] [EXT:https://code.claude.com/docs/en/workflows]

## Key API Summary

| Primitive | Where / how | Key facts |
|-----------|-------------|-----------|
| `/goal <condition>` | slash command; `/goal clear` (aliases stop, off, reset, none, cancel) | One per session, restored on resume, evaluator cannot run commands [EXT:https://code.claude.com/docs/en/goal] |
| Permission modes | `--permission-mode`, `permissions.defaultMode`, Shift+Tab | `default`/`manual`, `acceptEdits`, `plan`, `auto`, `dontAsk`, `bypassPermissions` [EXT:https://code.claude.com/docs/en/cli-reference] [EXT:https://code.claude.com/docs/en/permission-modes] |
| Auto Mode config | `autoMode` in `~/.claude/settings.json`, managed settings or `--settings` (ignored in project files) | `environment`, `allow`, `soft_deny`, `hard_deny`, `"$defaults"` [EXT:https://code.claude.com/docs/en/auto-mode-config] |
| Hooks | `hooks` key in `~/.claude/settings.json`, `.claude/settings.json`, `.claude/settings.local.json`, skill/agent frontmatter | event → matcher group → handlers; entries merge across levels [EXT:https://code.claude.com/docs/en/hooks] |
| `PreToolUse` | tool events, matcher on `tool_name` | `permissionDecision` allow/deny/ask/defer; exit 2 = deny [EXT:https://code.claude.com/docs/en/hooks] |
| `Stop` / `SubagentStop` | no matcher | `decision: block` + `reason`; `stop_hook_active` [EXT:https://code.claude.com/docs/en/hooks] |
| CLAUDE.md / Auto Memory | `./CLAUDE.md`, `.claude/rules/`, `~/.claude/projects/<project>/memory/MEMORY.md` | Memory is context, not enforcement; MEMORY.md first 200 lines/25KB [EXT:https://code.claude.com/docs/en/memory] |
| Settings | precedence managed > `--settings` > local > project > user | list keys like `permissions.allow` merge [EXT:https://code.claude.com/docs/en/settings] |
| Skills | `.claude/skills/<name>/SKILL.md` | Frontmatter `description`, `disable-model-invocation`, `allowed-tools`, `context: fork`, `hooks` [EXT:https://code.claude.com/docs/en/skills] |
| Subagents | `.claude/agents/`, `~/.claude/agents/`, `--agents` | Own context; `tools`, `model`, `permissionMode`, `isolation: worktree` [EXT:https://code.claude.com/docs/en/sub-agents] |
| Dynamic workflows | `ultracode` keyword, `/workflows`, `.claude/workflows/` | `agent()`, `parallel()`, `pipeline()`, `phase()`; ≤1,000 agents/run [EXT:https://code.claude.com/docs/en/workflows] |
| Headless | `claude -p` / `--print` | exit 0 success; `--output-format text\|json\|stream-json`; `--bare` [EXT:https://code.claude.com/docs/en/headless] [EXT:https://code.claude.com/docs/en/cli-reference] |

<!-- [MANUAL:api-notes] -->
<!-- Add custom notes here. This section is preserved during skill updates. -->
<!-- [/MANUAL:api-notes] -->

## CORRECTION

**Source:** _bmad-output/.skf-stage/cc-primitives/evidence-report.md
**Pattern:** replaced by
**Affected:** extraction inventory (docs-only mode)
**Detail:** - Mode: docs-only (no source tree; step 3 extraction inventory empty, replaced by the step 3c doc-fetch inventory)

## CORRECTION

**Source:** _bmad-output/.skf-stage/cc-primitives/provenance-map.json
**Pattern:** deprecated
**Affected:** PreToolUse decision fields
**Detail:** "description": "Top-level decision/reason are deprecated for PreToolUse; approve and block map to allow and deny.",

## CORRECTION

**Source:** _bmad-output/.skf-stage/cc-primitives/provenance-map.json
**Pattern:** deprecated
**Affected:** PreToolUse decision fields
**Detail:** "quote": "The deprecated values `\"approve\"` and `\"block\"` map to `\"allow\"` and `\"deny\"` respectively."

## Key Types

**Hook events used by orchestrators:** `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `SubagentStop`, `Stop`, `StopFailure`. [EXT:https://code.claude.com/docs/en/hooks]

**Hook handler `type`:** `command`, `http`, `mcp_tool`, `prompt`, `agent`; timeouts default to 600 s (command/http/mcp_tool), 30 s (prompt) and 60 s (agent). [EXT:https://code.claude.com/docs/en/hooks]

**Hook exit codes:** `0` = success (JSON on stdout is parsed; silence is not approval); `2` = blocking error (stderr becomes the reason, and JSON `allow` cannot override it); other codes = non-blocking error. [EXT:https://code.claude.com/docs/en/hooks]

**Common hook input fields:** `session_id`, `transcript_path`, `cwd`, `permission_mode`, `hook_event_name`; PreToolUse adds `tool_name`, `tool_input`, `tool_use_id`; Stop adds `stop_hook_active`, `last_assistant_message`. [EXT:https://code.claude.com/docs/en/hooks]

**Permission modes:** `default` (alias `manual`), `acceptEdits`, `plan`, `auto`, `dontAsk`, `bypassPermissions`. [EXT:https://code.claude.com/docs/en/cli-reference] [EXT:https://code.claude.com/docs/en/permission-modes]

**Output formats:** `text`, `json`, `stream-json`. [EXT:https://code.claude.com/docs/en/cli-reference]

## Architecture at a Glance

- **Settings layers:** managed, `--settings`, `.claude/settings.local.json`, `.claude/settings.json`, `~/.claude/settings.json`; hot-reloaded for most keys, including hooks. [EXT:https://code.claude.com/docs/en/settings]
- **Instructions:** CLAUDE.md hierarchy plus `.claude/rules/`, loaded as a user message after the system prompt; Auto Memory is machine-local. [EXT:https://code.claude.com/docs/en/memory]
- **Automation surfaces:** hooks (deterministic), skills (on-demand instructions), subagents (isolated contexts), workflows (scripted fan-out), headless runs. [EXT:https://code.claude.com/docs/en/hooks-guide] [EXT:https://code.claude.com/docs/en/skills] [EXT:https://code.claude.com/docs/en/sub-agents] [EXT:https://code.claude.com/docs/en/workflows] [EXT:https://code.claude.com/docs/en/headless]
- **Safety:** deny rules and PreToolUse denies hold in every mode; auto mode's classifier blocks escalations. [EXT:https://code.claude.com/docs/en/permission-modes] [EXT:https://code.claude.com/docs/en/hooks-guide]

## CLI

| Command / flag | Purpose |
|----------------|---------|
| `claude -p "query"` / `--print` | Non-interactive run [EXT:https://code.claude.com/docs/en/cli-reference] [EXT:https://code.claude.com/docs/en/headless] |
| `-c` / `--continue`, `-r` / `--resume <id\|name>`, `--session-id <uuid>` | Continue or resume sessions [EXT:https://code.claude.com/docs/en/cli-reference] |
| `--output-format`, `--input-format`, `--json-schema`, `--verbose`, `--include-partial-messages` | Machine-readable I/O [EXT:https://code.claude.com/docs/en/cli-reference] |
| `--permission-mode`, `--dangerously-skip-permissions`, `--permission-prompts none`, `--allowedTools`, `--disallowedTools` | Permissions [EXT:https://code.claude.com/docs/en/cli-reference] |
| `--max-turns`, `--max-budget-usd` | Print-mode limits [EXT:https://code.claude.com/docs/en/cli-reference] |
| `--settings`, `--setting-sources`, `--add-dir`, `--agents`, `--agent`, `--mcp-config` | Session configuration [EXT:https://code.claude.com/docs/en/cli-reference] |
| `--append-system-prompt`, `--system-prompt`, `--model`, `--effort`, `--bare` | Model and prompt [EXT:https://code.claude.com/docs/en/cli-reference] [EXT:https://code.claude.com/docs/en/headless] |
| `claude auto-mode defaults\|config\|critique\|reset`, `claude doctor`, `claude auth status` | Diagnostics [EXT:https://code.claude.com/docs/en/auto-mode-config] [EXT:https://code.claude.com/docs/en/cli-reference] |

## Full API Reference

Tier 2 references (T3, cited per page):

- `references/goal-and-permissions.md` — `/goal` lifecycle and limits, permission modes, Auto Mode configuration and classifier.
- `references/hooks.md` — hook configuration, events, matchers, handlers, exit codes, JSON output, PreToolUse and Stop control, debugging.
- `references/memory-and-settings.md` — CLAUDE.md, rules, Auto Memory, settings files, precedence and trust.
- `references/skills-and-plugins.md` — skill locations, frontmatter, substitutions, plugin manifest and layout.
- `references/subagents-and-workflows.md` — subagent definitions, delegation, limits; dynamic workflow scripts and limits.
- `references/headless-and-cli.md` — `claude -p` behaviour, output formats, exit codes, and the CLI flag table.
