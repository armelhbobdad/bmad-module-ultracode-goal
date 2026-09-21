---
created: "2026-08-10 13:41"
session: "23469d3c-bb7a-4480-8f18-58ba7e6ddfde"
---

# GMC re-install of the module at a story boundary

GMC (the user's Global Maths Club project, a separate local checkout) runs an installed snapshot of this module, not a link to skills/ultracode-goal/, so nothing merged or released here reaches it until someone re-runs `npx bmad-module-ultracode-goal install`, and the user's rule is that this happens only between stories of a running epic: "that should happen at a story boundary, not mid-story." The evident reason (not one the user spelled out) is that a re-install swaps the skill text, references and hook scripts under whatever `claude -p` session `drive_epic.py` has in flight. The installer writes two copies, `.claude/skills/ultracode-goal/` and `_bmad/ucg/ultracode-goal/`, matching every shipped file in skills/ultracode-goal/ minus the .npmignore'd dev artifacts; nothing in README.md, docs/ or the skill records the timing rule.
