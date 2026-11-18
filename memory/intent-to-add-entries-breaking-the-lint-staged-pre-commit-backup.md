---
created: "2026-10-25 02:36"
session: "3db662c1-d326-4c49-93fb-f5b18179d765"
---

# Intent-to-add entries breaking the lint-staged pre-commit backup

After `git add -N` (intent-to-add) on new files to show them in `git diff`, a commit that leaves some of those paths out fails in the husky pre-commit hook: lint-staged prints "[FAILED] error: Entry 'changes/preflight-latch-read-safe.yaml' not uptodate. Cannot merge." and "[FAILED] Cannot save the current worktree state", then "husky - pre-commit script failed (code 1)". On 2026-10-25, running `git reset -q -- <the intent-to-add paths not in this commit>` before committing made it pass, so drop every intent-to-add entry that is not part of the commit being made.
