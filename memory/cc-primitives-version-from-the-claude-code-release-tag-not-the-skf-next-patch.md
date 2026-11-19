---
created: "2026-11-19 00:09"
session: "a57a12c7-5bbf-4ae1-bf92-0e1c4f19db41"
---

# cc-primitives version from the Claude Code release tag, not the SKF next patch

On SKF 11.1.0, `skf-update-skill` gives a docs-only skill such as cc-primitives the next patch version (2.1.306 would have become 2.1.307): its load-baseline step skips the source-version step, so a docs-only update cannot record the release it documents. Asked which version the refresh should carry, the user chose the anthropics/claude-code release tag, v2.1.327, which matches the installed CLI and the docs the skill was compiled from. The version is set through the brief's `target_version`, the same way the earlier pins 2.1.283 and 2.1.306 were set. A future cc-primitives refresh pins the Claude Code release it documents, never the patch number the update proposes. The gap is SKF issue #1248.
