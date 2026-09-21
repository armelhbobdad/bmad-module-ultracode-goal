---
created: "2026-08-10 13:41"
session: "23469d3c-bb7a-4480-8f18-58ba7e6ddfde"
---

# claude -p subprocess spine versus cross-session messaging

`skills/ultracode-goal/scripts/drive_epic.py` spawns one cold-start `claude -p` per story (bounded by `--max-stories 1`, never `--resume`/`--continue`), and the user asked whether that is right: "Running claude code as shell command is a really good idea? While we have <https://code.claude.com/docs/en/cross-session-messaging>, rmux, and more alternative /agent-reach ?"; the question is open, not settled. The analysis recommended keeping the subprocess spine (hard lifecycle, envelope, fail-closed routing) because cross-session messaging (`CLAUDE_CODE_MESSAGING_SOCKET`, headless inbox via `crossSessionInbound`) is best-effort steering between tool calls, not an execution contract for fail-closed gating ("ops/steering channel only, never a completion contract"); rmux/tmux are display-only; the Agent SDK is worth adopting only if per-stage tool restriction becomes necessary. The session's claude-mem observations label this "Architecture ruling confirmed", but no user turn confirmed it, so it stays an assistant recommendation and must not be written into [docs/architecture.md](../docs/architecture.md) as a decision without the user's word. ("Cross-Session Recall" in docs/ is the optional claude-mem integration, unrelated.)
