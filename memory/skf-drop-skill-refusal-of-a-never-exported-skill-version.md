---
created: "2026-10-19 18:01"
session: "3db662c1-d326-4c49-93fb-f5b18179d765"
---

# skf-drop-skill refusal of a never-exported skill version

The drop workflow (`skf-drop-skill`) accepts only versions recorded in `skf-skills/.export-manifest.json`, so it cannot remove a failed intermediate build that was never exported, such as the stack skill's 1.3.0, which failed `skf-test-skill`. After checking that nothing in git, the export manifest or the `active` version references it, delete `skf-skills/<skill>/<version>/` by hand and keep its `forge-data/<skill>/<version>/` records as evidence. That is why `skf-skills/bmad-module-ultracode-goal-stack/` goes from 1.2.0 straight to 1.4.0: its 1.3.0 was deleted this way.
