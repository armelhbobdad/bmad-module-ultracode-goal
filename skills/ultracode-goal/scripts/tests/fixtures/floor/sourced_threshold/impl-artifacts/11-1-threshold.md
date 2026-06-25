---
story_id: 11-1-threshold
epic: 11
gate_ability: ci-machine
---

# Story 11.1 — Threshold

**Gate-ability:** `ci-machine`

## Acceptance Criteria

1. The request handler responds within the stated latency budget and the test
   asserts the measured duration against it.
   The handler must respond in under 200 ms (cited: planning-artifacts/prd-fixture.md:7).
   - *Verification:* pytest test_threshold.py::test_latency asserts the measured
     duration is within budget and returncode 0.
   - *Anti-vacuous twin:* AND a mutation adding a sleep must FAIL the latency test.
   - *Split:* `ci-deterministic`
