# Acceptance checklist — Story 7-1 (sample production story)

Red-phase checklist: every acceptance criterion mapped to the acceptance test that has to be
un-skipped and driven green before the story can close.

| AC | Planned test | Result |
|----|--------------|--------|
| 1 | `tests/acceptance/checkout.spec.ts` -> `renders the cart` | PASS |
| 2 | `tests/acceptance/checkout.spec.ts` -> `applies a discount code` | PASS |
| 3 | `tests/acceptance/checkout.spec.ts` -> `rejects an expired code` | PASS |
