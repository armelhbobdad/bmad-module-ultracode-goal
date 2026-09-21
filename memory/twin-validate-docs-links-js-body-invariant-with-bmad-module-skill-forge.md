---
created: "2026-08-06 11:48"
session: "4676d38b-96dc-4aaf-91e7-f88456790f36"
---

# Twin validate-docs-links.js body invariant with bmad-module-skill-forge

`tools/validate-docs-links.js` is a twin of `tools/validate-docs-links.js` in the sibling bmad-module-skill-forge checkout (`../bmad-module-skill-forge`): the body from the first `const` line onward is byte-identical and only the per-repo header comment differs (`test/test-validate-docs-links.js` is identical in both; `tools/build-docs.js` is not a twin). The user set the rule when the two drifted by a misplaced `run` JSDoc: "the two validate-docs-links.js bodies are now out of sync by that 10-line block. Reconverging is the same one-line move there, plus the Suppressed under --require-build comment nit that I deliberately left alone here so it could be fixed in both repos at once"; reconverged by e5fd295. Nothing enforces it (no test, CI step, or mention in CONTRIBUTING.md), so any edit to the validator body is applied to both checkouts by hand and checked with `diff <(tail -n +<first-const-line> tools/validate-docs-links.js) <(tail -n +<first-const-line> ../bmad-module-skill-forge/tools/validate-docs-links.js)` (expect empty output) and `npm run validate:docs-links` in each repo.
