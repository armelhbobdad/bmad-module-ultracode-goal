# graphify-kg + cc-primitives Integration

**Type:** Event Handler
**Co-import files:** 0 (compose-mode; no codebase — the contract is documented in a constituent skill)
**Detection:** constituent-documented-contract (`detection_method: constituent_documented_contract`) — documented by graphify-kg (Adoption Steps; Pattern Surface; `references/pattern-claude-code-integration.md`)
**Confidence:** T3 (constituent-documented-contract) [composed] — weaker of graphify-kg (T1) and cc-primitives (T3)

## Integration Pattern

1. What each install writes. `graphify claude install` writes a `## graphify` section to `./CLAUDE.md` and PreToolUse hooks to `./.claude/settings.json`, with the resolved `graphify` exe path, absolute unless resolution falls back to the bare `graphify` (graphify-kg SKILL.md L58; pattern-claude-code-integration.md L20, L75). `graphify install` (user scope) writes no settings: it copies the skill to `~/.claude/skills/graphify/SKILL.md` and adds a `# graphify` registration to `~/.claude/CLAUDE.md` (pattern-claude-code-integration.md L18). Both locations are Claude Code's: `~/.claude/skills/<name>/SKILL.md` is the personal skill scope and `~/.claude/CLAUDE.md` a user instruction file (cc-primitives skills-and-plugins.md L15; memory-and-settings.md L15).

2. The CLAUDE.md side. `claude_install` writes the packaged always-on block into `./CLAUDE.md`, replacing an exact `## graphify` section in place or appending it (pattern-claude-code-integration.md L47). When `graphify-out/graph.json` exists, its rules ask Claude to run `graphify query "<question>"` before the first grep, search or source-file read for a codebase question, and to put that rule in every subagent prompt that explores code. They also ask Claude to run `graphify update .` after modifying code (L57, L60). Per cc-primitives, Claude Code loads `./CLAUDE.md` at launch, delivers it as a user message after the system prompt, and treats it as context, not enforced configuration (memory-and-settings.md L14, L16, L17). The rules guide Claude; they enforce nothing.

3. The PreToolUse side. The install writes two command hooks every time, replacing an old payload: matcher `Bash|Grep` runs `{exe} hook-guard search` and matcher `Read|Glob` runs `{exe} hook-guard read`, each with `"timeout": 10` (L64, L68, L69). `{exe}` is the resolved `graphify` executable: `shutil.which("graphify")`, else `graphify.exe` or `graphify` beside `sys.executable`, else the bare `graphify`, with forward slashes and double quotes when it contains a space; a project install always writes the bare `graphify`, because that file gets committed (L75). graphify's earlier entries are stripped first and every other hook is kept; a `settings.json` that is not a JSON object is refused with exit 1; the previous file is kept as `settings.json.graphify-bak` (L77, L78, L79). On the Claude Code side, tool events match on `tool_name`, and `PreToolUse` fires before the call and can block (cc-primitives hooks.md L61, L56).

4. How the guard answers. It reads the tool call JSON on stdin and always exits 0 (L83), and prints a JSON nudge or nothing (pattern-cli-reference.md L89); Claude Code parses stdout JSON at exit 0 (hooks.md L80). Nudges are budgeted per agent (L87). In strict mode it denies at most one raw Read per session id through `hookSpecificOutput.permissionDecision: "deny"`, never through the exit code (L88), the field cc-primitives documents for PreToolUse control (hooks.md L90; SKILL.md L64). A deny holds even in `bypassPermissions` (cc-primitives SKILL.md L46), so graphify's strict deny does too (inferred).

