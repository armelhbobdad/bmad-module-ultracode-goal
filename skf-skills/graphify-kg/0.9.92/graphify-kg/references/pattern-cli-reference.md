# Pattern: the graphify CLI, command by command

## Contents

- [How a command is dispatched](#how-a-command-is-dispatched)
- [Build and refresh commands](#build-and-refresh-commands)
- [Query commands](#query-commands)
- [Graph tools and exports](#graph-tools-and-exports)
- [Integration commands](#integration-commands)
- [Internal commands](#internal-commands)
- [Exit code summary](#exit-code-summary)
- [Temporal context](#temporal-context)

## How a command is dispatched

1. `graphify -v`, `--version` or `version` prints `graphify 0.9.92` and returns, after the stale-skill refresh has run. [SRC:graphify/__main__.py:L846] [SRC:graphify/__main__.py:L838]
2. No argument, `-h`, `--help` or `-?` prints the usage list. [SRC:graphify/__main__.py:L852]
3. `-h`, `--help` or `-?` as an exact token after the command prints `Run 'graphify --help' for full usage.` and returns with exit 0 without dispatching the command. The exceptions are `query`, `explain`, `path`, `save-result`, `install` and `uninstall`, whose arguments can contain those tokens. The stale-skill refresh and the version check have already run by then, unless an argv token is `install`, `uninstall`, `hook-check` or `hook-guard`. [SRC:graphify/__main__.py:L833-L844] [SRC:graphify/__main__.py:L1080-L1083]
4. `install.dispatch_install_cli(cmd)` handles `install`, `uninstall` and every per-platform `install`/`uninstall` pair. Everything else goes to `cli.dispatch_command(cmd)`. [AST:graphify/install.py:L2489] [AST:graphify/cli.py:L1393]
5. A first argument that is an existing path, `.`, `..`, or starts with `./`, `../`, `/` or `~` becomes `graphify extract {path}`. [SRC:graphify/cli.py:L5381]
6. Anything else prints `error: unknown command '{cmd}'` and exits 1. [SRC:graphify/cli.py:L5389]

## Build and refresh commands

| Command | Flags | Exit codes |
|---------|-------|------------|
| `extract {path}` | `--backend B`, `--model M`, `--mode deep`, `--force` (or `GRAPHIFY_FORCE=1`), `--max-workers N`, `--token-budget N`, `--max-concurrency N`, `--api-timeout S`, `--out DIR` / `--output DIR`, `--google-workspace`, `--no-gitignore`, `--no-cluster`, `--code-only`, `--postgres DSN`, `--cargo`, `--global`, `--as TAG` [SRC:graphify/__main__.py:L952] | 0; 1 (path missing, unknown backend, no LLM key, refused write, failed AST or semantic pass, empty graph, or a non-numeric `--exclude-hubs`, which raises an uncaught ValueError); 2 (an invalid or non-positive `--max-workers`, `--token-budget`, `--max-concurrency`, `--api-timeout` or `--resolution`; `--no-dedup` with `--dedup-llm`; an unknown `--mode`; or, with the ollama backend, an `OLLAMA_BASE_URL` rejected as link-local or metadata) [SRC:graphify/cli.py:L3709-L3729] [SRC:graphify/cli.py:L3791] [SRC:graphify/cli.py:L3828] [SRC:graphify/cli.py:L3837] [SRC:graphify/cli.py:L4161] [SRC:graphify/cli.py:L4191] |
| `update [path]` | `--force`, `--no-cluster` [SRC:graphify/__main__.py:L890] | 0; 1; 2 (see `pattern-update-refresh.md`) [SRC:graphify/cli.py:L2793] |
| `watch [path]` | none; the CLI calls `_watch(watch_path)` without a debounce argument, so the 3.0 s default always applies [SRC:graphify/cli.py:L2339] [SRC:graphify/watch.py:L2746] | 1 when the path is missing or watchdog is absent; otherwise runs until Ctrl+C [SRC:graphify/cli.py:L2339] |
| `check-update {path}` | none [SRC:graphify/__main__.py:L944] | 1 without a path; else 0, cron-safe, even when the flag is set [SRC:graphify/cli.py:L2859] [SRC:graphify/cli.py:L2863] |
| `cluster-only [path]` | `--no-viz`, `--graph PATH`, `--no-label`, `--backend=`, `--model=`, `--max-concurrency=N`, `--batch-size=N` [SRC:graphify/__main__.py:L894] | 0; 1 (no graph, `to_json` refused) [SRC:graphify/cli.py:L2691] |
| `label [path]` | `--missing-only`, `--backend=`, `--model=`, `--max-concurrency=N`, `--batch-size=N` [SRC:graphify/__main__.py:L902] | 0; 1 [SRC:graphify/cli.py:L2691] |
| `add {url}` | `--author`, `--contributor`, `--dir` [SRC:graphify/__main__.py:L885] | 0; 1 |
| `clone {github-url}` | `--branch`, `--out` [SRC:graphify/__main__.py:L876] | 0; 1 |

`extract` also parses `--exclude`, `--allow-partial`, `--allow-dedup-shrink`, `--dedup-llm`, `--no-dedup`, `--resolution`, `--exclude-hubs` and `--timing`, none of which `graphify --help` lists. [SRC:graphify/cli.py:L3756-L3812] [SRC:graphify/__main__.py:L952]

`--exclude` and `--no-gitignore` persist in `graphify-out/.graphify_build.json`: an explicit `--exclude` list replaces the saved one, and a later run without `--no-gitignore` keeps the saved `false`. [SRC:graphify/cli.py:L3869]

`extract` refuses two kinds of shrink: a dedup that would shrink the existing graph (`Pass --allow-dedup-shrink to write the smaller graph.`), and an incomplete extraction whose result is smaller (`... or pass --allow-partial to overwrite anyway.`). Both exit 1. [SRC:graphify/cli.py:L5089] [SRC:graphify/cli.py:L5115]

`cluster-only` and `label` call `to_json` without force, so the export guard (#479) can refuse. They then print `graph.json NOT written: refusing to overwrite ...`, leave the report and label files untouched, and exit 1. [SRC:graphify/cli.py:L2680] [AST:graphify/export.py:L287]

## Query commands

| Command | Flags | Exit codes |
|---------|-------|------------|
| `query "Q"` | `--dfs`, `--context C` (repeatable), `--seed X` (repeatable), `--budget N` (default 2000), `--graph PATH` [SRC:graphify/__main__.py:L908] | 0; 1 (usage, missing or oversized graph); 4 no node matches [SRC:graphify/cli.py:L1668] |
| `path "A" "B"` | `--graph PATH`, `--directed` (default), `--undirected` [SRC:graphify/__main__.py:L858] | 0, also for "No path found"; 1 usage; 3 ambiguous or both ends on one node; 4 no match [SRC:graphify/cli.py:L1962] [SRC:graphify/cli.py:L1972] [SRC:graphify/cli.py:L2032] |
| `explain "X"` | `--all`, `--graph PATH` [SRC:graphify/__main__.py:L863] | 0; 1; 3 ambiguous; 4 no match [SRC:graphify/cli.py:L2106] |
| `affected "X"` | `--relation R` (repeatable), `--depth N` (default 2), `--graph PATH` [SRC:graphify/__main__.py:L917] | 0; 1 |
| `god-nodes` | `--top N` (default 10), `--graph PATH`, `--json` [SRC:graphify/__main__.py:L921] | 0; 1 |
| `save-result` | `--question`, `--answer`, `--answer-file`, `--type`, `--nodes`, `--outcome`, `--correction`, `--memory-dir` [SRC:graphify/__main__.py:L926] [SRC:graphify/cli.py:L1815] | 0; 1 (an uncaught error, such as an unreadable `--answer-file`); 2 (an argparse usage error: missing `--question`, neither `--answer` nor `--answer-file`, an invalid `--outcome`, or an unknown option) [SRC:graphify/cli.py:L1812-L1825] |
| `reflect` | `--memory-dir`, `--out`, `--graph`, `--analysis`, `--labels`, `--half-life-days`, `--min-corroboration`, `--if-stale` [SRC:graphify/__main__.py:L936] [SRC:graphify/cli.py:L1854] | 0; 2 on an argparse usage error (an unknown option, or a non-numeric `--half-life-days` or `--min-corroboration`). The branch has no explicit exit 1; only an uncaught exception inside reflect() would exit 1 [SRC:graphify/cli.py:L1841-L1857] |

The help line `query, path and explain exit 0 with an answer, 3 when a name is ambiguous ..., 4 when no node matches` holds for `path` and `explain`. The `query` branch itself exits only with 4 (`EXIT_NOT_FOUND`) on a no-match. [SRC:graphify/__main__.py:L915] [SRC:graphify/cli.py:L90] [SRC:graphify/cli.py:L91]

`query`, `path` and `explain` write a query log only when `GRAPHIFY_QUERY_LOG=<path>` or `GRAPHIFY_QUERY_LOG_ENABLE=1` is set. `GRAPHIFY_QUERY_LOG_DISABLE=1` always wins. [SRC:graphify/querylog.py:L15]

## Graph tools and exports

| Command | Notes | Exit codes |
|---------|-------|------------|
| `diagnose multigraph` | `--graph`, `--json`, `--max-examples N`, `--directed`/`--undirected`, `--extract-path` [SRC:graphify/__main__.py:L866] | 0; 1 |
| `merge-graphs {g1} {g2} ...` | `--out` (default `graphify-out/merged-graph.json`), `--previous` [SRC:graphify/__main__.py:L878] | 0; 1 |
| `merge-driver {base} {current} {other}` | the git merge driver `hook install` registers [SRC:graphify/__main__.py:L877] | 0; 1 |
| `tree` | `--graph`, `--output` (default `GRAPH_TREE.html` next to the graph file: `graphify-out/GRAPH_TREE.html` for the default graph, else `<dir of --graph>/GRAPH_TREE.html`), `--root`, `--max-children`, `--top-k-edges`, `--label` [SRC:graphify/__main__.py:L945] [SRC:graphify/cli.py:L2909-L2910] | 0; 1 |
| `export html, callflow-html, obsidian, wiki, svg, graphml, neo4j, falkordb` | `--graph`, `--labels` and per-format options; `NEO4J_PASSWORD` / `FALKORDB_PASSWORD` keep a password off argv [SRC:graphify/__main__.py:L985] [SRC:graphify/__main__.py:L993] | 0; 1 |
| `global add, remove, list, path` | the cross-project graph at `~/.graphify/global-graph.json` [SRC:graphify/__main__.py:L979] | 0; 1 |
| `benchmark [graph.json]` | token comparison [SRC:graphify/__main__.py:L984] | 1 for an oversized graph; no other explicit exit [SRC:graphify/cli.py:L3559] |
| `prs` | PR dashboard, handled by `graphify.prs.cmd_prs` (outside this skill's scope) [SRC:graphify/__main__.py:L925] | set by `cmd_prs` [SRC:graphify/cli.py:L1511] |
| `provider list, show, add, remove` | custom LLM providers [SRC:graphify/__main__.py:L978] | 0; 1 |

## Integration commands

| Command | Writes | Exit codes |
|---------|--------|------------|
| `install [P]` (`--platform P`, `--project`, `--strict`) | the platform skill; for `claude`, also the CLAUDE.md registration; `--project --strict` also strict hooks. The default platform is `windows` on Windows, else `claude` [SRC:graphify/install.py:L2499] | 0; 1 (unknown option, platform given twice, unknown platform) [AST:graphify/install.py:L917] |
| `uninstall` (`--purge`, `--project`, `--platform P`) | Without `--project`, it runs a fixed set of platform uninstallers (kilo, devin and pi are not among them) and removes the git hooks. `--purge` also deletes the output dir (`graphify-out/` or `GRAPHIFY_OUT`). `--platform P` is ignored in this mode. With `--project`, it removes only project-scoped files (for P if given, else for every platform), leaves the git hooks in place and ignores `--purge` [SRC:graphify/install.py:L2553-L2584] [SRC:graphify/install.py:L2054] [SRC:graphify/install.py:L2236-L2290] | 0; 1 (unsafe purge target: the project, home, a parent of either, or a filesystem root; unknown option; `--platform` without a value) [SRC:graphify/install.py:L2217] [SRC:graphify/install.py:L2566-L2574] |
| `claude install, uninstall` (`--strict`, `--project`) | `./CLAUDE.md` section and `./.claude/settings.json` PreToolUse hooks [SRC:graphify/__main__.py:L1006] | 0; 1 (usage, unparseable settings.json) [SRC:graphify/install.py:L2599] [SRC:graphify/install.py:L1058] |
| `hook install, uninstall, status` | git hooks and the merge driver [SRC:graphify/__main__.py:L997] | 0; 1 usage [SRC:graphify/cli.py:L1530]; an `install` or `uninstall` outside a git repo raises `RuntimeError` [AST:graphify/hooks.py:L1093] |
| other platforms (`codex`, `gemini`, `cursor`, `codebuddy`, `opencode`, `kilo`, `aider`, `copilot`, `vscode`, `claw`, `droid`, `trae`, `trae-cn`, `antigravity`, `hermes`, `kiro`, `pi`, `devin`, `amp`, `agents`) | each `install`/`uninstall`; a missing or unknown sub-command prints a usage line [SRC:graphify/__main__.py:L1010] | 0; 1 (missing or unknown sub-command; `pi guard` with no `pi` on PATH). `graphify pi guard install\|uninstall` exits with Pi's own non-zero return code when `pi install` / `pi remove` fails [AST:graphify/install.py:L2489] [SRC:graphify/install.py:L2699-L2716] |

`graphify-mcp` is a separate console script; `graphify` has no `serve` command. See `pattern-claude-code-integration.md`. [SRC:pyproject.toml:L130]

## Internal commands

- `hook-check`: a no-op that always exits 0. Installed Codex hooks call it. [SRC:graphify/cli.py:L2843]
- `hook-guard search|read [--strict]` is the Claude Code / CodeBuddy PreToolUse guard. It prints a JSON nudge or nothing. With `read --strict` (or `GRAPHIFY_HOOK_STRICT` set to `1`, `true`, `yes` or `on`), it denies at most one raw Read per session id through `permissionDecision: deny`: only for an indexed in-project file that is not stale, only when no query, explain or path ran within `GRAPHIFY_HOOK_STRICT_TTL` seconds (1800 by default), and never for a call without a session id. `search` stays nudge-only. `hook-guard gemini` is the Gemini CLI BeforeTool hook: it always prints `{"decision":"allow"}`, with `additionalContext` added when graph.json exists. Every kind exits 0. [SRC:graphify/cli.py:L1089-L1271] [SRC:graphify/cli.py:L1262-L1265] [SRC:graphify/cli.py:L994] [SRC:graphify/cli.py:L916] [SRC:graphify/cli.py:L892] [SRC:graphify/cli.py:L2855] [SRC:graphify/install.py:L1013]
- `cache-check {files_from}`, `merge-chunks {chunks...} --out {path}` and `merge-semantic --cached {p} --new {p} --out {p}`: helpers for the semantic pass (semantic cache lookup, merging `.graphify_chunk_*.json` files, merging cached with fresh results). They are not in `--help`. Each exits 1 on a usage error (missing arguments or `--out`). merge-chunks skips invalid chunks with a warning and exits 1 only when no chunk is valid. merge-semantic treats a missing `--cached` or `--new` file as empty and exits 0. cache-check exits 1 with an uncaught error when `files_from` does not exist. [SRC:graphify/cli.py:L5198] [SRC:graphify/cli.py:L5213-L5216] [SRC:graphify/cli.py:L5243] [SRC:graphify/cli.py:L5258] [SRC:graphify/cli.py:L5276-L5278] [SRC:graphify/cli.py:L5319-L5325] [SRC:graphify/cli.py:L5339] [SRC:graphify/cli.py:L5359-L5364]

## Exit code summary

| Code | Meaning |
|------|---------|
| 0 | done, including "no changes" and `path`'s "No path found" |
| 1 | usage error (except save-result and reflect, which use argparse), missing path or graph, refused write, failed rebuild, unknown command |
| 2 | `update`: unknown option or second path; `extract`: an invalid or non-positive `--max-workers`, `--token-budget`, `--max-concurrency`, `--api-timeout` or `--resolution` (a non-numeric `--exclude-hubs` exits 1 instead), `--no-dedup` with `--dedup-llm`, unknown `--mode`, or an OLLAMA_BASE_URL rejected for the ollama backend; any argparse usage error in `save-result` or `reflect` [SRC:graphify/cli.py:L2793] [SRC:graphify/cli.py:L3714] [SRC:graphify/cli.py:L3791] [SRC:graphify/cli.py:L3828] [SRC:graphify/cli.py:L4191] [SRC:graphify/cli.py:L1812] [SRC:graphify/cli.py:L1841] |
| 3 | `path` / `explain`: ambiguous name (`EXIT_AMBIGUOUS`) [SRC:graphify/cli.py:L90] |
| 4 | `query` / `path` / `explain`: no node matches (`EXIT_NOT_FOUND`) [SRC:graphify/cli.py:L91] |

`graphify pi guard install|uninstall` passes Pi's own non-zero exit code through. [SRC:graphify/install.py:L2713]

A closed stdout pipe is treated as success: `main()` catches `BrokenPipeError` and exits 0. [AST:graphify/__main__.py:L798]

## Temporal context

- T2-past: #3140 (closed). `graphify --help` used to omit 14 working command paths in `dispatch_command`. Some are still unlisted at 0.9.92, for example `hook-guard`, `cache-check` and the extra `extract` flags. [QMD:graphify-kg-temporal:targeted-issues.md]
- T2-future: #2404 (open). The help guard hides per-subcommand `--help` handlers. [QMD:graphify-kg-temporal:targeted-issues.md]
- T2-past: PR #1737 (merged 2026-07-08) split `__main__.py` into `install.py` (`dispatch_install_cli`) and `cli.py` (`dispatch_command`). [QMD:graphify-kg-temporal:prs.md]
- T2-future: #3061 (open). `graphify watch` has no `--debounce` flag at 0.9.92. As the first argument it is taken as the path and fails with `error: path not found: --debounce` (exit 1). After a path it is silently ignored and the 3.0 s default stays. Only `python -m graphify.watch --debounce N` honours it. [QMD:graphify-kg-temporal:targeted-issues.md] [SRC:graphify/cli.py:L2332-L2339] [SRC:graphify/watch.py:L2746] [SRC:graphify/watch.py:L2859]
