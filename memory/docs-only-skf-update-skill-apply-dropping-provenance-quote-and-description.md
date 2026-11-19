---
created: "2026-11-19 00:10"
session: "a57a12c7-5bbf-4ae1-bf92-0e1c4f19db41"
---

# Docs-only skf-update-skill apply dropping provenance quote and description

On SKF 11.1.0, `skf-build-change-manifest.py apply` (its `_apply_docs_only` path) writes a docs-only skill's new provenance-map entries without their `quote` or `description` fields, and leaves carried entries holding the quotes of the previous version. The cc-primitives 2.1.327 refresh repaired all 1,420 entries by script from the verified inventory right after `apply` ("quotes set or replaced 823"). A future docs-only update needs the same repair until the bug is fixed. It is SKF issue #1247, which the health check flagged as a possible regression of the closed #808.
