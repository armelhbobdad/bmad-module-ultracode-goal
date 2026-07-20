---
name: ucg-status
description: Read-only status view over an ultracode-goal run, rendered from the files that run already wrote - the heartbeat snapshot, the decision-log tail, the deferred-work ledger, the escalation sidecars, and an index of known run folders. Launches nothing, attaches to nothing, writes nothing. Use when an operator asks "what is this run doing", wants to check on a long or headless run, asks which runs exist or whether one is still live, or runs `/ucg-status`.
---

# UCG Status

## Overview

`/ucg-status` answers **"what is this run doing"** from artifacts alone. It is the read
side over what the spine already produces: it starts no run, attaches to no session,
resumes nothing, and writes nothing. Everything it shows was on disk before it ran.

That read-only property is the whole point, not a limitation. A status view is most
useful against a run that is currently going, and a reader that touched the run's
artifacts would be changing the thing it claims to describe. So this skill has exactly
one move: run the renderer and show what came back.

## Conventions

- This nested sub-skill ships no `scripts/` or `customize.toml` of its own: the renderer
  (`status_render.py`), `customize.toml`, and `references/` all live in the **parent**
  `ultracode-goal/` skill dir, one level up. `{skill-root}` in this file therefore
  resolves to that **parent** dir, so `{skill-root}/scripts/…` and
  `{skill-root}/customize.toml` resolve there; qualify every script path with it so it
  resolves from any cwd.
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{workflow.implementation_artifacts}` and `{workflow.deferred_work_path}` resolve from
  the parent module's `customize.toml` workflow block (the same scalars the autonomous
  run reads).
- This skill writes nothing, including no decision-log entry. A status read is not an
  event in the run's history, and recording every glance at a run would bury the
  decisions the log exists to carry.

## On Activation

`/ucg-status` normally runs **cold** - outside the session that owns the run, which is
exactly the situation where nobody can see the transcript any more. Resolve the scalars
the renderer needs before calling it, against the **parent** module, so they are the same
paths the autonomous run wrote to. Run `python3
{project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --key workflow`
(on failure, merge `{skill-root}/customize.toml` →
`{project-root}/_bmad/custom/ultracode-goal.toml` →
`{project-root}/_bmad/custom/ultracode-goal.user.toml`, scalars override / arrays append).

If a scalar cannot be resolved, do not pass an unresolved `{…}` token to the renderer:
say which scalar failed and stop. A render rooted at a path nobody resolved would describe
some other run, or no run, while looking exactly like a real answer.

## 1. Run the renderer

```
uv run {skill-root}/scripts/status_render.py --impl-artifacts {workflow.implementation_artifacts} --deferred-work {workflow.deferred_work_path} --runs-root {project-root}/_bmad-output/ultracode-goal --repo {project-root}
```

`--deferred-work` carries the scalar Conventions told you to resolve. The two paths are
independent in the parent `customize.toml`, and the renderer defaults the ledger to
`deferred-work.md` *inside* `--impl-artifacts` when the flag is absent — so omitting it on
a project that moved the ledger renders `n/a`, or a different checkout's ledger, while
looking exactly like a clean read. Pass it and the render reads the same ledger the gate writes,
the same way `references/finalize.md` threads that scalar to `mem_observation.py`.

Add `--run-dir <the run folder>` when the operator named a specific run, so the render
carries that run's decision-log tail. The runs index in the render lists the folders
available to name.

Pass `--runs-root <dir>` when the operator named a different runs root - runs kept under
a non-default output root, or another checkout's runs read from here. The invocation
above spells out the module's default, and no `customize.toml` scalar carries it, so this
flag is where an operator whose runs live elsewhere says so. Only the runs index moves.

`--impl-artifacts` is required and the renderer refuses to run without it (exit 2, nothing
rendered). Every **source** it reads is optional: an absent, empty or unparseable file
renders `n/a` and the render continues. That split is deliberate and matches the rest of
the module - a status read has no authority, so failing closed on a missing artifact would
turn a reporting gap into a dead end, while an invocation rooted nowhere would produce a
confident answer about the wrong run.

## 2. Show what came back

Print the render. Do not re-derive, re-order, or re-judge any row: the renderer read the
files, and a second opinion formed here would be a second, later reading of artifacts that
may have moved on since.

Two things are worth saying out loud alongside it:

- **The `[machine-derived]` suffix is exclusive.** Only two rendered fields carry it: the
  gate's own reason strings, copied across unedited from the gate result the spine last
  read, and the turn counter the Stop hook maintains. Every other row is model-maintained.
  The label carries information *because* it is exclusive - if everything were labeled it
  would say nothing.
- **`no run:` means no heartbeat file, not a broken read.** The runs index still renders
  below it, so a reader who is simply pointed at the wrong artifacts directory can see
  which runs do exist.

## What the render carries

| row | what it is |
|---|---|
| epic / story / position / phase | where the spine is, from the heartbeat snapshot |
| last verdict | the gate's most recent verdict word |
| last reason(s) | the gate's reason strings, verbatim `[machine-derived]` |
| budget used | turns spent against the per-story ceiling `[machine-derived]` |
| stories | one row per in-scope story: phase, verdict, attempts, re-loops |
| escalations | one block per escalation on disk (see below) |
| deferred work | every row of the ledger, across every run it has accumulated |
| decision log tail | the run's own account of itself, last lines |
| runs index | every known run folder, `terminal` once it holds a run report, else `live` |

**Escalations render from the typed sidecar where one exists.** Where only the Stop hook's
raw marker is on disk, the block instead reads `escalation (unpromoted: session ended
before Execute promoted it)`. That is not an error state to clean up: it is the residual of
a session that died between the hook writing the marker and Execute promoting it, and it is
the only evidence that escalation happened at all. Report it as a pending escalation whose
typed record was never written, and leave the marker alone.

## Optional diff-viewer affordance

When `hunk` is on PATH, each story that recorded a baseline commit gains one extra
copy-paste line, `hunk show <commit>`, so a reader can go straight from a story row to its
diff. When it is not on PATH, nothing about it is rendered and the render is otherwise
unchanged.

It is an affordance, never a dependency, and it is confined to stdout. The probe's result
never reaches an artifact: the run's gate artifacts and its headless envelope are
byte-identical whether or not the viewer is installed. A run whose recorded evidence
depended on which tools the reader happened to have installed would no longer be
reproducible from the run itself.

## Scope

This targets the **sequential spine only**. Under the experimental `--parallel` fan-out
each worktree agent sees its own copy of the implementation-artifacts directory and writes
no shared heartbeat, so there is no single snapshot for this to read. The watch surface for
a fan-out run is the workflow progress view and its run log, as the launch briefing says.
Do not imply this render covers a fan-out run.
