---
created: "2026-11-05 19:10"
session: "18a0e403-10ce-436e-a0f4-b2362871b122"
---

# cc-primitives reference skill overstating mid-session hook hot-reload

The SKF-generated reference skill cc-primitives 2.1.306 said settings are "hot-reloaded for most keys, including hooks" (SKILL.md:101), "most edits hot-reload (hooks, permissions)" (references/memory-and-settings.md:45) and "Edits are picked up by the file watcher" (references/hooks.md:30), while the Claude Code docs say only that the watcher normally picks up an edit and that a missed one needs a session restart. Issue #211 hit exactly that gap (hooks preflight wrote mid-session never fired while `--assert-armed` reported armed), which is why preflight now proves liveness with a refused `git commit --dry-run`. The `skf-update-skill` refresh to cc-primitives 2.1.327 (commit e78a2d5 on branch `chore/cc-primitives-2.1.327`, docs fetched 2026-11-18) fixes all three places: the file watcher applies most edits, `hooks` and `permissions` included, without a restart, but it can miss one, and a hook change not seen after a few seconds needs a session restart (the settings and hooks-guide pages). Even so, do not take a settings.local.json write as proof that the running session loaded its hooks: prove liveness. Fix any later drift with another `skf-update-skill` refresh on its own branch, never a hand edit under `.claude/` or `skf-skills/` (generated content the next export overwrites).
