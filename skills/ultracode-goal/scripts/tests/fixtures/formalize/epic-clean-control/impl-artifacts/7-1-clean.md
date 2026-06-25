---
story_id: 7-1-clean
epic: 7
gate_ability: ci-machine
---

# Story 7.1 — Clean

**Gate-ability:** `ci-machine`

## Acceptance Criteria

1. The script asserts the JSON output keys equal the documented set exactly and
   the process exits 0.
   - *Verification:* pytest test_clean.py::test_schema asserts
     `set(out.keys()) == EXPECTED` and returncode 0.
   - *Anti-vacuous twin:* AND a mutation dropping a key must FAIL the schema test.
   - *Split:* `ci-deterministic`
