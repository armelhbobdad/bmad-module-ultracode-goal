---
created: "2026-07-19 15:27"
session: "41ec4a24-47b1-43e4-be68-dee08405dadb"
---

# Stacked fix PR landing in an already-merged epic branch

On 2026-07-19 fix PR #42 (`ultracode/fix-empty-set-fail-opens`) was opened with base `ultracode/epic-4` instead of main because Epic 4 had already modified `skills/ultracode-goal/references/gate.md`; PR #41 (`ultracode/epic-4`) merged to main at 15:18 (`e6857ac`), #42 merged seconds later into the epic branch (its merge commit `cb9cf5e` is not an ancestor of main: `git merge-base --is-ancestor cb9cf5e e6857ac` exits 1), so main carried Epic 4 without the fix until PR #43 re-merged the epic branch (`6f6a56c`). PR #42's body assumed "Merge #41 first, then this retargets to `main` cleanly"; GitHub retargets an open PR's base only when that base branch is deleted, and this repo has `delete_branch_on_merge=false`, so a stacked PR keeps pointing at the epic branch after that branch's PR merges. Retarget with `gh pr edit <n> --base main` once the base PR has merged and before the stacked PR is merged, and verify landing with `git merge-base --is-ancestor <fix-sha> origin/main` (exit 0), not by the PR reading MERGED. Since 70a176e `.github/workflows/quality.yaml` also runs on `push: branches: [main]`, citing this incident as "a stacked merge-order trap", which validates the merged pair after the fact but does not prevent it; CONTRIBUTING.md says only "Branch from `main`". The lesson is the assistant's contemporaneous record of session 41ec4a24 (PR #43's body is the fullest account).
