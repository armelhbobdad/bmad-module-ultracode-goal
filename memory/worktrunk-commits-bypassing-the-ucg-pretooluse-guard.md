---
created: "2026-11-18 20:42"
session: "5b07f74c-c6ab-4198-89e2-8c44ba4ea42d"
---

# worktrunk commits bypassing the UCG PreToolUse guard

worktrunk (`wt` 0.82) creates commits and moves the target branch inside its own process: `wt step commit`, `wt step squash` and `wt merge` all do. The UCG guard `guard_pretooluse.py` classifies only git verbs in a Bash command (`_classify` returns only those), so none of them passes the protected-branch, tests-ran, freshness, empty-index, intent-to-add or un-skip checks, and `wt` is not on UCG's command allowlist. wt's own hook commands also run outside Claude Code's permission system. This came from a lab run in a throwaway repo while worktrunk was weighed as a worktree manager for UCG; a guarded session given `wt` would land work the guard never checked.
