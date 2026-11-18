---
created: "2026-09-29 11:22"
session: "32c0ba1b-6b80-4f30-bf50-a7a5a6ac2c6d"
---

# Armed UCG hooks and the .current-story marker in this checkout left alone

This development checkout runs UCG's own hooks (`guard_pretooluse.py` and `budget_stop.py`, armed from the gitignored `.claude/settings.local.json`) beside a long-lived `_bmad-output/implementation-artifacts/.current-story` marker (it read `qd-20260811-queue-drain`). The user's standing rule for this repository: "In this repo, leave _bmad-output/implementation-artifacts/.current-story and the hook files alone. Ignore the Stop hook's "turn budget exceeded" message here." So do not delete or rewrite the marker, and do not disarm or edit the hooks to silence that message or to get past a refusal. When the protected-branch guard refuses a command, take the way through that [[repo-guard-refusing-commits-in-other-repositories-from-a-ucg-session]] records.
