---
created: "2026-06-08 20:46"
session: "19773476-05ca-422a-be7e-4f5f67b385ca"
---

# Prettier scope excluding markdown

`npx prettier --check <file>.md` reports `[warn] Code style issues found` on README.md, CHANGELOG.md, CONTRIBUTING.md and ROADMAP.md at HEAD, and that is not a gate failure: `format:check`/`format:fix` glob only `**/*.{js,cjs,mjs,json,yaml}`, and the lint-staged `*.md` hook and the CI markdownlint job run `markdownlint-cli2` alone, so nothing ever runs prettier on markdown. Do not "fix" it with `npx prettier --write <file>.md`: it rewrites emphasis markers (`*already*` becomes `_already_`) and churns lines nothing checks; `git restore <file>.md` undoes churn already applied. Validate markdown with `npm run lint:md` or `npx markdownlint-cli2 <file>.md`.
