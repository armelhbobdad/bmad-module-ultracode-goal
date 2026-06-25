# Benchmark label — epic-clean-control (story 2.3 AC-5)

Labelled CLEAN CONTROL fixture for the step-3 second-hypothesis-stream benchmark. Reuses the Epic-11
`all_clean` floor fixture — no JUDGMENT defects of any class.

- **Labelled defects:** none.
- **formalize_check.py ground truth (epic 7):** no `invented_nfr_threshold` (or other JUDGMENT-class)
  `judgment_candidates[]`; nothing to seed as a RED hypothesis.
- **Expected seeded-subagent result (AC-5 oracle):** `reds: []`.

This control arm is MANDATORY and non-vacuous: a seed implementation that rubber-stamps every
`judgment_candidate` into a RED would surface a red here against the `reds: []` ground truth and FAIL —
distinguishing genuine confirm-or-clear from blind promotion (guards the AD-1 decider boundary at
runtime). Operator-benchmark half parked to the end-of-epic batch review.
