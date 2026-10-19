---
name: graphify-kg
description: >
  Graphify v0.9.92 knowledge-graph CLI (PyPI package graphifyy; console scripts graphify and
  graphify-mcp): the update refresh and its shrink guard, every subcommand's flags and exit codes,
  the graphify-out/ layout and formats, the ignore rules, and what graphify install and graphify
  claude install write. Use when running or debugging the UltraCode Goal Finalize refresh
  (graphify update .), reading graph.json or GRAPH_REPORT.md, or wiring graphify's Claude Code
  skill, CLAUDE.md blocks, git hooks or MCP server into a project. Not for graphify's extraction
  internals (the extract, cache, build and llm modules).
---

# graphify v0.9.92 — the CLI, the update refresh and the integrations

## Overview

graphify turns a folder into a knowledge graph under `graphify-out/`. This skill documents the CLI surface of release 0.9.92 (PyPI `graphifyy`), read at tag `v0.9.92`, commit `86c57be8`, from https://github.com/Graphify-Labs/graphify. [SRC:pyproject.toml:L6] [SRC:pyproject.toml:L7]

- Two console scripts: `graphify` runs `graphify.__main__:main`, and `graphify-mcp` runs `graphify.serve:_main`. [SRC:pyproject.toml:L129] [SRC:pyproject.toml:L130]
- Compiled at the Deep tier from 14 Python files (77 AST-verified definitions, all T1) plus the packaged skill, the CLAUDE.md block, the README, ARCHITECTURE.md and docs/how-it-works.md. T2 notes come from the issue tracker, the PRs and the changelog.
- Not read for this skill: `graphify/extract.py`, `graphify/cache.py`, `graphify/build.py` and `graphify/llm.py`. Where a behaviour depends on one of them, the skill names the call and stops there.
- Facts here are 0.9.92 facts. A note written against an older graphify (for example 0.9.26) may differ, and this skill wins for 0.9.92.

## Quick Start

```bash
uv tool install graphifyy     # the package is graphifyy, the command is graphify
graphify --version            # prints "graphify 0.9.92"
graphify update .             # re-extract the code layer, rebuild graph.json and GRAPH_REPORT.md
echo $?                       # 0 updated or unchanged, 1 refused or failed, 2 bad arguments
graphify update . --force     # write a smaller graph the shrink guard refused
```

[SRC:README.md:L53] [SRC:graphify/__main__.py:L846] [SRC:graphify/cli.py:L2779]

- `update` accepts `--force`, `--no-cluster` and one optional path. An exact `-h`, `--help` or `-?` token after `update` is caught first by the universal help guard in `__main__`: it prints `Run 'graphify --help' for full usage.`, exits 0 and does not rebuild. Any other `-`-prefixed token exits 2 (`error: unknown update option: X`), and so does a second path (`error: update accepts at most one path argument`). A path that does not exist exits 1. `GRAPHIFY_FORCE=1` (also `true` or `yes`) is the same as `--force`. [SRC:graphify/__main__.py:L1081] [SRC:graphify/cli.py:L2780] [SRC:graphify/cli.py:L2793] [SRC:graphify/cli.py:L2796] [SRC:graphify/cli.py:L2814]
- With no path, `update` reads the scan root from `graphify-out/.graphify_root`, which the last build wrote, and falls back to `.`. [SRC:graphify/cli.py:L2803]
- The CLI waits on the per-repo rebuild lock (`block_on_lock=True`) rather than skipping when a hook rebuild is already running. [SRC:graphify/cli.py:L2821]
- When the rebuild returns False, the CLI prints `Nothing to update or rebuild failed — check output above.` to stderr and exits 1. [SRC:graphify/cli.py:L2834] [SRC:graphify/cli.py:L2837]
- The stale-skill refresh is skipped whenever any argv token equals `install`, `uninstall`, `hook-check` or `hook-guard`, so per-platform commands such as `claude install`, `hook install` and `cursor uninstall` skip it too. Other commands, `update` and `--version` among them, run it first. It re-copies only single-writer, non-vscode user-scope skill directories whose `.graphify_version` stamp is older than the package; project-scope copies are never refreshed. `GRAPHIFY_NO_AUTO_REFRESH` set to `1`, `true` or `yes` turns it off. [SRC:graphify/__main__.py:L833] [SRC:graphify/__main__.py:L834] [SRC:graphify/__main__.py:L838] [SRC:graphify/__main__.py:L294] [SRC:graphify/__main__.py:L307] [SRC:graphify/__main__.py:L321]

