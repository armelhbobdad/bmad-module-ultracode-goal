---
title: UCG Awareness Fragment Shaping Decision
description: Operator sign-off that each of the four planning shaping fragments encodes its workflow's shift-left shaping as additive persistent_facts guardrails, signed against the note that the gate, not the shaping, is the guarantee.
---

# UCG Awareness Fragment Shaping Decision

This is the decision-doc gate. Content adequacy of a shaping
fragment is a human judgment, so for each of the four planning fragments an
operator confirms that every shift-left shaping bullet for that workflow
appears as a `persistent_facts` guardrail entry, names the permanent floor classes
the fragment targets, and records an `ACCEPTED` or `REWORK` verdict with a
reviewer and a date.

Every block below is signed against the downgrade note: these fragments are
run-scoped guardrail facts, narrower than per-acceptance-criterion machine
directives by design. The formalize/preflight gate, not this shaping, is the
load-bearing guarantee that an artifact is UCG-ready. A fragment steers authoring toward
readiness; the gate still decides the verdict.

The fixed block format each entry below follows, which
`test_shaping_decision_doc_present_and_signed` parses, is:

- a `## Fragment: <fragment-id>` heading whose `<fragment-id>` is the
  `[ucg:<skill>]` identity of the fragment,
- a `Fragment file:` line naming the on-disk fragment path,
- `Shift-left shaping coverage:` and `Permanent floor classes:` lines,
- and `Reviewer:`, `Date:`, `Status:` lines.

A block whose `Status:` is not `ACCEPTED`, that is missing, or whose
`Fragment file:` names a path that does not exist on disk fails the test.

## Fragment: [ucg:bmad-prd]

- Fragment file: `skills/ultracode-goal/assets/ucg-awareness/bmad-prd.toml`
- Shift-left shaping coverage: machine-checkable NFR budgets (named metric, concrete
  numeric/boolean threshold, measurement method); gate-ability tag on each
  requirement and NFR from {ci-machine, partly-operator, decision-doc}; stable
  traceable FR id on each functional requirement; resolve open questions as ADRs
  before UCG/preflight rather than leaving a TBD on a load-bearing requirement.
- Permanent floor classes: invented-NFR-threshold (threshold numbers cite a source
  or are marked UNKNOWN); undecided-decision (open questions resolved as ADRs
  before a UCG or preflight run).
- Bound surface: the live `bmad-prd` surface only, never the deprecated
  `bmad-create-prd` or `bmad-edit-prd` shims.
- Reviewer: Armel
- Date: 2026-06-25
- Status: ACCEPTED

## Fragment: [ucg:bmad-architecture]

- Fragment file: `skills/ultracode-goal/assets/ucg-awareness/bmad-architecture.toml`
- Shift-left shaping coverage: each load-bearing decision authored as a numbered
  architecture decision with an explicit Binds, Prevents, and Rule plus an
  ADOPTED marker once settled; Deferred-with-a-revisit-trigger entries instead of
  a silent TBD; resolve open questions as ADRs before preflight; decision ids stay
  stable and no inherited parent decision is silently weakened; no structural
  dimension the altitude owns is left wholly silent.
- Permanent floor classes: undecided-decision (unresolved or untagged forks an
  in-scope story depends on); invented-NFR-threshold (architecture numbers cite
  a source or are recorded Deferred-with-revisit).
- Reviewer: Armel
- Date: 2026-06-25
- Status: ACCEPTED

## Fragment: [ucg:bmad-create-epics-and-stories]

- Fragment file: `skills/ultracode-goal/assets/ucg-awareness/bmad-create-epics-and-stories.toml`
- Shift-left shaping coverage: per-story gate-ability tag from {ci-machine,
  partly-operator, decision-doc}; every AC a deterministic machine-checkable
  assertion; each AC names a verification artifact an existing story or test
  declares; a mandatory anti-vacuous twin per AC; the deterministic-CI-vs-operator
  split made explicit per AC; every in-scope FR covered by at least one story
  with no AC presupposing an undecided question.
- Permanent floor classes: vacuous AC; orphaned never-green index; leaked TEA
  artifact (TEA outputs under the trace_output root, never the source or
  implementation tree); invented NFR threshold.
- Reviewer: Armel
- Date: 2026-06-25
- Status: ACCEPTED

## Fragment: [ucg:bmad-create-story]

- Fragment file: `skills/ultracode-goal/assets/ucg-awareness/bmad-create-story.toml`
- Shift-left shaping coverage: each story inherits the epic AC contract verbatim
  (machine-checkable, named verification, mandatory anti-vacuous twin,
  CI-deterministic-vs-operator split, gate-ability tag); every Task and Subtask
  carries an (AC: #) back-reference and every AC has an implementing Task; Dev
  Notes cite only real, resolvable source paths and real architecture-decision
  ids with no invented reference or guessed threshold; the story has a definable done derivable from
  its own ACs, verifications, and Tasks before ATDD handoff.
- Permanent floor classes: vacuous AC; orphaned never-green index; invented NFR
  threshold; leaked TEA artifact.
- Reviewer: Armel
- Date: 2026-06-25
- Status: ACCEPTED
