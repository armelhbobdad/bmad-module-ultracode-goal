# Pattern: the iwec MCP server, the iwes LSP server and the npm launchers

## Contents

- [Which directory a server serves](#which-directory-a-server-serves)
- [iwec transports](#iwec-transports)
- [iwec tools](#iwec-tools)
- [iwec prompts and resources](#iwec-prompts-and-resources)
- [iwes capabilities](#iwes-capabilities)
- [Registering the servers](#registering-the-servers)
- [npm launchers and versions](#npm-launchers-and-versions)
- [History](#history)

## Which directory a server serves

- Both servers call `load_config()`, which reads `.iwe/config.toml` from the directory they were started in, and both serve that directory joined with `workspace.path` when that key is set: `iwec` through `workspace_path_in` in `IweServer::new`, `iwes` in `main.rs`. A client entry with another working directory serves that directory (plus its `workspace.path`), not the current repository. [SRC:crates/iwec/src/main.rs:L57] [SRC:crates/iwec/src/main.rs:L62] [SRC:crates/iwec/src/main.rs:L64] [SRC:crates/iwec/src/lib.rs:L1836] [SRC:crates/diwe/src/config.rs:L457] [SRC:crates/iwes/src/main.rs:L52] [SRC:crates/iwes/src/main.rs:L133] [SRC:crates/iwes/src/main.rs:L139] [SRC:npm/mcp/README.md:L20] [SRC:server.json:L5]
- A config that fails to load stops either server with `Error: ...` and exit `1`. [SRC:crates/iwec/src/main.rs:L57] [SRC:crates/iwes/src/main.rs:L52]

## iwec transports

| Flag | Default | Notes |
|---|---|---|
| `--transport stdio\|http` | `stdio` | [SRC:crates/iwec/src/main.rs:L23] |
| `--host` | `127.0.0.1` | HTTP only [SRC:crates/iwec/src/main.rs:L26] |
| `--port` | `8000` | HTTP only [SRC:crates/iwec/src/main.rs:L29] |

HTTP serves Streamable HTTP at `/mcp`; it is plain HTTP, so TLS or authentication needs a reverse proxy. `IWE_DEBUG` raises logging to DEBUG on stderr. [SRC:crates/iwec/src/main.rs:L83] [SRC:docs/mcp.md:L19] [SRC:docs/mcp.md:L31] [SRC:crates/iwec/src/main.rs:L37]

## iwec tools

`iwe_find`, `iwe_retrieve`, `iwe_tree`, `iwe_stats`, `iwe_squash`, `iwe_create`, `iwe_update`, `iwe_delete`, `iwe_query`, `iwe_rename`, `iwe_extract`, `iwe_inline`, `iwe_normalize`, `iwe_attach` (14). [SRC:crates/iwec/src/lib.rs:L765] [SRC:crates/iwec/src/lib.rs:L784] [SRC:crates/iwec/src/lib.rs:L1115] [SRC:crates/iwec/src/lib.rs:L1462] [SRC:docs/mcp.md:L35]

- `iwe_create` writes `content` verbatim at an explicit `key`; `if_exists` is `fail` (default) or `skip` for idempotent retries. [SRC:crates/iwec/src/lib.rs:L933] [SRC:crates/iwec/src/lib.rs:L441]
- `iwe_query` runs a `find`/`count`/`update`/`delete` operation document and is always strict: every mutation needs an `expect` guard. [SRC:crates/iwec/src/lib.rs:L488] [SRC:crates/iwec/src/lib.rs:L513] [SRC:crates/iwe/docs/query.md:L811]
- `iwe_create` and `iwe_rename` refuse keys with a leading `/` or a `..` segment: `Key 'K' must stay inside the workspace`. [SRC:crates/iwec/src/lib.rs:L729] [SRC:crates/iwec/src/lib.rs:L969] [SRC:crates/iwec/src/lib.rs:L1231]
- Results from `iwe_create`, `iwe_update` and, when not a dry run, `iwe_delete` and `iwe_query` update/delete may carry stats warnings (dangling links, orphans, similar pages); a create skipped by `if_exists: "skip"` carries none. Resolve them before the session ends. Each finding is reported only once per server session. `iwe_rename`, `iwe_extract`, `iwe_inline`, `iwe_normalize` and `iwe_attach` never return stats warnings. [SRC:crates/iwec/src/lib.rs:L933] [SRC:crates/iwec/src/lib.rs:L1001] [SRC:crates/iwec/src/lib.rs:L1035] [SRC:crates/iwec/src/lib.rs:L1091] [SRC:crates/iwec/src/lib.rs:L1113] [SRC:crates/iwec/src/lib.rs:L1931] [SRC:crates/iwec/src/lib.rs:L1242] [SRC:crates/iwec/src/lib.rs:L1329] [SRC:crates/iwec/src/lib.rs:L1425] [SRC:crates/iwec/src/lib.rs:L1453] [SRC:crates/iwec/src/lib.rs:L1558] [SRC:crates/iwec/src/lib.rs:L1102] [SRC:crates/iwec/src/lib.rs:L1187] [SRC:crates/iwec/src/lib.rs:L1210] [SRC:crates/diwe/src/stats.rs:L87]

## iwec prompts and resources

- Prompts: `explore` (graph statistics), `review` (a key with 2 levels each way and backlinks), `refactor` (a key with 3 levels down, 1 up). [SRC:crates/iwec/src/lib.rs:L1606] [SRC:crates/iwec/src/lib.rs:L1626] [SRC:crates/iwec/src/lib.rs:L1663]
- Resources: `iwe://tree`, `iwe://stats`, `iwe://config` (JSON) and `iwe://documents/{key}` (markdown). [SRC:crates/iwec/src/lib.rs:L1725] [SRC:crates/iwec/src/lib.rs:L1728] [SRC:crates/iwec/src/lib.rs:L1731] [SRC:crates/iwec/src/lib.rs:L1826]
- Server info: name `iwe` with the crate version, plus a fixed instructions string. [SRC:crates/iwec/src/lib.rs:L1711] [SRC:crates/iwec/src/lib.rs:L1713]
- The server watches the workspace and applies file updates and removals to its in-memory graph. [SRC:crates/iwec/src/main.rs:L65] [SRC:crates/iwec/src/lib.rs:L1981] [AST:crates/iwec/src/watcher.rs:L38] [SRC:crates/iwec/src/watcher.rs:L11]

## iwes capabilities

- stdio LSP with references, definition, hover, formatting, completion (trigger characters from `[completion] trigger_characters`, default `[`), symbols, inlay hints, rename and code actions. [SRC:crates/iwes/src/main.rs:L57] [SRC:crates/iwes/src/main.rs:L66]
- Code-action kinds are the built-in list/section/delete actions plus every `[actions.NAME]`. [SRC:crates/iwes/src/main.rs:L96] [SRC:crates/iwes/src/main.rs:L97] [AST:crates/iwes/src/router/server/actions.rs:L262]
- A client named `helix` gets Helix-specific handling. [SRC:crates/iwes/src/lib.rs:L35]
- `IWE_DEBUG` writes DEBUG logs to `iwe.log` in the working directory. [SRC:crates/iwes/src/main.rs:L32] [SRC:crates/iwes/src/main.rs:L39]
- The server loop is `main_loop(connection, params)`. [AST:crates/iwes/src/lib.rs:L31]

## Registering the servers

- `iwe init`, when its agent artifacts are enabled, appends an `<!-- iwe -->` section to `AGENTS.md` and registers `"iwe": { "command": "iwec", "args": [] }` in `.mcp.json`; each is left untouched when already present. Without an interactive confirmation it only prints both. [AST:crates/iwe/src/init/agents.rs:L44] [SRC:crates/iwe/src/init/agents.rs:L5] [AST:crates/iwe/src/init/agents.rs:L69] [SRC:crates/iwe/src/init/agents.rs:L95] [SRC:crates/iwe/src/init.rs:L191] [SRC:crates/iwe/src/init.rs:L335]
- The npm form for an MCP client is `"command": "npx", "args": ["-y", "@iwe-org/mcp"]`, over stdio. [SRC:npm/mcp/README.md:L13] [SRC:npm/mcp/README.md:L14] [SRC:server.json:L17] [SRC:server.json:L19]

## npm launchers and versions

- `@iwe-org/iwe` exposes `iwe`, `iwes`, `iwec` and runs the prebuilt binary from a per-platform optional dependency (darwin arm64/x64, linux x64/arm64, win32 x64); an unsupported platform or a skipped optional dependency exits `1` with a message. Node >= 18. [SRC:npm/iwe/package.json:L13] [SRC:npm/iwe/package.json:L15] [SRC:npm/iwe/lib/run.js:L5] [SRC:npm/iwe/lib/run.js:L17] [SRC:npm/iwe/lib/run.js:L27] [SRC:npm/iwe/package.json:L19]
- `@iwe-org/mcp` runs `@iwe-org/iwe`'s `iwec`. [SRC:npm/mcp/bin/iwe-mcp.js:L2]
- In the tagged tree the npm and `server.json` versions are `0.0.0` placeholders; the Cargo workspace version is the release version (`0.28.0`). [SRC:npm/iwe/package.json:L3] [SRC:server.json:L11] [SRC:Cargo.toml:L11]
- Other install routes: `brew install iwe-org/iwe/iwe`, `npm install -g @iwe-org/iwe`, `cargo install iwe` / `iwes` / `iwec`. [SRC:docs/how-to-install.md:L10] [SRC:docs/how-to-install.md:L20] [SRC:docs/how-to-install.md:L38]

## History

- **#401 (T2-past):** `iwec` once accepted path-traversing keys; since iwec 0.24.1 `iwe_create` and `iwe_rename` reject them. [QMD:iwe-kg-temporal:issues.md] [SRC:crates/iwec/CHANGELOG.md:L67]
- **#407 (T2-past):** `iwe_retrieve` returned a fabricated document for an unknown key; since 0.25.0 it fails with `Document 'KEY' not found`. [QMD:iwe-kg-temporal:issues.md]
- **#410 (T2-future):** per-workspace MCP server name and instructions are requested and not implemented in 0.28.0. [QMD:iwe-kg-temporal:issues.md]
- **#278 (T2-past):** an `iwes` panic during rename in a small vault, through `main_loop`, was fixed in May 2026. [QMD:iwe-kg-temporal:issues.md]
