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
| `.claude/settings.local.json` | One project, not shared (gitignored when Claude Code saves to it); shown as "Local Settings" in `/hooks` [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide] |
| Skill frontmatter | Rest of the session once the skill is invoked [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/skills] |
| Subagent frontmatter | Only while that subagent runs; `Stop` becomes `SubagentStop` [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/sub-agents] |

Entries merge across levels; identical handlers in several files run once; settings/policy/plugin hooks also fire inside subagents. [EXT:https://code.claude.com/docs/en/hooks] Edits are picked up by the file watcher; `"disableAllHooks": true` disables hooks (managed hooks still run unless managed settings also set it). [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide] Settings JSON must be strict (no comments or trailing commas). [EXT:https://code.claude.com/docs/en/hooks-guide]

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

`SessionStart` (session begins or resumes), `UserPromptSubmit` (before processing a prompt), `PreToolUse` (after parameters are created, before the call; can block), `PostToolUse`, `SubagentStop`, `Stop` (main agent finished responding; not on user interrupt), `StopFailure` (turn ended by an API error). PreToolUse/PostToolUse fire on every tool call except `EndConversation`. [EXT:https://code.claude.com/docs/en/hooks] `SubagentStart` fires when a subagent begins. [EXT:https://code.claude.com/docs/en/sub-agents]

## Matchers and the if filter

- `"*"`, `""` or no matcher → every occurrence; only letters, digits, `_`, `-`, spaces, commas and pipes → exact string or list; anything else → unanchored JavaScript regex; case-sensitive. [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide]
- Tool events match against `tool_name`; `Stop`, `UserPromptSubmit` and similar events have no matcher support (a matcher there is silently ignored). [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide]
- The handler `if` field uses permission-rule syntax on tool events only; on other events the hook never runs; it is best-effort, so hard enforcement belongs in permission rules. [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide]

## Handlers

- `type`: `command`, `http`, `mcp_tool`, `prompt`, `agent`. [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide]
- `command` is a shell command; with `args` it is spawned directly without a shell. [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide]
- `timeout` (seconds): 600 for command/http/mcp_tool, 30 for prompt, 60 for agent; a timed-out hook is canceled and a timed-out PreToolUse hook does not block. [EXT:https://code.claude.com/docs/en/hooks]
- `async: true` runs in the background and cannot block; `statusMessage` sets the spinner text. [EXT:https://code.claude.com/docs/en/hooks]
- All matching hooks run in parallel, in the current directory with Claude Code's environment (minus `OTEL_*` exporters). [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide]
- `CLAUDE_PROJECT_DIR` (session start root, even inside a worktree), `CLAUDE_PLUGIN_ROOT`, `CLAUDE_PLUGIN_DATA` are exported; `CLAUDE_ENV_FILE` only to SessionStart, Setup, CwdChanged and FileChanged. [EXT:https://code.claude.com/docs/en/hooks]
- Scripts must be executable; use absolute paths such as `${CLAUDE_PROJECT_DIR}`. [EXT:https://code.claude.com/docs/en/hooks-guide] [EXT:https://code.claude.com/docs/en/hooks]

## Input

Command hooks receive JSON on stdin (HTTP hooks as the POST body). [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide] Common fields: `session_id`, `transcript_path` (written asynchronously), `cwd`, `permission_mode` (default, plan, acceptEdits, auto, dontAsk, bypassPermissions), `hook_event_name`. [EXT:https://code.claude.com/docs/en/hooks] PreToolUse adds `tool_name`, `tool_input`, `tool_use_id` (Bash: `tool_input.command`). [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide] Stop adds `stop_hook_active`, `last_assistant_message`, `background_tasks`, `session_crons`; SubagentStop adds `agent_id`, `agent_type`, `agent_transcript_path`. [EXT:https://code.claude.com/docs/en/hooks]

## Exit codes

- `0`: success; stdout JSON is parsed; exit-0 stderr goes only to the debug log; silence is not approval. [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide]
- `2`: blocking error; stderr (or the JSON reason) becomes the block message; JSON `allow` cannot override it; some events (e.g. SessionStart) cannot be blocked. [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide]
- Other codes: non-blocking error for most events (exit 1 without JSON included); a missing or non-executable script also fails silently as non-blocking — policy hooks should exit 2. [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide]

## JSON output

Stdout must contain only the JSON object (shell-profile echoes break parsing). [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide] Universal fields: `continue` (false stops Claude and wins over event decisions), `stopReason`, `systemMessage`, `suppressOutput` (no effect). [EXT:https://code.claude.com/docs/en/hooks] `hookSpecificOutput` needs `hookEventName`; `additionalContext` belongs inside it (top-level is ignored) and is wrapped in a system reminder; text fields are capped at 10,000 characters. [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide]

## PreToolUse control

`hookSpecificOutput.permissionDecision`: `allow` | `deny` | `ask` | `defer`, with `permissionDecisionReason` (shown to Claude for deny, to the user for allow/ask). [EXT:https://code.claude.com/docs/en/hooks] Deny/ask permission rules still apply whatever the hook says; conflicts resolve deny > defer > ask > allow; `updatedInput` replaces the whole input. [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide] Exit 2 equals deny. [EXT:https://code.claude.com/docs/en/hooks] Top-level `decision`/`reason` are deprecated here. [EXT:https://code.claude.com/docs/en/hooks] `defer` works only in `-p` mode. [EXT:https://code.claude.com/docs/en/hooks] PreToolUse fires before permission-mode checks, so a deny holds even in bypass; hooks tighten but cannot loosen restrictions. [EXT:https://code.claude.com/docs/en/hooks-guide]

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

## Stop and SubagentStop control

Top-level `decision: "block"` with a required `reason` prevents stopping; omit `decision` to allow; exit 2 routes stderr as the reason. [EXT:https://code.claude.com/docs/en/hooks] `additionalContext` on Stop continues the conversation as "Stop hook feedback". [EXT:https://code.claude.com/docs/en/hooks] Check `stop_hook_active` to avoid infinite loops; after eight consecutive continuations Claude Code overrides the block (`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` raises it). [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide] Stop hooks fire whenever Claude finishes responding, not only at task completion. [EXT:https://code.claude.com/docs/en/hooks-guide] A SubagentStop block keeps the subagent running with the reason as its next instruction. [EXT:https://code.claude.com/docs/en/hooks]

## Prompt and agent hooks

Prompt hooks send the input to Haiku by default (`model` selects another); on Stop/SubagentStop `ok: false` feeds the reason back unless `impossible: true`. [EXT:https://code.claude.com/docs/en/hooks-guide] [EXT:https://code.claude.com/docs/en/hooks] Agent hooks are experimental (60 s, up to 50 tool turns). [EXT:https://code.claude.com/docs/en/hooks-guide]

## Security, trust and headless

Command hooks run with your full user permissions; quote shell variables. [EXT:https://code.claude.com/docs/en/hooks] Interactive sessions hold settings-file hooks until workspace trust is accepted; `-p`/SDK sessions treat the folder as trusted and run committed project hooks without a dialog. [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/headless] In `-p`, async hooks still running at teardown are cancelled. [EXT:https://code.claude.com/docs/en/hooks]

## Debugging

`/hooks` is a read-only browser; `claude --debug` writes hook details to `~/.claude/debug/<session-id>.txt`; `--debug-file <path>` picks the path; `/debug` enables logging mid-session; Ctrl+O shows the transcript; pipe sample JSON into the script to test it. [EXT:https://code.claude.com/docs/en/hooks] [EXT:https://code.claude.com/docs/en/hooks-guide]
