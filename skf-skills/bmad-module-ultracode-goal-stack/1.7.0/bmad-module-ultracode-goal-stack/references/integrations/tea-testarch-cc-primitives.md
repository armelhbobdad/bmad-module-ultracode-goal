# tea-testarch + cc-primitives Integration

**Type:** Event Handler
**Co-import files:** 0 (compose-mode; no codebase — the contract is documented in a constituent skill)
**Detection:** constituent-documented-contract (`detection_method: constituent_documented_contract`) — documented by tea-testarch (Gotchas; `references/pattern-framework-and-ci.md`)
**Confidence:** T3 (constituent-documented-contract) [composed] — weaker of tea-testarch (T1-low) and cc-primitives (T3)

## Integration Pattern

1. Where to install. TEA's bmad-testarch-framework workflow installs tea-enforce.cjs when the platform supports tool hooks, naming Claude Code (via `.claude/settings.json`). It skips Cursor, Windsurf and Codex, where test-review stays the enforcement path (tea-testarch pattern-framework-and-ci.md L41). It copies the script byte-for-byte to `.claude/hooks/tea-enforce.cjs` and writes `.tea/enforce-config.json`, which holds the stack's globs and `hookSha256` (L42).

2. What it registers. It merges three entries into the project's existing `.claude/settings.json` and never overwrites the file (tea-testarch L43; SKILL.md L87):
   - `PreToolUse` with matcher `Write|Edit|MultiEdit`
   - `PostToolUse` with matcher `Write|Edit|MultiEdit|Bash`
   - `Stop`, which runs tea-enforce.cjs with `--stop` (the skill renders the command as `node $CLAUDE_PROJECT_DIR/.claude/hooks/tea-enforce.cjs --stop`; quote the path)

   tea-testarch lists the modes `--pre` (default), `--post` and `--stop` (L44) but shows only the Stop command. That PreToolUse runs `--pre` and PostToolUse runs `--post` is inferred from the default and the event names; the pinned step-04 (v1.27.2, section 3.3) confirms both and writes all three commands with the script path double-quoted, as `node "$CLAUDE_PROJECT_DIR/.claude/hooks/tea-enforce.cjs" --stop`.

   cc-primitives documents the host side. `.claude/settings.json` is a committable project hook location whose entries merge with the other settings levels, and a settings file has one `hooks` object to which new events are added as sibling keys (hooks.md L25, L30, L20). A matcher made only of letters, digits, `_`, `-`, spaces, commas and pipes is an exact string or list matched against `tool_name`, and a matcher on `Stop` is silently ignored (hooks.md L60-L61). PreToolUse fires on every tool call except `EndConversation` (hooks.md L56). PostToolUse fires only after a tool call succeeds, and a failed call fires `PostToolUseFailure` instead (the Claude Code hooks page that hooks.md cites; hooks.md L56 words both as every tool call), so `--post` does not run on a failed write. cc-primitives has no tool-name catalogue. Apart from `Bash` and `EndConversation` it names only `Agent`, `AskUserQuestion`, `EnterPlanMode`, `ExitPlanMode`, `ScheduleWakeup`, `WaitForMcpServers`, `Workflow`, `SendMessage`, `Skill` and `Monitor` (subagents-and-workflows.md L18, L25, L28, L41; skills-and-plugins.md L47; headless-and-cli.md L18, L28). It never names `Write`, `Edit` or `MultiEdit`, so it cannot confirm TEA's matcher tool names.

3. How it blocks. The script blocks patterns such as `.only`, `waitForTimeout` and `Thread.sleep` by exiting 2, with stderr sent to the agent (tea-testarch L44; SKILL.md L87). cc-primitives defines exit 2 as a blocking error whose stderr becomes the block message (hooks.md L83; SKILL.md L91). On `PreToolUse`, exit 2 equals deny, and a deny holds even in bypass mode (hooks.md L92; SKILL.md L46, L65). On `Stop`, exit 2 prevents stopping and routes stderr as the reason, so Claude keeps working (hooks.md L108; SKILL.md L48).

