---
created: "2026-11-18 07:50"
session: "2e0859f5-9e6d-4ee2-9f4b-2f2cdbb0f2dc"
---

# markdownlint MD034 bare-URL errors on `www.` hostnames in memory notes

The lint-staged pre-commit hook runs markdownlint-cli2 over staged `memory/*.md` files with MD034 on (`.markdownlint-cli2.yaml`), and nothing lints a note when `iwe create` or `iwe update` writes it. So a note holding a bare `www.` or `www.HOST` outside a code span is accepted by the store and fails only at commit time, with `MD034/no-bare-urls Bare URL used [Context: "www"]` and then `husky - pre-commit script failed (code 1)`. It hit on [[lower-case-www-trim-on-a-gh-repo-host-absent-from-hostname]], which named `www.` hosts in plain text. Put such hostnames in backticks, headings included, and fix a failed note with `iwe update` rather than an editor.
