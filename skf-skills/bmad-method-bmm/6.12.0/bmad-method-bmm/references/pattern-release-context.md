# Release and issue context (T2)

Temporal context fetched on 2026-09-28 from the upstream repository (releases, CHANGELOG, merged PRs, issues) and indexed as the QMD collection `bmad-method-bmm-temporal`. T2-past entries explain how v6.12.0 got here; T2-future entries are open issues at fetch time and may change after v6.12.0.

## Contents

- [v6.12.0 breaking changes (T2-past)](#v6120-breaking-changes-t2-past)
- [v6.11.0 changes that shape v6.12.0 (T2-past)](#v6110-changes-that-shape-v6120-t2-past)
- [Open upstream issues at fetch time (T2-future)](#open-upstream-issues-at-fetch-time-t2-future)

## v6.12.0 breaking changes (T2-past)

- `persistent_facts` ships empty; re-add `project-context.md` to an override if the auto-load mattered. [QMD:bmad-method-bmm-temporal:releases.md]
- `{diff_output}` is now `{diff_file}`; custom review overrides must be updated. [QMD:bmad-method-bmm-temporal:releases.md]
- Deprecated shims are opt-in on fresh installs; pass `--shims` to keep them. [QMD:bmad-method-bmm-temporal:releases.md]
- `bmad-checkpoint-preview` is now `bmad-walkthrough` (`CK` → `WT`); the old ID still forwards. [QMD:bmad-method-bmm-temporal:releases.md]
- Build no longer auto-triggers on interactive edits, git bookkeeping or formatting chores; Build decides ceremony after investigating (simple changes get a two-section spec). [QMD:bmad-method-bmm-temporal:releases.md]

## v6.11.0 changes that shape v6.12.0 (T2-past)

- **Quick Dev renamed to Build** (#2651): `bmad-quick-dev` → `bmad-build`, `bmad-dev-auto` → `bmad-build-auto`; rename `_bmad/custom/bmad-quick-dev{,.user}.toml` → `bmad-build{,.user}.toml`. The shim's rename prompt means unattended runs on the old name with a legacy customization file refuse to start. [QMD:bmad-method-bmm-temporal:releases.md]
- **Build is the official Phase 4 loop** (#2637, #2641): `bmad-create-story` and `bmad-dev-story` deprecated, moved to `v6-shims/`, dropped from `bmad-help` and the dev agent menu (`DS`, `CS`); Phase 4 is `bmad-sprint-planning → bmad-build → bmad-code-review`. [QMD:bmad-method-bmm-temporal:releases.md]
- **Readiness folded into sprint planning** (#2659): `bmad-check-implementation-readiness` removed (listed in `removals.txt`); `bmad-sprint-status` became a shim; `SS` dispatches `action=status`. [QMD:bmad-method-bmm-temporal:releases.md]
- **Build Auto contract** (#2640, #2668): `deferred-work.md` and `final_revision` are gone for Build Auto; deferred findings live in the spec frontmatter `deferred:` list; `## Finalize` sets `status: done` before the commit; a story's range is `baseline_revision..<next story's baseline_revision>` (or `..HEAD`). [QMD:bmad-method-bmm-temporal:releases.md]
- **Review layers configurable** (#2550): `[[workflow.review_layers]]` in `bmad-code-review`, `bmad-build`, `bmad-build-auto`; triage tags by layer `id`; Build Auto's intent-gap halts unify to `intent gap` (#2564). [QMD:bmad-method-bmm-temporal:releases.md]
- **`uv` required** (#2281, #2601): config is layered TOML; `bmad-build` and `bmad-build-auto` halt without `uv`; the per-module `_bmad/bmm/config.yaml` still ships and older skills still read it. [QMD:bmad-method-bmm-temporal:releases.md]
- **Retrospective rebuilt** (#2612, #2665): evidence-based epic review with `-H <epic>` as the stable orchestrator interface; it can retro a spec folder left by unattended Build Auto runs, writing `{spec-folder}/RETROSPECTIVE.md` without touching sprint status. [QMD:bmad-method-bmm-temporal:releases.md]
- **sprint-planning script core** (#2659): `scripts/sprint_plan.py` (generate/status/validate, JSON-only); `sprint-status.yaml` format unchanged, so Build's sprint sync is unaffected. [QMD:bmad-method-bmm-temporal:releases.md]
- **`stories.yaml` contract** (#2549, #2666): optional Story Breakdown in `bmad-spec`; Build and Build Auto can be dispatched by spec folder plus story id. [QMD:bmad-method-bmm-temporal:releases.md]
- **`implementation_handoff` and `open_spec` keys** (#2561, #2629, #2635, #2652). [QMD:bmad-method-bmm-temporal:releases.md]

## Open upstream issues at fetch time (T2-future)

- **#2760** — `bmad-build` and `bmad-code-review` run three identical review layers; `bmad-build` alone never reaches `done` (it stops at `review`). [QMD:bmad-method-bmm-temporal:issues.md]
- **#2852** — Approve and stop sets the spec `ready-for-dev` but does not sync `sprint-status.yaml`. [QMD:bmad-method-bmm-temporal:issues.md]
- **#2849** — `bmad-build` resume and parallel runs lack attributable per-run state. [QMD:bmad-method-bmm-temporal:issues.md]
- **#2885** — `bmad-create-epics-and-stories` step 01 cannot find a PRD or architecture written into run folders by `bmad-prd`/`bmad-architecture`. [QMD:bmad-method-bmm-temporal:issues.md]
- **#2827** — `sprint_plan.py generate` can write an empty `development_status` instead of failing when keys do not follow its positional identifier scheme (reported on 6.11.0). [QMD:bmad-method-bmm-temporal:issues.md]
- **#2725** — BOM-prefixed epic files silently dropped; non-scalar YAML values crash validate; CRLF files rewritten wholesale (reported on 6.11.0). [QMD:bmad-method-bmm-temporal:issues.md]
- **#2720** — research shims fail at activation step 1 and the `bmad-sprint-status` forwarding had no receiving clause (reported on 6.11.0). [QMD:bmad-method-bmm-temporal:issues.md]
- **#2718** — `render_skill.py` short config tokens halt as ambiguous in multi-module installs, so `bmad-build`/`bmad-build-auto` cannot render (reported on 6.11.0). [QMD:bmad-method-bmm-temporal:issues.md]
