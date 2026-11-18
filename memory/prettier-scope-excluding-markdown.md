---
created: "2026-06-08 20:46"
session: "19773476-05ca-422a-be7e-4f5f67b385ca"
---

# Prettier scope excluding markdown

`npx prettier --check <file>.md` reports `[warn] Code style issues found` on README.md, CHANGELOG.md, CONTRIBUTING.md and ROADMAP.md at HEAD, and that is not a gate failure: `format:check`/`format:fix` glob only `**/*.{js,cjs,mjs,json,yaml}`, and the lint-staged `*.md` hook and the CI markdownlint job run `markdownlint-cli2` alone, so nothing ever runs prettier on markdown. Never run prettier on markdown, `npx prettier --write <file>.md` included: it rewrites emphasis markers (`*already*` becomes `_already_`) and re-pads markdown tables, which can break a test. `test/test-releasing-runbook.py::test_the_restore_drill_has_a_record_that_names_its_filter` matches the compact header of `docs/_internal/RELEASING.md`'s restore-drill table with the regex `^\| Date \| Target \| Filter \| Result \|`, so on 2026-10-17 the padded table failed it with "E assert None", and restoring the table's compact `| Date | Target | Filter | Result |` form fixed it. After an accidental run, `git restore <file>.md` or put that table back in compact form. Validate markdown with `npm run lint:md` or `npx markdownlint-cli2 <file>.md`.