<!-- [MANUAL:additional-notes] -->
<!-- Add custom notes here. This section is preserved during skill updates. -->
<!-- [/MANUAL:additional-notes] -->

## Adoption Steps

1. **Build once.** `graphify .` is rewritten to `graphify extract .`, the full pipeline (AST plus the LLM semantic pass for docs, papers and images). `--code-only` indexes code with the local AST and needs no API key. [SRC:graphify/cli.py:L5381] [SRC:graphify/__main__.py:L952] [SRC:graphify/__main__.py:L971]
   ```bash
   graphify . --code-only
   ```
2. **Refresh after code changes.** `graphify update .` runs `watch._rebuild_code` on the full corpus: AST extraction, build, clustering, report, and the shrink check. The help text and the function's docstring both say no LLM is needed. [SRC:graphify/__main__.py:L890] [SRC:graphify/watch.py:L1677]
   ```bash
   timeout 300 graphify update . || echo "graphify-refresh-failed: $?"
   ```
3. **Decide on a refusal.** A refusal leaves graph.json as it was and prints one of two warnings to stderr. For an unexplained node loss it prints `[graphify] WARNING: new graph has N nodes but existing graph.json has M. Refusing to overwrite — you may be missing chunk files from a previous session. Pass --force to override.` When a saved semantic node vanished, even if the node count did not drop, it prints `[graphify] WARNING: Refusing to overwrite — saved semantic node(s) are missing from the new graph: <ids>.` The N/M line follows that one only when the graph also shrank. Re-run with `--force` only when the loss is intended. `--force` never overrides an unreadable or oversized existing graph. [SRC:graphify/watch.py:L1508] [SRC:graphify/watch.py:L1512] [SRC:graphify/watch.py:L1540] [SRC:graphify/watch.py:L2196]
4. **Keep the corpus stable.** Exclusions belong in `.graphifyignore`, which every rebuild re-applies. `--exclude` and `--no-gitignore` given to `extract` persist in `graphify-out/.graphify_build.json`, and `update` re-reads them. [SRC:graphify/detect.py:L1463] [SRC:graphify/watch.py:L106] [SRC:graphify/watch.py:L1789]
5. **Wire Claude Code.** `graphify install` copies the skill to `~/.claude/skills/graphify/` and registers it in `~/.claude/CLAUDE.md`. `graphify claude install` writes a `## graphify` section to `./CLAUDE.md` and PreToolUse hooks to `./.claude/settings.json`. [AST:graphify/install.py:L917] [AST:graphify/install.py:L2136]
6. **Rebuild on git events.** `graphify hook install` adds post-commit, post-checkout, post-merge and post-rewrite blocks and registers a `graph.json` merge driver. [AST:graphify/hooks.py:L1093]
7. **Serve the graph over MCP.** Run `graphify-mcp` for stdio, or `graphify-mcp --transport http --port 8080` for Streamable HTTP. [AST:graphify/serve.py:L2743] [AST:graphify/serve.py:L2901]

## Pattern Surface

