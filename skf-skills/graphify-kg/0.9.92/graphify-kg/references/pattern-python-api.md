# Pattern: the Python module helpers

The importable functions of 11 of the in-scope modules, the ones the CLI builds on, read at tag `v0.9.92`. Each signature is the declaration as written, a `*` starting the keyword-only parameters. `graphify/__init__.py` imports nothing eagerly (its `__getattr__` maps a few names lazily), so import from the module itself, for example `from graphify.paths import out_path`. [SRC:graphify/__init__.py:L4]

## Contents

- [Output paths and atomic writes](#output-paths-and-atomic-writes)
- [File classification and Office conversion](#file-classification-and-office-conversion)
- [The manifest and incremental detection](#the-manifest-and-incremental-detection)
- [Language overrides](#language-overrides)
- [Graph export formats](#graph-export-formats)
- [URL safety and sanitizing](#url-safety-and-sanitizing)
- [Platform installers and uninstallers](#platform-installers-and-uninstallers)
- [The MCP server over HTTP](#the-mcp-server-over-http)
- [Report inputs, the query log and check-update](#report-inputs-the-query-log-and-check-update)
- [Temporal context](#temporal-context)

## Output paths and atomic writes

Module `graphify.paths`.

- `out_path(*parts: str) -> Path` returns `Path(GRAPHIFY_OUT, *parts)`, so it follows both a relative name (`graphify-out`) and an absolute `GRAPHIFY_OUT` override. [AST:graphify/paths.py:L431]
- `default_graph_json() -> str` returns `str(out_path("graph.json"))`, the fallback graph path that serve and the CLI read commands use, so a `GRAPHIFY_OUT` override holds everywhere. [AST:graphify/paths.py:L440]
- `load_node_link_graph(path_or_data)` loads a graph.json path or an already-parsed dict into a networkx graph. A path is checked against the graph size cap first. It accepts the raw `--no-cluster` writer's `edges` key as well as `links`, and restores the stored edge direction before loading. [AST:graphify/paths.py:L565]
- `restore_arc_direction(data: dict) -> dict` copies each link's `source` and `target` into `_src` and `_tgt`, keeping markers already there, so an undirected load does not lose the direction graph.json stores in arc order. [AST:graphify/paths.py:L546]
- `write_text_atomic(path: "str | Path", text: str) -> None` writes UTF-8 text to a `.gfy-*.tmp` file in the destination's folder, creating the folder when needed, then renames it into place. A symlinked destination is written through to its target. There is no fsync. [AST:graphify/paths.py:L188] [SRC:graphify/paths.py:L146] [SRC:graphify/paths.py:L147]
- `write_text_atomic_if_changed(path: "str | Path", text: str) -> bool` writes only when the decoded text differs from the file, and returns True when it wrote. A missing or non-UTF-8 file counts as changed. [AST:graphify/paths.py:L193]
- `write_json_atomic(path: "str | Path", obj, *, indent: "int | None" = None, ensure_ascii: bool = True, compact: bool = False) -> None` streams `json.dump` into the temporary file. `compact=True` writes one line with `,` and `:` separators, the graph.json form. [AST:graphify/paths.py:L216]
- `os_replace_with_fallback(src: "str | Path", dst: "str | Path") -> None` is `os.replace` with a copy-and-swap fallback. The fallback runs on any `PermissionError`, on any platform (the motivating cases are Windows WinError 5/32), and on an `OSError` whose `winerror` is 17. A symlink at `dst` is replaced, never followed, and any other error is raised again. [AST:graphify/paths.py:L56] [SRC:graphify/paths.py:L84]
- `is_absolute_any_platform(p: "str | Path | None") -> bool` is True when the string is absolute under POSIX or Windows rules (drive letter, UNC or root, either separator). It is meant for paths stored in graph.json, caches and manifests, which move between machines. [AST:graphify/paths.py:L450]
- `nfc(s: str) -> str` NFC-normalizes a path string: macOS reports file names in NFD, while manifests and graph `source_file` values are usually NFC. [AST:graphify/paths.py:L534]
- `stem_filename_budget(output_dir: "str | Path", *, reserve: int = 0, limit: int = 200) -> int` is the longest file-name stem an exporter may write into `output_dir`. It returns `limit` on POSIX, and on Windows for an extended-length `\\?\...` folder. Otherwise, on Windows, it returns `max(16, min(limit, 259 - len(absolute folder) - len(os.sep) - reserve - 3))`: what still fits in MAX_PATH after the folder, `reserve` and `.md`, but never less than 16, so in a very deep folder the path can still exceed MAX_PATH. [AST:graphify/paths.py:L499] [SRC:graphify/paths.py:L528] [SRC:graphify/paths.py:L531]
- `disambiguate_ambiguous_candidates(candidates: list[str], candidate_files: dict[str, str], call_site_file: str) -> str | None` breaks the tie for a bare-name call that matches several nodes: first the test or non-test preference, then path proximity. It returns a node id only when exactly one candidate survives. [AST:graphify/paths.py:L367]

```python
from graphify.paths import default_graph_json, load_node_link_graph, out_path, write_json_atomic

G = load_node_link_graph(default_graph_json())   # graphify-out/graph.json, or the GRAPHIFY_OUT override
write_json_atomic(out_path("notes", "counts.json"), {"nodes": G.number_of_nodes()}, indent=2)
```

## File classification and Office conversion

Module `graphify.detect`. `classify_file` returns a `FileType` (SKILL.md, Key Types).

- `classify_file(path: Path) -> FileType | None` sends package manifests and `.blade.php` files to `CODE`. Otherwise it classifies by the effective suffix, so a `.graphifyrc` `language.{ext}` override counts: code, paper (None for a PDF inside an Xcode asset catalog), image, document (`PAPER` instead when at least 3 academic-paper signals, such as arXiv, `doi:`, abstract, journal or numbered `[N]` citations, appear in the file's first 3000 characters; this is a content heuristic and does not check whether the file was converted), Office and Google Workspace files as `DOCUMENT`, and video. A file with no suffix is classified by its shebang, and anything else is None. [AST:graphify/detect.py:L518] [SRC:graphify/detect.py:L543-L547] [SRC:graphify/detect.py:L323-L329] [SRC:graphify/detect.py:L274]
- `count_words(path: Path) -> int` counts the words of a PDF, `.docx` or `.xlsx` through the converters below, else of the file's text. A FIFO, socket or device node counts 0 instead of blocking the scan, and any error gives 0. [AST:graphify/detect.py:L895]
- `extract_pdf_text(path: Path) -> str` joins the page text `pypdf` extracts. It returns "" for a file over the 50 MiB cap, on an error, and without `pypdf`, which it reports once on stderr with the `graphifyy[pdf]` extra to install. [AST:graphify/detect.py:L562] [SRC:graphify/detect.py:L64]
- `docx_to_markdown(path: Path) -> str` converts with python-docx, headings and list items included. It returns "" for a file that fails the zip-bomb checks, without the library, or on an error. [AST:graphify/detect.py:L661]
- `xlsx_to_markdown(path: Path) -> str` writes each non-empty sheet as `## Sheet: {name}` and a markdown table, read with openpyxl in read-only, values-only mode. It returns "" in the same cases as `docx_to_markdown`. [AST:graphify/detect.py:L708]
- `xlsx_extract_structure(path: Path) -> dict` returns `{"nodes": [...], "edges": [...]}` for the sheets, named tables and column headers, and empty lists without openpyxl or when the workbook does not load. Its own comment says this path is not wired into the dispatcher. [AST:graphify/detect.py:L740] [SRC:graphify/detect.py:L759]
- `convert_office_file(path: Path, out_dir: Path, root: "Path | None" = None) -> Path | None` writes a `.docx` or `.xlsx` as `{stem}_{hash}.md` in `out_dir`, the 8-character hash taken from the NFC path relative to `root` (default `out_dir.parent.parent`). It rewrites the sidecar only when the source is newer, and returns None for another suffix, for empty text or without the library. `detect()` converts into `graphify-out/converted/`. [AST:graphify/detect.py:L830] [SRC:graphify/detect.py:L2117]

```python
from pathlib import Path
from graphify.detect import classify_file, convert_office_file, count_words

spec = Path("docs/spec.docx")
ftype = classify_file(spec)                      # FileType.DOCUMENT
sidecar = convert_office_file(spec, Path("graphify-out/converted"), root=Path("."))
words = count_words(spec)
```

## The manifest and incremental detection

Module `graphify.detect`. `manifest.json` itself is described in `references/pattern-output-layout.md`.

- `load_manifest(manifest_path: str = _MANIFEST_PATH, *, root: Path | None = None) -> dict` reads `graphify-out/manifest.json` by default and returns {} on any error. With `root`, relative keys come back absolute. Keys are NFC-normalized. [AST:graphify/detect.py:L2472] [SRC:graphify/detect.py:L37]
- `save_manifest(files: dict[str, list[str]], manifest_path: str = _MANIFEST_PATH, *, kind: str = "both", root: Path | None = None, scan_corpus: set[str] | list[str] | None = None, clear_semantic: set[str] | list[str] | None = None, clear_ast: set[str] | list[str] | None = None) -> None` stamps each file's mtime and content hashes. `kind="ast"`, which `graphify update` writes, stamps `ast_hash` and keeps a `semantic_hash` only for unchanged content; `"semantic"` stamps `semantic_hash`; `"both"` stamps both. With `root`, keys are written relative and posix-style. With `root`, `scan_corpus` (the raw full scan) drops the rows of in-root files that still exist on disk but that the scan no longer includes, and also the absolute rows of a previous checkout. Out-of-root rows are kept, and without `root` it prunes nothing. Rows of files deleted from disk are dropped in every case. [AST:graphify/detect.py:L2559] [SRC:graphify/detect.py:L2670] [SRC:graphify/detect.py:L2727]
- `detect_incremental(root: Path, manifest_path: str = _MANIFEST_PATH, *, follow_symlinks: bool | None = None, google_workspace: bool | None = None, kind: str = "semantic", extra_excludes: list[str] | None = None, gitignore: bool = True, cache_root: Path | None = None) -> dict` returns `detect()`'s result plus `incremental`, `new_files`, `unchanged_files`, `new_total`, `deleted_files` and `excluded_files`. A file is new when it has no manifest row, when its `.graphifyrc` language override changed, when the hash `kind` names is missing, or when its mtime moved and its MD5 no longer matches that hash. Legacy mtime-only rows compare the mtime alone. On the fast path, an unchanged mtime with that hash present counts as unchanged and nothing is hashed. The one exception is a row stamped in the same mtime tick as the file (2 s for whole-second mtimes, 0.05 s otherwise), which is re-hashed. With no manifest, every file is new. [AST:graphify/detect.py:L2842] [SRC:graphify/detect.py:L2926] [SRC:graphify/detect.py:L2947] [SRC:graphify/detect.py:L2950] [SRC:graphify/detect.py:L2959] [SRC:graphify/detect.py:L2895] [SRC:graphify/detect.py:L3010]

`graphify update` does not call `detect_incremental`: it rebuilds the full corpus. [SRC:graphify/cli.py:L2821]

```python
from pathlib import Path
from graphify.detect import detect_incremental, load_manifest

changes = detect_incremental(Path("."), kind="ast")   # compare by ast_hash; the default "semantic" compares semantic_hash
for ftype, paths in changes["new_files"].items():
    print(ftype, len(paths))
print(len(changes["deleted_files"]), "deleted;", len(load_manifest(root=Path("."))), "files in the manifest")
```

## Language overrides

Module `graphify.rcfile`. The `.graphifyrc` format is in `references/pattern-ignore-rules.md`.

- `parse_language_value(value: str) -> str` resolves the right side of `language.{ext}=`: a `LANGUAGE_ALIASES` name (any case) or a dotted extension graphify knows as code or document. Anything else raises `ValueError`. [AST:graphify/rcfile.py:L85]
- `activate_language_overrides(root: Path) -> dict[str, str]` loads `{root}/.graphifyrc` and makes its `languages` the active overrides, then returns them. A malformed file prints `[graphify] warning: ignoring .graphifyrc: ...` once per root and activates none. [AST:graphify/rcfile.py:L207] [SRC:graphify/rcfile.py:L221]
- `set_language_overrides(mapping: dict[str, str] | None) -> None` replaces this thread's overrides, lower-casing and dotting each key and target. [AST:graphify/rcfile.py:L194]
- `get_language_overrides() -> dict[str, str]` returns a copy of this thread's overrides. [AST:graphify/rcfile.py:L203]
- `effective_suffix(path: Path | str) -> str` returns the override target for a remapped extension, else the real suffix with its case kept. [AST:graphify/rcfile.py:L227]
- `cache_salt(path: Path | str) -> str | None` returns `"language={target}"` for a remapped file, else None, so an AST cache entry is not reused after the file's language changes. [AST:graphify/rcfile.py:L241]

```python
from pathlib import Path
from graphify.rcfile import activate_language_overrides, cache_salt, effective_suffix, parse_language_value

parse_language_value("PHP")               # ".php"
activate_language_overrides(Path("."))    # {".inc": ".php"} when .graphifyrc has language.inc=php
effective_suffix("lib/util.inc")          # ".php"
cache_salt("lib/util.inc")                # "language=.php"
```

## Graph export formats

Module `graphify.export`. `communities` maps a community id to its node ids, as `.graphify_analysis.json` stores it.

- `to_obsidian(G: nx.Graph, communities: dict[int, list[str]], output_dir: str, community_labels: dict[int, str] | None = None, cohesion: dict[int, float] | None = None) -> int` writes an Obsidian vault: one note per node with `[[wikilinks]]`, plus one `_COMMUNITY_{name}.md` overview per community. It returns the number of notes written. [AST:graphify/export.py:L760]
- `to_canvas(G: nx.Graph, communities: dict[int, list[str]], output_path: str, community_labels: dict[int, str] | None = None, node_filenames: dict[str, str] | None = None) -> None` writes an Obsidian Canvas. Communities become groups laid out in a grid, with every node in one group when `communities` is empty, and nodes become cards. Of the edges between canvas nodes, it keeps only the 200 with the highest `weight` (default 1.0), each labelled `relation [confidence]`, or `[confidence]` when there is no relation. `graphify export obsidian` writes the vault to `graphify-out/obsidian/` and the canvas inside it as `graph.canvas`. [AST:graphify/export.py:L1113] [SRC:graphify/export.py:L1146] [SRC:graphify/export.py:L1273] [SRC:graphify/export.py:L1276] [SRC:graphify/export.py:L1280] [SRC:graphify/cli.py:L3239] [SRC:graphify/cli.py:L3497]
- `to_graphml(G: nx.Graph, communities: dict[int, list[str]], output_path: str) -> None` writes GraphML for Gephi or yEd, with the community as a node attribute and the edge `confidence` as an edge attribute. `graphify export graphml` writes `graph.graphml`. [AST:graphify/export.py:L1292] [SRC:graphify/cli.py:L3528]
- `to_svg(G: nx.Graph, communities: dict[int, list[str]], output_path: str, community_labels: dict[int, str] | None = None, figsize: tuple[int, int] = (20, 14)) -> None` draws a spring layout with matplotlib, node size by degree and community colours. `graphify export svg` writes `graph.svg`. [AST:graphify/export.py:L1369] [SRC:graphify/export.py:L1384] [SRC:graphify/cli.py:L3522]
- `to_cypher(G: nx.Graph, output_path: str) -> None` writes one `MERGE` per node, labelled by its `file_type`, then one `MATCH ... MERGE (a)-[:{RELATION} {confidence: ...}]->(b)` per edge in its stored direction. `graphify export neo4j` and `graphify export falkordb` write it as `cypher.txt` when `--push` is not given. [AST:graphify/export.py:L552] [SRC:graphify/cli.py:L3542]
- `attach_hyperedges(G: nx.Graph, hyperedges: list) -> None` appends hyperedges to `G.graph["hyperedges"]`, skipping any without an `id` and any whose id is already there. [AST:graphify/export.py:L200]
- `prune_dangling_edges(graph_data: dict) -> tuple[dict, int]` drops the edges, under `links` or else `edges`, whose source or target is not a node, and returns the data with the number dropped. [AST:graphify/export.py:L492]
- `existing_graph_node_count(path: "str | Path")` returns the node count of an existing graph.json; None when it is absent, empty or over the size cap; and the `MALFORMED_GRAPH` sentinel when it is present but cannot be parsed, which callers treat as a refusal. The raw `--no-cluster` write path uses it for its shrink check. [AST:graphify/export.py:L245] [SRC:graphify/export.py:L242]

```python
import json
from graphify.export import existing_graph_node_count, prune_dangling_edges, to_graphml
from graphify.paths import default_graph_json, load_node_link_graph

before = existing_graph_node_count(default_graph_json())
with open(default_graph_json(), encoding="utf-8") as fh:
    data, dropped = prune_dangling_edges(json.load(fh))
G = load_node_link_graph(data)
communities: dict[int, list[str]] = {}
for node, attrs in G.nodes(data=True):
    communities.setdefault(attrs.get("community") or 0, []).append(node)
to_graphml(G, communities, "graphify-out/graph.graphml")
```

## URL safety and sanitizing

Module `graphify.security`.

- `validate_url(url: str) -> str` returns the URL when its scheme is `http` or `https` and its host is no cloud-metadata name and resolves to no private or reserved address. Otherwise, a DNS failure included, it raises `ValueError`. [AST:graphify/security.py:L103]
- `safe_fetch(url: str, max_bytes: int = _MAX_FETCH_BYTES, timeout: int = 30) -> bytes` fetches a validated URL, validates each redirect again, and stops reading at 52,428,800 bytes by default. It raises `ValueError` for a refused URL or redirect, `urllib.error.HTTPError` for a non-2xx status, `urllib.error.URLError` for a connection failure and `OSError` past the cap. [AST:graphify/security.py:L258] [SRC:graphify/security.py:L21]
- `safe_fetch_text(url: str, max_bytes: int = _MAX_TEXT_BYTES, timeout: int = 15) -> str` is `safe_fetch` with a 10,485,760-byte default cap, decoded as UTF-8 with bad bytes replaced. [AST:graphify/security.py:L302] [SRC:graphify/security.py:L22]
- `sanitize_label(text: str | None) -> str` removes control characters and cuts the text to 256 characters; None gives "". The result is safe in JSON and plain text; wrap it in `html.escape()` for HTML. [AST:graphify/security.py:L394] [SRC:graphify/security.py:L391]
- `sanitize_metadata(metadata: Mapping[str, Any] | None) -> dict[str, object]` returns a JSON-safe copy: control characters removed, HTML-sensitive characters escaped, long strings and lists capped, and entries whose cleaned key is empty dropped. [AST:graphify/security.py:L442]

```python
from graphify.security import safe_fetch_text, sanitize_label, validate_url

validate_url("https://example.com/paper")        # returned unchanged
validate_url("file:///etc/passwd")               # raises ValueError: only http and https
page = safe_fetch_text("https://example.com/")   # at most 10,485,760 bytes, decoded
label = sanitize_label("Title\x00 with a control character")
```

## Platform installers and uninstallers

Modules `graphify.install` and `graphify.hooks`. The Claude Code side is in `references/pattern-claude-code-integration.md`.

- `claude_uninstall(project_dir: Path | None = None, *, project: bool = False, remove_user_skill: bool | None = None) -> None` runs for `graphify claude uninstall`. It removes the skill tree, the graphify section of `CLAUDE.md` and of its local-only variants, and the PreToolUse hook. A bare call removes the user-global skill; `project_dir` or `project=True` limits the removal to that project unless `remove_user_skill=True`. [AST:graphify/install.py:L2291] [SRC:graphify/install.py:L2597]
- `gemini_install(project_dir: Path | None = None, *, project: bool = False) -> None` runs for `graphify gemini install [--project]`. It copies the skill, writes the graphify section of `GEMINI.md` and installs the BeforeTool hook in `.gemini/settings.json` again. [AST:graphify/install.py:L1026] [SRC:graphify/install.py:L1101] [SRC:graphify/install.py:L2613]
- `gemini_uninstall(project_dir: Path | None = None, *, project: bool = False, remove_user_skill: bool | None = None) -> None` removes the skill under the same scope rules. When `GEMINI.md` exists and holds the graphify section, it also removes that section, deleting a file left empty unless it is a symlink, and then removes the BeforeTool hook from `.gemini/settings.json`. If `GEMINI.md` is missing or has no graphify section, it returns early and the hook stays. [AST:graphify/install.py:L1131] [SRC:graphify/install.py:L1149] [SRC:graphify/install.py:L1164]
- `vscode_install(project_dir: Path | None = None) -> None` runs for `graphify vscode install`. It installs the VS Code Copilot Chat skill at `~/.copilot/skills/graphify/SKILL.md` and adds a graphify section to `.github/copilot-instructions.md`. [AST:graphify/install.py:L1174] [SRC:graphify/install.py:L1173] [SRC:graphify/install.py:L1206]
- `vscode_uninstall(project_dir: Path | None = None) -> None` removes that skill with its `references/` and version stamp, and the instructions section. [AST:graphify/install.py:L1227]
- `codebuddy_install(project_dir: Path | None = None) -> None` runs for `graphify codebuddy install`. It copies the skill, writes the `CODEBUDDY.md` section and adds a PreToolUse hook to `.codebuddy/settings.json`. [AST:graphify/install.py:L2360] [SRC:graphify/install.py:L2381]
- `codebuddy_uninstall(project_dir: Path | None = None, *, project: bool = False, remove_user_skill: bool | None = None) -> None` removes the skill tree and the `CODEBUDDY.md` section under the same scope rules. [AST:graphify/install.py:L2422]
- `uninstall_all(project_dir: Path | None = None, purge: bool = False) -> None` runs for `graphify uninstall` without `--project`. It first refuses an unsafe `--purge` target, before changing anything (exit 1). It then runs a fixed list: the claude, codebuddy and gemini uninstallers with `remove_user_skill=True`; the vscode, cursor, kiro and antigravity uninstallers; the AGENTS.md section cleanup; removal of the amp and agents user-scope skills; and removal of the OpenCode plugin and the Codex hook. Next it removes the git hooks and, with `purge`, deletes the output folder. The list leaves out the kilo, pi and devin uninstallers, so their user-scope skills stay, and so do kilo's command file and plugin. The user-scope skills that `install(platform=P)` copies for codex, opencode, aider, claw, droid, trae, trae-cn, hermes, kiro and kimi stay too, and no uninstaller removes them: the per-platform uninstalls for those platforms only clean `AGENTS.md` (plus the Codex hook or the OpenCode plugin), and the kiro one removes only the project skill. [AST:graphify/install.py:L2236] [SRC:graphify/install.py:L2255] [SRC:graphify/install.py:L2584] [SRC:graphify/install.py:L938] [SRC:graphify/install.py:L2747-L2760] [SRC:graphify/install.py:L1313]
- `uninstall(path: Path = Path(".")) -> str`, in `graphify.hooks`, runs for `graphify hook uninstall`. It removes the post-commit, post-checkout, post-merge and post-rewrite blocks and unregisters the merge driver, and returns one status line for each. Outside a git repository it raises `RuntimeError`. [AST:graphify/hooks.py:L1134] [SRC:graphify/hooks.py:L1138] [SRC:graphify/cli.py:L1525]

```bash
graphify gemini install --project   # gemini_install(project=True)
graphify vscode install             # vscode_install()
graphify hook uninstall             # prints the status lines uninstall(Path(".")) returns
graphify uninstall --purge          # uninstall_all(purge=True)
```

## The MCP server over HTTP

Module `graphify.serve`. Flags and tools are in `references/pattern-claude-code-integration.md`.

- `serve_http(graph_path: str | None = None, *, host: str = "127.0.0.1", port: int = 8080, api_key: str | None = None, path: str = "/mcp", json_response: bool = False, stateless: bool = False, session_timeout: float | None = 3600.0) -> None` serves the stdio server's tools over Streamable HTTP at `http://{host}:{port}{path}`. `graphify-mcp --transport http` calls it. `api_key` turns on the `Authorization: Bearer` or `X-API-Key` check, and a blank key counts as none. `serve_http` does not read `GRAPHIFY_API_KEY` itself. Only `serve._main()` (the `graphify-mcp` script, or `python -m graphify.serve`) reads it, as the default of `--api-key`. A Python caller has to pass `api_key=os.environ.get("GRAPHIFY_API_KEY")` explicitly, or the server runs without auth. [AST:graphify/serve.py:L2901] [SRC:graphify/serve.py:L3014] [SRC:graphify/serve.py:L2932] [SRC:graphify/serve.py:L2990] [SRC:graphify/serve.py:L3029]
- `find_node_ambiguity(G: nx.Graph, label: str) -> list[str]` returns one node id per source file when the best match tier for `label` spans several files, else `[]`. Several matches inside one file are not ambiguity. [AST:graphify/serve.py:L1733]
- `ToolError` (SKILL.md, Key Types) is what a tool handler raises to return an `isError: true` result. [AST:graphify/serve.py:L34]

```python
from graphify.serve import serve_http

# what `graphify-mcp --transport http` runs, here with an explicit graph and key; needs graphifyy[mcp]
serve_http("graphify-out/graph.json", host="127.0.0.1", port=8080, api_key="change-me")
```

## Report inputs, the query log and check-update

Modules `graphify.report`, `graphify.querylog` and `graphify.watch`.

- `load_learning_for_report(graph_path) -> dict | None` returns `{"overlay": ..., "dead_ends": [...]}` from the `.graphify_learning.json` overlay beside the graph and the notes in its `memory/` folder. It returns None when neither exists and never raises. The update rebuild and the `cluster-only` / `label` path pass its result to `generate()` as `learning`. [AST:graphify/report.py:L40] [SRC:graphify/watch.py:L2513] [SRC:graphify/cli.py:L2698]
- `log_query(*, kind: str, question: str, corpus: str, result: str | None = None, nodes_returned: int | None = None, duration_ms: float | None = None, **extra: Any) -> None` appends one JSON line when the query log is enabled. Each line always has `ts`, `kind`, `question`, `corpus` and `nodes_returned`. It adds `result_chars` only when a `result` is passed, `duration_ms` (rounded to 3 places) only when one is given, each extra that is not None, and the full `response` only when a `result` is passed and `GRAPHIFY_QUERY_LOG_RESPONSES` is `1`, `true` or `yes`. The `path` and `explain` commands pass neither, so their lines lack `result_chars` and `duration_ms`. It never raises. [AST:graphify/querylog.py:L43] [SRC:graphify/querylog.py:L60] [SRC:graphify/querylog.py:L74] [SRC:graphify/querylog.py:L34]
- `nodes_from_result(result: str) -> int | None` returns N from the first `N nodes found` in a result, else None. `log_query` uses it when no count is given. [AST:graphify/querylog.py:L38]
- `check_update(watch_path: Path) -> bool` runs for `graphify check-update {path}`. When `{path}/graphify-out/needs_update` exists, it prints that non-code changes are pending and that `/graphify --update` applies them. It always returns True, so a cron job does not alarm. [AST:graphify/watch.py:L2674] [SRC:graphify/watch.py:L2682] [SRC:graphify/cli.py:L2862]

```bash
GRAPHIFY_QUERY_LOG_ENABLE=1 graphify query "what calls to_json"   # appends to ~/.cache/graphify-queries.log
graphify check-update .                                          # exits 0 whether or not an update is pending
```

## Temporal context

- T2-future: #2459 (open). `detect_incremental` defaults to `kind="semantic"` and over-reports changed files; it drives the skill's `/graphify --update`, not the CLI's `update`. [QMD:graphify-kg-temporal:targeted-issues.md]
