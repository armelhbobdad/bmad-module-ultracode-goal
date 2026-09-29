---
name: bmad-method-bmm
description: >
  BMAD Method v6.12.0 planning and delivery skills that UltraCode Goal orchestrates (bmad-build,
  bmad-build-auto, sprint planning, code review, correct-course, retrospective, epics-and-stories,
  PRD, architecture and spec), plus every v6 deprecation shim mapped to its replacement. Use when
  checking how a BMM skill is invoked, what it reads and writes, which sprint-status transitions
  it performs, or which replacement a deprecated shim such as bmad-create-story or bmad-dev-story
  now forwards to. Not for the installer (see bmad-method-installer) or TEA test-architecture skills.
---

# BMAD Method v6.12.0 — BMM planning and delivery skills

## Overview

Reference for the `bmm` module ("BMad Method") skills at tag `v6.12.0` of <https://github.com/bmad-code-org/BMAD-METHOD> (commit `05bfbd46`), compiled at Forge tier **Deep**. [SRC:src/bmm-skills/module.yaml:L1]

- **Surface:** 37 skill IDs — 10 under `src/bmm-skills/plan/`, 7 under `src/bmm-skills/ship/`, 14 BMM shims under `src/bmm-skills/v6-shims/`, 6 core shims under `src/core-skills/v6-shims/` — plus `module.yaml` and `module-help.csv`.
- **Confidence:** 25 Python helper functions AST-verified (T1); every skill-behaviour claim cites a verified source line (T1-low); release notes and open issues at fetch time add T2 context.
- **Shape:** reference-app — the value is the wiring contract (invocation, files read and written, status literals), not a library API. Each skill is a markdown workflow (`SKILL.md`, step files, `customize.toml`).

## Quick Start

The Phase 4 chain in `module-help.csv` is `bmad-sprint-planning` → `bmad-build` → `bmad-code-review`, with `bmad-retrospective` optional at epic end. [SRC:src/bmm-skills/module-help.csv:L4] [SRC:src/bmm-skills/module-help.csv:L16] [SRC:src/bmm-skills/module-help.csv:L19]

1. **Plan the sprint** — `bmad-sprint-planning` runs a readiness gate (PASS/CONCERNS/FAIL) and, on PASS, generates `{implementation_artifacts}/sprint-status.yaml`. [SRC:src/bmm-skills/plan/bmad-sprint-planning/SKILL.md:L18] [SRC:src/bmm-skills/plan/bmad-sprint-planning/references/generate-tracking.md:L11]
2. **Build a story** — `bmad-build` resolves `story_key` against `sprint-status.yaml` by exact numeric epic-story equality [SRC:src/bmm-skills/ship/bmad-build/step-01-clarify-and-route.md:L44], syncs the story to `in-progress` when implementation starts [SRC:src/bmm-skills/ship/bmad-build/step-03-implement.md:L27] and to `review` (not `done`) on completion. [SRC:src/bmm-skills/ship/bmad-build/step-05-present.md:L17]
3. **Review it** — `bmad-code-review` sets the story `done` only when every decision-needed and patch finding is resolved and no high/medium remains; otherwise `in-progress`. [SRC:src/bmm-skills/ship/bmad-code-review/steps/step-04-present.md:L91] [SRC:src/bmm-skills/ship/bmad-code-review/steps/step-04-present.md:L92] [SRC:src/bmm-skills/ship/bmad-code-review/steps/step-04-present.md:L104]
4. **Close the epic** — `bmad-retrospective -H <epic>` is the stable orchestrator interface; pass the same number to `detect-epic --epic <N>`. [SRC:src/bmm-skills/ship/bmad-retrospective/SKILL.md:L22] [SRC:src/bmm-skills/ship/bmad-retrospective/SKILL.md:L22]

Unattended loops use `bmad-build-auto`: one iteration per invocation, one `stories.yaml` entry, never advancing to another story id. [SRC:src/bmm-skills/ship/bmad-build-auto/SKILL.md:L3] [SRC:src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md:L39]

