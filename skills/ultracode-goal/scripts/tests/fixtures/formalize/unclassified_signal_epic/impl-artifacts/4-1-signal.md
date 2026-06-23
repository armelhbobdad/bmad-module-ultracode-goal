---
story_id: 4-1-signal
epic: 4
gate_ability: ci-machine
---

# Story 4.1 — Signal

**Gate-ability:** `ci-machine`

## Acceptance Criteria

1. The script asserts the JSON output keys equal the documented set exactly, and
   carries a detectable check-shaped anomaly the kernel has no classification
   for: UCG-UNCLASSIFIED-SIGNAL on this load-bearing line.
   - *Verification:* pytest test asserts `set(out.keys()) == FR5_TOP_KEYS`.
   - *Anti-vacuous twin:* AND a mutation dropping a key must FAIL the test.
   - *Split:* `ci-deterministic`
