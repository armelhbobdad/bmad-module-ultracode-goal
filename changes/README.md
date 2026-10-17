# Change fragments

Each change a user or a pipeline can notice gets one short YAML file in this folder, `changes/<topic>.yaml`, added by the pull request that makes the change. At release, `tools/changes.js` renders the fragments added since the last stable release into the new CHANGELOG.md block and the GitHub Release notes, and their types set the smallest version bump the release may take.

Fragments stay here after a release. A release takes only the fragments that did not exist at the last stable tag, so nothing is deleted when a version ships. A release never renders a released fragment again (only the markdownlint check still lints it), so every new change, and each release's lead, needs a file with a new name (for a lead, for example `lead-2-4-0.yaml`). A released fragment that was edited, renamed or copied is refused, and the check names the file.

## When to add one

Add a fragment when a user or a pipeline can notice the change: a stage behaves differently, a flag, verdict, status, blocker, exit code or `customize.toml` key appears or goes, the install changes, or the user docs gain something worth announcing. Refactors, tests, CI and maintainer-only docs need none. Write one fragment per change: a pull request with two user-visible changes adds two.

Every pull request is checked for its fragments (`npm run changes:pr`, run by the required `em-dash` check). A pull request that changes the code the npm package ships (`skills/` outside the dev artifacts `.npmignore` keeps out, such as each skill's `scripts/tests/`; `tools/cli/`; `tools/ucg-npx-wrapper.js`) or `.npmignore` needs a fragment of its own, or, when no user or pipeline can notice any of its changes, a `Changelog: none (<reason>)` line in one of its commit messages, with the reason written out. One such line covers the whole pull request, so a pull request that mixes a refactor and a fix still needs a fragment for the fix. The line never covers a covered item the pull request removes or adds (see the end of [Which type](#which-type)): a removal needs a `breaking` fragment that names it, an addition an `added` or `breaking` fragment. Editing another pull request's pending fragment counts only for the covered items the edit names in backticks. The check does not read `package.json`, `README.md` or `docs/`, which the package also ships: a change a user notices there still takes a fragment. [CONTRIBUTING.md](../CONTRIBUTING.md#change-fragments) has the details.

## Format

```yaml
type: breaking
scope: ultracode-goal
summary: |
  Under `--profile production`, `gate_eval.py` now reads an omitted `--nfr` or `--test-review` as a failing signal, so a per-story gate given neither can no longer `advance`.
migration: |
  Pass both paths to every production per-story gate, or `--epic-level` for the epic roll-up.
```

| Key | Required | What it holds |
| --- | --- | --- |
| `type` | always | `breaking`, `added`, `changed`, `fixed`, `docs` or `lead` (see below) |
| `scope` | for every type except `docs` and `lead` | the skill or area that changed, in lower case: `ultracode-goal`, `ucg-status, ucg-resolve`, `all skills`, `installer`, `packaging` |
| `summary` | always | one paragraph a user understands: what changed, with flags, statuses, verdicts and file names in backticks |
| `migration` | for `breaking` only | the exact action a user takes, in one paragraph |
| `issues` | no | issue numbers, as a list of numbers |
| `prs` | no | pull request numbers, as a list of numbers |

Name the file after the change, in lower case with hyphens, such as `gate-production-signals-required.yaml`. No other key is accepted. A summary or migration holds no em dash and cites no section of a stage reference (§): describe the behaviour instead. A `lead` holds only a `summary`, the paragraph that opens the release notes, and a release takes at most one. The required `markdownlint` check (`npm run lint:md`) also lints the fragments as the release block, rendered into the CHANGELOG.md a release would write, so Markdown that would break the release commit, such as a bare URL (write `<https://example.com>`), fails your pull request instead.

## Which type

Pick the type by what a user sees, not by the commit type. When unsure, pick the higher one.

- **breaking**: the change removes or renames a covered item (one of the public surfaces [STABILITY.md](../docs/_internal/STABILITY.md) lists: a CLI subcommand or option, a `[workflow]` key of `customize.toml`, a key of the headless emit shape, the skill name or an invocation phrase, a `gate_eval.py` flag, choice, `gate_status`, verdict or printed key), changes the verdict a documented invocation returns, raises a requirement, or makes an input that used to succeed now halt or exit non-zero.
- **added**: a new flag, option, `customize.toml` key, preflight blocker or capability.
- **changed**: the output or a default is different, and nothing was removed.
- **fixed**: the behaviour now matches the docs.
- **docs**: a change to the user docs worth announcing.
- **lead**: the opening paragraph of the release notes, usually written for the release itself.

The minimum version bump is major for a `breaking` fragment, minor for `added` or `changed`, and patch for `fixed` or `docs`. The covered-surface check (`tools/covered-surfaces.js`) can raise it: removing one of the covered items above, or adding or removing a key of the headless emit shape, needs a major bump and a `breaking` fragment that names the item, in backticks (the plain word does not count); adding a covered item needs at least a minor bump. A key added to the `gate_eval.py` result is listed for review instead, since one that every invocation prints is a shape change and one that only a new flag prints is not. A tool minimum in `tools/tool-requirements.yaml` works the other way round: raising one, or giving a tool its first one, needs a major bump and a `breaking` fragment that names the tool by its `name` in backticks, such as `Claude Code`, while lowering or removing one needs at least a minor bump.

## Commands

- `npm run validate:changes` checks every file in this folder, refuses a released fragment that changed, and checks that `## [Unreleased]` in `CHANGELOG.md` is empty.
- `npm run changes:pr` checks the fragments your branch needs, from its merge base with `origin/main` to `HEAD`: commit first, then run it before you push. On a failure it prints what is missing and a fragment to fill in, which `npm run validate:changes` refuses until you rewrite each sentence that starts with "Rewrite this paragraph".
- `npm run changes:preview` shows the fragments added since the last stable tag, any file here to fix, the covered-surface changes, the minimum bump and why, the next version, the release gate's verdict for the minimum bump and the rendered block. The verdict covers the whole next release, not only your pull request. Pass a bump to check another one: `npm run changes:preview -- --bump minor`.
