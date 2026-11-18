# Hooks

## Contents

- [Configuration](#configuration)
- [Events](#events)
- [Matchers and the if filter](#matchers-and-the-if-filter)
- [Handlers](#handlers)
- [Input](#input)
- [Exit codes](#exit-codes)
- [JSON output](#json-output)
- [PreToolUse control](#pretooluse-control)
- [Defer and resume in -p](#defer-and-resume-in--p)
- [Stop and SubagentStop control](#stop-and-subagentstop-control)
- [Prompt and agent hooks](#prompt-and-agent-hooks)
- [Security, trust and headless](#security-trust-and-headless)
- [Debugging](#debugging)

## Configuration

Hooks are defined in JSON settings files with three levels: event → matcher group → handlers. [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide] A settings file has one `hooks` object; add new events as sibling keys inside it. [EXT:https://code.claude.com/docs/en/hooks-guide]

| Location | Scope |
|----------|-------|
| `~/.claude/settings.json` | All your projects, local to the machine [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide] |
| `.claude/settings.json` | One project, committable [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide] |
| `.claude/settings.local.json` | One project, not shared (gitignored when Claude Code saves to it); labeled as local settings in `/hooks` [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide] |
| Skill frontmatter | Rest of the session once the skill is invoked [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/skills] |
| Subagent frontmatter | Only while that subagent runs; `Stop` becomes `SubagentStop` [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/sub-agents] |

Entries merge across levels; the same handler defined in more than one settings file runs once, while a plugin's or skill's copy of it stays separate; settings/policy/plugin hooks also fire inside subagents. [EXT:https://code.claude.com/docs/en/hooks] Direct edits to hooks in settings files are normally picked up automatically by the file watcher; if a change hasn't appeared after a few seconds, the watcher may have missed it, so restart the session to force a reload. [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide] `"disableAllHooks": true` disables hooks (managed hooks still run unless managed settings also set it). [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide] Settings JSON must be strict (no comments or trailing commas). [EXT:https://code.claude.com/docs/en/hooks-guide]

Example (a PreToolUse handler for Bash `rm` commands): [EXT:https://code.claude.com/docs/en/hooks]

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "if": "Bash(rm *)",
            "command": "${CLAUDE_PROJECT_DIR}/.claude/hooks/block-rm.sh",
            "args": []
          }
        ]
      }
    ]
  }
}
```

## Events

`SessionStart` (session begins or resumes), `UserPromptSubmit` (before Claude processes a prompt, also on turns Claude Code starts itself, such as a scheduled task or a background subagent's report), `PreToolUse` (after parameters are created, before the call; can block), `PostToolUse`, `SubagentStop`, `Stop` (main agent finished responding; not on user interrupt), `StopFailure` (turn ended by an API error). PreToolUse/PostToolUse fire on every tool call except `EndConversation`. [EXT:https://code.claude.com/docs/en/hooks] `SubagentStart` fires when a subagent begins. [EXT:https://code.claude.com/docs/en/sub-agents]

## Matchers and the if filter

- `"*"`, `""` or no matcher → every occurrence; only letters, digits, `_`, `-`, spaces, commas and pipes → exact string or list; anything else → unanchored JavaScript regex; case-sensitive. `FileChanged` and `StopFailure` use a narrower exact-match set (letters, digits, `_` and `|` only): a hyphen, space or comma keeps their matcher on the regex path, and only `|` separates alternatives. [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide]
- Tool events match against `tool_name`; on `PreToolUse` and `PermissionRequest` a `Bash` matcher (also `Bash|PowerShell`, `^Bash$`, `Bash.*`) runs on Monitor commands too (v2.1.314+), where its `allow` and `updatedInput` have no effect, so allowing or rewriting them needs a matcher that includes Monitor; `Stop`, `UserPromptSubmit` and similar events have no matcher support (a matcher there is silently ignored). [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide]
- The handler `if` field uses permission-rule syntax on tool events only; on other events the hook never runs; it is best-effort, so hard enforcement belongs in permission rules. [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide]
- In the `if` field, Bash patterns strip leading `VAR=value` assignments before matching, so `Bash(git *)` runs the hook for `FOO=bar git push`. [EXT:https://code.claude.com/docs/en/hooks]

## Handlers

- `type`: `command`, `http`, `mcp_tool`, `prompt`, `agent`. [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide]
- `command` is a shell command; with `args` it is spawned directly without a shell. [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide]
- `timeout` (seconds): 600 for command/http/mcp_tool on most events (30 on `UserPromptSubmit`, `PreModelSwitch` and `PostModelSwitch`; 10 on `MessageDisplay`), 30 for prompt, 60 for agent; `SessionEnd` hooks share a 1.5 s budget that a longer per-hook `timeout` raises up to 60 s; the timeout isn't enforced on an `async: true` command hook; a timed-out hook is canceled and a timed-out PreToolUse hook does not block unless `onFailure` is `"block"`. [EXT:https://code.claude.com/docs/en/hooks]
- `async: true` runs in the background and cannot block; `statusMessage` sets the spinner text. [EXT:https://code.claude.com/docs/en/hooks]
- `onFailure: "block"` on a `command` or `http` hook (v2.1.295+) makes a failure (can't start, exit code other than 0 or 2, HTTP error, timeout, invalid JSON) do what exit 2 does on that event, and deny on `PermissionRequest`; it has no effect on `Stop`, `SubagentStop`, `TaskCompleted`, `TeammateIdle` or async hooks. [EXT:https://code.claude.com/docs/en/hooks]
- All matching hooks run in parallel (at most 12 prompt or agent hooks at once), in the current directory with Claude Code's environment, minus the `OTEL_*` exporter variables and, when `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB` is `1`, the variables it strips (in a session with the HIPAA configuration, Anthropic credentials are removed too). [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide] If the current directory no longer exists, command hooks run from the first of these that still exists: the directory the session started in, the project root, the home directory or the system temp directory. [EXT:https://code.claude.com/docs/en/hooks]
- `CLAUDE_PROJECT_DIR` (the project root where the session started, which it keeps after Claude enters a worktree mid-session), `CLAUDE_PLUGIN_ROOT`, `CLAUDE_PLUGIN_DATA` are exported; `CLAUDE_ENV_FILE` only to SessionStart, Setup, CwdChanged and FileChanged. [EXT:https://code.claude.com/docs/en/hooks]
- Scripts must be executable; use absolute paths such as `${CLAUDE_PROJECT_DIR}`. [EXT:https://code.claude.com/docs/en/hooks-guide] [EXT:https://code.claude.com/docs/en/hooks]

## Input

Command hooks receive JSON on stdin (HTTP hooks as the POST body). [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide] Common fields: `session_id`, `transcript_path` (written asynchronously), `cwd`, `permission_mode` (default, plan, acceptEdits, auto, dontAsk, bypassPermissions), `hook_event_name`. [EXT:https://code.claude.com/docs/en/hooks] PreToolUse adds `tool_name`, `tool_input`, `tool_use_id` (Bash: `tool_input.command`). [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide] Stop adds `stop_hook_active`, `last_assistant_message`, `background_tasks`, `session_crons`; SubagentStop adds `agent_id`, `agent_type`, `agent_transcript_path`. [EXT:https://code.claude.com/docs/en/hooks]

## Exit codes

- `0`: success; stdout JSON is parsed; Claude never sees exit-0 stderr (debug logging shows it); silence is not approval. [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide]
- `2`: blocking error; stderr (or the JSON reason) becomes the block message; JSON `allow` cannot override it; some events (e.g. SessionStart) cannot be blocked. [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide] On events such as `Stop` and `SubagentStop`, JSON `continue: false` takes precedence over exit 2 and ends the turn (a `PreToolUse` call stays blocked with or without it); on `Stop`, `SubagentStop`, `TaskCompleted` and a plugin's `UserPromptSubmit` hook, an exit 2 with nothing on stdout whose stderr says a file is missing (such as `No such file or directory`) is a non-blocking error. [EXT:https://code.claude.com/docs/en/hooks]
- Other codes: non-blocking error for most events when stdout is plain text, empty or invalid JSON (exit 1 without JSON included), but stdout JSON that passes validation still decides as if the hook had exited 0 (for a hook whose failure blocks the action, such as one with `onFailure: "block"`, the run counts as a failure instead); a missing or non-executable script is a non-blocking error too, so a policy hook needs `onFailure: "block"` to block when it can't run. [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide]

## JSON output

Stdout must contain only the JSON object (shell-profile echoes break parsing). [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide] Universal fields: `continue` (false stops Claude after the hook runs, but it doesn't block a `PreToolUse` call, so also return `permissionDecision: "deny"` for that), `stopReason`, `systemMessage`, `suppressOutput` (no effect), `terminalSequence` (ignored in `-p` and the Agent SDK). [EXT:https://code.claude.com/docs/en/hooks] `hookSpecificOutput` needs `hookEventName`; `additionalContext` belongs inside it (top-level is ignored) and is wrapped in a system reminder; text fields are capped at 10,000 characters. [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide]

## PreToolUse control

`hookSpecificOutput.permissionDecision`: `allow` | `deny` | `ask` | `defer`, with `permissionDecisionReason` (shown to Claude for deny, to the user for ask, and only written to the debug log for allow and defer; when Claude Code denies an `ask` call in a `-p` run where no one can answer the prompt, Claude reads the reason in the tool result). [EXT:https://code.claude.com/docs/en/hooks] Deny/ask permission rules still apply whatever the hook says; conflicts resolve deny > defer > ask > allow; `updatedInput` replaces the whole input. [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide] Exit 2 equals deny. [EXT:https://code.claude.com/docs/en/hooks] Top-level `decision`/`reason` are deprecated here. [EXT:https://code.claude.com/docs/en/hooks] `defer` works only in `-p` mode and only when Claude makes a single tool call in the turn: see [Defer and resume in -p](#defer-and-resume-in--p). [EXT:https://code.claude.com/docs/en/hooks] PreToolUse fires before any permission-mode check, so a hook's deny holds in every mode, `bypassPermissions` and `dontAsk` included. [EXT:https://code.claude.com/docs/en/hooks-guide] A settings-file or plugin hook can't loosen restrictions past what permission rules allow: its `allow` skips the permission prompt, but deny and ask rules still apply, and it can't suppress the prompt for the actions no mode auto-approves, network-path reads, `requiresUserInteraction` MCP tools, tools an Agent SDK app marks `always_ask` (unless the permission mode approves the call) or connector tools the organization set to `ask` in sessions where that setting reaches Claude Code (in plan mode a file edit gets the same prompt, block or approval it would get with no hook). [EXT:https://code.claude.com/docs/en/hooks-guide] [EXT:https://code.claude.com/docs/en/hooks] `AskUserQuestion` and `ExitPlanMode` need `updatedInput` paired with `allow`. [EXT:https://code.claude.com/docs/en/hooks] Without managed settings, a `managed-mcp.json` file or a Team or Enterprise `/login` as the session's credential, an installed mod can still approve a call a PreToolUse hook blocked (in plan mode only a read-only one); a session on an API key or a long-lived `CLAUDE_CODE_OAUTH_TOKEN` isn't using that login, even when it is stored. [EXT:https://code.claude.com/docs/en/hooks-guide] [EXT:https://code.claude.com/docs/en/permissions]

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Destructive command blocked by hook"
  }
}
```

[EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide]

## Defer and resume in -p

- `defer` is for integrations that run `claude -p` as a subprocess and read its JSON output, such as an Agent SDK app or a custom UI: the turn ends with the tool call preserved, so the calling process can collect input through its own interface and resume. [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide]
- Claude Code honours it only in `-p` mode and only when Claude makes a single tool call in the turn: in interactive sessions it logs a warning and ignores the hook result, and with several tool calls at once `defer` is ignored with a warning and the tool goes through the normal permission flow. [EXT:https://code.claude.com/docs/en/hooks]
- In the decision-control table only `PreToolUse` lists `defer`: `PreModelSwitch` accepts `allow`, `deny` and `ask` but not `defer`, and `PermissionRequest` decides through `decision.behavior` (`allow` or `deny`). [EXT:https://code.claude.com/docs/en/hooks]
- `AskUserQuestion` is the typical case; a `-p` run offers it only when it has a permission host, such as an MCP tool passed with `--permission-prompt-tool`, so start the run with one. [EXT:https://code.claude.com/docs/en/hooks] With `--permission-prompts none`, Claude Code removes the tools that need an answer from a person, such as `AskUserQuestion`. [EXT:https://code.claude.com/docs/en/headless]
- With `defer`, `permissionDecisionReason` goes only to the debug log, and `updatedInput` and `additionalContext` are ignored. [EXT:https://code.claude.com/docs/en/hooks]
- When several `PreToolUse` hooks return different decisions, `deny` > `defer` > `ask` > `allow`, and every matching hook runs to completion before Claude Code merges the results. [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide] For permission rules, see [PreToolUse control](#pretooluse-control).
- An async hook's `permissionDecision` has no effect, and on `PreToolUse` a timed-out `command`, `http` or `mcp_tool` hook doesn't block the call unless its failure blocks the action (such as with `onFailure: "block"`): the call continues through the normal permission flow. [EXT:https://code.claude.com/docs/en/hooks]
- On `defer` the tool doesn't execute, the turn ends with a result carrying `stop_reason: "tool_deferred"`, and the pending tool call stays in the transcript. [EXT:https://code.claude.com/docs/en/hooks]
- The result's `deferred_tool_use` carries the tool's `id`, `name` and `input`; the documented example result also has `"type": "result"`, `"subtype": "success"` and `session_id`. [EXT:https://code.claude.com/docs/en/hooks] A `-p` run exits 0 on success and non-zero when the run fails. [EXT:https://code.claude.com/docs/en/headless]
- The calling process runs `claude -p --resume <session-id>` with the same permission host, and the same tool call fires `PreToolUse` again. [EXT:https://code.claude.com/docs/en/hooks] Capturing the session ID and how `--resume` finds a session: [Sessions](sessions-and-results.md#resume-and-continue).
- That resume can skip the prompt a `-p` run otherwise needs. [EXT:https://code.claude.com/docs/en/hooks] Claude Code sends Claude a continuation message on it, `Continue from where you left off.` by default, overridden by `CLAUDE_CODE_RESUME_PROMPT` (an empty string uses the default). [EXT:https://code.claude.com/docs/en/env-vars]
- The hook answers with `allow` and the answer in `updatedInput` (the tool executes and Claude continues), or with `deny`. [EXT:https://code.claude.com/docs/en/hooks] For `AskUserQuestion` and `ExitPlanMode`, `allow` alone is not sufficient; for `AskUserQuestion`, echo the original `questions` array and add an `answers` object mapping each question's text to the chosen answer. [EXT:https://code.claude.com/docs/en/hooks] A hook's `allow` can't skip the approval prompt of an MCP tool marked `requiresUserInteraction`, with or without `updatedInput`. [EXT:https://code.claude.com/docs/en/hooks]
- If the answer isn't ready, the hook can return `defer` again; if that resume carried a prompt, Claude answers it without the tool's result and doesn't run the call, so resume without a prompt until the hook returns `allow` or `deny`. [EXT:https://code.claude.com/docs/en/hooks]
- There is no timeout or retry limit: the session stays on disk until the `cleanupPeriodDays` retention sweep deletes it, after 30 days by default. [EXT:https://code.claude.com/docs/en/hooks]
- A `-p` resume doesn't restore a stored permission mode other than plan: it starts in the mode a new `claude -p` run would start in (see [Permissions in unattended runs](headless-and-cli.md#permissions-in-unattended-runs)), so pass `--permission-mode` or `--dangerously-skip-permissions` again if the deferred session used one. [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/sessions]
- A deferred session that ended in plan mode resumes in plan mode (v2.1.246+) only when all of these hold: `--permission-prompt-tool` is passed with `--resume` and `--permission-prompts none` isn't, `permissions.denyInsteadOfPrompting` is off, none of `--permission-mode`, `--dangerously-skip-permissions` or `--fork-session` is passed, the run isn't started through channels, and no deny rule removes `ExitPlanMode`. [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/sessions]
- In plan mode, apart from `ExitPlanMode`, a `PreToolUse` hook's `allow` has no effect on a file edit or another call that isn't read-only, though Claude Code still applies its `updatedInput`. [EXT:https://code.claude.com/docs/en/permissions]
- A result with `stop_reason: "tool_deferred_unavailable"` means the deferred call's tool isn't available in the resumed session (for example its MCP server isn't connected); `PreToolUse` doesn't fire, and `deferred_tool_use` names the tool. [EXT:https://code.claude.com/docs/en/hooks]
- From v2.1.319, while that call is pending any prompt sent doesn't reach Claude and the run exits with code 1, with a `result` field starting `<tool> isn't available, so its deferred call didn't run.` [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/env-vars] Before v2.1.319, Claude Code answered a prompt without the tool's result and dropped the call; on those versions, send a new prompt once the tool is available. [EXT:https://code.claude.com/docs/en/hooks]
- To run the call, make the tool available and resume again; to drop it, resume with a prompt and `CLAUDE_CODE_DROP_UNAVAILABLE_DEFERRED_TOOL=1` (v2.1.319+), and Claude receives an error as the call's result and answers the prompt, leaving no call pending. [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/env-vars]
- Dropping writes the `tool_deferred_unavailable` result with an empty `result` field, then Claude's answer in a second result, and exits 0 unless that answer is an error; with the variable set and no prompt, the run still drops the call and exits 1. [EXT:https://code.claude.com/docs/en/hooks]

## Stop and SubagentStop control

Top-level `decision: "block"` with a required `reason` prevents stopping; omit `decision` to allow; exit 2 routes stderr as the reason, but `continue: false` in the same output takes precedence over exit 2 and ends the turn, and an exit 2 with nothing on stdout whose stderr says a file is missing (such as `No such file or directory`) counts as a non-blocking error. [EXT:https://code.claude.com/docs/en/hooks] `additionalContext` on Stop continues the conversation as "Stop hook feedback". [EXT:https://code.claude.com/docs/en/hooks] Check `stop_hook_active` to avoid infinite loops; after eight consecutive continuations Claude Code overrides the block (`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` raises it); the count resets each time Claude calls a tool. [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide] Stop hooks fire whenever Claude finishes responding, not only at task completion. [EXT:https://code.claude.com/docs/en/hooks-guide] A SubagentStop block keeps the subagent running with the reason as its next instruction. [EXT:https://code.claude.com/docs/en/hooks]

## Prompt and agent hooks

Prompt hooks send the input to a Claude model, by default the one Claude Code uses for background functionality (`model` selects another); on Stop/SubagentStop `ok: false` feeds the reason back unless `impossible: true`. [EXT:https://code.claude.com/docs/en/hooks-guide] [EXT:https://code.claude.com/docs/en/hooks] Agent hooks are experimental (60 s, up to 50 tool turns). [EXT:https://code.claude.com/docs/en/hooks-guide]

## Security, trust and headless

Command hooks run with your full user permissions; quote shell variables. [EXT:https://code.claude.com/docs/en/hooks] Interactive sessions hold settings-file hooks until workspace trust is accepted. `-p`/SDK sessions never show the dialog and treat the folder as trusted, so hooks committed in the repository's `.claude/settings.json`, and a project skill's frontmatter hooks, run without a dialog. A project subagent's frontmatter hooks still don't run until the folder's trust dialog is accepted, and a `-p` session doesn't count as accepting it. [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/headless] [EXT:https://code.claude.com/docs/en/permissions] In `-p`, async hooks still running at teardown are cancelled. [EXT:https://code.claude.com/docs/en/hooks]

## Debugging

`/hooks` is a read-only browser; `claude --debug` writes hook details to `~/.claude/debug/<session-id>.txt`; `--debug-file <path>` picks the path; `/debug` enables logging mid-session; Ctrl+O shows the transcript; pipe sample JSON into the script to test it. [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide]
