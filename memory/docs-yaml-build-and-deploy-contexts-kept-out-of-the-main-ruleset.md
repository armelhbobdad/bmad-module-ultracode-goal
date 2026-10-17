---
created: "2026-08-07 11:31"
session: "9507dda8-dad6-4b2c-ae09-66cac7a0d9d3"
---

# docs.yaml build and deploy contexts kept out of the main ruleset

The main-branch ruleset (`main-protection`, id 17255028; since the release pipeline of 2026-10-17, release.yaml finds it by name, and the repo variable RELEASE_RULESET_ID it read before was deleted the same day) requires only the quality.yaml contexts listed between the required-checks markers of [RELEASING.md](../docs/_internal/RELEASING.md), which `tools/check-required-checks.js` compares with quality.yaml and the live ruleset. `.github/workflows/docs.yaml` reports `build` and `deploy`, and neither is required. Do not add them: since that pipeline docs.yaml runs only by `workflow_dispatch` (the release run dispatches it at each stable tag), so neither context ever reports on a pull request, and a required docs context would leave every PR stuck behind an Expected check. Before it, the same held through docs.yaml's path-filtered `pull_request` trigger and its main-only `deploy`. RELEASING.md's instruction to add new contexts to the ruleset applies to quality.yaml jobs only; the constraint is the assistant's contemporaneous record of session 9507dda8. Verify the live list with `gh api /repos/armelhbobdad/bmad-module-ultracode-goal/rulesets/17255028 --jq '[.rules[] | select(.type=="required_status_checks") | .parameters.required_status_checks[].context]'`.
