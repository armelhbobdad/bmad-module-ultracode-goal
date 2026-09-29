# bmad-method-bmm (constituent)

- **Version:** 6.12.0 (BMAD-METHOD tag `v6.12.0`, commit `05bfbd46`)
- **Export count:** 37 (skill IDs, source skill metadata)
- **Confidence:** T1 (source skill: Deep, reference-app)
- **Source skill:** `skf-skills/bmad-method-bmm/6.12.0/bmad-method-bmm`

## Key exports used in this stack

| Export | Role |
|--------|------|
| `bmad-sprint-planning` | Builds the sprint status the Phase 4 chain reads |
| `bmad-build` | Turns a story into reviewed, verified code (stops at review) |
| `bmad-build-auto` | One unattended development-loop iteration |
| `bmad-code-review` | Review and close (sets done) |
| `bmad-retrospective` | Optional at epic end |
| `bmad-correct-course` | Mid-sprint change handling |
| `bmad-create-story`, `bmad-dev-story` | Deprecated v6 shims, retained in full under `v6-shims/` |

## Usage patterns (from source skill)

- Phase 4 chain in `module-help.csv`: `bmad-sprint-planning` → `bmad-build` → `bmad-code-review`, `bmad-retrospective` optional.
- Deprecated IDs forward to replacements through `src/bmm-skills/v6-shims/` and `src/core-skills/v6-shims/`; external module repos (gds, loop, tea, bmb, os-utils) still invoke the core IDs.
