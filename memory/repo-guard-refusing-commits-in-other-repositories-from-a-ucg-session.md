---
created: "2026-11-15 13:04"
session: "36d1b26b-c2ef-451e-ae63-24abfb0b9fe2"
---

# Repo guard refusing commits in other repositories from a UCG session

This repository's PreToolUse guard (`skills/ultracode-goal/scripts/hooks/guard_pretooluse.py`, armed from the gitignored `.claude/settings.local.json` with `ULTRACODE_PROTECTED_BRANCHES=main,master`) reads the branch from the hook event's `cwd`, the session's working directory, not from the repository a command targets. Its docstring (`:9-14`) calls this deliberate. So while this checkout sits on `main`, a commit in another checkout on a feature branch is refused with "PreToolUse:Bash hook error: Protected-branch guard: refusing `git commit` on 'main'", both as `cd ../bmad-module-skill-forge && git commit ...` and as `git -C ../bmad-module-skill-forge commit ...`. `git push` is refused the same way. Hit on 2026-11-15 while committing Skill Forge's side of #226 from a session started here. The way through: the user runs that commit or push with the `!` prefix, or the other repository's work runs in a session started in that repository, where this hook is not loaded. Do not switch this checkout off `main` just to pass the guard. Related: [[repo-guard-reading-a-commit-revision-suffix-as-a-git-commit]], [[remote-branch-deletion-via-gh-api-while-on-main]].
