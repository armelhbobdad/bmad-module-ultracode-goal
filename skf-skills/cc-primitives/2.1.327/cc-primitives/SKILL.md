---
name: cc-primitives
description: >
  Claude Code v2.1.327 primitives that UltraCode Goal composes, from the official docs: /goal, Auto Mode,
  permission modes and permission rules, Auto Memory, PreToolUse and Stop hooks in settings.local.json, skills,
  subagents, dynamic workflows, headless claude -p and the CLI flags, and what a script driving claude -p
  sessions unattended needs: session ids and resume, the result and usage JSON, usage limits and retries,
  prompt-cache TTLs, PreToolUse defer, worktrees and background sessions. Use when wiring a BMAD module into
  Claude Code through hooks, settings, permission rules, skills, subagents or headless runs, when driving claude
  -p sessions from a script, or when checking how one of these primitives behaves. Not for BMAD skill workflows
  (see bmad-method-bmm).
---

# Claude Code v2.1.327: primitives for orchestrating modules

## Overview

Docs-only reference compiled from 28 pages of the official Claude Code documentation (<https://code.claude.com/docs>), fetched 2026-11-18. The docs site is unversioned; the pin `v2.1.327` (anthropics/claude-code, commit `9fa26078`) is recorded for reference. Every claim is T3 and cites its page. The `slash-commands` URL now serves the skills page, because custom slash commands were merged into skills. [EXT:https://code.claude.com/docs/en/skills] The `plugins-reference` URL serves the same page as `plugins/manifest-reference`, which the docs index lists instead. [EXT:https://code.claude.com/docs/en/plugins/manifest-reference]

Covered primitives: `/goal`, Auto Mode and permission modes, permission rules, CLAUDE.md and Auto Memory, settings files and precedence, hooks (`PreToolUse`, `Stop`, and the rest), skills, plugins, subagents, dynamic workflows, headless `claude -p` with its CLI flags, and, for a script that drives `claude -p` sessions: session ids and resume, the run result and its usage fields, usage limits and retries, prompt-cache TTLs, worktrees and background sessions.

## Quick Start

Run a goal unattended in one invocation. The goal loop runs to completion, and stream JSON shows progress while it runs: [EXT:https://code.claude.com/docs/en/goal]

```bash
claude -p "/goal CHANGELOG.md has an entry for every PR merged this week" --output-format stream-json --verbose
```

- `/goal` works as a session-scoped, prompt-based Stop hook. After every turn the configured small fast model checks the condition: `not yet met` keeps Claude working, `met` clears the goal, `impossible` clears it with a failure reason. [EXT:https://code.claude.com/docs/en/goal]
- A goal does not change the permission mode. Pair it with auto mode for unattended goal turns; on v2.1.302+ `-p` runs start in Manual/default when nothing sets a mode (no `--permission-mode` or `--dangerously-skip-permissions` flag and no `permissions.defaultMode` in a settings file). [EXT:https://code.claude.com/docs/en/goal] [EXT:https://code.claude.com/docs/en/permission-modes] [EXT:https://code.claude.com/docs/en/headless]
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

**Block a dangerous command before it runs (PreToolUse):** register a `command` hook under `hooks.PreToolUse[]` with `matcher: "Bash"`. The script reads the JSON on stdin and prints `hookSpecificOutput.permissionDecision: "deny"`, or exits 2 with the reason on stderr; `"onFailure": "block"` (v2.1.295+) also blocks when the script can't run. A deny holds even in `bypassPermissions`, except that when the machine has no managed settings and no `managed-mcp.json` file and the session doesn't use a Team or Enterprise `/login`, a mod you installed can approve a call the hook blocked (in plan mode, only a read-only call). [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide] From v2.1.314 a `Bash`-matcher `PreToolUse` hook also runs on shell commands Claude starts with the Monitor tool: it can deny or ask there, but its `allow` and `updatedInput` have no effect. [EXT:https://code.claude.com/docs/en/hooks]

**Keep Claude working until checks pass (Stop):** return `{"decision":"block","reason":…}` or exit 2. Read `stop_hook_active` to avoid endless loops; after 8 consecutive continuations Claude Code overrides the next block and ends the turn, and the count resets each time Claude calls a tool (`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` raises the cap). [EXT:https://code.claude.com/docs/en/hooks]

**Run unattended in CI:** use `claude -p "…" --output-format json` and read `result`, `session_id` and `total_cost_usd` (a client-side estimate that includes earlier runs' spend after `--continue`/`--resume`); pick `--permission-mode auto|dontAsk|acceptEdits`, or `--permission-prompts none` when nobody can answer. Resume with `claude -p --resume <session-id>` and pass `--permission-mode` (and `--settings`, `--mcp-config`, `--add-dir`, `--plugin-dir`, `--fallback-model`) again: a `-p` resume starts in the mode a new `-p` run would, except that a session that ended in plan mode resumes in plan mode when every condition the sessions page lists holds (among them `--permission-prompt-tool` passed and no `--permission-mode`), and it doesn't restore those flags. [EXT:https://code.claude.com/docs/en/headless] [EXT:https://code.claude.com/docs/en/sessions]

**Drive `claude -p` sessions from a script:** give each run its id up front with `--session-id <uuid>` (must be a valid UUID). [EXT:https://code.claude.com/docs/en/cli-reference] Pass `--permission-mode` on every run, resumes included: from v2.1.302 a `-p` run with no mode set starts in Manual (`default`), and a `-p` resume doesn't restore a stored mode other than plan mode. [EXT:https://code.claude.com/docs/en/permission-modes] [EXT:https://code.claude.com/docs/en/sessions] With `--output-format json` the result includes `total_cost_usd` and a per-model cost breakdown, both client-side estimates. [EXT:https://code.claude.com/docs/en/headless] In the Agent SDK's result message, `usage` counts only the top-level agent loop, while `total_cost_usd` and `modelUsage` also count subagents. [EXT:https://code.claude.com/docs/en/agent-sdk/cost-tracking] Set `CLAUDE_CODE_RETRY_WATCHDOG=1` (v2.1.186+) so `429` and `529` capacity errors retry indefinitely and a session that hits a usage limit waits out the remaining window; from v2.1.239 a standard-speed request still fails at once on a `429` that reports a spend limit or exhausted usage credits. [EXT:https://code.claude.com/docs/en/env-vars] Give each session its own worktree: worktrees Claude Code creates branch by default from the remote default branch unless `worktree.baseRef` is `"head"` (falling back to the local `HEAD` when no remote is configured or `origin/HEAD` isn't cached and can't be fetched), `claude -p --worktree` skips the workspace trust check, and `.worktreeinclude` copies files that match it and are gitignored into worktrees Claude Code creates with git. [EXT:https://code.claude.com/docs/en/worktrees] Details: [Sessions and results](references/sessions-and-results.md), [Limits and caching](references/limits-and-caching.md), [Worktrees and background sessions](references/worktrees-and-background.md).

**Pause a run at a tool call for an outside answer (defer):** in a `-p` run where Claude makes a single tool call in the turn, a `PreToolUse` hook that returns `permissionDecision: "defer"` keeps the tool from running, and the turn ends with a result carrying `stop_reason: "tool_deferred"` and the pending call (`id`, `name`, `input`) in `deferred_tool_use`. `claude -p --resume <session-id>` fires `PreToolUse` again for the same call; the hook answers `allow` (with `updatedInput`), `deny`, or `defer` again, so resume without a prompt until it answers `allow` or `deny`. There is no timeout or retry limit: the session stays on disk until the `cleanupPeriodDays` retention sweep deletes it, after 30 days by default. [EXT:https://code.claude.com/docs/en/hooks] See [Defer and resume](references/hooks.md#defer-and-resume-in--p).

**Ship a workflow as a skill:** write `.claude/skills/<name>/SKILL.md` with `description` frontmatter. Invoke it with `/<name>` (also inside a `-p` prompt), and reach bundled files through `${CLAUDE_SKILL_DIR}`. [EXT:https://code.claude.com/docs/en/skills] [EXT:https://code.claude.com/docs/en/headless]

**Fan work out:** delegate to subagents defined in `.claude/agents/*.md` (or `--agents` JSON), or ask for a dynamic workflow in plain words ("use a workflow") or with the keyword `ultracode`. The keyword is an opt-in only in a prompt you type, not in a `-p` prompt, a scheduled task or a relayed webhook. Workflows still run under `claude -p` and the Agent SDK when a `Workflow` (or `Workflow(<name>)`) allow rule, auto mode's classifier, bypass mode, a PreToolUse `allow` (not enough on its own in plan mode) or the host (`--permission-prompt-tool`, `canUseTool`) approves the launch. [EXT:https://code.claude.com/docs/en/sub-agents] [EXT:https://code.claude.com/docs/en/workflows]

## Key API Summary

| Primitive | Where / how | Key facts |
|-----------|-------------|-----------|
| `/goal <condition>` | slash command; `/goal clear` (aliases stop, off, reset, none, cancel) | One per session, restored on resume, evaluator cannot run commands [EXT:https://code.claude.com/docs/en/goal] |
| Permission modes | `--permission-mode`, `permissions.defaultMode`, Shift+Tab | `default`/`manual`, `acceptEdits`, `plan`, `auto`, `dontAsk`, `bypassPermissions` [EXT:https://code.claude.com/docs/en/cli-reference] [EXT:https://code.claude.com/docs/en/permission-modes] |
| Permission rules | `permissions.allow` / `ask` / `deny`, `--allowedTools` | deny → ask → allow; `Bash(cmd *)` also matches bare `cmd`; an allow rule doesn't match past a leading `VAR=` assignment unless the variable is known-safe, deny and ask match past any [EXT:https://code.claude.com/docs/en/permissions] |
| Auto Mode config | `autoMode` in `~/.claude/settings.json`, managed settings or `--settings` (ignored in project files) | `environment`, `allow`, `soft_deny`, `hard_deny`, `"$defaults"` [EXT:https://code.claude.com/docs/en/auto-mode-config] |
| Hooks | `hooks` key in `~/.claude/settings.json`, `.claude/settings.json`, `.claude/settings.local.json`, skill/agent frontmatter | event → matcher group → handlers; entries merge across levels [EXT:https://code.claude.com/docs/en/hooks] |
| `PreToolUse` | tool events, matcher on `tool_name` | `permissionDecision` allow/deny/ask/defer; exit 2 = deny; `defer` is honoured only under `-p` when Claude makes a single tool call in the turn (otherwise ignored with a warning), ends the turn with a result carrying `stop_reason: "tool_deferred"` and a `deferred_tool_use` field, has no timeout or retry limit, and resumes with `claude -p --resume <session-id>` [EXT:https://code.claude.com/docs/en/hooks] |
| `Stop` / `SubagentStop` | `Stop`: no matcher; `SubagentStop`: matcher on agent type (`agent_type`, same values as `SubagentStart`) | `decision: block` + `reason`; `stop_hook_active` [EXT:https://code.claude.com/docs/en/hooks] |
| CLAUDE.md / Auto Memory | `./CLAUDE.md`, `.claude/rules/`, `~/.claude/projects/<project>/memory/MEMORY.md` | Memory is context, not enforcement; MEMORY.md first 200 lines/25KB [EXT:https://code.claude.com/docs/en/memory] |
| Settings | precedence managed > `--settings` > local > project > user | list keys like `permissions.allow` merge [EXT:https://code.claude.com/docs/en/settings] |
| Skills | `.claude/skills/<name>/SKILL.md` | Frontmatter `description`, `disable-model-invocation`, `allowed-tools`, `context: fork`, `hooks` [EXT:https://code.claude.com/docs/en/skills] |
| Subagents | `.claude/agents/`, `~/.claude/agents/`, `--agents` | Own context; `tools`, `model`, `permissionMode`, `isolation: worktree` (branches from the repository's default branch, not the parent session's `HEAD`, unless `worktree.baseRef` is `"head"`; a branch name isn't accepted) [EXT:https://code.claude.com/docs/en/sub-agents] [EXT:https://code.claude.com/docs/en/worktrees] |
| Dynamic workflows | plain-words request or `ultracode` keyword (the keyword opts in only in a typed prompt, not a `-p` prompt), `/effort ultracode`, `/workflows`, `.claude/workflows/`; under `-p` or the Agent SDK a `Workflow` or `Workflow(<name>)` allow rule, auto mode's classifier, bypass mode, a PreToolUse `allow` (not enough alone in plan mode) or the host (`--permission-prompt-tool`, `canUseTool`) approves the launch | `agent()`, `parallel()`, `pipeline()`, `phase()`; up to 16 concurrent agents by default, fewer on fewer CPUs (`CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS`, 1 to 256, v2.1.269+); up to 4,096 items per `parallel()`/`pipeline()` call; 1,000 agents per run; no mid-run user input; a usage limit pauses a run (v2.1.271+, or v2.1.319+ in the Desktop Code tab) only in an interactive terminal session or a local Desktop Code tab session, signed in with a claude.ai subscription without usage-based billing, with `autoContinueAtUsageLimit` on (and, in the Code tab, the **Auto-continue when limits reset** checkbox checked), a reset within 24 hours and at most two earlier waits; under `-p`, the Agent SDK or a background session the agent fails instead [EXT:https://code.claude.com/docs/en/workflows] |
| Headless | `claude -p` / `--print` | exit 0 success; `--output-format text\|json\|stream-json`; `--bare` [EXT:https://code.claude.com/docs/en/headless] [EXT:https://code.claude.com/docs/en/cli-reference] |
| Sessions and resume | `--session-id <uuid>`, `-r`/`--resume`, `-c`/`--continue`, `--fork-session` | a `-p` resume starts in the mode a new `-p` run would, so pass `--permission-mode` again (a session that ended in plan mode resumes in plan mode only when every condition the sessions page lists holds); a session that ended inside a worktree without exiting it returns to that worktree on resume, `-p` included from v2.1.212; a deleted worktree resumes in the launch directory, and under `-p` any other refusal to re-enter the worktree stops the resume with a stderr error [EXT:https://code.claude.com/docs/en/sessions] [EXT:https://code.claude.com/docs/en/cli-reference] [EXT:https://code.claude.com/docs/en/worktrees] |
| Run result | `--output-format json` | `result`, `session_id`, `total_cost_usd` and a per-model cost breakdown (client-side estimates; after `--continue`/`--resume` they include earlier runs' spend); `usage.cache_creation` reports cache writes under `ephemeral_1h_input_tokens` and `ephemeral_5m_input_tokens`; in the Agent SDK result message, `usage` counts only the top-level agent loop and `modelUsage` counts subagents too, per model [EXT:https://code.claude.com/docs/en/headless] [EXT:https://code.claude.com/docs/en/agent-sdk/cost-tracking] [EXT:https://code.claude.com/docs/en/prompt-caching] |
| Usage and rate limits | `CLAUDE_CODE_RETRY_WATCHDOG=1`, `CLAUDE_CODE_MAX_RETRIES` | without the watchdog, failed API requests are retried up to `CLAUDE_CODE_MAX_RETRIES` times (default 10, capped at 15 as of v2.1.186), and retrying can stop earlier on `529`; with the watchdog (v2.1.186+), `429`/`529` capacity errors retry indefinitely and a usage limit is waited out, but from v2.1.239 a standard-speed `429` that reports a spend limit or exhausted usage credits fails at once [EXT:https://code.claude.com/docs/en/env-vars] |
| Prompt cache | `promptCacheTtl`, `subagentPromptCacheTtl` (v2.1.242+), `ENABLE_PROMPT_CACHING_1H`, `FORCE_PROMPT_CACHING_5M` | main conversation, `claude -p` included: one hour on a subscription within plan usage, five minutes on usage credits, an API key or a cloud provider; everything else (such as subagents, workflows and compaction) five minutes by default, apart from server-controlled helper requests that get one hour on a subscription within plan usage [EXT:https://code.claude.com/docs/en/prompt-caching] |
| Worktrees | `--worktree`/`-w`, `worktree.baseRef` (`fresh` \| `head`), `.worktreeinclude`, `WorktreeCreate` | default base `fresh` (the remote default branch, or the local `HEAD` when no remote is configured or `origin/HEAD` isn't cached and can't be fetched), never a branch name; `.worktreeinclude` copies files that match it and are gitignored, and is skipped when a `WorktreeCreate` hook creates the worktree [EXT:https://code.claude.com/docs/en/worktrees] [EXT:https://code.claude.com/docs/en/settings-reference] [EXT:https://code.claude.com/docs/en/hooks] |
| Background sessions | `claude --bg "<prompt>"`, `claude agents --json [--all]` | rejected with `-p`; `claude agents --json` is the supported way to read session state from outside Claude Code (`state`, `status`, `waitingFor`) [EXT:https://code.claude.com/docs/en/agent-view] |

<!-- [MANUAL:api-notes] -->
<!-- Add custom notes here. This section is preserved during skill updates. -->
<!-- [/MANUAL:api-notes] -->

## CORRECTION

**Source:** [EXT:https://code.claude.com/docs/en/hooks]
**Pattern:** deprecated
**Affected:** PreToolUse top-level `decision`/`reason` fields
**Detail:** Top-level `decision`/`reason` are deprecated for PreToolUse (use `hookSpecificOutput.permissionDecision`/`permissionDecisionReason`); the deprecated values `approve` and `block` map to `allow` and `deny`.

## Key Types

**Hook events used by orchestrators:** `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PermissionRequest`, `PermissionDenied`, `PostToolUse`, `SubagentStart`, `SubagentStop`, `Stop`, `StopFailure`, `Notification` (matchers such as `agent_needs_input` and `quota_auto_resume_fired`), and `WorktreeCreate` (replaces the default git behaviour for `--worktree`, `isolation: "worktree"` and background sessions) with `WorktreeRemove` for the worktrees it created. [EXT:https://code.claude.com/docs/en/hooks]

**Hook handler `type`:** `command`, `http`, `mcp_tool`, `prompt`, `agent`; timeouts default to 600 s (command/http/mcp_tool), 30 s (prompt) and 60 s (agent), except that command/http/mcp_tool default to 30 s on `UserPromptSubmit`, `PreModelSwitch` and `PostModelSwitch` and 10 s on `MessageDisplay`, and `SessionEnd` hooks share a 1.5 s budget. [EXT:https://code.claude.com/docs/en/hooks]

**Hook exit codes:** `0` = success (JSON on stdout is parsed; silence is not approval); `2` = blocking error on events that can block (stderr becomes the reason unless the printed JSON makes a blocking decision with its own reason; JSON `allow` cannot override it); any other code = non-blocking error when stdout is plain text, empty or invalid JSON, but stdout JSON that passes validation still decides as if the hook had exited 0 (with `onFailure: "block"` the run counts as a failure instead). [EXT:https://code.claude.com/docs/en/hooks]

**Common hook input fields:** `session_id`, `transcript_path`, `cwd`, `permission_mode`, `hook_event_name`; PreToolUse adds `tool_name`, `tool_input`, `tool_use_id`; Stop adds `stop_hook_active`, `last_assistant_message`. [EXT:https://code.claude.com/docs/en/hooks]

**Permission modes:** `default` (alias `manual`), `acceptEdits`, `plan`, `auto`, `dontAsk`, `bypassPermissions`. [EXT:https://code.claude.com/docs/en/cli-reference] [EXT:https://code.claude.com/docs/en/permission-modes]

**Output formats:** `text`, `json`, `stream-json`. [EXT:https://code.claude.com/docs/en/cli-reference]

**Background session `state`:** `working`, `blocked`, `done`, `failed` or `stopped`; `waitingFor` (present only while `status` is waiting) is `permission prompt`, `input needed`, `sandbox request`, `worker request` or `dialog open`. [EXT:https://code.claude.com/docs/en/agent-view]

**`worktree.baseRef`:** `"fresh"` (default: branch from `origin/<default-branch>`, falling back to the local `HEAD` when no remote is configured or `origin/HEAD` isn't cached locally and can't be fetched) or `"head"` (branch from the current local `HEAD`, unpushed commits included). [EXT:https://code.claude.com/docs/en/settings-reference] [EXT:https://code.claude.com/docs/en/worktrees]

## Architecture at a Glance

- **Settings layers:** managed, `--settings`, `.claude/settings.local.json`, `.claude/settings.json`, `~/.claude/settings.json`; a file watcher applies most edits, `permissions` and `hooks` included, to the running session without a restart, while some keys are read only at session start. [EXT:https://code.claude.com/docs/en/settings] The watcher can miss an edit: when a hook change hasn't appeared after a few seconds, restart the session to force a reload. [EXT:https://code.claude.com/docs/en/hooks-guide]
- **Instructions:** CLAUDE.md hierarchy plus `.claude/rules/`, loaded as a user message after the system prompt; Auto Memory is machine-local. [EXT:https://code.claude.com/docs/en/memory]
- **Automation surfaces:** hooks (deterministic), skills (on-demand instructions), subagents (isolated contexts), workflows (scripted fan-out), headless runs. [EXT:https://code.claude.com/docs/en/hooks-guide] [EXT:https://code.claude.com/docs/en/skills] [EXT:https://code.claude.com/docs/en/sub-agents] [EXT:https://code.claude.com/docs/en/workflows] [EXT:https://code.claude.com/docs/en/headless]
- **Parallel sessions:** `claude --worktree <name>` (also with `-p`) starts each session in its own git worktree. [EXT:https://code.claude.com/docs/en/worktrees] A background session (`claude --bg`) moves into its own worktree under `.claude/worktrees/` before editing files, unless `worktree.bgIsolation` is `"none"` or another exception the page lists applies, and `claude agents --json` reads its state from outside Claude Code. [EXT:https://code.claude.com/docs/en/agent-view]
- **Safety:** deny rules and PreToolUse denies hold in every mode, `bypassPermissions` included. The exception: without managed settings, a `managed-mcp.json` file or a Team or Enterprise `/login`, an installed mod can approve a call a PreToolUse hook blocked and some calls a deny rule refuses (in plan mode, only calls that are read-only). Auto mode's classifier blocks escalations. [EXT:https://code.claude.com/docs/en/permission-modes] [EXT:https://code.claude.com/docs/en/hooks-guide] [EXT:https://code.claude.com/docs/en/permissions]

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
| `--worktree` / `-w`, `--bg`, `claude agents --json` | Worktree sessions and background sessions ([details](references/worktrees-and-background.md)) [EXT:https://code.claude.com/docs/en/cli-reference] [EXT:https://code.claude.com/docs/en/agent-view] |
| `claude auto-mode defaults\|config\|critique\|reset`, `claude doctor`, `claude auth status` | Diagnostics [EXT:https://code.claude.com/docs/en/auto-mode-config] [EXT:https://code.claude.com/docs/en/cli-reference] |

## Full API Reference

Tier 2 references (T3, cited per page):

- `references/goal-and-permissions.md`: `/goal` lifecycle and limits, permission modes, permission rules and Bash rule matching, Auto Mode configuration and classifier.
- `references/hooks.md`: hook configuration, events, matchers, handlers, exit codes, JSON output, PreToolUse and Stop control, the PreToolUse `defer` round trip in `-p`, debugging.
- `references/memory-and-settings.md`: CLAUDE.md, rules, Auto Memory, settings files, precedence and trust.
- `references/skills-and-plugins.md`: skill locations, frontmatter, substitutions, plugin manifest and layout.
- `references/subagents-and-workflows.md`: subagent definitions, delegation, limits; dynamic workflow scripts and limits.
- `references/headless-and-cli.md`: `claude -p` behaviour, output formats, exit codes, and the CLI flag table.
- `references/sessions-and-results.md`: session ids, resume and continue under `-p`, session storage, the json and stream-json result fields, usage and cost.
- `references/limits-and-caching.md`: usage and rate limits under `-p`, retries and `CLAUDE_CODE_RETRY_WATCHDOG`, workflow concurrency and usage-limit behaviour, prompt-cache TTLs.
- `references/worktrees-and-background.md`: `claude --worktree`, `worktree.baseRef`, `.worktreeinclude`, isolation checks, `WorktreeCreate`/`WorktreeRemove`, background sessions and `claude agents --json`.
