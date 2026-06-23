---
story_id: 9-1-leak
epic: 9
gate_ability: ci-machine
---

# Story 9.1 — Leak

**Gate-ability:** `ci-machine`

## Acceptance Criteria

1. The script asserts the JSON output keys equal the documented set exactly and
   the process exits 0.
   - *Verification:* pytest test_clean.py::test_schema asserts
     `set(out.keys()) == EXPECTED` and returncode 0.
   - *Anti-vacuous twin:* AND a mutation dropping a key must FAIL the schema test.
   - *Split:* `ci-deterministic`
