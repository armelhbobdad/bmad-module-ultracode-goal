---
created: "2026-10-26 04:12"
session: "3db662c1-d326-4c49-93fb-f5b18179d765"
---

# Release bot PR shows no checks in gh pr checks

The bot PR that `release.yaml` opens (branch `release/bot/vX.Y.Z-<run_id>-<attempt>`) prints `no checks reported on the 'release/bot/...' branch` in `gh pr checks`, because its required checks run through `workflow_dispatch` of `quality.yaml` on the temp branch, not as pull-request checks. A watcher keyed on `gh pr checks <bot PR>` therefore never sees them pass, and gate 2 times out: on 2026-10-25 the first 3.0.0 `major` dispatch (run 40239814551) failed with "PR #167 was neither approved nor admin-bypass-merged within 30m.", its cleanup step closed the bot PR, and nothing was published. Watch the release run's own steps instead (`gh run view <run> --json jobs`): once "Wait for required status checks" is completed/success and "Wait for PR approval or admin-bypass merge" is in_progress, review and admin-merge the bot PR. The second dispatch (run 40242635011) did that and shipped 3.0.0 through bot PR #168.
