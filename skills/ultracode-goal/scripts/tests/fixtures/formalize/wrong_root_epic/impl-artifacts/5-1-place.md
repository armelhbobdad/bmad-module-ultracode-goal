---
story_id: 5-1-place
epic: 5
gate_ability: ci-machine
---

# Story 5.1 — Place

**Gate-ability:** `ci-machine`

## Acceptance Criteria

1. The script asserts the resolved checks reflect the per-root flags exactly.
   - *Verification:* pytest test asserts `result['checks']['prd_present']` is False.
   - *Anti-vacuous twin:* AND a mutation using a blanket recursive glob must FAIL.
   - *Split:* `ci-deterministic`
