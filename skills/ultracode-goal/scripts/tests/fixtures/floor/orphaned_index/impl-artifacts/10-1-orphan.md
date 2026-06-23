---
story_id: 10-1-orphan
epic: 10
gate_ability: ci-machine
---

# Story 10.1 — Orphan

**Gate-ability:** `ci-machine`

## Acceptance Criteria

1. The script asserts the JSON output keys equal the documented set exactly and
   the process exits 0.
   - *Verification:* pytest test_orphan.py::test_schema asserts
     `set(out.keys()) == EXPECTED` and returncode 0.
   - *Anti-vacuous twin:* AND a mutation dropping a key must FAIL the schema test.
   - *Split:* `ci-deterministic`
   - traces: 10-9-ghost-story
