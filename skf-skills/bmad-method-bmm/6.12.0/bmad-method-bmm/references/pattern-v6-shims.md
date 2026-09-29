# Pattern: v6 deprecation shims

## Contents

- [Why shims exist](#why-shims-exist)
- [BMM shim map](#bmm-shim-map)
- [Core shim map](#core-shim-map)
- [Rename-style shims and the legacy customization trap](#rename-style-shims-and-the-legacy-customization-trap)
- [Intent-forwarding shims](#intent-forwarding-shims)
- [Retained in full: bmad-create-story](#retained-in-full-bmad-create-story)
- [Retained in full: bmad-dev-story](#retained-in-full-bmad-dev-story)
- [Mapping the v6 story loop onto bmad-build](#mapping-the-v6-story-loop-onto-bmad-build)

## Why shims exist

Deprecated v6 skill IDs are kept for backward compatibility: some retain their full workflow, others forward to the replacement with a stated intent and pre-resolved customization. Removal rides the v7 cut, never a 6.x minor, and nesting in `v6-shims/` does not change the installed path or ID. [SRC:src/bmm-skills/v6-shims/README.md:L24] [SRC:src/bmm-skills/v6-shims/README.md:L26] Every shim's frontmatter carries `metadata.lifecycle: shim`. [SRC:src/bmm-skills/v6-shims/bmad-create-story/SKILL.md:L5] [SRC:src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md:L5] [SRC:src/bmm-skills/plan/bmad-generate-project-context/SKILL.md:L5]

## BMM shim map

| Deprecated ID | Replacement |
|---------------|-------------|
| `bmad-quick-dev` | `bmad-build` [SRC:src/bmm-skills/v6-shims/README.md:L9] |
| `bmad-dev-auto` | `bmad-build-auto` [SRC:src/bmm-skills/v6-shims/README.md:L10] |
| `bmad-create-story` | Retained in full [SRC:src/bmm-skills/v6-shims/README.md:L11] |
| `bmad-dev-story` | Retained in full [SRC:src/bmm-skills/v6-shims/README.md:L12] |
| `bmad-create-prd` | `bmad-prd` (create) [SRC:src/bmm-skills/v6-shims/README.md:L13] [SRC:src/bmm-skills/v6-shims/bmad-create-prd/SKILL.md:L24] |
| `bmad-edit-prd` | `bmad-prd` (update) [SRC:src/bmm-skills/v6-shims/README.md:L14] [SRC:src/bmm-skills/v6-shims/bmad-edit-prd/SKILL.md:L24] |
| `bmad-validate-prd` | `bmad-prd` (validate) [SRC:src/bmm-skills/v6-shims/README.md:L15] [SRC:src/bmm-skills/v6-shims/bmad-validate-prd/SKILL.md:L24] |
| `bmad-create-architecture` | `bmad-architecture` (create) [SRC:src/bmm-skills/v6-shims/README.md:L16] [SRC:src/bmm-skills/v6-shims/bmad-create-architecture/SKILL.md:L24] |
| `bmad-market-research` | `bmad-deep-recon` (market) [SRC:src/bmm-skills/v6-shims/README.md:L17] [SRC:src/bmm-skills/v6-shims/bmad-market-research/SKILL.md:L16] |
| `bmad-domain-research` | `bmad-deep-recon` (domain) [SRC:src/bmm-skills/v6-shims/README.md:L18] [SRC:src/bmm-skills/v6-shims/bmad-domain-research/SKILL.md:L16] |
| `bmad-technical-research` | `bmad-deep-recon` (technical) [SRC:src/bmm-skills/v6-shims/README.md:L19] [SRC:src/bmm-skills/v6-shims/bmad-technical-research/SKILL.md:L16] |
| `bmad-sprint-status` | `bmad-sprint-planning` (status view) [SRC:src/bmm-skills/v6-shims/README.md:L20] [SRC:src/bmm-skills/v6-shims/bmad-sprint-status/SKILL.md:L24] |
| `bmad-checkpoint-preview` | `bmad-walkthrough` [SRC:src/bmm-skills/v6-shims/README.md:L21] [SRC:src/bmm-skills/v6-shims/bmad-checkpoint-preview/SKILL.md:L15] |
| `bmad-document-project` | `bmad-project-context` (setup) [SRC:src/bmm-skills/v6-shims/bmad-document-project/SKILL.md:L16] |
| `bmad-generate-project-context` (under `plan/`) | `bmad-project-context` (setup) [SRC:src/bmm-skills/plan/bmad-generate-project-context/SKILL.md:L3] [SRC:src/bmm-skills/plan/bmad-generate-project-context/SKILL.md:L12] |

## Core shim map

| Deprecated ID | Replacement |
|---------------|-------------|
| `bmad-editorial-review` | `bmad-review` structure then prose lenses [SRC:src/core-skills/v6-shims/README.md:L9] [SRC:src/core-skills/v6-shims/bmad-editorial-review/SKILL.md:L8] |
| `bmad-editorial-review-prose` | `bmad-review` prose lens [SRC:src/core-skills/v6-shims/README.md:L10] [SRC:src/core-skills/v6-shims/bmad-editorial-review-prose/SKILL.md:L8] |
| `bmad-editorial-review-structure` | `bmad-review` structure lens [SRC:src/core-skills/v6-shims/README.md:L11] [SRC:src/core-skills/v6-shims/bmad-editorial-review-structure/SKILL.md:L8] |
| `bmad-review-adversarial-general` | `bmad-review` adversarial lens [SRC:src/core-skills/v6-shims/README.md:L12] [SRC:src/core-skills/v6-shims/bmad-review-adversarial-general/SKILL.md:L8] |
| `bmad-review-edge-case-hunter` | `bmad-review` edge-case lens; raw JSON array output [SRC:src/core-skills/v6-shims/README.md:L13] [SRC:src/core-skills/v6-shims/bmad-review-edge-case-hunter/SKILL.md:L8] |
| `bmad-review-verification-gap` | `bmad-review` verification-gap lens; `No verification gaps found.` when empty [SRC:src/core-skills/v6-shims/README.md:L14] [SRC:src/core-skills/v6-shims/bmad-review-verification-gap/SKILL.md:L8] |

External module repos (gds, loop, tea, bmb, os-utils) still invoke the core IDs. [SRC:src/core-skills/v6-shims/README.md:L19]

## Rename-style shims and the legacy customization trap

`bmad-quick-dev`, `bmad-dev-auto` and `bmad-checkpoint-preview` check for a legacy `_bmad/custom/<old-id>{,.user}.toml`. With none, they print a redirect notice and invoke the replacement exactly once with the original input. [SRC:src/bmm-skills/v6-shims/bmad-quick-dev/SKILL.md:L15] [SRC:src/bmm-skills/v6-shims/bmad-dev-auto/SKILL.md:L15] [SRC:src/bmm-skills/v6-shims/bmad-checkpoint-preview/SKILL.md:L15] With one, they map it to the new name (`bmad-quick-dev.toml` → `bmad-build.toml`, `bmad-dev-auto.toml` → `bmad-build-auto.toml`) and require explicit approval to rename; declined or unavailable approval HALTs and invokes nothing — so an unattended caller on the old ID with a legacy override never starts. [SRC:src/bmm-skills/v6-shims/bmad-quick-dev/SKILL.md:L17] [SRC:src/bmm-skills/v6-shims/bmad-dev-auto/SKILL.md:L17] [SRC:src/bmm-skills/v6-shims/bmad-quick-dev/SKILL.md:L19] [SRC:src/bmm-skills/v6-shims/bmad-dev-auto/SKILL.md:L19]

## Intent-forwarding shims

`bmad-create-prd`, `bmad-edit-prd`, `bmad-validate-prd`, `bmad-create-architecture` and `bmad-sprint-status` resolve the four legacy fields (`activation_steps_prepend`, `activation_steps_append`, `persistent_facts`, `on_complete`), emit a deprecation notice, and invoke the replacement with a fixed intent plus those pre-resolved values; the replacement takes over. [SRC:src/bmm-skills/v6-shims/bmad-sprint-status/SKILL.md:L14] [SRC:src/bmm-skills/v6-shims/bmad-create-prd/SKILL.md:L24] [SRC:src/bmm-skills/v6-shims/bmad-edit-prd/SKILL.md:L24] [SRC:src/bmm-skills/v6-shims/bmad-validate-prd/SKILL.md:L24] [SRC:src/bmm-skills/v6-shims/bmad-create-architecture/SKILL.md:L24] [SRC:src/bmm-skills/v6-shims/bmad-sprint-status/SKILL.md:L24] The research shims forward to `bmad-deep-recon` with the research type pre-set. [SRC:src/bmm-skills/v6-shims/bmad-market-research/SKILL.md:L16] [SRC:src/bmm-skills/v6-shims/bmad-domain-research/SKILL.md:L16] [SRC:src/bmm-skills/v6-shims/bmad-technical-research/SKILL.md:L16]

## Retained in full: bmad-create-story

- Description: deprecated, `bmad-build` is the official implementation method, use only when invoked by name; activation prints a deprecation notice. [SRC:src/bmm-skills/v6-shims/bmad-create-story/SKILL.md:L3] [SRC:src/bmm-skills/v6-shims/bmad-create-story/SKILL.md:L67]
- Reads `{implementation_artifacts}/sprint-status.yaml`; accepts a story path or an epic/story number (e.g. `2-4`, `1.6`, `epic 1 story 5`), which skips auto-discovery. [SRC:src/bmm-skills/v6-shims/bmad-create-story/SKILL.md:L77] [SRC:src/bmm-skills/v6-shims/bmad-create-story/SKILL.md:L99]
- Auto-discovery takes the first `development_status` story (top to bottom, excluding `epic-X` and `epic-X-retrospective`) with status `backlog`; none found HALTs with suggestions. [SRC:src/bmm-skills/v6-shims/bmad-create-story/SKILL.md:L142] [SRC:src/bmm-skills/v6-shims/bmad-create-story/SKILL.md:L144] [SRC:src/bmm-skills/v6-shims/bmad-create-story/SKILL.md:L146] [SRC:src/bmm-skills/v6-shims/bmad-create-story/SKILL.md:L147] [SRC:src/bmm-skills/v6-shims/bmad-create-story/SKILL.md:L151]
- Writes `{implementation_artifacts}/{{story_key}}.md` (heading `Story {{epic_num}}.{{story_num}}: {{story_title}}`, `Status: ready-for-dev`, Tasks/Subtasks, Dev Agent Record). [SRC:src/bmm-skills/v6-shims/bmad-create-story/SKILL.md:L83] [SRC:src/bmm-skills/v6-shims/bmad-create-story/template.md:L1] [SRC:src/bmm-skills/v6-shims/bmad-create-story/template.md:L3] [SRC:src/bmm-skills/v6-shims/bmad-create-story/template.md:L17] [SRC:src/bmm-skills/v6-shims/bmad-create-story/template.md:L39]
- Sprint updates: epic `backlog` → `in-progress` on its first story (HALT if the epic is `done`); story verified `backlog` then set `ready-for-dev`; `last_updated` bumped. [SRC:src/bmm-skills/v6-shims/bmad-create-story/SKILL.md:L175] [SRC:src/bmm-skills/v6-shims/bmad-create-story/SKILL.md:L179] [SRC:src/bmm-skills/v6-shims/bmad-create-story/SKILL.md:L410] [SRC:src/bmm-skills/v6-shims/bmad-create-story/SKILL.md:L411] [SRC:src/bmm-skills/v6-shims/bmad-create-story/SKILL.md:L412]
- Completion points to `dev-story` next and `code-review` afterwards. [SRC:src/bmm-skills/v6-shims/bmad-create-story/SKILL.md:L427] [SRC:src/bmm-skills/v6-shims/bmad-create-story/SKILL.md:L428]

## Retained in full: bmad-dev-story

- Description and notice mirror create-story. [SRC:src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md:L3] [SRC:src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md:L65]
- May modify only `baseline_commit`, Tasks/Subtasks checkboxes, Dev Agent Record, File List, Change Log and Status. [SRC:src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md:L15]
- Discovery: explicit `{{story_path}}` wins; otherwise the first story with status `ready-for-dev`; without sprint-status it searches `*-*-*.md`. [SRC:src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md:L94] [SRC:src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md:L110] [SRC:src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md:L160]
- `baseline_commit` is captured via `git rev-parse HEAD` (or `NO_VCS`) and never overwritten. [SRC:src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md:L268] [SRC:src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md:L281]
- Sprint updates: story → `in-progress` at step 4; → `review` at step 9 after verifying `in-progress`; story file Status → `review`. [SRC:src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md:L288] [SRC:src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md:L441] [SRC:src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md:L442] [SRC:src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md:L420]
- Runs to completion in one execution; HALTs on new dependencies, 3 consecutive failures, missing config, incomplete tasks, regressions, incomplete File List or a failed Definition of Done. [SRC:src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md:L17] [SRC:src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md:L337] [SRC:src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md:L338] [SRC:src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md:L339] [SRC:src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md:L460] [SRC:src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md:L461] [SRC:src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md:L462] [SRC:src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md:L463]
- Review continuation: detects a `Senior Developer Review (AI)` section and prioritizes `[AI-Review]` tasks. [SRC:src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md:L230] [SRC:src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md:L250]
- Hands off to code review, ideally with a different LLM. [SRC:src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md:L492] [SRC:src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md:L496]

## Mapping the v6 story loop onto bmad-build

| v6 loop | v6.12.0 official path |
|---------|------------------------|
| `bmad-create-story` picks `backlog`, writes `{story_key}.md`, sets `ready-for-dev` | `bmad-build` resolves `story_key` from sprint-status and writes a spec (`spec-{slug}.md` or `{spec_folder}/stories/{id}-{slug}.md`) [SRC:src/bmm-skills/v6-shims/bmad-create-story/SKILL.md:L147] [SRC:src/bmm-skills/v6-shims/bmad-create-story/SKILL.md:L411] [SRC:src/bmm-skills/ship/bmad-build/step-01-clarify-and-route.md:L44] [SRC:src/bmm-skills/ship/bmad-build/step-01-clarify-and-route.md:L96] [SRC:src/bmm-skills/ship/bmad-build/step-01-clarify-and-route.md:L22] |
| `bmad-dev-story` sets `in-progress` then `review` | `bmad-build` sets `in-progress` at step-03 and `review` at step-05 [SRC:src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md:L288] [SRC:src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md:L442] [SRC:src/bmm-skills/ship/bmad-build/step-03-implement.md:L27] [SRC:src/bmm-skills/ship/bmad-build/step-05-present.md:L17] |
| `bmad-code-review` sets `done` | unchanged [SRC:src/bmm-skills/ship/bmad-code-review/steps/step-04-present.md:L91] |
| story file `baseline_commit` | spec frontmatter `baseline_commit` (build) or `baseline_revision` (build-auto) [SRC:src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md:L281] [SRC:src/bmm-skills/ship/bmad-build/step-03-implement.md:L21] [SRC:src/bmm-skills/ship/bmad-build-auto/step-03-implement.md:L20] |
