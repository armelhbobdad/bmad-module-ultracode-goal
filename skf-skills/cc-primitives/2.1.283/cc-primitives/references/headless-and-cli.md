# Headless runs and CLI reference

## Contents

- [claude -p behaviour](#claude--p-behaviour)
- [Output formats](#output-formats)
- [Permissions in unattended runs](#permissions-in-unattended-runs)
- [Sessions](#sessions)
- [CLI commands](#cli-commands)
- [CLI flags](#cli-flags)

## claude -p behaviour

- `-p` / `--print` runs non-interactively and works with any `claude` command; stdin can be piped (10 MB cap). [EXT:https://code.claude.com/docs/en/headless]
- Exit 0 on success, non-zero on failure; invalid flags go to stderr, in-run failures are printed as the result on stdout; SIGTERM exits 143 with no result — send SIGINT to end the turn cleanly. [EXT:https://code.claude.com/docs/en/headless]
- `-p` without `--bare` runs the project's `.claude/settings.json` hooks and `.mcp.json` servers even in an untrusted folder. [EXT:https://code.claude.com/docs/en/headless]
- `--bare` skips auto-discovery of hooks, skills, commands, subagents, plugins, MCP, auto memory and CLAUDE.md, requires `ANTHROPIC_API_KEY` (or an `apiKeyHelper` in `--settings`), leaves only Bash/read/edit tools, and is slated to become the `-p` default. [EXT:https://code.claude.com/docs/en/headless]
- Background Bash tasks are killed about 5 s after the result; background subagents or workflows keep `-p` open (10-minute idle ceiling, `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS`). [EXT:https://code.claude.com/docs/en/headless]
- `--mcp-config` waits for servers up to `MCP_TIMEOUT` (30 s); invalid entries appear in `mcp_server_errors`. [EXT:https://code.claude.com/docs/en/headless]

## Output formats

`--output-format text|json|stream-json`: json returns `result`, session ID and metadata (including `total_cost_usd`); stream-json emits newline-delimited events ending in a result message; `--json-schema` fills `structured_output`; token streaming needs `stream-json --verbose --include-partial-messages`; subagent messages carry `parent_tool_use_id`; `system/init` and `system/api_retry` events report session metadata and retries. [EXT:https://code.claude.com/docs/en/headless] Costs on `--continue`/`--resume` cover the whole conversation. [EXT:https://code.claude.com/docs/en/headless]

## Permissions in unattended runs

- `-p` starts in Manual/default on every plan — pass the mode explicitly: `auto` (classifier), `dontAsk` (deny anything that would prompt), `acceptEdits`. [EXT:https://code.claude.com/docs/en/headless] [EXT:https://code.claude.com/docs/en/cli-reference]
- `--permission-prompts none` denies prompts unless a `PermissionRequest` hook allows them and removes tools needing a human (e.g. AskUserQuestion); denials are listed in `permission_denials`. [EXT:https://code.claude.com/docs/en/headless]
- `--allowedTools` pre-approves tools; `Bash(git diff *)` prefix-matches. [EXT:https://code.claude.com/docs/en/headless]

## Sessions

`--continue` (most recent; plain `--continue` skips `-p`/SDK sessions, `-p --continue` includes them), `--resume <id|name|transcript path>`, `--session-id <uuid>`, `--fork-session`, `--name`, `--no-session-persistence`; capture `session_id` from JSON output. [EXT:https://code.claude.com/docs/en/headless] [EXT:https://code.claude.com/docs/en/cli-reference] `CLAUDE_CODE_RESUME_INTERRUPTED_TURN=1` continues an interrupted turn on resume. [EXT:https://code.claude.com/docs/en/headless]

## CLI commands

| Command | Purpose |
|---------|---------|
| `claude -p "query"` | Query and exit [EXT:https://code.claude.com/docs/en/cli-reference] |
| `claude -c`, `claude -c -p "query"`, `claude -r "<session>" "query"` | Continue / resume [EXT:https://code.claude.com/docs/en/cli-reference] |
| `claude update`, `claude install [version]` | Update / reinstall [EXT:https://code.claude.com/docs/en/cli-reference] |
| `claude auth login --console`, `claude auth status` | Auth (status exits 0 when logged in) [EXT:https://code.claude.com/docs/en/cli-reference] |
| `claude agents --json` | Active background sessions [EXT:https://code.claude.com/docs/en/cli-reference] |
| `claude doctor` | Read-only diagnostics [EXT:https://code.claude.com/docs/en/cli-reference] |
| `claude mcp`, `claude mcp login <name>` | MCP servers [EXT:https://code.claude.com/docs/en/cli-reference] |
| `claude setup-token` | Long-lived token for CI [EXT:https://code.claude.com/docs/en/cli-reference] |

`claude --help` does not list every flag. [EXT:https://code.claude.com/docs/en/cli-reference]

## CLI flags

| Flag | Meaning |
|------|---------|
| `--add-dir` | Extra working directories [EXT:https://code.claude.com/docs/en/cli-reference] |
| `--agent`, `--agents` | Select an agent / define subagents as JSON [EXT:https://code.claude.com/docs/en/cli-reference] |
| `--allowedTools`, `--disallowedTools`, `--tools` | Pre-approve, remove or deny, restrict built-in tools [EXT:https://code.claude.com/docs/en/cli-reference] |
| `--append-system-prompt[-file]`, `--system-prompt[-file]`, `--append-subagent-system-prompt` | Prompt control (replace and replace-file are exclusive) [EXT:https://code.claude.com/docs/en/cli-reference] |
| `--bare` | Minimal mode (sets `CLAUDE_CODE_SIMPLE`) [EXT:https://code.claude.com/docs/en/headless] [EXT:https://code.claude.com/docs/en/cli-reference] |
| `--bg` | Background agent (not with `-p`) [EXT:https://code.claude.com/docs/en/cli-reference] |
| `--dangerously-skip-permissions` | = `--permission-mode bypassPermissions` [EXT:https://code.claude.com/docs/en/cli-reference] |
| `--debug-file <path>` | Debug log to a file [EXT:https://code.claude.com/docs/en/cli-reference] |
| `--disable-slash-commands` | Disable skills and commands [EXT:https://code.claude.com/docs/en/cli-reference] |
| `--effort low\|medium\|high\|xhigh\|max\|ultracode` | Session effort [EXT:https://code.claude.com/docs/en/cli-reference] |
| `--fallback-model` | Fallback models [EXT:https://code.claude.com/docs/en/cli-reference] |
| `--include-hook-events`, `--include-partial-messages`, `--forward-subagent-text` | Extra stream-json events [EXT:https://code.claude.com/docs/en/cli-reference] |
| `--input-format`, `--output-format`, `--json-schema`, `--verbose` | I/O [EXT:https://code.claude.com/docs/en/cli-reference] |
| `--max-budget-usd`, `--max-turns` | Print-mode limits [EXT:https://code.claude.com/docs/en/cli-reference] |
| `--mcp-config`, `--strict-mcp-config` | MCP servers [EXT:https://code.claude.com/docs/en/cli-reference] |
| `--model` | Model alias or full name [EXT:https://code.claude.com/docs/en/cli-reference] |
| `--permission-mode`, `--permission-prompt-tool`, `--permission-prompts` | Permission handling [EXT:https://code.claude.com/docs/en/cli-reference] |
| `--plugin-dir` | Session-only plugin [EXT:https://code.claude.com/docs/en/cli-reference] |
| `--setting-sources`, `--settings` | Setting sources; inline or file settings (≤2 MiB) [EXT:https://code.claude.com/docs/en/cli-reference] |
| `--system-prompt-snapshot off` | Rebuild the system prompt each request [EXT:https://code.claude.com/docs/en/cli-reference] |
| `--worktree` / `-w` | Isolated git worktree under `.claude/worktrees/` [EXT:https://code.claude.com/docs/en/cli-reference] |
