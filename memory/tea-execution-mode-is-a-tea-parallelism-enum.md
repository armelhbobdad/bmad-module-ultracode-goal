---
created: "2026-08-21 05:51"
session: "facc2bd7-2d0b-476e-b99c-5c1faf51f0b6"
---

# tea_execution_mode as a TEA parallelism enum, not a Create-mode toggle

`tea_execution_mode` is TEA's parallelism enum (every installed `bmad-testarch-*` skill reads it as `execution_mode: config.tea_execution_mode || 'auto',  // "auto" | "subagent" | "agent-team" | "sequential"`), and Create-vs-Resume is an interactive `[C] Create` prompt in each TEA SKILL.md, never a config key. A value outside the four is harmless: each step file then runs `normalizeConfigExecutionMode`, which returns `null` for it, and `|| 'auto'` applies, so a stray `create` resolves to `auto` (checked against TEA 1.27.2 on 2026-10-17; an earlier version of this note said the fallback does not rescue it, which was wrong). So preflight never writes the key, and logs a stray value without touching `_bmad/tea/config.yaml`, which the installer regenerates. The enum is documented in no tracked file here; the TEA-mode bullet in [preflight.md](../skills/ultracode-goal/references/preflight.md) and the `test_preflight_check.py` fixture that used `create` were corrected on the branch fix/preflight-conditional-wording.
