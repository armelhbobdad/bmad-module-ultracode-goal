---
story_id: 6-1-experience
epic: 6
gate_ability: ci-machine
---

# Story 6.1 — Experience

**Gate-ability:** `ci-machine`

## Acceptance Criteria

1. The onboarding flow feels clear and intuitive to a first-time operator, with
   a reasonable, user-friendly progression that reads as graceful.
   - *Verification:* pytest test_experience.py::test_onboarding_walkthrough plus a
     moderated usability session reviewed against the named rubric.
   - *Anti-vacuous twin:* AND a mutation that strips the progress affordance must
     FAIL the moderated walkthrough — the twin proves the assertion is load-bearing.
   - *Split:* `ci-deterministic`

2. The error copy is sensible and appropriate for a non-technical reader.
   - *Verification:* pytest test_experience.py::test_error_copy_review against the
     named editorial rubric artifact.
   - *Anti-vacuous twin:* AND a mutation that blanks the copy must FAIL the review.
   - *Split:* `operator`

3. The script asserts the JSON payload keys equal the documented set exactly and
   the process exit code is 0.
   - *Verification:* pytest test_experience.py::test_schema asserts
     `set(out.keys()) == EXPECTED` and returncode 0.
   - *Anti-vacuous twin:* AND a mutation dropping a key must FAIL the schema test.
   - *Split:* `ci-deterministic`
