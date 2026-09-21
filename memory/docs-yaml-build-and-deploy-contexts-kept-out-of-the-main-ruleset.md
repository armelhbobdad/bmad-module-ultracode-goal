---
created: "2026-08-07 11:31"
session: "9507dda8-dad6-4b2c-ae09-66cac7a0d9d3"
---

# docs.yaml build and deploy contexts kept out of the main ruleset

The main-branch ruleset (`main-protection`, id 17255028, read by release.yaml from the repo variable RELEASE_RULESET_ID) requires only the quality.yaml contexts listed in [RELEASING.md](../docs/_internal/RELEASING.md); `.github/workflows/docs.yaml` also reports `build` and `deploy` on main, and neither is required. Do not add them: docs.yaml's `pull_request` trigger has a `paths` filter (docs/**, website/**, tools/build-docs.js, the workflow itself, package.json), so `build` never reports on a PR outside that filter, and `deploy` never reports on any PR because of `if: github.ref == 'refs/heads/main' && github.event_name != 'pull_request'`; a required docs context would leave such a PR stuck behind an Expected check. RELEASING.md's instruction to add new contexts to the ruleset applies to quality.yaml jobs only; the constraint is the assistant's contemporaneous record of session 9507dda8. Verify the live list with `gh api /repos/armelhbobdad/bmad-module-ultracode-goal/rulesets/17255028 --jq '[.rules[] | select(.type=="required_status_checks") | .parameters.required_status_checks[].context]'`.
