---
name: ucg-formalize
description: Opt-in standalone readiness verdict for one BMAD Epic via the `/ucg-formalize <epic>` trigger. Runs the formalize_check.py kernel, auto-remediates machine-derivable gaps, delegates judgment to one throwaway subagent, and emits the canonical five-key headless envelope. Use when an operator asks to "formalize an epic", "check epic readiness", or runs `/ucg-formalize`.
---

# UCG Formalize

## Overview

`/ucg-formalize <epic>` is the **opt-in, operator-on-demand** readiness verdict for
a single BMAD Epic. It is the thin LLM layer over the readiness kernel
(`scripts/formalize_check.py`): it RUNS that one kernel,
auto-remediates the machine-derivable MECHANICAL gaps, delegates the JUDGMENT
candidates to exactly one throwaway subagent, maps the graduated kernel verdict
(ready / remediable / blocked) into the canonical five-key headless envelope, and
records every verdict and remediation to the run's `.decision-log.md`.

This skill never recomputes the readiness verdict. The kernel is the one source of
mechanical truth (one shared kernel, two entry points: this standalone command and
the autonomous run's preflight clause both adapt the SAME kernel JSON through the
SAME envelope, so the two can never drift). This layer only ADAPTS the kernel's rich
verdict; it does not re-derive `mechanical_budget`, and it never spins up a second
readiness evaluator. It is opt-in and never auto-invoked — there is no auto-fire of
a UCG prompt outside an explicit `/ucg-formalize` call.

## Conventions

These follow the parent `ultracode-goal` SKILL.md Conventions block.

- `{skill-root}` resolves to this skill's installed directory (where the parent
  `customize.toml` lives) — qualify every script path with it so it resolves
  regardless of the current working directory, exactly as the parent
  `references/preflight.md` and `references/gate.md` qualify theirs.
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{planning_artifacts}`, `{workflow.implementation_artifacts}`, and
  `{workflow.tea_config_path}` resolve from the parent module's resolved workflow
  block (the same scalars the autonomous run reads).
- The decision log (`.decision-log.md`) is canonical memory: record the verdict and
  every auto-remediation as you go.

## 1. Run the readiness kernel

Resolve the Epic id `<id>` the operator named, then run the readiness kernel — qualified
by `{skill-root}` so it resolves from any cwd:

```
uv run {skill-root}/scripts/formalize_check.py --epic <id> --project-root {project-root} --planning-artifacts {planning_artifacts} --impl-artifacts {workflow.implementation_artifacts} --tea-config {workflow.tea_config_path}
```

READ the kernel's readiness verdict JSON from stdout. It is the rich verdict — its shape
is `{ready, verdict, mechanical_budget, judgment_required, mechanical_gaps[], judgment_candidates[], checks{}}`.
Do NOT recompute it: `mechanical_budget` is the kernel's per-item count, read off
the JSON, never re-counted in this prose; the verdict is the kernel's, never
re-judged here. There is exactly one kernel — never invoke a second readiness
evaluator alongside it.

The kernel is fail-closed: a missing / unreadable / ambiguous artifact is recorded
as a FAILING gap, never a neutral pass.

## 2. Mechanical auto-remediation pass

Iterate the kernel's `mechanical_gaps[]` and apply the machine-derivable fix for
each entry where `remediable: true`. The remediation per kind:

- **`leaked_tea_artifact`** — MOVE the TEA artifact from the source/impl tree to the
  `trace_output` root and re-point any reference to it. A path move is
  meaning-preserving.
- **`orphaned_index`** (regenerable story/AC) — regenerate the missing story or AC
  stub via `bmad-create-story` so the cited id resolves.
- **`missing_planning_artifact` / `missing_impl_artifact`** — backfill the
  regenerable scaffold (a PRD/ADR stub, the `sprint-status.yaml` rollup via
  `bmad-sprint-planning`).
- **`ac_missing_named_verification` / `ac_missing_anti_vacuous_twin`** — backfill the
  canonical named-verification / anti-vacuous-twin / gate-ability scaffold derivable
  from the AC shape.

Log each remediation to `.decision-log.md` as you apply it. Never
auto-remediate a `judgment_candidate`, and never auto-remediate a
`remediable: false` mechanical gap (an unreadable artifact cannot be fixed from its
own unreadable content).

**RE-RUN the kernel** (step 1) after the remediation pass so `mechanical_budget`
reflects the fixes — the remediate-then-re-run loop. The verdict mapping in step 4
reads the POST-remediation kernel verdict.

**Remediation halt catch-all.** If a remediation sub-skill itself fails or blocks on
interactive input, do not re-invoke it blind: record a non-remediable gap naming the
sub-skill and the exact input it needed, and let the verdict mapping route the run to
`status=blocked`.

## 3. Judgment subagent (exactly one)

Spawn **EXACTLY ONE** throwaway subagent to read the JUDGMENT candidates — never two,
never a second pass. The kernel flags judgment; the subagent decides it. Seed
the subagent with the kernel's `judgment_candidates[].source` list as targeted
hypotheses to confirm (it confirms the flagged sources, it does not scan blind), plus
the artifact paths. The corpus stays in the subagent's discarded context
(zero-net-context) — this layer holds only the returned findings.

The subagent must return **ONLY this object** — the identical three-key contract the
parent `references/preflight.md` semantic scan uses (the live three-key shape, NOT the
superseded two-key `{reds, concerns}` PRD shape) — no prose, no document quotes beyond
the one-line evidence fields:

```json
{"reds": [{"source": "<artifact path:line>",
           "kind": "undecided-product|undecided-architecture|contradiction|undefinable-done",
           "decision_needed": "<the exact decision a human must make>",
           "evidence": "<one quoted line>"}],
 "concerns": [{"source": "<artifact path:line>", "note": "<cosmetic / non-blocking gap, one line>"}],
 "advisories_checked": [{"sig": "<advisory id>", "status": "recurred|not-observed|unknown"}]}
