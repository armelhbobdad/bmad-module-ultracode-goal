# Stability and Public Contract

> **Status:** 0.x — pre-1.0. The surfaces below are the intended public contract at `0.1.0`. Per [Semantic Versioning 2.0.0](https://semver.org/), a `0.x` series makes no stability guarantee across minor versions; this document records what we *try* to hold stable and what is explicitly `@internal`, so a consumer knows which surfaces to pin against and which to treat as free to change.

This is the stability posture for `bmad-module-ultracode-goal` at `0.1.0`. It enumerates the surfaces a downstream consumer or automator may reasonably depend on, versus everything else, which is `@internal`.

## Public contract at 0.1.0

The following surfaces are the intended public contract. We aim not to break them within the `0.x` series without a deprecation note; see [SemVer note](#semver-note).

### CLI command surface

The installer CLI is invoked via `npx bmad-module-ultracode-goal <subcommand>`. Covered:

- **Subcommands**: `install`, `update`, `status`, `uninstall`. Renaming, removing, or changing the semantics of any subcommand is a contract change.
- **Options**: `-V` / `--version` (prints the installed package version) and `-h` / `--help` (top-level and per-subcommand).

### The `[workflow]` customize.toml keys

The keys in the shipped `[workflow]` block of `customize.toml` — including `persistent_facts`, `tea_config_path`, `trace_output_dir`, `implementation_artifacts`, `deferred_work_path`, `epic_branch_prefix`, `protected_branches`, `max_turns_per_story`, `story_token_budget`, `parallel_max_concurrency`, `allowlist_commands`, and `on_epic_complete` — are the supported override surface. Teams and users override them in `_bmad/custom/ultracode-goal.toml` (and `.user.toml`) with base → team → user resolution (scalars override, tables deep-merge, arrays append). Renaming or removing a key, or changing how it resolves, is a contract change. See [architecture](../architecture.md).

### The headless five-key JSON emit shape

Every headless (`-H`) exit point emits one object with exactly these five keys, always present, `null` when an artifact was not produced, `reason` carrying a one-line cause only when blocked:

```json
{"status": "complete|blocked",
 "skill": "ultracode-goal",
 "decision_log": "<path>",
 "report": "<path or null>",
 "deferred_work": "<path or null>",
 "reason": "<one line when blocked, else null>"}
```

An automator parses this one schema regardless of where the run stopped. Changing a key name, adding or removing a key, or changing the `null`-when-absent guarantee is a contract change.

### The skill name and invocation phrases

The skill name `ultracode-goal` and its documented invocation phrases — "run an epic autonomously", "execute this epic", "ultracode goal", "autonomously deliver the epic" — are part of the contract. Removing or renaming the skill, or dropping a documented trigger phrase, is a contract change.

### gate_eval.py CLI and verdict vocabulary

`scripts/gate_eval.py` is the deterministic completion authority. Covered:

- **CLI flags**: `--trace-output` (required), `--profile` (`light` | `production`, required), `--nfr`, `--test-review` (production only).
- **Verdict vocabulary**: the `verdict` values `advance` / `defer` / `reloop` / `escalate`, and the `gate_status` values `PASS` / `CONCERNS` / `FAIL` / `WAIVED` / `NOT_EVALUATED`, plus the mapping between them. See the [gate model](../gate-model.md).

The printed JSON object's key set (`verdict`, `gate_status`, `p0_status`, `p1_status`, `overall_status`, `nfr_status`, `review_score`, `reasons`) is the consumable shape; the human-readable `reasons` strings are not contractual wording.

## @internal — not covered

Everything not enumerated above is `@internal` and may change in any `0.x` release without a deprecation note. Do not pin against:

- **Installer library internals** — the implementation behind the CLI subcommands; what is covered is the observable subcommand surface, not how the files get placed.
- **Reference file structure** — the `references/*.md` stage files' internal structure, step ordering, prose, and section headings. The stage *names* are referenced by the health-check fingerprint (see below) but the file contents are an authoring surface.
- **Script internals** — the internal functions, regexes, and intermediate behavior of `preflight_check.py`, `gate_eval.py`, `health_check_fp.py`, and the hook scripts. The covered surface is `gate_eval.py`'s CLI and verdict vocabulary above; everything else (the `preflight_check.py` JSON shape, the fingerprint tuple format, the hook env-var names) is internal and may change.
- **The experimental `--parallel` workflow** — `assets/execute-epic.workflow.js`, the `/ultracode-goal-execute` registration, its args binding, its return shape, and `parallel_max_concurrency`'s runtime behavior are explicitly experimental and excluded from the contract. See [parallel mode](../parallel-mode.md).
- **`_bmad-output/` artifact layout** — run folders, the decision log, `run-report.md`, `run-status.json`, the deferred-work ledger, and the improvement queue are run outputs, not a downstream-consumable schema. The headless emit shape (covered above) is the supported way to locate these paths programmatically.

## SemVer note

This is a `0.x` module: **minor versions may break.** We try to hold the surfaces in [Public contract at 0.1.0](#public-contract-at-010) stable, and the two surfaces an automator is most likely to encode against — the **headless five-key JSON emit shape** and the **`[workflow]` customize.toml keys** — get a deprecation note in `CHANGELOG.md` before changing. `@internal` surfaces change freely. Once the module reaches `1.0.0`, this document is superseded by a full SemVer contract.
