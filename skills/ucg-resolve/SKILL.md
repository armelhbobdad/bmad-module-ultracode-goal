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
`{ucg-root}/references/preflight.md`, step 3, and it is the half that makes this skill
more than a note-taker.

## Conventions

- This skill ships no `scripts/` or `customize.toml` of its own: the scripts,
  `customize.toml`, and `references/` all live in the **parent `ultracode-goal`
  module**. `{ucg-root}` names that module directory —
  `{project-root}/_bmad/ucg/ultracode-goal` in an installed project, or
  `{project-root}/skills/ultracode-goal` in a source checkout of the module itself.
  Resolve it once (first of those two that exists) and qualify every script path with
  it, so `{ucg-root}/scripts/…` and `{ucg-root}/customize.toml` resolve from any cwd.
  It is deliberately **not** `{skill-root}`: this is a top-level skill, so `{skill-root}`
  would resolve to this skill's own directory, which holds none of those files.
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{workflow.implementation_artifacts}` and `{workflow.deferred_work_path}` resolve from
  the parent module's `customize.toml` workflow block (the same scalars the autonomous
  run reads and writes).
- The decision log is canonical memory: record each answer and the disposition applied to
  it as you go. It lives in the run's own folder,
  `{project-root}/_bmad-output/ultracode-goal/<run folder>/.decision-log.md` — the module's
  default runs root, which no `customize.toml` scalar carries. Write to the folder whose
  Epic the enumerated artifacts belong to; ask the operator when more than one could be it,
  and when none exists append nothing rather than create a stray log. Append to it with
  Write/Edit, never a Bash heredoc, as section 3 says, which also covers a log too large to
  Read.

## On Activation

`/ucg-resolve` normally runs **cold** — the operator arrives at a run that stopped, in a
session that never saw it start. That is the whole point of this surface, so resolve the
scalars before reading any artifact. Run `uv run --no-project
{project-root}/_bmad/scripts/resolve_customization.py --skill {ucg-root} --key workflow`
(on failure, merge `{ucg-root}/customize.toml` →
`{project-root}/_bmad/custom/ultracode-goal.toml` →
`{project-root}/_bmad/custom/ultracode-goal.user.toml`, scalars override / arrays append).

That block also carries the module's three universal defaults, and this entry point takes
**one of them**: load `{workflow.persistent_facts}` — read-only context, and a cold session
is the one that most needs it. Do **not** execute `{workflow.activation_steps_prepend}` or
`{workflow.activation_steps_append}`: those are operator-configured actions belonging to the
autonomous run, and a standalone decide-surface stays side-effect-free apart from the answers
it is here to record. `ucg-formalize` and `ucg-status` state the same split, so the three
sub-skills agree on what the shared override file reaches.

If a scalar cannot be resolved, do not pass an unresolved `{…}` token to a path: say
which scalar failed and stop. A decision surface rooted at a path nobody resolved would
enumerate some other run's pending work, or none at all, while looking exactly like a
real answer.

## 1. Enumerate the pending decisions

This surface applies answers and clears artifacts, so it is for a run that has **stopped**.
An operator who only wants to know what is pending gets that from the read-only
`/ucg-status`; begin this pass only when they are here to decide.

Three sources, all on disk. Read these and nothing else — the run's transcript is gone,
and anything not written down is not a pending decision this surface can honor.

1. **The typed escalation sidecars** — `{workflow.implementation_artifacts}/escalation-<story_id>.json`,
   one per escalating story, each a single object with the four string fields `source`,
   `kind`, `decision_needed`, and `evidence`. A sidecar left pending by an earlier run is
   genuinely still pending: the arming step deliberately does not purge `escalation-*.json`,
   so a decision an operator chose to leave open survives to this pass.
2. **The preflight RED sidecar** — `{workflow.implementation_artifacts}/.preflight-reds.json`,
   shape `{"reds": [...]}`. **One** file holds the REDs the last preflight left pending, from
   whichever Epic ran it (section 2 says what that means for an entry no RED carries). There
   is no second RED sidecar and no per-story one: a per-story or per-run RED file would carry
   an id that changed between scans, and an id that changes cannot carry an answer forward.
3. **The deferred-work ledger** — `{workflow.deferred_work_path}`, restricted to its
   `decision:` rows. Those are the rows whose `source` column reads `decision` (as opposed
   to `gate` or `code-review`) **and** whose `status` is still `open`; a row already marked
   `resolved` is not a pending decision. The ledger is a markdown table per Epic: read
   **every** table, not just the first (earlier runs' parked work sits under the earlier
   headings), locate columns by header **name** rather than by position, and let a malformed
   or bullet-list ledger yield no rows here rather than a crash — the same three properties
   the in-repo reader has (`{ucg-root}/scripts/status_render.py`, `ledger_rows()`).

**Every pending item is keyed by a stable `id`.**

**For a preflight RED, read the `id` off the sidecar entry — never re-derive it.** Each
entry in `.preflight-reds.json` carries its own minted `id`, written there by the preflight
that found it (`{ucg-root}/references/preflight.md`, step 3). The id is a pure function of
the decision — its `kind`, the bare artifact path, and a digest of the wording — so a RED a
later scan restates unchanged **inherits its existing id**, and the value on the entry is
the same one the next preflight derives for that finding; a reworded decision derives a new
id and is asked again. Re-deriving your own by hand would be guesswork against a recipe run
by a different session: the moment your version and the derived one diverge, the `close` you
record names an id no scan ever produces, the RED stands, and the run blocks forever on a
question the operator already answered.

**For a typed escalation sidecar, ask the id layer for the id** — that file is hard-capped
at four fields and cannot carry one, so its id is derived rather than read:

```
uv run {ucg-root}/scripts/red_ids.py --mint-one <kind> <artifact path> <decision_needed>
```

For a sidecar the three arguments are its own `kind`, `source` and `decision_needed`
fields, each passed verbatim: `<artifact path>` is the sidecar's `source` field, its
`:line` suffix and all (the id layer strips it), never the path of the sidecar file
itself. The resume also reads a close keyed by the sidecar file's own path as closed,
since earlier passes keyed some that way, but never key an answer by an id minted from
that path: section 2 mints those ids only to recognize an entry already recorded.

It prints the id and touches nothing. **A ledger `decision:` row is keyed by the same
call** — kind `decision`, the ledger path, and the row's reason — because the row's own
`id` column is unique only within its Epic heading, so `d1` under one Epic and `d1` under
another would key to a single entry in a project-wide `.decisions.json` and one answer
would silently suppress a decision the operator was never shown.

**Never derive an id by hand at any of these surfaces.** The id is the join key between
this session and a preflight that ran days ago or will run days from now, and a value two
model invocations have to agree on by hand is a value they will eventually disagree on. One
implementation mints it; every surface reads it.

Every minted form keeps **line numbers excluded**: the scan reports `source` as
`<artifact path:line>`, and the id layer strips that `:line` suffix before deriving
anything, so an id is never minted from the raw `source` value. Why the recipe is shaped
that way — including the digest that keeps two findings of the same `kind` in one artifact
apart — lives in `{ucg-root}/references/preflight.md`, step 3, and in
`{ucg-root}/scripts/red_ids.py`.

## 2. Walk them in one guided pass

Present the enumerated decisions **once**, in one ordered pass, and take an answer for
each. For every item show its `kind`, the artifact it came from, and the exact decision
needed — the same three facts the artifact already carries, so the operator is reading the
run's own record rather than a summary of it.

Do not re-open an item whose `.decisions.json` entry carries an `action` of `close`.
Re-asking a question the operator already **resolved** is the exact failure this surface
exists to remove.

An entry recorded with `action` `defer` is the opposite case: it is a parked question, not
an answered one. Present it again while an item this pass enumerated carries its `id`, and
replace its entry in place when the operator decides it, carrying its answer forward
(section 3). Suppressing a deferred item would deadlock the run outright: `defer` clears
nothing, so the next preflight still blocks on that RED
(`{ucg-root}/references/preflight.md`, step 3, drops only the ids whose `action` is
`close`), while this surface, the only one that can answer it, would never ask again. The
scan blocks forever on a question the operator is no longer offered.

An entry with no `action`, or with an `action` that is neither `close` nor `defer`, is
pending as well while an item this pass enumerated carries its `id`. An earlier version of
this surface wrote some entries that way, and preflight drops none of their ids, so that
item's question stays open. Present it again, as you present a deferred one.

**An item carries an entry's `id` only on an exact match, as written.** A RED carries the
`id` on its `reds` entry, and a ledger `decision:` row the id the id layer printed for it.
An escalation sidecar carries the id the id layer printed from its own fields, and one
more for each spelling of the sidecar file's own path the resume reads a close by
(`_sidecar_ids` in `{ucg-root}/scripts/preflight_check.py`): its path relative to
`{project-root}`, its absolute path, that absolute path with its folder's symlinks
resolved, and the resolved path relative to `{project-root}`, each written with forward
slashes and, on Windows, with backslashes too. Ask the id layer for each of those with the
sidecar's own `kind` and `decision_needed`. Mint them only to recognize an entry already
recorded, never to key an answer: an entry keyed by any of them belongs to that sidecar's
item.

When an item you present already has an entry, show its `answer`, and each earlier answer
its `history` holds (section 3), beside the decision needed. Such an answer can hold the
operator's whole ruling: they decide on the record as it stands, and may find it already
answers the question.

**An entry no enumerated item carries is orphaned, not pending.** That is an entry whose
`action` is anything but `close` and whose `id` no item of this pass carries: none of the
three sources holds its question at this pass, so there is no item to present it with.
List the orphaned entries after the pending items, apart from them, each with its `id`,
its `answer` and each earlier answer its `history` holds, and ask nothing about them; the
record keeps each one as it stands. Say beside that list that a later preflight can raise
an orphaned entry again and block on it. `.preflight-reds.json` is one project-wide file
that each preflight replaces, so it holds only the REDs of the last preflight, from
whichever Epic ran it: a RED one Epic's preflight raised can be gone from it after another
Epic's preflight, while that first Epic's next preflight can raise it again. An orphaned
entry whose `id` a later RED, sidecar or ledger row carries is pending again at that pass,
which asks it.

**When a source could not be read in full, call nothing orphaned.** That is an unreadable
`.preflight-reds.json`, an escalation sidecar that cannot be read or whose fields no id can
be minted from, or a ledger on disk that cannot be read, or is malformed or a bullet list,
so it yields no rows here. In that case present every entry that is not a `close` as
pending, with its `id`, its `answer` and its `history`, since an id that source would carry
cannot be ruled out.

## 3. Record the answer, then apply its disposition

Every answer lands in `{workflow.implementation_artifacts}/.decisions.json`:

```json
{"decisions": [{"id": "<the pending item's stable id>",
                "answer": "<what the operator decided, one line>",
                "action": "close|defer",
                "history": [{"answer": "<an answer this entry replaced, verbatim>",
                             "action": "<that answer's action, when it had one>"}]}]}
