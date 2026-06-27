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
recomputes the readiness verdict (Step 1 carries that rule at its point of use). Each
verdict and remediation lands in `.decision-log.md`.

## Conventions

- This nested sub-skill ships no `scripts/` or `customize.toml` of its own: the kernel
  (`formalize_check.py`, `headless_envelope.py`), `customize.toml`, and `references/`
  all live in the **parent** `ultracode-goal/` skill dir, one level up. `{skill-root}` in
  this file therefore resolves to that **parent** dir, so `{skill-root}/scripts/…` and
  `{skill-root}/customize.toml` resolve there; qualify every script path with it so it
  resolves from any cwd.
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{workflow.implementation_artifacts}` and `{workflow.tea_config_path}` resolve from
  the parent module's `customize.toml` workflow block (the same scalars the autonomous
  run reads). `{planning_artifacts}` is not a workflow scalar — it resolves from BMad
  core `config.yaml` (root + `bmm` section), mirroring the parent SKILL.md, and is not
  part of the customize override surface.
- The decision log (`.decision-log.md`) is canonical memory: record the verdict and
  every auto-remediation as you go.

## On Activation

`/ucg-formalize` can run cold (outside an active `ultracode goal` run), so resolve the
scalars the step-1 kernel consumes before calling it — against the **parent** module, so
they are the same scalars the autonomous run reads. Run `python3
{project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --key workflow`
(on failure, merge `{skill-root}/customize.toml` →
`{project-root}/_bmad/custom/ultracode-goal.toml` →
`{project-root}/_bmad/custom/ultracode-goal.user.toml`, scalars override / arrays append),
and load `{planning_artifacts}` from `{project-root}/_bmad/config.yaml` (root + `bmm`
section). If they cannot be resolved, do not pass unresolved `{…}` tokens to the kernel:
record a blocked verdict and push a non-remediable blocker — `source` the unresolved
config path, note "customization/config scalars unresolved" — into step 4's ordered
blocker list, so the Headless `reason` renders.

## 1. Run the readiness kernel

Resolve the Epic id `<id>` the operator named, then run the readiness kernel — qualified
by `{skill-root}` so it resolves from any cwd:

```
uv run {skill-root}/scripts/formalize_check.py --epic <id> --project-root {project-root} --planning-artifacts {planning_artifacts} --impl-artifacts {workflow.implementation_artifacts} --tea-config {workflow.tea_config_path}
```

Read the kernel's readiness verdict JSON from stdout. Its shape is
`{ready, verdict, mechanical_budget, judgment_required, mechanical_gaps[], judgment_candidates[], checks{}}`.
Do not recompute it: read `mechanical_budget` and the verdict off the JSON, never re-derive
them here. There is one kernel — a second readiness evaluator would let the two callers
drift, the failure this shared kernel exists to prevent.

The kernel is fail-closed: a missing / unreadable / ambiguous artifact is recorded
as a failing gap, never a neutral pass.

## 2. Mechanical auto-remediation pass

Iterate the kernel's `mechanical_gaps[]` and apply the machine-derivable fix for
each entry where `remediable: true`. The remediation per kind:

- **`leaked_tea_artifact`** — move the TEA artifact from the source/impl tree to the
  `{workflow.trace_output_dir}` root and re-point any reference to it. A path move is
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

**Re-run the kernel** (step 1) after the remediation pass so `mechanical_budget`
reflects the fixes — the remediate-then-re-run loop. The verdict mapping in step 4
reads the post-remediation kernel verdict.

**Remediation halt catch-all.** If a remediation sub-skill itself fails or blocks on
interactive input, do not re-invoke it blind: record a non-remediable gap naming the
sub-skill and the exact input it needed, and let the verdict mapping route the run to
`status=blocked`. Likewise cap the loop at one pass per gap: if a kernel re-run still
reports a gap whose `kind`+`source` a prior pass already remediated, the fix did not take —
record it as a non-remediable blocker and route to `status=blocked` rather than re-entering
step 2, so the remediate-then-re-run loop always converges instead of spinning silently.

## 3. Judgment subagent (exactly one)

Spawn **exactly one throwaway subagent** to read the judgment candidates; a second pass
would double-judge the same candidates, so never two. Seed the subagent with the kernel's
`judgment_candidates[].source` list as targeted hypotheses to confirm (it confirms the
flagged sources, it does not scan blind), plus the artifact paths. The corpus stays in the
subagent's discarded context (zero-net-context) — this layer holds only the returned findings.

The subagent must return **only this object** — the live three-key contract the parent
`references/preflight.md` semantic scan uses — no prose, no document quotes beyond the
one-line evidence fields:

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

**If subagent spawning is unavailable** — wrong runtime, quota exhausted, or the spawn
errors — do not dead-end the verdict: read the kernel's flagged
`judgment_candidates[].source` inline in the current context (accepting the context cost;
only the zero-net-context property is lost) and proceed to verdict mapping. This degraded
path runs zero subagents, never an extra one, so it preserves the one-subagent determinism.

## 4. Verdict mapping

Map the post-remediation kernel verdict plus the subagent reds to the headless status by
this deterministic decision-list; `remediable` is an internal loop state, never a headless
emit value.

| Condition | Route | Headless status |
|-----------|-------|-----------------|
| `mechanical_budget == 0` AND no reds (verdict ready) | accept | `status=complete` |
| `mechanical_budget > 0`, all gaps remediable, no reds (verdict remediable) | remediate-then-re-run (step 2), then re-map | (loops; never emits `remediable`) |
| any red OR any non-remediable mechanical gap OR any artifact the kernel could not read | reject | `status=blocked` |

The blocked row's three triggers (any red, any non-remediable mechanical gap, any
unreadable artifact) are all load-bearing. The one whose *why* the table cannot carry is
the unreadable artifact: an artifact the kernel could not read is fail-closed to
`status=blocked` (mirroring `gate_eval.py`'s `nfr_status is None -> failing` read), never
treated as neutral — formalize's `blocked` is a deliberate strengthening over gate_eval's
reloop.

For a blocked envelope, assemble the **ordered blocker list** — confirmed reds before
non-remediable mechanical gaps, each in `source` (`path:line`) order — and hand it to the
shared `build_headless_envelope` adapter (see Headless), which renders `reason` positionally
from it.

## Headless

With `-H`, run non-interactively and emit exactly one object at the single exit point.
This is the canonical five-always-present-key envelope — byte-identical to the
autonomous parent `SKILL.md` shape: `skill` is the constant `ultracode-goal` (never
`ucg-formalize`), and the script-layer keys (`verdict`, `mechanical_budget`) never leak
into the envelope.

Serialize the envelope through the one shared adapter
`{skill-root}/scripts/headless_envelope.py` (`build_headless_envelope`) — the same
definition `references/preflight.md` uses under INV-9 — passing the ordered blocker list
from step 4. The adapter emits the canonical keys and the positional `reason`
(`blockers[0]`), so this entry point and the autonomous run cannot serialize a blocked
exit differently.

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
 "reason": "<positional blockers[0], one line>"}
```

An automator parses the five canonical keys at any verdict; `reason` appears only on a
blocked emit. Record the final verdict to
`.decision-log.md` before emitting; the log carries the full blocker and remediation list.

## Measurement protocol (AD-5 / NFR-9)

The kernel emits a self-measured `timing` block on every verdict carrying `wall_clock_ms`,
`mechanical_ms`, `epic`, and `artifact_count`. This layer measures `end_to_end_ms` by bracketing the
step-2 remediation loop and step-3 judgment read with two real monotonic clock reads (a one-line
`python3 -c 'import time; print(time.monotonic_ns())'` before and after — measured, never authored),
and appends one line (`epic`, `artifact_count`, `wall_clock_ms`, `mechanical_ms`, `end_to_end_ms`) to
`.decision-log.md` on every verdict, on NFR-9's existing channel.

The wall-clock ceiling is declared-unknown (AD-5 / NFR-7): set only from a first real
preflight-invoked run, never authored here. An over-budget formalize never blocks, escalates, or
downgrades a verdict — the measurement is provenance, not a gate (INV-7).
