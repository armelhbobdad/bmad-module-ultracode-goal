# Pattern: planning skills

## Contents

- [Shared headless shape](#shared-headless-shape)
- [bmad-prd](#bmad-prd)
- [bmad-spec](#bmad-spec)
- [bmad-architecture](#bmad-architecture)
- [bmad-ux](#bmad-ux)
- [bmad-create-epics-and-stories](#bmad-create-epics-and-stories)
- [bmad-product-brief and bmad-prfaq](#bmad-product-brief-and-bmad-prfaq)
- [bmad-project-context](#bmad-project-context)
- [lint_spine.py (AST)](#lint_spinepy-ast)

## Shared headless shape

`bmad-prd`, `bmad-architecture` and `bmad-ux` honor a forwarded intent plus pre-resolved customization verbatim, detect headless from a `headless: true` flag or a non-interactive/skill caller, default to interactive when detection is ambiguous, halt `blocked` when intent stays ambiguous, and end with JSON whose `status` is `complete`, `partial` or `blocked`. [SRC:src/bmm-skills/plan/bmad-prd/SKILL.md:L18] [SRC:src/bmm-skills/plan/bmad-prd/references/headless.md:L9] [SRC:src/bmm-skills/plan/bmad-prd/references/headless.md:L10] [SRC:src/bmm-skills/plan/bmad-prd/references/headless.md:L14] [SRC:src/bmm-skills/plan/bmad-prd/references/headless.md:L29] [SRC:src/bmm-skills/plan/bmad-prd/assets/headless-schemas.md:L7] [SRC:src/bmm-skills/plan/bmad-architecture/SKILL.md:L51] [SRC:src/bmm-skills/plan/bmad-architecture/references/headless.md:L3] [SRC:src/bmm-skills/plan/bmad-architecture/references/headless.md:L3] [SRC:src/bmm-skills/plan/bmad-architecture/references/headless.md:L5] [SRC:src/bmm-skills/plan/bmad-architecture/references/headless.md:L11] [SRC:src/bmm-skills/plan/bmad-ux/references/headless.md:L7] [SRC:src/bmm-skills/plan/bmad-ux/references/headless.md:L24] [SRC:src/bmm-skills/plan/bmad-ux/references/headless.md:L28] [SRC:src/bmm-skills/plan/bmad-ux/references/headless.md:L29] Validate intents always write `validation-report.html` and `validation-report.md` and set `offer_to_update: true`. [SRC:src/bmm-skills/plan/bmad-prd/references/headless.md:L39] [SRC:src/bmm-skills/plan/bmad-prd/references/headless.md:L39] [SRC:src/bmm-skills/plan/bmad-architecture/references/headless.md:L5] [SRC:src/bmm-skills/plan/bmad-ux/references/headless.md:L37]

## bmad-prd

Create, update or validate a PRD; the `bmad-create-prd`, `bmad-edit-prd` and `bmad-validate-prd` shims invoke it with a pre-set intent. [SRC:src/bmm-skills/plan/bmad-prd/SKILL.md:L3] [SRC:src/bmm-skills/plan/bmad-prd/SKILL.md:L18]

- Config: `user_name`, `communication_language`, `document_output_language`, `planning_artifacts`, `project_name`, `date`; missing keys never block. [SRC:src/bmm-skills/plan/bmad-prd/SKILL.md:L22] [SRC:src/bmm-skills/plan/bmad-prd/SKILL.md:L22]
- Intent detection: Create (no PRD), Update (existing PRD plus a change signal), Validate (critique only). [SRC:src/bmm-skills/plan/bmad-prd/SKILL.md:L24] [SRC:src/bmm-skills/plan/bmad-prd/SKILL.md:L34] [SRC:src/bmm-skills/plan/bmad-prd/SKILL.md:L36]
- Create binds the workspace to `prd_output_path` + `run_folder_pattern` (defaults `{planning_artifacts}/prds` and `prd-{project_name}-{date}`) and writes `prd.md` with `status: draft`; Close sets `status: final`. [SRC:src/bmm-skills/plan/bmad-prd/SKILL.md:L32] [SRC:src/bmm-skills/plan/bmad-prd/customize.toml:L65] [SRC:src/bmm-skills/plan/bmad-prd/customize.toml:L66] [SRC:src/bmm-skills/plan/bmad-prd/SKILL.md:L32] [SRC:src/bmm-skills/plan/bmad-prd/SKILL.md:L93]
- Headless inputs: `intent`, a brief/spec (text, path or URL) for Create, an existing `prd.md` plus change signal for Update, optional `doc_workspace`. [SRC:src/bmm-skills/plan/bmad-prd/references/headless.md:L20] [SRC:src/bmm-skills/plan/bmad-prd/references/headless.md:L21] [SRC:src/bmm-skills/plan/bmad-prd/references/headless.md:L21] [SRC:src/bmm-skills/plan/bmad-prd/references/headless.md:L22]
- Headless outputs: `{doc_workspace}/prd.md`, `{doc_workspace}/.memlog.md`, `external_handoffs` entries, `changes_summary`, `conflicts_with_prior_decisions[]`, and for Validate `validation_report`. [SRC:src/bmm-skills/plan/bmad-prd/assets/headless-schemas.md:L19] [SRC:src/bmm-skills/plan/bmad-prd/assets/headless-schemas.md:L21] [SRC:src/bmm-skills/plan/bmad-prd/assets/headless-schemas.md:L25] [SRC:src/bmm-skills/plan/bmad-prd/assets/headless-schemas.md:L38] [SRC:src/bmm-skills/plan/bmad-prd/references/headless.md:L37] [SRC:src/bmm-skills/plan/bmad-prd/assets/headless-schemas.md:L53]
- Customization: `prd_template`, `validation_checklist_template`, `validation_report_template`, `external_sources`, `external_handoffs`, `finalize_reviewers` (all defaulted). [SRC:src/bmm-skills/plan/bmad-prd/customize.toml:L43] [SRC:src/bmm-skills/plan/bmad-prd/customize.toml:L52] [SRC:src/bmm-skills/plan/bmad-prd/customize.toml:L60] [SRC:src/bmm-skills/plan/bmad-prd/customize.toml:L108] [SRC:src/bmm-skills/plan/bmad-prd/customize.toml:L127] [SRC:src/bmm-skills/plan/bmad-prd/customize.toml:L148]
- Next skills: `bmad-ux`, `bmad-architecture`, `bmad-create-epics-and-stories`. [SRC:src/bmm-skills/plan/bmad-prd/SKILL.md:L93]

## bmad-spec

Condenses any input into `SPEC.md` plus supporting files; also updates, validates, and can break a spec into stories. [SRC:src/bmm-skills/plan/bmad-spec/SKILL.md:L3] [SRC:src/bmm-skills/plan/bmad-spec/SKILL.md:L3]

- Kernel: Why, Capabilities, Constraints, Non-goals, Success signal. [SRC:src/bmm-skills/plan/bmad-spec/SKILL.md:L9]
- Folder: `{output_folder}/specs/spec-{slug}/` (`spec_output_path` `{output_folder}/specs`, `run_folder_pattern` `spec-{slug}`); a slug from the source artifact is inherited; reusing a slug updates in place. [SRC:src/bmm-skills/plan/bmad-spec/SKILL.md:L32] [SRC:src/bmm-skills/plan/bmad-spec/customize.toml:L45] [SRC:src/bmm-skills/plan/bmad-spec/customize.toml:L52] [SRC:src/bmm-skills/plan/bmad-spec/SKILL.md:L36] [SRC:src/bmm-skills/plan/bmad-spec/SKILL.md:L38]
- Headless is the default invocation (no TTY or a programmatic caller): input in, JSON out, `files` lists every file written; errors `missing_slug` and `insufficient_intent`. [SRC:src/bmm-skills/plan/bmad-spec/SKILL.md:L24] [SRC:src/bmm-skills/plan/bmad-spec/assets/headless-schemas.md:L3] [SRC:src/bmm-skills/plan/bmad-spec/assets/headless-schemas.md:L18] [SRC:src/bmm-skills/plan/bmad-spec/SKILL.md:L37] [SRC:src/bmm-skills/plan/bmad-spec/SKILL.md:L40] [SRC:src/bmm-skills/plan/bmad-spec/assets/headless-schemas.md:L32]
- `SPEC.md` is derived from `.memlog.md` and never hand-edited; bmad-spec is its single writer. [SRC:src/bmm-skills/plan/bmad-spec/SKILL.md:L46] [SRC:src/bmm-skills/plan/bmad-spec/SKILL.md:L57]
- `stories.yaml` is written only by Story Breakdown, which headless runs never perform; entries are ordered for execution and never carry `status`; `spec_checkpoint`, `done_checkpoint` and `invoke_dev_with` are caller orchestration fields. [SRC:src/bmm-skills/plan/bmad-spec/SKILL.md:L49] [SRC:src/bmm-skills/plan/bmad-spec/SKILL.md:L134] [SRC:src/bmm-skills/plan/bmad-spec/assets/stories-schema.md:L3] [SRC:src/bmm-skills/plan/bmad-spec/assets/stories-schema.md:L20] [SRC:src/bmm-skills/plan/bmad-spec/assets/stories-schema.md:L12] [SRC:src/bmm-skills/plan/bmad-spec/assets/stories-schema.md:L13] [SRC:src/bmm-skills/plan/bmad-spec/assets/stories-schema.md:L14]

## bmad-architecture

Creates, updates or validates a short architecture document from a spec, a raw idea or an existing codebase. [SRC:src/bmm-skills/plan/bmad-architecture/SKILL.md:L3]

- Intents: create (default), update, validate; misrouted asks go to `bmad-prd`, `bmad-ux`, `bmad-spec`, `bmad-create-epics-and-stories` or `bmad-workflow-builder`. [SRC:src/bmm-skills/plan/bmad-architecture/SKILL.md:L55] [SRC:src/bmm-skills/plan/bmad-architecture/SKILL.md:L55]
- Output: `ARCHITECTURE-SPINE.md` in `{doc_workspace}` = `spine_output_path` (`{planning_artifacts}/architecture`) + `run_folder_pattern` (`architecture-{project_name}-{date}`; `architecture-epic-{epic_id}` suggested at epic altitude). [SRC:src/bmm-skills/plan/bmad-architecture/SKILL.md:L60] [SRC:src/bmm-skills/plan/bmad-architecture/customize.toml:L53] [SRC:src/bmm-skills/plan/bmad-architecture/customize.toml:L54] [SRC:src/bmm-skills/plan/bmad-architecture/customize.toml:L50]
- Headless payload: intent, altitude, purpose, driving input, optional parent spine, `doc_workspace`; results name `{doc_workspace}/ARCHITECTURE-SPINE.md` and `.memlog.md`. [SRC:src/bmm-skills/plan/bmad-architecture/references/headless.md:L5] [SRC:src/bmm-skills/plan/bmad-architecture/references/headless.md:L16] [SRC:src/bmm-skills/plan/bmad-architecture/references/headless.md:L17]
- Updates keep AD IDs stable (`AD-n`). Close sets `status: final`. [SRC:src/bmm-skills/plan/bmad-architecture/SKILL.md:L81] [SRC:src/bmm-skills/plan/bmad-architecture/SKILL.md:L76]
- Reviewer gate: `lint_spine.py` first, every `finalize_reviewers` entry always runs, headless never skips it; reviews go to `{doc_workspace}/reviews/review-{slug}.md`. [SRC:src/bmm-skills/plan/bmad-architecture/references/reviewer-gate.md:L5] [SRC:src/bmm-skills/plan/bmad-architecture/references/reviewer-gate.md:L7] [SRC:src/bmm-skills/plan/bmad-architecture/references/reviewer-gate.md:L7] [SRC:src/bmm-skills/plan/bmad-architecture/references/reviewer-gate.md:L9]
- Next: `bmad-spec`, then `bmad-create-epics-and-stories` or `bmad-build` at epic altitude. [SRC:src/bmm-skills/plan/bmad-architecture/SKILL.md:L76]

## bmad-ux

Captures UX in `DESIGN.md` (look) and `EXPERIENCE.md` (behavior). [SRC:src/bmm-skills/plan/bmad-ux/SKILL.md:L3] Output folder: `ux_output_path` (`{planning_artifacts}/ux-designs`) + `run_folder_pattern` (`ux-{project_name}-{date}`), holding both spines, `.memlog.md`, `.working/`, `imports/`, optional `mockups/`, `wireframes/` and validation reports. [SRC:src/bmm-skills/plan/bmad-ux/customize.toml:L59] [SRC:src/bmm-skills/plan/bmad-ux/customize.toml:L60] [SRC:src/bmm-skills/plan/bmad-ux/customize.toml:L54] Finalize sets `status: final` on both spines; next skills are `bmad-architecture`, `bmad-create-epics-and-stories`, `bmad-build`. [SRC:src/bmm-skills/plan/bmad-ux/SKILL.md:L90] [SRC:src/bmm-skills/plan/bmad-ux/SKILL.md:L90] Headless Create/Update reports `{doc_workspace}/DESIGN.md`. [SRC:src/bmm-skills/plan/bmad-ux/assets/headless-schemas.md:L19]

## bmad-create-epics-and-stories

Turns PRD requirements and architecture decisions into user-value stories with complete acceptance criteria. [SRC:src/bmm-skills/plan/bmad-create-epics-and-stories/SKILL.md:L8]

- Inputs: PRD (required, `{planning_artifacts}/*prd*.md`), Architecture (required), optional UX spine pair under `ux-designs/ux-*/`. [SRC:src/bmm-skills/plan/bmad-create-epics-and-stories/steps/step-01-validate-prerequisites.md:L49] [SRC:src/bmm-skills/plan/bmad-create-epics-and-stories/steps/step-01-validate-prerequisites.md:L50] [SRC:src/bmm-skills/plan/bmad-create-epics-and-stories/steps/step-01-validate-prerequisites.md:L59] [SRC:src/bmm-skills/plan/bmad-create-epics-and-stories/steps/step-01-validate-prerequisites.md:L69]
- Output: `{planning_artifacts}/epics.md` with `## Epic N:` and `### Story N.M:` headings, "As a / I want / So that" bodies and Given/When/Then acceptance criteria — the headings `sprint_plan.py` parses. [SRC:src/bmm-skills/plan/bmad-create-epics-and-stories/steps/step-01-validate-prerequisites.md:L80] [SRC:src/bmm-skills/plan/bmad-create-epics-and-stories/steps/step-03-create-stories.md:L168] [SRC:src/bmm-skills/plan/bmad-create-epics-and-stories/templates/epics-template.md:L40] [SRC:src/bmm-skills/plan/bmad-create-epics-and-stories/templates/epics-template.md:L46] [SRC:src/bmm-skills/plan/bmad-create-epics-and-stories/templates/epics-template.md:L48] [SRC:src/bmm-skills/plan/bmad-create-epics-and-stories/templates/epics-template.md:L56] [SRC:src/bmm-skills/plan/bmad-sprint-planning/references/generate-tracking.md:L16]
- Interactive gates: [C] menus in steps 1 and 4, explicit approval of the epic structure. [SRC:src/bmm-skills/plan/bmad-create-epics-and-stories/steps/step-01-validate-prerequisites.md:L226] [SRC:src/bmm-skills/plan/bmad-create-epics-and-stories/steps/step-02-design-epics.md:L183] [SRC:src/bmm-skills/plan/bmad-create-epics-and-stories/steps/step-04-final-validation.md:L131]
- Upstream issue #2885 (open at fetch time): step 01's non-recursive globs miss the PRD and architecture that `bmad-prd` and `bmad-architecture` write into run folders. [QMD:bmad-method-bmm-temporal:issues.md]

## bmad-product-brief and bmad-prfaq

`bmad-product-brief` creates, updates or validates `brief.md` in `brief_output_path` (`{planning_artifacts}/briefs`) + `brief-{project_name}-{date}`. [SRC:src/bmm-skills/plan/bmad-product-brief/SKILL.md:L3] [SRC:src/bmm-skills/plan/bmad-product-brief/SKILL.md:L31] [SRC:src/bmm-skills/plan/bmad-product-brief/customize.toml:L47] [SRC:src/bmm-skills/plan/bmad-product-brief/customize.toml:L48] `bmad-prfaq` accepts `--headless`/`-H` (requires customer, problem, stakes, solution), writes `{planning_artifacts}/prfaq-{project_name}.md` and a distillate, and returns a verdict of `forged`, `needs-heat` or `cracked`. [SRC:src/bmm-skills/plan/bmad-prfaq/SKILL.md:L16] [SRC:src/bmm-skills/plan/bmad-prfaq/SKILL.md:L79] [SRC:src/bmm-skills/plan/bmad-prfaq/SKILL.md:L121] [SRC:src/bmm-skills/plan/bmad-prfaq/references/verdict.md:L34] [SRC:src/bmm-skills/plan/bmad-prfaq/references/verdict.md:L71]

## bmad-project-context

Manages a repository's agent instructions as a block inside `AGENTS.md`, delimited by `<!-- bmad:context -->` and `<!-- /bmad:context -->`; intents `setup`, `adopt`, `refresh`, `record`, `audit`; every write is approved by the user. [SRC:src/bmm-skills/plan/bmad-project-context/SKILL.md:L3] [SRC:src/bmm-skills/plan/bmad-project-context/references/template.md:L17] [SRC:src/bmm-skills/plan/bmad-project-context/references/template.md:L52] [SRC:src/bmm-skills/plan/bmad-project-context/SKILL.md:L12] [SRC:src/bmm-skills/plan/bmad-project-context/SKILL.md:L10] It replaces `bmad-document-project` and `bmad-generate-project-context`, which forward to it with `setup` intent. [SRC:src/bmm-skills/module-help.csv:L3] [SRC:src/bmm-skills/v6-shims/bmad-document-project/SKILL.md:L16] [SRC:src/bmm-skills/plan/bmad-generate-project-context/SKILL.md:L12]

## lint_spine.py (AST)

| Function | Citation |
|----------|----------|
| `lint(text)` | [AST:src/bmm-skills/plan/bmad-architecture/scripts/lint_spine.py:L211] |
| `find_placeholders(body, offset)` | [AST:src/bmm-skills/plan/bmad-architecture/scripts/lint_spine.py:L70] |
| `find_frontmatter_placeholders(frontmatter)` | [AST:src/bmm-skills/plan/bmad-architecture/scripts/lint_spine.py:L91] |
| `find_ad_issues(body, offset)` | [AST:src/bmm-skills/plan/bmad-architecture/scripts/lint_spine.py:L109] |
| `find_unpinned_stack(body, offset)` | [AST:src/bmm-skills/plan/bmad-architecture/scripts/lint_spine.py:L153] |
| `split_frontmatter(text)` | [AST:src/bmm-skills/plan/bmad-architecture/scripts/lint_spine.py:L42] |
| `blank_fences(text)` | [AST:src/bmm-skills/plan/bmad-architecture/scripts/lint_spine.py:L60] |
| `line_of(text, idx)` | [AST:src/bmm-skills/plan/bmad-architecture/scripts/lint_spine.py:L66] |
| `main(argv)` | [AST:src/bmm-skills/plan/bmad-architecture/scripts/lint_spine.py:L230] |

Finding categories: `placeholder`, `ad_id`, `ad_fields`, `version_pin`; `ok` is true only with zero findings; a missing spine yields `ok: false` with a `not found` error, never a non-zero exit. [SRC:src/bmm-skills/plan/bmad-architecture/scripts/lint_spine.py:L13] [SRC:src/bmm-skills/plan/bmad-architecture/scripts/lint_spine.py:L14] [SRC:src/bmm-skills/plan/bmad-architecture/scripts/lint_spine.py:L15] [SRC:src/bmm-skills/plan/bmad-architecture/scripts/lint_spine.py:L16] [SRC:src/bmm-skills/plan/bmad-architecture/scripts/lint_spine.py:L222] [SRC:src/bmm-skills/plan/bmad-architecture/scripts/lint_spine.py:L238] [SRC:src/bmm-skills/plan/bmad-architecture/scripts/lint_spine.py:L21]
