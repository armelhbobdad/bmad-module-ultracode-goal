# Contributing to UltraCode Goal

UCG runs a BMAD Epic autonomously to a machine-checked Definition-of-Done. Completion is decided by a deterministic script reading TEA's gate artifact — never by the model's opinion of its own work. See [README.md](README.md) for the pitch; this file covers how to land changes without breaking that contract.

UCG is a [BMAD](https://github.com/bmad-code-org/BMAD-METHOD) module. For BMAD philosophy, framework conventions, and module-authoring patterns in general, start at [docs.bmad-method.org](https://docs.bmad-method.org). This doc stays scoped to what's UCG-specific.

## What You Can Contribute

- **Stage references** (`skills/ultracode-goal/references/*.md`) — the per-stage instructions the conductor loads one at a time (ingest-and-scope, preflight, define-done, execute, gate, finalize). Example: tightening the resume logic in `execute.md`.
- **Deterministic scripts and their tests** (`skills/ultracode-goal/scripts/`) — the plumbing that the LLM must not second-guess: `preflight_check.py`, `gate_eval.py`, the hooks, `health_check_fp.py`. Every script change ships with a test in `scripts/tests/`.
- **Validators** — deterministic checks that run in `npm run quality`. Example: a check that flags a stage reference drifting from the stage table in `SKILL.md`.
- **Docs** (`docs/`) — tutorial / reference / explanation content.
- **Bug reports** — always useful, especially when they arrive via the workflow health-check loop (see below).

If you're not sure where a change belongs, open an issue and ask before writing code.

## Local Setup

**Prerequisites:**

- [Node.js](https://nodejs.org/) >= 22 (see `.nvmrc`)
- [Python](https://www.python.org/) >= 3.10
- [uv](https://docs.astral.sh/uv/) — runs the Python test suite
- `git`, `gh` — used by the run itself and by the health-check loop

```bash
git clone https://github.com/armelhbobdad/bmad-module-ultracode-goal.git
cd bmad-module-ultracode-goal
npm install           # also wires husky pre-commit hooks via "prepare"
npm run quality       # run the full local pre-flight
```

The `npm run quality` script is your contract with CI. If it passes locally, CI should too. The same steps run in [`.github/workflows/quality.yaml`](.github/workflows/quality.yaml) on every pull request. The Python gate runs the suite under `uv`:

```bash
uv run --with pytest pytest skills/ultracode-goal/scripts/tests/ -v
```

## Workflow for Changes

1. **Branch from `main`.** Name it like the commit scope: `fix/gate-eval-...`, `feat/health-check-...`, `docs/readme-...`, `ci/quality-...`.
2. **Match the commit-message convention from the git log.** UCG uses conventional-commit prefixes with a scoped subsystem:
   - `feat(skills): ...`
   - `fix(cli): ...`
   - `fix(health-check): ...`
   - `docs(readme): ...`
   - `ci(quality): ...`
   - `chore: ...` (no scope needed)

   `git log --oneline -20` is the authoritative style guide. Match what you see.

3. **Reference issues with `Fixes #NNN`** in the PR body. Use **same-repo GitHub issue numbers only** — internal author notes are not public contracts.
4. **Pre-commit hooks run automatically** via husky + lint-staged on staged files only.
5. **PR description:** explain _why_. What was broken, what does this change, and how did you verify it? Keep it honest and short.
6. **If you used Claude (or any AI assistant)** to write a non-trivial chunk of the change, add a `Co-Authored-By:` trailer to the commit. Not mandatory, but we prefer accurate attribution over silent ghostwriting.

## The Quality Gate

`npm run quality` must pass before you push. If it fails:

- **Fix the root cause.** Do not `git commit --no-verify`. Do not disable a rule to make the linter shut up. If a hook is wrong, fix the hook in a separate PR.
- **If a Python test fails on your machine but not in CI,** check your `uv` version and re-run the suite from a clean shell.

CI re-runs everything on the PR. A green local run and a red CI run usually means uncommitted files or a Node/uv version that drifts from `.nvmrc`. Check both before filing a CI bug.

## Workflow Health Check

Every UCG run that reaches Finalize ends with a health-check reflection step that can file a GitHub issue on your behalf when it finds a defect in its own stage references.

- **Deduplication is automatic.** Reports carry a deterministic fingerprint computed as the first 7 hex chars of `sha1("severity|ultracode-goal/{stage}|skills/ultracode-goal/references/{stage}.md|section-slug")`, applied as an `fp-XXXXXXX` label. The [`.github/workflows/health-check-dedup.yaml`](.github/workflows/health-check-dedup.yaml) Action extracts that label, finds the lowest-numbered open canonical issue with the same fingerprint, comments "duplicate of #N", upvotes the canonical issue to preserve the signal count, and closes the duplicate. **Re-reporting is safe.**
- **Triage** by the `health-check` plus `fp-*` labels. The `fp-*` label is the dedup key; the `health-check` label scopes the queue.
- **Maintainers must pre-create the labels** the loop and the Action depend on: `health-check`, `workflow-improvement`, `bug`, `friction`, `gap`, `duplicate`. The dedup Action assumes they exist.
- If you skipped the terminal step in-session, ask the conductor to run the health check for that run, or file via the [Workflow Health Check](.github/ISSUE_TEMPLATE/workflow-health-check.md) template directly.

## Releasing

Maintainers only — if you're not cutting a release, skip this section.

Releases go through the OIDC-backed GitHub Actions release pipeline — the only supported route, with a required-reviewer gate on the `release` environment and auto-provenance on the npm tarball. The canonical, step-by-step procedure (branch-protection rules, the `release` environment, npm Trusted Publisher registration, and the rollback playbook) lives in `docs/_internal/RELEASING.md`.

## What We Don't Accept

- **Changes that bypass `npm run quality`** — skipping hooks, excluding files from linters, loosening a validator to make a PR green. Fix the underlying issue instead.
- **Tests that mock the gate contract.** UCG's whole value is that completion is decided by `gate_eval.py` reading a real TEA artifact. A test that mocks the gate file's status to force an `advance` hides exactly the contract the suite exists to protect. Test against real artifact shapes.
- **Emoji in source files and docs.** Project standard. (Badges and the README's star CTA are the exceptions.)
- **Drive-by reformats.** Please don't reflow whole files or rename things you didn't touch.

## Code of Conduct and License

By participating, you agree to the [Code of Conduct](.github/CODE_OF_CONDUCT.md). Be decent; assume good faith; disagree with the argument, not the person.

Contributions are licensed under the project's [MIT License](LICENSE).

## Acknowledgement

UCG is maintained in spare hours. Good issues, small focused PRs, and willingness to iterate on review are the most useful things you can send. If UCG saved you an afternoon of babysitting an epic, a ⭐ keeps the lights on.
