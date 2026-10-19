# Pattern: the `iwe` CLI and the query language

## Contents

- [Command set](#command-set)
- [Keys: named versus filtering](#keys-named-versus-filtering)
- [Selectors shared by read commands](#selectors-shared-by-read-commands)
- [Reading: find and retrieve](#reading-find-and-retrieve)
- [The query language](#the-query-language)
- [Writing: guards and --strict](#writing-guards-and---strict)
- [Exit codes](#exit-codes)
- [Agent routes bundled in the binary](#agent-routes-bundled-in-the-binary)
- [History](#history)

## Command set

- Public subcommands: `init`, `create`, `new`, `retrieve`, `find`, `count`, `normalize`, `tree`, `squash`, `export`, `schema`, `stats`, `rename`, `delete`, `extract`, `inline`, `update`, `attach`, `completions`, `docs`; `internal` is hidden. [SRC:crates/iwe/src/main.rs:L84] [SRC:crates/iwe/src/main.rs:L105] [SRC:crates/iwe/src/main.rs:L106]
- `iwe docs` prints the bundled references: `query`, `config`, `schema`, `agent`, `query-schema` (the last is generated from the binary's query schema). [SRC:crates/iwe/src/main.rs:L443] [SRC:crates/iwe/src/main.rs:L1668] [SRC:crates/iwe/src/main.rs:L1674]
- Global `-v/--verbose`: `1` logs INFO and `2` DEBUG to stderr. [SRC:crates/iwe/src/main.rs:L1451] [SRC:crates/iwe/src/main.rs:L1456]

## Keys: named versus filtering

- A key is the document's path relative to the workspace root without the extension (`folder/document`). [SRC:docs/keys.md:L5]
- Named keys must exist and fail the command up front (`retrieve`/`tree`/`export`/`update -k`, and the key of `delete`, `rename`, `extract`, `inline`, `squash`, `stats`, `attach`); filtering keys may match nothing (`find`/`count -k`, `--filter`, `$key`, anchors, `--exclude`, keys combined with `--lexical`/`--fuzzy`). [SRC:docs/keys.md:L17] [SRC:docs/keys.md:L18]

## Selectors shared by read commands

`FilterArgs` is flattened into `retrieve`, `find`, `count`, `tree`, `schema`, `export`: [SRC:crates/iwe/src/filter_args.rs:L47] [SRC:crates/iwe/src/main.rs:L578]

| Flag | Meaning |
|---|---|
| `--filter 'YAML'` | inline filter document, wrapped in `{}` [SRC:crates/iwe/src/filter_args.rs:L50] |
| `-k/--key KEY` | repeatable; 1 key `$eq`, 2+ `$in` [SRC:crates/iwe/src/filter_args.rs:L59] |
| `--includes`, `--included-by` | `KEY` or `KEY:DEPTH` inclusion anchors (0 = unbounded) [SRC:crates/iwe/src/filter_args.rs:L64] [SRC:crates/iwe/src/filter_args.rs:L71] |
| `--references`, `--referenced-by` | `KEY` or `KEY:DIST` reference anchors [SRC:crates/iwe/src/filter_args.rs:L78] [SRC:crates/iwe/src/filter_args.rs:L85] |
| `--roots` | only documents with no incoming inclusion edge [SRC:crates/iwe/src/filter_args.rs:L112] |
| `--max-depth`, `--max-distance` | defaults for anchors without a suffix (1; 0 = unbounded) [SRC:crates/iwe/src/filter_args.rs:L116] [SRC:crates/iwe/src/filter_args.rs:L122] |

## Reading: find and retrieve

- `find`: `--fuzzy` (title and key), `--lexical` (BM25 over title and body), `--limit`, `--max-tokens`, `--max-document-tokens`, `--project` (replaces defaults), `--add-fields` (extends them), `--blocks PRED`, `--matches REGEX`, `--sort field:1|-1`, `-f markdown|keys|json|yaml`. A bare positional pattern is deprecated and means fuzzy. [SRC:crates/iwe/src/main.rs:L608] [SRC:crates/iwe/src/main.rs:L611] [SRC:crates/iwe/src/main.rs:L637] [SRC:crates/iwe/src/main.rs:L647] [SRC:crates/iwe/src/main.rs:L654] [SRC:crates/iwe/src/main.rs:L660] [SRC:crates/iwe/src/main.rs:L603]
- `retrieve`: `--expand-includes`, `--expand-included-by`, `--expand-references`, `--expand-referenced-by` take a depth where bare = 1, `0` = unbounded and omitted = not followed; `--lexical`/`--fuzzy` seed the read; `--limit` caps seeds before expansion, `--max-documents` caps the documents returned after it; `--max-tokens`/`--max-document-tokens` cap content; `--backlinks` defaults to true; `--children` fills the `includes` edges; `-e/--exclude` drops keys. [SRC:crates/iwe/src/main.rs:L485] [SRC:crates/iwe/src/main.rs:L514] [SRC:crates/iwe/src/main.rs:L518] [SRC:crates/iwe/src/main.rs:L558] [SRC:crates/iwe/src/main.rs:L566] [SRC:crates/iwe/src/main.rs:L546] [SRC:crates/iwe/src/main.rs:L553] [SRC:crates/iwe/src/main.rs:L536]
- `expand_depth(0)` maps to `UNBOUNDED` (`u32::MAX`). [AST:crates/diwe/src/retrieve.rs:L68] [SRC:crates/diwe/src/retrieve.rs:L63]
- `--max-documents` counts the seed, so one seed plus one child needs at least `2`; `tree --depth` counts the root as level 1. [SRC:crates/iwe/docs/agent.md:L85] [SRC:crates/iwe/docs/agent.md:L107]

## The query language

- Operations: `find`, `count`, `update`, `delete`; `update` and `delete` require an explicit filter (`{}` on purpose selects everything). [SRC:crates/iwe/docs/query.md:L17] [SRC:crates/iwe/docs/query.md:L20] [SRC:crates/iwe/docs/query.md:L22]
- A filter is YAML: top-level keys are ANDed, a bare scalar against an array tests membership, and cross-type comparisons are always false (`priority: "3"` does not match an integer). [SRC:crates/iwe/docs/query.md:L27] [SRC:crates/iwe/docs/query.md:L37] [SRC:crates/iwe/docs/query.md:L39]
- Graph operators: `$key` (with `$in`, `$nin`, `$startsWith`), `$includes`/`$includedBy` (`maxDepth`, `minDepth`), `$references`/`$referencedBy` (`maxDistance`, `minDistance`), and `$content` for block membership. [SRC:crates/iwe/docs/query.md:L98] [SRC:crates/iwe/docs/query.md:L116] [SRC:crates/iwe/docs/query.md:L117] [SRC:crates/iwe/docs/query.md:L118] [SRC:crates/iwe/docs/query.md:L119] [SRC:crates/iwe/docs/query.md:L198]
- `$startsWith` is a plain string prefix: `notes` also matches `notes-archive/gamma`; write the trailing `/` for the directory. [SRC:crates/iwe/docs/query.md:L109] [SRC:crates/iwe/CHANGELOG.md:L84]
- Block operators for `update`: `$replace`, `$replaceText`, `$insertBefore`, `$insertAfter`, `$append`, `$delete` (CLI flags `--replace`, `--replace-text`, `--insert-before`, `--insert-after`, `--append`, `--delete`). [SRC:crates/iwe/src/main.rs:L1317] [SRC:crates/iwe/src/main.rs:L1324] [SRC:crates/iwe/src/main.rs:L1331] [SRC:crates/iwe/src/main.rs:L1338] [SRC:crates/iwe/src/main.rs:L1345] [SRC:crates/iwe/src/main.rs:L1352]
- `expect: N` or `expect: { min: M, max: N }` on each block operator, plus a document-level `--expect`; a violated guard fails the whole operation before anything is written. [SRC:crates/iwe/docs/query.md:L749] [SRC:crates/iwe/src/main.rs:L1357]

## Writing: guards and --strict

- `update` runs in **body mode** (`--content`, exactly one `-k`) or **mutation mode** (`--set`, `--unset`, block operators); combining them is an error. [SRC:crates/iwe/src/main.rs:L3757]
- `--strict` on `create` validates the document against its bound schemas before writing. On `update` and `delete` it runs the same schema gate on the pending writes and also requires expect guards. `delete --strict` requires the document-level `--expect`. `update --strict` in mutation mode (`--set`/`--unset`/block operators) requires the document-level `--expect` plus an inline `expect` on every block operator. `update --strict` in body mode (`--content`) checks no expect guard and ignores `--expect`; it only runs the schema gate. `--dry-run` is exempt from both checks. [SRC:crates/iwe/src/main.rs:L837] [SRC:crates/iwe/src/main.rs:L1363] [SRC:crates/iwe/src/main.rs:L3263] [SRC:crates/iwe/src/main.rs:L3838] [SRC:crates/iwe/src/main.rs:L3930] [SRC:crates/iwe/docs/query.md:L811]
- A strict schema failure prints `error: --strict blocked the write: schema validation failed` and exits `2`. [SRC:crates/iwe/src/main.rs:L3004] [SRC:crates/iwe/src/main.rs:L3008] [SRC:crates/iwe/src/main.rs:L3010]
- `create --if-exists`: `fail`, `skip`, and in template mode `suffix` or `override`; the default is `fail` except template mode without a key. `new` defaults to `suffix` (or `fail` with `--key`). [SRC:crates/iwe/src/main.rs:L833] [SRC:crates/iwe/src/main.rs:L874]
- `create`, `normalize --key` and `rename` refuse a key with a `..` segment or a leading `/` (since 0.24.1). [SRC:crates/iwe/CHANGELOG.md:L77]
- The agent policy's mutation recipe: preview, validate the affected keys and counts, then apply the identical arguments without `--dry-run`. `create` and `new` have no `--dry-run`. `create` uses `--strict` plus the `--if-exists` collision policy instead. `new` has no `--strict` flag, so it relies on `--if-exists` alone and its write is never schema-validated. [SRC:crates/iwe/docs/agent.md:L32] [SRC:crates/iwe/docs/agent.md:L112] [SRC:crates/iwe/src/main.rs:L835] [SRC:crates/iwe/src/main.rs:L851]

## Exit codes

| Code | When |
|---|---|
| `0` | success; an empty `find` result is not an error [SRC:docs/cli.md:L133] |
| `1` | runtime error, including a named key that is not found, an `--if-exists` value that content-mode `create` does not accept, and `iwe schema validate` finding invalid documents [SRC:docs/cli.md:L136] [SRC:crates/iwe/src/main.rs:L2724] [SRC:crates/iwe/src/main.rs:L2236] [SRC:crates/iwe/src/main.rs:L3001] |
| `2` | `init` on an existing `.iwe`; `internal claude enable` on an existing `MEMORY.md`; a `--strict` schema block, or a bound schema that fails to load or compile; `--strict` without a required expect guard on `update`/`delete`; a violated `--expect` on `update`/`delete`, with or without `--strict`; an invalid `--filter`/`--expect`/`--set`/`--sort`/`--blocks`/`--matches`/block-operator argument; template-variable errors on `create`; schema-binding errors in `iwe schema`; clap usage errors [SRC:crates/iwe/src/init.rs:L33] [SRC:crates/iwe/src/internal/claude/enable.rs:L152] [SRC:crates/iwe/src/main.rs:L3010] [SRC:crates/iwe/src/main.rs:L3016] [SRC:crates/iwe/src/main.rs:L3270] [SRC:crates/iwe/src/main.rs:L4039] [SRC:crates/iwe/src/main.rs:L3279] [SRC:crates/iwe/src/main.rs:L3948] [SRC:crates/iwe/src/main.rs:L2860] [SRC:crates/iwe/src/main.rs:L4008] [SRC:crates/iwe/src/main.rs:L3911] [SRC:crates/iwe/src/main.rs:L1941] [SRC:crates/iwe/src/main.rs:L1945] [SRC:crates/iwe/src/main.rs:L3734] [SRC:crates/iwe/src/main.rs:L2314] [SRC:crates/iwe/src/main.rs:L2977] [SRC:crates/iwe/src/main.rs:L1449] |

`docs/cli.md` documents only `0` and `1`; the code also exits `2`. An exit `2` from `iwe update --strict` is not necessarily a schema violation: read stderr, and treat any non-zero exit as failure. [SRC:docs/cli.md:L128]

## Agent routes bundled in the binary

`iwe docs agent` (the `graph` skill's whole body) holds the routing policy: one bounded `find` for identities (Cluster A), one bounded `retrieve` for prose (Cluster B), `count`/`schema` (C), `tree` (D), `create`/`new` (E), atomic `update` (F), structural refactors (G) and destructive work behind a dry run and confirmation (H). [SRC:crates/iwe/docs/agent.md:L53] [SRC:crates/iwe/docs/agent.md:L74] [SRC:crates/iwe/docs/agent.md:L95] [SRC:crates/iwe/docs/agent.md:L105] [SRC:crates/iwe/docs/agent.md:L110] [SRC:crates/iwe/docs/agent.md:L120] [SRC:crates/iwe/docs/agent.md:L141] [SRC:crates/iwe/docs/agent.md:L157] [EXT:https://raw.githubusercontent.com/iwe-org/skills/e3908762d5fa661fcba41d836d5fcb75dba4cebc/skills/graph/SKILL.md]

- `iwe normalize` rewrites the whole workspace in place and has no dry run. [SRC:crates/iwe/docs/agent.md:L203]
- The policy forbids installing, updating or repairing IWE from an agent run. [SRC:crates/iwe/docs/agent.md:L20]

## History

- **0.28.0 known bug (T2-future):** `iwe create` and `iwe normalize` drop a list-item continuation paragraph that follows a nested code fence with no blank line (#419); fixed on master by #420 after the tag. [QMD:iwe-kg-temporal:issues.md] [AST:crates/iwe/src/new.rs:L286] [AST:crates/iwe/src/new.rs:L267]
- **0.27.0:** `rename` keeps `[[Name]]` links when a note moves folders under the same file name, and otherwise writes the shortest name that resolves. [SRC:crates/iwe/CHANGELOG.md:L29]
- **0.25.0:** named-key commands report every unknown key in one error, `Documents not found: 'a', 'b'`. [QMD:iwe-kg-temporal:releases.md]
