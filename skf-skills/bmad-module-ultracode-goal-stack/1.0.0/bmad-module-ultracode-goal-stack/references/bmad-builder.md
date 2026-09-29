# bmad-builder (constituent)

- **Version:** 2.2.2 (bmad-builder tag `v2.2.2`, commit `4a142227`)
- **Export count:** 5 (registered skills, source skill metadata)
- **Confidence:** T1-low (source skill: Quick, best-effort; skills read from `SKILL.md` frontmatter and `module-help.csv`)
- **Source skill:** `skf-skills/bmad-builder/2.2.2/bmad-builder`

## Key exports used in this stack

| Export | Menu codes | Role |
|--------|------------|------|
| `bmad-bmb-setup` | SB | Install or update BMad Builder module config and help entries |
| `bmad-agent-builder` | BA, AA | Build or analyze an agent skill |
| `bmad-workflow-builder` | BW, AW, CW | Build, analyze or convert a workflow/skill |
| `bmad-module-builder` | IM, CM, VM | Ideate, create (scaffold) and validate a module |
| `bmad-eval-runner` | — | Run a skill's evals and report results |

## Usage patterns (from source skill)

- Module code `bmb`, registered by `skills/module.yaml` and `skills/module-help.csv`.
- Config keys `bmad_builder_output_folder` (default `{project-root}/skills`) and `bmad_builder_reports` (default `{project-root}/skills/reports`).
- Sequences: BA → AA, BW → AW, IM → CM → VM.
