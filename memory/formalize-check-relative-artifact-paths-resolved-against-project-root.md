---
created: "2026-06-26 15:51"
session: "d1c66114-9e4b-4d21-bba3-1d908f3a5221"
---

# formalize_check.py relative artifact paths resolved against project-root

`skills/ultracode-goal/scripts/formalize_check.py` resolves a non-absolute `--planning-artifacts`, `--impl-artifacts` or `--tea-config` against `--project-root` in `_resolve()` (after expanding a literal `{project-root}` token), never against the shell's cwd, while `--project-root` itself is checked with `is_dir` against cwd, so a relative project-root plus `<FX>`-prefixed artifact flags doubles the prefix. A doubled directory that does not exist is not an invocation error: `build_verdict` records fail-closed mechanical gaps (`prd_absent`, `adr_absent`, `sprint_status_absent`, `no_in_scope_stories`, each `"remediable": true`) and `main()` exits 0, so the verdict reads `remediable` instead of failing, and a hand reproduction of a vacuous `ready` then looks already fixed. `scripts/tests/bench_ucg_formalize.md` invites the mistake by mapping `{project-root}` to the relative fixture dir and showing `<FX>`-prefixed flags. Pass absolute paths, as `_run_project` in `scripts/tests/test_formalize_check.py` does with `str(root / ...)`, and copy the `_mini_project` fixture layout rather than hand-rolling one. The trap is the assistant's contemporaneous record of session d1c66114, re-hit in session bf4b846a.
