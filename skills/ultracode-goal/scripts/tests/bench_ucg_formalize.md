# Operator benchmark: `/ucg-formalize -H` over the Epic-11 floor fixtures

This is the AC6 **operator-benchmark** half of Story 1.3. The `ci-deterministic`
half (the kernel-JSON routing for every fixture) is asserted automatically by
`test_ucg_formalize_envelope.py::test_judgment_fixtures_route_to_blocked`. What an
operator must confirm here is the part a machine cannot: that the standalone
`/ucg-formalize -H` flow — running the kernel, the ONE throwaway JUDGMENT subagent,
the FR-6 mapping, and the five-key envelope end to end — routes each of the four
Epic-11 JUDGMENT-floor classes to `status=blocked` with the matching class named in
`reason`, routes a sound fixture to `status=complete`, and (the false-positive
guard) flips the UNKNOWN-marker case back to `complete`.

Do NOT fabricate results in the log below. Run the procedure, observe the real
emitted envelope, and record pass/fail per row. An unrun row stays `PENDING`.

## What is being benchmarked

The kernel deterministically routes the two never-machine-clearable JUDGMENT classes
(`vacuous_ac`, `invented_nfr_threshold`) straight to a blocked kernel verdict. The
two MECHANICAL floor classes (`leaked_tea_artifact`, `orphaned_index` regenerable)
are remediable: the kernel routes them to remediate-then-re-run, and whether the END
result blocks depends on the subagent's JUDGMENT read and on whether remediation
clears them. That subagent read is exactly what the operator confirms here — a
machine cannot grade it, which is why AC6 is `partly-operator`.

## Fixtures (under `scripts/tests/fixtures/floor/`)

| Fixture | Epic | Floor class | Expected envelope |
|---------|------|-------------|-------------------|
| `vacuous_ac` | 8 | vacuous AC (JUDGMENT) | `status=blocked`, reason names the vacuous-AC class |
| `leaked_tea` | 9 | leaked TEA artifact (MECHANICAL → if unclearable, JUDGMENT) | `status=blocked`, reason names the leaked-TEA class |
| `orphaned_index` | 10 | orphaned never-green index | `status=blocked`, reason names the orphaned-index class |
| `invented_threshold` | 11 | invented NFR threshold (JUDGMENT) | `status=blocked`, reason names the invented-threshold class |
| `all_clean` | 7 | (sound) | `status=complete` |
| `invented_threshold_unknown` | 11 | UNKNOWN-marker negative case | `status=complete` (flips from blocked) |

## Procedure (per fixture)

For each fixture directory `FX` and its Epic id `EID` from the table:

1. Point the resolved workflow scalars at the fixture so `/ucg-formalize` resolves
   it exactly as it resolves a real Epic:
   - `{project-root}` → the fixture dir `scripts/tests/fixtures/floor/FX`
   - `{planning_artifacts}` → `…/FX/planning-artifacts`
   - `{workflow.implementation_artifacts}` → `…/FX/impl-artifacts`
   - `{workflow.tea_config_path}` → `…/FX/tea/config.yaml`
2. Run the standalone command headless: `/ucg-formalize EID -H`.
3. The skill runs the kernel (step 1 of SKILL.md), applies the mechanical
   remediation pass (step 2), spawns the ONE JUDGMENT subagent (step 3), maps the
   verdict (step 4), and emits the five-key envelope (Headless section).
4. Read the emitted JSON envelope. Confirm:
   - the key set is exactly `{status, skill, decision_log, report, deferred_work}`
     plus `reason` only when blocked, with `skill == "ultracode-goal"`;
   - for the four defect fixtures: `status == "blocked"` and `reason` names the
     expected JUDGMENT class;
   - for `all_clean`: `status == "complete"`;
   - for `invented_threshold_unknown`: `status == "complete"` (the false-positive
     guard — the block was caused by the genuine unsourced number, not by blocking
     unconditionally).
5. Confirm `.decision-log.md` recorded the verdict and any remediations (NFR-9).

## Sanity pre-check (deterministic kernel half)

Before the operator run, the kernel-only routing can be sanity-checked without the
subagent (this is what the pytest asserts):

```
uv run {skill-root}/scripts/formalize_check.py --epic <EID> --project-root <FX> --planning-artifacts <FX>/planning-artifacts --impl-artifacts <FX>/impl-artifacts --tea-config <FX>/tea/config.yaml
```

Expected kernel `verdict`: `blocked` for `vacuous_ac` and `invented_threshold`;
`remediable` for `leaked_tea` and `orphaned_index`; `ready` for `all_clean` and
`invented_threshold_unknown`.

## Recorded pass/fail log

Operator: record the date, the observed `status`/`reason`, and PASS/FAIL per row.
Leave rows `PENDING` until actually run — do not pre-fill.

| Date | Fixture | Observed status | Observed reason | Result |
|------|---------|-----------------|-----------------|--------|
|      | `vacuous_ac` |  |  | PENDING |
|      | `leaked_tea` |  |  | PENDING |
|      | `orphaned_index` |  |  | PENDING |
|      | `invented_threshold` |  |  | PENDING |
|      | `all_clean` |  |  | PENDING |
|      | `invented_threshold_unknown` (negative) |  |  | PENDING |
