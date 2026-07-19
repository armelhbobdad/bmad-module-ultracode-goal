# Acceptance checklist — Story 7-2 (sample production story that failed its gate)

| AC | Planned test | Result |
|----|--------------|--------|
| 1 | `tests/acceptance/refund.spec.ts` -> `refunds a paid order` | PASS |
| 2 | `tests/acceptance/refund.spec.ts` -> `refuses a double refund` | FAIL |
