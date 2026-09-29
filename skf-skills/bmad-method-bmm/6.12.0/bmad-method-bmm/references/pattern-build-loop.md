# Pattern: the Build loop (`bmad-build`, `bmad-build-auto`)

## Contents

- [Activation](#activation)
- [bmad-build — interactive implementation](#bmad-build--interactive-implementation)
- [bmad-build — spec file contract](#bmad-build--spec-file-contract)
- [bmad-build — review and completion](#bmad-build--review-and-completion)
- [bmad-build-auto — one unattended iteration](#bmad-build-auto--one-unattended-iteration)
- [bmad-build-auto — HALT protocol and result](#bmad-build-auto--halt-protocol-and-result)
- [Customization keys (both skills)](#customization-keys-both-skills)
- [Differences an orchestrator must handle](#differences-an-orchestrator-must-handle)

## Activation

Both skills are rendered, not read directly: activation runs `render_skill.py` through `uv` with `--project-root` and `--skill`, then follows the single absolute `workflow.md` path printed on stdout. A failed render (including `uv` unavailable) is reported and the skill HALTs without running workflow sources. [SRC:src/bmm-skills/ship/bmad-build/SKILL.md:L9] [SRC:src/bmm-skills/ship/bmad-build/SKILL.md:L12] [SRC:src/bmm-skills/ship/bmad-build/SKILL.md:L13] [SRC:src/bmm-skills/ship/bmad-build-auto/SKILL.md:L9] [SRC:src/bmm-skills/ship/bmad-build-auto/SKILL.md:L12] [SRC:src/bmm-skills/ship/bmad-build-auto/SKILL.md:L13]

`bmad-build` is described as turning delegated implementation work (feature, story, bug fix, meaningful change — a bare story or issue link counts) into reviewed, verified code; it skips obvious low-risk mechanical maintenance and does not volunteer for user-directed interactive edits or VCS bookkeeping. [SRC:src/bmm-skills/ship/bmad-build/SKILL.md:L3] [SRC:src/bmm-skills/ship/bmad-build/SKILL.md:L3] `bmad-build-auto` is "one iteration of an unattended development loop", used when invoked by name. [SRC:src/bmm-skills/ship/bmad-build-auto/SKILL.md:L3]

## bmad-build — interactive implementation

**Routing (step-01).**

- Plan-like wording in the invocation is not authority to skip steps. [SRC:src/bmm-skills/ship/bmad-build/step-01-clarify-and-route.md:L11]
- A spec folder plus story id reads `{spec_folder}/stories.yaml` (HALT if missing or unparseable) and, when no story file exists, targets `{spec_folder}/stories/{story_id}-{slug}.md`. [SRC:src/bmm-skills/ship/bmad-build/step-01-clarify-and-route.md:L21] [SRC:src/bmm-skills/ship/bmad-build/step-01-clarify-and-route.md:L22]
- An existing spec resumes by `status`: `draft` → step-02, `ready-for-dev`/`in-progress` → step-03 (or step-oneshot when `route: oneshot`), `in-review` → step-04; `done` is ingested as context only. [SRC:src/bmm-skills/ship/bmad-build/step-01-clarify-and-route.md:L23] [SRC:src/bmm-skills/ship/bmad-build/step-01-clarify-and-route.md:L23]
- With no explicit argument, active specs in `implementation_artifacts` are listed and the skill HALTs for Resume or New. [SRC:src/bmm-skills/ship/bmad-build/step-01-clarify-and-route.md:L31]
- `story_key` is the full sprint-status key (e.g. `3-2-digest-delivery`), resolved from `{implementation_artifacts}/sprint-status.yaml` by exact numeric epic-story equality; zero or multiple matches leave it unset. [SRC:src/bmm-skills/ship/bmad-build/step-01-clarify-and-route.md:L3] [SRC:src/bmm-skills/ship/bmad-build/step-01-clarify-and-route.md:L44] [SRC:src/bmm-skills/ship/bmad-build/step-01-clarify-and-route.md:L44]
- Epic context is cached at `{implementation_artifacts}/epic-<N>-context.md`, compiled by a synchronous subagent with `compile-epic-context.md`; a failed verification HALTs. [SRC:src/bmm-skills/ship/bmad-build/step-01-clarify-and-route.md:L57] [SRC:src/bmm-skills/ship/bmad-build/step-01-clarify-and-route.md:L62] [SRC:src/bmm-skills/ship/bmad-build/step-01-clarify-and-route.md:L65]
- A dirty working tree or mismatched branch HALTs; a multi-goal intent HALTs with Split / Keep; split goals go to `{implementation_artifacts}/deferred-work.md`. [SRC:src/bmm-skills/ship/bmad-build/step-01-clarify-and-route.md:L80] [SRC:src/bmm-skills/ship/bmad-build/step-01-clarify-and-route.md:L84] [SRC:src/bmm-skills/ship/bmad-build/step-01-clarify-and-route.md:L87]
- Default spec path: `{implementation_artifacts}/spec-{slug}.md` (slug led by a tracking id); an existing non-draft file gets `-2`, `-3` suffixes, a draft is resumed. [SRC:src/bmm-skills/ship/bmad-build/step-01-clarify-and-route.md:L96] [SRC:src/bmm-skills/ship/bmad-build/step-01-clarify-and-route.md:L96]

**Planning (step-02).** The route gate records intent gaps, irreversibles and footprint; a gap-free, reversible, small change takes the one-shot route (`route: oneshot`, `status: in-progress`), otherwise the planned route (`route: dispatch`). [SRC:src/bmm-skills/ship/bmad-build/step-02-plan.md:L15] [SRC:src/bmm-skills/ship/bmad-build/step-02-plan.md:L20] [SRC:src/bmm-skills/ship/bmad-build/step-02-plan.md:L22] A spec over 1600 tokens prompts Split / Keep; Open Questions HALT for answers; the spec cannot leave `draft` with open questions. [SRC:src/bmm-skills/ship/bmad-build/step-02-plan.md:L26] [SRC:src/bmm-skills/ship/bmad-build/step-02-plan.md:L34] [SRC:src/bmm-skills/ship/bmad-build/spec-template.md:L50] CHECKPOINT 1 offers **Approve and stop**, leaving the spec `ready-for-dev` for a fresh session; approval sets `ready-for-dev` and locks the frozen block. [SRC:src/bmm-skills/ship/bmad-build/step-02-plan.md:L55] [SRC:src/bmm-skills/ship/bmad-build/step-02-plan.md:L58]

**Implementation (step-03).** HALT if `{spec_file}` is missing; write `baseline_commit` (HEAD or `NO_VCS`, never overwritten); set `in-progress`; sync sprint-status to `in-progress` when `story_key` is set and the file exists; run `{workflow.implementation_handoff}`; write a unified diff since `baseline_commit` (untracked files included) to a temp `{diff_file}`. [SRC:src/bmm-skills/ship/bmad-build/step-03-implement.md:L15] [SRC:src/bmm-skills/ship/bmad-build/step-03-implement.md:L21] [SRC:src/bmm-skills/ship/bmad-build/step-03-implement.md:L25] [SRC:src/bmm-skills/ship/bmad-build/step-03-implement.md:L27] [SRC:src/bmm-skills/ship/bmad-build/step-03-implement.md:L31] [SRC:src/bmm-skills/ship/bmad-build/step-03-implement.md:L41]

## bmad-build — spec file contract

- Frontmatter `status` starts at `draft` (`ready-for-dev`, `in-progress`, `in-review`, `done`). [SRC:src/bmm-skills/ship/bmad-build/spec-template.md:L5]
- `route` is `oneshot` or `dispatch`; `review_loop_iteration` is incremented before each loopback; `context` lists `{project-root}/`-prefixed docs for the implementation agent. [SRC:src/bmm-skills/ship/bmad-build/spec-template.md:L6] [SRC:src/bmm-skills/ship/bmad-build/spec-template.md:L7] [SRC:src/bmm-skills/ship/bmad-build/spec-template.md:L8]
- Intent and constraints sit in a human-owned `<frozen-after-approval>` block. [SRC:src/bmm-skills/ship/bmad-build/spec-template.md:L16]
- Revisions are stored as full canonical identifiers, verbatim. [SRC:src/bmm-skills/ship/bmad-build/workflow.md:L35]

## bmad-build — review and completion

**Review (step-04).** Sets `in-review`; the spec is passed as `{claims_file}` only to the edge-case layer; without subagents, standalone reviewer prompts are written under `implementation_artifacts` and the skill HALTs for a human. [SRC:src/bmm-skills/ship/bmad-build/step-04-review.md:L11] [SRC:src/bmm-skills/ship/bmad-build/step-04-review.md:L17] [SRC:src/bmm-skills/ship/bmad-build/step-04-review.md:L27] Every finding gets one verdict and one row in `## Review Triage Log`, routed to `intent_gap`, `bad_spec`, `patch` or `defer`. [SRC:src/bmm-skills/ship/bmad-build/step-04-review.md:L43] [SRC:src/bmm-skills/ship/bmad-build/step-04-review.md:L56]

| Bucket | Effect |
|--------|--------|
| `intent_gap` | Revert code, back to step-02 after the human resolves it [SRC:src/bmm-skills/ship/bmad-build/step-04-review.md:L63] |
| `bad_spec` | Amend non-frozen sections, add a Spec Change Log entry, re-run step-03 [SRC:src/bmm-skills/ship/bmad-build/step-04-review.md:L64] |
| `patch` | Fixed; unfixable post-patch verification HALTs and escalates [SRC:src/bmm-skills/ship/bmad-build/step-04-review.md:L75] |
| `defer` | Appended to `{implementation_artifacts}/deferred-work.md` with `source_spec` [SRC:src/bmm-skills/ship/bmad-build/step-04-review.md:L76] |

`review_loop_iteration` above 5 HALTs for human escalation. [SRC:src/bmm-skills/ship/bmad-build/step-04-review.md:L62]

**Default review layers** (`[[workflow.review_layers]]`): `blind-hunter`, `edge-case-hunter` (`review-prompts/edge-case-hunter.md`), `verification-gap` (`review-prompts/verification-gap.md`); the one-shot route uses `[[workflow.oneshot_review_layers]]`, default only `blind-hunter`. [SRC:src/bmm-skills/ship/bmad-build/customize.toml:L84] [SRC:src/bmm-skills/ship/bmad-build/customize.toml:L108] [SRC:src/bmm-skills/ship/bmad-build/customize.toml:L124] [SRC:src/bmm-skills/ship/bmad-build/customize.toml:L134] Edge Case Hunter returns only a JSON array (`location`, `trigger_condition`, `guard_snippet`, `potential_consequence`); a clean verification-gap run prints exactly `No verification gaps found.` [SRC:src/bmm-skills/ship/bmad-build/review-prompts/edge-case-hunter.md:L60] [SRC:src/bmm-skills/ship/bmad-build/review-prompts/verification-gap.md:L109]

**Present (step-05).** Never auto-push; set spec `done`; sync sprint-status to **`review`** (not `done`); create a local conventional commit when VCS is available and the tree is dirty; summarize in one or two sentences with the commit hash; offer PR, `bmad-walkthrough`, or another change; run `{workflow.on_complete}` last. [SRC:src/bmm-skills/ship/bmad-build/step-05-present.md:L9] [SRC:src/bmm-skills/ship/bmad-build/step-05-present.md:L15] [SRC:src/bmm-skills/ship/bmad-build/step-05-present.md:L17] [SRC:src/bmm-skills/ship/bmad-build/step-05-present.md:L21] [SRC:src/bmm-skills/ship/bmad-build/step-05-present.md:L27] [SRC:src/bmm-skills/ship/bmad-build/step-05-present.md:L35] [SRC:src/bmm-skills/ship/bmad-build/step-05-present.md:L41]

**One-shot route.** Entered from step-02 or when resuming a `route: oneshot` spec; syncs sprint-status to `in-progress`; a discovered intent gap, irreversible or growth resets to `dispatch`/`draft` and returns to step-02; finalize sets `done` and syncs `review`; it stops and waits after presenting. [SRC:src/bmm-skills/ship/bmad-build/step-oneshot.md:L3] [SRC:src/bmm-skills/ship/bmad-build/step-oneshot.md:L17] [SRC:src/bmm-skills/ship/bmad-build/step-oneshot.md:L27] [SRC:src/bmm-skills/ship/bmad-build/step-oneshot.md:L33] [SRC:src/bmm-skills/ship/bmad-build/step-oneshot.md:L79] [SRC:src/bmm-skills/ship/bmad-build/step-oneshot.md:L99]

**Sprint sync rules** (`sync-sprint-status.md`): set `development_status[{story_key}]` to the target; never regress; `in-progress` also moves `epic-N` from `backlog` to `in-progress`; update `last_updated` preserving comments. [SRC:src/bmm-skills/ship/bmad-build/sync-sprint-status.md:L1] [SRC:src/bmm-skills/ship/bmad-build/sync-sprint-status.md:L3] [SRC:src/bmm-skills/ship/bmad-build/sync-sprint-status.md:L4] [SRC:src/bmm-skills/ship/bmad-build/sync-sprint-status.md:L5]

## bmad-build-auto — one unattended iteration

The goal is a hardened, reviewable artifact with no human interaction; the invocation prompt is the intent. [SRC:src/bmm-skills/ship/bmad-build-auto/workflow.md:L3] [SRC:src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md:L18]

**Dispatch modes (step-01).**

| Prompt shape | Behaviour |
|--------------|-----------|
| Existing spec file with known status | `draft` → step-02, `ready-for-dev`/`in-progress` → step-03, `in-review` → step-04; `blocked` HALTs (`blocked spec supplied`); `done` triggers a follow-up review (`review_loop_iteration` 0, `followup_pass` true) [SRC:src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md:L20] [SRC:src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md:L21] [SRC:src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md:L22] [SRC:src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md:L23] [SRC:src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md:L24] [SRC:src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md:L25] |
| Spec folder + story id | Reads `{spec_folder}/stories.yaml` (only `title`/`description`; checkpoint fields and `invoke_dev_with` are caller fields); story files by `{spec_folder}/stories/{story_id}-*.md`; first dispatch needs `{spec_folder}/SPEC.md` [SRC:src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md:L27] [SRC:src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md:L29] [SRC:src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md:L29] [SRC:src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md:L31] [SRC:src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md:L37] |
| Anything else | Story ID, ticket ID, file path, or free-form intent; too little intent HALTs `unclear intent` [SRC:src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md:L41] [SRC:src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md:L42] |

Each invocation handles exactly one `stories.yaml` entry and never advances to another story id. [SRC:src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md:L39] Folder+id blocking conditions: `no stories.yaml found`, `story id not found in stories.yaml`, `ambiguous story file match`, `story already blocked`, `unrecognized status in existing story file`, `no epic spec found`. [SRC:src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md:L29] [SRC:src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md:L29] [SRC:src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md:L32] [SRC:src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md:L35] [SRC:src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md:L36] [SRC:src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md:L37] A lower story left `in-review` without a `done` spec HALTs with `missing previous-story continuity decision`. [SRC:src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md:L63] A dirty tree, branch mismatch or unwritable Git metadata HALTs; multiple goals only add a warning. [SRC:src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md:L74] [SRC:src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md:L74] [SRC:src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md:L75]

**Spec path.** Folder+id: `{spec_folder}/stories/{story_id}-{slug}.md` (no fallback, no suffixing); otherwise `{implementation_artifacts}/spec-{slug}.md` with `-2`, `-3` suffixes. [SRC:src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md:L78] [SRC:src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md:L80] [SRC:src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md:L80]

**Plan → implement → review.** Planning asks nothing; an intent gap HALTs `intent gap`; a passing spec becomes `ready-for-dev`; `Halt after planning.` in the prompt stops there; a spec still failing after one repair HALTs. [SRC:src/bmm-skills/ship/bmad-build-auto/step-02-plan.md:L6] [SRC:src/bmm-skills/ship/bmad-build-auto/step-02-plan.md:L14] [SRC:src/bmm-skills/ship/bmad-build-auto/step-02-plan.md:L22] [SRC:src/bmm-skills/ship/bmad-build-auto/step-02-plan.md:L22] [SRC:src/bmm-skills/ship/bmad-build-auto/step-02-plan.md:L23] Implementation records `baseline_revision` (HEAD or `NO_VCS`), sets `in-progress`, runs `workflow.implementation_handoff` synchronously, and writes `{diff_file}`; unfixable `## Verification` failures HALT. [SRC:src/bmm-skills/ship/bmad-build-auto/step-03-implement.md:L20] [SRC:src/bmm-skills/ship/bmad-build-auto/step-03-implement.md:L24] [SRC:src/bmm-skills/ship/bmad-build-auto/step-03-implement.md:L30] [SRC:src/bmm-skills/ship/bmad-build-auto/step-03-implement.md:L38] [SRC:src/bmm-skills/ship/bmad-build-auto/step-03-implement.md:L40] Review sets `in-review`, launches all layers in parallel, routes findings to `intent_gap`/`bad_spec`/`patch`/`defer`, logs each pass in `## Review Triage Log`; an `intent_gap` saves a patch under `implementation_artifacts`, reverts, and HALTs; `bad_spec` loops back (more than 5 loops HALTs); patches re-engage the step-03 subagent. [SRC:src/bmm-skills/ship/bmad-build-auto/step-04-review.md:L11] [SRC:src/bmm-skills/ship/bmad-build-auto/step-04-review.md:L25] [SRC:src/bmm-skills/ship/bmad-build-auto/step-04-review.md:L56] [SRC:src/bmm-skills/ship/bmad-build-auto/step-04-review.md:L62] [SRC:src/bmm-skills/ship/bmad-build-auto/step-04-review.md:L70] [SRC:src/bmm-skills/ship/bmad-build-auto/step-04-review.md:L71] [SRC:src/bmm-skills/ship/bmad-build-auto/step-04-review.md:L72] [SRC:src/bmm-skills/ship/bmad-build-auto/step-04-review.md:L73] Deferred findings go to the frontmatter `deferred` list (`summary`, `evidence`, optional `location`, `severity`). [SRC:src/bmm-skills/ship/bmad-build-auto/step-04-review.md:L84] [SRC:src/bmm-skills/ship/bmad-build-auto/step-04-review.md:L93]

Default review layers: `blind-hunter`, `edge-case-hunter`, `verification-gap`, and an `intent-alignment` auditor fed the verbatim intent and the diff. [SRC:src/bmm-skills/ship/bmad-build-auto/customize.toml:L55] [SRC:src/bmm-skills/ship/bmad-build-auto/customize.toml:L79] [SRC:src/bmm-skills/ship/bmad-build-auto/customize.toml:L95] [SRC:src/bmm-skills/ship/bmad-build-auto/customize.toml:L104]

## bmad-build-auto — HALT protocol and result

- Finalize writes `## Auto Run Result` (summary, files changed, review breakdown, follow-up recommendation, verification, residual risks) and sets `followup_review_recommended`. [SRC:src/bmm-skills/ship/bmad-build-auto/step-04-review.md:L99] [SRC:src/bmm-skills/ship/bmad-build-auto/step-04-review.md:L107]
- With VCS, finalize writes `status: done` and commits the reviewed-diff files including the spec, without pushing; a dirty tree afterwards HALTs; success ends by HALTing with `done`. [SRC:src/bmm-skills/ship/bmad-build-auto/step-04-review.md:L113] [SRC:src/bmm-skills/ship/bmad-build-auto/step-04-review.md:L114] [SRC:src/bmm-skills/ship/bmad-build-auto/step-04-review.md:L116]
- On HALT an existing spec gets its `status` updated and details appended under `## Auto Run Result`, including `Blocking condition:`. [SRC:src/bmm-skills/ship/bmad-build-auto/workflow.md:L16] [SRC:src/bmm-skills/ship/bmad-build-auto/workflow.md:L28]
- In folder+id mode the write-back always targets the id-keyed story spec; unresolved and ambiguous cases use `{spec_folder}/stories/{story_id}-unresolved.md` and `-ambiguous.md`. [SRC:src/bmm-skills/ship/bmad-build-auto/workflow.md:L11] [SRC:src/bmm-skills/ship/bmad-build-auto/workflow.md:L13] [SRC:src/bmm-skills/ship/bmad-build-auto/workflow.md:L14]
- With no known spec file, HALT creates `{implementation_artifacts}/bmad-build-auto-result-<slug-or-timestamp>.md`. [SRC:src/bmm-skills/ship/bmad-build-auto/workflow.md:L32]
- After writing the result, HALT follows `workflow.on_complete`, then stops; no subagents when required HALTs `no subagents`; backgrounded subagents are forbidden because nothing resumes a yielded turn. [SRC:src/bmm-skills/ship/bmad-build-auto/workflow.md:L43] [SRC:src/bmm-skills/ship/bmad-build-auto/workflow.md:L53] [SRC:src/bmm-skills/ship/bmad-build-auto/workflow.md:L55]
- Spec statuses: `draft`, `ready-for-dev`, `in-progress`, `in-review`, `done`, `blocked`; frontmatter `warnings` (e.g. `oversized`, `multiple-goals`) and append-only `deferred` are machine-readable for orchestration. [SRC:src/bmm-skills/ship/bmad-build-auto/spec-template.md:L5] [SRC:src/bmm-skills/ship/bmad-build-auto/spec-template.md:L9] [SRC:src/bmm-skills/ship/bmad-build-auto/spec-template.md:L10] [SRC:src/bmm-skills/ship/bmad-build-auto/spec-template.md:L6]

## Customization keys (both skills)

| Key | Default | Notes |
|-----|---------|-------|
| `activation_steps_prepend` / `activation_steps_append` | `[]` | Build-auto runs prepend before config load, append before step-01 [SRC:src/bmm-skills/ship/bmad-build/customize.toml:L17] [SRC:src/bmm-skills/ship/bmad-build/customize.toml:L21] [SRC:src/bmm-skills/ship/bmad-build-auto/customize.toml:L17] [SRC:src/bmm-skills/ship/bmad-build-auto/customize.toml:L21] |
| `persistent_facts` | `[]` | Literal text or `file:` references [SRC:src/bmm-skills/ship/bmad-build/customize.toml:L27] [SRC:src/bmm-skills/ship/bmad-build-auto/customize.toml:L27] |
| `on_complete` | `""` | Terminal instruction [SRC:src/bmm-skills/ship/bmad-build/customize.toml:L32] [SRC:src/bmm-skills/ship/bmad-build-auto/customize.toml:L32] |
| `open_spec` (build) | empty | Leaves the completed spec closed [SRC:src/bmm-skills/ship/bmad-build/customize.toml:L34] |
| `implementation_handoff` | fresh-context subagent reading `{spec_file}` | [SRC:src/bmm-skills/ship/bmad-build/customize.toml:L71] [SRC:src/bmm-skills/ship/bmad-build-auto/customize.toml:L42] |
| `[[workflow.review_layers]]` | 3 layers (build), 4 (build-auto) | `when` gates a layer; empty `instruction` disables it [SRC:src/bmm-skills/ship/bmad-build/customize.toml:L80] [SRC:src/bmm-skills/ship/bmad-build-auto/customize.toml:L55] |

Overrides live in `_bmad/custom/bmad-build{,.user}.toml` and `_bmad/custom/bmad-build-auto{,.user}.toml`. [SRC:src/bmm-skills/ship/bmad-build/customize.toml:L4] [SRC:src/bmm-skills/ship/bmad-build-auto/customize.toml:L4]

## Differences an orchestrator must handle

- `bmad-build` writes sprint-status (`in-progress`, then `review`); no file under `src/bmm-skills/ship/bmad-build-auto/` references `sprint-status.yaml` or `story_key` at v6.12.0 (source grep, 0 matches), so an orchestrator driving `bmad-build-auto` owns sprint-status updates itself. [SRC:src/bmm-skills/ship/bmad-build/step-03-implement.md:L27] [SRC:src/bmm-skills/ship/bmad-build/step-05-present.md:L17]
- `bmad-build` records `baseline_commit`; `bmad-build-auto` records `baseline_revision`. [SRC:src/bmm-skills/ship/bmad-build/step-03-implement.md:L21] [SRC:src/bmm-skills/ship/bmad-build-auto/step-03-implement.md:L20]
- `bmad-build` HALTs for humans at CHECKPOINT 1, Open Questions and triage; `bmad-build-auto` converts every such case into a HALT with a blocking condition and a terminal status. [SRC:src/bmm-skills/ship/bmad-build/step-02-plan.md:L55] [SRC:src/bmm-skills/ship/bmad-build/step-02-plan.md:L34] [SRC:src/bmm-skills/ship/bmad-build-auto/step-02-plan.md:L6] [SRC:src/bmm-skills/ship/bmad-build-auto/workflow.md:L55]
- Neither skill pushes. [SRC:src/bmm-skills/ship/bmad-build/step-05-present.md:L9] [SRC:src/bmm-skills/ship/bmad-build-auto/step-04-review.md:L113]
