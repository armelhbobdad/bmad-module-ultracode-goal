---
created: "2026-08-07 11:31"
session: "9507dda8-dad6-4b2c-ae09-66cac7a0d9d3"
---

# STABILITY.md posture strings hand-moved on every major bump

`docs/_internal/STABILITY.md` ships in the npm tarball (no `files` field in package.json; `.npmignore` excludes only root-level `/*.md`) and self-describes as what a consumer pins against, but its major-version posture lives in three hand-maintained strings: the frontmatter `description` ("The 2.x stability posture: ..."), the `> **Status:** 2.x.` line, and the opening sentence. v2.0.0 shipped all three saying `1.x` (`git show v2.0.0:docs/_internal/STABILITY.md | grep 'Status:'`) because 5a4a59b wrote the `1.x` strings fresh during 2.0.0 prep, and caf3a8d (2026-08-06, "chore: state the 2.x posture") flipped them in the v2.1.0 prep; being a `chore:` commit, that rationale never reached the generated CHANGELOG section. Nothing checks the strings: RELEASING.md has no STABILITY.md step (its only version-coupling invariant is package.json against `.claude-plugin/marketplace.json`), no CI step or `tools/` validator reads the file, and the two pytest files that do (`test_budget_stop.py`, `test_headless_envelope_schema.py`) assert only the `[workflow]` keys. On every major bump, move all three by hand and confirm with `grep -n '2\.x' docs/_internal/STABILITY.md`. The trap is the assistant's contemporaneous record of session 9507dda8.