```

Any `reds` entry maps to `status=blocked`. Record each red with its source and the
exact decision needed in `.decision-log.md`. A purely cosmetic gap belongs in
`concerns`, never red.

## 4. Verdict mapping

Map the POST-remediation kernel verdict plus the subagent reds to the headless status
by this deterministic decision-list. `status=complete` is reached ONLY when the
post-remediation kernel verdict is `ready`; `remediable` is an internal loop state and
is NEVER a headless emit value.

| Condition | Route | Headless status |
|-----------|-------|-----------------|
| `mechanical_budget == 0` AND no reds (verdict ready) | accept | `status=complete` |
| `mechanical_budget > 0`, all gaps remediable, no reds (verdict remediable) | remediate-then-re-run (step 2), then re-map | (loops; never emits `remediable`) |
| any red OR any non-remediable mechanical gap OR any artifact the kernel could not read | reject | `status=blocked` |

The `status=blocked` row enumerates all three triggers and they are all load-bearing:

- **any red** — a JUDGMENT candidate the subagent confirmed as a real undecided
  product/architecture decision or an unresolvable input.
- **any non-remediable mechanical gap** — a `remediable: false` gap (e.g. an
  unreadable story file) that no machine fix can clear.
- **any unreadable artifact** — fail-closed (mirroring
  `gate_eval.py:201-203` `nfr_status is None -> treated as failing`): an artifact the
  kernel could not read is a FAILING signal routed to `status=blocked`, NEVER treated
  as neutral or passing. formalize's `blocked` is a deliberate strengthening over
  gate_eval's reloop.

`reason` (in the blocked envelope) carries the first blocker by a DETERMINISTIC order — JUDGMENT candidates before non-remediable mechanical gaps, each in `source` (`path:line`) order — so two runs over the same kernel verdict select the same `reason` (determinism covers the envelope's `reason`, not only `status`).

## Headless

With `-H`, run non-interactively and emit exactly one object at the single exit point.
This is the canonical five-ALWAYS-present-key envelope — byte-identical to the
autonomous parent `SKILL.md` shape: `skill` is the constant
`ultracode-goal` (never `ucg-formalize`), `decision_log` is the always-present audit
anchor, and the script-layer keys (`verdict`, `mechanical_budget`) are NEVER
leaked into the envelope.

On the accept path (`status=complete`, post-remediation verdict ready) emit all five
keys:

```json
{"status": "complete",
 "skill": "ultracode-goal",
 "decision_log": "<path to this run's .decision-log.md>",
 "report": "<path to the readiness report, or null>",
 "deferred_work": "<path to the deferred-work ledger, or null>"}
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
 "reason": "<first/most-severe blocker, one line>"}
```

An automator parses one schema regardless of the verdict; this is the SAME envelope
the autonomous run's preflight clause emits for the same blocked input, so the two entry points
cannot drift. Record the final verdict to `.decision-log.md` before emitting;
the log carries the full blocker and remediation list.

## Measurement protocol (AD-5 / NFR-9)

The kernel emits a self-measured `timing` block on every verdict — ready, remediable, and blocked
alike — carrying `wall_clock_ms`, `mechanical_ms`, `epic`, and `artifact_count`: monotonic deltas the
kernel measures itself, never an author-supplied number. This SKILL layer reads that block, measures
`end_to_end_ms` with a monotonic clock wrapped around the EXISTING step-2 remediation loop and the
EXISTING step-3 judgment subagent read — the same single spawn, with no extra subagent and no extra
prompt introduced solely to time it (the mechanical-vs-end-to-end split AD-5 names) — and appends one
measurement line (`epic`, `artifact_count`, `wall_clock_ms`, `mechanical_ms`, `end_to_end_ms`) to the
run's `.decision-log.md` on every verdict. It rides NFR-9's existing channel: no separate logging
destination, file, or endpoint is introduced; the record lands only in `.decision-log.md`.

Per AD-5 / NFR-7 the wall-clock ceiling is DECLARED-UNKNOWN — it is set only from a first real
preflight-invoked run (a downstream operator action, out of scope here), and no number is authored
into this SKILL or the kernel before then. An over-budget formalize never blocks, escalates, or
downgrades a verdict; the measurement is provider-agnostic provenance, never a gate (INV-7). On a
non-Claude-Code provider the standalone `/ucg-formalize` still records its own duration; only the
preflight auto-invocation is Claude-Code-only.
