# Pattern: the graphify-out/ layout and formats

## Contents

- [Where the folder is](#where-the-folder-is)
- [File by file](#file-by-file)
- [graph.json](#graphjson)
- [GRAPH_REPORT.md](#graph_reportmd)
- [Backups](#backups)
- [Size cap and path checks](#size-cap-and-path-checks)
- [Temporal context](#temporal-context)

## Where the folder is

- The name is `graphify-out`, or the `GRAPHIFY_OUT` env var, read once at import. A relative name and an absolute path both work. An unset or blank `GRAPHIFY_OUT` silently becomes `graphify-out`. Only a value that normalizes to `.` (e.g. `.`, `./`, `foo/..`) or to `..` parts alone (e.g. `..`, `../..`) prints `warning: GRAPHIFY_OUT='...' points at the project or a parent of it; using 'graphify-out' instead` to stderr and falls back. An absolute path that names the project or a parent is not detected and is used as given. [SRC:graphify/paths.py:L30] [SRC:graphify/paths.py:L39-L49] [SRC:graphify/paths.py:L53]
- Rebuilds write to `{scan root}/{GRAPHIFY_OUT}`; an absolute `GRAPHIFY_OUT` replaces the scan root, so that output lands outside it. [SRC:graphify/watch.py:L1713] [SRC:graphify/paths.py:L5]
- `detect()` prunes the configured output folder from its walk, matching it by resolved path, and `_SKIP_DIRS` also skips any directory named `graphify-out`. The exception is `{GRAPHIFY_OUT}/memory/`: when it exists, detect() adds it as an extra scan root and does not noise-filter it. [SRC:graphify/detect.py:L2072-L2080] [SRC:graphify/detect.py:L943] [SRC:graphify/detect.py:L2006-L2010]

## File by file

| Path under graphify-out/ | Written by | Content |
|--------------------------|------------|---------|
| `graph.json` | `extract`, `update`, `cluster-only`, `label` | the graph, see below [AST:graphify/export.py:L287] |
| `GRAPH_REPORT.md` | `update` (not with `--no-cluster`), `cluster-only`, `label` | the report, see below. `extract` never writes it. On the clustered path it prints `` [graphify extract] next: run `graphify cluster-only <dir>` to generate GRAPH_REPORT.md and name communities `` instead, and `extract --no-cluster` prints no hint: it exits 0 after its `(no clustering)` line [AST:graphify/report.py:L96] [SRC:graphify/cli.py:L5187-L5194] [SRC:graphify/cli.py:L4936] [SRC:graphify/cli.py:L4963] [SRC:graphify/watch.py:L2584] [SRC:graphify/cli.py:L2699] |
| `graph.html` | `update` (re-rendered from graph.json), `cluster-only` and `label` (unless `--no-viz`), `export html` (unless `--no-viz`) | interactive view. It is removed when `GRAPHIFY_VIZ_NODE_LIMIT` is 0 or less. `--no-viz` on `cluster-only`, `label` or `export html` also deletes an existing graph.html instead of leaving it in place [SRC:graphify/watch.py:L1619-L1622] [SRC:graphify/cli.py:L2734-L2736] [SRC:graphify/cli.py:L3476-L3479] |
| `.graphify_labels.json` | `update`, `cluster-only`, `label` | community names. `update` writes only curated (manual or LLM) names here and keeps hub fallbacks in `.graphify_labels.pending.json`. `cluster-only` and `label` write every name they used, hub-derived ones included. `cluster-only --no-label` with no existing labels file writes nothing, because only `Community N` placeholders exist then; `label` ignores `--no-label` and always writes names [SRC:graphify/watch.py:L2519-L2521] [SRC:graphify/watch.py:L2604] [SRC:graphify/cli.py:L2620] [SRC:graphify/cli.py:L2347] [SRC:graphify/cli.py:L2604-L2606] [SRC:graphify/cli.py:L2715-L2717] |
| `.graphify_labels.pending.json` | `update` | hub-derived fallback names, kept out of the tracked labels file [SRC:graphify/watch.py:L2414] |
| `.graphify_labels.json.sig` | `update`, `cluster-only`, `label` | community membership signatures, written atomically after the labels. `cluster-only` skips it, as it skips the labels, when only placeholders exist [SRC:graphify/watch.py:L2613-L2614] [SRC:graphify/cli.py:L2715] [SRC:graphify/cli.py:L2724-L2727] |
| `.graphify_root` | `extract`, `update` | the scan root. `extract` always writes the resolved absolute path. `update` writes the path as given, resolved to absolute only when `GRAPHIFY_OUT` is absolute [SRC:graphify/cli.py:L5123-L5125] [SRC:graphify/cli.py:L4924-L4925] [SRC:graphify/watch.py:L432-L434] |
| `manifest.json` | `extract`, `update` | per-file `mtime`, `ast_hash` and `semantic_hash`; `update` stamps `kind="ast"` [SRC:graphify/detect.py:L37] [SRC:graphify/detect.py:L2686] [SRC:graphify/watch.py:L2628] |
| `.graphify_build.json` | `extract` | `{"excludes": [...], "gitignore": false}` re-applied by every rebuild [SRC:graphify/watch.py:L106] |
| `.graphify_semantic_marker` | `extract` (clustered path only, `--no-cluster` never writes it) | `{"output_tokens": N}`, written when that run spent output tokens. No command removes the marker file itself, so once written it stays until the whole output folder is deleted, as `graphify uninstall --purge` does. [SRC:graphify/cli.py:L5129-L5132] [SRC:graphify/install.py:L2282-L2286] |
| `.rebuild.lock` | rebuilds | owner PID while a rebuild runs; unlinked on release [SRC:graphify/watch.py:L217] |
| `.pending_changes`, `.pending_full` | non-blocking rebuilds (the git hooks and `watch`), written before they try the lock | queued work. Incremental requests append paths to `.pending_changes`, full requests touch `.pending_full`, and the lock holder drains both, so a file left on disk means a rebuild was already running. `update` blocks on the lock and never queues. [SRC:graphify/watch.py:L1714-L1740] [SRC:graphify/watch.py:L82-L90] [SRC:graphify/watch.py:L2845] [SRC:graphify/cli.py:L2821] |
| `.graph.tmp.json` | `update` | the candidate graph before `_check_shrink`; deleted on refusal [SRC:graphify/watch.py:L2523] |
| `needs_update` | `watch` | flag for non-code changes that need `/graphify --update`; read by `check-update` and by the PreToolUse guard [SRC:graphify/watch.py:L2689] [SRC:graphify/watch.py:L2682] |
| `YYYY-MM-DD/` | `backup_if_protected` | one dated backup folder per day [SRC:graphify/export.py:L75] |
| `memory/` | `save-result` | saved Q&A; `detect()` always scans it [SRC:graphify/detect.py:L2007] |
| `reflections/LESSONS.md` | `reflect`, and every graphify git hook (post-commit, post-checkout, post-merge, post-rewrite) after its rebuild when `memory/` holds `*.md` files | lessons from `memory/` [SRC:graphify/hooks.py:L248-L256] [SRC:graphify/hooks.py:L323-L331] [SRC:graphify/cli.py:L1843-L1846] |
| `converted/` | `detect()` | Markdown sidecars of `.docx`, `.xlsx` and Google Workspace files [SRC:docs/how-it-works.md:L19] |
| `*-callflow.html` | `export callflow-html` | regenerated by `update` when present [SRC:graphify/watch.py:L2645] |
| `GRAPH_TREE.html`, `merged-graph.json` | `tree`, `merge-graphs` | default outputs. `tree` writes beside its `--graph` file (graphify-out/ by default), and `merge-graphs` writes to `{GRAPHIFY_OUT}/merged-graph.json`. [SRC:graphify/cli.py:L2909-L2910] [SRC:graphify/cli.py:L2992] |

`.graphify_analysis.json` and `cost.json` are in the backup set; this skill did not trace which command writes them. [SRC:graphify/export.py:L31]

## graph.json

`to_json` writes NetworkX node-link data (`edges="links"`), atomically and compact on one line. [SRC:graphify/export.py:L488]

```json
{
  "directed": false,
  "multigraph": false,
  "graph": {"schema_version": 1, "graphify_version": "0.9.92"},
  "nodes": [{"id": "...", "label": "...", "community": 3, "community_name": "...", "file_type": "code", "norm_label": "...", "source_file": "..."}],
  "links": [{"source": "...", "target": "...", "relation": "calls", "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": "..."}],
  "hyperedges": [],
  "built_at_commit": "86c57be8..."
}
```

This shape illustrates the keys `to_json` writes; the values are placeholders.

- `graph.schema_version` is `GRAPH_SCHEMA_VERSION`, 1 at 0.9.92. `graph.graphify_version` names the release. [SRC:graphify/export.py:L476]
- `built_at_commit` is the analysed repo's HEAD, when known. [SRC:graphify/export.py:L485]
- Every node gets `community` and `norm_label`; `community_name` is added when labels exist. [SRC:graphify/export.py:L381] [SRC:graphify/export.py:L382]
- A link without `confidence_score` gets the default for its confidence: EXTRACTED 1.0, INFERRED 0.55, AMBIGUOUS 0.2. [SRC:graphify/export.py:L197]
- Keys are ordered (`id` and `label` first for nodes; `source`, `target` and `relation` first for links), and both lists are sorted, so equal graphs serialize to equal bytes. [AST:graphify/export.py:L287]
- `multigraph` is set to true when the restored links hold parallel edges (#4500). [SRC:graphify/export.py:L411]
- `update` inherits the existing graph's `directed` flag, with or without `--no-cluster`. [SRC:graphify/watch.py:L2249-L2252] [SRC:graphify/watch.py:L2352-L2355]

Extraction-time schema (`validate_extraction`): nodes need `id`, `label`, `file_type` and `source_file`; edges need `source`, `target`, `relation`, `confidence` and `source_file`; `file_type` is one of code, document, paper, image, rationale or concept; `confidence` is EXTRACTED, INFERRED or AMBIGUOUS. It returns a list of error strings. It does not raise for a non-dict input, missing keys, non-dict items, or unhashable ids and endpoints, but an unhashable `file_type` or `confidence` value (a list or dict) still raises `TypeError`. `assert_valid` raises `ValueError` listing every error. [AST:graphify/validate.py:L10] [SRC:graphify/validate.py:L48] [SRC:graphify/validate.py:L68] [AST:graphify/validate.py:L90] [SRC:graphify/validate.py:L4]

## GRAPH_REPORT.md

`report.generate()` builds these sections in order. The title, Corpus Check, Summary, God Nodes, Surprising Connections and Communities are always emitted. God Nodes may be empty, and Surprising Connections prints `- None detected - ...` when it has nothing. Import Cycles appears whenever the graph has code nodes or import edges, and prints `- None detected.` when there are no cycles. Graph Freshness, Community Hubs, Hyperedges, Ambiguous Edges, Knowledge Gaps, Work-memory lessons and Suggested Questions appear only when they have content. Work-memory lessons comes after Knowledge Gaps and before Suggested Questions. [AST:graphify/report.py:L96] [SRC:graphify/report.py:L233-L258] [SRC:graphify/report.py:L264-L283] [SRC:graphify/report.py:L380-L389]

1. `# Graph Report - {root}  ({date})` [SRC:graphify/report.py:L129]
2. `## Corpus Check` [SRC:graphify/report.py:L131]
3. `## Summary`: node, edge and community counts, the EXTRACTED / INFERRED / AMBIGUOUS split, token cost [SRC:graphify/report.py:L200]
4. `## Graph Freshness`: `Built from commit: {8 chars}`, when `built_at_commit` is given (`update` gives it) [SRC:graphify/report.py:L211]
5. `## Community Hubs (Navigation)` [SRC:graphify/report.py:L224]
6. `## God Nodes (most connected - your core abstractions)` [SRC:graphify/report.py:L235]
7. `## Surprising Connections (you probably didn't know these)` [SRC:graphify/report.py:L240]
8. `## Import Cycles`, `## Hyperedges (group relationships)` [SRC:graphify/report.py:L273] [SRC:graphify/report.py:L287]
9. `## Communities (N total, M thin omitted)` [SRC:graphify/report.py:L295]
10. `## Ambiguous Edges - Review These`, `## Knowledge Gaps` [SRC:graphify/report.py:L317] [SRC:graphify/report.py:L344]
11. `## Work-memory lessons`: emitted only when `.graphify_learning.json` beside graph.json (written by `graphify reflect` when a graph is present) has a `preferred` node, or when `memory/` aggregates to at least one `dead_end`. Saved outcomes alone are not enough. [SRC:graphify/report.py:L40-L60] [SRC:graphify/report.py:L71-L80]
12. `## Suggested Questions` (AMBIGUOUS-based questions go in a `### Low-confidence Hints` subsection) [SRC:graphify/report.py:L389] [SRC:graphify/report.py:L400]

`update` compares graphs without `built_at_commit` and reports without the `Built from commit` line, so a new HEAD alone does not rewrite an unchanged graph. [SRC:graphify/watch.py:L1351] [SRC:graphify/watch.py:L2561]

## Backups

`backup_if_protected(out_dir)` runs before every `update` overwrite. [AST:graphify/export.py:L42] [SRC:graphify/watch.py:L2577]

- It acts only when `graph.json` exists and the graph is protected: a `.graphify_semantic_marker` is present, or `.graphify_labels.json` holds a name other than `Community N`. [AST:graphify/export.py:L42]
- It copies the backup set into `graphify-out/YYYY-MM-DD/`, one folder per day, overwritten when graph.json has changed since that day's copy. [SRC:graphify/export.py:L75]
- `GRAPHIFY_NO_BACKUP` set to any non-empty value disables it; an empty value does not. A failure to create the dated backup folder prints `[graphify] warning: backup failed (...) - continuing with overwrite` and the write goes ahead. Per-file copy errors are skipped silently, so an incomplete backup gets no warning: the folder is still returned, and `[graphify] backed up ...` is still printed when any file was copied (#3769). The same-day hash check reads both graph.json files outside that guard, so a read error there propagates. [SRC:graphify/export.py:L54] [SRC:graphify/export.py:L81-L85] [SRC:graphify/export.py:L88] [SRC:graphify/export.py:L93-L100] [SRC:graphify/export.py:L101-L103] [QMD:graphify-kg-temporal:targeted-issues.md]

## Size cap and path checks

- Graph readers check the file against a 512 MiB cap before parsing it (`update`, the CLI query commands, `serve`). `GRAPHIFY_MAX_GRAPH_BYTES` replaces the cap, so it can raise or lower it. It takes plain bytes or a case-insensitive `MB`/`GB` suffix (binary: MiB/GiB). A blank, unparseable, zero or negative value falls back to 512 MiB. [SRC:graphify/security.py:L32] [SRC:graphify/security.py:L49-L66] [AST:graphify/security.py:L357]
- `validate_graph_path` keeps a graph path inside the nearest `graphify-out` folder and requires that folder to exist. [AST:graphify/security.py:L315]
- An oversized `graph.json` makes `update` refuse (exit 1); `--force` does not change that. [SRC:graphify/watch.py:L2196]

## Temporal context

- T2-future: #3769 (open). Incomplete protected backups are reported as successful. [QMD:graphify-kg-temporal:targeted-issues.md]
- T2-past: in 0.9.92, `cluster-only` and `label` call `backup_if_protected` before rewriting graph.json and GRAPH_REPORT.md, so the dated folder keeps the previous report (#2402). `graph.html` is still not in the backup set, the part that keeps #2402 open. [QMD:graphify-kg-temporal:targeted-issues.md] [SRC:graphify/cli.py:L2656-L2660] [SRC:graphify/export.py:L31]
- T2-past: 0.9.92 preserves parallel edges through the graph.json round-trip and shows them in MCP query output (#4500, #4503). [QMD:graphify-kg-temporal:changelog.md]
- T2-future: #4427 (open). The skill's own `generate()` calls do not pass `built_at_commit`, so their reports have no Graph Freshness section; `update` passes it. [QMD:graphify-kg-temporal:issues.md]
