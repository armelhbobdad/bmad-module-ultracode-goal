---
story_id: 8-1-vacuous
epic: 8
gate_ability: ci-machine
---

# Story 8.1 — Vacuous

**Gate-ability:** `ci-machine`

## Acceptance Criteria

1. The test does `assert True`, so the criterion passes no matter what the code
   does under test.
   - *Verification:* pytest test_vacuous.py::test_runs executes the suite.
   - *Anti-vacuous twin:* AND a mutation breaking the feature must FAIL the test.
   - *Split:* `ci-deterministic`
