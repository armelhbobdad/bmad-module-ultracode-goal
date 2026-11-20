# Headless runs and CLI reference

## Contents

- [claude -p behaviour](#claude--p-behaviour)
- [Output formats](#output-formats)
- [Permissions in unattended runs](#permissions-in-unattended-runs)
- [Sessions](#sessions)
- [CLI commands](#cli-commands)
- [CLI flags](#cli-flags)

## claude -p behaviour

- `-p` / `--print` runs any `claude` command non-interactively, but not every option combines with it: `--bg`, and `--cloud` with a task description, are rejected with an error; stdin can be piped (10 MB cap). [EXT:https://code.claude.com/docs/en/headless]
- Exit 0 on success, non-zero on failure; invalid flags go to stderr, in-run failures are printed as the result on stdout; SIGTERM exits 143 with no result — send SIGINT to end the turn cleanly. [EXT:https://code.claude.com/docs/en/headless]
- `-p` without `--bare` runs the project's `.claude/settings.json` hooks and `.mcp.json` servers even in an untrusted folder. [EXT:https://code.claude.com/docs/en/headless]
- `--bare` skips auto-discovery of hooks, skills, commands, subagents, plugins, MCP, auto memory and `CLAUDE.md` (skills in an `--add-dir` directory still load). Hooks passed with `--settings` or in a plugin loaded by flag still don't run, so don't use bare mode for a run that needs hooks. It never reads OAuth credentials or the keychain, so on the Anthropic API it needs `ANTHROPIC_API_KEY` or an `apiKeyHelper` in `--settings`; Bedrock, Google Cloud's Agent Platform and Foundry keep reading their own provider credentials. It leaves only Bash/read/edit tools, sends no system reminders and runs no background commands or background subagents (from v2.1.286; before it, every `--bare` session sent system reminders and background tasks stayed available), and is slated to become the `-p` default. [EXT:https://code.claude.com/docs/en/headless] Under `--bare`, the project's `env` block and helpers such as `awsAuthRefresh` in its settings files still apply, and Claude Code reads `apiKeyHelper` only from `--settings`. [EXT:https://code.claude.com/docs/en/permissions]
- After Claude's turn ends and stdin has closed, `-p` waits for background work Claude started. For a background command the main conversation started, it waits until the command exits or reaches its time limit, and Claude then takes one more turn. For background subagents and workflows, it waits until each one finishes or the 10-minute cap ends the wait. For Monitor watches, it waits until the watch times out (five minutes by default) or the cap ends the wait. For pending self-paced `/loop` wakeups in a run whose prompt was passed as text, it waits even past the cap. Unless a main-conversation background command is still running, Claude Code stops whatever is still running after 10 minutes of continuous idle waiting and drops its partial result (`CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS`, `0` for no cap); reaching `--max-budget-usd` stops the remaining background work. [EXT:https://code.claude.com/docs/en/headless]
- When background work starts another turn, the run prints each turn's result with the default `text` output and the last turn's result with `json` output (before v2.1.295, `text` output also printed only the last turn's result). A `-p` run doesn't wait for MCP work in the background: an MCP task on a remote server goes on (resume that session to follow it), and the result of an MCP call that automatic backgrounding moved is lost. [EXT:https://code.claude.com/docs/en/headless]
- `--mcp-config` with `-p` waits (v2.1.221+) for still-pending servers before the first turn, up to `MCP_TIMEOUT` (30 s by default; a shorter wait applies in a self-hosted environment). A remote server with a cached tool list skips the wait, shows `pending` in `system/init` and connects on its first tool call. Invalid entries are skipped (the run continues and exits cleanly) and listed in `mcp_server_errors`, a key omitted when empty, so a CI gate can fail on a non-empty array. [EXT:https://code.claude.com/docs/en/headless]
- Usage and rate limits, API retries and workflow concurrency for `-p` runs: [Limits and caching](limits-and-caching.md).

## Output formats

`--output-format text|json|stream-json`: `json` returns `result`, `session_id` and metadata such as usage, plus `total_cost_usd` and a per-model cost breakdown (both client-side estimates that can differ from the bill); `stream-json` emits newline-delimited events ending in a result message; `--json-schema` fills `structured_output`, which is absent when the run ends without valid structured output, so check for the field; token streaming needs `stream-json --verbose --include-partial-messages`; subagent messages carry `parent_tool_use_id`; `system/init` and `system/api_retry` events report session metadata and retries. [EXT:https://code.claude.com/docs/en/headless] Costs on `--continue`/`--resume` cover the whole conversation. [EXT:https://code.claude.com/docs/en/headless] Result, usage and cost fields in full: [Sessions and results](sessions-and-results.md).

## Permissions in unattended runs

- `-p` starts in Manual/default when nothing sets a mode (v2.1.302+), and a call that needs approval is denied unless something approves it, such as a `PermissionRequest` hook or `--permission-prompt-tool`. Pass the mode explicitly: `auto` (classifier), `dontAsk` (deny anything that would prompt, though an installed mod can still approve some calls), `acceptEdits`. [EXT:https://code.claude.com/docs/en/headless] [EXT:https://code.claude.com/docs/en/permission-modes]
- `--permission-prompts none` (v2.1.259+) denies prompts unless a `PermissionRequest` hook allows them, removes tools needing a human (e.g. `AskUserQuestion`) and cancels any MCP elicitation request that no `Elicitation` hook answers; with `--output-format stream-json`, denials appear as `permission_denied` system messages and the final result message lists them in `permission_denials`. [EXT:https://code.claude.com/docs/en/headless]
- `--allowedTools` pre-approves tools, apart from reads from network paths; `Bash(git diff *)` matches `git diff` with or without arguments, and the space before `*` matters (`Bash(git diff*)` would also match `git diff-index`); in a run that starts in auto mode a bare `Bash` entry is dropped as a broad allow rule. [EXT:https://code.claude.com/docs/en/headless] How Bash rules match: [Permission rules](goal-and-permissions.md#permission-rules).
- In a folder never trusted, `-p` doesn't use the project's `.claude/settings.json` `permissions.allow` rules or `additionalDirectories` (it warns on stderr), while workspace trust never gates a skill's `allowed-tools`. [EXT:https://code.claude.com/docs/en/permissions]

## Sessions

`--continue` (most recent in the current directory; plain `--continue` skips `-p` and SDK sessions and sessions whose first prompt was `/loop`, `-p --continue` includes them; from v2.1.257 it opens a finished background session but not one still running), `--resume <id|name|transcript path>` (a session ID is found in any project on this machine; before v2.1.223 the ID search covered only the current project directory and its git worktrees), `--session-id <uuid>`, `--fork-session`, `--name`, `--no-session-persistence`; capture `session_id` from JSON output. [EXT:https://code.claude.com/docs/en/headless] [EXT:https://code.claude.com/docs/en/cli-reference] `CLAUDE_CODE_RESUME_INTERRUPTED_TURN=1` continues an interrupted turn on resume. [EXT:https://code.claude.com/docs/en/headless] Full detail: [Sessions and results](sessions-and-results.md).

## CLI commands

| Command | Purpose |
|---------|---------|
| `claude -p "query"` | Query and exit [EXT:https://code.claude.com/docs/en/cli-reference] |
| `claude -c`, `claude -c -p "query"`, `claude -r "<session>" "query"` | Continue / resume [EXT:https://code.claude.com/docs/en/cli-reference] |
| `claude update`, `claude install [version]` | Update / reinstall [EXT:https://code.claude.com/docs/en/cli-reference] |
| `claude auth login --console`, `claude auth status` | Auth (status exits 0 when logged in) [EXT:https://code.claude.com/docs/en/cli-reference] |
| `claude agents --json` | Active sessions as a JSON array for scripting: every live session, plus background sessions still working or blocked; `--json --all` also includes completed background sessions, `--cwd <path>` limits the list to sessions started under that directory; see [Worktrees and background sessions](worktrees-and-background.md) [EXT:https://code.claude.com/docs/en/cli-reference] [EXT:https://code.claude.com/docs/en/agent-view] |
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
| `--append-system-prompt[-file]`, `--system-prompt[-file]`, `--append-subagent-system-prompt[-file]` | Prompt control: an append flag combines with a replace flag, and from v2.1.283 a system-prompt flag and its own `-file` form are both used; the subagent pair applies only with `-p`, and `--append-subagent-system-prompt` can't be combined with its `-file` form [EXT:https://code.claude.com/docs/en/cli-reference] |
| `--bare` | Minimal mode (sets `CLAUDE_CODE_SIMPLE`) [EXT:https://code.claude.com/docs/en/headless] [EXT:https://code.claude.com/docs/en/cli-reference] |
| `--bg` | Background agent (not with `-p`); see [Worktrees and background sessions](worktrees-and-background.md) [EXT:https://code.claude.com/docs/en/cli-reference] |
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
| `--worktree` / `-w` | Isolated git worktree under `.claude/worktrees/`; see [Worktrees and background sessions](worktrees-and-background.md) [EXT:https://code.claude.com/docs/en/cli-reference] |
