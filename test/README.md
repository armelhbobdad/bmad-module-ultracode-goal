# Test Suites

Four layers, all wired into `npm run quality` and CI:

| Suite | Command | Covers |
|-------|---------|--------|
| Installation components | `npm run test:install` | module.yaml shape, SKILL.md frontmatter + routing, stage references, uv-script shebangs, marketplace.json version coupling |
| CLI integration | `npm run test:cli` | End-to-end install/update/uninstall in temp dirs: file copies, dev-artifact filtering, IDE skill installation, manifest accuracy, .gitignore handling |
| Python (pytest) | `npm run test:python` | The skill's deterministic scripts and the stage prose that drives them: gate_eval, gate_trail, preflight_check, formalize_check, status_render, headless_envelope, the PreToolUse/Stop hooks, the Cross-Session Recall and install-time merge plumbing, the health-check fingerprint tool, and the subskill registrations; and, in `test/test-*.py`, the GitHub Actions workflows: `release.yaml` step by step with stub `gh`, `git`, `npm` and `node` (the check wait, the cleanup after a failed run, the version and dist-tag rule, the resume path, the npm floor), the install smoke test, the action pins and Dependabot, and the release runbook's claims |
| Release tools | `npm run test:changes-tool`, `npm run test:docs-links-tool` | The change fragments and the release gate (`tools/changes.js`), the covered-surface diff backtested against the release tags (`tools/covered-surfaces.js`), the resume decisions (`tools/release-state.js`) and the required-checks lists (`tools/check-required-checks.js`) |

The validators (`npm run validate:skills`, `npm run validate:refs`, `npm run validate:fixtures`, `npm run validate:em-dash`, `npm run validate:tool-requirements`, `npm run validate:changes`) act as a fifth, static layer.
