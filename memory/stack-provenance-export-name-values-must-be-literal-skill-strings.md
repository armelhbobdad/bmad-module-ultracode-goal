---
created: "2026-09-28 22:55"
session: "ec3183b9-d501-4eb5-a70d-d37b22bc3f9e"
---

# Stack provenance export_name values must be literal skill strings

`skf-test-skill` scores a stack skill's Export Coverage in the stack branch of `.claude/skills/skf-test-skill/scripts/reconcile-coverage.py`: the denominator is the count of `entries[].export_name` in `forge-data/<stack>/<version>/provenance-map.json`, and each name counts as documented only if it appears as a case-sensitive substring in `SKILL.md` or a top-level `references/*.md` file (`references/integrations/*.md` is not read). In the 2026-09-28 re-compose of `bmad-module-ultracode-goal-stack` 1.1.0, 9 of the 11 entries added for tea-testarch and cc-primitives were written as descriptive labels (`hook exit 2`, `skill precedence`, `.claude/settings.json hooks`, `module.yaml (TEA registration)`, ...), so the script returned `"documented": 35`, `"denominator": 44`, `"exportCoverage": 79.55` and the total scored 86.81 against `--threshold=90`, although every contract behind those names was documented. When `skf-create-stack-skill` step 7 writes the compose-mode provenance map, give each entry an `export_name` that already occurs verbatim in the skill (`exit 2`, `.claude/settings.json`, `tea-enforce.cjs`) and grep the full name list against `SKILL.md` and `references/*.md` before `commit-dir`.
