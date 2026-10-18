---
name: ucg-formalize
description: Opt-in standalone readiness verdict for one BMAD Epic via the `/ucg-formalize <epic>` trigger. Runs the formalize_check.py kernel, auto-remediates machine-derivable gaps, delegates judgment to one throwaway subagent, and emits the canonical five-key headless envelope. Use when an operator asks to "formalize an epic", "check epic readiness", or runs `/ucg-formalize`.
---

# UCG Formalize

## Overview

`/ucg-formalize <epic>` is the **opt-in, operator-on-demand** readiness verdict for a
single BMAD Epic — the thin LLM layer over the readiness kernel
(`scripts/formalize_check.py`). It adapts the kernel's graduated verdict
(ready / remediable / blocked) into the canonical five-key headless envelope; it never
recomputes the readiness verdict. Each verdict and remediation lands in
`.decision-log.md`.

## Conventions

- This skill ships no `scripts/` or `customize.toml` of its own: the kernel
  (`formalize_check.py`, `headless_envelope.py`), `customize.toml`, and `references/`
  all live in the **parent `ultracode-goal` module**. `{ucg-root}` names that module
  directory — `{project-root}/_bmad/ucg/ultracode-goal` in an installed project, or
  `{project-root}/skills/ultracode-goal` in a source checkout of the module itself.
  Resolve it once (first of those two that exists) and qualify every script path with
  it, so `{ucg-root}/scripts/…` and `{ucg-root}/customize.toml` resolve from any cwd.
  It is deliberately **not** `{skill-root}`: this is a top-level skill, so `{skill-root}`
  would resolve to this skill's own directory, which holds none of those files.
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{workflow.implementation_artifacts}`, `{workflow.tea_config_path}`,
  `{workflow.trace_output_dir}` (step 2's leaked-TEA destination) and
  `{workflow.deferred_work_path}` resolve from the parent module's `customize.toml`
  workflow block (the same path scalars the autonomous run reads).
  `{planning_artifacts}` is not a workflow scalar — it resolves from BMad
  core `config.yaml` (root + `bmm` section), mirroring the parent SKILL.md, and is not
  part of the customize override surface.
- **Of the three universal `[workflow]` defaults, this entry point loads one and runs
  neither.** `persistent_facts` **is** loaded: it is read-only context, and a cold
  standalone verdict is exactly the session that has none. `activation_steps_prepend` and
  `activation_steps_append` are **not** executed here — they are operator-configured
  actions belonging to the autonomous run, and the standalone surfaces stay thin and
  side-effect-free. `ucg-resolve` and `ucg-status` state this same split, so the three
  agree; `ucg-status` in particular could not honor it otherwise, having promised to write
  nothing at all.
- The decision log (`.decision-log.md`) is canonical memory: record the verdict and
  every auto-remediation as you go. It lives in the Epic's run folder under
  `{project-root}/_bmad-output/ultracode-goal/`: reuse the newest `epic-<id>-*` folder
  for this Epic when one exists (appending a session entry), otherwise create
  `epic-<id>-<UTC yyyymmddThhmmssZ>` for this standalone check. That resolved path is
  what the Headless `decision_log` key carries, so two invocations over the same Epic
  cannot scatter their verdicts across two files.

## On Activation

`/ucg-formalize` can run cold (outside an active `ultracode goal` run), so resolve the
scalars this skill consumes — the step-1 kernel's *and* step 2's
`{workflow.trace_output_dir}` — before calling the kernel, against the **parent** module,
so they are the same path scalars the autonomous run reads. Run `python3
{project-root}/_bmad/scripts/resolve_customization.py --skill {ucg-root} --key workflow`
(on failure, merge `{ucg-root}/customize.toml` →
`{project-root}/_bmad/custom/ultracode-goal.toml` →
`{project-root}/_bmad/custom/ultracode-goal.user.toml`, scalars override / arrays append),
and load `{planning_artifacts}` from `{project-root}/_bmad/config.yaml` (root + `bmm`
section). If they cannot be resolved, do not pass unresolved `{…}` tokens to the kernel
or to a step-2 file move (a move into a literal `{workflow.trace_output_dir}` directory
would log as a successful remediation the kernel re-run can never see):
record a blocked verdict and push a non-remediable blocker — `source` the unresolved
config path, note "customization/config scalars unresolved" — into step 4's ordered
blocker list, so the Headless `reason` renders.

## 1. Run the readiness kernel

Resolve the Epic id `<id>` the operator named, then run the readiness kernel — qualified
by `{ucg-root}` so it resolves from any cwd:

```
uv run {ucg-root}/scripts/formalize_check.py --epic <id> --project-root {project-root} --planning-artifacts {planning_artifacts} --impl-artifacts {workflow.implementation_artifacts} --tea-config {workflow.tea_config_path}
```

Read the kernel's readiness verdict JSON from stdout. Its shape is
`{ready, verdict, mechanical_budget, judgment_required, mechanical_gaps[], judgment_candidates[], judged_candidates[], scan, checks{}}`;
`judged_candidates[]` is empty and `scan` is `null` until step 3's re-run passes `--scan`.
`checks.decomposed_children` lists each story key the kernel read as a decomposed child,
with the parent story file its criteria come from and the parent's row (`null` when the
split removed it). It gates nothing: a story inserted above a `done` parent's row reads
the same way, so record it in `.decision-log.md` with the verdict, one line per key and
its parent file, and outside `-H` name it to the operator with the verdict.
Do not recompute it: read `mechanical_budget` and the verdict off the JSON, never re-derive
them here. There is one kernel — a second readiness evaluator would let the two callers
drift.

The kernel is fail-closed: a missing / unreadable / ambiguous artifact is recorded
as a failing gap, never a neutral pass.

## 2. Mechanical auto-remediation pass

Iterate the kernel's `mechanical_gaps[]` and apply the machine-derivable fix for
each entry where `remediable: true`. The remediation per kind:

- **`leaked_tea_artifact`** — move the TEA artifact from the source/impl tree to the
  `{workflow.trace_output_dir}` root and re-point any reference to it. A path move is
  meaning-preserving. Verify identity before moving: a non-TEA false positive is
  archived *out of* the impl-artifacts scan tree — never into the trace dir (that
  misfiles it) and never left in place (an uncleared remediable gap keeps the verdict
  off `ready`).
- **`orphaned_index`** (regenerable story/AC) — regenerate the missing story or AC
  stub via `ucg-create-story` so the cited id resolves.
- **`missing_planning_artifact` / `missing_impl_artifact`** — backfill the
  regenerable scaffold (a PRD/ADR stub, the `sprint-status.yaml` rollup via
  `bmad-sprint-planning`).
- **`ac_missing_named_verification` / `ac_missing_anti_vacuous_twin`** — backfill the
  canonical named-verification / anti-vacuous-twin / gate-ability scaffold derivable
  from the AC shape.
- **`story_keys_uncovered` / `story_without_ac`**: run the `ucg-create-story` scaffold
  for the story keys the gap's `detail` names: `story_keys_uncovered` lists the unresolved
  subset, and `story_without_ac` names the one story whose AC section is missing. A
  decomposed child is never scaffolded: it has no story file by design, and the kernel
  already counts it covered by its parent's file when its row sits above the parent's
  row and the parent row is `done`, or when the split removed the parent's row. So a
  listed key whose id extends a parent's (`95-0-a-i` of `95-0-a`) is a story of its own,
  or a child the kernel found under a parent row that is not `done` or below a `done`
  parent's row (the `detail` names each key below a `done` parent's row, with that row;
  for a parent row that is not `done`, find the parent from the key's id). The split
  is recorded when its split record (`.split-<parent key>.json` beside
  `sprint-status.yaml`, which `{ucg-root}/scripts/story_sizing.py --record` writes)
  names the child, the child's row cites the parent ACs it claims, or
  `.decision-log.md` names the parent and the ACs each child claims
  (`{ucg-root}/references/execute.md`'s decomposition conventions write all three).
  When it is recorded, the parent's status, the child's place or both break those
  conventions: in this same pass, set the parent's row to `done` and move each child's
  row above the first row of the parent's stem, and scaffold nothing. A split recorded
  only by the row citation or the decision log also gets its split record in this
  pass, or the Epic-level roll-up refuses the parent: one `story_sizing.py` run with
  `--parent` and `--record {workflow.implementation_artifacts}`, the parent's ACs and
  one `--child` per child row with the ACs it claims. A run that does not exit 0
  writes none: record that in `.decision-log.md` with what the script printed (its
  `unclaimed`, `double_claimed` and `unknown_claims` on exit 1, the usage error on
  exit 2), and name it to the operator outside `-H`.
  When no split is recorded, the key shape alone proves nothing (a `3-2a` added after
  `3-2` shipped sits below its row, and an inserted `3-2a` beside an in-progress `3-2`
  is its own story too): scaffold it like any other key, and never set a row `done` or
  move one to clear the gap.
- **`no_in_scope_stories`** — same scaffold, but this gap's `detail` names only the Epic
  and the artifacts directory, never a key list, so take the keys from the **sprint
  rollup's rows for this Epic** instead of trying to read them out of `detail`. First
  discriminate on the input: when the Epic id matches **no row at all** in the rollup,
  that is a mistyped or unseeded Epic, not a gap to scaffold over — record it as a
  non-remediable blocker and route to `status=blocked` rather than authoring stories for
  an Epic nobody planned.
- **`blank_pxi_score`** — write the gap's own `recomputed` value into the blank Score
  cell at its `source` line. Use the value the kernel supplies; never re-derive the
  product here, which would be a second multiplier free to disagree with the first.

The kernel emits **ten** `remediable: true` kinds and the list above covers all ten. A
`remediable: true` kind that is nonetheless *not* listed here is never improvised from
its `detail`: record it as a non-remediable blocker naming the kind and route to
`status=blocked`. That clause is what keeps this list honest as the kernel grows — a new
kind blocks loudly instead of being guessed at, and the halt catch-all below then covers
the never-remediated case as well as the remediated-but-unfixed one.

Log each remediation to `.decision-log.md` as you apply it. Never
auto-remediate a `judgment_candidate`, and never auto-remediate a
`remediable: false` mechanical gap (an unreadable artifact cannot be fixed from its
own unreadable content).

**Re-run the kernel** (step 1) after the remediation pass so `mechanical_budget`
reflects the fixes: the remediate-then-re-run loop. Step 3 is seeded from this
re-run's `judgment_candidates[]`, whose lines are the lines as remediation left them, and
step 4 maps the verdict of step 3's own re-run on the answered scan.

**Remediation halt catch-all.** If a remediation sub-skill itself fails, is not installed
(the Skill tool does not know its name), or blocks on interactive input, do not re-invoke
it blind: record a non-remediable gap naming the sub-skill and the exact input it needed,
and let the verdict mapping route the run to `status=blocked`. A `ucg-create-story` that
is not installed means a partial or older UltraCode Goal install (its installer copies the
skill beside the ultracode-goal skill): name the operator's fix, run from the project root:
`npx bmad-module-ultracode-goal update`, or `install` where UCG was never installed. Never
substitute another skill (`bmad-build`, `bmad-build-auto`, or BMAD's deprecated
`bmad-create-story`) or write the story file or its acceptance criteria by hand.
Likewise cap the loop at one pass per gap: if a kernel re-run still
reports a gap whose `kind`+`source` a prior pass already remediated, the fix did not take —
record it as a non-remediable blocker and route to `status=blocked` rather than re-entering
step 2, so the remediate-then-re-run loop always converges instead of spinning silently.

## 3. Judgment subagent (exactly one)

Spawn **exactly one throwaway subagent** to read the judgment candidates; a second pass
would double-judge the same candidates, so never two. Seed the subagent with the
post-remediation kernel's `judgment_candidates[]` list (step 2's re-run), each candidate's
`id`, `source` and `why_machine_cannot_decide` (the reason tells apart two candidates the
kernel flags on one line), as targeted hypotheses
to confirm (it confirms the flagged sources, it does not scan blind), plus the artifact
paths. The corpus stays in the
subagent's discarded context (zero-net-context) — this layer holds only the returned findings.

The kernel only *flags*; the subagent *decides*. It must **confirm-or-clear** each seeded
`judgment_candidate` into `reds` or `concerns`, never recording one as a RED unprompted,
and the entry that answers a seeded candidate carries that candidate's `id`, copied as
given, in its `candidate` field, and its `source`, copied as given, in `source`: that pair
is how step 3's kernel re-run knows it was judged.
Fail-closed: a `judgment_candidate` the subagent can neither confirm nor clear **defaults
to RED** (JUDGMENT), mirroring `gate_eval.py`'s `nfr_status is None → failing` and the
identical rule the spine's scan carries (`{ucg-root}/references/preflight.md`, second hypothesis
stream). Without it a candidate the subagent simply does not return on is neither red nor
concern, and silently vanishes into an accept — which would make this standalone pass
fail-open exactly where the spine's is fail-closed, and contradict the kernel's own
fail-closed contract stated in step 1. **This rule binds the degraded inline read below
too**: losing the subagent costs the zero-net-context property, never the fail-closed one.

The subagent must return **only this object** — the live three-key contract the parent
`{ucg-root}/references/preflight.md` semantic scan uses — no prose, no document quotes beyond the
one-line evidence fields:

```json
{"reds": [{"source": "<artifact path:line>",
           "kind": "undecided-product|undecided-architecture|contradiction|undefinable-done",
           "decision_needed": "<the exact decision a human must make>",
           "evidence": "<one quoted line>",
           "candidate": "<only when this answers a seeded judgment candidate: its id, copied as given>"}],
 "concerns": [{"source": "<artifact path:line>", "note": "<cosmetic / non-blocking gap, one line>",
               "candidate": "<only when this answers a seeded judgment candidate: its id, copied as given>"}],
 "advisories_checked": [{"sig": "<advisory id>", "status": "recurred|not-observed|unknown"}]}
