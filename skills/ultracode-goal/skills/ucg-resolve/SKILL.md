---
name: ucg-resolve
description: Decide-surface for a blocked or escalated ultracode-goal run. Reconstructs every pending decision from on-disk artifacts alone - the typed escalation sidecars, the single preflight RED sidecar, and the deferred-work ledger's decision rows - walks them in one guided pass, records each answer, applies what a close resolves, and hands control back to the existing resume. Use when an operator returns to a run that stopped, asks what is pending or what still needs deciding, wants to answer a preflight RED so it does not re-fire at the next preflight, or runs `/ucg-resolve`.
---

# UCG Resolve

## Overview

`/ucg-resolve` is where an operator answers what a stopped run is waiting on. It
reconstructs the pending decisions from artifacts alone, walks them in **one** guided
pass, writes the answers down, applies what an answer resolves, and then hands control
back to the resume the module already has.

The loop only counts as closed if an answer given here is not asked for again. So a
decision resolved at this surface is consumed by the next preflight's semantic
intervention scan and does not re-fire — that consumption lives in
`{skill-root}/references/preflight.md`, step 3, and it is the half that makes this skill
more than a note-taker.

## Conventions

- This nested sub-skill ships no `scripts/` or `customize.toml` of its own: the scripts,
  `customize.toml`, and `references/` all live in the **parent** `ultracode-goal/` skill
  dir, one level up. `{skill-root}` in this file therefore resolves to that **parent**
  dir, so `{skill-root}/scripts/…` and `{skill-root}/customize.toml` resolve there;
  qualify every script path with it so it resolves from any cwd.
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{workflow.implementation_artifacts}` and `{workflow.deferred_work_path}` resolve from
  the parent module's `customize.toml` workflow block (the same scalars the autonomous
  run reads and writes).
- The decision log (`.decision-log.md`) is canonical memory: record each answer and the
  disposition applied to it as you go.

## On Activation

`/ucg-resolve` normally runs **cold** — the operator arrives at a run that stopped, in a
session that never saw it start. That is the whole point of this surface, so resolve the
scalars before reading any artifact. Run `python3
{project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --key workflow`
(on failure, merge `{skill-root}/customize.toml` →
`{project-root}/_bmad/custom/ultracode-goal.toml` →
`{project-root}/_bmad/custom/ultracode-goal.user.toml`, scalars override / arrays append).

If a scalar cannot be resolved, do not pass an unresolved `{…}` token to a path: say
which scalar failed and stop. A decision surface rooted at a path nobody resolved would
enumerate some other run's pending work, or none at all, while looking exactly like a
real answer.

## 1. Enumerate the pending decisions

Three sources, all on disk. Read these and nothing else — the run's transcript is gone,
and anything not written down is not a pending decision this surface can honor.

1. **The typed escalation sidecars** — `{workflow.implementation_artifacts}/escalation-<story_id>.json`,
   one per escalating story, each a single object with the four string fields `source`,
   `kind`, `decision_needed`, and `evidence`. A sidecar left pending by an earlier run is
   genuinely still pending: the arming step deliberately does not purge `escalation-*.json`,
   so a decision an operator chose to leave open survives to this pass.
2. **The preflight RED sidecar** — `{workflow.implementation_artifacts}/.preflight-reds.json`,
   shape `{"reds": [...]}`. **One** file holds every still-pending preflight RED. There is
   no second RED sidecar and no per-story one: a per-story or per-run RED file would carry
   an id that changed between scans, and an id that changes cannot carry an answer forward.
3. **The deferred-work ledger** — `{workflow.deferred_work_path}`, restricted to its
   `decision:` rows. Those are the rows whose `source` column reads `decision` (as opposed
   to `gate` or `code-review`) **and** whose `status` is still `open`; a row already marked
   `resolved` is not a pending decision. The ledger is a markdown table per Epic, and the
   in-repo parser is table-only and fails soft — match that behavior: a malformed or
   bullet-list ledger yields no rows here, never a crash.

**Every pending item is keyed by a stable `id`.** It is minted from the finding's `kind`
plus the **bare path of the artifact it was found in**, with **line numbers excluded**.
The preflight scan reports its `source` field as `<artifact path:line>`; the `:line`
suffix is stripped first, and the id is never minted from that raw `source` value. A
line-bearing id would evaporate the moment anyone edited above the finding, taking the
operator's answer with it. With the line excluded, a RED that a later scan re-detects
**inherits its existing id** instead of arriving as something nobody has answered.

## 2. Walk them in one guided pass

Present the enumerated decisions **once**, in one ordered pass, and take an answer for
each. For every item show its `kind`, the artifact it came from, and the exact decision
needed — the same three facts the artifact already carries, so the operator is reading the
run's own record rather than a summary of it.

Do not re-open an item that `.decisions.json` already carries an entry for. Re-asking a
question the operator already answered is the exact failure this surface exists to remove.

## 3. Record the answer, then apply its disposition

Every answer lands in `{workflow.implementation_artifacts}/.decisions.json`:

```json
{"decisions": [{"id": "<the pending item's stable id>",
                "answer": "<what the operator decided, one line>",
                "action": "close|defer"}]}
```

Three keys per entry — `id`, `answer`, `action` — and the action enum has exactly the two
values shown. There is no third one to reach for.

The two dispositions are genuinely different things, not two names for one:

- **`close`** — the decision is made. Apply it immediately, record the entry, and clear
  the artifact that carried it: remove the matching entry from the `reds[]` array of the
  RED sidecar, delete the answered typed escalation sidecar, or mark the ledger row
  resolved. Clearing the RED sidecar is **entry-level removal, never deleting the file** —
  it holds the REDs nobody has answered yet, and deleting it would discard every one of
  them. Leave the raw `.escalation-<story_id>.md` markdown residual alone: it is the only
  evidence that the escalation happened at all, and the session that wrote it is gone.
- **`defer`** — the decision is not made yet. Record the entry **without clearing
  anything**. The artifact stays exactly where it is, the item stays pending, and the next
  preflight still blocks on it. A deferred answer clears nothing, which is what makes it
  honest: it parks a decision, it does not resolve one.

Record each answer and its disposition in `.decision-log.md` as you apply it.

## 4. Hand control back to the existing resume

`/ucg-resolve` defines no resume of its own. Once the pass is done, hand back to the
resume the module already has: **re-enter Execute at the first story whose last verdict is
not advance**; advanced stories are not re-run; and **re-assert** — never rebuild — the
Epic branch, both hooks, the allowlist, and the in-flight story's baseline marker.

That rule is not restated here in a second form. It already lives in the module's Execute
reference and in the parent skill's Resume paragraph, and a second copy would become a
second, divergent rule the first time one of them changed.

There is no other re-entry point. It is not the first story of the Epic, and not the story
the answered decision happened to name — either would re-run stories that already
advanced, which is precisely what the shipped resume rule exists to prevent. The baseline
marker in particular is **re-read, never regenerated**: the in-flight story may already
carry commits, and a regenerated baseline silently re-anchors its evidence range to a
mid-story HEAD.

## Scope

This is a decide-surface, not a runner. It launches nothing itself: it reads artifacts,
records answers, applies what a `close` resolves, and hands off. Like the read-only status
view, it targets the **sequential spine** — under the experimental `--parallel` fan-out each
worktree agent sees its own implementation-artifacts directory, so there is no single set of
pending decisions for this to reconstruct.
