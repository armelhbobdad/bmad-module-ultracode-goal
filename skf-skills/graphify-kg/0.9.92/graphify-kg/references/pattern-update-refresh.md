# Pattern: the `graphify update` refresh

## Contents

- [Invocation and exit codes](#invocation-and-exit-codes)
- [Before the command runs](#before-the-command-runs)
- [The rebuild lock and the queue](#the-rebuild-lock-and-the-queue)
- [Which files are re-extracted](#which-files-are-re-extracted)
- [Reconciling with the existing graph](#reconciling-with-the-existing-graph)
- [The shrink guard](#the-shrink-guard)
- [What a successful update writes](#what-a-successful-update-writes)
- [Every way update exits 1](#every-way-update-exits-1)
- [The --no-cluster path](#the---no-cluster-path)
- [Temporal context](#temporal-context)

## Invocation and exit codes

```bash
graphify update [PATH] [--force] [--no-cluster]
```

| Input | Result |
|-------|--------|
| `--force`, or `GRAPHIFY_FORCE` set to `1`, `true` or `yes` | the shrink guard is bypassed [SRC:graphify/cli.py:L2780] |
| `--no-cluster` | raw merged extraction, no clustering, no report [SRC:graphify/__main__.py:L893] |
| an exact `-h`, `--help` or `-?` token | caught by the universal help guard before `update` runs: `Run 'graphify --help' for full usage.`, exit 0, no rebuild [SRC:graphify/__main__.py:L1081] |
| any other argument starting with `-` | `error: unknown update option: X`, exit 2 [SRC:graphify/cli.py:L2793] |
| a second path | `error: update accepts at most one path argument`, exit 2 [SRC:graphify/cli.py:L2796] |
| no path | the scan root saved in `graphify-out/.graphify_root`, else `.` [SRC:graphify/cli.py:L2803] |
| a path that does not exist | `error: path not found`, exit 1 [SRC:graphify/cli.py:L2814] |
| the rebuild returned True | exit 0, including "No code-graph changes detected" [SRC:graphify/watch.py:L2561] |
| the rebuild returned False | `Nothing to update or rebuild failed — check output above.` on stderr, exit 1 [SRC:graphify/cli.py:L2837] |

The `.graphify_root` lookup is `Path(GRAPHIFY_OUT) / ".graphify_root"`. With the default or a relative `GRAPHIFY_OUT`, it resolves against the current directory, so a bare `graphify update` finds the marker only when run from the folder that holds the output folder. With an absolute `GRAPHIFY_OUT`, the marker is found from any directory, and rebuilds write it as an absolute path. [SRC:graphify/cli.py:L2803] [SRC:graphify/watch.py:L432]

On success the CLI prints `Code graph updated. For doc/paper/image changes run /graphify --update in your AI assistant.` and then, on stdout, `Tip: set GEMINI_API_KEY or GOOGLE_API_KEY to use Gemini for semantic extraction.`. The tip is left out only when `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `MOONSHOT_API_KEY`, `DEEPSEEK_API_KEY` or `GRAPHIFY_NO_TIPS` is set. Other keys, such as `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`, do not suppress it. [SRC:graphify/cli.py:L2823] [SRC:graphify/cli.py:L2824] [SRC:graphify/cli.py:L2831]

## Before the command runs

- `main()` re-execs `update`, `extract`, `cluster-only` and `label` as `python -m graphify` with `PYTHONHASHSEED=0` unless `PYTHONHASHSEED` is already set or pytest is running (`PYTEST_CURRENT_TEST`), so Louvain clustering is reproducible. A re-exec that raises OSError is ignored and the command runs unpinned. On Windows the child is run and waited for, and its exit status is passed on. [SRC:graphify/__main__.py:L725] [SRC:graphify/__main__.py:L761] [SRC:graphify/__main__.py:L774] [SRC:graphify/__main__.py:L778] [AST:graphify/__main__.py:L798]
- `_run_cli()` then runs the stale-skill refresh, unless any argv token equals `install`, `uninstall`, `hook-check` or `hook-guard`, so per-platform commands such as `claude install`, `hook install` and `cursor uninstall` skip it too; `update` and `--version` run it. It re-copies only single-writer, non-vscode user-scope skill copies whose `.graphify_version` stamp is older than the package. A differing `SKILL.md` is kept as `SKILL.md.bak`, and the refresh reports on stderr. `GRAPHIFY_NO_AUTO_REFRESH` set to `1`, `true` or `yes` disables it. [SRC:graphify/__main__.py:L833] [SRC:graphify/__main__.py:L834] [SRC:graphify/__main__.py:L838] [SRC:graphify/__main__.py:L294] [SRC:graphify/__main__.py:L321]

An unattended caller that must not touch `~/.claude/skills/` should export `GRAPHIFY_NO_AUTO_REFRESH=1` before calling graphify at all.

## The rebuild lock and the queue

- The output folder is `PATH / GRAPHIFY_OUT`, which is `graphify-out` unless the env var names another name or an absolute path. [SRC:graphify/watch.py:L1713] [SRC:graphify/paths.py:L30]
- `_rebuild_lock` takes an advisory `fcntl.flock` (POSIX) or `msvcrt.locking` (Windows) on `graphify-out/.rebuild.lock`, writes the owning PID into it, and unlinks it on release. [SRC:graphify/watch.py:L217]
- The CLI passes `block_on_lock=True`, so `graphify update` waits for a running hook rebuild instead of exiting. A hook (or `watch`) passes no flag: it first appends its paths to `.pending_changes`, or touches `.pending_full` for a full request, then tries the lock, and when the lock is held it returns False. [SRC:graphify/cli.py:L2821] [SRC:graphify/watch.py:L1714] [SRC:graphify/watch.py:L1728]
- The lock holder drains both queues before and after its own pass, for up to 20 late passes. [SRC:graphify/watch.py:L1728] [SRC:graphify/watch.py:L25]
- A relative path with a deleted working directory fails with `Rebuild failed: current working directory no longer exists and GRAPHIFY_REPO_ROOT is not set.`. Setting `GRAPHIFY_REPO_ROOT` to an existing directory makes the rebuild `chdir` there first; no file in this skill's scope sets it. [SRC:graphify/watch.py:L1576]

## Which files are re-extracted

- `detect()` re-runs on the scan root with the `--exclude` patterns and the gitignore setting that `extract` saved in `.graphify_build.json`. Without that file, gitignore is honoured and nothing extra is excluded. [SRC:graphify/watch.py:L1789] [SRC:graphify/watch.py:L106]
- Files with no supported extension or shebang are listed once: `[graphify watch] N file(s) not classified ... skipped`. [SRC:graphify/watch.py:L1803]
- Code files are re-extracted, together with document files that have an AST extractor. The code comment gives `.md`, `.mdx` and `.qmd` as examples; `graphify.extract._get_extractor`, which this skill did not read, makes the actual choice. [SRC:graphify/watch.py:L1828]
- A document that already carries semantic (LLM) nodes is not AST-scanned again. It stays in the corpus for the deletion and shrink accounting. [SRC:graphify/watch.py:L1841] [SRC:graphify/watch.py:L1979]
- With no code file and no existing `graph.json`, the run prints `[graphify watch] No code files found - nothing to rebuild.` and exits 1. With code files and no `graph.json`, `update` builds a new graph: it does not require an earlier build. [SRC:graphify/watch.py:L1838]
- `graphify update` always rebuilds the full corpus (`changed_paths` is None). Work that the git hooks or `watch` queue while it holds the lock is drained afterwards under the same lock: queued paths as incremental passes, a queued full request as another full pass. Only the post-commit hook passes a change list; the post-checkout, post-merge and post-rewrite hooks and `watch` request full rebuilds. [SRC:graphify/cli.py:L2821] [SRC:graphify/watch.py:L1738] [SRC:graphify/watch.py:L1754-L1766] [SRC:graphify/hooks.py:L247] [SRC:graphify/hooks.py:L322] [SRC:graphify/watch.py:L2845]

## Reconciling with the existing graph

`_reconcile_existing_graph` merges the fresh AST output with what the old graph keeps: semantic nodes, docs, and AST nodes of files not re-extracted. It also decides what to evict. [SRC:graphify/watch.py:L993]

- **An unreadable or oversized graph.json** raises inside reconcile. `_rebuild_code` prints `error: ...` and returns False, so update exits 1. `--force` does not bypass this: force means accept a shrink, not overwrite a graph that could not be read. [SRC:graphify/watch.py:L2190] [SRC:graphify/watch.py:L2196]
- **A deleted source** has its nodes, edges and hyperedges evicted, and the path joins the deleted set. The exception is a missing path that the previous scan's manifest.json never listed and that a referrer not re-extracted this run still points at. That is a placeholder, not a deletion, so its nodes are kept. Such a path is still evicted when one of its nodes carries a `source_location` or it is the `source_file` of an edge, because it was then extracted itself. When manifest.json is unreadable or lists none of the files in this run's scan, every missing path is evicted as before. [SRC:graphify/watch.py:L1157] [SRC:graphify/watch.py:L1184] [SRC:graphify/watch.py:L1182] [SRC:graphify/watch.py:L929] [SRC:graphify/watch.py:L939-L946] [SRC:graphify/watch.py:L950-L960] [SRC:graphify/watch.py:L971] [SRC:graphify/watch.py:L979-L982]
- **A present file a live ignore rule now matches** is treated like a deletion. `.graphifyignore` and `--exclude` rules count on every rebuild; `.gitignore` rules count only on a full rebuild, which `graphify update` is. The run prints `[graphify watch] pruned N node(s) from M newly-ignored file(s) ...`. [SRC:graphify/watch.py:L1110] [SRC:graphify/watch.py:L1193]
- **A present file that left the corpus without matching a rule** keeps its nodes, fail-closed. For a source with an AST extractor (code, and also `.md`), the run prints `[graphify watch] fail-closed: kept N node(s) ... Add them to .graphifyignore if the exclusion is intentional.`; a doc, paper or image source with no AST extractor is kept without a note. [SRC:graphify/watch.py:L1136] [SRC:graphify/watch.py:L1179] [SRC:graphify/watch.py:L1199]

## The shrink guard

`watch._check_shrink` is the only check that can refuse an update because nodes went missing. The clustered path calls `export.to_json(..., force=True)` on the temporary `graphify-out/.graph.tmp.json`, so the node-count guard inside `to_json` never runs for update. [SRC:graphify/watch.py:L1449] [SRC:graphify/watch.py:L2523] [SRC:graphify/watch.py:L2524]

Order of the checks: [SRC:graphify/watch.py:L1449]

1. `force`, or an empty existing graph: allowed. [SRC:graphify/watch.py:L1487]
2. A legacy caller that declares deletions but passes no rebuilt set: allowed. Update always passes one. [SRC:graphify/watch.py:L1489]
3. A saved semantic node that the new graph lacks, on a file that was not deleted: refused with `[graphify] WARNING: Refusing to overwrite — saved semantic node(s) are missing from the new graph: {ids}.` The test is `graphify.build._lost_saved_semantic_nodes`, not read for this skill. [SRC:graphify/watch.py:L1501]
4. A new node count at least the old one: allowed. [SRC:graphify/watch.py:L1521]
5. A net loss: allowed when every lost node has no `source_file`, or belongs to a file in the rebuilt set or a deleted file (newly ignored included), and no lost node belongs to a file whose extraction failed. On a full `update`, the rebuilt set is every code file and AST-extractable document that detect() returned under the project root. That includes semantic-backed docs that were not AST-scanned, so the set is wider than the files re-extracted this run. [SRC:graphify/watch.py:L1523] [SRC:graphify/watch.py:L2211] [SRC:graphify/watch.py:L2217]
6. Otherwise: refused with `[graphify] WARNING: new graph has N nodes but existing graph.json has M. Refusing to overwrite — you may be missing chunk files from a previous session. Pass --force to override.` [SRC:graphify/watch.py:L1543]

In practice for a full `update`: deleting code shrinks the graph without a warning (rule 5). A file newly matched by `.gitignore` or `.graphifyignore` is pruned with a stdout note (rule 5). A refusal means a source whose extraction failed, a saved semantic node that vanished, or nodes the rebuild cannot account for. On a refusal the temporary file is deleted and graph.json stays as it was. [SRC:graphify/watch.py:L1543]

## What a successful update writes

The clustered path, in order: [SRC:graphify/watch.py:L2563]

1. The new graph goes to `graphify-out/.graph.tmp.json`, through `to_json(force=True)`. [SRC:graphify/watch.py:L2524]
2. When the graph and the report both equal what is on disk, graph.json, GRAPH_REPORT.md, the label files and graph.html are left alone. The temp file is deleted and `[graphify watch] No code-graph changes detected; graph.json/GRAPH_REPORT.md left untouched.` is printed, but `.graphify_root` and `manifest.json` (`kind="ast"`) are still rewritten. A topology-only comparison earlier in the run, before clustering, can also skip. It re-saves `manifest.json` and keeps graph.json and GRAPH_REPORT.md. It re-renders `graph.html` when that file is missing or stale, and deletes it when the viz node limit is 0 or less. [SRC:graphify/watch.py:L2561] [SRC:graphify/watch.py:L2618] [SRC:graphify/watch.py:L2626] [SRC:graphify/watch.py:L2370] [SRC:graphify/watch.py:L2378] [SRC:graphify/watch.py:L1620]
3. `_check_shrink` runs, then the graph.html stale marker is touched. [SRC:graphify/watch.py:L2563] [SRC:graphify/watch.py:L2575]
4. `backup_if_protected` snapshots the outputs into `graphify-out/YYYY-MM-DD/` when the graph is semantic or curated. [SRC:graphify/watch.py:L2577] [AST:graphify/export.py:L42]
5. The temporary file replaces `graph.json` atomically, then `GRAPH_REPORT.md` is written. [SRC:graphify/watch.py:L2583] [SRC:graphify/watch.py:L2584]
6. The labels follow: `.graphify_labels.json` holds curated names only, `.graphify_labels.pending.json` holds hub-derived fallback names, and `.graphify_labels.json.sig` holds the membership signatures. [SRC:graphify/watch.py:L2400] [SRC:graphify/watch.py:L2401] [SRC:graphify/watch.py:L2414]
7. Then `.graphify_root`, and `manifest.json` stamped `kind="ast"`. [SRC:graphify/watch.py:L2618] [SRC:graphify/watch.py:L2628]
8. `graph.html` is re-rendered from the persisted graph, or removed when the viz node limit is 0 or less, and any `*-callflow.html` is regenerated. [SRC:graphify/watch.py:L1620] [SRC:graphify/watch.py:L2645]

The success lines go to stdout: `[graphify watch] Rebuilt: N nodes, E edges, C communities`, then `[graphify watch] {products} updated in {out}`. `{products}` is `graph.json`, then `, graph.html` only when graph.html was rendered, then ` and GRAPH_REPORT.md`, then `, K callflow HTML` when `*-callflow.html` files exist in the output directory. Example: `graph.json, graph.html and GRAPH_REPORT.md, 1 callflow HTML updated in graphify-out`. [SRC:graphify/watch.py:L2661] [SRC:graphify/watch.py:L2663] [SRC:graphify/watch.py:L2664] [SRC:graphify/watch.py:L2666]

## Every way update exits 1

| Cause | Message (stream) |
|-------|------------------|
| path not found | `error: path not found: {path}` (stderr) [SRC:graphify/cli.py:L2814] |
| working directory gone | `[graphify watch] Rebuild failed: current working directory no longer exists ...` (stdout) [SRC:graphify/watch.py:L1576] |
| rebuild lock not obtained (even the blocking CLI wait gives up this way after 100 lock-inode retries) | `[graphify watch] Rebuild already in progress for {path} - nothing to queue.` (stdout) [SRC:graphify/watch.py:L1730] [SRC:graphify/watch.py:L246-L276] |
| no code files and no graph | `[graphify watch] No code files found - nothing to rebuild.` (stdout) [SRC:graphify/watch.py:L1838] |
| unreadable or oversized graph.json | `error: {exc}` (stderr) [SRC:graphify/watch.py:L2190] |
| graph.json re-read failed just before the compare | `error: Cannot read {graph.json}: {exc}. Refusing to overwrite; delete the file and run a full rebuild.` (stderr) [SRC:graphify/watch.py:L2540] [SRC:graphify/watch.py:L2272] |
| shrink refused | `[graphify] WARNING: ... Refusing to overwrite ...` (stderr) [SRC:graphify/watch.py:L1543] |
| any exception in the pipeline | `[graphify watch] Rebuild failed: {exc}` (stdout) [SRC:graphify/watch.py:L2670] |

Every `_rebuild_code` failure (every row except `path not found`) is followed by `Nothing to update or rebuild failed — check output above.` on stderr, then exit 1. `path not found` exits 1 at once, before the rebuild runs, and does not print that line. [SRC:graphify/cli.py:L2814] [SRC:graphify/cli.py:L2834]

## The --no-cluster path

`--no-cluster` writes the deduplicated raw extraction as `nodes`, `links` and `hyperedges` and keeps the old graph's `directed` flag. When the result differs from graph.json on disk, it runs the same `_check_shrink`, backs up, and replaces `graph.json` through `.graph.tmp.json`; an identical result is not rewritten. No `GRAPH_REPORT.md` is written. [SRC:graphify/watch.py:L2287] [SRC:graphify/watch.py:L2288] [SRC:graphify/watch.py:L2305] [SRC:graphify/watch.py:L2307]

## Temporal context

- T2-past: #3774 (closed). `graphify <path>` used to write with force on every normal run, so the #479 guard in `to_json` never engaged. At 0.9.92 `extract` adds a dedup-shrink refusal (`--allow-dedup-shrink`) and a partial-build refusal (`--allow-partial`). [QMD:graphify-kg-temporal:targeted-issues.md] [SRC:graphify/cli.py:L5089] [SRC:graphify/cli.py:L5115]
- T2-past: #3105 (closed). `extract` overwrote a 570-node graph with 111 nodes because hollow LLM responses did not count as incomplete. [QMD:graphify-kg-temporal:targeted-issues.md]
- T2-past: #3294 (closed). The code-only `_rebuild_code` deleted `graphify-out/needs_update` on every exit. [QMD:graphify-kg-temporal:targeted-issues.md]
- T2-future: #3570 (open). The changed-files incremental rebuild (the post-commit hook path; the issue also names watch, but at 0.9.92 `watch` calls `_rebuild_code` without a change list) can drop cross-file dependency edges. `graphify update` is a full rebuild and is not affected, though paths a post-commit hook queues during the run are then drained as incremental passes. [QMD:graphify-kg-temporal:targeted-issues.md] [SRC:graphify/hooks.py:L247] [SRC:graphify/watch.py:L2845] [SRC:graphify/watch.py:L1754-L1766]
- T2-future: #3763 (open). It reports that a plain AST-only `graphify update .` (and the watch path) dropped EXTRACTED code-to-semantic edges through a `sem_edges` filter in watch.py. At 0.9.92 that filter is gone and edge preservation is tier-scoped, so the pinned source cannot say whether #3763 still reproduces. [QMD:graphify-kg-temporal:targeted-issues.md] [SRC:graphify/watch.py:L1246]
- T2-future: #2976 (open). `graphify label` can see its final write refused by the `to_json` guard when graph.json grew mid-run. [QMD:graphify-kg-temporal:targeted-issues.md]
