---
created: "2026-10-24 14:54"
session: "3db662c1-d326-4c49-93fb-f5b18179d765"
---

# Empty-index guard refusing a message-only git commit --amend

In the maintainer's dev session this repository's own PreToolUse guard (`skills/ultracode-goal/scripts/hooks/guard_pretooluse.py`, armed from the gitignored `.claude/settings.local.json`) refuses `git commit --amend` when nothing is staged, with "PreToolUse:Bash hook error: Empty-index guard: refusing `git commit`" and "the staged index is empty (or could not be read)", so a commit message cannot be reworded in place. Undo the local commit with `git reset --soft HEAD~1`, which keeps the work staged, then run `git commit -q -F <msgfile>` again as a separate tool call (the recovery used on 2026-10-24).