4. Where the two contracts diverge.
   - In cc-primitives' Events list only `PreToolUse` is annotated "can block" ("before the call"). Stop blocking is documented separately (hooks.md L56, L108). There is no PostToolUse control section and no PostToolUse-specific input field (hooks.md L78).
   - What a `--post` exit 2 does is therefore not documented at constituent level. By the event's name it runs after the tool, so it cannot be relied on to stop the write. That narrows TEA's "the hook blocks writes with exit 2" (SKILL.md L87) to the `--pre` path. This is an inference, not a documented fact.
   - A `Stop` exit 2 re-prompts the agent. cc-primitives says to check `stop_hook_active` to avoid infinite loops, and says Claude Code ends the turn anyway after 8 consecutive blocks (hooks.md L108; SKILL.md L48).
   - Stop hooks fire whenever Claude finishes responding, not only at task completion (hooks.md L108). They do not fire on a user interrupt, and a turn ended by an API error fires `StopFailure` instead (hooks.md L56). So `--stop` runs each time the main agent finishes responding normally. tea-testarch does not say whether `--stop` checks `stop_hook_active`, but the pinned source does: tea-enforce.cjs returns 0 before its sweep when `payload.stop_hook_active === true` (tea-enforce.cjs L1043-L1044 at v1.27.2).

5. When enforcement silently disappears. TEA fails open: a malformed payload, an unreadable config or an internal error all give exit 0 (tea-testarch L45), which cc-primitives treats as success (hooks.md L82).
   - Failures of the handler itself are non-blocking errors: a missing or non-executable script, or any exit code other than 0 or 2 with plain-text, empty or invalid-JSON stdout (hooks.md L84). `onFailure: "block"` (v2.1.295+) would make such a failure, or a timeout, do what exit 2 does on that event, but it has no effect on `Stop`, so it could reach only TEA's `PreToolUse` and `PostToolUse` entries (hooks.md L71). A timed-out PreToolUse hook does not block unless `onFailure` is `"block"` (hooks.md L69). The Claude Code hooks page that hooks.md cites adds one exception: on Windows without Git Bash, a shell-form `PreToolUse` command hook (TEA's commands are strings with no `args`) that fails or times out with `onFailure` unset can block the call.
   - TEA blocks violations with exit 2 (tea-testarch pattern-framework-and-ci.md L44), the blocking error cc-primitives documents (hooks.md L83). cc-primitives adds that a policy hook needs `onFailure: "block"` to block when it can't run (hooks.md L84; never for a `Stop` hook, L71); neither skill says TEA sets it, and the pinned v1.27.2 step-04 (section 3.3) registers none. Its fail-open path is a separate, deliberate choice that `onFailure` does not reach: on its own failures it exits 0, so Claude Code lets the call through, as it does for a hook that cannot start outside the Windows case above (hooks.md L82, L84) (inferred).
   - Headless runs: `claude -p --bare` skips auto-discovery of hooks, so TEA's project hooks do not load. `-p` without `--bare` runs the project's `.claude/settings.json` hooks even in an untrusted folder (headless-and-cli.md L16-L17).

## Key Files

