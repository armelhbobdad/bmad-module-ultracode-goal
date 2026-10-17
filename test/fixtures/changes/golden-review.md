## Review before approving

v3.0.0 is a major step from v2.2.0; the change fragments and covered surfaces need at least major.

Approve only when:

- [ ] each breaking change says what stopped working and gives a migration a user can follow;
- [ ] each surface change below is described by a fragment of the right type, or needs no note;
- [ ] the notes below read well as the GitHub Release page (it adds Installation and the compare link).

### Why the minimum is major

- major: breaking fragment changes/customize-retire-story-token-budget.yaml (ultracode-goal)
- major: breaking fragment changes/resolve-refuses-dirty-tree.yaml (ucg-resolve)
- major: hard surface change: customize.toml: customize.toml key `story_token_budget` removed
- minor: changed fragment changes/all-skills-run-folder.yaml (all skills)
- minor: added fragment changes/gate-baseline-flag.yaml (ultracode-goal)
- minor: added fragment changes/status-resolve-exit-codes.yaml (ucg-status, ucg-resolve)
- minor: added fragment changes/status-sizing-note.yaml (ucg-status)
- minor: additive surface change: gate_eval.py: gate_eval.py flag `--baseline` added
- patch: docs fragment changes/docs-claim-by-claim.yaml
- patch: fixed fragment changes/headless-envelope-only.yaml (ultracode-goal)
- patch: fixed fragment changes/packaging-maintainer-files.yaml (packaging)

### Surface changes since v2.2.0

Hard (a breaking fragment names each one):

- customize.toml: customize.toml key `story_token_budget` removed

Additive:

- gate_eval.py: gate_eval.py flag `--baseline` added

Review (never fails; decide whether each one needs a note):

- gate_eval.py: gate_eval.py result key `sweep_scope` added

### [3.0.0](https://github.com/armelhbobdad/bmad-module-ultracode-goal/compare/v2.2.0...v3.0.0) (2026-10-01)

UltraCode Goal 3.0.0 holds every story to the full gate, reads TEA's gate file where TEA writes it, and records every turn the Stop hook counts. Three behaviours a pipeline can depend on changed: read Breaking changes before you upgrade one.

#### Breaking changes

- **ucg-resolve:** `/ucg-resolve` now stops when the working tree has uncommitted changes outside the run folder. Before, it reset the story's turn counter and left the changes in place, so the resumed story started on code it never wrote. The resolve ends `blocked` with the reason `dirty-tree`, and nothing is reset. ([#899](https://github.com/armelhbobdad/bmad-module-ultracode-goal/pull/899); issue [#897](https://github.com/armelhbobdad/bmad-module-ultracode-goal/issues/897))

  **Migration:** Commit or stash the changes (`git status` lists them), then run `/ucg-resolve` again. A clean tree is not affected.

- **ultracode-goal:** The deprecated `story_token_budget` key is gone from `customize.toml`. No layer read it: the per-story bound has always been `max_turns_per_story`. An override that still sets it is now reported as an unknown key, and the run stops at preflight with `status: "blocked"`. ([#909](https://github.com/armelhbobdad/bmad-module-ultracode-goal/pull/909); issue [#902](https://github.com/armelhbobdad/bmad-module-ultracode-goal/issues/902))

  **Migration:** Delete `story_token_budget` from `_bmad/custom/ultracode-goal.toml` and `.user.toml`, and set `max_turns_per_story` if you relied on a per-story bound. Every other key resolves as before.

#### Added

- **ucg-status:** `/ucg-status` now shows a story that advanced over its turn ceiling as a sizing note, matching the line the run report already printed. It still reads the run without writing to it. ([#923](https://github.com/armelhbobdad/bmad-module-ultracode-goal/pull/923))
- **ucg-status, ucg-resolve:** New exit codes for pipelines: `ucg_status.py` exits `3` and `ucg_resolve.py` exits `5` (state-conflict) when the run folder belongs to another Epic (`foreign-run`) or predates the run-id layout (`legacy-layout`). Nothing is written into the refused folder. ([#909](https://github.com/armelhbobdad/bmad-module-ultracode-goal/pull/909); issues [#900](https://github.com/armelhbobdad/bmad-module-ultracode-goal/issues/900), [#901](https://github.com/armelhbobdad/bmad-module-ultracode-goal/issues/901))
- **ultracode-goal:** New `--baseline <ref>` flag for `gate_eval.py`: compare the story's trace against a tag, branch or full commit instead of the Epic branch's base, for example the release an audit checked out. The verdict JSON keeps its key set, and the run report names the ref the gate compared against. ([#917](https://github.com/armelhbobdad/bmad-module-ultracode-goal/pull/917); issue [#911](https://github.com/armelhbobdad/bmad-module-ultracode-goal/issues/911))

#### Changed

- **all skills:** UCG now writes every run artifact under `_bmad-output/ultracode-goal/runs/<run-id>/`, for both `implementation_artifacts` and `deferred_work_path`. A run folder from an older release is still read: `/ucg-status` and `/ucg-resolve` find it, and a resume moves it once and says so in the decision log. `drive_epic.py` now stages its spawn logs in `_bmad-output/.ucg-stage/<story>/`. ([#899](https://github.com/armelhbobdad/bmad-module-ultracode-goal/pull/899), [#909](https://github.com/armelhbobdad/bmad-module-ultracode-goal/pull/909); issues [#895](https://github.com/armelhbobdad/bmad-module-ultracode-goal/issues/895), [#897](https://github.com/armelhbobdad/bmad-module-ultracode-goal/issues/897), [#900](https://github.com/armelhbobdad/bmad-module-ultracode-goal/issues/900), [#901](https://github.com/armelhbobdad/bmad-module-ultracode-goal/issues/901))

#### Fixed

- **packaging:** The npm package no longer ships maintainer-only files (the docs build script and two docs validators), about 60 KB less. ([#889](https://github.com/armelhbobdad/bmad-module-ultracode-goal/pull/889); issue [#887](https://github.com/armelhbobdad/bmad-module-ultracode-goal/issues/887))
- **ultracode-goal:** Under `-H`, the envelope is now the only line a headless run prints on stdout, blocks included, as the docs promised. A refused settings write no longer ends the run before Execute: it records `settings-write-refused` in `.decision-log.md` and stops at the next story boundary. ([#899](https://github.com/armelhbobdad/bmad-module-ultracode-goal/pull/899); issue [#894](https://github.com/armelhbobdad/bmad-module-ultracode-goal/issues/894))

#### Documentation

- The published docs were checked claim by claim against the code. Corrections include: Python 3.11 is the minimum, not 3.10; `gh` is needed only to submit health-check findings, not to run an Epic; `/ucg-status` reads a run without writing to it; and `--light` still runs TEA test-design and trace. ([#922](https://github.com/armelhbobdad/bmad-module-ultracode-goal/pull/922))
