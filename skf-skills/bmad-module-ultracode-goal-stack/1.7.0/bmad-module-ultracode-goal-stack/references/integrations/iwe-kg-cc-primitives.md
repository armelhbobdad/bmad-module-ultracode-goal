# iwe-kg + cc-primitives Integration

**Type:** Event Handler
**Co-import files:** 0 (compose-mode; no codebase — the contract is documented in a constituent skill)
**Detection:** constituent-documented-contract (`detection_method: constituent_documented_contract`) — documented by iwe-kg (Adoption Steps; Pattern Surface; `references/pattern-plugin-wiring.md`; `references/pattern-memory-internal.md`)
**Confidence:** T3 (constituent-documented-contract) [composed] — weaker of iwe-kg (T1-low) and cc-primitives (T3)

## Integration Pattern

1. How the hooks arrive. The IWE Claude Code plugin is installed with `/plugin marketplace add iwe-org/skills`, then `/plugin install iwe@iwe-org`, and ships only `hooks.json` and frontmatter-only skills whose bodies the `iwe` binary prints (iwe-kg pattern-plugin-wiring.md L47; SKILL.md L124). Its `hooks/hooks.json` registers two command hooks, each with a 20 s timeout (pattern-plugin-wiring.md L19): `SessionStart` with matcher `startup|resume|clear|compact|fork`, running `iwe internal claude hook session-start`, and `PostToolUse` with matcher `Write|Edit|MultiEdit|Bash`, running `iwe internal claude hook post-tool` (pattern-plugin-wiring.md L23, L24; SKILL.md L54). cc-primitives names `hooks/hooks.json` as a plugin's default hook file, installs plugins with `/plugin install <plugin>@<marketplace>`, and, for a skill folder that is also a plugin, needs `/reload-plugins` after `hooks/` changes (skills-and-plugins.md L60, L63, L20). Plugin hooks also fire inside subagents (hooks.md L30).

2. When they do nothing. Both commands succeed silently when `iwe` is not on `PATH`, and the PostToolUse one also swallows every failure (pattern-plugin-wiring.md L26). Both print nothing without a `MEMORY` document in the workspace (pattern-plugin-wiring.md L28; SKILL.md L72). The MEMORY check runs after `load_config()`, though. So in a workspace with an older config version, these runs migrate `.iwe/config.toml` in place (pattern-memory-internal.md L38): any SessionStart run, a PostToolUse run for a Write/Edit/MultiEdit of a `.md`/`.dj` file, and a PostToolUse run for a Bash command with an `iwe create|update|rename|delete|attach` segment lacking `--strict` or an `iwe create|new` segment lacking `--dry-run`. The SessionStart command also turns an `iwe` exit 2 into success (`|| [ $? -eq 2 ]`, pattern-plugin-wiring.md L23); cc-primitives says SessionStart cannot be blocked anyway (hooks.md L83).

3. What SessionStart gives Claude. `hook session-start` reads the hook JSON from stdin, enters the store at the payload's `cwd` and prints the `<iwe-memory>` block, or nothing (pattern-memory-internal.md L62; pattern-plugin-wiring.md L27). The listings hold titles and keys, never bodies (pattern-memory-internal.md L64). cc-primitives documents `SessionStart` as firing when a session begins or resumes (hooks.md L56) but does not say what Claude Code does with a SessionStart hook's plain-text stdout. The Claude Code hooks page that cc-primitives hooks.md cites does say it: on exit 0, a SessionStart hook's plain-text stdout (output that does not start with `{`) is added as context Claude can see. So the `<iwe-memory>` block reaches Claude. Only the constituent-level citation is missing.

4. What PostToolUse gives Claude. The hook looks only at `Write`, `Edit`, `MultiEdit` and `Bash` (pattern-memory-internal.md L68). It schema-checks a workspace `.md` file an editor tool wrote without rewriting it (pattern-memory-internal.md L69), and the keys an `iwe create|update|rename|delete|attach` segment without `--strict` printed (pattern-memory-internal.md L70). It prints one JSON line, `{"suppressOutput": true, "systemMessage": NOTICE, "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": CONTEXT}}` (pattern-memory-internal.md L71). That is the shape cc-primitives asks for: `hookSpecificOutput` with `hookEventName`, and `additionalContext` inside it, which Claude Code wraps in a system reminder (hooks.md L88). cc-primitives lists `suppressOutput` as having no effect (hooks.md L88). Its matcher is the same tool list as TEA's `PostToolUse` entry, and all matching hooks run in parallel (hooks.md L72), so the two run side by side whenever one of those calls succeeds (inferred; a failed call fires `PostToolUseFailure` instead).

5. Where the session must start. Hooks and skills use the session's working directory verbatim: start Claude Code at the workspace root (pattern-plugin-wiring.md L29). `claude -p --bare` skips auto-discovery of hooks and installed plugins (headless-and-cli.md L17), so the hooks of an IWE plugin installed with `/plugin install` do not run there. Claude Code's headless page adds that a plugin passed explicitly with `--plugin-dir` (or `--plugin-url`) still loads in bare mode.

