# tea-testarch + bmad-method-bmm Integration

**Type:** Middleware Chain
**Co-import files:** 0 (compose-mode; no codebase — the contract is documented in a constituent skill)
**Detection:** constituent-documented-contract (`detection_method: constituent_documented_contract`) — documented by tea-testarch (Adoption Steps; `references/pattern-config-and-registration.md`; `references/pattern-atdd-and-automate.md`); BMM scopes TEA out
**Confidence:** T1-low (constituent-documented-contract) [composed] — weaker of tea-testarch (T1-low) and bmad-method-bmm (T1-low)

## Integration Pattern

Only TEA documents this seam. Its module-help.csv row puts bmad-testarch-atdd (AT, phase 4-implementation) after `bmad-create-story:create` and before `bmad-dev-story`, with automate (TA) next. ATDD needs an approved story with clear acceptance criteria and reads it from `{story_file}`; for BMM stories, story_key is the filename without `.md`. BMM's create-story writes that file as `{implementation_artifacts}/{{story_key}}.md` with `Status: ready-for-dev`, and dev-story takes an explicit `{{story_path}}` or else discovers the first story with that status. ATDD writes `{test_artifacts}/atdd-checklist-{story_key}.md` and red-phase scaffolds, which carry `test.skip()` in every execution mode. When the story file is writable, it also adds an `### ATDD Artifacts` subsection under the story's `## Dev Notes`; a failed update does not fail the run. Its last step recommends dev-story, then automate. In the GREEN phase the developer removes `test.skip()` for one test and confirms it fails first. TEA's Gotchas say to review only after the developer removes `test.skip()`, because test-review row C1 (CRITICAL) fires on skipped tests. BMM's side does not document the crossing: its skill scopes TEA out, and create-story's completion points straight to dev-story. BMM describes the preceded-by/followed-by columns as catalogue order and phase routing for bmad-help, and no TEA workflow is required, so ATDD presumably runs only when an orchestrator or the user invokes it (inferred). In BMM 6.12.0 both neighbours of the AT slot are deprecated shims (retained in full, but opt-in via `--shims` on fresh installs and dropped from bmad-help). The official Phase 4 is sprint-planning → bmad-build → code-review, and TEA v1.27.2's skill never mentions bmad-build (no grep match).

## Key Files