```

**Mint ids before mapping, and apply the operator's closes.** Hand the returned scan
object — the degraded inline read below yields the same object — to the same id layer the
spine runs (`{ucg-root}/references/preflight.md`, step 3), in report-only mode:

```
uv run {ucg-root}/scripts/red_ids.py --scan - --impl-artifacts {workflow.implementation_artifacts} --dry-run
```

It mints each red's stable id and drops every red whose id an operator already closed in
`{workflow.implementation_artifacts}/.decisions.json`, so a decision answered through
`/ucg-resolve` does not re-block this surface at every invocation. Never mint, compare, or
edit an id by hand, and a non-zero exit clears nothing: every scanned red stands.
`--dry-run` is deliberate — `.preflight-reds.json` is the autonomous run's durable
registry and a standalone readiness check must not overwrite it, which also means a red
found only here is not answerable through `/ucg-resolve` until an autonomous preflight
records it.

Any surviving `reds` entry maps to `status=blocked`. Record each red with its minted id,
its source, and the exact decision needed in `.decision-log.md`, and each seeded candidate
the subagent cleared with its source and the concern's note: a clearing is what lets the
re-run below read `ready`. A purely cosmetic gap belongs in `concerns`, never red.

**Then re-run the kernel on the answered scan.** Step 1's verdict counts every judgment
candidate as still owed, so it reads `blocked` whenever the kernel flagged one. Pass the
same scan object to the kernel with the step-1 arguments plus `--scan -` (the object on
stdin), as the spine does (`{ucg-root}/references/preflight.md`, step 3):

```
uv run {ucg-root}/scripts/formalize_check.py <the step-1 arguments> --scan -
```

A candidate is judged (`judged_candidates`) when an entry carries its `id` in
`candidate` and its `source` as seeded, and then it no longer sets `judgment_required`;
one no entry answers keeps the verdict `blocked`, the fail-closed default above. An
entry whose pair names no candidate judges nothing, and a scan the kernel cannot read, or
one `red_ids.py` refuses, judges nothing. This re-run's verdict is the one step 4 maps.

**If subagent spawning is unavailable** (wrong runtime, quota exhausted, or the spawn
errors), do not dead-end the verdict: read the kernel's flagged candidates inline in the
current context (accepting the context cost; only the zero-net-context property is lost)
and build the same scan object, each answer carrying its candidate's `id` and `source`.
Then run the id layer and the kernel re-run above on it, as for a subagent's object,
before the verdict mapping: losing the subagent skips neither.

## 4. Verdict mapping

Map the kernel verdict of step 3's re-run on the answered scan, plus the subagent reds,
to the headless status by
this deterministic decision-list; `remediable` is an internal loop state, never a headless
emit value.

| Condition | Route | Headless status |
|-----------|-------|-----------------|
| re-run kernel `verdict == ready` (`mechanical_budget == 0`, every judgment candidate answered) AND no reds | accept | `status=complete` |
| `mechanical_budget > 0`, all gaps remediable, no reds (verdict remediable) | remediate-then-re-run (step 2), re-run the kernel with the same scan object (`--scan -`; the judgment pass is not spawned again), then re-map | (loops; never emits `remediable`) |
| any red OR any non-remediable mechanical gap OR any artifact the kernel could not read | reject | `status=blocked` |
| re-run kernel `verdict == blocked` with a judgment candidate no scan entry answered, whatever the budget | reject | `status=blocked` |
| re-run kernel verdict unreadable, absent, or none of `ready`, `remediable`, `blocked` | reject | `status=blocked` |

**The loop row keeps the scan.** A second remediation can move a seeded candidate's line,
and its answer then no longer matches: that candidate reads as unanswered and the
unanswered-candidate row rejects, fail-closed. Invoking `/ucg-formalize` again seeds a
fresh scan from the new lines.

**The unanswered-candidate row is why this list is total.** A candidate the subagent did not answer is
the fail-closed default of step 3, a RED nobody judged, but it reaches this mapping only
as the kernel's `judgment_candidates`, not as a red, so without this row it would satisfy
neither the accept row (the kernel did not say `ready`) nor the first reject row. Its
blocker list is those candidates, each by `source`, with `decision_needed` naming that the
kernel flagged it and the judgment pass left it unanswered. A candidate the subagent
cleared into `concerns` is judged, and the re-run no longer counts it, so clearing every
flagged candidate reaches the accept row.

**Row 1 is keyed on the kernel's own verdict word, never on the budget alone.** The two
are not equivalent: `formalize_check.py` sets `verdict = "blocked"` whenever
`judgment_required` is true, *independent of* `mechanical_budget`, and step 2 never
removes a judgment candidate (it is forbidden to remediate one). So budget `0` with zero
reds is reachable while the kernel still reads `blocked`, whenever a flagged candidate
went unanswered or the kernel could not read the scan. Keying the accept row on the
budget would route that state to `complete` and hand back a ready verdict the kernel
never gave. The budget and reds clause is the *explanation* of a ready verdict, not the
test for one.

An artifact the kernel could not read is fail-closed to `status=blocked` (mirroring
`gate_eval.py`'s `nfr_status is None -> failing` read), never treated as neutral —
formalize's `blocked` is a deliberate strengthening over gate_eval's reloop.

For a blocked envelope, assemble the **ordered blocker list**: confirmed reds, then
non-remediable mechanical gaps, then judgment candidates no scan entry answered, each
group in `source` (`path:line`) order, or the unreadable verdict itself when that is the
row that applied. Hand it to the blocked adapter (see Headless), which renders `reason`
positionally from it.

## Headless

With `-H`, run non-interactively and emit exactly one object at the single exit point.
This is the canonical five-always-present-key envelope — byte-identical to the
autonomous parent `SKILL.md` shape: `skill` is the constant `ultracode-goal` (never
`ucg-formalize`), and the script-layer keys (`verdict`, `mechanical_budget`) never leak
into the envelope.

Serialize through the one shared module `{ucg-root}/scripts/headless_envelope.py` — the
same definition `{ucg-root}/references/preflight.md` and `{ucg-root}/references/finalize.md` use — so this entry
point and the autonomous run cannot serialize the same verdict differently. The module
exposes **two** entry points, and they are **picked by shape, never by name**:

| Path | Entry point | Argument |
|------|-------------|----------|
| accept (`status=complete`) | `build_complete_envelope(<decision-log path>)` | no blocker list; `report=` / `deferred_work=` when those artifacts exist |
| reject (`status=blocked`) | `build_headless_envelope(<ordered blocker list>, <decision-log path>)` | the step-4 ordered blocker list |

`build_headless_envelope` reads like the general adapter and is not: it is the **blocked**
one, which is why it is also exported as `build_blocked_envelope` — the name to read for.
Handing it a complete-shaped mapping now raises `ValueError`; before it raised, it read no
blockers, *synthesised* one, appended that fabrication to `.decision-log.md`, and wrote a
`blocked` `run-result.json` over a successful run. That was observed in the field, which is
why the shape rule is stated here rather than left to inference.

**This entry point passes no `impl_artifacts`.** The parent passes it so the adapter also
pins the envelope to `{workflow.implementation_artifacts}/run-result.json`; a readiness
check is not a run, and writing that file here would overwrite an autonomous run's terminal
verdict with the result of a standalone question. Stdout is the sole output of
`/ucg-formalize`.

On the accept path (`status=complete`, re-run verdict ready) emit all five
keys:

```json
{"status": "complete",
 "skill": "ultracode-goal",
 "decision_log": "<path to this run's .decision-log.md>",
 "report": "<path to the readiness report, or null>",
 "deferred_work": "<path to {workflow.deferred_work_path}, or null>"}