Both build skills activate by rendering, then follow the printed `workflow.md` path; if `uv` is missing they HALT. [SRC:src/bmm-skills/ship/bmad-build/SKILL.md:L9] [SRC:src/bmm-skills/ship/bmad-build/SKILL.md:L12] [SRC:src/bmm-skills/ship/bmad-build/SKILL.md:L13] [SRC:src/bmm-skills/ship/bmad-build-auto/SKILL.md:L9] [SRC:src/bmm-skills/ship/bmad-build-auto/SKILL.md:L13]

```bash
uv run --no-cache "{project-root}/_bmad/scripts/render_skill.py" --project-root "{project-root}" --skill "{skill-root}"
```

<!-- [MANUAL:additional-notes] -->
<!-- Add custom notes here. This section is preserved during skill updates. -->
<!-- [/MANUAL:additional-notes] -->

## Adoption Steps

1. **Drive stories through sprint-status, not story files.** Story keys are `<epic>-<story>-<slug>` (e.g. `1-2-account-management`), epics `epic-N`, retrospectives `epic-N-retrospective`. [SRC:src/bmm-skills/plan/bmad-sprint-planning/sprint-status-template.yaml:L55] [SRC:src/bmm-skills/plan/bmad-sprint-planning/sprint-status-template.yaml:L58] [SRC:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L55] [SRC:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L57]
2. **Invoke `bmad-build` with a story, spec path, or spec folder plus story id.** A spec folder plus id reads `{spec_folder}/stories.yaml` and writes `{spec_folder}/stories/{story_id}-{slug}.md`; otherwise the spec lands at `{implementation_artifacts}/spec-{slug}.md`. [SRC:src/bmm-skills/ship/bmad-build/step-01-clarify-and-route.md:L21] [SRC:src/bmm-skills/ship/bmad-build/step-01-clarify-and-route.md:L22] [SRC:src/bmm-skills/ship/bmad-build/step-01-clarify-and-route.md:L96]
3. **Resume by spec status.** `draft` → plan, `ready-for-dev`/`in-progress` → implement, `in-review` → review; `done` is context only. [SRC:src/bmm-skills/ship/bmad-build/step-01-clarify-and-route.md:L23] [SRC:src/bmm-skills/ship/bmad-build/step-01-clarify-and-route.md:L23]
4. **Run `bmad-code-review` after `bmad-build` to reach `done`.** Build stops at `review`; review promotes to `done` and syncs `development_status[story_key]`. [SRC:src/bmm-skills/ship/bmad-build/step-05-present.md:L17] [SRC:src/bmm-skills/ship/bmad-code-review/steps/step-04-present.md:L91] [SRC:src/bmm-skills/ship/bmad-code-review/steps/step-04-present.md:L104]
5. **For unattended runs call `bmad-build-auto` by name**, read the spec frontmatter `status` and `## Auto Run Result` after each iteration, and treat `blocked` as a stop. [SRC:src/bmm-skills/ship/bmad-build-auto/workflow.md:L16] [SRC:src/bmm-skills/ship/bmad-build-auto/workflow.md:L28] [SRC:src/bmm-skills/ship/bmad-build-auto/spec-template.md:L5]
6. **Retro an epic headlessly** with `-H <epic>`, then read the verdict from the retro document frontmatter — sprint-status alone cannot distinguish rejected from accepted. [SRC:src/bmm-skills/ship/bmad-retrospective/SKILL.md:L22] [SRC:src/bmm-skills/ship/bmad-retrospective/references/retro-document.md:L15] [SRC:src/bmm-skills/ship/bmad-retrospective/references/retro-document.md:L23]
7. **Stop calling deprecated IDs.** `bmad-create-story` and `bmad-dev-story` still run in full when invoked by name; `bmad-quick-dev` and `bmad-dev-auto` forward to the build skills. [SRC:src/bmm-skills/v6-shims/README.md:L9] [SRC:src/bmm-skills/v6-shims/README.md:L10] [SRC:src/bmm-skills/v6-shims/README.md:L11] [SRC:src/bmm-skills/v6-shims/README.md:L12]

## Pattern Surface

