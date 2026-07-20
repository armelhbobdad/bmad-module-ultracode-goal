# Test Suites

Three layers, all wired into `npm run quality` and CI:

| Suite | Command | Covers |
|-------|---------|--------|
| Installation components | `npm run test:install` | module.yaml shape, SKILL.md frontmatter + routing, stage references, uv-script shebangs, marketplace.json version coupling |
| CLI integration | `npm run test:cli` | End-to-end install/update/uninstall in temp dirs: file copies, dev-artifact filtering, IDE skill installation, manifest accuracy, .gitignore handling |
| Python (pytest) | `npm run test:python` | The skill's deterministic scripts and the stage prose that drives them: gate_eval, gate_trail, preflight_check, formalize_check, status_render, headless_envelope, the PreToolUse/Stop hooks, the Cross-Session Recall and install-time merge plumbing, the health-check fingerprint tool, and the subskill registrations |

The validators (`npm run validate:skills`, `npm run validate:refs`, `npm run validate:fixtures`) act as a fourth, static layer.
