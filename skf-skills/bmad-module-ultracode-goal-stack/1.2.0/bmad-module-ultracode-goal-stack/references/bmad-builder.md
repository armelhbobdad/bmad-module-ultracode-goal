# bmad-builder Reference

**Version:** 2.2.2 (bmad-builder tag `v2.2.2`, commit `4a142227`)
**Export count:** 5 exports (registered skills, source skill metadata)
**Confidence:** T1-low (dominant `confidence_distribution` bin: t1 0, t1_low 5, t2 0, t3 0; forge tier Quick, best-effort; skills read from `SKILL.md` frontmatter and `module-help.csv`)
**Source skill:** `skf-skills/bmad-builder/2.2.2/bmad-builder`

## Key Exports

| Export | Menu codes | Role |
|--------|------------|------|
| `bmad-bmb-setup` | SB | Set up (configure) the BMad Builder module in a project: `config.yaml` and `config.user.yaml` → `{project-root}/_bmad` |
| `bmad-agent-builder` | BA, AA | Build or analyze an agent skill |
| `bmad-workflow-builder` | BW, AW, CW | Build, analyze or convert a workflow/skill |
| `bmad-module-builder` | IM, CM, VM | Ideate, create (scaffold) and validate a module |
| `bmad-eval-runner` | — | Run a skill's evals and report results |

## Usage Patterns

- Module code `bmb` (`default_selected: false`), registered by `skills/module.yaml` and `skills/module-help.csv`.
- Config keys `bmad_builder_output_folder` (default `{project-root}/skills`) and `bmad_builder_reports` (default `{project-root}/skills/reports`).
- Sequences: BA → AA, BW → AW, IM → CM → VM.

## Common Imports

Compose-mode: no import statements. BMad Builder skills are invoked by skill name or menu code; `-H` runs `bmad-bmb-setup` headless.
