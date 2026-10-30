---
title: Stability and Public Contract
description: "The 4.x stability posture: which CLI, config, JSON, and gate surfaces are the supported public contract, what a major costs, and everything that is @internal and free to change."
---

> **Status:** 4.x. The surfaces below are the public contract. Per [Semantic Versioning 2.0.0](https://semver.org/), a breaking change to any of them requires a MAJOR bump; everything marked `@internal` may change in any release. This document is what a consumer pins against.

This is the stability posture for `bmad-module-ultracode-goal` at `4.x`. It enumerates the surfaces a downstream consumer or automator may reasonably depend on, versus everything else, which is `@internal`.

## Public contract

The following surfaces are the public contract. Breaking one requires a MAJOR bump; see [SemVer note](#semver-note).

### CLI command surface

The installer CLI is invoked via `npx bmad-module-ultracode-goal <subcommand>`. Covered:

- **Subcommands**: `install`, `update`, `status`, `uninstall`. Renaming, removing, or changing the semantics of any subcommand is a contract change.
- **Options**: `-V` / `--version` (prints the installed package version) and `-h` / `--help` (top-level and per-subcommand).

### The `[workflow]` customize.toml keys

The keys in the shipped `[workflow]` block of `customize.toml` (including `persistent_facts`, `tea_config_path`, `trace_output_dir`, `implementation_artifacts`, `deferred_work_path`, `epic_branch_prefix`, `protected_branches`, `max_turns_per_story`, `story_token_budget` (**deprecated, no-op**), `parallel_max_concurrency` (**deprecated, no-op**), `allowlist_commands`, `on_epic_complete`, `on_escalation`, `cross_session_recall`, `cross_session_recall_store`, and `graphify_integration`) are the supported override surface. Teams and users override them in `_bmad/custom/ultracode-goal.toml` (and `.user.toml`) with base → team → user resolution (scalars override, tables deep-merge, arrays append). Renaming or removing a key, or changing how it resolves, is a contract change. See [architecture](../architecture.md).

`story_token_budget` is **deprecated** as of the deprecation note in `CHANGELOG.md`: it is still shipped, still accepted, and still resolves, so existing overrides keep working and nothing errors. It is a no-op; no layer reads it any more. The runaway bound is turns only, via `max_turns_per_story`. The key stays enumerated here (and stays in `customize.toml`) precisely because removing it would be the contract break this section forbids.

`parallel_max_concurrency` is **deprecated** on the same terms, as of the retirement of the experimental `--parallel` fan-out: still shipped, still accepted, still resolves, read by nothing. The `--parallel` flag itself is likewise still accepted by the skill and ignored (the run logs one note and executes the sequential spine), so an operator's old invocation keeps working.

### The headless five-key JSON emit shape

Every headless (`-H`) exit point emits one object with exactly these five keys, always present, `null` when an artifact was not produced, plus a conditional sixth, `reason`, carrying a one-line cause only when blocked. A **complete** emit omits `reason` entirely; it is not present-and-`null`, so read it only when `status` is `blocked`:

```json
{"status": "complete|blocked",
 "skill": "ultracode-goal",
 "decision_log": "<path>",
 "report": "<path or null>",
 "deferred_work": "<path or null>",
 "reason": "<one line, present only when blocked; omitted on a complete emit>"}
```

An automator parses this one schema regardless of where the run stopped. Changing a key name, adding or removing a key, changing the `null`-when-absent guarantee, or making `reason` present on a complete emit is a contract change.

### The headless result file

A headless run writes that same object to `{workflow.implementation_artifacts}/run-result.json`, byte-identical to what it emitted on stdout, so an automator reads a pinned file path instead of scraping a transcript. Covered:

- **The path**: the basename `run-result.json` directly inside the resolved `{workflow.implementation_artifacts}`, with no run-id suffix and no subdirectory.
- **The contents**: the headless five-key emit shape above, unchanged.

- **The guarantee**: once a headless run resolves `{workflow.implementation_artifacts}` it clears any prior `run-result.json`, before any stage work. From that point on the file's presence means **this** run reached a terminal. The guarantee is scoped to that moment, so a consumer should still prefer a parseable stdout envelope when the file is absent.

Five documented exceptions, none of which is a contract break: a block that fires **before** `{workflow.implementation_artifacts}` resolves (the "not a BMAD project" stop) neither writes nor clears, so it leaves the stdout envelope as its sole output and is the one case where a prior run's file can survive; a terminal whose best-effort write failed leaves no file while still printing its envelope; a headless run whose call to the envelope adapter is itself refused by the permission layer builds nothing by hand, so it leaves no file and prints no envelope, recording the block and the refusal in its `.decision-log.md` instead (since 2.3.0); a headless run that has not yet reached a terminal (still running, crashed, or killed) has no file, because startup cleared any prior one; and an **attended** run writes no file at all and clears none. The file is overwrite-in-place, so it carries no cross-run history.

### The skill name and invocation phrases

The skill name `ultracode-goal` and its documented invocation phrases ("run an epic autonomously", "execute this epic", "ultracode goal", "autonomously deliver the epic") are part of the contract. Removing or renaming the skill, or dropping a documented trigger phrase, is a contract change.

### gate_eval.py CLI and verdict vocabulary

`scripts/gate_eval.py` is the deterministic completion authority. Covered:

- **CLI flags**: `--trace-output` (required), `--profile` (`light` | `production`, required), `--story`, `--nfr`, `--test-review` (production only), `--tests-ran` (per-story only), `--cycle-profile` (per-story only), `--epic-level`, `--rollup` and `--sprint-status` (roll-up only: `--rollup` requires `--epic-level`, `--story <epic id>` and `--sprint-status`, and `--sprint-status` is rejected without `--rollup`; every roll-up refusal resolves to `gate_status: NOT_EVALUATED` -> `escalate`, never to a silent narrower answer).
- **The roll-up's story set** (`--rollup`): every story row of the epic in `sprint-status.yaml`, except a decomposed parent on its split record: a `done` row with no resolvable gate artifact, for which `.split-<its key>.json` beside `--sprint-status`, as `scripts/story_sizing.py --parent <key> --record <dir>` writes it, holds a JSON object whose `parent` is that key and whose `children` are each another story row of the epic, when no chain of such records leads from it back to it and `--story <key>` would find no trace report, gate decision or trace summary of its own. Its children's gates count in its place, and a `reasons` line names it. The record's other fields are internal.
- **The production signals are required, not optional, on a per-story gate.** Under `--profile production` an omitted `--nfr` or `--test-review` is a *failing* signal, exactly as a supplied-but-missing path already was. `--epic-level` is the one sanctioned omission: it declares the epic roll-up, where TEA writes no aggregate to AND, and it cannot be combined with either path (doing so is an invocation error, exit 2). Under `--profile light` the flag is a no-op.
- **The sweep-scope cap** (`--tests-ran`): optional PATH to the story's `.tests-ran-<story_id>` marker, read in both profiles. The marker's `scope=` line is read fail-closed: `scope=full` passes the verdict through; `scope=scoped`, a missing marker, a missing `scope=` line, or an unrecognised value caps `advance`/`defer` at `reloop` (defer moves too, because its route advances the story). It cannot be combined with `--epic-level` (an invocation error, exit 2). **Omitting the flag skips the check**: invocations that predate the flag keep their verdicts, per the breaking-change rule below. The verdict JSON's `sweep_scope` key carries the recognised value or `null`, and is present exactly when the flag was supplied, so the printed shape of pre-flag invocations is unchanged.
- **The delta cycle profile** (`--cycle-profile`, `full` | `delta`): `delta` declares a mid-loop gate that re-ran only the previously failed assessor dimension(s); its verdict is capped at `reloop` (`advance` and `defer` both move to `reloop`). An unrecognised value is an argparse error (exit 2), and the flag cannot be combined with `--epic-level` (exit 2). Omission is the full behaviour. The `cycle_profile` JSON key is present exactly when the flag was supplied.
- **Verdict vocabulary**: the `verdict` values `advance` / `defer` / `reloop` / `escalate`, and the `gate_status` values `PASS` / `CONCERNS` / `FAIL` / `WAIVED` / `NOT_EVALUATED`, plus the mapping between them. See the [gate model](../gate-model.md).
- **`--story` fail-closed resolution**: when `--story` matches no artifact in a trace dir whose reports or gate-decision files are named per story, the result is `NOT_EVALUATED` (so, `escalate`), never a fallback to another story's gate. A trace dir whose candidates are all generically named (`trace.md`, `gate-decision.json`) still resolves unscoped. Which file the resolver picks, and how it decides that a name carries a story id, are internal.

The contractual mapping each `gate_status` resolves to:

```mermaid
flowchart LR
    PASS["PASS"] --> ADV["advance"]
    WAIVED["WAIVED"] --> ADV
    CONCERNS["CONCERNS"] --> DEF["defer"]
    FAIL["FAIL"] --> REL["reloop"]
    NE["NOT_EVALUATED"] --> ESC["escalate"]
    classDef verdict fill:#4F46E5,stroke:#3730A3,color:#fff
    class ADV,DEF,REL,ESC verdict
```

The printed JSON object's key set (`verdict`, `gate_status`, `p0_status`, `p1_status`, `overall_status`, `nfr_status`, `review_score`, `epic_level`, `reasons`) is the consumable shape; the human-readable `reasons` strings are not contractual wording. Two keys are conditional by design: `sweep_scope` appears exactly when `--tests-ran` was supplied (its value the recognised `scope=` reading, or `null`) and `cycle_profile` exactly when `--cycle-profile` was; each is absent otherwise, so an invocation that predates the flags prints the same shape it always did. `epic_level` is how a consumer tells an `advance` that ANDed both production signals from one that skipped them by declaration: `nfr_status: null` alone cannot say which, and the distinction is not readable from `reasons` precisely because that wording is not contractual.

### Supported tool versions

The minimum versions UCG supports, listed in `tools/tool-requirements.yaml` and shown in the [prerequisites table](../getting-started.md#prerequisites): Claude Code (the version preflight refuses to launch below), Node.js (`engines.node`), Python (the `requires-python` header of every script) and BMAD Method. Raising a minimum, or giving a tool its first one, turns away a setup the release before accepted, so it is a contract change. Lowering or removing a minimum is additive. The tested versions in the same list record what UCG's own runs used and are not part of the contract.

This bucket was added in 3.0.0. Adding it widens what the contract covers and removes nothing from it, so it is an additive change to this contract.

## @internal: not covered

Everything not enumerated above is `@internal` and may change in any release, major or minor, without a deprecation note. Do not pin against:

- **Installer library internals**: the implementation behind the CLI subcommands; what is covered is the observable subcommand surface, not how the files get placed.
- **Reference file structure**: the `references/*.md` stage files' internal structure, step ordering, prose, and section headings. The stage *names* are referenced by the health-check fingerprint (see below) but the file contents are an authoring surface.
- **Script internals**: the internal functions, regexes, and intermediate behavior of `preflight_check.py`, `gate_eval.py`, `health_check_fp.py`, and the hook scripts. The covered surface is `gate_eval.py`'s CLI and verdict vocabulary above; everything else (the `preflight_check.py` JSON shape, the fingerprint tuple format, the hook env-var names) is internal and may change.
- **The retired `--parallel` workflow**: the experimental fan-out (`assets/execute-epic.workflow.js`, its `/ultracode-goal-execute` registration, args binding and return shape) was explicitly excluded from this contract while it shipped, and has been removed. The `--parallel` flag is still accepted and ignored, and `parallel_max_concurrency` is deprecated, still resolving, no-op: the `story_token_budget` treatment (see [Public contract](#public-contract)).
- **`_bmad-output/` artifact layout**, with one exception: run folders, the decision log, `run-report.md`, `run-status.json`, the deferred-work ledger, and the improvement queue are run outputs, not a downstream-consumable schema. **`run-result.json` is the exception and is covered** (see [the headless result file](#the-headless-result-file)); it is the one artifact in that tree an automator may pin against. The headless emit shape (covered above) is the supported way to locate the rest of these paths programmatically.

## SemVer note

**A breaking change to any surface in [Public contract](#public-contract) requires a MAJOR bump.** That is the whole rule, and it is deliberately stricter than "we try": this module's value is that a machine-checked contract means what it says, so the versioning of the contract has to as well.

What counts as breaking, stated so it is not re-litigated per release:

- Removing or renaming an enumerated CLI flag, subcommand, config key, or JSON key.
- **Changing the verdict an unchanged, previously-documented invocation returns.** This is the one that bites, and it bit at 2.0.0: `gate_eval.py --profile production` with neither signal flag was the documented epic-level invocation and returned `advance`; it now returns `reloop` unless `--epic-level` is passed. That the old answer was unearned did not make the change non-breaking: a consumer's pipeline still changed behaviour on an upgrade they did not ask for.
- Adding a key to the JSON an UNCHANGED invocation prints (the verdict object or the headless envelope), for a consumer validating the shape strictly. A key that appears only when a newly introduced flag is supplied is additive, not breaking: `sweep_scope` and `cycle_profile` are the worked example, present exactly when `--tests-ran` / `--cycle-profile` are passed and absent from every pre-flag invocation's output.

What does not:

- Fixing a resolver so it returns the *right* artifact rather than a neighbour's, where the documented invocation and its vocabulary are unchanged.
- Anything behind `@internal`, including which file a resolver picks and how it decides a name carries a story id.
- Prose in `references/*.md`, which is an authoring surface.

**How a release checks this.** Every pull request that changes something a user can notice adds a change fragment to `changes/` ([`changes/README.md`](https://github.com/armelhbobdad/bmad-module-ultracode-goal/blob/main/changes/README.md)), and the release notes and the minimum version bump come from those fragments. `tools/covered-surfaces.js` reads the surfaces above (the CLI subcommands and options, the `[workflow]` keys, the headless emit keys and result file, the skill name and invocation phrases, the `gate_eval.py` flags, choices, statuses, verdicts and printed keys, and the tool minimums) at the last stable tag and now. The release gate (`node tools/changes.js gate`) refuses a release that removes one of them without a major bump and a `breaking` fragment that names it, or that adds one without at least a minor bump. Three kinds of change go the other way: adding or removing a key of the headless emit shape, or renaming the result file, is a major change, since the shape is exactly those keys; raising a tool minimum, or giving a tool its first one, is a major change, and lowering or removing one a minor one; and a `gate_status` that maps to another verdict is a major change. A key added to the printed `gate_eval.py` result is listed for a person to judge, since the text cannot tell a key every invocation prints from one only a new flag prints. A changed verdict for an unchanged invocation is not something the diff can see: its fragment says so, as a `breaking` one. The gate also refuses a major release while the **Status** line above names another major, so the copy of this document in each package names the major it describes.

**Deprecation.** The two surfaces an automator is most likely to encode against, the **headless five-key JSON emit shape** and the **`[workflow]` customize.toml keys**, get a deprecation note in the release notes (a change fragment, rendered into `CHANGELOG.md`) at least one minor before changing, and the key stays shipped and accepted meanwhile. `story_token_budget` is the worked example: deprecated, still resolving, no-op.
