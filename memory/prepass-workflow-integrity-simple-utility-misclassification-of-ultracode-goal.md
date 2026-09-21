---
created: "2026-08-06 18:28"
session: "504a7e6a-d2f8-4095-a8cd-daa05a320534"
---

# prepass-workflow-integrity.py simple-utility misclassification of ultracode-goal

BMAD's `prepass-workflow-integrity.py` (installed gitignored at `.claude/skills/bmad-workflow-builder/scripts/`) recognises stage files only as numbered `NN-name.md` files at the skill root or `prompts/`-prefixed references, so `skills/ultracode-goal/SKILL.md`, which routes its Stages table to unnumbered `references/*.md` files, is classified `simple-utility`: `uv run .claude/skills/bmad-workflow-builder/scripts/prepass-workflow-integrity.py skills/ultracode-goal` reports `"status": "pass"` with `"total_stages": 0`, empty `referenced`, `actual`, `missing_stages` and `orphaned_stages`, and `"issues": []`. That clean pass is vacuous: the stage cross-reference, missing/orphaned-stage and prompt-basics checks ran on an empty set, so a quality scan of this skill must cross-reference the `references/*.md` stage files itself (the 2026-08-06 scan covered the gap with completeness critics). Re-check after a BMAD upgrade of the scanner or a renaming of the stage files; the observation is the assistant's contemporaneous record of session 504a7e6a.
