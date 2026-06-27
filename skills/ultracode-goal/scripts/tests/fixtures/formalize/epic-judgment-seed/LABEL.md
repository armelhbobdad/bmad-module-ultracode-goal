# Benchmark label — epic-judgment-seed

Labelled DEFECT fixture for the step-3 second-hypothesis-stream benchmark. Reuses the
`invented_nfr_threshold` floor class: an NFR threshold number with no cited source and not
marked UNKNOWN.

- **Labelled defect (source:line):** `impl-artifacts/11-1-threshold.md:15` — "The handler must respond
  in under 200 ms." (a bare numeric threshold, no cited source, not marked UNKNOWN).
- **formalize_check.py ground truth (verified, absolute-path invocation, epic 11):**
  `verdict == "blocked"`, `checks.nfr_thresholds_unsourced == 1`, one `judgment_candidates[]` entry
  `kind == "invented_nfr_threshold"` with `source == "impl-artifacts/11-1-threshold.md:15"`.
- **Expected seeded-subagent result:** the seeded throwaway subagent CONFIRMS this
  machine-flagged candidate → `reds[]` contains an entry whose `source` EQUALS
  `impl-artifacts/11-1-threshold.md:15`. (A wrong-line or absent red FAILS the defect arm.)

Benchmark protocol: run `/ucg-formalize 11` (or preflight step 1b + step 3) against this dir and record
the matched `reds[]` source to the run's `.decision-log.md`.
