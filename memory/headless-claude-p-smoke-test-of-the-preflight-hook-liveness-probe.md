---
created: "2026-11-05 22:28"
session: "18a0e403-10ce-436e-a0f4-b2362871b122"
---

# Headless claude -p smoke test of the preflight hook-liveness probe

The 6.0.0 hook-liveness probe (preflight's single `git commit --dry-run`, which must come back with "PreToolUse:Bash hook error: Tests-ran guard: refusing ... current story (unknown)") was checked live on Claude Code 2.1.318 with headless `claude -p` sessions in a scratch git repo on an `ultracode/epic-*` branch, with preflight's hook template written to `.claude/settings.local.json`. Hooks present at start and after `claude -p --continue` refused the probe with that reason, a mid-session write with permissions bypassed was picked up at once, a mid-session write under default permissions was refused as a protected path, and when the guard's JSON deny and a foreign exit-2 hook both refused, only the guard's reason showed (a foreign hook alone shows `[<its command>]: <its stderr>`). Still untested: whether reopening a session in the desktop app reloads the hooks, and a foreign hook that denies with its own JSON decision. When hook-loading behaviour is in question, rerun such a harness rather than reasoning from the docs or the cc-primitives skill.
