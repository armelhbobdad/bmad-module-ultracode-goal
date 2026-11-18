---
created: "2026-11-05 19:10"
session: "18a0e403-10ce-436e-a0f4-b2362871b122"
---

# cc-primitives reference skill overstating mid-session hook hot-reload

The SKF-generated reference skill cc-primitives says settings are "hot-reloaded for most keys, including hooks" (SKILL.md:101), "most edits hot-reload (hooks, permissions)" (references/memory-and-settings.md:45) and "Edits are picked up by the file watcher" (references/hooks.md:30), in both `.claude/skills/cc-primitives/` and its source `skf-skills/cc-primitives/2.1.306/`, while the Claude Code docs (fetched 2026-11-05) say only that the watcher normally picks up an edit and that a missed one needs a session restart. Issue #211 hit exactly that gap (hooks preflight wrote mid-session never fired while `--assert-armed` reported armed), which is why preflight now proves liveness with a refused `git commit --dry-run`. Do not take a settings.local.json write as proof that the running session loaded its hooks on the skill's word. Fix the skill with an `skf-update-skill` refresh of cc-primitives on its own branch, never a hand edit under `.claude/` or `skf-skills/` (generated content the next export overwrites); the overstatement was still there on 2026-11-18.
