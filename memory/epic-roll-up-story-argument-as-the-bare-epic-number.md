---
created: "2026-10-18 13:19"
session: "32c0ba1b-6b80-4f30-bf50-a7a5a6ac2c6d"
---

# Epic roll-up --story argument as the bare epic number

`gate_eval.py --epic-level --rollup --story <epic>` matches `<epic>` against `preflight_check._epic_id_of(key)` for each story row in `sprint-status.yaml`, so it takes the bare epic number (`--story 52`), not the epic row key (`epic-52`). Passing `--story epic-52` returns `gate_status: NOT_EVALUATED` and `escalate` with "no stories for epic epic-52 in sprint-status.yaml; roll-up refused", which reads like a real block. `skills/ultracode-goal/references/gate.md` calls the argument "the sprint-status grouping key" and writes it `--story <epic_id>`, which is easy to misread as the `epic-<id>` row key. When running the roll-up by hand against a consumer project, also pass `--trace-output <project>/_bmad-output/test-artifacts/traceability`.
