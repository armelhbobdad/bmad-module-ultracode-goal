---
created: "2026-09-23 01:30"
session: "9ec28b9e-2f20-4967-97f3-00648db4c24d"
---

# ccc init no-op on a pre-existing .cocoindex_code/settings.yml

`ccc init` (cocoindex-code 0.2.41) prints "Project already initialized." and returns whenever `.cocoindex_code/settings.yml` exists (`cli.py:624-626`), so it neither writes its default `include_patterns`/`exclude_patterns` nor adds `/.cocoindex_code/` to `.gitignore` (the skipped `add_to_gitignore` call, `cli.py:129`). skf-setup triggers this on a first run: `skf-merge-ccc-exclusions.py` creates `settings.yml` holding only the six SKF patterns before `ccc init` runs. The skipped gitignore entry left the index (a 55 MB `target_sqlite.db` plus a 45 MB LMDB under `cocoindex.db/`) showing as `?? .cocoindex_code/`, and because ccc reads a present `exclude_patterns` key in place of its defaults (`settings.py:590`), tracked hidden directories such as `.github/` were indexed. Fixed on 2026-09-23 by deleting `settings.yml`, running `ccc init`, re-running the merge helper and `ccc index`; `.gitignore` now carries ccc's own `# CocoIndex Code (ccc)` block, which `ccc reset --all` removes again. Upstream issue armelhbobdad/bmad-module-skill-forge#490 asks for `ccc init` to run before the merge. Related: [SKF output folder skf-skills, not the default skills](skf-output-folder-skf-skills-not-the-default-skills.md).
