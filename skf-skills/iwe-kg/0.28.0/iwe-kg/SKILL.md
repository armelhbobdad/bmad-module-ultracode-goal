---
name: iwe-kg
description: >
  IWE 0.28.0 markdown knowledge-graph tooling for agent memory: the iwe CLI and its query
  language, the iwes LSP server, the iwec MCP server, the version-4 .iwe/config.toml contract
  and the hidden iwe internal claude commands behind the IWE Claude Code plugin's hooks and
  memory skills. Use when reading or writing this repository's IWE workspace or memory, editing
  .iwe/config.toml or .iwe/schemas, wiring iwes or iwec into an editor or MCP client, or
  debugging the plugin's SessionStart and PostToolUse hooks and session records. Not for IWE
  versions other than 0.28.0, and not for changing the iwe-org/skills plugin itself.
---

# IWE 0.28.0 — CLI, servers, config contract and memory internals

## Overview

Reference for the IWE Cargo workspace at tag `iwe-v0.28.0` of <https://github.com/iwe-org/iwe> (commit `5edc6d9a`, workspace version `0.28.0`), compiled at Forge tier **Deep**. [SRC:Cargo.toml:L11]

- **Binaries:** `iwe` (CLI), `iwes` (LSP server), `iwec` (MCP server), built from workspace members `crates/liwe`, `crates/diwe`, `crates/iwe`, `crates/iwes`, `crates/iwec`. [SRC:Cargo.toml:L2] [SRC:docs/how-to-install.md:L38] [SRC:docs/how-to-install.md:L39] [SRC:docs/how-to-install.md:L40]
- **Surface:** 37 Rust files in scope; 227 exports — 90 functions AST-verified (T1), 137 structs, enums, traits, constants and type aliases read at their declaration lines (T1-low); issues, PRs and release notes add T2 context; the plugin wiring from `iwe-org/skills` (commit `e3908762`) is T3.
- **Shape:** reference-app — the value is the wiring contract: which binary reads which file from which directory, and what each command writes.
- **Code over docs:** `crates/iwe/docs/config.md` still says config version `3` is current, but `Configuration::template()` writes `version = 4` and `load_config()` upgrades every config it reads to `4` through a private migration step; this skill follows the code. [SRC:crates/iwe/docs/config.md:L77] [SRC:crates/diwe/src/config.rs:L252] [SRC:crates/diwe/src/config.rs:L487] [SRC:crates/diwe/src/config.rs:L545]

## Quick Start

The CLI is the authoritative route into a workspace; `iwe docs agent` prints the bundled agent policy for the installed binary. [SRC:crates/iwe/docs/agent.md:L3] [SRC:crates/iwe/src/main.rs:L1673]

```bash
iwe init --auto                                    # detect conventions, write .iwe/config.toml
iwe find --lexical "<distinctive terms>" --limit 5 --project 'key=$key,title=$title' --format json
iwe retrieve --lexical "<all named entities> <shared topic>" --limit 1 --max-documents 1 --max-tokens 5000 --max-document-tokens 4500 --format json
iwe create <key> --content '<frontmatter-and-body>' --strict --if-exists fail
iwe update --key <key> --unset <field> --expect 1 --strict --dry-run
iwe delete <key> --expect 1 --strict --dry-run --format keys
```

Sources: [SRC:crates/iwe/help/init/after_help.txt:L7] [SRC:crates/iwe/docs/agent.md:L58] [SRC:crates/iwe/docs/agent.md:L79] [SRC:crates/iwe/docs/agent.md:L114] [SRC:crates/iwe/docs/agent.md:L137] [SRC:crates/iwe/docs/agent.md:L159]