5. When the guard does nothing. Any error inside the guard prints nothing and exits 0 (L89), so a guard bug never blocks a legitimate tool call, and a timed-out PreToolUse hook does not block (hooks.md L68). That fail-open covers only the Python guard. graphify-kg flags that the hook command itself has no shell-level fail-open guard and resolves `graphify` with `shutil.which` (#3280, open; SKILL.md L88; pattern-claude-code-integration.md L130). On Claude Code, an exit other than 0 or 2 is a non-blocking error, and so is a missing or non-executable command (hooks.md L82), so a launcher failure there should not block the call either (inferred). The one deliberate block is strict mode's single Read deny. `claude -p --bare` skips auto-discovery of hooks and CLAUDE.md, so neither the section nor the guard loads there (headless-and-cli.md L17).

## Key Files

Upstream source files behind the cited lines (from the constituents' `[SRC:…]` and `[AST:…]` tags):

- `graphify/install.py`
- `graphify/cli.py`
- `graphify/always_on/claude-md.md`

## Usage Convention

Run `graphify claude install` once per project, and again to refresh graphify's entries: it replaces only its own hooks and keeps TEA's and any other. Keep `.claude/settings.json` a JSON object, or graphify refuses to touch it. Treat the `## graphify` rules as context and the guard as a nudge: it always exits 0, and it denies only in strict mode, once per session, through `permissionDecision: "deny"`.

## Evidence

Verbatim citations from the constituent skills (file relative to the skill root, nearest heading, line):

- [from skill: graphify-kg] `SKILL.md` — ## Adoption Steps, L58: "**Wire Claude Code.** `graphify install` copies the skill to `~/.claude/skills/graphify/` and registers it in `~/.claude/CLAUDE.md`. `graphify claude install` writes a `## graphify` section to `./CLAUDE.md` and PreToolUse hooks to `./.claude/settings.json`."
- [from skill: graphify-kg] `SKILL.md` — ## Pattern Surface, L77: "| 12 | `graphify/install.py` | `install()`, `claude_install()` | skill copy, CLAUDE.md blocks, PreToolUse hooks"
- [from skill: graphify-kg] `references/pattern-claude-code-integration.md` — ## Which command writes what, L18: "| `graphify install` | `~/.claude/skills/graphify/SKILL.md` and `references/` | `# graphify` registration in `~/.claude/CLAUDE.md` | no |"
- [from skill: graphify-kg] `references/pattern-claude-code-integration.md` — ## Which command writes what, L20: "| `graphify claude install` | no | `## graphify` section in `./CLAUDE.md` | `./.claude/settings.json`, absolute exe path |"
- [from skill: graphify-kg] `references/pattern-claude-code-integration.md` — ## graphify claude install, L47: "`claude_install` writes the packaged always-on block, `graphify/always_on/claude-md.md`, into `./CLAUDE.md`. The block is replaced in place when an exact `## graphify` line exists (the section runs to the next H2) and appended otherwise."
- [from skill: graphify-kg] `references/pattern-claude-code-integration.md` — ## graphify claude install, L57: "- When graphify-out/graph.json exists, run `graphify query "<question>"` before your first grep, search or source-file read for a codebase question"
- [from skill: graphify-kg] `references/pattern-claude-code-integration.md` — ## graphify claude install, L60: "- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost)."
- [from skill: graphify-kg] `references/pattern-claude-code-integration.md` — ## graphify claude install, L64: "It then installs the PreToolUse hooks, every time, so an old payload is replaced:"
- [from skill: graphify-kg] `references/pattern-claude-code-integration.md` — ## graphify claude install, L68: "{"matcher": "Bash|Grep", "hooks": [{"type": "command", "command": "{exe} hook-guard search", "timeout": 10}]},"
- [from skill: graphify-kg] `references/pattern-claude-code-integration.md` — ## graphify claude install, L69: "{"matcher": "Read|Glob", "hooks": [{"type": "command", "command": "{exe} hook-guard read", "timeout": 10}]}"
- [from skill: graphify-kg] `references/pattern-claude-code-integration.md` — ## graphify claude install, L75: "A project install writes the bare `graphify` instead, because that file gets committed."
- [from skill: graphify-kg] `references/pattern-claude-code-integration.md` — ## graphify claude install, L77: "- graphify's earlier entries are stripped before the new ones are added, and every other hook is kept."
- [from skill: graphify-kg] `references/pattern-claude-code-integration.md` — ## graphify claude install, L78: "- An existing `settings.json` that is not a JSON object is left alone: `[graphify] refusing to modify ... not valid JSON`, exit 1."
- [from skill: graphify-kg] `references/pattern-claude-code-integration.md` — ## graphify claude install, L79: "- Before an overwrite, the previous file is copied to `settings.json.graphify-bak`; an identical result is not rewritten."
- [from skill: graphify-kg] `references/pattern-claude-code-integration.md` — ## The PreToolUse guard, L83: "`graphify hook-guard search|read [--strict]` reads the tool call JSON on stdin and always exits 0."
- [from skill: graphify-kg] `references/pattern-claude-code-integration.md` — ## The PreToolUse guard, L87: "- Every nudge is budgeted per agent (the session id, plus `agent_id` for subagents)."
- [from skill: graphify-kg] `references/pattern-claude-code-integration.md` — ## The PreToolUse guard, L88: "- **strict**: at most once per session id, a raw Read (tool_name `Read` or absent) of an in-project file is denied through `hookSpecificOutput.permissionDecision: "deny"`, never through the exit code."
- [from skill: graphify-kg] `references/pattern-claude-code-integration.md` — ## The PreToolUse guard, L89: "- Any error prints nothing and exits 0, so a legitimate tool call is never blocked by a guard bug."
- [from skill: graphify-kg] `references/pattern-cli-reference.md` — ## Internal commands, L89: "It prints a JSON nudge or nothing."
- [from skill: cc-primitives] `SKILL.md` — ## Common Workflows, L46: "A deny holds even in `bypassPermissions`."
- [from skill: cc-primitives] `SKILL.md` — ## Key API Summary, L64: "| `PreToolUse` | tool events, matcher on `tool_name` | `permissionDecision` allow/deny/ask/defer; exit 2 = deny"
- [from skill: cc-primitives] `references/hooks.md` — ## Events, L56: "`PreToolUse` (after parameters are created, before the call; can block)"
- [from skill: cc-primitives] `references/hooks.md` — ## Matchers and the if filter, L61: "- Tool events match against `tool_name`"
- [from skill: cc-primitives] `references/hooks.md` — ## Handlers, L68: "a timed-out PreToolUse hook does not block"
- [from skill: cc-primitives] `references/hooks.md` — ## Exit codes, L80: "- `0`: success; stdout JSON is parsed; exit-0 stderr goes only to the debug log; silence is not approval."
- [from skill: cc-primitives] `references/hooks.md` — ## PreToolUse control, L90: "`hookSpecificOutput.permissionDecision`: `allow` | `deny` | `ask` | `defer`"
- [from skill: cc-primitives] `references/memory-and-settings.md` — ## CLAUDE.md, L14: "- CLAUDE.md and Auto Memory are loaded every conversation as context, not enforced configuration; use a PreToolUse hook to block actions."
- [from skill: cc-primitives] `references/memory-and-settings.md` — ## CLAUDE.md, L15: "- Locations: managed policy (`/etc/claude-code/CLAUDE.md` on Linux), `~/.claude/CLAUDE.md`, `./CLAUDE.md` or `./.claude/CLAUDE.md`"
- [from skill: cc-primitives] `references/memory-and-settings.md` — ## CLAUDE.md, L16: "- Files from the working directory upward load at launch and concatenate root-first"
- [from skill: cc-primitives] `references/memory-and-settings.md` — ## CLAUDE.md, L17: "- Delivered as a user message after the system prompt"
- [from skill: cc-primitives] `references/headless-and-cli.md` — ## claude -p behaviour, L17: "- `--bare` skips auto-discovery of hooks, skills, commands, subagents, plugins, MCP, auto memory and CLAUDE.md"
- [from skill: cc-primitives] `references/skills-and-plugins.md` — ## Skill locations and precedence, L15: "| `~/.claude/skills/<name>/SKILL.md` | Personal, all projects"
- [from skill: graphify-kg] `references/pattern-claude-code-integration.md` — ## graphify claude install, L75: "`{exe}` is `shutil.which("graphify")`. When that finds nothing, it is `graphify.exe` or `graphify` beside `sys.executable`, and failing that the bare `graphify`."
- [from skill: graphify-kg] `SKILL.md` — ## Migration & Deprecation Warnings, L88: "The PreToolUse hook has no fail-open guard and resolves `graphify` with `shutil.which` (#3280, open)."
- [from skill: graphify-kg] `references/pattern-claude-code-integration.md` — ## Temporal context, L130: "The PreToolUse hook has no fail-open guard at the shell level, and `shutil.which` can return an unrunnable shim on a hardened Windows machine, failing every matching tool call."
- [from skill: cc-primitives] `references/hooks.md` — ## Exit codes, L82: "Other codes: non-blocking error for most events (exit 1 without JSON included); a missing or non-executable script also fails silently as non-blocking"
