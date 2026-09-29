# bmad-method-bmm Reference

**Version:** 6.12.0 (BMAD-METHOD tag `v6.12.0`, commit `05bfbd46`)
**Export count:** 37 exports (skill IDs, source skill metadata)
**Confidence:** T1-low (dominant `confidence_distribution` bin: t1 25, t1_low 593, t2 23, t3 0; forge tier Deep, reference-app)
**Source skill:** `skf-skills/bmad-method-bmm/6.12.0/bmad-method-bmm`

## Key Exports

| Export | Role |
|--------|------|
| `bmad-sprint-planning` | Owns `sprint-status.yaml`, which the Phase 4 chain reads |
| `bmad-build` | Turns a story into reviewed, verified code (stops at review) |
| `bmad-build-auto` | One unattended development-loop iteration |
| `bmad-code-review` | Review; sets `done` only when every decision-needed and patch finding is resolved and no high/medium remains, otherwise `in-progress` |
| `bmad-retrospective` | Optional at epic end (`-H <epic>` headless) |
| `bmad-correct-course` | Mid-sprint change proposal |
| `bmad-create-story`, `bmad-dev-story` | Deprecated v6 shims, retained in full under `v6-shims/`; TEA's ATDD slot sits between them |

## Usage Patterns

- Phase 4 chain in `module-help.csv`: `bmad-sprint-planning` → `bmad-build` → `bmad-code-review`, `bmad-retrospective` optional.
- `bmad-create-story` writes `{implementation_artifacts}/{{story_key}}.md` with `Status: ready-for-dev`; `bmad-dev-story` takes an explicit `{{story_path}}` or else the first `ready-for-dev` story.
- Most deprecated IDs forward to replacements through `src/bmm-skills/v6-shims/` and `src/core-skills/v6-shims/` (`bmad-create-story` and `bmad-dev-story` are retained in full instead); external module repos (gds, loop, tea, bmb, os-utils) still invoke the core IDs.

## Common Imports

Compose-mode: no import statements. BMM skills are invoked by skill name (for example `bmad-build` with a `story_key`), routed through `module-help.csv`.
