# Pattern: what graphify scans and what it ignores

## Contents

- [Ignore sources and their order](#ignore-sources-and-their-order)
- [Matching semantics](#matching-semantics)
- [Git-tracked files](#git-tracked-files)
- [Built-in skips](#built-in-skips)
- [Sensitive files](#sensitive-files)
- [How rebuilds apply the rules](#how-rebuilds-apply-the-rules)
- [File classification](#file-classification)
- [The .graphifyrc file](#the-graphifyrc-file)
- [Temporal context](#temporal-context)

## Ignore sources and their order

`detect()` collects `(anchor directory, pattern)` pairs, lowest priority first. The last match wins. [AST:graphify/detect.py:L1921] [SRC:graphify/detect.py:L1490]

1. git's user-wide excludes file, anchored at the VCS root (only while gitignore is on). [SRC:graphify/detect.py:L1369]
2. `$GIT_DIR/info/exclude`, anchored at the VCS root (only while gitignore is on). [SRC:graphify/detect.py:L1327]
3. For each directory from the walk ceiling down to the scan root: that directory's `.gitignore`, then its `.graphifyignore`. [SRC:graphify/detect.py:L1463]
4. `--exclude` patterns, from the command line or the saved `.graphify_build.json`, anchored at the scan root. They are appended after sources 1-3, so they beat the ignore files of the scan root and its ancestors. [SRC:graphify/detect.py:L1985-L1992]
5. Below the scan root, each directory's `.gitignore` then `.graphifyignore`, appended as the walk reaches it. These rank above `--exclude`: a nested `!` rule can re-include a file an `--exclude` pattern matched, unless an excluded ancestor directory blocks it. [SRC:graphify/detect.py:L2052-L2056] [SRC:graphify/detect.py:L1463]

The walk ceiling is the nearest VCS root (`.git`, `.hg`, `.svn`, `_darcs` or `.fossil`), else the scan root itself, so no ignore file leaks in from an unrelated parent folder. A `.git` counts only when it is a real repository or a `gitdir:` file. [SRC:graphify/detect.py:L1177] [SRC:graphify/detect.py:L1221]

`--no-gitignore` (an `extract` flag, saved for later rebuilds) drops sources 1 and 2 and every `.gitignore`, keeping `.graphifyignore` and `--exclude`. [SRC:graphify/__main__.py:L969] [SRC:graphify/cli.py:L3869]

A leftover `.graphifyinclude` at the scan root prints a stderr warning that the file is no longer supported and that re-including takes `!` patterns in `.graphifyignore`. One in a subfolder is skipped as a built-in skip file, with no message. [SRC:graphify/detect.py:L1937] [SRC:graphify/detect.py:L967] [SRC:graphify/detect.py:L2105]

## Matching semantics

`_is_ignored` follows gitignore: [SRC:graphify/detect.py:L1679]

- the last matching pattern decides, and a `!` pattern re-includes;
- a `!` cannot rescue a file whose parent directory is already excluded;
- a pattern applies only to paths under its own anchor directory, and not to the anchor itself;
- a pattern without a slash matches one path component (the target's own name), and a trailing `/` matches directories only.

`.graphifyignore` is read after `.gitignore` in the same directory, so its rules, `!` negations included, win a conflict there. [SRC:graphify/detect.py:L1463]

## Git-tracked files

`detect()` asks `git ls-files` for the tracked set only when git-only rules exist before the walk starts: in git's user-wide excludes file, in `$GIT_DIR/info/exclude`, or in a `.gitignore` between the walk ceiling and the scan root. When it does, a tracked file is not dropped by a git-only rule, and the directories above it stay walkable. When the only git-only rules come from `.gitignore` files below the scan root, the tracked set is never fetched, so tracked files those rules match are dropped. `.graphifyignore` and `--exclude` rules exclude even tracked files. [SRC:graphify/detect.py:L1974-L1982] [SRC:graphify/detect.py:L2052-L2056] [SRC:graphify/detect.py:L1783] [AST:graphify/detect.py:L1921]

## Built-in skips

- **Directories never walked:** `venv`, `.venv`, `node_modules`, `__pycache__`, `.git`, `dist`, `build`, `target`, `site-packages`, `lib64`, the pytest, mypy and ruff caches, `.tox`, `.nox`, `.eggs`, `*.egg-info`, `graphify-out`, `lcov-report`, `visual-tests`, `visual-test`, `__snapshots__`, `storybook-static`, `dist-protected`, `.next`, `.nuxt`, `.turbo`, `.angular`, `.idea`, `.cache`, `.parcel-cache`, `.svelte-kit`, `.terraform`, `.serverless`, `.graphify`, `.obsidian`, `.smart-env` and `.worktrees`. [SRC:graphify/detect.py:L936] [SRC:graphify/detect.py:L948]
- **Skipped only on evidence:** `env`, `.env` and `*_env` with venv markers; `coverage` with report artefacts; `out` with build-output markers; `snapshots` holding `.snap` files or sitting directly under `__tests__` or `__test__`. Also `*_venv`, `worktrees` inside a dot folder, and graphify's own installed skill folders. [SRC:graphify/detect.py:L1113] [SRC:graphify/detect.py:L975] [SRC:graphify/detect.py:L1137]
- **Other dot folders are scanned**: `.github/` and `.claude/` are walked by default. [SRC:graphify/detect.py:L2058]
- **The configured output folder** is pruned even when `GRAPHIFY_OUT` renames it; only its `memory/` subfolder is scanned, as an extra root (see Temporal context). [AST:graphify/detect.py:L1921] [SRC:graphify/detect.py:L2072-L2080] [SRC:graphify/detect.py:L2006-L2010]
- **Files:** the lock files (`package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `Cargo.lock`, `poetry.lock`, `Gemfile.lock`, `composer.lock`, `go.sum`, `go.work.sum`) and `.graphifyinclude`. [SRC:graphify/detect.py:L961]
- **Files graphify installed into the project**, such as `.cursor/rules/graphify.mdc` and `.kiro/steering/graphify.md`. Files graphify only adds a section to, such as `CLAUDE.md` and `settings.json`, are not skipped. [SRC:graphify/detect.py:L987]

## Sensitive files

`_is_sensitive` drops a file, listed in `skipped_sensitive`, when: [SRC:graphify/detect.py:L287]

- a parent folder is `.ssh`, `.gnupg`, `.aws` or `.gcloud`; [SRC:graphify/detect.py:L119]
- a parent folder is `secrets`, `.secrets` or `credentials` and the file is not graphable source code; [SRC:graphify/detect.py:L127]
- the name is `.env` or `.envrc`, or starts with `.env.` or `.envrc.` (case-insensitive; `.environment` and `.env_local` do not match). Templates ending `.example`, `.sample`, `.template` or `.dist` are not treated as sensitive, but no file category knows those suffixes, so they land in `unclassified` rather than the graph. The other name matches are a key or certificate extension (`.pem`, `.key`, `.p12`, `.pfx`, `.cert`, `.crt`, `.der`, `.p8`), an SSH key name (`id_rsa`, `id_dsa`, `id_ecdsa`, `id_ed25519`, with or without `.pub`, so public keys are dropped too), `secring` (optionally `.gpg` or `.pgp`), or a name ending in a credential dotfile (`.netrc`, `.pgpass`, `.htpasswd`, `.npmrc`, `.pypirc`, `.git-credentials`, `.boto`); [SRC:graphify/detect.py:L134] [SRC:graphify/detect.py:L138] [SRC:graphify/detect.py:L142] [SRC:graphify/detect.py:L151] [SRC:graphify/detect.py:L2147-L2153]
- the name holds a load-bearing keyword (`credential`, `secret`, `passwd`, `password`, `private_key`, `token`, `service_account`), unless the file is source code or a multi-word prose note. [SRC:graphify/detect.py:L172]

Also skipped: symlink targets outside the scan root, and anything that is not a regular file (FIFOs, sockets, devices). [SRC:graphify/detect.py:L2130] [SRC:graphify/detect.py:L2142]

The rebuild's ignore check, `ignored_predicate`, leaves out the sensitive-file heuristic on purpose: only a real ignore rule counts as intent to drop nodes. [AST:graphify/detect.py:L1809]

## How rebuilds apply the rules

- `update`, `watch` and the hooks re-read the `--exclude` patterns and the gitignore setting saved by `extract`. [SRC:graphify/watch.py:L1789]
- A file that is still on disk, left the corpus, and matches a live rule is pruned like a deletion. `.graphifyignore` and `--exclude` matches count on every rebuild; `.gitignore` matches only on a full rebuild such as `graphify update`. [SRC:graphify/watch.py:L1110] [SRC:graphify/watch.py:L1816]
- A file that is still on disk, left the corpus and matches no rule keeps its nodes. For a source with an AST extractor (code, and also `.md`), it is counted in a `[graphify watch] fail-closed: kept N node(s) from M file(s) that left the scan corpus ...` note. A doc, paper or image source with no AST extractor is kept without a note. [SRC:graphify/watch.py:L1136] [SRC:graphify/watch.py:L1179] [SRC:graphify/watch.py:L1199]
- `graphify watch` loads the ignore patterns once at start-up, and drops events for dot paths and for the output folder. [SRC:graphify/watch.py:L2775] [SRC:graphify/watch.py:L2814] [SRC:graphify/watch.py:L2816]

## File classification

| Category | Extensions |
|----------|------------|
| code | 112 extensions, including `.py`, `.ts`, `.js`, `.go`, `.rs`, `.java`, `.c`, `.cpp`, `.rb`, `.php`, `.sh`, `.sql`, `.json`, `.tf` [SRC:graphify/detect.py:L48] |
| document | `.md`, `.mdx`, `.qmd`, `.skill`, `.txt`, `.rst`, `.html`, `.yaml`, `.yml`, `.j2`, `.jinja`, `.jinja2` [SRC:graphify/detect.py:L49] |
| paper | `.pdf` [SRC:graphify/detect.py:L50] |
| image | `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.svg` [SRC:graphify/detect.py:L51] |
| office (converted to Markdown) | `.docx`, `.xlsx` [SRC:graphify/detect.py:L52] |
| video and audio | `.mp4`, `.mov`, `.webm`, `.mkv`, `.avi`, `.m4v`, `.mp3`, `.wav`, `.m4a`, `.ogg` [SRC:graphify/detect.py:L53] |

A file goes to `unclassified` and is skipped when `classify_file` returns no type. That happens when its extension (after any `.graphifyrc` remap) is in no supported set, or when it has no extension and no recognised shebang. Shebangs are read only for extensionless files, so `run.xyz` with a Python shebang is unclassified. Package manifests (`pyproject.toml`, `Cargo.toml`, `go.mod`, `pom.xml`, `apm.yml`, `apm.yaml`) are classified as code by file name before the extension is checked; the name list itself lives in `graphify.manifest_ingest`, not read for this skill. A `.pdf` inside an Xcode asset catalog (`.xcassets`, `.imageset`, ...) is unclassified. [AST:graphify/detect.py:L518] [SRC:graphify/detect.py:L519-L525] [SRC:graphify/detect.py:L531-L533] [SRC:graphify/detect.py:L536-L539] [SRC:graphify/detect.py:L2153]

## The .graphifyrc file

`{scan root}/.graphifyrc`: one `key=value` per line, with `#` comments and blank lines ignored. [SRC:graphify/rcfile.py:L34] [AST:graphify/rcfile.py:L112]

```ini
# .graphifyrc
# A language name:
language.inc=php
# Or an extension graphify already knows:
language.tpl=.ts
# Baked into the git hooks (see Team setup):
viz_node_limit=0
```

This is the README's example. [SRC:README.md:L384]

- `viz_node_limit` is a non-negative integer. `graphify hook install` bakes it into the hooks as `GRAPHIFY_VIZ_NODE_LIMIT`, and a per-run env value still wins. [SRC:graphify/hooks.py:L1101] [SRC:graphify/hooks.py:L1104]
- `language.{ext}` maps an extension to a language name from `LANGUAGE_ALIASES` (for example `php`, `pascal`, `typescript`, `objc`), or to an extension graphify knows. [SRC:graphify/rcfile.py:L39] [AST:graphify/rcfile.py:L85]
- Unknown keys are ignored. A malformed line makes `load_graphifyrc` raise `ValueError` naming the line. A scan reports it once on stderr (`warning: ignoring .graphifyrc`) and continues without overrides. [SRC:graphify/rcfile.py:L117] [SRC:graphify/rcfile.py:L221]
- `hook status` reports a malformed file as a warning. `hook install` calls the same loader without catching the error. [SRC:graphify/hooks.py:L1101] [SRC:graphify/hooks.py:L1183]

## Temporal context

- T2-past: 0.9.92 treats only a valid `.git` as a VCS root, so a stray `.git` in a home folder no longer leaks its `.gitignore` into unrelated scans (#4444, #4464). [QMD:graphify-kg-temporal:changelog.md]
- T2-future: #3637 (open). `detect()` always scans `graphify-out/memory/` and applies no ignore rule to it; the 0.9.92 code still does this. [QMD:graphify-kg-temporal:targeted-issues.md] [SRC:graphify/detect.py:L2007]