```

**Write the file read-modify-write, keyed by `id`.** Read any existing `.decisions.json`
first, merge this pass's answers into its `decisions[]` (a new answer for an `id` already
present replaces that entry and carries its answer forward, as the next paragraph says;
every other entry is preserved untouched), and write the whole
array back. The fence above is the shape of the *document*, not a licence to emit only this
pass's answers: a plain overwrite would discard every answer recorded by an earlier pass,
including the `close` entries preflight reads to keep resolved REDs suppressed. Those
decisions would silently return as pending and re-block a run the operator already
unblocked.

**A replacement never drops an earlier answer.** When a new answer replaces the entry for
its `id`, the new entry carries that entry forward in `history`: copy the replaced entry's
`history` list as it stands, then append the replaced entry itself, with every field but
`id` and `history` copied verbatim (its `answer`, and its `action` when it had one). When
the file holds more than one entry for that `id`, carry each forward, in file order, and
write one entry in their place. Leave `history` off an entry that replaced nothing. A pass
that only parks an item records one line, while the entry it replaces can hold the
operator's whole ruling: a plain replacement would erase that ruling, and nothing in the
pass would report the loss. Every reader of the file but one keys on `id` and `action` alone
(`{ucg-root}/scripts/red_ids.py`, which preflight and the resume read it through), so
`history` changes no suppression. The one is the gate's re-read of rulings at the start of
each cycle (`{ucg-root}/references/gate.md`, "An owned `gate-gap:` line is not this
story's to close"), which reads the `answer` and the `history` of each `close` entry and
applies only the latest ruling for each line or AC: a later return or reassignment
replaces an earlier one.

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
  override through the id layer with `uv run {ucg-root}/scripts/red_ids.py --from-sidecar
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
  (`{ucg-root}/scripts/hooks/budget_stop.py` increments it every Stop event and marks
  the story once it reaches the ceiling), and no ordinary resume clears it — the Stage 2 arming purge
  (`{ucg-root}/references/preflight.md`, step 5) deliberately skips it on re-entry so a story cannot evade its ceiling by stopping and
  resuming. Leave it standing here and the resumed story escalates again at the resume's
  step-0 ceiling check, before it has done a single turn of the work the operator just authorized, and
  the close would apply in name only. Answering a budget overrun by re-scoping, splitting,
  or handing off the story *is* the operator granting it a fresh budget, so the counter that
  recorded the exhausted one has no claim on the resumed run.
  **Closing an `operator-evidence-owed` escalation needs the evidence on disk.** Read the
  live results file its `decision_needed` names and confirm a `status` `pass` record for
  every AC it lists, made at the commit it names. Those are the story's
  `**Gate-ability:** operator-evidence` ACs; a plain `operator` tag is work the dev agent
  builds, never evidence this close waits on. If one is missing, say which and record
  `defer`. An AC the operator moves out of the story in writing needs no record, and the
  close waits for the move instead: the story file must carry it in the moved-AC form
  (`{ucg-root}/references/gate.md`, "A moved AC leaves the story's list"), its number
  starting no item under `## Acceptance Criteria` and a note under an H2 heading of its own
  after that section naming that number, the owner and the ruling. Until it does, record
  `defer`. When it does, write `{workflow.implementation_artifacts}/.moved-<story_id>`,
  one line per AC it moves, opened by its `AC-<n>`, `AC-<n> to <owner> per <ruling>`,
  adding to any lines already there, and an `oracle=<absolute path>` line for each oracle
  source the operator edited with the move (a relative one resolved against
  `{project-root}`, and only a path inside the work tree `git rev-parse --show-toplevel`
  prints); log each open `gate-gap:` line on the moved AC again, under the story's key,
  with `owned-by` the same owner per the same ruling; and log the move in the story's
  `.decision-log.md` entry as a `moved:` line, which records it for a reader and which no
  step reads. A written return of a moved AC to the story is applied here too, as
  `{ucg-root}/references/gate.md`, "A moved AC leaves the story's list", says: its line
  leaves the record, and the record goes once no AC line is left. A decomposed child's AC
  is not moved this way: it lives in its parent's story file, which is never edited and
  which every sibling reads; record `defer` and propose a re-plan of the split instead. An
  escalation whose `decision_needed` opens with "The moved-AC check refused (exit 1)"
  closes, its moved ACs owing no record, only once the operator states in writing that
  each source it names no longer lists the AC for this story and you have added each
  source they edited inside the work tree to `.moved-<story_id>` as an `oracle=<absolute
  path>` line, or once they return the AC in writing; until then record `defer`. One that
  opens with "The moved-AC check refused (exit 2)" closes at once when it is the story's
  first exit-2 refusal at that commit; when it says one came before at that commit, it
  closes only once the operator confirms in writing that trace can write its files there,
  and until then record `defer`. An AC the escalation names as partly recorded, with the
  ids of the records TEA
  already counted for it, closes only on a `pass` record at that commit whose `id` is not
  among the ones the escalation names, or on the operator's written narrowing or move of
  the AC: the records already counted are not enough, since re-gating them changes
  nothing. This surface never writes a record itself: the operator is its producer
  (`{ucg-root}/references/gate.md`, "Operator evidence is a recorded live result"). A
  ruling that narrows or moves the AC is the operator's story edit: record it, naming each
  AC a move retires, then close.
  **That close also writes the story's re-gate marker and resets its turn counter.** Write
  `{workflow.implementation_artifacts}/.regate-<story_id>` as two lines, `sha=` the
  assessed commit the sidecar names (in full, as `git rev-parse` prints it) and
  `decision=` the id you closed, then delete the sidecar as for any close, and delete `{workflow.implementation_artifacts}/.budget-<story_id>.json`: waiting for operator
  evidence is not the story's work. The marker is the re-gate entry. While its `sha=`
  names `HEAD`, the resume's `--assert-armed` call routes the story `gate-owed`, so it
  re-enters at Stage 5 to re-gate that commit, and is never re-driven from step 0, where
  the turn-ceiling read could escalate it and a commit past the assessed one would make
  the records stale (`{ucg-root}/references/execute.md`, the resume rule). The gate
  deletes the marker once the re-gate's verdict is logged.
  **Closing an `evidence-commit-rejected` escalation makes no commit.** Record the
  operator's answer (the hook fixed or reconfigured, or the file it named changed by them),
  then delete only the sidecar. Leave the staged evidence and
  `{workflow.implementation_artifacts}/.evidence-owed-<story_id>` alone, even when the
  answer is to commit as it stands: the resume makes that commit under the gate's hook rule
  and removes the marker (`{ucg-root}/references/gate.md`, "Commit the gate's evidence
  before the next story starts"), on the Epic's last story too, where every row already
  reads `done` and the resume re-enters only for that commit before Finalize.
  **Closing a `coupled-stories` escalation records a proposed move, and the resumed run
  makes it; a re-plan is the operator's own edit.**
  The sidecar proposes moving clauses the earlier story owes to the later story it
  names, which narrows the earlier story's AC, or it proposes only a re-plan, where no
  move fits: the later story is outside the run's scope, the two stories are a pair no
  move applies to (a decomposed child beside a story that has a file, or children of two
  parents), or an AC between two decomposed children holds a clause no run measured
  (`{ucg-root}/references/execute.md`, "Two stories green only together"). When the
  operator approves a proposed move, as proposed or
  reworded, write the sidecar's `decision_needed` verbatim into this answer's
  `.decision-log.md` entry, under both story keys it names, beside the operator's answer
  and the id you closed, before you delete the sidecar: once the sidecar is gone, that
  entry is the only copy of the move the resumed run writes into both story files, or for
  two decomposed children into every record of their split (the split record, both child
  rows in `sprint-status.yaml`, the earlier child's ATDD checklist and the later child's
  when it has one). This
  surface edits neither story file and moves no test case: the ruling is the operator's,
  and the resumed run applies it before the earlier story's next commit. An answer that
  re-plans the rows instead (one story in place of the two, or another order) is the
  operator's own edit of `sprint-status.yaml` and the story files: record `defer` until
  they have made it, then `close`. A sidecar that proposes only a re-plan has no move for
  this surface to record or for the resumed run to apply, so whatever the operator rules
  for it is their own edit of those files: record `defer` until they have made it, then
  `close`.
- **`defer`** — the decision is not made yet. Record the entry **without clearing
  anything**. The artifact stays exactly where it is, the item stays pending, and the next
  preflight still blocks on it.

Record each answer and its disposition in `.decision-log.md` as you apply it, with
Write/Edit and never a Bash heredoc. A heredoc puts decision prose (commit and push verbs,
backticked names, apostrophes) into a Bash command string, and the PreToolUse guard's git
gates read that string as commands (`{ucg-root}/references/execute.md`, step 4, gives the
reason). Once the log is too large to Read affordably, do not Read it, since both file
tools refuse a file this session has not Read. Write the entry instead to a new file beside
the log, `{project-root}/_bmad-output/ultracode-goal/<run folder>/dlog-slice-resolve-<n>.md`,
with `<n>` one past the highest number a `dlog-slice-resolve-*.md` in that folder already
carries (`1` when there is none): the name has to be new for every append, or Write finds
the file on disk and asks for the Read again. Then append it in one Bash call, with both
paths in full:
`cat "{project-root}/_bmad-output/ultracode-goal/<run folder>/dlog-slice-resolve-<n>.md" >> "{project-root}/_bmad-output/ultracode-goal/<run folder>/.decision-log.md"`.
Keep the slice rather than deleting it: it is the only copy of the entry if the append is
interrupted. This holds for every entry the pass writes, the coupled-stories entry above
included.

## 4. Hand control back to the existing resume

`/ucg-resolve` defines no resume of its own. Close the pass by stating what closed, what is
still pending, and that anything still pending re-blocks at the next preflight. Name every
entry this pass replaced, by `id`, with the earlier answer it carried into `history`, so
the operator sees what the record held before this pass. List the orphaned entries apart
from both, by `id`, and say that a later preflight can raise any of them again and block
on it, and that the pass after that preflight asks it. **Hand back
only when the pass closed at least one item, or when the operator asks for the resume**: a
pass that deferred everything hands into a run blocked on the identical items, and an empty
enumeration means the run stopped for a non-decision reason — say so, point at the read-only
`/ucg-status`, and hand nothing back. A pass that found only orphaned entries is not an
empty enumeration, so do not say the run stopped for a non-decision reason: the run can
have stopped on a RED that another Epic's preflight has since dropped from
`.preflight-reds.json`, and its next preflight raises that RED again. Such a pass closed
nothing, so point at the read-only `/ucg-status`, as for an empty enumeration, and hand
back only when the operator asks for the resume.

Otherwise hand back to the resume the module already has, which **routes by the last stage
the blocked run reached**, not by story. Which branch applies is not a detail this surface
may skip, because the two arrive from different places:

- **Blocked at Stage 1 or Stage 2** — epic unresolved, or a preflight RED, which is the
  arrival this skill's own trigger advertises. Re-run **from that stage**, so the hard
  preflight gate is never skipped and the answered RED is consumed by the scan that
  applies the override. Such a run blocked before any story, so it carries no gate
  verdicts and there is no story to re-enter at.
- **The log carries gate verdicts** — re-enter Execute at the first story whose last
  verdict is not advance; advanced stories are not re-run. Within that branch there is
  no other re-entry point: it is not the first story of the Epic, and not the story the
  answered decision happened to name, either of which would re-run stories that already
  advanced, which is precisely what the shipped resume rule exists to prevent. When every
  story advanced and a story's `.evidence-owed-<story_id>` is on disk, the resume drives no
  story: it makes that story's owed evidence commit and goes to Finalize.

Either branch **re-asserts** — never rebuilds — the Epic branch, both hooks, the
allowlist, the `.mem-state.json` recall latch, and the in-flight story's baseline marker.
The latch belongs on that list here more than anywhere: this skill is reached from a
blocked run, which removed its latch at its last exit (Stage 6, or preflight step 4's
STOP) with `mem_recall.py unlatch`, so the resume writes a fresh one under its own run
id, never the blocked run's. The baseline marker splits on whether
`.baseline-<story_id>` exists: mid-story it is **re-read, never regenerated** — the story
may already carry commits, and a regenerated baseline silently re-anchors its evidence
range to a mid-story HEAD — while at a story boundary there is none to re-read and one is
written fresh at `HEAD`, which is the half the Execute reference owns.

What this section pins is the routing branch and the re-assert set, nothing further. The
rule itself already lives in `{ucg-root}/references/execute.md`'s resume paragraph and in
the parent skill's Resume paragraph, which are loaded at hand-back time and carry the
current script call and both halves of that split. Where those two and this one ever
disagree, they are the owners and this is the stale copy.

## Scope

This is a decide-surface, not a runner. It launches nothing itself: it reads artifacts,
records answers, applies what a `close` resolves, and hands off. Like the read-only status
view, it targets the **sequential spine**, which is the only execution path.
