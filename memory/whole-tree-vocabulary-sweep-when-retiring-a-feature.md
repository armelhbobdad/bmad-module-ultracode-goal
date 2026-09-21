---
created: "2026-08-04 21:48"
session: "aaa0183f-7e6f-4b48-9a53-6932565cebe1"
---

# Whole-tree vocabulary sweep when retiring a feature

When retiring a feature or flag, grep the whole tracked tree case-insensitively for its vocabulary (the flag name, the mode name and its synonyms; for `--parallel` that was `parallel`, `fan-out` and `worktree`) with `git grep -i -n -e '<word>' -e '<synonym>'` before opening the PR, because the stragglers live in files the change never touched and a diff-scoped inventory cannot see them. PR #89 (2026-08-04) retired the `--parallel` fan-out from a diff-scoped inventory and the adversarial review then confirmed 15 findings, none in the diff, swept by commit 764d5b2 ("none of them in the diff, which is why grep-the-diff could not see them": README's flags table, ROADMAP.md, STABILITY.md, three skill references, the bug-report template, the llms.txt entry in tools/build-docs.js); cd17eaf (2026-07-19, dropping the retired token ceiling from the user-facing surface) is the same class, so it is a pattern. Triage hits rather than deleting them: `worktree` has a live second meaning since c5a0fb2 (the Stage-5 gate measures a git worktree of the commit), and pre-retirement prose survives on purpose in frozen prose-regression fixtures under `scripts/tests/fixtures/`. Nothing in CONTRIBUTING.md or docs/_internal/ records the sweep; the rule is the assistant's contemporaneous record of session aaa0183f.
