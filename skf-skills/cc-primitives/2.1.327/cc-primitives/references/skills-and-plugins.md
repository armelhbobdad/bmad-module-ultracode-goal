# Skills and plugins

## Contents

- [Skill locations and precedence](#skill-locations-and-precedence)
- [SKILL.md frontmatter](#skillmd-frontmatter)
- [Invocation and substitutions](#invocation-and-substitutions)
- [Loading, budgets and compaction](#loading-budgets-and-compaction)
- [Plugins](#plugins)

## Skill locations and precedence

| Location | Scope |
|----------|-------|
| `~/.claude/skills/<name>/SKILL.md` | Personal, all projects [EXT:https://code.claude.com/docs/en/skills] |
| `.claude/skills/<name>/SKILL.md` | Project; loaded from the start directory up to the repo root (in a linked worktree, up to the worktree root; on v2.1.277+ a worktree with no root `.claude/skills` loads the main checkout's project skills) [EXT:https://code.claude.com/docs/en/skills] |
| `<subdir>/.claude/skills/<name>/SKILL.md` | Nested; loads in sessions started in or below `<subdir>`, and in a session started above it once Claude works on files there; in neither case in cloud threads in a project [EXT:https://code.claude.com/docs/en/skills] |
| `<plugin>/skills/<name>/SKILL.md` | `/plugin-name:skill-name` [EXT:https://code.claude.com/docs/en/skills] |

Same-named skills: enterprise > personal > project; a skill beats a same-named `.claude/commands/` file; plugin skills are namespaced. [EXT:https://code.claude.com/docs/en/skills] An added directory's skill whose folder name clashes with an enterprise, personal or project skill, or one in a directory added earlier, runs as `/<prefix>:<skill-name>` (v2.1.309+), where the prefix is the added directory's folder name, starting with its parent folder's name when two added directories share a folder name; between two added directories, the skill from the directory added first (in `--add-dir` or `/add-dir` order) runs. [EXT:https://code.claude.com/docs/en/skills] Custom slash commands were merged into skills; `.claude/commands/` files still work but lack `name`/`paths` and supporting files. [EXT:https://code.claude.com/docs/en/skills] Adding, editing or removing a skill under `~/.claude/skills/`, the project `.claude/skills/` or an `--add-dir` directory's `.claude/skills/` is picked up live (not in bare mode), and live detection covers `SKILL.md` text only. A top-level skills directory created mid-session needs `/reload-skills`, and again after each later change there. For a skill folder that is also a plugin, changes to `.mcp.json`, `agents/` and `output-styles/` need `/reload-plugins`, and so do changes to `hooks/`, except a mod's module file when it reloads on its own. [EXT:https://code.claude.com/docs/en/skills]

## SKILL.md frontmatter

Frontmatter must start on line 1; unknown keys and YAML parse failures are silently ignored (the skill loads with no fields). [EXT:https://code.claude.com/docs/en/skills] All fields are optional; `description` is recommended. [EXT:https://code.claude.com/docs/en/skills]

| Field | Meaning |
|-------|---------|
| `name` | Command name (defaults to the directory name) [EXT:https://code.claude.com/docs/en/skills] |
| `description` | Routing text; description + `when_to_use` truncated at 1,536 characters in the skill listing (the cap is configurable with `skillListingMaxDescChars`) [EXT:https://code.claude.com/docs/en/skills] |
| `argument-hint`, `arguments` | Autocomplete hint; named positional arguments [EXT:https://code.claude.com/docs/en/skills] |
| `disable-model-invocation: true` | You can invoke it; Claude can't on its own (only when your message has `/name` as a separate word with no punctuation attached); description not in context [EXT:https://code.claude.com/docs/en/skills] |
| `user-invocable: false` | Hidden from `/`; only Claude invokes [EXT:https://code.claude.com/docs/en/skills] |
| `allowed-tools` / `disallowed-tools` | Pre-approve tools for the invoking turn / remove tools while active [EXT:https://code.claude.com/docs/en/skills] |
| `model`, `effort` | Per-turn model; effort override [EXT:https://code.claude.com/docs/en/skills] |
| `context: fork`, `agent`, `background` | Run in a forked subagent (default general-purpose, background by default; Claude Code waits for the result under `-p` or the Agent SDK or with `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`, and from v2.1.295 a dynamic-workflow agent that invokes it waits too) [EXT:https://code.claude.com/docs/en/skills] |
| `hooks` | Registered on invocation for the rest of the session [EXT:https://code.claude.com/docs/en/skills] |
| `paths` | Restrict automatic loading to matching files [EXT:https://code.claude.com/docs/en/skills] |

Outside Claude Code (Skills API, claude.ai) only `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools` are allowed. [EXT:https://code.claude.com/docs/en/skills]

## Invocation and substitutions

- `/name` or automatic loading by description; at the terminal prompt skills stack at the start of a message; in `-p`, put `/skill-name` in the prompt, and only the first skill loads, with the rest of the line as its arguments. [EXT:https://code.claude.com/docs/en/skills] [EXT:https://code.claude.com/docs/en/headless]
- `$ARGUMENTS` (appended as `ARGUMENTS: …` when unused), `$N`; `${CLAUDE_SESSION_ID}` (the current session ID), `${CLAUDE_SKILL_DIR}` (the skill folder), `${CLAUDE_PROJECT_DIR}`, `${CLAUDE_PLUGIN_ROOT}` and `${CLAUDE_PLUGIN_DATA}` (plugin skills), `${CLAUDE_EFFORT}` (the current effort level). [EXT:https://code.claude.com/docs/en/skills]
- Using `${CLAUDE_SKILL_DIR}` in both the body and `allowed-tools` runs a bundled script without a prompt; a project skill's `allowed-tools` applies even in a `-p` run in a never-trusted folder, but a managed `allowManagedPermissionRulesOnly` (v2.1.282+) makes Claude Code ignore it in project and personal skills. [EXT:https://code.claude.com/docs/en/skills]
- `` !`<command>` `` injects command output before the content reaches Claude; a failed command aborts the invocation. [EXT:https://code.claude.com/docs/en/skills] Injected commands never prompt for permission while the skill renders: outside auto mode, one whose permission check returns anything other than allow aborts the invocation unless `allowed-tools` pre-approves it, and one that a deny or ask rule matches aborts even then. [EXT:https://code.claude.com/docs/en/skills]
- Permission rules: `Skill(name)` exact, `Skill(name *)` prefix. [EXT:https://code.claude.com/docs/en/skills]

## Loading, budgets and compaction

- Body loads only when used and then stays in context across turns as one message (not re-read). [EXT:https://code.claude.com/docs/en/skills]
- Keep SKILL.md under 500 lines; move reference material to supporting files. [EXT:https://code.claude.com/docs/en/skills]
- After auto-compaction each skill's latest invocation is re-attached (first 5,000 tokens, 25,000 total). [EXT:https://code.claude.com/docs/en/skills]
- The skill listing budget is 1% of the context window (`SLASH_COMMAND_TOOL_CHAR_BUDGET` or `skillListingBudgetFraction` raise it). [EXT:https://code.claude.com/docs/en/skills]
- A forked skill does not see conversation history. [EXT:https://code.claude.com/docs/en/skills]

## Plugins

- Manifest `.claude-plugin/plugin.json` (optional; `name` is the only required key, kebab-case, namespaces components); everything else lives at the plugin root. [EXT:https://code.claude.com/docs/en/plugins/manifest-reference]
- Defaults: `skills/<name>/SKILL.md`, `hooks/hooks.json`, `.mcp.json`; a root CLAUDE.md is not loaded. [EXT:https://code.claude.com/docs/en/plugins/manifest-reference]
- Manifest `skills` adds to the default scan; `commands`, `agents`, `outputStyles`, `workflows`, `experimental.themes` and `experimental.monitors` replace their defaults; `hooks`, `mcpServers` and `lspServers` merge with `hooks/hooks.json`, `.mcp.json` and `.lsp.json`; paths must start with `./` (`skills` also accepts `"."`, `mcpServers` an `https://` bundle URL). [EXT:https://code.claude.com/docs/en/plugins/manifest-reference]
- `${CLAUDE_PLUGIN_ROOT}` (changes on update) and `${CLAUDE_PLUGIN_DATA}` (`~/.claude/plugins/data/<id>/`, kept across updates) resolve in Markdown bodies but not in Bash tool environments. [EXT:https://code.claude.com/docs/en/plugins/manifest-reference]
- `userConfig` values are prompted, for options not yet set, in the interactive `/plugin` interface when the plugin is installed or enabled there (`/plugin configure <plugin>@<marketplace>` reopens the dialog); the `claude plugin install` shell command never prompts (pass `--config KEY=VALUE` or pipe a JSON object to `claude plugin configure --values-stdin`); `claude plugin validate [--strict]`; install with `/plugin install <plugin>@<marketplace>`. [EXT:https://code.claude.com/docs/en/plugins/components] [EXT:https://code.claude.com/docs/en/plugins/manifest-reference] [EXT:https://code.claude.com/docs/en/skills]
- Plugin subagents ignore `hooks`, `mcpServers`, `permissionMode` and `initialPrompt`. [EXT:https://code.claude.com/docs/en/sub-agents] [EXT:https://code.claude.com/docs/en/plugins/components]
