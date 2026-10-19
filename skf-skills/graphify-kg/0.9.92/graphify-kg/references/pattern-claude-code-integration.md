# Pattern: wiring graphify into Claude Code, git and MCP

## Contents

- [Which command writes what](#which-command-writes-what)
- [graphify install](#graphify-install)
- [graphify claude install](#graphify-claude-install)
- [The PreToolUse guard](#the-pretooluse-guard)
- [Uninstalling](#uninstalling)
- [Git hooks](#git-hooks)
- [The MCP server](#the-mcp-server)
- [Temporal context](#temporal-context)

## Which command writes what

| Command | Skill copy | CLAUDE.md | `.claude/settings.json` |
|---------|------------|-----------|-------------------------|
| `graphify install` | `~/.claude/skills/graphify/SKILL.md` and `references/` | `# graphify` registration in `~/.claude/CLAUDE.md` | no |
| `graphify install --project` | `./.claude/skills/graphify/` | `# graphify` registration in `./.claude/CLAUDE.md`, and the `## graphify` section in `./CLAUDE.md` | `./.claude/settings.json`, bare `graphify` command |
| `graphify claude install` | no | `## graphify` section in `./CLAUDE.md` | `./.claude/settings.json`, absolute exe path |
| `graphify claude install --project` | as `install --project`, but always the `claude` skill files, also on Windows | as `install --project` | as `install --project` |

[AST:graphify/install.py:L917] [AST:graphify/install.py:L2136] [SRC:graphify/install.py:L1975] [SRC:graphify/install.py:L2588]

With `CLAUDE_CONFIG_DIR` set, the user-scope skill and registration go to `$CLAUDE_CONFIG_DIR/skills/graphify/SKILL.md` and `$CLAUDE_CONFIG_DIR/CLAUDE.md`. [SRC:graphify/install.py:L194] [SRC:graphify/install.py:L962]

## graphify install

- The platform defaults to `windows` on Windows and to `claude` elsewhere. Both install to the `claude` destination, `.claude/skills/graphify/`, with different skill files (next point). [SRC:graphify/install.py:L2499] [SRC:graphify/install.py:L608] [SRC:graphify/install.py:L709]
- For the `claude` platform, the packaged `graphify/skill.md` is copied through a temporary file and an atomic rename, after `graphify/skills/claude/references/` has been installed beside it atomically. On Windows the default platform is `windows`: it copies `graphify/skill-windows.md` with `graphify/skills/windows/references/` to the same `.claude/skills/graphify/` location. So on Windows `graphify install --project` installs the windows skill files, while `graphify claude install --project` always installs the claude ones. [SRC:graphify/install.py:L317] [SRC:graphify/install.py:L343] [SRC:graphify/install.py:L368] [SRC:graphify/install.py:L709] [SRC:graphify/install.py:L2499] [SRC:graphify/install.py:L2590]
- An existing `SKILL.md` that differs from the packaged one is kept as `SKILL.md.bak`, overwritten on each install. [SRC:graphify/install.py:L359]
- A `.graphify_version` stamp is written next to `SKILL.md`. On later runs graphify uses it to re-copy a stale user-scope copy only: one whose stamp is older than the package, in a folder that only one platform writes to, and not vscode. Project-scope copies such as `./.claude/skills/graphify/` are never refreshed. The refresh is skipped when any argv token is `install`, `uninstall`, `hook-check` or `hook-guard`, and `GRAPHIFY_NO_AUTO_REFRESH` set to `1`, `true` or `yes` turns it off. [SRC:graphify/install.py:L376] [SRC:graphify/__main__.py:L294] [SRC:graphify/__main__.py:L307] [SRC:graphify/__main__.py:L833]
- The registration block is added or refreshed in place, keyed on the exact `# graphify` H1 line, keeping the file's own line endings: [SRC:graphify/install.py:L546] [SRC:graphify/install.py:L1012] [SRC:graphify/install.py:L563]

```markdown
# graphify
- **graphify** (`~/.claude/skills/graphify/SKILL.md`) - any input to knowledge graph. Trigger: `/graphify`
When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.
```

- When the CLAUDE.md cannot be written, a read-only dotfile for example, the registration is skipped with a hint on stderr and the install still completes. [SRC:graphify/install.py:L563]
- `--strict` without `--project` only prints a note: strict mode belongs to the project hook. [SRC:graphify/install.py:L2548]
- The install prints `Done. Open your AI coding assistant and type:`, then `/graphify .` on its own line, and ends with the hosted-version notice `Prefer a hosted version? Try the graphify platform free for 14 days:` / `https://app.graphify.com`. With `--project`, a `git add` hint is printed just before `Done.`. For claude or windows, the `./CLAUDE.md` and `settings.json` output and a second `git add` hint follow the notice. [SRC:graphify/install.py:L988] [SRC:graphify/install.py:L992] [SRC:graphify/install.py:L984] [SRC:graphify/install.py:L1980]

## graphify claude install

`claude_install` writes the packaged always-on block, `graphify/always_on/claude-md.md`, into `./CLAUDE.md`. The block is replaced in place when an exact `## graphify` line exists (the section runs to the next H2) and appended otherwise. An unchanged file prints `graphify already configured ... (no change)`. [AST:graphify/install.py:L2136] [SRC:graphify/install.py:L1001] [SRC:graphify/install.py:L756]

The block at 0.9.92 (the opening of each rule; the first rule continues past this excerpt): [SRC:graphify/always_on/claude-md.md:L1]

```markdown
## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- When graphify-out/graph.json exists, run `graphify query "<question>"` before your first grep, search or source-file read for a codebase question, and put this rule in every subagent prompt that explores code. ...
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
- A committed graphify-out/graph.json is rewritten whole on every build, so a large diff to it in a pull request is expected. ...
```

It then installs the PreToolUse hooks, every time, so an old payload is replaced: [SRC:graphify/install.py:L2165] [SRC:graphify/install.py:L445]

```json
{"hooks": {"PreToolUse": [
  {"matcher": "Bash|Grep", "hooks": [{"type": "command", "command": "{exe} hook-guard search", "timeout": 10}]},
  {"matcher": "Read|Glob", "hooks": [{"type": "command", "command": "{exe} hook-guard read", "timeout": 10}]}
]}}
```

[SRC:graphify/install.py:L476] [SRC:graphify/install.py:L478]

- `{exe}` is `shutil.which("graphify")`. When that finds nothing, it is `graphify.exe` or `graphify` beside `sys.executable`, and failing that the bare `graphify`. Backslashes become forward slashes, and the value is wrapped in double quotes when it contains a space and is not already quoted. A project install writes the bare `graphify` instead, because that file gets committed. [SRC:graphify/install.py:L1804] [SRC:graphify/install.py:L1830] [SRC:graphify/install.py:L1839] [SRC:graphify/install.py:L472]
- `--strict` adds `--strict` to the read hook. [SRC:graphify/install.py:L445]
- graphify's earlier entries are stripped before the new ones are added, and every other hook is kept. [SRC:graphify/install.py:L2165]
- An existing `settings.json` that is not a JSON object is left alone: `[graphify] refusing to modify ... not valid JSON`, exit 1. [SRC:graphify/install.py:L1058]
- Before an overwrite, the previous file is copied to `settings.json.graphify-bak`; an identical result is not rewritten. [SRC:graphify/install.py:L1085] [SRC:graphify/install.py:L1097]

## The PreToolUse guard

`graphify hook-guard search|read [--strict]` reads the tool call JSON on stdin and always exits 0. [SRC:graphify/cli.py:L2855] [SRC:graphify/cli.py:L1089]

- **search** (Bash and Grep): when the configured graph.json exists (`graphify-out/graph.json` by default, or under `GRAPHIFY_OUT`) and the Bash command really runs a search tool, or the call is the Grep tool, it may print a nudge toward `graphify query`. [SRC:graphify/cli.py:L1144]
- **read** (Read and Glob): only for the fixed extension list in `_HOOK_SOURCE_EXTS` (common code types such as `.py`, `.js`/`.ts`/`.tsx`, `.go`, `.rs`, `.java`, `.c`/`.cpp`, `.cs`, `.php`, `.lua` and PowerShell `.ps1`/`.psm1`/`.psd1`, plus `.sh`, `.md`, `.rst`, `.txt` and `.mdx`), for targets inside the project (`CLAUDE_PROJECT_DIR` or the cwd), and never for files under the output folder. Other code types graphify extracts, such as `.sql`, `.tf`, `.json`, `.dart`, `.zig` or `.mjs`, get no read nudge and no strict deny. A target newer than graph.json, or a `needs_update` flag, softens it to a stale-graph nudge. [SRC:graphify/cli.py:L72-L77] [SRC:graphify/detect.py:L48] [SRC:graphify/cli.py:L1155] [SRC:graphify/cli.py:L1255]
- Every nudge is budgeted per agent (the session id, plus `agent_id` for subagents). The first one always fires. Later ones are suppressed while a query, explain or path ran within `GRAPHIFY_HOOK_STRICT_TTL` seconds (1800 by default), and at most `GRAPHIFY_HOOK_NUDGE_CAP` are sent (default 5; 0 or a non-number disables the cap). A call without a session id is suppressed only by that fresh stamp. [SRC:graphify/cli.py:L927]
- **strict**: at most once per session id, a raw Read (tool_name `Read` or absent) of an in-project file is denied through `hookSpecificOutput.permissionDecision: "deny"`, never through the exit code. The file must be one the graph indexes (or one the manifest cannot rule out) and not stale. The deny happens only when no query, explain or path ran within `GRAPHIFY_HOOK_STRICT_TTL` seconds (1800 by default), and a call without a session id is never denied. Other reads get the budgeted nudge. `GRAPHIFY_HOOK_STRICT` set to `1`, `true`, `yes` or `on` forces strict on without reinstalling, and `0`, `false`, `no` or `off` turns it off. [SRC:graphify/cli.py:L1262] [SRC:graphify/cli.py:L994] [SRC:graphify/cli.py:L916] [SRC:graphify/cli.py:L892]
- Any error prints nothing and exits 0, so a legitimate tool call is never blocked by a guard bug. [SRC:graphify/cli.py:L1089]

## Uninstalling

- `graphify claude uninstall` strips the `## graphify` section from `CLAUDE.md`, `CLAUDE.local.md` and `.claude/CLAUDE.local.md`, removes the graphify hooks from `.claude/settings.json` and `.claude/settings.local.json`, and also removes the user-global skill. With `--project` it removes the project skill instead of the user-global one, and also strips the `# graphify` skill-registration block from `./.claude/CLAUDE.md`. No uninstaller removes the user-scope `# graphify` registration that `graphify install` writes to `~/.claude/CLAUDE.md` (or `$CLAUDE_CONFIG_DIR/CLAUDE.md`), so delete that block by hand. [AST:graphify/install.py:L2291] [SRC:graphify/install.py:L2188] [SRC:graphify/install.py:L2593] [SRC:graphify/install.py:L2022] [SRC:graphify/install.py:L409] [SRC:graphify/install.py:L959]
- `graphify uninstall` runs a fixed set of removals: claude, codebuddy and gemini (each with its user-global skill), vscode (whose `~/.copilot/skills/graphify/` folder is also the copilot user-scope skill), cursor, kiro, antigravity, the AGENTS.md section, the amp and agents user-scope skills, the opencode plugin and the codex hook. It then removes the git hooks, ignoring any error, such as being outside a repo. It does not run the kilo, devin or pi uninstallers, so their user-scope skills (and kilo's `~/.config/kilo/command/graphify.md`) remain; run `graphify <platform> uninstall` for those. The user-scope skills that `graphify install --platform P` writes for codex, opencode, aider, claw, droid, trae, trae-cn, hermes, kiro or kimi (such as `~/.codex/skills/graphify/`, `~/.config/opencode/skills/graphify/` or `~/.hermes/skills/graphify/`) also stay, and no uninstaller removes them: `graphify <platform> uninstall` for those platforms only strips `AGENTS.md` (plus the codex hook or the opencode plugin), `graphify kiro uninstall` removes only the project skill, and kimi has no command of its own. Delete those folders by hand. `--purge` then deletes the output folder, unless it would delete the project, a parent of it, the home folder or a filesystem root (exit 1, nothing changed). [AST:graphify/install.py:L2236] [SRC:graphify/install.py:L2255] [SRC:graphify/install.py:L2274] [SRC:graphify/install.py:L1173] [SRC:graphify/install.py:L938] [SRC:graphify/install.py:L203-L215] [SRC:graphify/install.py:L247] [SRC:graphify/install.py:L2747-L2760] [SRC:graphify/install.py:L1313] [SRC:graphify/install.py:L2217]

## Git hooks

`graphify hook install` finds the nearest git repo (else `RuntimeError`) and asks git for the hooks folder (`git rev-parse --git-path hooks`). It honours `core.hooksPath` only when that resolves inside the repo or to git's own hooks dir. Any other `core.hooksPath` is refused with a `[graphify hooks] refusing hooks path ...` warning on stderr, and the default git hooks dir is used instead. It uses `.husky/` rather than Husky's `.husky/_`. In each hook file it updates an existing marked block in place, or appends one (a new file starts with `#!/bin/sh` and is made executable). [AST:graphify/hooks.py:L1093] [SRC:graphify/hooks.py:L797] [SRC:graphify/hooks.py:L785] [SRC:graphify/hooks.py:L840] [SRC:graphify/hooks.py:L1080] [SRC:graphify/hooks.py:L857]

| Hook | Runs when | Rebuild |
|------|-----------|---------|
| post-commit | after a commit; skipped during a rebase or merge, in a linked worktree, with `GRAPHIFY_SKIP_HOOK=1`, when nothing changed or only output-folder files changed, and on every step but the last of a multi-commit cherry-pick or revert | the files in `git diff --name-only HEAD~1 HEAD` (`git diff --name-only HEAD` on a root commit); on the last step of a cherry-pick or revert range, `git diff --name-only <sequencer/head> HEAD` (changed-paths rebuild) [SRC:graphify/hooks.py:L425] [SRC:graphify/hooks.py:L459] [SRC:graphify/hooks.py:L487] [SRC:graphify/hooks.py:L489] [SRC:graphify/hooks.py:L504] |
| post-checkout | a branch switch to a different HEAD, when the output folder exists | full corpus [SRC:graphify/hooks.py:L550] [SRC:graphify/hooks.py:L559] |
| post-merge | after a merge, when a folder named literally `graphify-out` exists | full corpus [SRC:graphify/hooks.py:L592] [SRC:graphify/hooks.py:L617] |
| post-rewrite | after `rebase` (including `git pull --rebase`), not after `amend` | full corpus [SRC:graphify/hooks.py:L645] [SRC:graphify/hooks.py:L671] |

- Every block runs in a subshell, so its `exit 0` skips end only graphify's part of the hook. [SRC:graphify/hooks.py:L422]
- The rebuild runs detached, with `PYTHONHASHSEED=0`, logging to `~/.cache/graphify-rebuild.log`, and is killed after `GRAPHIFY_REBUILD_TIMEOUT` seconds (600 by default). [SRC:graphify/hooks.py:L433] [SRC:graphify/hooks.py:L521] [SRC:graphify/hooks.py:L201]
- Every hook rebuild (the post-commit body and the shared post-checkout, post-merge and post-rewrite body) passes `GRAPHIFY_FORCE` through as `force`, and then refreshes `reflections/LESSONS.md` when `memory/` holds `*.md` notes. [SRC:graphify/hooks.py:L226] [SRC:graphify/hooks.py:L247-L256] [SRC:graphify/hooks.py:L298] [SRC:graphify/hooks.py:L322-L331]
- The merge driver is registered through `git config` (`merge.graphify.name`, `merge.graphify.driver` = `graphify merge-driver %O %A %B`, or the pinned Python form) and a `.gitattributes` line `graphify-out/graph.json merge=graphify`. [SRC:graphify/hooks.py:L980] [SRC:graphify/hooks.py:L965]
- `graphify hook status` reports each hook as `installed`, `installed (out of date: ...)`, `not installed` or `not installed (hook exists but graphify not found)`, plus the merge driver and the `.graphifyrc` viz limit. [AST:graphify/hooks.py:L1174]

## The MCP server

```bash
graphify-mcp                                  # stdio, graphify-out/graph.json
graphify-mcp path/to/graph.json               # or --graph PATH
graphify-mcp --transport http --host 127.0.0.1 --port 8080 --path /mcp --api-key "$GRAPHIFY_API_KEY"
```

[SRC:graphify/serve.py:L2959] [SRC:graphify/serve.py:L2984]

- Flags: `--transport stdio|http` (default stdio), `--host` (127.0.0.1), `--port` (8080), `--api-key` (default from `GRAPHIFY_API_KEY`), `--path` (`/mcp`), `--json-response`, `--stateless`, `--session-timeout` (3600 s; 0 disables). [AST:graphify/serve.py:L2901] [SRC:graphify/serve.py:L2997]
- Both transports need `graphifyy[mcp]`. Over stdio, a missing `mcp` raises `ImportError: mcp not installed. Run: pip install "graphifyy[mcp]"`. Over HTTP, a missing `uvicorn`, `starlette` or `mcp` raises `ImportError: HTTP transport needs the mcp extra (mcp + starlette + uvicorn). Run: pip install "graphifyy[mcp]"`. [AST:graphify/serve.py:L2743] [SRC:graphify/serve.py:L2749] [SRC:graphify/serve.py:L2927] [SRC:graphify/serve.py:L2850] [SRC:pyproject.toml:L68]
- With an API key, HTTP requests need `Authorization: Bearer {key}` or `X-API-Key: {key}`; anything else gets 401. Binding `0.0.0.0` without a key prints a warning. [SRC:graphify/serve.py:L2797] [SRC:graphify/serve.py:L2808] [SRC:graphify/serve.py:L2952]
- Tools: `query_graph`, `get_node`, `get_neighbors`, `get_community`, `god_nodes`, `graph_stats`, `shortest_path`, `list_prs`, `get_pr_impact`, `triage_prs`. [SRC:graphify/serve.py:L2203] [SRC:graphify/serve.py:L2322]

## Temporal context

- T2-future: #3280 (open). The PreToolUse hook has no fail-open guard at the shell level, and `shutil.which` can return an unrunnable shim on a hardened Windows machine, failing every matching tool call. [QMD:graphify-kg-temporal:targeted-issues.md]
- T2-past: #4360 (closed 2026-10-12, before 0.9.92). `install` and `uninstall` no longer rewrite the line endings of CLAUDE.md, AGENTS.md and related files. [QMD:graphify-kg-temporal:issues.md]
- T2-future: #4545 (open, filed against 0.9.92). `--version` and `--help` run the skill refresh, which can rewrite installed skill files. [QMD:graphify-kg-temporal:issues.md]
- T2-past: 0.9.92 makes post-merge rebuild after a real merge commit and adds the post-rewrite hook (#4463, #4476, #4490, #4491). Re-run `graphify hook install` on repos with older hook blocks; `hook status` reports them as out of date. [QMD:graphify-kg-temporal:changelog.md] [AST:graphify/hooks.py:L1174]
