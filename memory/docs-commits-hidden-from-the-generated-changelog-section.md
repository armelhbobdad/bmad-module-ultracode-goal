---
created: "2026-08-02 18:42"
session: "69c5ff6f-e98d-41a7-866b-444f3e6f1641"
---

# docs: commits hidden from the generated CHANGELOG section

The release job generates each `## [x.y.z]` block of CHANGELOG.md with `npx conventional-changelog-cli -p conventionalcommits -i CHANGELOG.md -s` (`.github/workflows/release.yaml`), and the conventionalcommits preset renders only feat, fix, perf and revert; docs, test, chore, refactor, build and ci are hidden. In this module `skills/ultracode-goal/references/*.md` steer runtime behaviour (docs/\_internal/STABILITY.md calls their prose an "authoring surface"), so behaviour changes committed as `docs:` never reach the machine section: 8643c43 (inert controls) and ed6024a (guard matcher) in 2.0.0, and even ab4ea90 touching gate_eval.py in 2.2.0. They reached CHANGELOG.md only through the hand-written Added/Changed/Fixed narrative filed above the machine section, which has been the route every release since 2.0.0. The machine section is never a complete record of a release; no `.versionrc` or preset config makes `docs` visible, and neither RELEASING.md nor CONTRIBUTING.md says so.