- Every command that loads `.iwe/config.toml` reads it from the **current directory only**; there is no parent walk, and with no file the built-in template applies. [AST:crates/diwe/src/config.rs:L470] [SRC:crates/diwe/src/config.rs:L474] [SRC:crates/diwe/src/config.rs:L501]
- `--strict` on `create`, `update` and `delete` validates the documents the write would produce against the bound schemas. It exits **2** with `error: --strict blocked the write: schema validation failed`, and also exits 2 when a bound schema fails to load or compile. On `update`/`delete`, `--strict` does nothing under `--dry-run`: neither the schema gate nor the guard check runs, so a strict dry-run does not prove the apply will pass. On apply, `delete --strict` requires the document-level `--expect`, and `update --strict` in mutation mode (`--set`/`--unset`/block operators) requires `--expect` plus an inline `expect` on every block operator. Body-mode `update -k KEY --content ... --strict` only runs the schema gate. [SRC:crates/iwe/src/main.rs:L2200] [SRC:crates/iwe/src/main.rs:L3008] [SRC:crates/iwe/src/main.rs:L3012] [SRC:crates/iwe/src/main.rs:L3263] [SRC:crates/iwe/src/main.rs:L3330] [SRC:crates/iwe/src/main.rs:L3838] [SRC:crates/iwe/src/main.rs:L3930] [SRC:crates/iwe/src/main.rs:L4021]
- For the result and budget bounds (`--limit`, `--max-documents`, `--max-tokens`, `--max-document-tokens`), the `retrieve --expand-*` depths and the `--max-depth`/`--max-distance`/`KEY:DEPTH` anchors, `0` means unlimited, and the agent policy says never to pass it. `tree --depth 0` is not unlimited: markdown/keys output prints nothing, and json/yaml output lists the roots without children. The agent policy's default result limit is 20. [SRC:crates/iwe/docs/agent.md:L28] [SRC:crates/iwe/docs/agent.md:L30] [SRC:crates/iwe/src/main.rs:L564] [SRC:crates/iwe/src/main.rs:L614] [SRC:crates/iwe/src/main.rs:L485] [SRC:crates/iwe/src/filter_args.rs:L116] [SRC:crates/iwe/src/main.rs:L2651] [SRC:crates/iwe/src/main.rs:L2598]

<!-- [MANUAL:additional-notes] -->
<!-- Add custom notes here. This section is preserved during skill updates. -->
<!-- [/MANUAL:additional-notes] -->

## Adoption Steps