| # | File | Surface | Purpose |
|---|------|---------|---------|
| 1 | `src/bmm-skills/module.yaml` | `planning_artifacts`, `implementation_artifacts`, `project_knowledge` | Artifact roots every skill resolves [SRC:src/bmm-skills/module.yaml:L30] [SRC:src/bmm-skills/module.yaml:L35] [SRC:src/bmm-skills/module.yaml:L40] |
| 2 | `src/bmm-skills/module-help.csv` | `preceded-by` / `followed-by` columns | Catalog order and phase routing for `bmad-help` [SRC:src/bmm-skills/module-help.csv:L1] [SRC:src/bmm-skills/module-help.csv:L4] |
| 3 | `plan/bmad-sprint-planning/SKILL.md` | intents `readiness`, `sprint-planning`, `status`, `validate`, `fix` | Owns `sprint-status.yaml` end to end [SRC:src/bmm-skills/plan/bmad-sprint-planning/SKILL.md:L17] [SRC:src/bmm-skills/plan/bmad-sprint-planning/SKILL.md:L18] [SRC:src/bmm-skills/plan/bmad-sprint-planning/SKILL.md:L19] [SRC:src/bmm-skills/plan/bmad-sprint-planning/SKILL.md:L20] [SRC:src/bmm-skills/plan/bmad-sprint-planning/SKILL.md:L21] |
| 4 | `plan/bmad-sprint-planning/scripts/sprint_plan.py` | `generate` / `status` / `validate` | JSON-only contract for tracking [SRC:src/bmm-skills/plan/bmad-sprint-planning/SKILL.md:L56] [SRC:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L7] |
| 5 | `ship/bmad-build/step-01-clarify-and-route.md` | `story_key`, spec status routing | Story resolution and resume [SRC:src/bmm-skills/ship/bmad-build/step-01-clarify-and-route.md:L3] [SRC:src/bmm-skills/ship/bmad-build/step-01-clarify-and-route.md:L23] [SRC:src/bmm-skills/ship/bmad-build/step-01-clarify-and-route.md:L44] |
| 6 | `ship/bmad-build/sync-sprint-status.md` | `development_status[{story_key}]` | Never-regress sprint sync [SRC:src/bmm-skills/ship/bmad-build/sync-sprint-status.md:L1] [SRC:src/bmm-skills/ship/bmad-build/sync-sprint-status.md:L3] [SRC:src/bmm-skills/ship/bmad-build/sync-sprint-status.md:L4] |
| 7 | `ship/bmad-build/customize.toml` | `[[workflow.review_layers]]`, `implementation_handoff`, `on_complete` | Review and handoff overrides [SRC:src/bmm-skills/ship/bmad-build/customize.toml:L71] [SRC:src/bmm-skills/ship/bmad-build/customize.toml:L80] [SRC:src/bmm-skills/ship/bmad-build/customize.toml:L32] |
| 8 | `ship/bmad-build-auto/workflow.md` | HALT protocol, `## Auto Run Result` | Unattended terminal contract [SRC:src/bmm-skills/ship/bmad-build-auto/workflow.md:L16] [SRC:src/bmm-skills/ship/bmad-build-auto/workflow.md:L32] [SRC:src/bmm-skills/ship/bmad-build-auto/workflow.md:L55] |
| 9 | `ship/bmad-build-auto/step-04-review.md` | finalize, `followup_review_recommended` | Commit plus `status: done` [SRC:src/bmm-skills/ship/bmad-build-auto/step-04-review.md:L107] [SRC:src/bmm-skills/ship/bmad-build-auto/step-04-review.md:L113] [SRC:src/bmm-skills/ship/bmad-build-auto/step-04-review.md:L116] |
| 10 | `ship/bmad-code-review/steps/step-01-gather-context.md` | review target tiers, `review_mode` | What gets reviewed [SRC:src/bmm-skills/ship/bmad-code-review/steps/step-01-gather-context.md:L5] [SRC:src/bmm-skills/ship/bmad-code-review/steps/step-01-gather-context.md:L22] [SRC:src/bmm-skills/ship/bmad-code-review/steps/step-01-gather-context.md:L38] |
| 11 | `ship/bmad-code-review/steps/step-04-present.md` | story status + sprint sync | `done` vs `in-progress` decision [SRC:src/bmm-skills/ship/bmad-code-review/steps/step-04-present.md:L91] [SRC:src/bmm-skills/ship/bmad-code-review/steps/step-04-present.md:L92] [SRC:src/bmm-skills/ship/bmad-code-review/steps/step-04-present.md:L104] |
| 12 | `ship/bmad-retrospective/SKILL.md` | `-H <epic>`, `detect-epic --epic` | Headless epic review [SRC:src/bmm-skills/ship/bmad-retrospective/SKILL.md:L3] [SRC:src/bmm-skills/ship/bmad-retrospective/SKILL.md:L22] [SRC:src/bmm-skills/ship/bmad-retrospective/SKILL.md:L52] |
| 13 | `ship/bmad-retrospective/references/retro-document.md` | frontmatter `verdict` | Accept/reject signal for an epic gate [SRC:src/bmm-skills/ship/bmad-retrospective/references/retro-document.md:L9] [SRC:src/bmm-skills/ship/bmad-retrospective/references/retro-document.md:L15] [SRC:src/bmm-skills/ship/bmad-retrospective/references/retro-document.md:L21] |
| 14 | `ship/bmad-correct-course/SKILL.md` | `sprint-change-proposal-{date}.md` | Mid-sprint change proposal [SRC:src/bmm-skills/ship/bmad-correct-course/SKILL.md:L3] [SRC:src/bmm-skills/ship/bmad-correct-course/SKILL.md:L69] |
| 15 | `plan/bmad-create-epics-and-stories/templates/epics-template.md` | `## Epic N:` / `### Story N.M:` headings | Headings `sprint_plan.py` parses [SRC:src/bmm-skills/plan/bmad-create-epics-and-stories/templates/epics-template.md:L40] [SRC:src/bmm-skills/plan/bmad-create-epics-and-stories/templates/epics-template.md:L46] [SRC:src/bmm-skills/plan/bmad-sprint-planning/references/generate-tracking.md:L16] |
| 16 | `plan/bmad-spec/assets/stories-schema.md` | `stories.yaml` entries | Folder+id dispatch contract for build skills [SRC:src/bmm-skills/plan/bmad-spec/assets/stories-schema.md:L3] [SRC:src/bmm-skills/plan/bmad-spec/assets/stories-schema.md:L20] |
| 17 | `plan/bmad-prd/references/headless.md` | intent `create`/`update`/`validate`, JSON status | Headless PRD contract [SRC:src/bmm-skills/plan/bmad-prd/references/headless.md:L20] [SRC:src/bmm-skills/plan/bmad-prd/assets/headless-schemas.md:L7] |
| 18 | `plan/bmad-architecture/references/headless.md` | `ARCHITECTURE-SPINE.md` JSON result | Headless architecture contract [SRC:src/bmm-skills/plan/bmad-architecture/references/headless.md:L5] [SRC:src/bmm-skills/plan/bmad-architecture/references/headless.md:L11] [SRC:src/bmm-skills/plan/bmad-architecture/references/headless.md:L16] |
| 19 | `v6-shims/README.md` (bmm + core) | shim → replacement table | Deprecated ID forwarding [SRC:src/bmm-skills/v6-shims/README.md:L9] [SRC:src/core-skills/v6-shims/README.md:L9] |
| 20 | `v6-shims/bmad-create-story/SKILL.md`, `v6-shims/bmad-dev-story/SKILL.md` | full legacy workflows | Retained v6 story loop [SRC:src/bmm-skills/v6-shims/README.md:L11] [SRC:src/bmm-skills/v6-shims/README.md:L12] [SRC:src/bmm-skills/v6-shims/bmad-create-story/SKILL.md:L147] [SRC:src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md:L110] |

