---
created: "2026-11-20 00:13"
session: "5b07f74c-c6ab-4198-89e2-8c44ba4ea42d"
---

# graphify query and explain writing graphify-out/cache/last_query_stamp

On graphify 0.9.112 the read commands are not free of writes: `graphify query`, `graphify explain` and `graphify path` each create or replace `graphify-out/cache/last_query_stamp`, a 17-byte file holding the current epoch time. It surfaced when a subagent bound to a read-only rule ran `graphify query` and `graphify explain` with `GRAPHIFY_NO_AUTO_REFRESH=1` and `GRAPHIFY_QUERY_LOG_DISABLE=1` and the file still appeared in this repository's gitignored `graphify-out/`. The write is `_touch_query_stamp()` in graphify's `cli.py`, called after each of those commands with no environment check and silent on failure, so neither variable switches it off. Its reader is the strict hook guard, which skips its block while the stamp is younger than `GRAPHIFY_HOOK_STRICT_TTL` (default 1800 seconds). The graphify-kg reference skill, pinned at 0.9.92, does not mention the file and names only the opt-in query log as a write. It matters wherever a checkout must hold no tool state, or an agent must leave a repository untouched: a graph read still changes `graphify-out/cache/`.
