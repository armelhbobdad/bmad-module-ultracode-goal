---
story_id: 1-2-floor
epic: 1
gate_ability: ci-machine
---

# Story 1.2 — Floor

**Gate-ability:** `ci-machine`

## Acceptance Criteria

1. Over a fixture the script reports the leaked count as a non-zero JSON value and
   the verdict equals the documented string exactly.
   - *Verification:* pytest test asserts `result['checks']['tea_artifacts_in_source']`
     count matches and `result['verdict'] == 'blocked'`.
   - *Anti-vacuous twin:* AND a clean twin fixture must FAIL if it fires vacuously.
   - *Split:* `ci-deterministic`
