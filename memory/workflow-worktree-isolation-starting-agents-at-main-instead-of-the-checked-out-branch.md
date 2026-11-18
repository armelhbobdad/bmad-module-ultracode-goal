---
created: "2026-11-02 19:41"
session: "3db662c1-d326-4c49-93fb-f5b18179d765"
---

# Workflow worktree isolation starting agents at main instead of the checked-out branch

Workflow agents run with worktree isolation get a `.claude/worktrees/wf_*` worktree on a `worktree-wf_*` branch created at `main`, not at the branch the main checkout has checked out. On 2026-11-02 the main checkout was on `fix/v410-open-issues` (24f9340), yet the guard-budget fixer's worktree (`worktree-wf_2684b4cf-e04-1`) started at main and the agent had to move it to 24f9340. A workflow prompt that builds on an integration branch must name the exact base commit to reset onto (as the v3.3.0 rounds did with d5a1e56) and have each agent verify it before editing.
