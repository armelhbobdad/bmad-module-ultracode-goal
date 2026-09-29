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

   tea-testarch lists the modes `--pre` (default), `--post` and `--stop` (L44) but shows only the Stop command. That PreToolUse runs `--pre` and PostToolUse runs `--post` is inferred from the default and the event names.

   cc-primitives documents the host side. `.claude/settings.json` is a committable project hook location whose entries merge with the other settings levels, and a settings file has one `hooks` object to which new events are added as sibling keys (hooks.md L25, L30, L20). A matcher made only of letters, digits, `_`, `-`, spaces, commas and pipes is an exact string or list matched against `tool_name`, and a matcher on `Stop` is silently ignored (hooks.md L60-L61). PreToolUse and PostToolUse fire on every tool call except `EndConversation` (hooks.md L56). cc-primitives has no tool-name catalogue (it names only `Bash` and `EndConversation`), so it cannot confirm `MultiEdit`.

3. How it blocks. The script blocks patterns such as `.only`, `waitForTimeout` and `Thread.sleep` by exiting 2, with stderr sent to the agent (tea-testarch L44; SKILL.md L87). cc-primitives defines exit 2 as a blocking error whose stderr becomes the block message (hooks.md L81; SKILL.md L104). On `PreToolUse`, exit 2 equals deny, and a deny holds even in bypass mode (hooks.md L90; SKILL.md L46, L64). On `Stop`, exit 2 prevents stopping and routes stderr as the reason, so Claude keeps working (hooks.md L106; SKILL.md L48).

4. Where the two contracts diverge.
   - In cc-primitives' Events list only `PreToolUse` is annotated "can block" ("before the call"). Stop blocking is documented separately (hooks.md L56, L106). There is no PostToolUse control section and no PostToolUse-specific input field (hooks.md L76).
   - What a `--post` exit 2 does is therefore not documented at constituent level. By the event's name it runs after the tool, so it cannot be relied on to stop the write. That narrows TEA's "the hook blocks writes with exit 2" (SKILL.md L87) to the `--pre` path. This is an inference, not a documented fact.
   - A `Stop` exit 2 re-prompts the agent. cc-primitives says to check `stop_hook_active` to avoid infinite loops, and says Claude Code ends the turn anyway after 8 consecutive blocks (hooks.md L106; SKILL.md L48).
   - Stop hooks fire whenever Claude finishes responding, so `--stop` runs at every turn end (hooks.md L106). tea-testarch does not say whether `--stop` checks `stop_hook_active`.

5. When enforcement silently disappears. TEA fails open: a malformed payload, an unreadable config or an internal error all give exit 0 (tea-testarch L45), which cc-primitives treats as success (hooks.md L80).
   - Failures of the handler itself are non-blocking errors: a missing or non-executable script, or any exit code other than 0 or 2 (hooks.md L82). A timed-out PreToolUse hook does not block (hooks.md L68).
   - TEA's fail-open choice departs from cc-primitives' advice that policy hooks should exit 2 (hooks.md L82).
   - Headless runs: `claude -p --bare` skips auto-discovery of hooks, so TEA's project hooks do not load. `-p` without `--bare` runs the project's `.claude/settings.json` hooks even in an untrusted folder (headless-and-cli.md L16-L17).

## Key Files