Upstream source files behind the cited lines (from the constituents' `[SRC:…]` tags):

- `src/workflows/testarch/bmad-testarch-framework/steps-c/step-04-docs-and-scripts.md`
- `src/workflows/testarch/bmad-testarch-framework/resources/hooks/tea-enforce.cjs`
- `src/workflows/testarch/bmad-testarch-framework/workflow.yaml`
- `src/workflows/testarch/bmad-testarch-framework/steps-c/step-03-scaffold-framework.md`

## Usage Convention

Add your own Claude Code hooks as sibling entries in the existing `hooks` object and keep TEA's three entries. Rely only on tea-enforce's `PreToolUse` exit 2 to stop a bad write; its `PostToolUse` exit 2 presumably arrives after the tool has run (inferred; neither skill documents PostToolUse control). Treat its `Stop` exit 2 as a single re-prompt. tea-testarch does not say whether `--stop` checks `stop_hook_active`, but the pinned tea-enforce.cjs returns 0 without sweeping whenever `stop_hook_active` is true (L1043-L1044 at v1.27.2). So `--stop` never blocks twice in a row and never reaches the 8-block cap by itself. On a stop that follows any stop-hook continuation, including one from `/goal`'s prompt-based Stop hook, TEA skips its sweep (inferred). `claude -p --bare` skips auto-discovery of hooks, so TEA's enforcement does not load in bare headless runs.

## Evidence

Verbatim citations from the constituent skills (file relative to the skill root, nearest heading, line):

- [from skill: tea-testarch] `SKILL.md` — ## Gotchas, L87: "**Framework edits `.claude/settings.json`.** On Claude Code it merges `PreToolUse`, `PostToolUse` and `Stop` entries for `.claude/hooks/tea-enforce.cjs` into the existing file, and the hook blocks writes with exit 2."
- [from skill: tea-testarch] `references/pattern-framework-and-ci.md` — ## tea-enforce.cjs write-time hook, L41: "Installed when the platform supports tool hooks (Claude Code via `.claude/settings.json`); skipped on Cursor, Windsurf and Codex, where test-review remains the enforcement path."
- [from skill: tea-testarch] `references/pattern-framework-and-ci.md` — ## tea-enforce.cjs write-time hook, L42: "Copied byte-for-byte to `.claude/hooks/tea-enforce.cjs`; `.tea/enforce-config.json` holds the stack's globs and `hookSha256`."
- [from skill: tea-testarch] `references/pattern-framework-and-ci.md` — ## tea-enforce.cjs write-time hook, L43: "Registration is merged into an existing `.claude/settings.json`, never overwriting it: `PreToolUse` matcher `Write|Edit|MultiEdit`, `PostToolUse` matcher `Write|Edit|MultiEdit|Bash`, `Stop` runs `node $CLAUDE_PROJECT_DIR/.claude/hooks/tea-enforce.cjs --stop`."
- [from skill: tea-testarch] `references/pattern-framework-and-ci.md` — ## tea-enforce.cjs write-time hook, L44: "Blocks patterns such as `.only`, `waitForTimeout`, `Thread.sleep` (exit 2, stderr to the agent); modes `--pre` (default), `--post`, `--stop`."
- [from skill: tea-testarch] `references/pattern-framework-and-ci.md` — ## tea-enforce.cjs write-time hook, L45: "Fails open (malformed payload, unreadable config, internal error → exit 0); an invalid config disables enforcement for that call; with no config a broad default applies."
- [from skill: tea-testarch] `SKILL.md` — ## Pattern Surface, L56: "`{test_dir}/README.md`, framework config, `tea-enforce.cjs` hook"
- [from skill: tea-testarch] `context-snippet.md` — (no markdown heading; the snippet's |gotchas: line), L6: "framework merges tea-enforce.cjs hooks into .claude/settings.json"
- [from skill: cc-primitives] `references/hooks.md` — ## Configuration, L20: "A settings file has one `hooks` object; add new events as sibling keys inside it."
- [from skill: cc-primitives] `references/hooks.md` — ## PreToolUse control, L92: "Exit 2 equals deny."
- [from skill: cc-primitives] `references/hooks.md` — ## Events, L56: "PreToolUse/PostToolUse fire on every tool call except `EndConversation`."
- [from skill: cc-primitives] `references/hooks.md` — ## Stop and SubagentStop control, L108: "Top-level `decision: "block"` with a required `reason` prevents stopping"
- [from skill: cc-primitives] `references/hooks.md` — ## Stop and SubagentStop control, L108: "Stop hooks fire whenever Claude finishes responding, not only at task completion."
- [from skill: cc-primitives] `references/hooks.md` — ## Exit codes, L82: "`0`: success; stdout JSON is parsed; Claude never sees exit-0 stderr (debug logging shows it); silence is not approval."
- [from skill: cc-primitives] `references/hooks.md` — ## Exit codes, L84: "Other codes: non-blocking error for most events when stdout is plain text, empty or invalid JSON (exit 1 without JSON included)"
- [from skill: cc-primitives] `references/hooks.md` — ## Handlers, L69: "a timed-out hook is canceled and a timed-out PreToolUse hook does not block unless `onFailure` is `"block"`"
- [from skill: cc-primitives] `references/hooks.md` — ## Handlers, L71: "`onFailure: "block"` on a `command` or `http` hook (v2.1.295+) makes a failure (can't start, exit code other than 0 or 2, HTTP error, timeout, invalid JSON) do what exit 2 does on that event, and deny on `PermissionRequest`; it has no effect on `Stop`, `SubagentStop`, `TaskCompleted`, `TeammateIdle` or async hooks."
- [from skill: cc-primitives] `references/hooks.md` — ## Security, trust and headless, L116: "`-p`/SDK sessions never show the dialog and treat the folder as trusted, so hooks committed in the repository's `.claude/settings.json`, and a project skill's frontmatter hooks, run without a dialog."
- [from skill: cc-primitives] `SKILL.md` — ## Common Workflows, L46: "or exits 2 with the reason on stderr; `"onFailure": "block"` (v2.1.295+) also blocks when the script can't run. A deny holds even in `bypassPermissions`."
- [from skill: cc-primitives] `SKILL.md` — ## Common Workflows, L48: "**Keep Claude working until checks pass (Stop):** return `{"decision":"block","reason":…}` or exit 2."
- [from skill: cc-primitives] `SKILL.md` — ## Common Workflows, L48: "after 8 consecutive blocks Claude Code ends the turn anyway (`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` raises the cap)"
- [from skill: cc-primitives] `SKILL.md` — ## Quick Start, L31: "A `Stop` hook blocks the stop with a top-level decision:"
- [from skill: cc-primitives] `SKILL.md` — ## Key API Summary, L64: "`hooks` key in `~/.claude/settings.json`, `.claude/settings.json`, `.claude/settings.local.json`, skill/agent frontmatter"
- [from skill: cc-primitives] `SKILL.md` — ## Key Types, L91: "`2` = blocking error on events that can block (stderr becomes the reason unless the printed JSON makes a blocking decision with its own reason; JSON `allow` cannot override it)"
- [from skill: cc-primitives] `SKILL.md` — (YAML frontmatter description), L6-L7: "Use when wiring a BMAD module into Claude Code"
- [from skill: cc-primitives] `references/goal-and-permissions.md` — ## /goal, L19: "Implemented as a session-scoped prompt-based Stop hook using the configured small fast model"
- [from skill: cc-primitives] `context-snippet.md` — (no markdown heading; the snippet's |gotchas: line), L6: "Stop hooks need stop_hook_active checks (8-block cap)"
- [from skill: cc-primitives] `references/hooks.md` — ## Configuration, L25: "`.claude/settings.json` | One project, committable"
- [from skill: cc-primitives] `references/hooks.md` — ## Configuration, L30: "Entries merge across levels; identical handlers in several files run once; settings/policy/plugin hooks also fire inside subagents."
- [from skill: cc-primitives] `references/hooks.md` — ## Events, L56: "`PreToolUse` (after parameters are created, before the call; can block), `PostToolUse`, `SubagentStop`, `Stop` (main agent finished responding; not on user interrupt)"
- [from skill: cc-primitives] `references/hooks.md` — ## Matchers and the if filter, L60: "only letters, digits, `_`, `-`, spaces, commas and pipes → exact string or list; anything else → unanchored JavaScript regex; case-sensitive."
- [from skill: cc-primitives] `references/hooks.md` — ## Matchers and the if filter, L61: "Tool events match against `tool_name`; `Stop`, `UserPromptSubmit` and similar events have no matcher support (a matcher there is silently ignored)."
- [from skill: cc-primitives] `references/hooks.md` — ## Handlers, L73: "`CLAUDE_PROJECT_DIR` (session start root, even inside a worktree)"
- [from skill: cc-primitives] `references/hooks.md` — ## Handlers, L74: "Scripts must be executable; use absolute paths such as `${CLAUDE_PROJECT_DIR}`."
- [from skill: cc-primitives] `references/hooks.md` — ## Handlers, L72: "All matching hooks run in parallel (at most 12 prompt or agent hooks at once), in the current directory with Claude Code's environment (minus `OTEL_*` exporters)."
- [from skill: cc-primitives] `references/hooks.md` — ## Input, L78: "PreToolUse adds `tool_name`, `tool_input`, `tool_use_id` (Bash: `tool_input.command`)."
- [from skill: cc-primitives] `references/hooks.md` — ## Exit codes, L83: "`2`: blocking error; stderr (or the JSON reason) becomes the block message; JSON `allow` cannot override it; some events (e.g. SessionStart) cannot be blocked."
- [from skill: cc-primitives] `references/hooks.md` — ## Exit codes, L84: "a missing or non-executable script is a non-blocking error too, so a policy hook needs `onFailure: "block"` to block when it can't run."
- [from skill: cc-primitives] `references/hooks.md` — ## PreToolUse control, L92: "PreToolUse fires before any permission-mode check, so a hook's deny holds in every mode, bypassPermissions and `dontAsk` included."
- [from skill: cc-primitives] `references/hooks.md` — ## Stop and SubagentStop control, L108: "omit `decision` to allow; exit 2 routes stderr as the reason."
- [from skill: cc-primitives] `references/hooks.md` — ## Stop and SubagentStop control, L108: "Check `stop_hook_active` to avoid infinite loops; after eight consecutive continuations Claude Code overrides the block (`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` raises it); the count resets each time Claude calls a tool."
- [from skill: cc-primitives] `references/hooks.md` — ## Security, trust and headless, L116: "Command hooks run with your full user permissions; quote shell variables."
- [from skill: cc-primitives] `references/headless-and-cli.md` — ## claude -p behaviour, L16: "`-p` without `--bare` runs the project's `.claude/settings.json` hooks and `.mcp.json` servers even in an untrusted folder."
- [from skill: cc-primitives] `references/headless-and-cli.md` — ## claude -p behaviour, L17: "`--bare` skips auto-discovery of hooks, skills, commands, subagents, plugins, MCP, auto memory and CLAUDE.md"
- [from skill: cc-primitives] `SKILL.md` — ## Key API Summary, L65: "`permissionDecision` allow/deny/ask/defer; exit 2 = deny"
- [from skill: cc-primitives] `SKILL.md` — ## Key Types, L87: "**Hook events used by orchestrators:** `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `SubagentStop`, `Stop`, `StopFailure`."
- [from skill: cc-primitives] `SKILL.md` — (YAML frontmatter description), L5: "PreToolUse and Stop hooks in settings.local.json"
- [from skill: cc-primitives] `references/headless-and-cli.md` — ## claude -p behaviour, L17: "`--bare` skips auto-discovery of hooks"
- [from skill: cc-primitives] `references/hooks.md` — ## Events, L56: "`StopFailure` (turn ended by an API error)"
- [from skill: cc-primitives] `references/subagents-and-workflows.md` — ## Subagent definitions, L18: "Every non-fork subagent loses `AskUserQuestion`, `EndConversation`, `EnterPlanMode`, `ScheduleWakeup`, `WaitForMcpServers` and `Workflow` even when they are listed in `tools`. It also loses `Agent` at the depth limit and `ExitPlanMode` unless `permissionMode` is `plan`."
- [from skill: cc-primitives] `references/subagents-and-workflows.md` — ## Delegation and execution, L25: "Resume with SendMessage by agent ID or name"
- [from skill: cc-primitives] `references/subagents-and-workflows.md` — ## Delegation and execution, L28: "Disable one with `permissions.deny` `Agent(subagent-name)`"
- [from skill: cc-primitives] `references/subagents-and-workflows.md` — ## Dynamic workflows, L41: "allow rule `Workflow` or `Workflow(<name>)`"
- [from skill: cc-primitives] `references/skills-and-plugins.md` — ## Invocation and substitutions, L47: "Permission rules: `Skill(name)` exact, `Skill(name *)` prefix."
- [from skill: cc-primitives] `references/headless-and-cli.md` — ## Permissions in unattended runs, L28: "removes tools needing a human (e.g. AskUserQuestion)"
- [from skill: cc-primitives] `references/headless-and-cli.md` — ## claude -p behaviour, L18: "For Monitor watches, it waits until the watch times out"
