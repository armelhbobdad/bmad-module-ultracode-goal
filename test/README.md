# Test Suites

Three layers, all wired into `npm run quality` and CI:

| Suite | Command | Covers |
|-------|---------|--------|
| Installation components | `npm run test:install` | module.yaml shape, SKILL.md frontmatter + routing, stage references, uv-script shebangs, marketplace.json version coupling |
| CLI integration | `npm run test:cli` | End-to-end install/update/uninstall in temp dirs: file copies, dev-artifact filtering, IDE skill installation, manifest accuracy, .gitignore handling |
| Python (pytest) | `npm run test:python` | The skill's deterministic scripts: gate_eval, preflight_check, the PreToolUse/Stop hooks, and the health-check fingerprint tool |

The validators (`npm run validate:skills`, `npm run validate:refs`) act as a fourth, static layer.
