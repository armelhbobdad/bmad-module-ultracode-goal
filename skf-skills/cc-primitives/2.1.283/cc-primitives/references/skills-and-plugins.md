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
| `.claude/skills/<name>/SKILL.md` | Project; loaded from the start directory up to the repo root [EXT:https://code.claude.com/docs/en/skills] |
| `<subdir>/.claude/skills/<name>/SKILL.md` | Nested; loads once Claude works on files there [EXT:https://code.claude.com/docs/en/skills] |
| `<plugin>/skills/<name>/SKILL.md` | `/plugin-name:skill-name` [EXT:https://code.claude.com/docs/en/skills] |

Same-named skills: enterprise > personal > project; a skill beats a same-named `.claude/commands/` file; plugin skills are namespaced. [EXT:https://code.claude.com/docs/en/skills] Custom slash commands were merged into skills; `.claude/commands/` files still work but lack `name`/`paths` and supporting files. [EXT:https://code.claude.com/docs/en/skills] Edits under skill directories are picked up live; plugin hooks/agents/MCP need `/reload-plugins`. [EXT:https://code.claude.com/docs/en/skills]

## SKILL.md frontmatter

Frontmatter must start on line 1; unknown keys and YAML parse failures are silently ignored (the skill loads with no fields). [EXT:https://code.claude.com/docs/en/skills] All fields are optional; `description` is recommended. [EXT:https://code.claude.com/docs/en/skills]

| Field | Meaning |
|-------|---------|
| `name` | Command name (defaults to the directory name) [EXT:https://code.claude.com/docs/en/skills] |
| `description` | Routing text; description + `when_to_use` truncated at 1,536 characters [EXT:https://code.claude.com/docs/en/skills] |
| `argument-hint`, `arguments` | Autocomplete hint; named positional arguments [EXT:https://code.claude.com/docs/en/skills] |
| `disable-model-invocation: true` | Only the user can invoke; description not in context [EXT:https://code.claude.com/docs/en/skills] |
| `user-invocable: false` | Hidden from `/`; only Claude invokes [EXT:https://code.claude.com/docs/en/skills] |
| `allowed-tools` / `disallowed-tools` | Pre-approve tools for the invoking turn / remove tools while active [EXT:https://code.claude.com/docs/en/skills] |
| `model`, `effort` | Per-turn model; effort override [EXT:https://code.claude.com/docs/en/skills] |
| `context: fork`, `agent`, `background` | Run in a forked subagent (default general-purpose, background by default) [EXT:https://code.claude.com/docs/en/skills] |
| `hooks` | Registered on invocation for the rest of the session [EXT:https://code.claude.com/docs/en/skills] |
| `paths` | Restrict automatic loading to matching files [EXT:https://code.claude.com/docs/en/skills] |

Outside Claude Code (Skills API, claude.ai) only `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools` are allowed. [EXT:https://code.claude.com/docs/en/skills]

## Invocation and substitutions

- `/name` or automatic loading by description; skills stack at the start of a message; in `-p`, put `/skill-name` in the prompt. [EXT:https://code.claude.com/docs/en/skills] [EXT:https://code.claude.com/docs/en/headless]
- `$ARGUMENTS` (appended as `ARGUMENTS: …` when unused), `$N`; `${CLAUDE_SKILL_DIR}` (the skill folder), `${CLAUDE_PROJECT_DIR}`, `${CLAUDE_PLUGIN_ROOT}` (plugin skills), `${CLAUDE_EFFORT}` (ultracode reports as `xhigh`). [EXT:https://code.claude.com/docs/en/skills]
- Using `${CLAUDE_SKILL_DIR}` in both the body and `allowed-tools` runs a bundled script without a prompt; workspace trust does not gate `allowed-tools`. [EXT:https://code.claude.com/docs/en/skills]
- `` !`<command>` `` injects command output before the content reaches Claude; a failed command aborts the invocation. [EXT:https://code.claude.com/docs/en/skills]
- Permission rules: `Skill(name)` exact, `Skill(name *)` prefix. [EXT:https://code.claude.com/docs/en/skills]

## Loading, budgets and compaction

- Body loads only when used and then stays in context across turns as one message (not re-read). [EXT:https://code.claude.com/docs/en/skills]
- Keep SKILL.md under 500 lines; move reference material to supporting files. [EXT:https://code.claude.com/docs/en/skills]
- After auto-compaction each skill's latest invocation is re-attached (first 5,000 tokens, 25,000 total). [EXT:https://code.claude.com/docs/en/skills]
- The skill listing budget is 1% of the context window (`SLASH_COMMAND_TOOL_CHAR_BUDGET` or `skillListingBudgetFraction` raise it). [EXT:https://code.claude.com/docs/en/skills]
- A forked skill does not see conversation history. [EXT:https://code.claude.com/docs/en/skills]

## Plugins

- Manifest `.claude-plugin/plugin.json` (optional; `name` is the only required key, kebab-case, namespaces components); everything else lives at the plugin root. [EXT:https://code.claude.com/docs/en/plugins-reference]
- Defaults: `skills/<name>/SKILL.md`, `hooks/hooks.json`, `.mcp.json`; a root CLAUDE.md is not loaded. [EXT:https://code.claude.com/docs/en/plugins-reference]
- Manifest `skills` adds to the default scan; `commands`, `agents`, workflows and others replace defaults; `hooks` merge with `hooks/hooks.json`; paths must start with `./`. [EXT:https://code.claude.com/docs/en/plugins-reference]
- `${CLAUDE_PLUGIN_ROOT}` (changes on update) and `${CLAUDE_PLUGIN_DATA}` (`~/.claude/plugins/data/<id>/`, persistent) resolve in Markdown bodies but not in Bash tool environments. [EXT:https://code.claude.com/docs/en/plugins-reference]
- `userConfig` values are prompted at enable time; `claude plugin validate [--strict]`; install with `/plugin install <plugin>@<marketplace>`. [EXT:https://code.claude.com/docs/en/plugins-reference] [EXT:https://code.claude.com/docs/en/skills]
- Plugin subagents ignore `hooks`, `mcpServers` and `permissionMode`. [EXT:https://code.claude.com/docs/en/sub-agents]