Upstream source files behind the cited lines (from the constituents' `[SRC:…]` tags):

- `src/module-help.csv`
- `src/workflows/testarch/bmad-testarch-atdd/steps-c/step-01-preflight-and-context.md`
- `src/workflows/testarch/bmad-testarch-atdd/steps-c/step-04c-aggregate.md`
- `src/workflows/testarch/bmad-testarch-atdd/steps-c/step-05-validate-and-complete.md`
- `src/workflows/testarch/bmad-testarch-atdd/steps-c/step-04-generate-tests.md`
- `src/workflows/testarch/bmad-testarch-atdd/SKILL.md`
- `src/workflows/testarch/bmad-testarch-atdd/workflow.yaml`
- `src/workflows/testarch/bmad-testarch-atdd/atdd-checklist-template.md`
- `src/bmm-skills/v6-shims/bmad-create-story/SKILL.md`
- `src/bmm-skills/v6-shims/bmad-create-story/template.md`
- `src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md`
- `src/bmm-skills/v6-shims/README.md`
- `src/bmm-skills/module-help.csv`
- `src/bmm-skills/ship/bmad-build/step-01-clarify-and-route.md`
- `src/bmm-skills/ship/bmad-build-auto/step-02-plan.md`

## Usage Convention

Run `bmad-testarch-atdd` with `story_file={implementation_artifacts}/{story_key}.md` once the story is `ready-for-dev` and before implementation starts; on the legacy loop that is after `bmad-create-story` and before `bmad-dev-story`, which needs shims opted in (`--shims`, or the interactive shim prompt) on a fresh v6.12.0 install. The orchestrator has to invoke ATDD explicitly, because neither skill documents BMM doing it, and test-review should wait until the developer has removed `test.skip()` (row C1 fires on skipped tests). TEA v1.27.2 documents no placement inside a `bmad-build` run.

## Evidence

Verbatim citations from the constituent skills (file relative to the skill root, nearest heading, line):

- [from skill: tea-testarch] `SKILL.md` — ## Adoption Steps, L46: "**Per story:** atdd (AT) after `bmad-create-story:create` and before `bmad-dev-story`, then automate (TA)."
- [from skill: tea-testarch] `references/pattern-config-and-registration.md` — ## module-help.csv rows, L52: "| `bmad-testarch-atdd` | AT | 4-implementation | After `bmad-create-story:create`, before `bmad-dev-story`; atdd-checklist + red-phase tests"
- [from skill: tea-testarch] `references/pattern-config-and-registration.md` — ## module-help.csv rows, L45: "No TEA workflow is `required`."
- [from skill: tea-testarch] `references/pattern-atdd-and-automate.md` — ## ATDD inputs and prerequisites, L16: "Hard prerequisites: an approved story with clear acceptance criteria"
- [from skill: tea-testarch] `references/pattern-atdd-and-automate.md` — ## ATDD inputs and prerequisites, L17: "Story from `{story_file}` (asked for when absent); for BMM stories `story_key` is the filename without `.md`, otherwise a title slug (≤ 64 chars)."
- [from skill: tea-testarch] `references/pattern-atdd-and-automate.md` — ## ATDD outputs and steps, L34: "| Checklist | `{test_artifacts}/atdd-checklist-{story_key}.md` (`workflowType: testarch-atdd`)"
- [from skill: tea-testarch] `references/pattern-atdd-and-automate.md` — ## ATDD outputs and steps, L41: "If the story file is writable an `### ATDD Artifacts` subsection is added under `## Dev Notes`; a failed update does not fail the run."
- [from skill: tea-testarch] `references/pattern-atdd-and-automate.md` — ## ATDD outputs and steps, L43: "`step-05-validate-and-complete` (recommends dev-story, then automate)."
- [from skill: tea-testarch] `references/pattern-atdd-and-automate.md` — ## ATDD red-phase contract, L28: "GREEN phase: the developer removes `test.skip()` for one test and confirms it fails first."
- [from skill: tea-testarch] `references/pattern-atdd-and-automate.md` — ## ATDD red-phase contract, L24: "Scaffolds carry `test.skip()` in every execution mode"
- [from skill: tea-testarch] `SKILL.md` — ## Pattern Surface, L58: "| 4 | `bmad-testarch-atdd` | AT | `atdd-checklist-{story_key}.md` and red-phase `test.skip()` scaffolds"
- [from skill: tea-testarch] `SKILL.md` — ## Gotchas, L86: "Scaffolds carry `test.skip()`, and test-review registry row C1 (CRITICAL) fires on skipped tests. Review after the developer removes `test.skip()`."
- [from skill: tea-testarch] `references/pattern-release-context.md` — ## Upcoming (after v1.27.2), L16: "per-scope files carry a `run_key` (`system`, `epic-{epic_num}`, `story-{story_key}`"
- [from skill: tea-testarch] `references/pattern-test-design.md` — ## Mode detection, L28: "| Intent unclear and `{implementation_artifacts}/sprint-status.yaml` exists | Epic-level"
- [from skill: bmad-method-bmm] `references/pattern-v6-shims.md` — ## BMM shim map, L24: "| `bmad-create-story` | Retained in full"
- [from skill: bmad-method-bmm] `references/pattern-v6-shims.md` — ## BMM shim map, L25: "| `bmad-dev-story` | Retained in full"
- [from skill: bmad-method-bmm] `SKILL.md` — frontmatter description (before the first heading), L9: "Not for the installer (see bmad-method-installer) or TEA test-architecture skills."
- [from skill: bmad-method-bmm] `references/pattern-v6-shims.md` — ## Retained in full: bmad-create-story, L64: "Writes `{implementation_artifacts}/{{story_key}}.md` (heading `Story {{epic_num}}.{{story_num}}: {{story_title}}`, `Status: ready-for-dev`, Tasks/Subtasks, Dev Agent Record)."
- [from skill: bmad-method-bmm] `references/pattern-v6-shims.md` — ## Retained in full: bmad-create-story, L66: "Completion points to `dev-story` next and `code-review` afterwards."
- [from skill: bmad-method-bmm] `references/pattern-v6-shims.md` — ## Retained in full: bmad-create-story, L61: "Description: deprecated, `bmad-build` is the official implementation method, use only when invoked by name; activation prints a deprecation notice."
- [from skill: bmad-method-bmm] `references/pattern-v6-shims.md` — ## Retained in full: bmad-dev-story, L72: "Discovery: explicit `{{story_path}}` wins; otherwise the first story with status `ready-for-dev`"
- [from skill: bmad-method-bmm] `references/pattern-v6-shims.md` — ## Retained in full: bmad-dev-story, L71: "May modify only `baseline_commit`, Tasks/Subtasks checkboxes, Dev Agent Record, File List, Change Log and Status."
- [from skill: bmad-method-bmm] `SKILL.md` — ## Pattern Surface, L58: "`preceded-by` / `followed-by` columns | Catalog order and phase routing for `bmad-help`"
- [from skill: bmad-method-bmm] `SKILL.md` — ## Quick Start, L24: "The Phase 4 chain in `module-help.csv` is `bmad-sprint-planning` → `bmad-build` → `bmad-code-review`, with `bmad-retrospective` optional at epic end."
- [from skill: bmad-method-bmm] `SKILL.md` — ## Migration & Deprecation Warnings, L82: "v6.12.0: deprecated shims are opt-in on fresh installs (`--shims` keeps them)"
- [from skill: bmad-method-bmm] `references/pattern-release-context.md` — ## v6.11.0 changes that shape v6.12.0 (T2-past), L22: "`bmad-create-story` and `bmad-dev-story` deprecated, moved to `v6-shims/`, dropped from `bmad-help` and the dev agent menu (`DS`, `CS`); Phase 4 is `bmad-sprint-planning → bmad-build → bmad-code-review`."
- [from skill: bmad-method-bmm] `context-snippet.md` — gotchas line (context snippet has no heading), L6: "create-story/dev-story are deprecated shims, opt-in via --shims on fresh v6.12.0 installs"
- [from skill: bmad-method-bmm] `references/pattern-v6-shims.md` — ## Mapping the v6 story loop onto bmad-build, L83: "| `bmad-create-story` picks `backlog`, writes `{story_key}.md`, sets `ready-for-dev` | `bmad-build` resolves `story_key` from sprint-status and writes a spec (`spec-{slug}.md` or `{spec_folder}/stories/{id}-{slug}.md`)"
- [from skill: bmad-method-bmm] `references/pattern-build-loop.md` — ## bmad-build-auto — one unattended iteration, L81: "a passing spec becomes `ready-for-dev`; `Halt after planning.` in the prompt stops there"
- [from skill: bmad-method-bmm] `references/pattern-build-loop.md` — ## bmad-build — interactive implementation, L26: "An existing spec resumes by `status`: `draft` → step-02, `ready-for-dev`/`in-progress` → step-03"
