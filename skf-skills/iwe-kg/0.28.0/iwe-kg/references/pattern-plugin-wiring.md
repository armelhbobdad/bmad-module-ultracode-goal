# Pattern: the IWE Claude Code plugin wiring (iwe-org/skills 0.14.0)

The plugin itself lives outside the `iwe` repository. The manifest, hooks table, skill shims and install sections are T3, read from `iwe-org/skills` at commit `e3908762` and cited with EXT links. The binary-side bullets (hook output, `MEMORY` gating, where the prompts come from, and where the README and the binary disagree) come from the `iwe` 0.28.0 source at commit `5edc6d9` and are cited with SRC line references. [SRC:crates/iwe/src/main.rs:L1628] [SRC:crates/iwe/src/internal/claude/prompt.rs:L6] [SRC:crates/iwe/src/internal/claude/hook/post_tool.rs:L34]

## Contents

- [Manifest](#manifest)
- [Hooks](#hooks)
- [Skill shims](#skill-shims)
- [Install and permissions](#install-and-permissions)
- [Where the README and the 0.28.0 binary disagree](#where-the-readme-and-the-0280-binary-disagree)

## Manifest

`.claude-plugin/plugin.json`: name `iwe`, version `0.14.0`, author `iwe-org`, homepage <https://iwe.md>, repository <https://github.com/iwe-org/skills>. [EXT:https://raw.githubusercontent.com/iwe-org/skills/e3908762d5fa661fcba41d836d5fcb75dba4cebc/.claude-plugin/plugin.json]

## Hooks

`hooks/hooks.json` registers two command hooks, each with a 20 s timeout: [EXT:https://raw.githubusercontent.com/iwe-org/skills/e3908762d5fa661fcba41d836d5fcb75dba4cebc/hooks/hooks.json]

| Event | Matcher | Command |
|---|---|---|
| `SessionStart` | `startup\|resume\|clear\|compact\|fork` | `! command -v iwe >/dev/null 2>&1 \|\| iwe internal claude hook session-start \|\| [ $? -eq 2 ]` |
| `PostToolUse` | `Write\|Edit\|MultiEdit\|Bash` | `! command -v iwe >/dev/null 2>&1 \|\| iwe internal claude hook post-tool 2>/dev/null \|\| true` |

- Both commands succeed silently when `iwe` is not on `PATH`; the PostToolUse one also swallows every failure. [EXT:https://raw.githubusercontent.com/iwe-org/skills/e3908762d5fa661fcba41d836d5fcb75dba4cebc/hooks/hooks.json]
- The binary side: `session-start` prints the `<iwe-memory>` block or nothing; `post-tool` prints one JSON object with `hookSpecificOutput.additionalContext` or nothing. [SRC:crates/iwe/src/main.rs:L1628] [SRC:crates/iwe/src/main.rs:L1630] [SRC:crates/iwe/src/main.rs:L1635]
- Both hooks are inert without a `MEMORY` document in the workspace. [EXT:https://raw.githubusercontent.com/iwe-org/skills/e3908762d5fa661fcba41d836d5fcb75dba4cebc/README.md] [SRC:crates/iwe/src/internal/claude/hook/store.rs:L126]
- Hooks and skills use the session's working directory verbatim: start Claude Code at the workspace root. On Windows the one-liners need git-bash or WSL. [EXT:https://raw.githubusercontent.com/iwe-org/skills/e3908762d5fa661fcba41d836d5fcb75dba4cebc/README.md]

## Skill shims

Each plugin skill is frontmatter plus one injected command, so its text always comes from the installed binary: [EXT:https://raw.githubusercontent.com/iwe-org/skills/e3908762d5fa661fcba41d836d5fcb75dba4cebc/README.md]

| Skill | Requires | `allowed-tools` | Body |
|---|---|---|---|
| `distill` | IWE CLI >=0.21.0 | `Bash(iwe:*), AskUserQuestion` | `iwe internal claude prompt distill` [EXT:https://raw.githubusercontent.com/iwe-org/skills/e3908762d5fa661fcba41d836d5fcb75dba4cebc/skills/distill/SKILL.md] |
| `init` | IWE CLI >=0.21.0 | `Bash(iwe:*), AskUserQuestion` | `iwe internal claude prompt init` [EXT:https://raw.githubusercontent.com/iwe-org/skills/e3908762d5fa661fcba41d836d5fcb75dba4cebc/skills/init/SKILL.md] |
| `reflect` | IWE CLI >=0.21.0 | `Bash(iwe:*)` | `iwe internal claude prompt reflect` [EXT:https://raw.githubusercontent.com/iwe-org/skills/e3908762d5fa661fcba41d836d5fcb75dba4cebc/skills/reflect/SKILL.md] |
| `graph` | IWE CLI >=0.20.0 | `Bash(iwe:*)` | `iwe docs agent` [EXT:https://raw.githubusercontent.com/iwe-org/skills/e3908762d5fa661fcba41d836d5fcb75dba4cebc/skills/graph/SKILL.md] |

- Without injection, each shim tells the agent to run its command and to report an older `iwe` when the command is unknown. [EXT:https://raw.githubusercontent.com/iwe-org/skills/e3908762d5fa661fcba41d836d5fcb75dba4cebc/skills/distill/SKILL.md]
- The prompts behind the three memory skills are compiled into 0.28.0 from `crates/iwe/templates/claude/prompts/{init,distill,reflect}.md`; the `graph` body is `crates/iwe/docs/agent.md`. [SRC:crates/iwe/src/internal/claude/prompt.rs:L6] [SRC:crates/iwe/src/internal/claude/prompt.rs:L10] [SRC:crates/iwe/src/internal/claude/prompt.rs:L14] [SRC:crates/iwe/src/help.rs:L123]

## Install and permissions

- Plugin: `/plugin marketplace add iwe-org/skills`, then `/plugin install iwe@iwe-org`; skills are then `/iwe:init`, `/iwe:distill`, `/iwe:reflect`. Through `npx skills add iwe-org/skills` they are plain `/init`, `/distill`, `/reflect`, and bare `init` can resolve to Claude Code's built-in skill. [EXT:https://raw.githubusercontent.com/iwe-org/skills/e3908762d5fa661fcba41d836d5fcb75dba4cebc/README.md]
- One allowlist rule covers the memory skills: `{ "permissions": { "allow": ["Bash(iwe:*)"] } }` in `.claude/settings.json`. [EXT:https://raw.githubusercontent.com/iwe-org/skills/e3908762d5fa661fcba41d836d5fcb75dba4cebc/README.md]
- Turning memory off is deleting `MEMORY.md`; re-adding it resumes at each session's distilled line. [EXT:https://raw.githubusercontent.com/iwe-org/skills/e3908762d5fa661fcba41d836d5fcb75dba4cebc/README.md]

## Where the README and the 0.28.0 binary disagree

- The README says an editor-tool markdown write "is rewritten into the store's canonical form". In 0.28.0 the PostToolUse handler only schema-checks such a file, and the 0.26.0 changelog records the rewrite's removal. Trust the binary. [EXT:https://raw.githubusercontent.com/iwe-org/skills/e3908762d5fa661fcba41d836d5fcb75dba4cebc/README.md] [SRC:crates/iwe/src/internal/claude/hook/post_tool.rs:L34] [SRC:crates/iwe/src/internal/claude/hook/post_tool.rs:L55] [SRC:crates/iwe/CHANGELOG.md:L42]
