---
story_id: 10-2-helper
epic: 10
gate_ability: ci-machine
---

# Story 10.2 — Helper

**Gate-ability:** `ci-machine`

## Acceptance Criteria

1. The helper script asserts its emitted count equals the expected value exactly
   and the process exits 0.
   - *Verification:* pytest test_helper.py::test_count asserts
     `out['count'] == EXPECTED` and returncode 0.
   - *Anti-vacuous twin:* AND a mutation off-by-one must FAIL the count test.
   - *Split:* `ci-deterministic`
