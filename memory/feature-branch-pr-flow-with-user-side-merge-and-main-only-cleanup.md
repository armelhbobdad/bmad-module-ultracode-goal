---
created: "2026-06-04 15:15"
session: "042f6fbb-9532-42bb-af73-6b22d68a1bca"
---

# Feature-branch PR flow with user-side merge and main-only cleanup

Every change goes through a fresh branch off main, a commit, a push and a PR against main; the user merges the PR themselves, and after the merge the branch is cleaned up locally and remotely so only main persists. The user stated it in the same form across sessions: "create a new branch off main, commit, push, open a PR against main. Once merged, clean the branch" (2026-06-08), "create a new branch off main" (2026-06-04, twice), "create new branch off main, commit and open a PR" (2026-08-06), "merged. clean up the local and remote branch you just created" (2026-06-03) and the sweep "delete all local and remote branches except main" (2026-08-07). So: branch off main, open the PR, then stop and wait for the user's "merged"; never merge it or push to main directly (the protected-branch guard registered in `.claude/settings.local.json` refuses commits and pushes from main anyway); after the merge, delete the branch locally and remotely (from main that is `gh api -X DELETE repos/armelhbobdad/bmad-module-ultracode-goal/git/refs/heads/<branch>` plus `git fetch --prune`). CONTRIBUTING.md documents the contributor PR flow but not that the maintainer merges and expects the branch cleaned afterwards.