6. The `iwe init` artifacts. When its agent artifacts are enabled, `iwe init` appends an `<!-- iwe -->` section to `AGENTS.md` and registers `iwec` in `.mcp.json` (pattern-servers.md L55). Claude Code reads `AGENTS.md` only when there is no CLAUDE.md (memory-and-settings.md L20). So by default, where a project `CLAUDE.md`, `.claude/CLAUDE.md` or `CLAUDE.local.md` exists in the working directory or above it, the `<!-- iwe -->` section does not load. The exceptions are a `CLAUDE.md` that imports it with `@AGENTS.md` (memory-and-settings.md L18) and Project instructions set to `claude-md-and-agents-md` (memory-and-settings.md L20). A user-level `~/.claude/CLAUDE.md` or a managed `CLAUDE.md` does not count for this check (memory-and-settings.md L20). A `-p` session without `--bare` connects the project's `.mcp.json` servers (headless-and-cli.md L16).

## Key Files

Upstream files behind the cited lines (from the constituents' `[SRC:…]`, `[AST:…]` and `[EXT:…]` tags):

- `hooks/hooks.json` (iwe-org/skills, commit `e3908762`)
- `crates/iwe/src/main.rs`
- `crates/iwe/src/internal/claude/hook/post_tool.rs`
- `crates/iwe/src/internal/claude/hook/store.rs`
- `crates/iwe/src/internal/claude/hook/index.rs`
- `crates/iwe/src/init/agents.rs`

## Usage Convention

Install the plugin, keep `iwe` on `PATH`, and start Claude Code at the workspace root. Expect no blocking from either hook: SessionStart cannot be blocked, and the PostToolUse command always succeeds. Read the PostToolUse `additionalContext` as the place IWE reports schema problems after a write; pass `--strict` on `iwe` writes so the gate runs before the write instead. The allowlist rule `Bash(iwe:*)` in `.claude/settings.json` covers the memory skills (pattern-plugin-wiring.md L48).

## Evidence

Verbatim citations from the constituent skills (file relative to the skill root, nearest heading, line):

- [from skill: iwe-kg] `SKILL.md` — ## Adoption Steps, L54: "6. **Wire the plugin hooks.** SessionStart runs `iwe internal claude hook session-start`; PostToolUse on `Write|Edit|MultiEdit|Bash` runs `hook post-tool`; both are no-ops without `iwe` on `PATH`."
- [from skill: iwe-kg] `SKILL.md` — ## Pattern Surface, L73: "| 13 | `crates/iwe/src/internal/claude/hook/index.rs` | `render_memory_index()` | SessionStart `<iwe-memory>` block"
- [from skill: iwe-kg] `SKILL.md` — ## Pattern Surface, L74: "| 14 | `crates/iwe/src/internal/claude/hook/post_tool.rs` | `post_tool_report()` | PostToolUse schema check, `--strict` nudge, similar-page notice"
- [from skill: iwe-kg] `SKILL.md` — ## Pattern Surface, L72: "| 12 | `crates/iwe/src/internal/claude/hook/store.rs` | `enter_memory_store()` | Memory is on iff config loads and key `MEMORY` exists"
- [from skill: iwe-kg] `SKILL.md` — ## Architecture at a Glance, L124: "ships only `hooks.json` and frontmatter-only skills whose bodies come from `iwe internal claude prompt NAME` and `iwe docs agent`."
- [from skill: iwe-kg] `references/pattern-plugin-wiring.md` — ## Hooks, L19: "`hooks/hooks.json` registers two command hooks, each with a 20 s timeout:"
- [from skill: iwe-kg] `references/pattern-plugin-wiring.md` — ## Hooks, L23: "| `SessionStart` | `startup\|resume\|clear\|compact\|fork` | `! command -v iwe >/dev/null 2>&1 \|\| iwe internal claude hook session-start \|\| [ $? -eq 2 ]` |"
- [from skill: iwe-kg] `references/pattern-plugin-wiring.md` — ## Hooks, L24: "| `PostToolUse` | `Write\|Edit\|MultiEdit\|Bash` | `! command -v iwe >/dev/null 2>&1 \|\| iwe internal claude hook post-tool 2>/dev/null \|\| true` |"
- [from skill: iwe-kg] `references/pattern-plugin-wiring.md` — ## Hooks, L26: "- Both commands succeed silently when `iwe` is not on `PATH`; the PostToolUse one also swallows every failure."
- [from skill: iwe-kg] `references/pattern-plugin-wiring.md` — ## Hooks, L27: "- The binary side: `session-start` prints the `<iwe-memory>` block or nothing; `post-tool` prints one JSON object with `hookSpecificOutput.additionalContext` or nothing."
- [from skill: iwe-kg] `references/pattern-plugin-wiring.md` — ## Hooks, L28: "- Both hooks are inert without a `MEMORY` document in the workspace."
- [from skill: iwe-kg] `references/pattern-plugin-wiring.md` — ## Hooks, L29: "- Hooks and skills use the session's working directory verbatim: start Claude Code at the workspace root."
- [from skill: iwe-kg] `references/pattern-plugin-wiring.md` — ## Install and permissions, L47: "- Plugin: `/plugin marketplace add iwe-org/skills`, then `/plugin install iwe@iwe-org`; skills are then `/iwe:init`, `/iwe:distill`, `/iwe:reflect`."
- [from skill: iwe-kg] `references/pattern-plugin-wiring.md` — ## Install and permissions, L48: "- One allowlist rule covers the memory skills: `{ "permissions": { "allow": ["Bash(iwe:*)"] } }` in `.claude/settings.json`."
- [from skill: iwe-kg] `references/pattern-memory-internal.md` — ## SessionStart hook output, L62: "- `hook session-start` reads the hook JSON from stdin"
- [from skill: iwe-kg] `references/pattern-memory-internal.md` — ## SessionStart hook output, L64: "- Listings project `title=$title,key=$key` (plus the sort field): titles and keys, never bodies."
- [from skill: iwe-kg] `references/pattern-memory-internal.md` — ## PostToolUse hook behaviour, L68: "- Only `tool_name` `Write`, `Edit`, `MultiEdit` and `Bash` are looked at."
- [from skill: iwe-kg] `references/pattern-memory-internal.md` — ## PostToolUse hook behaviour, L69: "The file is **not rewritten**."
- [from skill: iwe-kg] `references/pattern-memory-internal.md` — ## PostToolUse hook behaviour, L70: "- Bash: for an `iwe create|update|rename|delete|attach` segment without `--strict`, the keys the command printed are schema-checked."
- [from skill: iwe-kg] `references/pattern-memory-internal.md` — ## PostToolUse hook behaviour, L71: "- Output is one JSON line: `{"suppressOutput": true, "systemMessage": NOTICE, "hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": CONTEXT}}`."
- [from skill: iwe-kg] `references/pattern-servers.md` — ## Registering the servers, L55: "- `iwe init`, when its agent artifacts are enabled, appends an `<!-- iwe -->` section to `AGENTS.md` and registers `"iwe": { "command": "iwec", "args": [] }` in `.mcp.json`; each is left untouched when already present."
- [from skill: cc-primitives] `SKILL.md` — ## Key Types, L87: "**Hook events used by orchestrators:** `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `SubagentStop`, `Stop`, `StopFailure`."
- [from skill: cc-primitives] `references/hooks.md` — ## Configuration, L30: "Entries merge across levels; identical handlers in several files run once; settings/policy/plugin hooks also fire inside subagents."
- [from skill: cc-primitives] `references/hooks.md` — ## Events, L56: "`SessionStart` (session begins or resumes)"
- [from skill: cc-primitives] `references/hooks.md` — ## Handlers, L72: "- All matching hooks run in parallel"
- [from skill: cc-primitives] `references/hooks.md` — ## Exit codes, L83: "some events (e.g. SessionStart) cannot be blocked."
- [from skill: cc-primitives] `references/hooks.md` — ## JSON output, L88: "`suppressOutput` (no effect)."
- [from skill: cc-primitives] `references/hooks.md` — ## JSON output, L88: "`hookSpecificOutput` needs `hookEventName`; `additionalContext` belongs inside it (top-level is ignored) and is wrapped in a system reminder; text fields are capped at 10,000 characters."
- [from skill: cc-primitives] `references/skills-and-plugins.md` — ## Skill locations and precedence, L20: "For a skill folder that is also a plugin, changes to `hooks/`, `.mcp.json`, `agents/` and `output-styles/` need `/reload-plugins`."
- [from skill: cc-primitives] `references/skills-and-plugins.md` — ## Plugins, L60: "- Defaults: `skills/<name>/SKILL.md`, `hooks/hooks.json`, `.mcp.json`; a root CLAUDE.md is not loaded."
- [from skill: cc-primitives] `references/skills-and-plugins.md` — ## Plugins, L63: "install with `/plugin install <plugin>@<marketplace>`."
- [from skill: cc-primitives] `references/memory-and-settings.md` — ## CLAUDE.md, L20: "By default AGENTS.md is read only when there is no `CLAUDE.md`, `.claude/CLAUDE.md` or `CLAUDE.local.md` in the working directory or above it; `~/.claude/CLAUDE.md`, the managed CLAUDE.md and `.claude/rules/` don't count. The **Project instructions** setting changes this (`claude-md-and-agents-md` reads both)."
- [from skill: cc-primitives] `references/headless-and-cli.md` — ## claude -p behaviour, L16: "- `-p` without `--bare` runs the project's `.claude/settings.json` hooks and `.mcp.json` servers even in an untrusted folder."
- [from skill: cc-primitives] `references/headless-and-cli.md` — ## claude -p behaviour, L17: "- `--bare` skips auto-discovery of hooks, skills, commands, subagents, plugins, MCP, auto memory and CLAUDE.md"
- [from skill: iwe-kg] `references/pattern-memory-internal.md` — ## The memory switch, L38: "in a workspace with an older config version migrates `.iwe/config.toml` in place."
