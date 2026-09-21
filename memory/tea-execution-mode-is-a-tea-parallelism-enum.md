---
created: "2026-08-21 05:51"
session: "facc2bd7-2d0b-476e-b99c-5c1faf51f0b6"
---

# tea_execution_mode as a TEA parallelism enum, not a Create-mode toggle

`tea_execution_mode` is TEA's parallelism enum (every installed `bmad-testarch-*` skill reads it as `execution_mode: config.tea_execution_mode || 'auto',  // "auto" | "subagent" | "agent-team" | "sequential"`), and Create-vs-Resume is an interactive `[C] Create` prompt in each TEA SKILL.md, never a config key. The TEA-mode bullet in [preflight.md](../skills/ultracode-goal/references/preflight.md) ("force **Create** mode ... Set/confirm whatever the TEA config exposes (`tea_execution_mode`)") and the fixture `tea_execution_mode: create  # forced for unattended runs` in `skills/ultracode-goal/scripts/tests/test_preflight_check.py` both tie the key to forcing Create mode, which is wrong: a session that writes `create` into a consumer's TEA config hands an out-of-enum value to all eight skills, and the `|| 'auto'` fallback does not rescue a present-but-invalid value. The enum is documented in no tracked file here (only the installed TEA step files carry it; `_bmad/tea/config.yaml` ships `tea_execution_mode: auto`), and none of the sites had been corrected at v2.2.0.