Upstream source files behind the cited lines (from the constituents' `[SRC:…]` tags):

- `src/workflows/testarch/bmad-testarch-framework/steps-c/step-04-docs-and-scripts.md`
- `src/workflows/testarch/bmad-testarch-framework/resources/hooks/tea-enforce.cjs`
- `src/workflows/testarch/bmad-testarch-framework/workflow.yaml`
- `src/workflows/testarch/bmad-testarch-framework/steps-c/step-03-scaffold-framework.md`

## Usage Convention

Add your own Claude Code hooks as sibling entries in the existing `hooks` object and keep TEA's three entries. Rely only on tea-enforce's `PreToolUse` exit 2 to stop a bad write; its `PostToolUse` exit 2 presumably arrives after the tool has run (inferred; neither skill documents PostToolUse control). Treat its `Stop` exit 2 as a re-prompt bounded by the 8-block cap (tea-testarch does not say whether `--stop` checks `stop_hook_active`). `claude -p --bare` skips auto-discovery of hooks, so TEA's enforcement does not load in bare headless runs.

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
- [from skill: cc-primitives] `references/hooks.md` — ## PreToolUse control, L90: "Exit 2 equals deny."
- [from skill: cc-primitives] `references/hooks.md` — ## Events, L56: "PreToolUse/PostToolUse fire on every tool call except `EndConversation`."
- [from skill: cc-primitives] `references/hooks.md` — ## Stop and SubagentStop control, L106: "Top-level `decision: "block"` with a required `reason` prevents stopping"
- [from skill: cc-primitives] `references/hooks.md` — ## Stop and SubagentStop control, L106: "Stop hooks fire whenever Claude finishes responding, not only at task completion."
- [from skill: cc-primitives] `references/hooks.md` — ## Exit codes, L80: "`0`: success; stdout JSON is parsed; exit-0 stderr goes only to the debug log; silence is not approval."
- [from skill: cc-primitives] `references/hooks.md` — ## Exit codes, L82: "Other codes: non-blocking error for most events (exit 1 without JSON included)"
- [from skill: cc-primitives] `references/hooks.md` — ## Handlers, L68: "a timed-out hook is canceled and a timed-out PreToolUse hook does not block"
- [from skill: cc-primitives] `references/hooks.md` — ## Security, trust and headless, L114: "`-p`/SDK sessions treat the folder as trusted and run committed project hooks without a dialog."
- [from skill: cc-primitives] `SKILL.md` — ## Common Workflows, L46: "or exits 2 with the reason on stderr. A deny holds even in `bypassPermissions`."
- [from skill: cc-primitives] `SKILL.md` — ## Common Workflows, L48: "**Keep Claude working until checks pass (Stop):** return `{"decision":"block","reason":…}` or exit 2."
- [from skill: cc-primitives] `SKILL.md` — ## Common Workflows, L48: "after 8 consecutive blocks Claude Code ends the turn anyway (`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` raises the cap)"
- [from skill: cc-primitives] `SKILL.md` — ## Quick Start, L31: "A `Stop` hook blocks the stop with a top-level decision:"
- [from skill: cc-primitives] `SKILL.md` — ## Key API Summary, L63: "`hooks` key in `~/.claude/settings.json`, `.claude/settings.json`, `.claude/settings.local.json`, skill/agent frontmatter"
- [from skill: cc-primitives] `SKILL.md` — ## Key Types, L104: "`2` = blocking error (stderr becomes the reason, and JSON `allow` cannot override it); other codes = non-blocking error."
- [from skill: cc-primitives] `SKILL.md` — (YAML frontmatter description), L6: "Use when wiring a BMAD module into Claude Code"
- [from skill: cc-primitives] `references/goal-and-permissions.md` — ## /goal, L18: "Implemented as a session-scoped prompt-based Stop hook using the small fast model"
- [from skill: cc-primitives] `context-snippet.md` — (no markdown heading; the snippet's |gotchas: line), L6: "Stop hooks need stop_hook_active checks (8-block cap)"
- [from skill: cc-primitives] `references/hooks.md` — ## Configuration, L25: "`.claude/settings.json` | One project, committable"
- [from skill: cc-primitives] `references/hooks.md` — ## Configuration, L30: "Entries merge across levels; identical handlers in several files run once; settings/policy/plugin hooks also fire inside subagents."
- [from skill: cc-primitives] `references/hooks.md` — ## Events, L56: "`PreToolUse` (after parameters are created, before the call; can block), `PostToolUse`, `SubagentStop`, `Stop` (main agent finished responding; not on user interrupt)"
- [from skill: cc-primitives] `references/hooks.md` — ## Matchers and the if filter, L60: "only letters, digits, `_`, `-`, spaces, commas and pipes → exact string or list; anything else → unanchored JavaScript regex; case-sensitive."
- [from skill: cc-primitives] `references/hooks.md` — ## Matchers and the if filter, L61: "Tool events match against `tool_name`; `Stop`, `UserPromptSubmit` and similar events have no matcher support (a matcher there is silently ignored)."
- [from skill: cc-primitives] `references/hooks.md` — ## Handlers, L71: "`CLAUDE_PROJECT_DIR` (session start root, even inside a worktree)"
- [from skill: cc-primitives] `references/hooks.md` — ## Handlers, L72: "Scripts must be executable; use absolute paths such as `${CLAUDE_PROJECT_DIR}`."
- [from skill: cc-primitives] `references/hooks.md` — ## Handlers, L70: "All matching hooks run in parallel, in the current directory with Claude Code's environment (minus `OTEL_*` exporters)."
- [from skill: cc-primitives] `references/hooks.md` — ## Input, L76: "PreToolUse adds `tool_name`, `tool_input`, `tool_use_id` (Bash: `tool_input.command`)."
- [from skill: cc-primitives] `references/hooks.md` — ## Exit codes, L81: "`2`: blocking error; stderr (or the JSON reason) becomes the block message; JSON `allow` cannot override it; some events (e.g. SessionStart) cannot be blocked."
- [from skill: cc-primitives] `references/hooks.md` — ## Exit codes, L82: "a missing or non-executable script also fails silently as non-blocking — policy hooks should exit 2."
- [from skill: cc-primitives] `references/hooks.md` — ## PreToolUse control, L90: "PreToolUse fires before permission-mode checks, so a deny holds even in bypass; hooks tighten but cannot loosen restrictions."
- [from skill: cc-primitives] `references/hooks.md` — ## Stop and SubagentStop control, L106: "omit `decision` to allow; exit 2 routes stderr as the reason."
- [from skill: cc-primitives] `references/hooks.md` — ## Stop and SubagentStop control, L106: "Check `stop_hook_active` to avoid infinite loops; after eight consecutive continuations Claude Code overrides the block (`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` raises it)."
- [from skill: cc-primitives] `references/hooks.md` — ## Security, trust and headless, L114: "Command hooks run with your full user permissions; quote shell variables."
- [from skill: cc-primitives] `references/headless-and-cli.md` — ## claude -p behaviour, L16: "`-p` without `--bare` runs the project's `.claude/settings.json` hooks and `.mcp.json` servers even in an untrusted folder."
- [from skill: cc-primitives] `references/headless-and-cli.md` — ## claude -p behaviour, L17: "`--bare` skips auto-discovery of hooks, skills, commands, subagents, plugins, MCP, auto memory and CLAUDE.md"
- [from skill: cc-primitives] `SKILL.md` — ## Key API Summary, L64: "`permissionDecision` allow/deny/ask/defer; exit 2 = deny"
- [from skill: cc-primitives] `SKILL.md` — ## Key Types, L100: "**Hook events used by orchestrators:** `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `SubagentStop`, `Stop`, `StopFailure`."
- [from skill: cc-primitives] `SKILL.md` — (YAML frontmatter description), L5: "PreToolUse and Stop hooks in settings.local.json"
- [from skill: cc-primitives] `references/headless-and-cli.md` — ## claude -p behaviour, L17: "`--bare` skips auto-discovery of hooks"
