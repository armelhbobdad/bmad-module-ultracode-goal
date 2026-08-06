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

- This skill ships no `scripts/` or `customize.toml` of its own: the renderer
  (`status_render.py`), `customize.toml`, and `references/` all live in the **parent
  `ultracode-goal` module**. `{ucg-root}` names that module directory —
  `{project-root}/_bmad/ucg/ultracode-goal` in an installed project, or
  `{project-root}/skills/ultracode-goal` in a source checkout of the module itself.
  Resolve it once (first of those two that exists) and qualify every script path with
  it, so `{ucg-root}/scripts/…` and `{ucg-root}/customize.toml` resolve from any cwd.
  It is deliberately **not** `{skill-root}`: this is a top-level skill, so `{skill-root}`
  would resolve to this skill's own directory, which holds none of those files.
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{workflow.implementation_artifacts}` and `{workflow.deferred_work_path}` resolve from
  the parent module's `customize.toml` workflow block (the same scalars the autonomous
  run reads).
- Of the `[workflow]` block's three universal defaults, this skill loads
  `{workflow.persistent_facts}` (read-only context, and this skill runs cold) and executes
  **neither** `{workflow.activation_steps_prepend}` nor `{workflow.activation_steps_append}`.
  Those are operator-configured actions, and running one here would break the promise
  below. `ucg-formalize` and `ucg-resolve` state the same split.
- This skill writes nothing, including no decision-log entry. A status read is not an
  event in the run's history, and recording every glance at a run would bury the
  decisions the log exists to carry.

## On Activation

`/ucg-status` normally runs **cold** - outside the session that owns the run, which is
exactly the situation where nobody can see the transcript any more. Resolve the scalars
the renderer needs before calling it, against the **parent** module, so they are the same
paths the autonomous run wrote to. Run `python3
{project-root}/_bmad/scripts/resolve_customization.py --skill {ucg-root} --key workflow`
(on failure, merge `{ucg-root}/customize.toml` →
`{project-root}/_bmad/custom/ultracode-goal.toml` →
`{project-root}/_bmad/custom/ultracode-goal.user.toml`, scalars override / arrays append).

If a scalar cannot be resolved, do not pass an unresolved `{…}` token to the renderer:
say which scalar failed and stop. A render rooted at a path nobody resolved would describe
some other run, or no run, while looking exactly like a real answer.

## 1. Run the renderer

```
uv run {ucg-root}/scripts/status_render.py --impl-artifacts {workflow.implementation_artifacts} --deferred-work {workflow.deferred_work_path} --runs-root {project-root}/_bmad-output/ultracode-goal --repo {project-root}
```

`--deferred-work` carries the scalar Conventions told you to resolve. The two paths are
independent in the parent `customize.toml`, and the renderer defaults the ledger to
`deferred-work.md` *inside* `--impl-artifacts` when the flag is absent — so omitting it on
a project that moved the ledger renders `n/a`, or a different checkout's ledger, while
looking exactly like a clean read. Pass it and the render reads the same ledger the gate writes,
the same way `{ucg-root}/references/finalize.md` threads that scalar to `mem_observation.py`.

`--run-dir <the run folder>` is what makes the decision-log tail render at all, so the
invocation above - which omits it - always renders that row `n/a`. Do not ship that as the
normal answer:

- **When the operator named a run**, pass it. The runs index in the render lists the
  folders available to name.
- **When the operator named none**, resolve it: pass the run folder whose Epic matches the
  heartbeat's `epic` row, so the default read carries the log of the run it is describing.
  If no folder matches, or more than one does, leave the flag off **and say the tail is
  unscoped** - otherwise `n/a` reads as "this run has an empty log" when it means "nobody
  told the renderer which log to read".

The two halves can disagree, and the render does not say so. The heartbeat is a single
project-level file that whichever run ran last overwrote, while run folders are per-Epic
siblings; naming a run other than the one the heartbeat describes yields a header, stories,
escalations and ledger belonging to the **latest** run above a decision-log tail belonging
to the **named** one. When they differ, say which is which above the render, because
nothing in the render itself distinguishes them.

Pass `--runs-root <dir>` when the operator named a different runs root - runs kept under
a non-default output root, or another checkout's runs read from here. The invocation
above spells out the module's default, and no `customize.toml` scalar carries it, so this
flag is where an operator whose runs live elsewhere says so. Only the runs index moves.

`--impl-artifacts` is required and the renderer refuses to run without it (exit 2, nothing
rendered). Every **source** it reads is optional: an absent, empty or unparseable file
renders `n/a` and the render continues. That split is deliberate and matches the rest of
the module; `status_render.py` carries the reasoning behind it.

Pass `--impl-artifacts <dir>` yourself when the operator names an **isolated-track** run,
taking the dir that run recorded in its `.decision-log.md`
(`{ucg-root}/references/ingest-and-scope.md`, the cross-file/colliding-epic rule). The
configured scalar is the shared track's: rooted there, the render reads the shared track's
heartbeat, escalations and baselines and presents them as the answer about a different run.

## 2. Show what came back

Print the render. Do not re-derive, re-order, or re-judge any row: the renderer read the
files, and a second opinion formed here would be a second, later reading of artifacts that
may have moved on since.

Three things are worth saying out loud alongside it:

- **The `[machine-derived]` suffix is exclusive.** Only two rendered fields carry it: the
  gate's own reason strings, copied across unedited from the gate result the spine last
  read, and the turn counter the Stop hook maintains. Every other row is copied from an
  artifact a model wrote - except the runs index's `live` / `terminal` word, which the
  renderer derives from the files on disk, not from anything a model maintained.
- **`no run:` means no heartbeat file, not a broken read.** The runs index still renders
  below it, so a reader who is simply pointed at the wrong artifacts directory can see
  which runs do exist.
- **`live` means no run report is on disk yet, not that a process is attached.** A run
  whose session died mid-flight renders `live` for good. The one recency signal is the
  heartbeat's `Updated` row, and it belongs to the run that wrote the heartbeat rather
  than to every row of the index - so when the operator asked whether a run is still
  going, quote that timestamp (with `Phase`) alongside the index row instead of reading
  `live` as the answer.

## What the render carries

| row | what it is |
|---|---|
| epic / story / position / phase | where the spine is, from the heartbeat snapshot |
| last verdict | the gate's most recent verdict word |
| last reason(s) | the gate's reason strings, verbatim `[machine-derived]` |
| budget used | turns spent against the per-story ceiling `[machine-derived]` |
| re-loops this run | how many times this run re-entered a story, from the heartbeat |
| profile | the profile the run is on, from the heartbeat |
| updated | when the heartbeat was last written: this with `phase` is how a reader judges liveness |
| stories | one row per in-scope story: phase, verdict, attempts, re-loops |
| escalations | one block per escalation on disk (see below) |
| deferred work | every row of the ledger, across every run it has accumulated |
| decision log tail | the run's own account of itself, last lines - only when `--run-dir` was passed (§1) |
| runs index | every known run folder, `terminal` once it holds a run report, else `live` |

**Escalations render from the typed sidecar where one exists.** Where no readable one does,
the block carries one of two lines, and they mean different things:

- `escalation (unpromoted: session ended before Execute promoted it)` - only the Stop
  hook's raw marker is on disk. That is not an error state to clean up: it is the residual
  of a session that died between the hook writing the marker and Execute promoting it, and
  it is the only evidence that escalation happened at all. Report it as a pending
  escalation whose typed record was never written, and leave the marker alone.
- `escalation (typed record present but unreadable)` - the `escalation-<story>.json` named
  on the `- source:` line was written and then would not parse, which is the half-written
  file a session killed mid-write leaves. "Never promoted" would be the opposite of what
  happened: report it as a typed record that needs repair, because `/ucg-resolve` reads
  that same file to reconstruct the pending decision and cannot parse it either.

A marker and an unreadable sidecar can both be on disk for one story, and the marker wins
the render, so an `unpromoted` block is worth one directory check before you report the
typed record as never written.

## Optional diff-viewer affordance

When `hunk` is on PATH, each story that recorded a baseline commit gains one extra
copy-paste line, `hunk show <commit>`, so a reader can go straight from a story row to its
diff. When it is not on PATH, nothing about it is rendered and the render is otherwise
unchanged.

It is an affordance, never a dependency, and it is confined to stdout. The probe's result
never reaches an artifact: the run's gate artifacts and its headless envelope are
byte-identical whether or not the viewer is installed.
