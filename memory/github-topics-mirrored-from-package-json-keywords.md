---
created: "2026-06-04 17:15"
session: "777ccc3f-9c9a-4209-9a55-13ba5469e1a3"
---

# GitHub topics mirrored from package.json keywords

The repository's GitHub topics are a hand-mirrored copy of the `keywords` array in `package.json`, set via `PUT /repos/armelhbobdad/bmad-module-ultracode-goal/topics` after the user asked to "add all the keywords from @package.json as a github topics for this project." Nothing in `.github/workflows/` or `tools/` syncs them, so a `keywords` edit needs a matching topics PUT. Check drift with `gh api repos/armelhbobdad/bmad-module-ultracode-goal/topics --jq '.names'` against `jq '.keywords' package.json`; the sets should match.
