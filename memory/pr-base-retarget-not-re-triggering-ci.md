---
created: "2026-10-24 22:02"
session: "3db662c1-d326-4c49-93fb-f5b18179d765"
---

# PR base retarget not re-triggering CI

`.github/workflows/quality.yaml` triggers on `pull_request` with the default event types (opened, synchronize, reopened), so `gh pr edit <n> --base <branch>` leaves the check results measured against the old base in place, including the change-fragment step (`npm run changes:pr`), which compares the PR with its base. `gh pr close <n> && gh pr reopen <n>` re-runs every job against the new base without adding a commit; on 2026-10-24 that is how #157 was re-checked after its retarget, and all ten checks then passed against main.
