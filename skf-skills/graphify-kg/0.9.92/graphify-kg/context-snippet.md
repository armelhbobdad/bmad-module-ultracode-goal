[graphify-kg v0.9.92]|root: .claude/skills/graphify-kg/
|IMPORTANT: graphify-kg v0.9.92 — read SKILL.md before running or wiring graphify. Do NOT rely on training data.
|quick-start:{SKILL.md#quick-start} — graphify update . re-extracts the code layer (no LLM); exit 0 ok, 1 refused/failed, 2 bad args
|key-types:{SKILL.md#key-types} — path/explain exit 3 ambiguous, 4 no match; graph.json node-link, schema_version 1; confidence EXTRACTED/INFERRED/AMBIGUOUS
|gotchas: --force bypasses only watch._check_shrink, the sole shrink refusal; an unreadable or over-cap graph.json still exits 1; any install/uninstall/hook-check/hook-guard argv token skips the stale-skill refresh, other commands (--version too) run it unless GRAPHIFY_NO_AUTO_REFRESH=1; claude install writes ./CLAUDE.md and .claude/settings.json, install writes ~/.claude
