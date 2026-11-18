---
created: "2026-10-17 12:58"
session: "32c0ba1b-6b80-4f30-bf50-a7a5a6ac2c6d"
---

# Sibling-specific ids surviving a port from bmad-module-skill-forge

Files ported from ../bmad-module-skill-forge carry the sibling's own identifiers, and a sweep for the module names, `issue #`, `#[0-9]{3}`, `Story [0-9]`, `AC ?#`, `Default` and `pinned` did not catch them all. A review of the release-pipeline port found sibling Actions run ids ("Empirical repro: run 24842070205 / 24844278359", which return 404 here) in release.yaml, a sibling PR number written without a hash ("for example [509]", `prs: [509, 517]`) in tools/changes.js and test/test-changes.js, and sibling history stated as this repository's fact (a ruleset PUT that "has been refused" with HTTP 422, a 20-minute Windows job timing). Before committing a port, also grep for bare three-digit numbers in brackets, long run ids, and timings or claims quoted from the sibling's runs, then remove or neutralize each one (the fixture became `issues: [3], prs: [12, 14]`) and rename the sibling's `Default` ruleset to `main-protection`.

Related: [[no-skill-forge-or-skf-mentions-in-commit-messages]]
