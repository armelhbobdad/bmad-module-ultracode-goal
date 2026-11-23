---
created: "2026-11-23 12:49"
session: "775f5088-65e5-4882-8e03-0238bc221ade"
---

# gh pr merge --delete-branch removing the branch's local worktree

With `gh` 2.105.0, `gh pr merge <n> --merge --admin --delete-branch` run from the main checkout also removed the linked worktree that had the PR's branch checked out, and deleted the local branch with it. On 2026-11-23 four worktrees under `.claude/worktrees/` were gone after their PRs merged, `git worktree list` showed only the main checkout, and a later `EnterWorktree` into one failed with "ENOENT: no such file or directory, realpath '.../.claude/worktrees/ucg-p1'". The same happened to worktrees the EnterWorktree tool had created. All of them were clean and pushed, so nothing was lost; what it does to a worktree with uncommitted changes was not tried. Leave a worktree with ExitWorktree `keep` before merging its PR, finish everything that needs it first, and do not count on it existing afterwards.