```

On the reject path (`status=blocked`) emit the same five keys plus the conditional
sixth `reason`; `report` and `deferred_work` are `null` because the run blocked before
producing them:

```json
{"status": "blocked",
 "skill": "ultracode-goal",
 "decision_log": "<path to this run's .decision-log.md>",
 "report": null,
 "deferred_work": null,
 "reason": "<positional blockers[0], one line>"}
```

An automator parses the five canonical keys at any verdict; `reason` appears only on a
blocked emit. Record the final verdict to
`.decision-log.md` before emitting; the log carries the full blocker and remediation list.

## Measurement protocol

The kernel emits a self-measured `timing` block on every verdict carrying `wall_clock_ms`,
`mechanical_ms`, `epic`, and `artifact_count`. Append those four values verbatim as one line to
`.decision-log.md` on every verdict, reusing the existing decision-log channel. They are the
only durations recorded: measured by the kernel in Python, copied here, never authored. This
layer times nothing itself — a duration the model derives by subtracting two clock reads it
carried across the remediation loop is authored arithmetic wearing a measurement's name.

The wall-clock ceiling is declared-unknown: set only from a first real
preflight-invoked run, never authored here. An over-budget formalize never blocks, escalates, or
downgrades a verdict — the measurement is provenance, not a gate.
