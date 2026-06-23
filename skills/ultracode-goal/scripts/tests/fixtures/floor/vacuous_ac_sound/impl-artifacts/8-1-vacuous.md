---
story_id: 8-1-vacuous
epic: 8
gate_ability: ci-machine
---

# Story 8.1 — Vacuous

**Gate-ability:** `ci-machine`

## Acceptance Criteria

1. The test asserts the exit code equals 0 and the emitted JSON keys equal the
   documented set exactly.
   - *Verification:* pytest test_vacuous.py::test_runs asserts
     `set(out.keys()) == EXPECTED` and returncode 0.
   - *Anti-vacuous twin:* AND a mutation breaking the feature must FAIL the test.
   - *Split:* `ci-deterministic`
