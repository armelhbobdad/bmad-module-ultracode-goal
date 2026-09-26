---
created: "2026-09-23 01:45"
session: "9ec28b9e-2f20-4967-97f3-00648db4c24d"
---

# SKF output folder skf-skills, not the default skills

This module's source lives under `skills/` (293 of 384 tracked files at v2.2.0). That is also the SKF installer's default `skills_output_folder`, so with the default skf-setup adds `**/skills` to `.cocoindex_code/settings.yml` and drops the module source from the ccc index, and generated skills land in the source tree. On 2026-09-23 the user settled it: "Change `skills_output_folder` to `skf-skills`. It should be committed." The value lives in `_bmad/skf/config.yaml` and in the install answers at `_bmad/_config/skf-manifest.yaml`, both gitignored and so per-checkout: a fresh install asks "Where should generated skills be saved?" again, defaulting to `skills`, and has to be answered `skf-skills`. The user also confirmed keeping `**/skf-skills` excluded from the ccc index (skf-setup re-adds it on every run anyway) and listing `/skf-skills/` in `.npmignore`: `package.json` has no `files` list, so a committed folder would otherwise ship in every published package, the clean CI release included. `skf-merge-ccc-exclusions.py` only ever adds patterns, so a stale `**/skills` left by an earlier run has to be deleted from `settings.yml` by hand; upstream issues armelhbobdad/bmad-module-skill-forge#491 and #492 track both gaps.
