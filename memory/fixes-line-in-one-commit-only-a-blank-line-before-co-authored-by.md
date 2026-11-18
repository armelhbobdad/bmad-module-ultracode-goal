---
created: "2026-11-17 22:51"
session: "2e0859f5-9e6d-4ee2-9f4b-2f2cdbb0f2dc"
---

# Fixes line in one commit only, a blank line before Co-Authored-By

The user asked that the closing keyword (`Fixes #N`) appear once, in one commit only, with a blank line between it and the `Co-Authored-By:` trailer. It came as a house rule in the brief the user pasted for issue #244: "`Fixes #244` once, with a blank line between it and `Co-Authored-By:`". So in a change that closes an issue, write the `Fixes` line in a single commit message, not in every commit of the branch, and leave an empty line above the attribution trailer.
