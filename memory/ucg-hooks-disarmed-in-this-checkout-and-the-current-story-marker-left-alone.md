---
created: "2026-09-29 11:22"
session: "32c0ba1b-6b80-4f30-bf50-a7a5a6ac2c6d"
---

# UCG hooks disarmed in this checkout and the .current-story marker left alone

This development checkout ran UCG's own hooks (`guard_pretooluse.py` on `PreToolUse` and `budget_stop.py` on `Stop`, armed from the gitignored `.claude/settings.local.json`) beside a long-lived `_bmad-output/implementation-artifacts/.current-story` marker (it read `qd-20260811-queue-drain`). The user's standing rule had been: "In this repo, leave _bmad-output/implementation-artifacts/.current-story and the hook files alone. Ignore the Stop hook's "turn budget exceeded" message here." On 2026-11-23, after the guard had refused every commit that a session rooted here made, in this repository's own linked worktrees too, the user said "disarm": both hook entries were removed from `.claude/settings.local.json`, and its `permissions.allow` rules and the `.current-story` marker stayed. Running sessions picked the change up without a restart. The marker part of the rule still holds: do not delete or rewrite it. A UCG preflight run in this checkout arms the hooks again, so read `.claude/settings.local.json` before assuming either state; while they are armed, take the way through that [[repo-guard-refusing-commits-in-other-repositories-from-a-ucg-session]] records.
