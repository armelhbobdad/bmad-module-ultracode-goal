# Pattern: sprint-status.yaml and `bmad-sprint-planning`

## Contents

- [Intents](#intents)
- [Readiness gate](#readiness-gate)
- [Generating tracking](#generating-tracking)
- [File schema](#file-schema)
- [Status literals and ranks](#status-literals-and-ranks)
- [Who writes which transition](#who-writes-which-transition)
- [Status view recommendations](#status-view-recommendations)
- [Headless contract](#headless-contract)
- [Validate and fix](#validate-and-fix)
- [sprint_plan.py functions (AST)](#sprint_planpy-functions-ast)

## Intents

`bmad-sprint-planning` loads BMM config (including `planning_artifacts` and `implementation_artifacts`) and routes to one of five intents; trigger phrases include "run sprint planning", "show sprint status", "validate sprint status" and "fix sprint status". [SRC:src/bmm-skills/plan/bmad-sprint-planning/SKILL.md:L2] [SRC:src/bmm-skills/plan/bmad-sprint-planning/SKILL.md:L3] [SRC:src/bmm-skills/plan/bmad-sprint-planning/SKILL.md:L15]

| Intent | Behaviour |
|--------|-----------|
| `readiness` | Run the gate, report, stop [SRC:src/bmm-skills/plan/bmad-sprint-planning/SKILL.md:L17] |
| `sprint-planning` | Full flow and refresh path: gate, then on PASS `references/generate-tracking.md` [SRC:src/bmm-skills/plan/bmad-sprint-planning/SKILL.md:L18] |
| `status` | Skip the gate, load the status view [SRC:src/bmm-skills/plan/bmad-sprint-planning/SKILL.md:L19] |
| `validate` | Check format via `references/validate.md` [SRC:src/bmm-skills/plan/bmad-sprint-planning/SKILL.md:L20] |
| `fix` | Repair or rebuild via `references/fix-sprint-status.md` [SRC:src/bmm-skills/plan/bmad-sprint-planning/SKILL.md:L21] |

The deprecated `bmad-sprint-status` shim forwards with intent `status view`, skipping intent detection and the readiness gate. [SRC:src/bmm-skills/v6-shims/bmad-sprint-status/SKILL.md:L24]

## Readiness gate

The core question is whether a developer could implement the epics without inventing unrecorded decisions. [SRC:src/bmm-skills/plan/bmad-sprint-planning/references/readiness-gate.md:L7] PASS states the verdict in one line and continues to generation; CONCERNS lists gaps and asks whether to proceed; FAIL orders findings by severity, names a fixing skill such as `bmad-correct-course`, may save them to `implementation-readiness.md`, and stops. [SRC:src/bmm-skills/plan/bmad-sprint-planning/references/readiness-gate.md:L18] [SRC:src/bmm-skills/plan/bmad-sprint-planning/references/readiness-gate.md:L19] [SRC:src/bmm-skills/plan/bmad-sprint-planning/references/readiness-gate.md:L20]

## Generating tracking

Epic sources are typically `epics.md`, `epic-*.md` or a sharded `epics/` folder in `planning_artifacts`; when whole and sharded versions both exist the skill asks which is current. [SRC:src/bmm-skills/plan/bmad-sprint-planning/references/generate-tracking.md:L5] Output: `{implementation_artifacts}/sprint-status.yaml`. [SRC:src/bmm-skills/plan/bmad-sprint-planning/references/generate-tracking.md:L11]

```bash
uv run {skill-root}/scripts/sprint_plan.py generate \
  --epic-file <path> [--epic-file <path> ...] \
  --status-file {implementation_artifacts}/sprint-status.yaml \
  --stories-dir {implementation_artifacts} \
  --project "{project_name}" --date "{date}"
```

- `{date}` must be `MM-DD-YYYY HH:MM`; the script parses `## Epic N:` and `### Story N.M: Title` headings into kebab-case keys and ignores fenced code blocks. [SRC:src/bmm-skills/plan/bmad-sprint-planning/references/generate-tracking.md:L16] [SRC:src/bmm-skills/plan/bmad-sprint-planning/references/generate-tracking.md:L16]
- Merging preserves advanced statuses and never downgrades; legacy `drafted`/`contexted` are normalized; a story file on disk floors the story at `ready-for-dev`. [SRC:src/bmm-skills/plan/bmad-sprint-planning/references/generate-tracking.md:L16] [SRC:src/bmm-skills/plan/bmad-sprint-planning/references/generate-tracking.md:L16]
- `--dry-run` previews drift through `in_sync`, `new_entries`, `dropped_orphans`, `illegal`, `legacy_mapped`; reconciled orphans get their status transplanted with `--set <new-key>=<old-status>`. [SRC:src/bmm-skills/plan/bmad-sprint-planning/references/generate-tracking.md:L16] [SRC:src/bmm-skills/plan/bmad-sprint-planning/references/generate-tracking.md:L20]
- After generation the skill suggests `bmad-build` for the first story. [SRC:src/bmm-skills/plan/bmad-sprint-planning/references/generate-tracking.md:L25]
- `generate` requires `--epic-file` (repeatable); story headings accept split suffixes like `2.6a`. [SRC:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L666] [SRC:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L46]

## File schema

- Required top-level keys: `generated`, `last_updated`, `project`, `development_status`. [SRC:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L619]
- Keys: epics `^epic-(\d+)$`, retrospectives `^epic-(\d+)-retrospective$`, stories `^(\d+)-(\d+)([a-z]?)-.+`. [SRC:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L55] [SRC:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L56] [SRC:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L57]
- Story key example `1-2-account-management`; retrospective `epic-N-retrospective` defaults to `optional`. [SRC:src/bmm-skills/plan/bmad-sprint-planning/sprint-status-template.yaml:L55] [SRC:src/bmm-skills/plan/bmad-sprint-planning/sprint-status-template.yaml:L58]
- Entries are ordered per epic: epic key, its stories, its retrospective. [SRC:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L210]
- `action_items` entries carry an `action` field. [SRC:src/bmm-skills/plan/bmad-sprint-planning/sprint-status-template.yaml:L69]

## Status literals and ranks

| Kind | Rank order | New entries |
|------|------------|-------------|
| Story | `backlog` < `ready-for-dev` < `in-progress` < `review` < `done` [SRC:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L59] | `backlog` [SRC:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L278] |
| Epic | `backlog` < `in-progress` < `done` [SRC:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L60] | `backlog` |
| Retrospective | `optional` < `done` [SRC:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L61] | `optional` |
| Action item | `open`, `in-progress`, `done` [SRC:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L63] | — |

Legacy: `drafted` → `ready-for-dev`, `contexted` → `in-progress`. [SRC:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L68] The template glosses `ready-for-dev` as "story file created, ready for development" and retrospective `optional` as "can be completed but not required"; an epic moves to `in-progress` when its first story starts, through Build's sprint sync. [SRC:src/bmm-skills/plan/bmad-sprint-planning/sprint-status-template.yaml:L20] [SRC:src/bmm-skills/plan/bmad-sprint-planning/sprint-status-template.yaml:L26] [SRC:src/bmm-skills/plan/bmad-sprint-planning/sprint-status-template.yaml:L36]

## Who writes which transition

| Writer | Transition |
|--------|------------|
| `bmad-sprint-planning` (`generate`) | Creates entries at `backlog`/`optional`; floors to `ready-for-dev` when a story file exists; never downgrades except via `--fresh --set` [SRC:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L278] [SRC:src/bmm-skills/plan/bmad-sprint-planning/references/generate-tracking.md:L16] [SRC:src/bmm-skills/plan/bmad-sprint-planning/references/fix-sprint-status.md:L28] |
| `bmad-build` | Story → `in-progress` at implementation (epic → `in-progress` too); story → `review` on completion [SRC:src/bmm-skills/ship/bmad-build/step-03-implement.md:L27] [SRC:src/bmm-skills/ship/bmad-build/sync-sprint-status.md:L4] [SRC:src/bmm-skills/ship/bmad-build/step-05-present.md:L17] |
| `bmad-code-review` | Story → `done` or back to `in-progress`; updates `last_updated` [SRC:src/bmm-skills/ship/bmad-code-review/steps/step-04-present.md:L91] [SRC:src/bmm-skills/ship/bmad-code-review/steps/step-04-present.md:L92] [SRC:src/bmm-skills/ship/bmad-code-review/steps/step-04-present.md:L104] |
| `bmad-retrospective` (`sprint_status.py update`) | `epic-N-retrospective` → `done`; appends `action_items` with status `open` [SRC:src/bmm-skills/ship/bmad-retrospective/references/retro-document.md:L54] [SRC:src/bmm-skills/ship/bmad-retrospective/references/retro-document.md:L54] |
| `bmad-correct-course` | New epics enter at `backlog` when the approved proposal changes epics [SRC:src/bmm-skills/ship/bmad-correct-course/checklist.md:L256] [SRC:src/bmm-skills/ship/bmad-correct-course/checklist.md:L257] |
| `bmad-create-story` (shim) | Story `backlog` → `ready-for-dev`; epic `backlog` → `in-progress` on its first story [SRC:src/bmm-skills/v6-shims/bmad-create-story/SKILL.md:L410] [SRC:src/bmm-skills/v6-shims/bmad-create-story/SKILL.md:L411] [SRC:src/bmm-skills/v6-shims/bmad-create-story/SKILL.md:L175] |
| `bmad-dev-story` (shim) | Story → `in-progress`, then → `review` [SRC:src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md:L288] [SRC:src/bmm-skills/v6-shims/bmad-dev-story/SKILL.md:L442] |
| `bmad-build-auto` | None (no reference to `sprint-status.yaml` in its files at v6.12.0) |

## Status view recommendations

`status` runs `sprint_plan.py status` with `--date`. [SRC:src/bmm-skills/plan/bmad-sprint-planning/references/status-view.md:L7] The next action follows a fixed priority: resume `in-progress`, review what is in `review`, start the next ready or backlog story, run an open retrospective, then all done. [SRC:src/bmm-skills/plan/bmad-sprint-planning/references/status-view.md:L10] The script recommends `bmad-build` for an in-progress story, `bmad-code-review` for a story in review (also raised as a risk), `bmad-retrospective` with a null `story_key` when all stories are done and a retrospective is still optional; `all_done` is true when there is no recommendation. [SRC:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L566] [SRC:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L569] [SRC:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L560] [SRC:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L580] [SRC:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L592]

## Headless contract

Headless never asks: it runs the gate and generates tracking unless the intent was readiness-only; ambiguity (duplicate epic versions, unreconciled orphans, an unconfirmed fix) halts with a blocked status. [SRC:src/bmm-skills/plan/bmad-sprint-planning/SKILL.md:L39] [SRC:src/bmm-skills/plan/bmad-sprint-planning/SKILL.md:L39] The JSON response's success `status` is `complete`, reports `{implementation_artifacts}/sprint-status.yaml`, carries `gate` (`PASS`/`CONCERNS`/`FAIL`; on FAIL findings and no `status_file`), and for `status`/`validate` passes the script JSON under `report`. [SRC:src/bmm-skills/plan/bmad-sprint-planning/SKILL.md:L43] [SRC:src/bmm-skills/plan/bmad-sprint-planning/SKILL.md:L46] [SRC:src/bmm-skills/plan/bmad-sprint-planning/SKILL.md:L52] [SRC:src/bmm-skills/plan/bmad-sprint-planning/SKILL.md:L52]

## Validate and fix

`validate` never writes and exits 0 whether or not the file is valid. [SRC:src/bmm-skills/plan/bmad-sprint-planning/references/validate.md:L10] The fix flow never writes without confirmation, prefers the lower status on thin evidence, and rebuilds with `generate --fresh` plus one `--set key=status` per confirmed entry — the one path allowed to downgrade. [SRC:src/bmm-skills/plan/bmad-sprint-planning/references/fix-sprint-status.md:L3] [SRC:src/bmm-skills/plan/bmad-sprint-planning/references/fix-sprint-status.md:L13] [SRC:src/bmm-skills/plan/bmad-sprint-planning/references/fix-sprint-status.md:L25] [SRC:src/bmm-skills/plan/bmad-sprint-planning/references/fix-sprint-status.md:L28] If `sprint_plan.py` errors, the skill reads files itself, reports the failure and offers the fix flow. [SRC:src/bmm-skills/plan/bmad-sprint-planning/SKILL.md:L31]

## sprint_plan.py functions (AST)

| Function | Citation |
|----------|----------|
| `classify_key(key)` | [AST:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L145] |
| `parse_epics(paths)` | [AST:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L172] |
| `build_status(entries, existing_data, stories_dir, warnings)` | [AST:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L257] |
| `cmd_generate(args)` | [AST:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L376] |
| `cmd_status(args)` | [AST:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L484] |
| `cmd_validate(args)` | [AST:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L596] |
| `build_parser()` | [AST:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L661] |
| `main(argv=None)` | [AST:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L691] |
| `error(self, message)` (JSON argparse errors) | [AST:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L128] |

`sprint_plan.py` prints only JSON on stdout, argparse failures included. [SRC:src/bmm-skills/plan/bmad-sprint-planning/scripts/sprint_plan.py:L7]