## Migration & Deprecation Warnings

- `bmad-quick-dev` → `bmad-build`, `bmad-dev-auto` → `bmad-build-auto` (v6.11.0, #2651); a shim that finds a legacy customization file HALTs without forwarding unless the rename is approved, so unattended runs on the old ID refuse to start. [QMD:bmad-method-bmm-temporal:releases.md] [SRC:src/bmm-skills/v6-shims/bmad-quick-dev/SKILL.md:L19] [SRC:src/bmm-skills/v6-shims/bmad-dev-auto/SKILL.md:L19]
- `bmad-create-story` and `bmad-dev-story` are deprecated (v6.11.0, #2637, #2641) but retained in full in `v6-shims/`; removal rides the v7 cut. [QMD:bmad-method-bmm-temporal:releases.md] [SRC:src/bmm-skills/v6-shims/README.md:L24]
- v6.12.0: deprecated shims are opt-in on fresh installs (`--shims` keeps them), `persistent_facts` ships empty, `{diff_output}` became `{diff_file}`, and `bmad-checkpoint-preview` became `bmad-walkthrough`. [QMD:bmad-method-bmm-temporal:releases.md]
- `bmad-sprint-status` forwards to `bmad-sprint-planning` status view; `bmad-check-implementation-readiness` was removed and folded into the readiness gate (#2659). [QMD:bmad-method-bmm-temporal:releases.md] [SRC:src/bmm-skills/v6-shims/bmad-sprint-status/SKILL.md:L24]
- Open upstream issues at fetch time: #2760 (`bmad-build` alone never reaches `done`), #2852 (Approve and stop leaves sprint-status stale), #2885 (epics step 01 misses run-folder PRD/architecture). [QMD:bmad-method-bmm-temporal:issues.md]

See Full API Reference for migration details (`references/pattern-v6-shims.md`, `references/pattern-release-context.md`).

## CORRECTION

**Source:** _bmad-output/.skf-stage/bmad-method-bmm/provenance-map.json
**Pattern:** deprecated
**Affected:** bmad-generate-project-context
**Detail:** "description": "bmad-generate-project-context is deprecated and forwards to bmad-project-context.",

## CORRECTION

**Source:** _bmad-output/.skf-stage/bmad-method-bmm/provenance-map.json
**Pattern:** deprecated
**Affected:** bmad-generate-project-context
**Detail:** "quote": "Deprecated — forwards to bmad-project-context. Use when the user says \"generate project context\" or \"create project context\""

## CORRECTION

**Source:** _bmad-output/.skf-stage/bmad-method-bmm/provenance-map.json
**Pattern:** deprecated
**Affected:** bmad-generate-project-context
**Detail:** "description": "The deprecated skill's metadata lifecycle is shim.",

## CORRECTION

**Source:** _bmad-output/.skf-stage/bmad-method-bmm/provenance-map.json
**Pattern:** deprecated
**Affected:** bmad-create-story
**Detail:** "description": "The create-story skill's frontmatter description marks it deprecated, names bmad-build as the official implementation method, and restricts use to explicit invocation by name.",

## CORRECTION

**Source:** _bmad-output/.skf-stage/bmad-method-bmm/provenance-map.json
**Pattern:** deprecated
**Affected:** bmad-create-story
**Detail:** "quote": "Deprecated: `bmad-build` is now the official implementation method. Only use this when explicitly invoked by name"

## CORRECTION

**Source:** _bmad-output/.skf-stage/bmad-method-bmm/provenance-map.json
**Pattern:** deprecated
**Affected:** bmad-create-story
**Detail:** "quote": "<output>Deprecated: `bmad-build` is now the official implementation method."

## CORRECTION

**Source:** _bmad-output/.skf-stage/bmad-method-bmm/provenance-map.json
**Pattern:** deprecated
**Affected:** bmad-dev-story
**Detail:** "description": "The dev-story skill's frontmatter description marks it deprecated, names bmad-build as the official implementation method, and restricts use to explicit invocation by name.",

## CORRECTION

**Source:** _bmad-output/.skf-stage/bmad-method-bmm/SKILL.md
**Pattern:** deprecated
**Affected:** Adoption Steps (deprecated story loop IDs)
**Detail:** 7. **Stop calling deprecated IDs.** `bmad-create-story` and `bmad-dev-story` still run in full when invoked by name; `bmad-quick-dev` and `bmad-dev-auto` forward to the build skills. [SRC:src/bmm-skills/v6-shims/README.md:L9] [SRC:src/bmm-skills/v6-shims/README.md:L10] [SRC:src/bmm-skills/v6-shims/README.md:L11] [SRC:src/bmm-skills/v6-shims/README.md:L12]

## CORRECTION

**Source:** _bmad-output/.skf-stage/bmad-method-bmm/SKILL.md
**Pattern:** deprecated
**Affected:** Pattern Surface row 19 (v6-shims)
**Detail:** | 19 | `v6-shims/README.md` (bmm + core) | shim → replacement table | Deprecated ID forwarding [SRC:src/bmm-skills/v6-shims/README.md:L9] [SRC:src/core-skills/v6-shims/README.md:L9] |

## CORRECTION

**Source:** _bmad-output/.skf-stage/bmad-method-bmm/SKILL.md
**Pattern:** breaking change
**Affected:** references/pattern-release-context.md
**Detail:** - `references/pattern-release-context.md` — v6.11.0/v6.12.0 breaking changes and open upstream issues (T2).

## Key Types

**Story status** (`sprint_plan.py` rank order): `backlog` < `ready-for-dev` < `in-progress` < `review` < `done`. Epics: `backlog` < `in-progress` < `done`. Retrospectives: `optional` < `done`. Action items: `open`, `in-progress`, `done`. Legacy `drafted` → `ready-for-dev`, `contexted` → `in-progress`. [SRC:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L59] [SRC:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L60] [SRC:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L61] [SRC:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L63] [SRC:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L68]

**Spec status** (`bmad-build`): `draft`, `ready-for-dev`, `in-progress`, `in-review`, `done`; `bmad-build-auto` adds `blocked`. [SRC:src/bmm-skills/ship/bmad-build/step-01-clarify-and-route.md:L23] [SRC:src/bmm-skills/ship/bmad-build-auto/spec-template.md:L5]

**Spec `route`**: `oneshot` or `dispatch`. [SRC:src/bmm-skills/ship/bmad-build/spec-template.md:L6]

**Review triage buckets**: build skills route findings to `intent_gap`, `bad_spec`, `patch`, `defer`; `bmad-code-review` uses `decision_needed`, `patch`, `defer` with severity `high`/`medium`/`low`. [SRC:src/bmm-skills/ship/bmad-build/step-04-review.md:L56] [SRC:src/bmm-skills/ship/bmad-code-review/steps/step-03-triage.md:L25] [SRC:src/bmm-skills/ship/bmad-code-review/steps/step-03-triage.md:L42] [SRC:src/bmm-skills/ship/bmad-code-review/steps/step-03-triage.md:L43] [SRC:src/bmm-skills/ship/bmad-code-review/steps/step-03-triage.md:L44]

**Retro verdict**: `accepted`, `accepted-with-open-items`, `rejected`. [SRC:src/bmm-skills/ship/bmad-retrospective/references/retro-document.md:L15]

**Headless JSON status** (`bmad-prd`, `bmad-architecture`, `bmad-ux`): `complete`, `partial`, `blocked`. [SRC:src/bmm-skills/plan/bmad-prd/assets/headless-schemas.md:L7] [SRC:src/bmm-skills/plan/bmad-architecture/references/headless.md:L11] [SRC:src/bmm-skills/plan/bmad-ux/references/headless.md:L28] [SRC:src/bmm-skills/plan/bmad-ux/references/headless.md:L29]

## Architecture at a Glance

- **plan/** — `bmad-product-brief`, `bmad-prfaq`, `bmad-prd`, `bmad-ux`, `bmad-architecture`, `bmad-spec`, `bmad-create-epics-and-stories`, `bmad-sprint-planning`, `bmad-project-context`, `bmad-generate-project-context` (shim). [SRC:src/bmm-skills/plan/bmad-product-brief/SKILL.md:L3] [SRC:src/bmm-skills/plan/bmad-prfaq/SKILL.md:L16] [SRC:src/bmm-skills/module-help.csv:L10] [SRC:src/bmm-skills/module-help.csv:L11] [SRC:src/bmm-skills/module-help.csv:L12] [SRC:src/bmm-skills/module-help.csv:L5] [SRC:src/bmm-skills/module-help.csv:L13] [SRC:src/bmm-skills/module-help.csv:L14] [SRC:src/bmm-skills/module-help.csv:L3] [SRC:src/bmm-skills/plan/bmad-generate-project-context/SKILL.md:L3]
- **ship/** — `bmad-build`, `bmad-build-auto`, `bmad-code-review`, `bmad-correct-course`, `bmad-retrospective`, `bmad-walkthrough`, `bmad-qa-generate-e2e-tests`. [SRC:src/bmm-skills/module-help.csv:L4] [SRC:src/bmm-skills/module-help.csv:L16] [SRC:src/bmm-skills/module-help.csv:L6] [SRC:src/bmm-skills/module-help.csv:L19] [SRC:src/bmm-skills/module-help.csv:L17] [SRC:src/bmm-skills/module-help.csv:L18]
- **v6-shims/** — BMM forwarders (to build, build-auto, prd, architecture, deep-recon, sprint-planning, walkthrough, project-context) and two full retained workflows; core forwarders to `bmad-review` lenses. [SRC:src/bmm-skills/v6-shims/README.md:L9] [SRC:src/core-skills/v6-shims/README.md:L9] [SRC:src/core-skills/v6-shims/README.md:L19]
- **Customization** — every skill resolves `[workflow]` through `resolve_customization.py`: `{skill}/customize.toml` → `_bmad/custom/{skill}.toml` → `_bmad/custom/{skill}.user.toml`. [SRC:src/bmm-skills/ship/bmad-code-review/SKILL.md:L24] [SRC:src/bmm-skills/ship/bmad-code-review/SKILL.md:L29] [SRC:src/bmm-skills/ship/bmad-code-review/SKILL.md:L32]
- **Installer** — skills are discovered recursively and installed under their own `name`; folder nesting does not change the installed path. [SRC:src/bmm-skills/v6-shims/README.md:L26]

## CLI

Helper scripts are invoked with `uv run`; all print JSON on stdout. [SRC:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L7] [SRC:src/bmm-skills/ship/bmad-retrospective/scripts/sprint_status.py:L7] [SRC:src/bmm-skills/ship/bmad-retrospective/references/evidence-gathering.md:L11] [SRC:src/bmm-skills/plan/bmad-architecture/scripts/lint_spine.py:L21]

| Script | Commands and key flags |
|--------|------------------------|
| `sprint_plan.py` | `generate --epic-file … --status-file … --stories-dir … --project … --date "MM-DD-YYYY HH:MM" [--dry-run] [--fresh] [--set KEY=STATUS]`; `status --status-file … [--date] [--stale-days]`; `validate --status-file …` [AST:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L661] |
| `sprint_status.py` (retrospective) | `detect-epic --file … [--epic N]`; `update --file … --epic N [--set-retro-done] [--add-action JSON] [--set-action-status JSON] [--ref] [--verdict] [--date]` [AST:src/bmm-skills/ship/bmad-retrospective/scripts/sprint_status.py:L660] |
| `git_evidence.py` (retrospective) | `--repo . --range REV..REV --stories id,id` [AST:src/bmm-skills/ship/bmad-retrospective/scripts/git_evidence.py:L205] |
| `lint_spine.py` (architecture) | `--workspace <run-folder> [-o out.json]`; always exits 0 [AST:src/bmm-skills/plan/bmad-architecture/scripts/lint_spine.py:L230] |

```bash
uv run {skill-root}/scripts/sprint_plan.py generate \
  --epic-file <path> [--epic-file <path> ...] \
  --status-file {implementation_artifacts}/sprint-status.yaml \
  --stories-dir {implementation_artifacts} \
  --project "{project_name}" --date "{date}"
```

[SRC:src/bmm-skills/plan/bmad-sprint-planning/references/generate-tracking.md:L11] [SRC:src/bmm-skills/plan/bmad-sprint-planning/references/generate-tracking.md:L16]

<!-- [MANUAL:cli-notes] -->
<!-- Add custom notes here. This section is preserved during skill updates. -->
<!-- [/MANUAL:cli-notes] -->

## Full API Reference

Pattern-oriented reference files (Tier 2):

- `references/pattern-build-loop.md` — `bmad-build` and `bmad-build-auto`: routing, spec lifecycle, review layers, HALT conditions, result contract.
- `references/pattern-sprint-status.md` — `bmad-sprint-planning`, `sprint_plan.py`, status literals, who writes which transition.
- `references/pattern-review-and-close.md` — `bmad-code-review`, `bmad-correct-course`, `bmad-retrospective`, `bmad-walkthrough`, `bmad-qa-generate-e2e-tests`.
- `references/pattern-planning.md` — `bmad-prd`, `bmad-spec`, `bmad-architecture`, `bmad-ux`, `bmad-create-epics-and-stories`, `bmad-product-brief`, `bmad-prfaq`, `bmad-project-context`.
- `references/pattern-v6-shims.md` — every BMM and core shim, and the retained `bmad-create-story` / `bmad-dev-story` loop.
- `references/pattern-release-context.md` — v6.11.0/v6.12.0 breaking changes and open upstream issues (T2).
