# Contributing to UltraCode Goal

UCG runs a BMAD Epic autonomously to a machine-checked Definition-of-Done. Completion is decided by a deterministic script reading TEA's gate artifact, never by the model's opinion of its own work. See [README.md](README.md) for the pitch; this file covers how to land changes without breaking that contract.

UCG is a [BMAD](https://github.com/bmad-code-org/BMAD-METHOD) module. For BMAD philosophy, framework conventions, and module-authoring patterns in general, start at [docs.bmad-method.org](https://docs.bmad-method.org). This doc stays scoped to what's UCG-specific.

## What You Can Contribute

- **Stage references** (`skills/ultracode-goal/references/*.md`): the per-stage instructions the conductor loads one at a time (ingest-and-scope, preflight, define-done, execute, gate, finalize). Example: tightening the resume logic in `execute.md`.
- **Deterministic scripts and their tests** (`skills/ultracode-goal/scripts/`): the plumbing that the LLM must not second-guess: `preflight_check.py`, `gate_eval.py`, the hooks, `health_check_fp.py`. Every script change ships with a test in `scripts/tests/`.
- **Validators**: deterministic checks that run in `npm run quality`. Example: a check that flags a stage reference drifting from the stage table in `SKILL.md`.
- **Docs** (`docs/`): tutorial / reference / explanation content.
- **Bug reports**: always useful, especially when they arrive via the workflow health-check loop (see below).

If you're not sure where a change belongs, open an issue and ask before writing code.

## Local Setup

**Prerequisites:**

- [Node.js](https://nodejs.org/) >= 22, the supported floor (`engines.node`); development and CI run Node 24 (see `.nvmrc`)
- [Python](https://www.python.org/) >= 3.11
- [uv](https://docs.astral.sh/uv/): runs the Python test suite
- `git`, `gh`: used by the run itself and by the health-check loop

```bash
git clone https://github.com/armelhbobdad/bmad-module-ultracode-goal.git
cd bmad-module-ultracode-goal
npm install           # also wires husky hooks and links the reference skills
npm run quality       # run the full local pre-flight
```

The `npm run quality` script is your contract with CI. If it passes locally, CI should too. The same steps run in [`.github/workflows/quality.yaml`](.github/workflows/quality.yaml) on every pull request (as parallel jobs there; locally the stages run concurrently via `run-p`, and a failure kills the other stages). Every output line carries its stage label. A stage's stdout is additionally buffered and printed as one block when the stage finishes; stderr is not buffered, so a failing tool that reports on stderr (prettier does) prints its labeled lines live, possibly interleaved with other stages. `npm test` is an alias for the same gate. The Python gate runs the suite under `uv`, parallelized with `pytest-xdist`: the skill's script tests, and the workflow tests under `test/` (`test-*.py`):

```bash
uv run --with pytest==9.1.1 --with pytest-xdist==3.8.0 --with pyyaml==6.0.3 pytest skills/ultracode-goal/scripts/tests/ test/ -o "python_files=test-*.py test_*.py *_test.py" -n auto
```

When a failure needs localizing, re-run just that file serially and verbosely: `uv run --with pytest==9.1.1 pytest skills/ultracode-goal/scripts/tests/test_<name>.py -v` (for a workflow test, `uv run --with pytest==9.1.1 --with pyyaml==6.0.3 pytest test/test-<name>.py -v`).

The tool versions live in one list, `tools/tool-requirements.yaml`: each tool's minimum and the versions UCG has run on. The prerequisites table in `docs/getting-started.md` is generated from it, so to change a version, edit the list and run `node tools/tool-requirements.js --write`. `validate:tool-requirements` fails when a copy elsewhere disagrees with it: the minimums in `README.md`, `CONTRIBUTING.md` and `docs/`, the README Python badge, `engines.node`, `.nvmrc`, the workflows' Node and Python versions, the highest of the Claude Code versions `preflight_check.py` refuses to launch below, the `requires-python` headers of the skill's scripts, and the README "Tested with" rows.

Write no em dashes (U+2014) in anything you add, including commit messages: use a colon, a comma, parentheses or a new sentence. `validate:em-dash` fails on any em dash in the published docs (`README.md`, `docs/` outside `docs/_internal/`, `website/`) and on any em dash in the lines or commit messages your branch adds. It skips `CHANGELOG.md`, any `package-lock.json`, the generated reference skills under `skf-skills/` and the BMAD engine `.py` files vendored verbatim directly inside `skills/ultracode-goal/scripts/tests/fixtures/engine/` and `fixtures/engine-6.12/` (a new engine folder is added to the validator's `VENDORED_DIRS`).

### Reference skills

`skf-skills/` tracks version-pinned reference skills for the tools UCG conducts: BMAD Method 6.12.0 (`bmad-method-bmm`, `bmad-method-installer`), TEA 1.27.2 (`tea-testarch`), Claude Code 2.1.283 (`cc-primitives`), BMad Builder 2.2.2 (`bmad-builder`) and graphify 0.9.92 (`graphify-kg`), whose CLI the optional knowledge-graph refresh runs. It also tracks IWE 0.28.0 (`iwe-kg`), the CLI that keeps this repository's contributor memory in `memory/`, and a stack skill that ties all seven together (`bmad-module-ultracode-goal-stack`). Load the relevant one before changing code that drives or reads one of these tools.

Claude Code loads project skills only from `.claude/skills/`, which is gitignored, so `npm install` links each skill there through the `active` version of its group. The link step is `tools/link-reference-skills.js`, run from npm's `postprepare` script, and the links follow a newly activated version on their own. Re-run it with `npm run skills:link` after the BMAD or UCG installer rewrites `.claude/skills/`, or after a pull that adds a skill; `node tools/link-reference-skills.js --check` reports what is missing or stale without changing anything. It only ever touches its own links: a real folder or another link with the same name is left in place and reported, and it refuses to run when `.claude/` or `.claude/skills/` is itself a link. On Windows without symlink support, git checks `active` out as a plain file holding the version. The linker then links that version's folder directly, with a junction when symlinks are not allowed, so re-run it after `active` changes.

Claude Code lists the linked skills in every session, but with many skills installed it can show them without their descriptions. For an always-on index of each skill's version and API, copy the `skf-skills/*/active/*/context-snippet.md` files into your `CLAUDE.local.md`, which Claude Code loads after `CLAUDE.md`. Both files are gitignored, and `CLAUDE.md` is kept for the index an export of these skills writes.

For another agent (Codex, Cursor, GitHub Copilot, OpenCode, Gemini CLI and others read `.agents/skills/`), install each skill with the [`skills`](https://www.npmjs.com/package/skills) CLI, one version folder per command. The loop reads `active` in either form:

```bash
for a in skf-skills/*/active; do
  g=$(dirname "$a"); v=$(basename "$(readlink "$a" || cat "$a")")
  npx -y skills@1.7.0 add "./$g/$v/${g##*/}" -a codex -y || break
done
```

- Pass one version folder per skill, as the loop does. Pointing the CLI at `./skf-skills` as a whole installs the oldest version of a group that keeps several.
- Always pass `-a`. Without it, `-y` picks the agents itself. When it detects agents, it installs into those plus `.agents/skills/`, and for Claude Code that replaces the linker's link with one to a copy that no longer follows `active`. When it detects none, it installs into every agent it knows, including this repository's `skills/` folder.
- Never run `npx skills remove --all` here. It scans every agent's folder, `skills/` included, so it deletes the tracked `skills/ultracode-goal/` source along with the installer-written skills in `.claude/skills/`.
- The CLI copies each skill, so re-run the loop after the reference skills change. Its `skills-lock.json` cannot restore skills for Claude Code; both it and `.agents/` are gitignored. Set `DISABLE_TELEMETRY=1` to turn off the CLI's usage telemetry.

## Workflow for Changes

1. **Branch from `main`.** Name it like the commit scope: `fix/gate-eval-...`, `feat/health-check-...`, `docs/readme-...`, `ci/quality-...`.
2. **Match the commit-message convention from the git log.** UCG uses conventional-commit prefixes with a scoped subsystem:
   - `feat(skills): ...`
   - `fix(cli): ...`
   - `fix(health-check): ...`
   - `docs(readme): ...`
   - `ci(quality): ...`
   - `chore: ...` (no scope needed)

   `git log --oneline -20` is the authoritative style guide. Match what you see. The prefix is for the history only: release notes and the version bump come from change fragments (step 7), so the commit type and the merge style do not change what a release says.

3. **Reference issues with `Fixes #NNN`** in the PR body. Use **same-repo GitHub issue numbers only**; internal author notes are not public contracts.
4. **Pre-commit hooks run automatically** via husky + lint-staged on staged files only.
5. **PR description:** explain _why_. What was broken, what does this change, and how did you verify it? Keep it honest and short.
6. **If you used Claude (or any AI assistant)** to write a non-trivial chunk of the change, add a `Co-Authored-By:` trailer to the commit. Not mandatory, but we prefer accurate attribution over silent ghostwriting.
7. **Add a change fragment** in the same pull request for each change a user or a pipeline can notice, and run `npm run changes:pr` before you push: see [Change fragments](#change-fragments).

## Change fragments

Release notes are written from change fragments, not from commit subjects. A pull request that changes something a user or a pipeline can notice adds one short YAML file per change to [`changes/`](changes/README.md), named after the change: `changes/<topic>.yaml`. At release, the workflow renders every fragment added since the last stable release into the new `CHANGELOG.md` block and the GitHub Release, and refuses a `version_bump` smaller than the fragments call for. Fragments are never deleted: a release takes only the ones added since the last stable tag. A released fragment is never read again, so a new change always goes in a new file: the release refuses a released fragment that was edited, renamed or copied.

**When.** Add a fragment when a stage behaves differently, when a flag, verdict, status, blocker or `customize.toml` key appears or goes, when the install changes, or when the user docs gain something worth announcing. Refactors, tests, CI and maintainer-only docs need none; a refactor of the code the package ships says so in a commit message instead (see [The pull request check](#the-pull-request-check)).

**Which type.** Type the change by what a user sees, not by the commit prefix, and pick the higher type when unsure:

- `breaking`: the change removes or renames a covered item (one of the public surfaces [STABILITY.md](docs/_internal/STABILITY.md) lists: a CLI subcommand or option, a `[workflow]` key of `customize.toml`, a key of the headless emit shape, the skill name or an invocation phrase, a `gate_eval.py` flag, choice, `gate_status`, verdict or printed key), changes the verdict a documented invocation returns, raises a requirement, or makes an input that used to succeed now halt or exit non-zero. A `breaking` fragment needs a `migration`: the exact action a user takes.
- `added`: a new flag, option, `customize.toml` key, preflight blocker or capability.
- `changed`: the output or a default is different, and nothing was removed.
- `fixed`: the behaviour now matches the docs.
- `docs`: a change to the user docs worth announcing.

`lead` is a sixth type for the paragraph that opens a release's notes, usually added when the release is prepared.

```yaml
type: added
scope: ultracode-goal
summary: |
  New `--cycle-profile delta` for `gate_eval.py`: a mid-loop gate that re-ran only the failed assessor dimensions is capped at `reloop`, so it can never advance a story.
```

Write flags, statuses, verdicts and file names in backticks: a release that removes a covered item needs a `breaking` fragment that names it, and only a name in backticks counts. Add `prs:` once the pull request has a number. Before pushing, run `npm run changes:preview`: it lists the fragments added since the last stable tag, the covered-surface changes against it (`tools/covered-surfaces.js`), the minimum bump and why, and the rendered block. It also prints the release gate's verdict for the whole next release, not for your pull request alone: a refusal about an item or a fragment your pull request touches is yours to fix; any other refusal is for the maintainer who cuts the release, and your pull request only needs its own fragments to pass `npm run validate:changes` and `npm run changes:pr`. `npm run validate:changes` checks the format, which [`changes/README.md`](changes/README.md) describes in full.

### The pull request check

The required `em-dash` check runs `npm run changes:pr` on every pull request. It compares your branch, from its merge base with the base branch to `HEAD`, and fails when:

- the branch changes the code the npm package ships (anything under `skills/` outside the dev artifacts `.npmignore` keeps out, such as each skill's `scripts/tests/`; anything under `tools/cli/`; and `tools/ucg-npx-wrapper.js`) or `.npmignore`, which decides what ships, and has no change fragment of its own;
- a covered item the branch removes, or a tool minimum it raises or gives a tool for the first time, is not named in backticks by a `breaking` fragment on the branch (a tool by its `name`);
- a covered item the branch adds, or a tool minimum it lowers or removes, has no `added` or `breaking` fragment on the branch;
- a fragment the branch adds or edits is not valid, or the branch edits, renames or copies a fragment an earlier release shipped.

A fragment on the branch is one it adds. A fragment it edits that no release has shipped yet, such as another pull request's pending one, counts only for the covered items it names in backticks: a follow-up that removes a flag can name it in the pending `breaking` fragment it extends, and then needs no other fragment, but an edit that names none of the branch's covered items never stands in for a fragment of its own.

The check reads only the code the package ships. The package also ships `package.json`, `README.md` and part of `docs/`, and the check asks nothing of a branch that changes only those or other files (the `tools/*.js` scripts, `test/`, `.github/`). A change a user notices there still takes a fragment, as **When** says above: a user docs change worth announcing takes a `docs` fragment, and a raised `engines.node` floor or a new runtime requirement in `package.json` is `breaking`.

When no user or pipeline can notice any change the branch makes to the code the package ships, such as a refactor with the same output or a reworded comment, give the reason in one of the branch's commit messages instead of a fragment, on a line of its own (with the other trailers is best). A merge commit on the branch counts too. To add the line to a branch you already pushed, push an empty commit that carries it (`git commit --allow-empty`):

```text
Changelog: none (refactor, the output is unchanged)
```

The reason inside the parentheses is required: `Changelog: none` alone covers nothing, and neither does `Changelog: none (<reason>)` pasted as it is. One such line covers the whole branch, so use it only when nothing the branch changes in the code the package ships is noticeable: a branch that mixes a refactor and a fix still needs a fragment for the fix. The line only stands in for a fragment the first rule asks for. It never covers a covered item the branch removes or adds: those always need their fragment, because the release notes and the version bump come from it.

Run the check before you push. It reads commits, not the working tree, so commit first, and fetch the base branch so the merge base is current:

```bash
git fetch origin
npm run changes:pr
```

It compares with `origin/main` by default (on a pull request, with `origin/<base branch>`); pass `-- --base <ref>` for another base. In a fork, `origin` is your fork, so compare with the upstream repository instead:

```bash
git fetch upstream
npm run changes:pr -- --base upstream/main
```

The released-fragment rule takes the last stable tag reachable from the base, as CI does, so a branch forked before the latest release is still checked against it. On a failure the check prints what is missing and a fragment to fill in, with the type and scope worked out from what the branch changes, and exits `1`; in CI the same text is in the job summary. The fragment it prints fails `npm run validate:changes` until you rewrite each sentence that starts with "Rewrite this paragraph". It exits `2` when it cannot run, for example when the base branch has not been fetched, or when a shallow clone does not hold the merge base (`git fetch --unshallow origin`). The release workflow's own pull request, from a `release/bot/*` branch of this repository, is exempt: its one commit bumps the version and renders the notes from fragments already merged. A `release/bot/*` branch from a fork, or from a repository the check cannot confirm, is checked like any other.

## The Quality Gate

`npm run quality` must pass before you push. If it fails:

- **Fix the root cause.** Do not `git commit --no-verify`. Do not disable a rule to make the linter shut up. If a hook is wrong, fix the hook in a separate PR.
- **If a Python test fails on your machine but not in CI,** check your `uv` version and re-run the suite from a clean shell.

CI re-runs everything on the PR. A green local run and a red CI run usually means (a) uncommitted files, (b) a Node, uv or Python version that drifts from `.nvmrc` or the Python minimum, or (c) the pull request check failed: `npm run changes:pr` is not part of `npm run quality`, so run it after committing. Check all three before filing a CI bug.

## Workflow Health Check

Every UCG run that reaches Finalize ends with a health-check reflection step that can file a GitHub issue on your behalf when it finds a defect in its own stage references.

- **Deduplication is automatic.** Reports carry a deterministic fingerprint computed as the first 7 hex chars of `sha1("severity|ultracode-goal/{stage}|skills/ultracode-goal/references/{stage}.md|section-slug")`, applied as an `fp-XXXXXXX` label. The [`.github/workflows/health-check-dedup.yaml`](.github/workflows/health-check-dedup.yaml) Action extracts that label, finds the lowest-numbered open canonical issue with the same fingerprint, comments "duplicate of #N", upvotes the canonical issue to preserve the signal count, and closes the duplicate. **Re-reporting is safe.**
- **Triage** by the `health-check` plus `fp-*` labels. The `fp-*` label is the dedup key; the `health-check` label scopes the queue.
- **Maintainers must pre-create the labels** the loop and the Action depend on: `health-check`, `workflow-improvement`, `bug`, `friction`, `gap`, `duplicate`. The dedup Action assumes they exist.
- If you skipped the terminal step in-session, ask the conductor to run the health check for that run, or file via the [Workflow Health Check](.github/ISSUE_TEMPLATE/workflow-health-check.md) template directly.
- **When you fix a finding, record it as `resolved`.** The reporter's machine keeps a local seen-cache (default `~/.ultracode-goal/health-check-seen.json`) that suppresses a repeat report of a fingerprint it has already handled. Fixing the defect does not clear that entry, so without this step the fingerprint suppresses forever and a later *regression* of the same defect is silently swallowed. After the fix merges, and at the same moment you retire the local queue file (delete it, or archive it into a `resolved/` subfolder of the queue dir; the archive form is what keeps `seen --queue-path`'s prior-filing lookup able to show a later collision or regression the original text):

  ```bash
  uv run skills/ultracode-goal/scripts/health_check_fp.py record \
    --fp fp-XXXXXXX --cache ~/.ultracode-goal/health-check-seen.json \
    --issue-url "<the resolving PR or issue URL, or empty>" \
    --action resolved --date YYYY-MM-DD
  ```

  A `resolved` record does not suppress: the next sighting reports as a regression and links the original. A `defect_slug` recorded earlier for the fp survives this call automatically (re-pass `--defect-slug` only to change it), so the regression can still name which defect regressed under a colliding fingerprint. Prefer this over deleting the entry, which restores the signal but throws away the fact that the defect was ever seen.
- **Two limits worth knowing.** The cache is machine-local, so a `resolved` you record is not visible to other users; where the finding has a real issue URL, the shared truth is the issue's own state, and the health check consults it in preference to the local record. It accepts only a *completed* close (or a merged PR) as a fix: closing as **not planned** deliberately does not count, since that is how the dedup Action closes duplicates and how a wontfix is closed. And nothing detects a skipped `resolved`, so this remains a convention rather than an enforced step.

## Releasing

Maintainers only. If you're not cutting a release, skip this section.

- **Canonical path:** `.github/workflows/release.yaml`, triggered via GitHub Actions, Run workflow, then a `version_bump` (`alpha`, `beta`, `rc`, `patch`, `minor` or `major`, or `resume` on `main` to finish a cut whose bot PR merged but whose tag, npm publish or GitHub Release is missing). That is the only supported route: OIDC-backed publish, required-reviewer gate on the `release` environment, auto-provenance on the npm tarball.
- **Before dispatch:** run `npm run changes:preview -- --bump <type>` on an up-to-date `main`. The workflow's release gate refuses a `version_bump` below the minimum the preview prints, before anything is committed.

The canonical, step-by-step procedure (branch-protection rules, the `release` environment, npm Trusted Publisher registration, and the rollback playbook) lives in `docs/_internal/RELEASING.md`.

## What We Don't Accept

- **Changes that bypass `npm run quality`**: skipping hooks, excluding files from linters, loosening a validator to make a PR green. Fix the underlying issue instead.
- **Tests that mock the gate contract.** UCG's whole value is that completion is decided by `gate_eval.py` reading a real TEA artifact. A test that mocks the gate file's status to force an `advance` hides exactly the contract the suite exists to protect. Test against real artifact shapes.
- **Emoji in source files and docs.** Project standard. (Badges and the README's star CTA are the exceptions.)
- **Drive-by reformats.** Please don't reflow whole files or rename things you didn't touch.

## Code of Conduct and License

By participating, you agree to the [Code of Conduct](.github/CODE_OF_CONDUCT.md). Be decent; assume good faith; disagree with the argument, not the person.

Contributions are licensed under the project's [MIT License](LICENSE).

## Acknowledgement

UCG is maintained in spare hours. Good issues, small focused PRs, and willingness to iterate on review are the most useful things you can send. If UCG saved you an afternoon of babysitting an epic, a ⭐ keeps the lights on.
