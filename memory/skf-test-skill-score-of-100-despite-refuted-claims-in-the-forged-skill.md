---
created: "2026-10-19 11:27"
session: "3db662c1-d326-4c49-93fb-f5b18179d765"
---

# skf-test-skill score of 100 despite refuted claims in the forged skill

On 2026-10-19 skf-test-skill scored both new reference skills, graphify-kg and iwe-kg, 100 against a threshold of 90, yet a line-by-line claim sweep against the pinned source refuted 76 of 1,054 graphify-kg claims and 26 of 815 iwe-kg claims (wrong exit-code tables, wrong `--if-exists` defaults, a wrong `update --force` gotcha). A passing test score is therefore no evidence that a forged skill's claims are correct, and the gap-driven skf-update-skill does not repair claim-accuracy errors. Before exporting a forged or refreshed reference skill, sweep its claims against the pinned source and apply cited corrections, recorded as `forge-data/<skill>/<version>/claim-corrections-<date>.md` (as done for graphify-kg 0.9.92, iwe-kg 0.28.0, cc-primitives 2.1.306 and stack 1.4.0 and 1.5.0).
