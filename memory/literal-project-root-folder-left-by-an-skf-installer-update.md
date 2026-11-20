---
created: "2026-11-18 22:54"
session: "a57a12c7-5bbf-4ae1-bf92-0e1c4f19db41"
---

# Literal {project-root} folder left by an SKF installer update

Updating SKF from 4.0.0 to 11.1.0 with `npx bmad-module-skill-forge install` created an untracked folder named `{project-root}/` at the repository root, holding only placeholder `skf-skills/.gitkeep` and `forge-data/.gitkeep` files. The cause is `createOutputFolders` in the installer's `tools/cli/lib/installer.js`: it joins the raw `{project-root}/skf-skills` style values of `_bmad/skf/config.yaml` without resolving the placeholder. The real `skf-skills/` and `forge-data/` folders were untouched. The user had the stray folder deleted and the bug filed as SKF issue #1246; until it is fixed, expect the folder after any SKF install or update and delete it. The config's state before that update is in [[skf-config-keys-dropped-by-the-bmad-6-12-4-update]].