| # | File | Surface | Purpose |
|---|------|---------|---------|
| 1 | `pyproject.toml` | `[project.scripts]` | `graphify` and `graphify-mcp` console scripts [SRC:pyproject.toml:L128] |
| 2 | `graphify/__main__.py` | `main()` | hash-seed re-exec, stale-skill refresh, help, dispatch [AST:graphify/__main__.py:L798] |
| 3 | `graphify/cli.py` | `dispatch_command("update")` | flags, `.graphify_root` recovery, exit codes 0/1/2 [AST:graphify/cli.py:L1393] |
| 4 | `graphify/watch.py` | `_rebuild_code()` | lock, detect, extract, reconcile, cluster, write [SRC:graphify/watch.py:L1677] |
| 5 | `graphify/watch.py` | `_check_shrink()` | the only shrink refusal on the update path [SRC:graphify/watch.py:L1449] |
| 6 | `graphify/export.py` | `to_json()`, `backup_if_protected()` | graph.json writer, dated backups [AST:graphify/export.py:L287] [AST:graphify/export.py:L42] |
| 7 | `graphify/security.py` | `check_graph_file_size_cap()` | 512 MiB graph cap, `GRAPHIFY_MAX_GRAPH_BYTES` [AST:graphify/security.py:L357] |
| 8 | `graphify/detect.py` | `detect()`, `ignored_predicate()` | corpus scan and ignore rules [AST:graphify/detect.py:L1921] [AST:graphify/detect.py:L1809] |
| 9 | `graphify/rcfile.py` | `.graphifyrc` | `viz_node_limit`, `language.{ext}` overrides [AST:graphify/rcfile.py:L112] |
| 10 | `graphify/paths.py` | `GRAPHIFY_OUT` | output directory name or path [SRC:graphify/paths.py:L53] |
| 11 | `graphify/report.py` | `generate()` | GRAPH_REPORT.md sections [AST:graphify/report.py:L96] |
| 12 | `graphify/install.py` | `install()`, `claude_install()` | skill copy, CLAUDE.md blocks, PreToolUse hooks [AST:graphify/install.py:L917] [AST:graphify/install.py:L2136] |
| 13 | `graphify/hooks.py` | `install()`, `status()` | git hooks and the merge driver [AST:graphify/hooks.py:L1093] [AST:graphify/hooks.py:L1174] |
| 14 | `graphify/serve.py` | `_main()` | MCP server, stdio or Streamable HTTP [SRC:graphify/serve.py:L2959] |

## Migration & Deprecation Warnings

