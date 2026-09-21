---
created: "2026-06-19 23:29"
session: "54cc1394-dd8d-4768-86f5-d38826957c39"
---

# Upstream bmad-builder as the PR target for builder-skill fixes

The bmad-module-builder skill under `.claude/skills/bmad-module-builder/` is installed BMB tooling, not this repository's source: the bare `.claude` entry in `.gitignore` leaves nothing under it tracked, so edits to its scripts or tests run live on disk but there is nothing to branch, commit or PR from this repo. When the B1-B3 standalone-validator fix was made here, the user had it ported upstream: "Port the B1–B3 validator fix upstream to where the builder skill is maintained, so it's not local-only." The provenance is in the gitignored `_bmad/_config/manifest.yaml` (module `bmb`, npmPackage `bmad-builder`, repoUrl github.com/bmad-code-org/bmad-builder); the local clone is the sibling checkout `../bmad-builder` (origin = fork armelhbobdad/bmad-builder, upstream = bmad-code-org), and the fix landed there as PR #97 ("fix(validate-module): harden standalone module validation", merged 2026-06-22). Any other edit under that gitignored copy is lost on the next install and invisible to everyone else, so an upstream PR is its only durable home.
