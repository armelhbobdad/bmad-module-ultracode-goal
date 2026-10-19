# Pattern: the `.iwe/config.toml` contract (version 4)

## Contents

- [Where the config is read](#where-the-config-is-read)
- [Version and in-place migration](#version-and-in-place-migration)
- [Tables and defaults](#tables-and-defaults)
- [Templates and variables](#templates-and-variables)
- [Commands and actions](#commands-and-actions)
- [Schema bindings](#schema-bindings)
- [Docs versus code at 0.28.0](#docs-versus-code-at-0280)
- [History](#history)

## Where the config is read

- `load_config()` builds `current_dir/.iwe/config.toml` and reads only that path: no parent directory is searched. [AST:crates/diwe/src/config.rs:L470] [SRC:crates/diwe/src/config.rs:L474]
- A missing file is not an error: `Configuration::template()` is used instead. [SRC:crates/diwe/src/config.rs:L501]
- The marker is the `.iwe` directory (`IWE_MARKER`), the file name `config.toml`. [SRC:crates/diwe/src/config.rs:L22] [SRC:crates/diwe/src/config.rs:L21]
- `iwes` and `iwec` call `load_config()` at startup and exit 1 if it fails. [SRC:crates/iwes/src/main.rs:L52] [SRC:crates/iwec/src/main.rs:L57] `iwe` loads the config per subcommand. The document commands go through `get_configuration()`, which exits 1 on a load error. `internal claude enable` calls `load_config()` directly. `internal claude session`, `internal claude policy` and the hooks go through `enter_memory_store()`. [SRC:crates/iwe/src/main.rs:L2882] [SRC:crates/iwe/src/internal/claude/enable.rs:L140] [SRC:crates/iwe/src/internal/claude/hook/store.rs:L114] `iwe init` reads the config only when its interactive screen turns memory on: it then calls `enable_memory` on the config it just wrote. On an existing `.iwe` it exits 2 without reading the config. [SRC:crates/iwe/src/init.rs:L82] [SRC:crates/iwe/src/init/screen.rs:L89] [SRC:crates/iwe/src/init.rs:L227] [SRC:crates/iwe/src/internal/claude/enable.rs:L140] `iwe docs`, `iwe completions`, `iwe internal claude digest` and `iwe internal claude prompt` never load it. [SRC:crates/iwe/src/main.rs:L1489] [SRC:crates/iwe/src/main.rs:L1490] [SRC:crates/iwe/src/main.rs:L1503] [SRC:crates/iwe/src/main.rs:L1532] [SRC:crates/iwe/src/main.rs:L1668] [SRC:crates/iwe/src/main.rs:L1703] When the hook payload gives a `cwd`, `enter_memory_store()` first chdirs into it. If that `cwd` is not an absolute existing directory, it returns None and leaves memory off. [SRC:crates/iwe/src/internal/claude/hook/store.rs:L108] [SRC:crates/iwe/src/internal/claude/hook/store.rs:L111]
- The workspace's documents live in `workspace.path` under the project root (empty = the root itself). [AST:crates/diwe/src/config.rs:L457] [SRC:crates/iwe/docs/config.md:L41]
- Schemas are read from `.iwe/schemas/` next to the config. [AST:crates/diwe/src/config.rs:L453] [SRC:crates/diwe/src/config.rs:L454]

## Version and in-place migration

- `load_config()` runs a private migration step (not exported from `diwe::config`) that reads `version` (a missing one counts as `0`) and applies each step below the current number: v0→1 adds action `type` and the default code actions, v1→2 adds `markdown.refs_extension` and the `link` action, v2→3 turns `[models]` into `[commands]` and renames `model`/`prompt_template` on transform actions, v3→4 renames `[library]` to `[workspace]`. [SRC:crates/diwe/src/config.rs:L487] [SRC:crates/diwe/src/config.rs:L505] [SRC:crates/diwe/src/config.rs:L513] [SRC:crates/diwe/src/config.rs:L519] [SRC:crates/diwe/src/config.rs:L528] [SRC:crates/diwe/src/config.rs:L537] [SRC:crates/diwe/src/config.rs:L545] [AST:crates/diwe/src/config.rs:L709] [AST:crates/diwe/src/config.rs:L752]
- When any step ran, the upgraded text is **written back to `./.iwe/config.toml`** before it is parsed, even if that parse then fails. [SRC:crates/diwe/src/config.rs:L552] [SRC:crates/diwe/src/config.rs:L561] [SRC:crates/diwe/src/config.rs:L489] Every command that loads the config rewrites an older file in place. That covers the `iwe` document commands (via `get_configuration()`), `iwe internal claude enable`/`session`/`policy`, `iwes`, `iwec`, the SessionStart hook, and the PostToolUse hook for a Write/Edit/MultiEdit of a `.md`/`.dj` file, or for a Bash command with an `iwe create|update|rename|delete|attach` segment lacking `--strict` or an `iwe create|new` segment lacking `--dry-run`. [SRC:crates/iwe/src/main.rs:L2882] [SRC:crates/iwe/src/internal/claude/hook/post_tool.rs:L37] [SRC:crates/iwe/src/internal/claude/hook/post_tool.rs:L41] [SRC:crates/iwe/src/internal/claude/hook/post_tool.rs:L12] [SRC:crates/iwe/src/internal/claude/hook/post_tool.rs:L13] [SRC:crates/iwe/src/internal/claude/hook/post_tool.rs:L176] [SRC:crates/iwe/src/internal/claude/hook/post_tool.rs:L182] [SRC:crates/iwe/src/internal/claude/hook/post_tool.rs:L67] [SRC:crates/iwe/src/internal/claude/hook/post_tool.rs:L71] So `iwe update ... --strict` or `iwe delete ... --strict` on its own never loads or migrates the config from the hook, while `iwe new` does. `iwe init`, `iwe docs`, `iwe completions`, `iwe internal claude digest` and `iwe internal claude prompt` never migrate an existing file. [SRC:crates/iwe/src/init.rs:L82] [SRC:crates/iwe/src/main.rs:L1489] [SRC:crates/iwe/src/main.rs:L1490] [SRC:crates/iwe/src/main.rs:L1503] [SRC:crates/iwe/src/main.rs:L1532]
- `migrate_v3_to_v4()` drops `[library]` when `[workspace]` already exists, otherwise moves `[library]` to `[workspace]` at the same position. [SRC:crates/diwe/src/config.rs:L756] [SRC:crates/diwe/src/config.rs:L760]
- After migration the TOML is deserialized into `Configuration`; every table carries `deny_unknown_fields`, so a misspelled key fails the load with `unknown field`. [SRC:crates/diwe/src/config.rs:L80] [SRC:crates/diwe/src/config.rs:L25]
- `[library]` is still accepted as an alias of `[workspace]` when reading. [SRC:crates/diwe/src/config.rs:L89]

## Tables and defaults

`Configuration` holds `version`, `format`, `markdown`, `djot`, `workspace`, `completion`, `search`, `commands`, `actions`, `templates`, `schemas`. [SRC:crates/diwe/src/config.rs:L81]

| Table / key | Default | Notes |
|---|---|---|
| `format` | `markdown` | `markdown` (`.md`) or `djot` (`.dj`) [SRC:crates/liwe/src/model/config.rs:L32] [SRC:crates/liwe/src/model/config.rs:L41] |
| `[markdown] refs_extension` | `""` | extension written inside links [SRC:crates/liwe/src/model/config.rs:L16] |
| `[markdown] refs_path` | `relative` | or `absolute` [SRC:crates/liwe/src/model/config.rs:L189] |
| `[markdown] refs_text` | `preserve` | or `normalize` [SRC:crates/liwe/src/model/config.rs:L197] |
| `[markdown] date_format` | `%b %d, %Y` | dates written into document content, including `{{today}}` in a `document_template`, in a markdown-format workspace. With `format = "djot"`, `create --template`/`new` use `[djot] date_format` instead (same `%b %d, %Y` default), while `iwe attach` always uses `[markdown] date_format`. `{{today}}` in a `key_template` uses `[workspace] date_format` instead, and `iwe attach` always renders its key `{{today}}` as `%Y-%m-%d`. [SRC:crates/liwe/src/model/config.rs:L215] [SRC:crates/iwe/src/new.rs:L193] [SRC:crates/diwe/src/config.rs:L240] [SRC:crates/diwe/src/config.rs:L241] [SRC:crates/liwe/src/model/config.rs:L77] [SRC:crates/iwe/src/main.rs:L4249] [SRC:crates/iwe/src/new.rs:L184] [SRC:crates/iwe/src/main.rs:L4229] [SRC:crates/iwe/docs/config.md:L182] |
| `[markdown] wiki_link_path` | `preserve` | `full`, `short` [SRC:crates/liwe/src/model/config.rs:L180] |
| `[workspace] path` | `""` | documents directory under the root [SRC:crates/diwe/src/config.rs:L28] |
| `[workspace] date_format` | `%Y-%m-%d` | key dates (`DEFAULT_KEY_DATE_FORMAT`) [SRC:crates/liwe/src/model/config.rs:L10] |
| `[search] language` | `english` | BM25 stemmer [SRC:crates/diwe/src/config.rs:L55] |
| `[completion]` | unset | `link_format`, `min_prefix_length`, `trigger_characters` [SRC:crates/diwe/src/config.rs:L41] |

`Configuration::default()` carries `version: Some(1)`; only `template()` sets `4`. Code that builds a default configuration rather than the template is not version 4. [SRC:crates/diwe/src/config.rs:L222] [SRC:crates/diwe/src/config.rs:L252]

## Templates and variables

- `template()` ships `[templates.default]` with `key_template = "{{slug}}"`. [SRC:crates/diwe/src/config.rs:L436] [SRC:crates/diwe/src/config.rs:L439]
- Reserved variables are `slug`, `today`, `now`, `id`; `title` names the title, `body` the prose slot, and `content` is the legacy alias of `body`. [SRC:crates/iwe/src/new.rs:L23] [SRC:crates/iwe/src/new.rs:L22] [SRC:crates/iwe/src/new.rs:L20] [SRC:crates/iwe/src/new.rs:L21]
- `iwe create --template NAME` takes variables from `--vars-yaml` or `--vars-json` (you can pass only one of them; values keep their types) and from repeatable `--var NAME=VALUE` (VALUE kept as a string). `--var` is applied last, so it overrides a variable of the same name from either source. These cases exit 2 instead: passing both `body` and its legacy alias `content` in any mix of sources (`'body' and 'content' name the same variable; pass only one`, the two names in the order seen), a reserved name (`slug`, `today`, `now`, `id`), or a null value. `--set FIELD=VALUE` (VALUE parsed as YAML; the last one for a field wins) writes a frontmatter field above the rendered document. All four flags require `--template`. [SRC:crates/iwe/src/main.rs:L797] [SRC:crates/iwe/src/main.rs:L804] [SRC:crates/iwe/src/main.rs:L815] [SRC:crates/iwe/src/main.rs:L823] [SRC:crates/iwe/src/main.rs:L2374] [SRC:crates/iwe/src/main.rs:L2391] [SRC:crates/iwe/src/main.rs:L2400] [SRC:crates/iwe/src/main.rs:L2413] [SRC:crates/iwe/docs/config.md:L179]

## Commands and actions

- `[commands.NAME]` has `run` (required), `args`, `cwd`, `env`, `shell`, `timeout_seconds`. The template defines `[commands.default]` as `run = "claude -p"` with a 120 s timeout. [SRC:crates/diwe/src/config.rs:L107] [SRC:crates/diwe/src/config.rs:L108] [SRC:crates/diwe/src/config.rs:L113] [SRC:crates/diwe/src/config.rs:L259] [SRC:crates/diwe/src/config.rs:L260]
- `[actions.NAME]` is tagged by `type`: `transform`, `attach`, `sort`, `inline`, `extract`, `extract_all`, `link`. [SRC:crates/diwe/src/config.rs:L118] [SRC:crates/diwe/src/config.rs:L119] [SRC:crates/diwe/src/config.rs:L131]
- The template's actions: `today` (attach), `rewrite`, `expand`, `keywords`, `emoji` (transform via `default`), `sort`, `sort_desc`, `inline_section`, `inline_quote`, `extract`, `extract_all`, `link`. [SRC:crates/diwe/src/config.rs:L266] [SRC:crates/diwe/src/config.rs:L275] [SRC:crates/diwe/src/config.rs:L301] [SRC:crates/diwe/src/config.rs:L327] [SRC:crates/diwe/src/config.rs:L352] [SRC:crates/diwe/src/config.rs:L376] [SRC:crates/diwe/src/config.rs:L384] [SRC:crates/diwe/src/config.rs:L392] [SRC:crates/diwe/src/config.rs:L401] [SRC:crates/diwe/src/config.rs:L410] [SRC:crates/diwe/src/config.rs:L419] [SRC:crates/diwe/src/config.rs:L428]
- `iwes` turns each configured action into an LSP code action, alongside the built-in list/section/delete actions. [AST:crates/iwes/src/router/server/actions.rs:L262] [SRC:crates/iwes/src/router/server/actions.rs:L267] [SRC:crates/iwes/src/router/server/actions.rs:L276]

## Schema bindings

- `[schemas.NAME]` takes exactly one key, `match`: a glob string or a list of globs against document keys. [SRC:crates/diwe/src/config.rs:L215] [SRC:crates/diwe/src/config.rs:L216] [SRC:crates/diwe/src/config.rs:L199]
- `[schemas.person]` resolves to `.iwe/schemas/person.yaml`; a document is validated against every binding whose `match` hits, and a document no binding matches is unvalidated. [SRC:crates/iwe/docs/config.md:L290] [SRC:crates/iwe/docs/config.md:L295]
- `iwe schema validate` checks the store against the bindings; `--schema-file` bypasses them and `--explain` prints the binding trace. [SRC:crates/iwe/src/main.rs:L981] [SRC:crates/iwe/src/main.rs:L988]
- The memory starter binds `[schemas.memory] match = "**"`. For documents that carry `created`, its schema enforces the `^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}$` pattern on `created`. It checks `session` only when the key is present, and then it must be a non-empty string. A memory document with `created` but no `session` passes `--strict`. [SRC:crates/iwe/templates/claude/enable/starter.toml:L9] [SRC:crates/iwe/templates/claude/enable/starter.toml:L10] [SRC:crates/iwe/templates/claude/enable/schemas/memory.yaml:L6] [SRC:crates/iwe/templates/claude/enable/schemas/memory.yaml:L11] [SRC:crates/iwe/templates/claude/enable/schemas/memory.yaml:L15]

## Docs versus code at 0.28.0

`crates/iwe/docs/config.md` (printed by `iwe docs config`) shows `version = 3` in its full example and says "current is `3`". The binary's template writes `4` and every load upgrades to `4`, so write `version = 4`. [SRC:crates/iwe/docs/config.md:L12] [SRC:crates/iwe/docs/config.md:L77] [SRC:crates/iwe/src/help.rs:L121] [SRC:crates/diwe/src/config.rs:L252] [SRC:crates/diwe/src/config.rs:L545]

## History

- **0.25.0 (T2-past):** `[library]` became `[workspace]`, migrated in place to `version = 4` the first time a command reads the config; `iwe init --workspace` replaced `--library`, which is kept as a hidden alias; `iwe init --json` reports the detected directory as `evidence.workspace_path` (was `library_path`), and its settings map keys are now `workspace.path`, `workspace.date_format` and `workspace.frontmatter_document_title` (were `library.*`). [QMD:iwe-kg-temporal:releases.md] [SRC:crates/iwe/CHANGELOG.md:L53] [SRC:crates/iwe/CHANGELOG.md:L54] [SRC:crates/iwe/CHANGELOG.md:L55] [SRC:crates/iwe/CHANGELOG.md:L65]
- **0.28.0:** `find --sort` and query `sort` collate text by `workspace.locale` (then the system locale, then English); the `binary` collation restores codepoint order. [SRC:crates/iwe/CHANGELOG.md:L14] [SRC:crates/iwe/CHANGELOG.md:L18] [SRC:crates/iwe/CHANGELOG.md:L19] [SRC:crates/liwe/src/collation.rs:L56] [QMD:iwe-kg-temporal:releases.md]
