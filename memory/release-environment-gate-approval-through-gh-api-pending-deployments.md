---
created: "2026-11-16 21:06"
session: "36d1b26b-c2ef-451e-ae63-24abfb0b9fe2"
---

# Release environment gate approval through gh api pending_deployments

Gate 1 of `release.yaml` (the `release` environment) can be approved from the CLI instead of the "Approve and deploy" button that `docs/_internal/RELEASING.md` describes: `gh api repos/armelhbobdad/bmad-module-ultracode-goal/actions/runs/<run>/pending_deployments` gives the environment id and `current_user_can_approve`, then `gh api -X POST repos/armelhbobdad/bmad-module-ultracode-goal/actions/runs/<run>/pending_deployments -F 'environment_ids[]=<id>' -f state=approved -f comment=<text>` releases the job (it moved to `in_progress`). For v7.2.0, gate 2 was then cleared with `gh pr merge <bot PR> --merge --admin` (bot PR #238) after checking that the bot PR changed only the version bump and CHANGELOG. Both gates were cleared this way only after the user said "do it end to end. You have the full authorization." Related: [[release-bot-pr-shows-no-checks-in-gh-pr-checks]].
