---
created: "2026-11-20 02:02"
session: "5b07f74c-c6ab-4198-89e2-8c44ba4ea42d"
---

# claude -p with --no-session-persistence still writing under ~/.claude

On Claude Code 2.1.328 a headless run with `--no-session-persistence` keeps the transcript off disk but is not free of writes. A clean-room probe, `claude -p '<prompt>' --model haiku --output-format stream-json --verbose --no-session-persistence --strict-mcp-config`, run in a throwaway git repository and making one Agent tool call, left a project folder `~/.claude/projects/<slug of the working directory>/<session id>/subagents/` holding a 325-byte `agent-<id>.meta.json` (no transcript beside it) and a task folder under `/tmp/claude-1000/<slug of the working directory>/`. The agent that ran it also reported `~/.claude.json` rewritten during the run. The cc-primitives reference says the flag "keeps the session off disk, so it cannot be resumed", which holds for the transcript only. It matters for probes and fixtures that promise to leave nothing behind: they must remove those two folders afterwards and say so in their report.
