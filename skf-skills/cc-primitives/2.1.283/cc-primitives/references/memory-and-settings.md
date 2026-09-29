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
- Keep each file under 200 lines; files up to 4 MiB load in full. [EXT:https://code.claude.com/docs/en/memory]
- `claudeMdExcludes` skips unrelated files (arrays merge; managed files cannot be excluded); AGENTS.md is read only when there is no CLAUDE.md. [EXT:https://code.claude.com/docs/en/memory]
- `/context` and `/memory` show loaded memory files. [EXT:https://code.claude.com/docs/en/memory]

## Rules

`.claude/rules/*.md` (recursive) load at launch like `.claude/CLAUDE.md` unless scoped with `paths` frontmatter (the only field read), in which case they load when Claude reads matching files; `~/.claude/rules/` applies to every project and loads first. [EXT:https://code.claude.com/docs/en/memory]

## Auto Memory

- Typed notes (user, feedback, project, reference); on by default; `autoMemoryEnabled` (via `/memory` or settings) or `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` turns it off. [EXT:https://code.claude.com/docs/en/memory]
- Stored in `~/.claude/projects/<project>/memory/` (derived from the git repository, so worktrees share it); `autoMemoryDirectory` relocates it (absolute or `~/` path). [EXT:https://code.claude.com/docs/en/memory]
- `MEMORY.md` is a one-line-per-memory index; its first 200 lines or 25 KB load every session; topic files are read on demand. [EXT:https://code.claude.com/docs/en/memory]
- Machine-local; not loaded into subagents except forks. [EXT:https://code.claude.com/docs/en/memory]

## Settings files

| File | Scope |
|------|-------|
| `~/.claude/settings.json` | You, every project [EXT:https://code.claude.com/docs/en/settings] |
| `.claude/settings.json` | Team: permissions, hooks, plugins, env [EXT:https://code.claude.com/docs/en/settings] |
| `.claude/settings.local.json` | You, one project (personal overrides) [EXT:https://code.claude.com/docs/en/settings] |
| Managed settings | Organization; cannot be overridden [EXT:https://code.claude.com/docs/en/settings] |

- Installing Claude Code creates no settings file; `.claude/settings.local.json` is created on the first "don't ask again" approval, which is saved there as an allow rule and added to the global git excludes. [EXT:https://code.claude.com/docs/en/settings]
- From a git subdirectory the local file is read/written at the repository root (main checkout for worktrees). [EXT:https://code.claude.com/docs/en/settings]
- Settings are strict JSON; most edits hot-reload (hooks, permissions), but `model`/`effortLevel` are read at start; `ConfigChange` hooks fire on changes. [EXT:https://code.claude.com/docs/en/settings]
- `--settings` takes JSON inline or a file; `claude doctor` lists rejected entries; `/status` shows setting sources. [EXT:https://code.claude.com/docs/en/settings]
- `CLAUDE_CONFIG_DIR` relocates the home-directory files; `~/.claude.json` is Claude Code's own state file. [EXT:https://code.claude.com/docs/en/settings]

## Precedence and merging

Managed > command-line `--settings` > `.claude/settings.local.json` > `.claude/settings.json` > `~/.claude/settings.json`; the highest level that sets a key wins; list keys such as `permissions.allow` combine across files; `env` blocks follow the same levels. [EXT:https://code.claude.com/docs/en/settings]

## Trust and scope restrictions

- `permissions.defaultMode` `auto`/`bypassPermissions` do not take effect from project or local settings. [EXT:https://code.claude.com/docs/en/settings]
- In a committed file, `permissions.allow`, `additionalDirectories`, `extraKnownMarketplaces` and most `env` values wait for folder trust; deny and ask apply immediately; untracked local allow rules skip the trust step. [EXT:https://code.claude.com/docs/en/settings]
- A local allow rule does not outrank a project or managed ask rule. [EXT:https://code.claude.com/docs/en/settings]
- Cloud sessions do not read `~/.claude/settings.json` or `.claude/settings.local.json`. [EXT:https://code.claude.com/docs/en/settings]
- In `-p` runs, invalid settings are skipped silently (see `claude doctor`). [EXT:https://code.claude.com/docs/en/settings]
