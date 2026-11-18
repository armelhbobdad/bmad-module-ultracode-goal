---
created: "2026-10-19 01:13"
session: "3db662c1-d326-4c49-93fb-f5b18179d765"
---

# User-scope IWE MCP server serving ~/notes instead of this repository

The `iwe` MCP server available in sessions here is the user-scope entry in `~/.claude.json` (`npx -y @iwe-org/mcp` with `cwd: ~/notes`; this repository has no `.mcp.json` and no project-scope server), and an iwec server serves its working directory, so its `iwe_find` and `iwe_retrieve` tools query `~/notes`, not this repository's `memory/` store. Search and read this repository's memory with the `iwe` CLI run from the repository root (`iwe find --lexical ...`, `iwe retrieve -k <key>`), as the distill flow does, and treat a timeout or error from that MCP server as a problem of the user-scope server, not of this workspace.
