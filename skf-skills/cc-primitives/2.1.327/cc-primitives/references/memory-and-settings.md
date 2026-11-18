# Memory and settings

## Contents

- [CLAUDE.md](#claudemd)
- [Rules](#rules)
- [Auto Memory](#auto-memory)
- [Settings files](#settings-files)
- [Precedence and merging](#precedence-and-merging)
- [Trust and scope restrictions](#trust-and-scope-restrictions)

## CLAUDE.md

- CLAUDE.md and Auto Memory are loaded every conversation as context, not enforced configuration; use a PreToolUse hook to block actions. [EXT:https://code.claude.com/docs/en/memory]
- Locations: managed policy (`/etc/claude-code/CLAUDE.md` on Linux), `~/.claude/CLAUDE.md`, `./CLAUDE.md` or `./.claude/CLAUDE.md`, `./CLAUDE.local.md` (gitignore it). [EXT:https://code.claude.com/docs/en/memory]
- Files from the working directory upward load at launch and concatenate root-first, with `CLAUDE.local.md` after `CLAUDE.md`; subdirectory files load on demand. [EXT:https://code.claude.com/docs/en/memory]
- Delivered as a user message after the system prompt; project-root CLAUDE.md is re-read after `/compact`. [EXT:https://code.claude.com/docs/en/memory]
- `@path` imports expand at launch (four hops, relative to the importing file); external imports in project files need a one-time approval. [EXT:https://code.claude.com/docs/en/memory]
- Keep each file under 200 lines; Claude gets the whole of each `CLAUDE.md` that loads at launch up to 4 MiB, and Claude Code skips a file over 4 MiB entirely. [EXT:https://code.claude.com/docs/en/memory] From v2.1.309, a file that loads on demand (a subdirectory `CLAUDE.md` or `CLAUDE.local.md` and the files it imports with `@path`, rules in a subdirectory's `.claude/rules/`, and path-scoped rules) that is over its per-file limit reaches Claude only as its start, ending with a note to read the rest with the Read tool; the limit is 40,000 characters with a 200K context window, and with a 1M window 200,000 characters on Claude Opus 4.6 and Claude Sonnet 4.6 and 150,000 on later models. [EXT:https://code.claude.com/docs/en/memory]
- `claudeMdExcludes` skips unrelated files (arrays merge; managed files cannot be excluded). By default AGENTS.md is read only when there is no `CLAUDE.md`, `.claude/CLAUDE.md` or `CLAUDE.local.md` in the working directory or above it; `~/.claude/CLAUDE.md`, the managed CLAUDE.md and `.claude/rules/` don't count. The **Project instructions** setting changes this (`claude-md-and-agents-md` reads both). Reading AGENTS.md directly requires v2.1.277+. [EXT:https://code.claude.com/docs/en/memory]
- `/context all` (under **Memory files**) shows which `CLAUDE.md` and `CLAUDE.local.md` files loaded at launch; in fullscreen mode `/context` alone collapses that list. [EXT:https://code.claude.com/docs/en/memory] A subdirectory `CLAUDE.md` doesn't appear there because it loads on demand; when it loads, a `Loaded` line with its path appears in the terminal. [EXT:https://code.claude.com/docs/en/memory] `/memory` lists memory file locations across user and project scopes (including ones that don't exist yet), toggles auto memory and opens the auto memory folder. [EXT:https://code.claude.com/docs/en/memory]

## Rules

`.claude/rules/*.md` (recursive) load at launch like `.claude/CLAUDE.md` unless scoped with `paths` frontmatter (the only field read), in which case they load when Claude reads, writes or edits a matching file; `~/.claude/rules/` applies to every project and loads first. [EXT:https://code.claude.com/docs/en/memory]

## Auto Memory

- Typed notes (user, feedback, project, reference); on by default in local sessions; `autoMemoryEnabled` (via `/memory` or settings) or `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` turns it off. [EXT:https://code.claude.com/docs/en/memory]
- The `/memory` toggle turns auto memory off but doesn't turn it back on in a background session or in a session another Claude Code session started (such as when Claude runs `claude` through its Bash tool); to turn it back on, run `claude` directly in a terminal and use the toggle there. [EXT:https://code.claude.com/docs/en/memory]
- Stored in `~/.claude/projects/<project>/memory/` (derived from the git repository, so worktrees share it); `autoMemoryDirectory` relocates it (absolute or `~/` path). [EXT:https://code.claude.com/docs/en/memory]
- `MEMORY.md` is a one-line-per-memory index; its first 200 lines or 25 KB load every session; topic files are read on demand. [EXT:https://code.claude.com/docs/en/memory]
- Machine-local; not loaded into subagents except forks. [EXT:https://code.claude.com/docs/en/memory]

## Settings files

| File | Scope |
|------|-------|
| `~/.claude/settings.json` | You, every project [EXT:https://code.claude.com/docs/en/settings] |
| `.claude/settings.json` | Team: permissions, hooks, plugins, env [EXT:https://code.claude.com/docs/en/settings] |
| `.claude/settings.local.json` | You, one project (personal overrides) [EXT:https://code.claude.com/docs/en/settings] |
| Managed settings | Organization; nothing in your own settings files or `--settings` overrides a managed key, except a few security-sensitive keys where a stricter value from a lower level wins (see [Precedence and merging](#precedence-and-merging)); a managed `model` is a starting default, not a lock [EXT:https://code.claude.com/docs/en/settings] |

- Installing Claude Code creates no settings file. Claude Code creates `.claude/settings.local.json` the first time you give a standing approval that saves permanently (a "Yes, and don't ask again" for a Bash command, for example; a file-edit approval lasts only the session) or change one of the few `/config` options stored there (such as Show tips). The approval is saved there as an allow rule. On its first write in a git repository that doesn't already ignore the file, Claude Code adds `**/.claude/settings.local.json` to the global git excludes; a file you create by hand needs its own `.gitignore` entry until then. [EXT:https://code.claude.com/docs/en/settings] [EXT:https://code.claude.com/docs/en/permissions]
- From a git subdirectory the local file is read/written at the repository root (main checkout for worktrees); it stays beside `.claude/settings.json` instead outside a git repository, when the repository root is the home directory, on Windows, or when the repository root or its `.git` or `.claude` entry isn't owned by your user. [EXT:https://code.claude.com/docs/en/settings]
- Settings are strict JSON; most edits hot-reload (hooks, permissions), but `model`/`effortLevel` are read at start; `ConfigChange` hooks run for direct edits to settings files, not for managed settings that arrive from MDM or the claude.ai console. [EXT:https://code.claude.com/docs/en/settings]
- `--settings` takes JSON inline or a file; `claude doctor` lists rejected entries; `/status` shows setting sources. [EXT:https://code.claude.com/docs/en/settings]
- `CLAUDE_CONFIG_DIR` relocates the home-directory files; `~/.claude.json` is Claude Code's own state file. [EXT:https://code.claude.com/docs/en/settings]

## Precedence and merging

Managed > command-line `--settings` > `.claude/settings.local.json` > `.claude/settings.json` > `~/.claude/settings.json`; the highest level that sets a key wins; list keys such as `permissions.allow` combine across files, while the four keys that hold model lists or per-model entries (`fallbackModel`, `modelPicker`, `availableModels` and `modelSettings`) follow their own rules; `env` blocks follow the same levels, while shell environment variables are not a level in this stack. [EXT:https://code.claude.com/docs/en/settings]

For a few security-sensitive keys, Claude Code honors a stricter value from a lower level over a managed value. [EXT:https://code.claude.com/docs/en/settings] Among them, `true` for `permissions.blockReadsOutsideWorkingDirectories` (v2.1.257+) or `permissions.blockWritesOutsideWorkingDirectories` (v2.1.314+) from any scope, and `true` for `permissions.denyInsteadOfPrompting` from `~/.claude/settings.json` or `--settings` (v2.1.319+), are honored even when a managed source sets `false`. [EXT:https://code.claude.com/docs/en/settings]

## Trust and scope restrictions

- `permissions.defaultMode` `auto`/`bypassPermissions` do not take effect from project or local settings. [EXT:https://code.claude.com/docs/en/settings]
- In a committed file, `permissions.allow`, `additionalDirectories`, `extraKnownMarketplaces` and most `env` values wait for folder trust; deny and ask apply immediately; untracked local allow rules skip the trust step. [EXT:https://code.claude.com/docs/en/settings]
- `claude -p` and SDK sessions never show the trust dialog. [EXT:https://code.claude.com/docs/en/permissions] In a folder never trusted, they don't use the `permissions.allow` rules or `additionalDirectories` in `.claude/settings.json` (Claude Code prints a `this workspace has not been trusted` warning to stderr) or `extraKnownMarketplaces` entries, but they do use hooks in settings files and the `env` block. [EXT:https://code.claude.com/docs/en/permissions] Project and local `env` values apply at startup in `-p` mode, apart from the variables project and local settings can't set. [EXT:https://code.claude.com/docs/en/settings-reference] See [Permissions in unattended runs](headless-and-cli.md#permissions-in-unattended-runs).
- A local allow rule does not outrank a project or managed ask rule. [EXT:https://code.claude.com/docs/en/settings]
- Cloud sessions do not read `~/.claude/settings.json` or `.claude/settings.local.json`. [EXT:https://code.claude.com/docs/en/settings]
- A `-p` run shows no dialog: it skips a broken user, project or local settings file, or a broken value in one, and continues with the rest (run `claude doctor` afterwards to see what it dropped). [EXT:https://code.claude.com/docs/en/settings] A `claude -p` run exits instead when `~/.claude.json` can't be parsed. [EXT:https://code.claude.com/docs/en/settings] A managed settings document that can't be parsed as a JSON object makes Claude Code exit with code 1 at startup, `claude -p` included, even when another admin source delivers a valid policy. [EXT:https://code.claude.com/docs/en/errors]
