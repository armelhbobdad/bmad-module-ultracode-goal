---
created: "2026-08-02 13:38"
session: "69c5ff6f-e98d-41a7-866b-444f3e6f1641"
---

# Scratch directory children flagged as leaked TEA artifacts

`_leaked_tea_artifacts()` in `skills/ultracode-goal/scripts/formalize_check.py` walks `implementation_artifacts` with `rglob("*")` and flags any file whose name contains a `TEA_ARTIFACT_MARKERS` token (`trace`, `traceability`, `test-design`, ...); its exemption `_is_ucg_impl_artifact()` skips a file whose own name starts with a dot, never a file inside a dot-prefixed directory. A Rust build under `.scratch-<story_id>/` (`.scratch-2-3/target/debug/deps/libbacktrace-*.rlib`) therefore matches `trace` and lands in `mechanical_gaps[]` as "TEA artifact under the source/impl tree instead of the trace_output root" (severity medium, remediable), keeping the formalize verdict off `ready` and blocking the launch gate, and the prescribed MOVE remediation in [preflight.md](../skills/ultracode-goal/references/preflight.md) would misfile build output into the trace root. Step 0 of [execute.md](../skills/ultracode-goal/references/execute.md) claims the dot prefix keeps scratch out of every default glob, which does not hold for this scan; the practical exposure is a stale `.scratch-<story_id>/` left by a dead run when a later invocation formalizes the same tree, so delete the directory before Stage 2 rather than moving its files.
