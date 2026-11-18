---
created: "2026-11-03 15:03"
session: "18a0e403-10ce-436e-a0f4-b2362871b122"
---

# Set-aside review findings filed as GitHub issues, not only in deferred-work.md

bmad-build review triage appends the findings it sets aside to `_bmad-output/implementation-artifacts/deferred-work.md`, which `.gitignore:52:_bmad-output` keeps on the local machine, so they never reach GitHub or the PR. Asked how to handle the three set aside on PR #200, the user chose "Issues + PR list (Recommended)": each was filed as a GitHub issue (#197, #198, #199, label `bug`, each draft checked against HEAD first) and listed in the PR body's "Not fixed here" section. That is the precedent the user set for findings a review defers here; ask again when a case does not fit it.
