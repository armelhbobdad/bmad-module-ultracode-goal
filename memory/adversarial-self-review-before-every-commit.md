---
created: "2026-08-03 02:40"
session: "4e2f68a1-8a5e-438b-af3a-ea847b88489e"
---

# Adversarial self-review before every commit

Before any commit lands in this repository, run an independent adversarial review of the diff; the user's stated expectation, from the 2026-08-03 handoff prompt: "adversarially review your own work before committing (seven for seven at catching a real defect, including one where the right answer was not to ship)". The not-to-ship case was the CHANGELOG drain automation, which stayed parked. Nothing enforces the habit: husky/lint-staged lint staged files, `.husky/pre-push` runs `npm test`, and CONTRIBUTING.md only requires `npm run quality` to pass; the practice is visible only in commit bodies ("Pre-commit adversarial review: 18 confirmed findings fixed" in 2b38a29). Do it with an independent subagent or the bmad-review-adversarial-general / bmad-code-review skill; the ultracode-goal runtime's gate stages review the epic being driven, not the module's diff.
