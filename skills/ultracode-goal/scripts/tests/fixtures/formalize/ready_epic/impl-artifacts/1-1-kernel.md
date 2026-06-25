---
story_id: 1-1-kernel
epic: 1
gate_ability: ci-machine
---

# Story 1.1 — Kernel

**Gate-ability:** `ci-machine`

## Acceptance Criteria

1. Running the script over a fixture emits a JSON object whose top-level keys are
   exactly the documented set and the process exits 0.
   - *Verification:* pytest test_formalize_check.py::test_schema_keys asserts
     `set(out.keys()) == FR5_TOP_KEYS` and returncode 0.
   - *Anti-vacuous twin:* AND a negative case feeding malformed input asserts a
     mutation that drops a key must FAIL the test.
   - *Split:* `ci-deterministic`

2. The emitted budget equals the gap count exactly.
   - *Verification:* pytest test asserts `out['mechanical_budget'] == len(out['mechanical_gaps'])`.
   - *Anti-vacuous twin:* AND a mutation that returns a hardcoded count must FAIL.
   - *Split:* `ci-deterministic`
