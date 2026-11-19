---
created: "2026-11-18 20:42"
session: "5b07f74c-c6ab-4198-89e2-8c44ba4ea42d"
---

# worktrunk stage-all defaults on wt step commit and wt merge

In worktrunk 0.82, `wt step commit` and `wt merge` stage everything in the worktree by default, stray files and symlinked dependency folders included, and a merge can overwrite ignored files in the target. In a lab run that followed worktrunk's own Node recipe (symlink each worktree's `node_modules` to the primary worktree's), a merge replaced the primary worktree's real `node_modules` with a symlink pointing at itself, breaking every worktree's link. The `.gitignore` held `node_modules/`, and a trailing-slash pattern matches only a directory, not a symlink. Anyone trying wt for unattended agents here needs to control what it stages and keep dependency symlinks out of what it can commit.