- `detect_incremental` defaults to `kind="semantic"` and over-reports changed files; it drives the skill's `/graphify --update`, not the CLI's `update` (#2459, open). [QMD:graphify-kg-temporal:targeted-issues.md]
- `backup_if_protected` reports incomplete backups as successful (#3769, open), and its snapshot set leaves out `graph.html` (#2402, open). [QMD:graphify-kg-temporal:targeted-issues.md]
- `graphify watch` has no `--debounce` option (#3061, open). The CLI reads only `sys.argv[2]` as the path and calls `watch(path)` with the 3.0 s default. As a result, `graphify watch . --debounce 60` silently ignores the flag, and `graphify watch --debounce 5` exits 1 with `error: path not found: --debounce`. Only `python -m graphify.watch [path] --debounce N` honours it. [QMD:graphify-kg-temporal:targeted-issues.md] [SRC:graphify/cli.py:L2332] [SRC:graphify/cli.py:L2339] [SRC:graphify/watch.py:L2859]
- The changed-files incremental rebuild, which at 0.9.92 only the post-commit hook requests, can drop cross-file dependency edges (#3570, open); `graphify update` is a full rebuild and is not affected, though paths a post-commit hook queues during the run are then drained as incremental passes. #3763 (open) reports that a plain AST-only `graphify update .` (and the watch path) dropped code-to-semantic edges through a `sem_edges` filter in watch.py that 0.9.92 no longer has, so the pinned source cannot say whether it still reproduces. [QMD:graphify-kg-temporal:targeted-issues.md] [SRC:graphify/hooks.py:L247] [SRC:graphify/watch.py:L2845] [SRC:graphify/watch.py:L1754-L1766] [SRC:graphify/watch.py:L1246]
- `detect()` always scans `graphify-out/memory/` outside the ignore rules (#3637, open; still so at 0.9.92). [QMD:graphify-kg-temporal:targeted-issues.md] [SRC:graphify/detect.py:L2007]
- The PreToolUse hook has no fail-open guard and resolves `graphify` with `shutil.which` (#3280, open). [QMD:graphify-kg-temporal:targeted-issues.md] [SRC:graphify/install.py:L1830]
- `--version` and `--help` still refresh stale installed skills (#4545, open, filed against 0.9.92). [QMD:graphify-kg-temporal:issues.md] [SRC:graphify/__main__.py:L838]
- `graphify label` can refuse its own final write when graph.json grew mid-run (#2976, open). [QMD:graphify-kg-temporal:targeted-issues.md]

See the references for the migration details.

## Key Types

**Exit codes.** `update`: 0, 1 (path missing, refused, failed), 2 (bad option, two paths). `path` and `explain`: 0 with an answer, 3 ambiguous (`EXIT_AMBIGUOUS`), 4 no match (`EXIT_NOT_FOUND`). `query` exits 4 on no match; its branch has no exit-3 path, although the help groups it with 3. [SRC:graphify/cli.py:L90] [SRC:graphify/cli.py:L91] [SRC:graphify/cli.py:L1668] [SRC:graphify/cli.py:L1962] [SRC:graphify/cli.py:L2106]

**graph.json.** NetworkX node-link data written compact on one line: `nodes`, `links`, `hyperedges`, a `graph` object holding `schema_version` (1) and `graphify_version`, and `built_at_commit` when known. [SRC:graphify/export.py:L476] [SRC:graphify/export.py:L485] [SRC:graphify/export.py:L488]

- Node: `id`, `label`, `file_type`, `source_file`, plus `community`, `community_name` and `norm_label`, which `to_json` adds. [SRC:graphify/validate.py:L6] [SRC:graphify/export.py:L381] [SRC:graphify/export.py:L382]
- Edge: `source`, `target`, `relation`, `confidence`, `source_file`, and `confidence_score`, which defaults by confidence. [SRC:graphify/validate.py:L7] [SRC:graphify/export.py:L197]

| Value set | Members |
|-----------|---------|
| `confidence` | `EXTRACTED`, `INFERRED`, `AMBIGUOUS` [SRC:graphify/validate.py:L5]. `to_json` fills in 1.0, 0.55 or 0.2 only when an edge has no `confidence_score` [SRC:graphify/export.py:L197] [SRC:graphify/export.py:L415]. The extraction rubric puts INFERRED scores in the discrete set {0.55, 0.65, 0.75, 0.85, 0.95} [SRC:graphify/export.py:L189-L196]; `to_json` fills in only missing scores and does not enforce the set [SRC:graphify/export.py:L412-L415]. AST call edges get their score in `graphify.extract` (not read for this skill): 0.85 for an INFERRED call, and 1.0 for a type-qualified call, which is EXTRACTED |
| `file_type` | `code`, `document`, `paper`, `image`, `rationale`, `concept` [SRC:graphify/validate.py:L4] |
| backed-up artifacts | graph.json, GRAPH_REPORT.md, .graphify_labels.json, .graphify_analysis.json, manifest.json, .graphify_semantic_marker, cost.json [SRC:graphify/export.py:L31] |

**Environment.** `GRAPHIFY_OUT` (output dir), `GRAPHIFY_FORCE`, `GRAPHIFY_NO_BACKUP`, `GRAPHIFY_MAX_GRAPH_BYTES`, `GRAPHIFY_NO_AUTO_REFRESH`, `GRAPHIFY_SKIP_HOOK`, `GRAPHIFY_REBUILD_TIMEOUT` (hooks, default 600 s), `GRAPHIFY_HOOK_STRICT`, `GRAPHIFY_API_KEY` (MCP HTTP). [SRC:graphify/paths.py:L30] [SRC:graphify/export.py:L54] [SRC:graphify/security.py:L49] [SRC:graphify/hooks.py:L450] [SRC:graphify/hooks.py:L201]

**Python types.**

- `FileType` (`graphify.detect`, a `str` Enum): `CODE` = "code", `DOCUMENT` = "document", `PAPER` = "paper", `IMAGE` = "image", `VIDEO` = "video". `classify_file()` returns one, or None for a file it does not classify. It is the scan's classification, not the `file_type` set of graph.json nodes. [AST:graphify/detect.py:L29] [AST:graphify/detect.py:L518]
- `ToolError` (`graphify.serve`, an `Exception`): an MCP tool handler raises it to return a result marked `isError: true`, where a plain string return is a successful result. [AST:graphify/serve.py:L34] [SRC:graphify/serve.py:L2712]

## Architecture at a Glance

- **Entry:** `__main__.main()` re-execs `update`, `extract`, `cluster-only` and `label` as `python -m graphify` with `PYTHONHASHSEED=0` so clustering is deterministic. It skips this when `PYTHONHASHSEED` is already set (an explicit choice is left alone) or under pytest, and continues unpinned if the re-exec raises OSError. It then dispatches to `install.dispatch_install_cli` or `cli.dispatch_command`. [SRC:graphify/__main__.py:L759] [SRC:graphify/__main__.py:L761] [SRC:graphify/__main__.py:L774] [AST:graphify/install.py:L2489]
- **Refresh:** `cli` `update` → `watch._rebuild_code` → `detect.detect` → extraction (`graphify.extract`, not read) → `_reconcile_existing_graph` → `build.build_from_json` → `cluster.cluster` → `report.generate` (in memory) → `export.to_json(force=True)` into `graphify-out/.graph.tmp.json` → `watch._check_shrink` (skipped when graph and report are unchanged) → the temp file replaces graph.json, then GRAPH_REPORT.md is written. With `--no-cluster`, the reconciled extraction goes through `_check_shrink` (when it differs from disk) and is written directly, with no `to_json` and no report. [SRC:graphify/cli.py:L2821] [SRC:graphify/watch.py:L2511] [SRC:graphify/watch.py:L2524] [SRC:graphify/watch.py:L2563] [SRC:graphify/watch.py:L2583] [SRC:graphify/watch.py:L2288]
- **Output:** `<scan root>/graphify-out/`, or `<scan root>/<GRAPHIFY_OUT>` when the override is a relative name. An absolute `GRAPHIFY_OUT` (e.g. `/shared/graphify-out`) is used as given, outside the scan root. `graphify extract --out DIR` writes to `DIR/<GRAPHIFY_OUT>` instead. [SRC:graphify/watch.py:L1713] [SRC:graphify/paths.py:L5] [SRC:graphify/cli.py:L3852]
- **Integrations:** `install` (skills, CLAUDE.md, settings hooks), `hooks` (git), `serve` (MCP). [SRC:graphify/install.py:L917] [SRC:graphify/install.py:L2136] [SRC:graphify/hooks.py:L1093] [SRC:ARCHITECTURE.md:L32]

## CLI

| Command | Key flags | Exits |
|---------|-----------|-------|
| `update [path]` | `--force`, `--no-cluster` | 0, 1, 2 [SRC:graphify/cli.py:L2779] |
| `extract {path}` / `graphify {path}` | `--code-only`, `--no-gitignore`, `--exclude`, `--force`, `--allow-partial`, `--allow-dedup-shrink`, `--no-cluster` | 0, 1, 2 [SRC:graphify/cli.py:L5115] |
| `cluster-only [path]` / `label [path]` | `--graph`, `--no-viz`, `--no-label`, `--missing-only` | 0, 1 [SRC:graphify/cli.py:L2691] |
| `query "Q"` / `path "A" "B"` / `explain "X"` | `--graph`, `--budget`, `--seed`, `--undirected` | 0, 1, 3, 4 [SRC:graphify/__main__.py:L915] |
| `watch [path]` / `check-update {path}` | none at the CLI | 0, 1 [SRC:graphify/cli.py:L2859] |
| `hook install`, `hook uninstall`, `hook status` | none | 0, 1 [SRC:graphify/cli.py:L1530] |
| `install [P]` / `claude install` | `--project`, `--strict`, `--platform P` | 0, 1 [AST:graphify/install.py:L2489] |
| `uninstall` | `--purge`, `--project`, `--platform P` | 0, 1 [SRC:graphify/__main__.py:L857] |

An unknown command prints `error: unknown command` and exits 1. The full table is in `references/pattern-cli-reference.md`. [SRC:graphify/cli.py:L5389]

## Full API Reference

The pattern references hold the full detail, with the T2 context for each surface:

- `references/pattern-update-refresh.md`: `graphify update` end to end: the lock, the corpus, the shrink guard, what it writes, and every way it returns 1.
- `references/pattern-cli-reference.md`: every subcommand with its flags and exit codes.
- `references/pattern-output-layout.md`: `graphify-out/` file by file, the graph.json and GRAPH_REPORT.md formats, and the backups.
- `references/pattern-ignore-rules.md`: `.gitignore`, `.graphifyignore`, `--exclude`, the built-in skips, sensitive files, and `.graphifyrc`.
- `references/pattern-claude-code-integration.md`: `graphify install`, `graphify claude install`, the PreToolUse guard, the CLAUDE.md blocks, the git hooks, the merge driver and the MCP server.
- `references/pattern-python-api.md`: the importable Python helpers listed below, each with its signature, what it does, its citation and an example.

| Module | Helpers |
|--------|---------|
| `graphify.paths` | `out_path`, `default_graph_json`, `load_node_link_graph`, `restore_arc_direction`, `write_text_atomic`, `write_text_atomic_if_changed`, `write_json_atomic`, `os_replace_with_fallback`, `is_absolute_any_platform`, `nfc`, `stem_filename_budget`, `disambiguate_ambiguous_candidates` |
| `graphify.detect` | `classify_file`, `count_words`, `extract_pdf_text`, `docx_to_markdown`, `xlsx_to_markdown`, `xlsx_extract_structure`, `convert_office_file`, `load_manifest`, `save_manifest`, `detect_incremental` |
| `graphify.rcfile` | `parse_language_value`, `activate_language_overrides`, `set_language_overrides`, `get_language_overrides`, `effective_suffix`, `cache_salt` |
| `graphify.export` | `to_obsidian`, `to_canvas`, `to_graphml`, `to_svg`, `to_cypher`, `attach_hyperedges`, `prune_dangling_edges`, `existing_graph_node_count` |
| `graphify.security` | `validate_url`, `safe_fetch`, `safe_fetch_text`, `sanitize_label`, `sanitize_metadata` |
| `graphify.install` | `claude_uninstall`, `gemini_install`, `gemini_uninstall`, `vscode_install`, `vscode_uninstall`, `codebuddy_install`, `codebuddy_uninstall`, `uninstall_all` |
| `graphify.hooks` | `uninstall` |
| `graphify.serve` | `serve_http`, `find_node_ambiguity` |
| `graphify.report`, `graphify.querylog`, `graphify.watch` | `load_learning_for_report`, `log_query`, `nodes_from_result`, `check_update` |

## Full Integration Patterns

- **networkx** (18 import sites): `nx.Graph` is the in-memory graph, and `networkx.readwrite.json_graph` reads and writes graph.json. [SRC:graphify/export.py:L14]
- **mcp, starlette, uvicorn, pydantic** (`graphifyy[mcp]`): `serve()` runs `mcp.server.Server` over stdio, and `serve_http()` mounts a Streamable HTTP manager in a Starlette app run by uvicorn. pydantic supplies `AnyUrl` on mcp 2. [SRC:pyproject.toml:L68] [SRC:graphify/serve.py:L2147]
- **watchdog** (`graphifyy[watch]`): imported inside `watch()`; `PollingObserver` on macOS. [SRC:graphify/watch.py:L2758]
- **matplotlib, pypdf, python-docx, openpyxl**: optional extras, each imported inside the function that needs it. [SRC:graphify/export.py:L1384] [SRC:graphify/detect.py:L567]
