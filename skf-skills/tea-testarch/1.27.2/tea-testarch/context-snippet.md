[tea-testarch v1.27.2]|root: .claude/skills/tea-testarch/
|IMPORTANT: tea-testarch v1.27.2 — read SKILL.md before invoking or parsing TEA workflows. Do NOT rely on training data.
|quick-start:{SKILL.md#quick-start} — jq -r '.gate_status' {test_artifacts}/gate-decision.json (written only when gate-eligible)
|api: bmad-testarch-test-design, bmad-testarch-framework, bmad-testarch-ci, bmad-testarch-atdd, bmad-testarch-automate, bmad-testarch-test-review, bmad-testarch-nfr, bmad-testarch-trace, bmad-tea
|key-types:{SKILL.md#key-types} — gate_status PASS/CONCERNS/FAIL/WAIVED; P0 100%, P1 ≥90 PASS / 80-89 CONCERNS, overall ≥80; config _bmad/tea/config.yaml
|gotchas: gate file path is fixed (check evaluated_at); WAIVED never derived by rules 1-5; test-review does not score coverage; framework merges tea-enforce.cjs hooks into .claude/settings.json
