# /goal, permission modes and Auto Mode

## Contents

- [/goal](#goal)
- [Permission modes](#permission-modes)
- [Auto Mode configuration](#auto-mode-configuration)

## /goal

- Sets a completion condition; after every turn a small fast model checks it and starts another turn until it holds — the evaluator is a fresh model, not the worker. [EXT:https://code.claude.com/docs/en/goal]
- Session-scoped; one goal per session; a new `/goal <condition>` replaces the active one; `/goal` alone shows status; `/goal clear` (aliases `stop`, `off`, `reset`, `none`, `cancel`) removes it; `/clear` also removes it. [EXT:https://code.claude.com/docs/en/goal]
- Setting a goal starts a turn immediately with the condition as directive. [EXT:https://code.claude.com/docs/en/goal]
- The evaluator does not run commands or read files, so the condition must be demonstrable from Claude's own output. [EXT:https://code.claude.com/docs/en/goal]
- Conditions are capped at 4,000 characters; bound runtime with a clause such as "or stop after 20 turns". [EXT:https://code.claude.com/docs/en/goal]
- Resume (`--continue`, `--resume`) restores an active goal; the turn count, timer and token baseline reset. [EXT:https://code.claude.com/docs/en/goal]
- `claude -p "/goal …"` runs the loop to completion in one invocation; add `--output-format stream-json --verbose` to see progress. [EXT:https://code.claude.com/docs/en/goal]
- Implemented as a session-scoped prompt-based Stop hook using the small fast model (Haiku by default; `ANTHROPIC_DEFAULT_HAIKU_MODEL` changes it). [EXT:https://code.claude.com/docs/en/goal] [EXT:https://code.claude.com/docs/en/hooks]
- Verdicts: *Not yet met* (keep working, reason as guidance), *Met* (goal cleared, achieved entry), *Impossible* (cleared, failed entry). [EXT:https://code.claude.com/docs/en/goal]
- The loop stops with the goal still set if Claude answers the evaluator without tool use several turns in a row; unrecoverable errors clear the goal; transient failures retry three times then pause; `CLAUDE_CODE_GOAL_CHECKIN_MINUTES=0` turns retries and check-ins off. [EXT:https://code.claude.com/docs/en/goal]
- Evaluation is skipped while a subagent or background shell is still running; check-ins after 30 minutes of waiting, at most three idle check-ins between prompts. [EXT:https://code.claude.com/docs/en/goal]
- Unavailable when `disableAllHooks` is true or `allowManagedHooksOnly` is set in managed settings. [EXT:https://code.claude.com/docs/en/goal]
- Auto mode removes per-tool prompts, `/goal` removes per-turn prompts; a goal does not change the permission mode. [EXT:https://code.claude.com/docs/en/goal]

## Permission modes

| Mode | Behaviour |
|------|-----------|
| `default` / `manual` | Built-in start for `-p` and Agent SDK sessions; `manual` is an alias (v2.1.200+) [EXT:https://code.claude.com/docs/en/permission-modes] |
| `acceptEdits` | Reads, file edits and common filesystem commands without asking [EXT:https://code.claude.com/docs/en/permission-modes] [EXT:https://code.claude.com/docs/en/headless] |
| `plan` | Researches and proposes without changing; keeps its blocks in `-p` runs [EXT:https://code.claude.com/docs/en/permission-modes] |
| `auto` | Everything without asking, with background classifier checks; built-in start for interactive terminal/VS Code from v2.1.283 [EXT:https://code.claude.com/docs/en/permission-modes] |
| `dontAsk` | Pre-approved tools only; denies anything that would prompt; not in the Shift+Tab cycle [EXT:https://code.claude.com/docs/en/permission-modes] |
| `bypassPermissions` | No prompts or safety checks; isolated containers/VMs only; must be enabled at launch [EXT:https://code.claude.com/docs/en/permission-modes] |

- Starting mode comes from `--permission-mode` / `--dangerously-skip-permissions`, then `permissions.defaultMode`; `defaultMode: "auto"` has no effect in project or local settings files. [EXT:https://code.claude.com/docs/en/permission-modes] [EXT:https://code.claude.com/docs/en/settings]
- Shift+Tab cycles auto → default → acceptEdits → plan → default; `--allow-dangerously-skip-permissions` adds bypass to the cycle without activating it. [EXT:https://code.claude.com/docs/en/permission-modes]
- Deny rules block in every mode, including bypass; allow rules have no effect in bypass. [EXT:https://code.claude.com/docs/en/permission-modes]
- `--dangerously-skip-permissions` equals `--permission-mode bypassPermissions`; `permissions.disableBypassPermissionsMode: "disable"` blocks it; `permissions.disableAutoMode: "disable"` removes auto. [EXT:https://code.claude.com/docs/en/permission-modes]
- Auto mode pauses after 3 consecutive or 20 total classifier blocks; in `-p` without a prompt tool the blocked action is skipped and the run continues. [EXT:https://code.claude.com/docs/en/permission-modes]
- Auto mode blocks launching unsandboxed autonomous loops (e.g. `--dangerously-skip-permissions`) and sending keystrokes to its own tmux pane; entering auto drops broad allow rules such as `Bash(*)`. [EXT:https://code.claude.com/docs/en/permission-modes]
- In auto mode a subagent's frontmatter `permissionMode` is ignored. [EXT:https://code.claude.com/docs/en/permission-modes]
- If auto is selected but unavailable, the session starts in Manual. [EXT:https://code.claude.com/docs/en/permission-modes]

## Auto Mode configuration

- Deny and explicit ask rules are evaluated before the classifier; content-scoped `permissions.ask` forces a prompt even in auto; `permissions.deny` cannot be overridden. [EXT:https://code.claude.com/docs/en/auto-mode-config]
- The classifier trusts the working directory and the repo's remotes by default, and allows pushes to any branch of the current repo and PR creation. [EXT:https://code.claude.com/docs/en/auto-mode-config]
- `autoMode` is ignored in `.claude/settings.json` and `.claude/settings.local.json`; put it in `~/.claude/settings.json`, managed settings or `--settings`. [EXT:https://code.claude.com/docs/en/auto-mode-config]
- Fields: `environment` (usually all you need), `allow`, `soft_deny` (user intent can clear), `hard_deny` (unconditional); include `"$defaults"` to keep built-ins — an array without it replaces the built-in list. [EXT:https://code.claude.com/docs/en/auto-mode-config]
- `autoMode.classifyAllShell: true` routes every shell command through the classifier. [EXT:https://code.claude.com/docs/en/auto-mode-config]
- CLI: `claude auto-mode defaults`, `config`, `critique`, `reset`; `/auto-mode-setup` drafts `environment` entries. [EXT:https://code.claude.com/docs/en/auto-mode-config]
- Denials land in `/permissions` → Recently denied; a `PermissionDenied` hook receives the denied `tool_input`; a `PreToolUse` hook can checkpoint commands by full text. [EXT:https://code.claude.com/docs/en/auto-mode-config]
- `useAutoModeDuringPlan` (default on) lets the classifier review shell commands while planning. [EXT:https://code.claude.com/docs/en/permission-modes]
