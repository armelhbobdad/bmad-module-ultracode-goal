---
created: "2026-08-06 20:29"
session: "9507dda8-dad6-4b2c-ae09-66cac7a0d9d3"
---

# GitHub Actions outage fingerprint and component-status polling

Quality CI run 31118766021 (release-prep PR #96 for v2.1.0) lost its markdownlint and windows-latest validate jobs at "Set up job": action download returned "Service Unavailable", GitHub retried twice, then "Failed to resolve action download info": a GitHub Actions platform incident, not code. Attempts 1-4 all failed there before attempt 5 passed (only the attempt history shows it: `gh api repos/armelhbobdad/bmad-module-ultracode-goal/actions/runs/<id>/attempts/1/jobs`). Polling the GitHub Status incident list for the incident to disappear gave a false "resolved" signal mid-transition; the reliable signal was the GitHub Status API component status for Actions (and Pages), waited on until two consecutive `operational` readings. Set-up-phase failures across unrelated jobs with this fingerprint mean wait for the component and rerun the failed jobs rather than debugging the workflow; [RELEASING.md](../docs/_internal/RELEASING.md) has no outage section.
