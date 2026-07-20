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

**Every pending item is keyed by a stable `id`.**

**For a preflight RED, read the `id` off the sidecar entry — never re-derive it.** Each
entry in `.preflight-reds.json` carries its own minted `id`, written there by the preflight
that found it (`{skill-root}/references/preflight.md`, step 3). That stored value is the
one the next preflight matches an answer against, so it is the only id that can close the
loop — and because it is stored rather than recomputed, a RED a later scan re-detects
**inherits its existing id** instead of arriving as something nobody has answered. That
holds while the scan restates the decision unchanged; a reworded one is deliberately
treated as a new decision and asked again, which is why an answer you record here is
keyed to the wording the operator actually saw. Re-deriving your own from the entry's other fields would be guesswork against a
recipe run by a different session: the moment your version and the stored one diverge, the
`close` you record names an id no scan ever produces, the RED stands, and the run blocks
forever on a question the operator already answered — while this surface, matching on its
own self-consistent id, never offers it again.

**For a typed escalation sidecar, ask the id layer for the id** — that file is hard-capped
at four fields and cannot carry one, so it is the one case where an id is derived rather
than read:

```
uv run {skill-root}/scripts/red_ids.py --mint-one <kind> <artifact path> <decision_needed>
```

It prints the id and touches nothing. **Never derive an id by hand at either surface.** The
id is the join key between this session and a preflight that ran days ago or will run days
from now, and a value two model invocations have to agree on by hand is a value they will
eventually disagree on. One implementation mints it; both surfaces read it.

Both forms keep **line numbers excluded**: the scan reports `source` as
`<artifact path:line>`, and the id layer strips that `:line` suffix before deriving
anything, so an id is never minted from the raw `source` value. A line-bearing id would
evaporate the moment anyone edited above the finding, taking the operator's answer with it. The id also carries a
digest of the decision itself, which is what keeps it unique: one artifact routinely carries
several findings of the same `kind`, and on `kind` plus path alone they would collide, so
answering one would clear every other decision sharing that id. At this surface that means
an operator sees one question where two were pending, and the one they never saw silently
stops blocking.

## 2. Walk them in one guided pass

Present the enumerated decisions **once**, in one ordered pass, and take an answer for
each. For every item show its `kind`, the artifact it came from, and the exact decision
needed — the same three facts the artifact already carries, so the operator is reading the
run's own record rather than a summary of it.

Do not re-open an item whose `.decisions.json` entry carries an `action` of `close`.
Re-asking a question the operator already **resolved** is the exact failure this surface
exists to remove.

An entry recorded with `action` `defer` is the opposite case: it is a parked question, not
an answered one. Present it again, and replace its entry in place when the operator decides
it. Suppressing a deferred item would deadlock the run outright — `defer` clears nothing,
so the next preflight still blocks on that RED (`{skill-root}/references/preflight.md`,
step 3, drops only the ids whose `action` is `close`), while this surface, the only one that
can answer it, would never ask again. The scan blocks forever on a question the operator is
no longer offered.

## 3. Record the answer, then apply its disposition

Every answer lands in `{workflow.implementation_artifacts}/.decisions.json`:

```json
{"decisions": [{"id": "<the pending item's stable id>",
                "answer": "<what the operator decided, one line>",
                "action": "close|defer"}]}
```

Three keys per entry — `id`, `answer`, `action` — and the action enum has exactly the two
values shown. There is no third one to reach for; in particular, a re-presented `defer` is
answered by **replacing** its entry, not by inventing a third action word for it.

**Write the file read-modify-write, keyed by `id`.** Read any existing `.decisions.json`
first, merge this pass's answers into its `decisions[]` — a new answer for an `id` already
present replaces that entry, every other entry is preserved untouched — and write the whole
array back. The fence above is the shape of the *document*, not a licence to emit only this
pass's answers: a plain overwrite would discard every answer recorded by an earlier pass,
including the `close` entries preflight reads to keep resolved REDs suppressed. Those
decisions would silently return as pending and re-block a run the operator already
unblocked.

**If an existing `.decisions.json` is unreadable, unparseable, or parsed but missing a
list-valued `decisions`, stop — do not overwrite it.** Say which file failed and why. This
is the fail-closed twin of the rule preflight already applies to the same file (an
unparseable suppression file suppresses nothing): here the file is the operator's
accumulated answers, so writing over one we could not read would destroy the record rather
than merely ignore it.

Name the way out in the same breath, because this stop otherwise blocks the only surface
that can unblock the run: the **operator** repairs the file, or moves it aside (to
`.decisions.json.corrupt-<timestamp>`, say), and a fresh pass then starts a new record.
Say plainly that moving it aside discards every answer it held, so the REDs those `close`
entries were suppressing come back as pending and block again. This surface never repairs,
moves, or deletes the file itself — recovering a corrupt record is a judgment call about
which answers are still trustworthy, and that belongs to the person who gave them.

The two dispositions are genuinely different things, not two names for one:

- **`close`** — the decision is made. Apply it immediately, record the entry, and clear
  the artifact that carried it. For a preflight RED, record the entry and then re-apply the
  override through the id layer with `uv run {skill-root}/scripts/red_ids.py --from-sidecar
  --impl-artifacts {workflow.implementation_artifacts}`, which removes it and records the
  closed id in the sidecar's `resolved` audit list. For the other two sources, delete the answered typed
  escalation sidecar, or mark the ledger row resolved. Clearing the RED sidecar is
  **entry-level removal, never deleting the file** — it holds the REDs nobody has answered
  yet, and deleting it would discard every one of them. Let the script do that removal
  rather than editing the file by hand: it is the component that owns these ids, and a
  second writer hand-editing the registry is how the id an answer is keyed to goes missing. Leave the raw `.escalation-<story_id>.md` markdown residual alone: it is the only
  evidence that the escalation happened at all, and the session that wrote it is gone.
  **Closing a `budget-overrun` escalation also resets that story's turn counter** — delete
  `{workflow.implementation_artifacts}/.budget-<story_id>.json`, or set its `turns` to `0`.
  The Stop hook's counter is persistent and monotonic
  (`{skill-root}/scripts/hooks/budget_stop.py` increments it every Stop event and escalates
  once it reaches the ceiling), and no ordinary resume clears it — the Stage 2 arming purge
  (`{skill-root}/references/preflight.md`, step 5) deliberately skips it on re-entry so a story cannot evade its ceiling by stopping and
  resuming. Leave it standing here and the resumed story escalates again on its **first**
  Stop event, before it has done a single turn of the work the operator just authorized, and
  the close would apply in name only. Answering a budget overrun by re-scoping, splitting,
  or handing off the story *is* the operator granting it a fresh budget, so the counter that
  recorded the exhausted one has no claim on the resumed run. This is the one artifact a
  `close` resets beyond the record that carried the decision.
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