1. **Make the directory a workspace.** `iwe init` writes `.iwe/config.toml` and exits `2` when `.iwe` already exists; without a terminal it behaves as `--auto`; `--defaults` skips detection. [SRC:crates/iwe/src/init.rs:L82] [SRC:crates/iwe/src/init.rs:L33] [SRC:crates/iwe/help/init/long_about.txt:L11] [SRC:crates/iwe/src/main.rs:L733]
2. **Write the config for version 4.** Use `[workspace]` (not `[library]`), keep `version = 4`, and use only known keys: every table is `deny_unknown_fields`. A lower version is migrated **in place** by the first command that reads it. [SRC:crates/diwe/src/config.rs:L89] [SRC:crates/diwe/src/config.rs:L80] [SRC:crates/diwe/src/config.rs:L561] [SRC:crates/iwe/CHANGELOG.md:L53]
3. **Bind schemas by key glob.** `[schemas.NAME] match = "glob"` validates every matching document against `.iwe/schemas/NAME.yaml`; every matching binding applies. [SRC:crates/diwe/src/config.rs:L215] [SRC:crates/diwe/src/config.rs:L454] [SRC:crates/iwe/docs/config.md:L290] [SRC:crates/iwe/docs/config.md:L295]
4. **Write through `iwe`, guarded.** Preview with `--dry-run`, pin `--expect`, re-run the identical command without `--dry-run`; `create` and `new` are collision-guarded with `--if-exists` instead. [SRC:crates/iwe/docs/agent.md:L32] [SRC:crates/iwe/docs/query.md:L811]
5. **Switch memory on.** `iwe internal claude enable` (hidden, unstable) runs `iwe init --defaults` when needed, writes `MEMORY.md`, exits `2` when it already exists. [SRC:crates/iwe/src/internal/claude/enable.rs:L113] [SRC:crates/iwe/src/internal/claude/enable.rs:L226] [SRC:crates/iwe/src/internal/claude/enable.rs:L151] [SRC:crates/iwe/src/main.rs:L180]
6. **Wire the plugin hooks.** SessionStart runs `iwe internal claude hook session-start`; PostToolUse on `Write|Edit|MultiEdit|Bash` runs `hook post-tool`; both are no-ops without `iwe` on `PATH`. [EXT:https://raw.githubusercontent.com/iwe-org/skills/e3908762d5fa661fcba41d836d5fcb75dba4cebc/hooks/hooks.json]
7. **Serve agents and editors from the workspace root.** `iwec` and `iwes` both read `.iwe/config.toml` from their current directory and load the graph from that directory joined with `workspace.path` (the directory itself when it is unset). [SRC:crates/iwec/src/main.rs:L57] [SRC:crates/iwec/src/main.rs:L62] [SRC:crates/iwec/src/lib.rs:L1836] [SRC:crates/diwe/src/config.rs:L457] [SRC:crates/iwes/src/main.rs:L52] [SRC:crates/iwes/src/main.rs:L133] [SRC:crates/iwes/src/main.rs:L139]

## Pattern Surface

| # | File | Surface | Purpose |
|---|------|---------|---------|
| 1 | `crates/diwe/src/config.rs` | `load_config()` | Read `./.iwe/config.toml`, migrate, else template [AST:crates/diwe/src/config.rs:L470] [SRC:crates/diwe/src/config.rs:L487] |
| 2 | `crates/diwe/src/config.rs` | `migrate_v2_to_v3()` / `migrate_v3_to_v4()` | Public steps of the v0→v4 upgrade that `load_config()` runs through a private dispatcher and writes back to disk [SRC:crates/diwe/src/config.rs:L505] [AST:crates/diwe/src/config.rs:L709] [AST:crates/diwe/src/config.rs:L752] |
| 3 | `crates/diwe/src/config.rs` | `Configuration` keys | Top-level `version` and `format` (a string, `markdown` or `djot`); tables `markdown`, `djot`, `workspace` (alias `library`), `completion`, `search`, `commands`, `actions`, `templates`, `schemas` [SRC:crates/diwe/src/config.rs:L81] [SRC:crates/diwe/src/config.rs:L89] [SRC:crates/liwe/src/model/config.rs:L32] |
| 4 | `crates/diwe/src/config.rs` | `[schemas.NAME] match` | Key-glob schema bindings, `.iwe/schemas/NAME.yaml` [SRC:crates/diwe/src/config.rs:L215] [AST:crates/diwe/src/config.rs:L453] |
| 5 | `crates/iwe/src/main.rs` | `Command` enum | 20 public subcommands plus hidden `internal` [SRC:crates/iwe/src/main.rs:L84] [SRC:crates/iwe/src/main.rs:L106] |
| 6 | `crates/iwe/src/filter_args.rs` | `FilterArgs` | `--filter`, `-k`, `--includes`, `--included-by`, `--references`, `--referenced-by`, `--roots` [SRC:crates/iwe/src/filter_args.rs:L47] |
| 7 | `crates/iwe/docs/query.md` | filter / update / expect | YAML query language and guards [SRC:crates/iwe/docs/query.md:L17] [SRC:crates/iwe/docs/query.md:L749] |
| 8 | `crates/iwe/src/init.rs` | `init_workspace()` | `.iwe/` marker, config write, agent artifacts [AST:crates/iwe/src/init.rs:L80] |
| 9 | `crates/iwe/src/init/agents.rs` | `write_agent_instructions()` / `register_mcp()` | `AGENTS.md` section and `.mcp.json` `iwe` server [AST:crates/iwe/src/init/agents.rs:L44] [AST:crates/iwe/src/init/agents.rs:L69] |
| 10 | `crates/iwe/src/main.rs` | `internal claude` tree | `digest`, `enable`, `hook`, `session`, `prompt`, `policy` [SRC:crates/iwe/src/main.rs:L132] |
| 11 | `crates/iwe/src/internal/claude/enable.rs` | `enable_memory()` | Write `MEMORY.md`, starter or typed ontology [AST:crates/iwe/src/internal/claude/enable.rs:L49] |
| 12 | `crates/iwe/src/internal/claude/hook/store.rs` | `enter_memory_store()` | Memory is on iff config loads and key `MEMORY` exists [AST:crates/iwe/src/internal/claude/hook/store.rs:L105] [SRC:crates/iwe/src/internal/claude/hook/store.rs:L126] |
| 13 | `crates/iwe/src/internal/claude/hook/index.rs` | `render_memory_index()` | SessionStart `<iwe-memory>` block [AST:crates/iwe/src/internal/claude/hook/index.rs:L52] [SRC:crates/iwe/templates/claude/memory_index.md.jinja:L1] |
| 14 | `crates/iwe/src/internal/claude/hook/post_tool.rs` | `post_tool_report()` | PostToolUse schema check, `--strict` nudge, similar-page notice [AST:crates/iwe/src/internal/claude/hook/post_tool.rs:L22] |
| 15 | `crates/iwe/src/internal/claude/session.rs` | `session brief/list/read/stage/inbox/complete/adopt` | Distill bookkeeping [SRC:crates/iwe/src/main.rs:L238] |
| 16 | `crates/iwe/src/internal/claude/record.rs` | `.iwe/claude/sessions/ID.yaml` | Session records outside the graph [SRC:crates/iwe/src/internal/claude/record.rs:L9] [AST:crates/iwe/src/internal/claude/record.rs:L245] |
| 17 | `crates/iwe/templates/claude/enable/starter.md` | `MEMORY.md` knobs and sections | `distill`, `injection`; sections read by name [SRC:crates/iwe/templates/claude/enable/starter.md:L7] [SRC:crates/iwe/src/internal/claude/session.rs:L46] |
| 18 | `crates/iwec/src/lib.rs` | 14 tools, 3 prompts, 4 resources | MCP surface over the graph at the start directory joined with `workspace.path` [SRC:crates/iwec/src/lib.rs:L1713] [SRC:crates/iwec/src/lib.rs:L1836] [SRC:crates/diwe/src/config.rs:L457] |
| 19 | `crates/iwec/src/main.rs` | `--transport stdio\|http` | stdio default, HTTP at `127.0.0.1:8000/mcp` [SRC:crates/iwec/src/main.rs:L23] [SRC:crates/iwec/src/main.rs:L83] |
| 20 | `crates/iwes/src/main.rs` | LSP capabilities | Code actions from `[actions]`, completion triggers [SRC:crates/iwes/src/main.rs:L96] [SRC:crates/iwes/src/main.rs:L66] |
| 21 | `npm/mcp/package.json` | `@iwe-org/mcp` | `npx -y @iwe-org/mcp` runs `iwec` over stdio [SRC:npm/mcp/README.md:L13] [SRC:npm/mcp/bin/iwe-mcp.js:L2] |
| 22 | `hooks/hooks.json` (iwe-org/skills) | SessionStart / PostToolUse | Plugin hook commands [EXT:https://raw.githubusercontent.com/iwe-org/skills/e3908762d5fa661fcba41d836d5fcb75dba4cebc/hooks/hooks.json] |

## Migration & Deprecation Warnings

- `write_document` / `normalize`: 0.28.0 silently drops a list-item continuation paragraph placed directly after a nested code fence (issue #419); the fix (#420, `9f3fa99`) is on master after the tag. Put a blank line after such a fence. [QMD:iwe-kg-temporal:issues.md] [AST:crates/iwe/src/new.rs:L286]
- `IweServer`: two IWE MCP servers on one client both report server name `iwe` and the same instructions; per-workspace naming (#410) is open, not in 0.28.0. [QMD:iwe-kg-temporal:issues.md] [SRC:crates/iwec/src/lib.rs:L1711]
- `[library]` → `[workspace]` (0.25.0): old configs are rewritten in place to `version = 4`; `--library` survives only as a hidden alias of `--workspace`. [QMD:iwe-kg-temporal:releases.md] [SRC:crates/iwe/src/main.rs:L747]

See Full API Reference for migration details (`references/pattern-config-contract.md`, `references/pattern-memory-internal.md`).

## CORRECTION

**Source:** [QMD:iwe-kg-temporal:releases.md]
**Pattern:** deprecated
**Affected:** LibraryOptions, library_path_in
**Detail:** - `LibraryOptions` and `library_path_in` retained as deprecated aliases.

## CORRECTION

**Source:** [QMD:iwe-kg-temporal:releases.md]
**Pattern:** Changed
**Affected:** DocumentFinder
**Detail:** - `DocumentFinder` sorts text fields with the graph's `TitleCollator` (codepoint order unless the graph was given a localized collator)

## Key Types

- **Exit codes:** `0` success; `1` runtime error, including a named document that is not found, an `--if-exists` value that content-mode `create` does not accept, and `iwe schema validate` finding invalid documents. `2` covers `init` on an existing `.iwe`, `internal claude enable` on an existing `MEMORY.md` and a `--strict` schema block, and also refused or malformed requests: `--strict` without a required expect guard on `update`/`delete`, a violated `--expect` on `update`/`delete` (with or without `--strict`), an invalid `--filter`/`--expect`/`--set`/`--sort`/`--blocks`/`--matches`/block-operator argument, template-variable errors on `create`, schema-binding/compile errors, and clap usage errors. An exit `2` from `iwe update --strict` is not necessarily a schema violation: read stderr, and treat any non-zero exit as failure. `docs/cli.md` lists only `0` and `1`. [SRC:crates/iwe/src/init.rs:L31] [SRC:crates/iwe/src/init.rs:L33] [SRC:crates/iwe/src/main.rs:L180] [SRC:crates/iwe/src/internal/claude/enable.rs:L152] [SRC:crates/iwe/src/main.rs:L3010] [SRC:crates/iwe/src/main.rs:L3016] [SRC:crates/iwe/src/main.rs:L3270] [SRC:crates/iwe/src/main.rs:L3279] [SRC:crates/iwe/src/main.rs:L3948] [SRC:crates/iwe/src/main.rs:L4039] [SRC:crates/iwe/src/main.rs:L2860] [SRC:crates/iwe/src/main.rs:L4008] [SRC:crates/iwe/src/main.rs:L3911] [SRC:crates/iwe/src/main.rs:L1941] [SRC:crates/iwe/src/main.rs:L1945] [SRC:crates/iwe/src/main.rs:L3734] [SRC:crates/iwe/src/main.rs:L2314] [SRC:crates/iwe/src/main.rs:L2977] [SRC:crates/iwe/src/main.rs:L1449] [SRC:crates/iwe/src/main.rs:L2724] [SRC:crates/iwe/src/main.rs:L2236] [SRC:crates/iwe/src/main.rs:L3001] [SRC:docs/cli.md:L128]
- **Config `version`:** template writes `4`; the private migration step `load_config()` runs reads a missing version as `0`. [SRC:crates/diwe/src/config.rs:L252] [SRC:crates/diwe/src/config.rs:L487] [SRC:crates/diwe/src/config.rs:L513]
- **`format`:** `markdown` (`.md`, default) or `djot` (`.dj`). [SRC:crates/liwe/src/model/config.rs:L32] [SRC:crates/liwe/src/model/config.rs:L41] [SRC:crates/liwe/src/model/config.rs:L42]
- **Action `type`:** `transform`, `attach`, `sort`, `inline`, `extract`, `extract_all`, `link`. [SRC:crates/diwe/src/config.rs:L118]
- **`IfExists` (CLI):** `suffix`, `override`, `skip`, `fail`, with per-command defaults. `iwe create KEY --content ...` defaults to `fail` and accepts only `fail` or `skip`; `suffix` and `override` exit `1`. `iwe create --template` defaults to `fail` with a key and `suffix` without one. `iwe new` defaults to `suffix`, or to `fail` when `--key` is given. MCP `iwe_create` accepts only `fail` (the default) or `skip`. [SRC:crates/iwe/src/new.rs:L28] [SRC:crates/iwe/src/main.rs:L831] [SRC:crates/iwe/src/main.rs:L2230] [SRC:crates/iwe/src/main.rs:L2236] [SRC:crates/iwe/src/main.rs:L2243] [SRC:crates/iwe/src/main.rs:L2283] [SRC:crates/iwe/src/main.rs:L2120] [SRC:crates/iwec/src/lib.rs:L441] [SRC:crates/iwec/src/lib.rs:L459]
- **Query operations:** `find`, `count`, `update`, `delete`; `update`/`delete` need an explicit filter. [SRC:crates/iwe/docs/query.md:L17] [SRC:crates/iwe/docs/query.md:L22]
- **Memory knobs (MEMORY.md frontmatter):** `distill.max_chunk_size` 25000, `distill.max_proposals` 5, `distill.remind_after_days` 7 (`-1` never, `0` every session), `injection` slices with `heading`, `filter`, `sort`, `limit`, `max_tokens`. [SRC:crates/iwe/src/internal/claude/session.rs:L28] [SRC:crates/iwe/src/internal/claude/session.rs:L29] [SRC:crates/iwe/src/internal/claude/session.rs:L30] [SRC:crates/iwe/src/internal/claude/session.rs:L993] [SRC:crates/iwe/src/internal/claude/hook/store.rs:L330]
- **`ProposalStatus`:** `pending`, `written`, `rejected`. [SRC:crates/iwe/src/internal/claude/record.rs:L59]
- **Session states (`session list`):** `current`, `active` (another session whose last timestamped transcript entry is under 30 minutes old, or whose file was modified in that window when no entry stamp was read), `pending`, `done`, `adopted`. [SRC:crates/iwe/src/internal/claude/session.rs:L40] [SRC:crates/iwe/src/internal/claude/session.rs:L85] [SRC:crates/iwe/src/internal/claude/session.rs:L1121] [SRC:crates/iwe/src/internal/claude/session.rs:L1322]

## Architecture at a Glance

- **liwe** — graph model, keys, query language; **diwe** — config load/migrate, find/retrieve engines, schema validation, watcher, shared by all three binaries. [SRC:crates/diwe/src/lib.rs:L1] [AST:crates/diwe/src/config.rs:L470]
- **iwe** — CLI; `iwe internal` is hidden with `about = "Unstable helper commands, no compatibility guarantee"`. Its `claude` subcommand (`about = "Claude Code integration commands"`) is reachable only through it, so treat every `iwe internal ...` form here as tied to 0.28.0. [SRC:crates/iwe/src/main.rs:L105] [SRC:crates/iwe/src/main.rs:L111] [SRC:crates/iwe/src/main.rs:L112] [SRC:crates/iwe/src/main.rs:L125]
- **iwes** — stdio LSP server; `IWE_DEBUG` logs to `iwe.log` in the cwd. [SRC:crates/iwes/src/main.rs:L57] [SRC:crates/iwes/src/main.rs:L39]
- **iwec** — rmcp MCP server over stdio or Streamable HTTP, watching the workspace for file changes. [SRC:crates/iwec/src/main.rs:L65] [AST:crates/iwec/src/watcher.rs:L38]
- **Plugin (`iwe-org/skills` 0.14.0)** — ships only `hooks.json` and frontmatter-only skills whose bodies come from `iwe internal claude prompt NAME` and `iwe docs agent`. [EXT:https://raw.githubusercontent.com/iwe-org/skills/e3908762d5fa661fcba41d836d5fcb75dba4cebc/.claude-plugin/plugin.json] [EXT:https://raw.githubusercontent.com/iwe-org/skills/e3908762d5fa661fcba41d836d5fcb75dba4cebc/README.md]

## CLI

| Command group | Subcommands |
|---|---|
| Setup and reference | `init`, `completions`, `docs [query\|config\|schema\|agent\|query-schema]` |
| Read | `find`, `retrieve`, `count`, `tree`, `stats [similarity]`, `schema [validate]`, `export`, `squash` |
| Write | `create`, `new`, `update`, `delete`, `rename`, `extract`, `inline`, `attach`, `normalize` |
| Hidden (unstable) | `internal claude {digest, enable, hook {session-start, post-tool}, session {brief, list, read, stage, inbox, complete, adopt}, prompt {init, distill, reflect}, policy}` |

Sources: [SRC:crates/iwe/src/main.rs:L84] [SRC:crates/iwe/src/main.rs:L443] [SRC:crates/iwe/src/main.rs:L132] [SRC:crates/iwe/src/main.rs:L238] [SRC:crates/iwe/src/main.rs:L405] [SRC:crates/iwe/src/main.rs:L160]

## Full API Reference

The pattern-oriented depth lives in `references/`:

- `references/pattern-config-contract.md` — `.iwe/config.toml` v4 tables, defaults, migrations, schema bindings, template variables.
- `references/pattern-cli-and-query.md` — selectors, read flags, mutation guards, `--strict`, exit codes, the bundled agent routes.
- `references/pattern-memory-internal.md` — `iwe internal claude` commands, the memory switch, knobs, session records, transcripts, hooks' output.
- `references/pattern-plugin-wiring.md` — the `iwe-org/skills` 0.14.0 `hooks.json`, `plugin.json`, skill shims, permissions (T3), plus SRC-cited notes on what the 0.28.0 binary does.
- `references/pattern-servers.md` — `iwec` tools, prompts, resources, transports and cwd; `iwes` capabilities and code actions; npm launchers.
- `references/api-exports.md` — every extracted export grouped by crate and module, with citations.

## Full Type Definitions

Struct, enum and constant declarations (82 structs, 20 enums, 29 constants, 4 type aliases, 2 traits) are listed with their declaration lines in `references/api-exports.md`; the config tables with field defaults are in `references/pattern-config-contract.md`. [SRC:crates/diwe/src/config.rs:L81] [SRC:crates/liwe/src/model/config.rs:L14]

## Full Integration Patterns

The crates most imported alongside the in-scope files are `liwe` (73 imports in 19 files) and `diwe` (44 in 17); `rmcp` backs `iwec`, `lsp_server`/`lsp_types` back `iwes`, `clap` defines the CLI, `minijinja` renders the memory index and `toml_edit` performs the format-preserving migrations. [SRC:crates/iwec/src/main.rs:L10] [SRC:crates/iwes/src/main.rs:L57] [SRC:crates/iwe/src/main.rs:L6] [SRC:crates/iwe/src/internal/claude/hook/index.rs:L7] [SRC:crates/diwe/src/config.rs:L9]
