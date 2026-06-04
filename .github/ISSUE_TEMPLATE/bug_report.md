---
name: Bug report
about: Create a report to help us improve
title: ''
labels: ''
assignees: ''
---

**Describe the bug**
A clear and concise description of what the bug is.

**Steps to Reproduce**
What led to the bug and can it be reliably recreated — if so, with what steps.

**Expected behavior**
A clear and concise description of what you expected to happen.

**Run details (please be specific if relevant)**
- Epic shape (number of stories):
- Profile (production / `--light`):
- Execution (sequential / `--parallel`):
- Run mode (attended / headless `-H`):
- Claude Code version (`claude --version`):
- OS:
- Module version (`npm ls bmad-module-ultracode-goal`):

**Gate / decision artifacts**
If the bug is about a verdict, attach or paste the relevant `gate-decision.json` (or the `e2e-trace-summary.json` fallback) and the `.decision-log.md` line for the affected story. The `reasons` array in `gate_eval.py` output is especially useful.

**PR**
If you have an idea to fix and would like to contribute, please indicate here that you are working on a fix, or link to a proposed PR. Please review the [CONTRIBUTING.md](../../CONTRIBUTING.md) — contributions are always welcome!

**Additional context**
Add any other context about the problem here. The more information you can provide, the easier it will be to suggest a fix.
