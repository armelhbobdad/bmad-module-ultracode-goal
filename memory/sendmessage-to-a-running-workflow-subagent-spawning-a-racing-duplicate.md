---
created: "2026-10-30 19:23"
session: "3db662c1-d326-4c49-93fb-f5b18179d765"
---

# SendMessage to a running Workflow subagent spawning a racing duplicate

A `SendMessage` to a Workflow subagent that is still running resumes it as a second copy beside the original, and the two race on the same files and worktree. On 2026-10-30 a duplicate mutate fixer wrote a competing `mutate-msg-alt.txt` message file and a duplicate combine agent applied the round-1 patches while the workflow's own combine agent stood down; on 2026-11-02 messages to fix-up agents waiting on a full /tmp left the preflight fix-up sharing its worktree with a copy of itself. Do not message running workflow agents: stop the workflow and its agents (`TaskStop`), inspect each `.claude/worktrees/wf_*` state, and launch one fresh, controlled round from the saved worktrees.
