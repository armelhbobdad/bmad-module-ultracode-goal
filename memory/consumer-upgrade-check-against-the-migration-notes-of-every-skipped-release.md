---
created: "2026-10-26 12:48"
session: "3db662c1-d326-4c49-93fb-f5b18179d765"
---

# Consumer upgrade check against the migration notes of every skipped release

Before a consumer project's first run on a new version, check its `_bmad/custom/*.toml` and its recall settings in `_bmad/custom/ultracode-goal.toml` against the `**Migration:**` lines in CHANGELOG.md for every release between the old and the new version, skipped releases included. After the consumer project upgraded from 2.2.0 to 3.0.0 (skipping 2.3.0) with `npx bmad-module-ultracode-goal install`, the assistant reported the upgrade complete from a file check alone ("The install is complete: version 3.0.0, all six skills ... both copies match the package"), and a side-agent note the user relayed with "please consider this" corrected it: "The install check only confirmed the files landed. It didn't look at [the consumer project's] settings." A file check is not enough because some 3.0.0 changes turn settings off without any error: customizations in `bmad-create-story.toml` or `bmad-dev-story.toml` no longer reach a run unless copied to `ucg-create-story.toml` or `ucg-dev-story.toml`, and recall stays off until `cross_session_recall_store` names a folder.
