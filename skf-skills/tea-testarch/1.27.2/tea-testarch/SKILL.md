---
name: tea-testarch
description: >
  TEA (Test Architect) v1.27.2 test-architecture workflows that UltraCode Goal uses as its
  quality gate — framework, ci, test-design, atdd, automate, test-review, nfr and trace — with
  their inputs, output paths and _bmad/tea/config.yaml keys, and the exact gate-decision.json
  contract written by bmad-testarch-trace (step-05-gate-decision.md). Use when invoking a TEA
  workflow from an orchestrator, locating the files it reads or writes, or reading the
  PASS/CONCERNS/FAIL gate decision. Not for writing tests by hand or for the unreleased
  scoped-output layout that follows v1.27.2.
---

# TEA v1.27.2 — test-architecture workflows and the trace gate contract

## Overview

Reference for the `src/` tree of <https://github.com/bmad-code-org/bmad-method-test-architecture-enterprise> at tag `v1.27.2` (commit `d99ad29c`), compiled at Forge tier **Deep**.

- **Surface:** eight `bmad-testarch-*` workflow skills, the `bmad-tea` agent (Murat), `module.yaml` and `module-help.csv`. These are markdown step-file workflows with no importable API; every behaviour claim cites a verified source line (T1-low), and release notes add T2 context.
- **Shape:** reference-app. The value is the contract an orchestrator relies on: which skill to call, what it reads, where it writes, and how the gate is decided.
- **Config:** every workflow reads `{project-root}/_bmad/tea/config.yaml`. [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L7] [SRC:src/workflows/testarch/bmad-testarch-test-design/workflow.yaml:L7] [SRC:src/workflows/testarch/bmad-testarch-nfr/workflow.yaml:L7] [SRC:src/workflows/testarch/bmad-testarch-atdd/workflow.yaml:L7] [SRC:src/workflows/testarch/bmad-testarch-automate/workflow.yaml:L7]

## Quick Start

The gate signal is `{test_artifacts}/gate-decision.json`, written by `bmad-testarch-trace` step 5. [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L44] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L748] `test_artifacts` defaults to `{output_folder}/test-artifacts`. [SRC:src/module.yaml:L32]

```bash
GATE="$TEST_ARTIFACTS/gate-decision.json"   # $TEST_ARTIFACTS = the resolved {test_artifacts}
jq -r '.gate_status, .evaluated_at, .rationale' "$GATE"
```

- `gate_status` is `PASS`, `CONCERNS`, `FAIL` or `WAIVED`; the file is written only for gate-eligible runs (`allow_gate` true and `collection_status` `COLLECTED`). [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L748] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L262]
- Rules 1–5 never produce `WAIVED`, so an automated run yields `PASS`, `CONCERNS` or `FAIL`. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L304] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L305]
- The path is fixed in v1.27.2, and a non-eligible run writes nothing. A file left by an earlier run therefore survives: compare `evaluated_at` with your run start before trusting it. [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L44] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L748] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L751]

The workflows are skills. Each opens with "What would you like to do?" and a Create / Resume / Validate / Edit menu. Create runs from the beginning, and the workflow then proceeds without user input unless blocked. [SRC:src/workflows/testarch/bmad-testarch-trace/SKILL.md:L73] [SRC:src/workflows/testarch/bmad-testarch-trace/SKILL.md:L75] [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L111]

<!-- [MANUAL:additional-notes] -->
<!-- Add custom notes here. This section is preserved during skill updates. -->
<!-- [/MANUAL:additional-notes] -->

## Adoption Steps

1. **Configure `_bmad/tea/config.yaml`.** Set `test_artifacts`, `tea_execution_mode` (`auto`, `subagent`, `agent-team` or `sequential`), `tea_capability_probe`, `test_stack_type`, `ci_platform`, `test_framework` and the Playwright/Pact/browser flags. See `references/pattern-config-and-registration.md`. [SRC:src/module.yaml:L25] [SRC:src/module.yaml:L31] [SRC:src/module.yaml:L97] [SRC:src/module.yaml:L113]
2. **Phase 3, once per project:** test-design (TD, system-level) → framework (TF) → ci (CI), following `module-help.csv`. [SRC:src/module-help.csv:L4] [SRC:src/module-help.csv:L5] [SRC:src/module-help.csv:L6]
3. **Per story:** atdd (AT) after `bmad-create-story:create` and before `bmad-dev-story`, then automate (TA). [SRC:src/module-help.csv:L7] [SRC:src/module-help.csv:L8]
4. **Audits:** test-review (RV) and nfr (NR) follow automate. [SRC:src/module-help.csv:L9] [SRC:src/module-help.csv:L10]
5. **Gate:** trace (TR) after test-review, with `gate_type` `story`, `epic`, `release` or `hotfix`. Read `gate-decision.json` as shown in the Quick Start. [SRC:src/module-help.csv:L11] [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L32]
6. **Customize without editing skills:** use `_bmad/custom/<skill>.toml` (team) or `.user.toml` (personal) for `on_complete`, `persistent_facts` and the `activation_steps_*` arrays. Scalars override and arrays append. [SRC:src/workflows/testarch/bmad-testarch-trace/SKILL.md:L31] [SRC:src/workflows/testarch/bmad-testarch-trace/SKILL.md:L32] [SRC:src/workflows/testarch/bmad-testarch-atdd/customize.toml:L34] [SRC:src/workflows/testarch/bmad-testarch-atdd/customize.toml:L9]

## Pattern Surface

| # | Skill | Code | Main output | Reference |
|---|-------|------|-------------|-----------|
| 1 | `bmad-testarch-test-design` | TD | `test-design-architecture.md` and `test-design-qa.md` (system level); `test-design-epic-{epic_num}.md` (epic level) [SRC:src/workflows/testarch/bmad-testarch-test-design/workflow.yaml:L37] [SRC:src/workflows/testarch/bmad-testarch-test-design/workflow.yaml:L43] [SRC:src/workflows/testarch/bmad-testarch-test-design/workflow.yaml:L56] | `pattern-test-design.md` |
| 2 | `bmad-testarch-framework` | TF | `{test_dir}/README.md`, framework config, `tea-enforce.cjs` hook [SRC:src/workflows/testarch/bmad-testarch-framework/workflow.yaml:L28] [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-03-scaffold-framework.md:L175] [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-04-docs-and-scripts.md:L91] | `pattern-framework-and-ci.md` |
| 3 | `bmad-testarch-ci` | CI | `.github/workflows/test.yml` or the equivalent file for each platform [SRC:src/workflows/testarch/bmad-testarch-ci/steps-c/step-02-generate-pipeline.md:L112] [SRC:src/workflows/testarch/bmad-testarch-ci/workflow.yaml:L28] | `pattern-framework-and-ci.md` |
| 4 | `bmad-testarch-atdd` | AT | `atdd-checklist-{story_key}.md` and red-phase `test.skip()` scaffolds [SRC:src/workflows/testarch/bmad-testarch-atdd/workflow.yaml:L26] [SRC:src/workflows/testarch/bmad-testarch-atdd/steps-c/step-04-generate-tests.md:L362] | `pattern-atdd-and-automate.md` |
| 5 | `bmad-testarch-automate` | TA | `automation-summary.md` and `[P0]`–`[P3]` tagged tests [SRC:src/workflows/testarch/bmad-testarch-automate/workflow.yaml:L32] [SRC:src/workflows/testarch/bmad-testarch-automate/checklist.md:L516] | `pattern-atdd-and-automate.md` |
| 6 | `bmad-testarch-test-review` | RV | `test-review.md`, scored 0–100 with a recommendation [SRC:src/workflows/testarch/bmad-testarch-test-review/workflow.yaml:L35] [SRC:src/workflows/testarch/bmad-testarch-test-review/instructions.md:L10] [SRC:src/workflows/testarch/bmad-testarch-test-review/test-review-template.md:L28] | `pattern-test-review.md` |
| 7 | `bmad-testarch-nfr` | NR | `nfr-assessment.md` with an `nfr_assessment` gate YAML [SRC:src/workflows/testarch/bmad-testarch-nfr/workflow.yaml:L27] [SRC:src/workflows/testarch/bmad-testarch-nfr/nfr-report-template.md:L397] | `pattern-nfr.md` |
| 8 | `bmad-testarch-trace` | TR | `traceability-matrix.md`, `e2e-trace-summary.json`, `gate-decision.json` [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L42] [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L43] [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L44] | `pattern-gate-decision.md` |
| 9 | `bmad-tea` agent | — | Menu over TMT (`bmad-teach-me-testing`, out of scope here) and rows 1–8, plus `GATE` (optional review, then optional NFR, then trace Phase 2) [SRC:src/agents/bmad-tea/customize.toml:L63] [SRC:src/agents/bmad-tea/customize.toml:L93] | `pattern-config-and-registration.md` |

All output paths sit under `{test_artifacts}` unless the path shows otherwise.

## gate-decision.json

`schema_version` `'0.1.0'` holds a slim subset of `e2e-trace-summary.json`, written with 2-space indentation. [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L67] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L750] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L764]

| Field | Meaning |
|-------|---------|
| `evaluated_at` | ISO-8601 `snapshot_at` of the run [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L751] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L619] |
| `repo`, `target` | `project_name`; the trace target (`type`, `id`, `label`) [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L752] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L753] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L626] |
| `collection_status`, `gate_basis` | `COLLECTED` for eligible runs; `priority_thresholds` [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L754] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L610] |
| `gate_status`, `rationale` | The decision and why [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L756] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L757] |
| `p0_status`, `p1_status`, `overall_status` | `MET` / `NOT_MET` (P1 can also be `PARTIAL`) [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L727] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L731] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L734] |
| `critical_open` | P0 criteria below `FULL` coverage [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L761] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L678] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-04-analyze-gaps.md:L138] |
| `links` | `trace_report_path`, plus URLs left empty for CI to fill [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L762] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L709] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L710] |

**Decision** (the first rule that matches wins): P0 < 100% → FAIL; overall < 80% → FAIL; P1 < 80% → FAIL; P1 ≥ 90% → PASS; P1 80–89% → CONCERNS. With no P1 requirements, P1 counts as 100%. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L278] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L271] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L277] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L282] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L289] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L296] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L98] A synthetic oracle without `high` confidence, or any requirement covered only by live evidence, downgrades PASS to CONCERNS. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L314] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L331] Waivers are validated and reported but never change the decision. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L346] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L384]

## Gotchas

- **Coverage is not test-review's job.** Test-review scores test quality only; coverage gates belong to trace. [SRC:src/workflows/testarch/bmad-testarch-test-review/instructions.md:L12]
- **ATDD scaffolds are skipped on purpose.** Scaffolds carry `test.skip()`, and test-review registry row C1 (CRITICAL) fires on skipped tests. Review after the developer removes `test.skip()`. [SRC:src/workflows/testarch/bmad-testarch-atdd/steps-c/step-04-generate-tests.md:L362] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/criteria-registry.md:L138] [SRC:src/workflows/testarch/bmad-testarch-atdd/atdd-checklist-template.md:L273]
- **Framework edits `.claude/settings.json`.** On Claude Code it merges `PreToolUse`, `PostToolUse` and `Stop` entries for `.claude/hooks/tea-enforce.cjs` into the existing file, and the hook blocks writes with exit 2. [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-04-docs-and-scripts.md:L87] [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-04-docs-and-scripts.md:L137] [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-04-docs-and-scripts.md:L144] [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-04-docs-and-scripts.md:L150] [SRC:src/workflows/testarch/bmad-testarch-framework/steps-c/step-04-docs-and-scripts.md:L156] [SRC:src/workflows/testarch/bmad-testarch-framework/resources/hooks/tea-enforce.cjs:L73]
- **Parallel modes use `/tmp`.** With `tea_execution_mode: auto`, TEA tries agent-team, then subagent, then sequential, and workers exchange `/tmp/tea-<workflow>-…-{timestamp}.json` files. Setting `tea_capability_probe: false` makes an unexecutable mode fail instead of falling back. [SRC:src/module.yaml:L280] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-04-evaluate-and-score.md:L222] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-03-quality-evaluation.md:L267] [SRC:src/workflows/testarch/bmad-testarch-atdd/steps-c/step-04-generate-tests.md:L164]
- **NFR never guesses.** An unknown threshold is reported as `CONCERNS`, never `PASS`. [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/step-02-define-thresholds.md:L116] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/nfr-status-definitions.md:L41]
- **Fixed paths in v1.27.2.** Trace, NFR and automate write fixed file names under `{test_artifacts}`. Upstream moves them into per-workflow folders after v1.27.2 (see Migration). [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L42] [SRC:src/workflows/testarch/bmad-testarch-nfr/workflow.yaml:L27] [SRC:src/workflows/testarch/bmad-testarch-automate/workflow.yaml:L32]

## Migration & Deprecation Warnings

- **After v1.27.2 (breaking, PR #236):** outputs move to `{test_artifacts}/<workflow>/` with a `run_key` in the file name; the gate file becomes `trace/gate-decision-{run_key}.json`. Scripts that read the flat paths need the new ones. [QMD:tea-testarch-temporal:changelog.md] [QMD:tea-testarch-temporal:prs.md]
- **After v1.27.2:** the unused keys `test_design_output`, `test_review_output` and `trace_output` are removed from `module.yaml`. [SRC:src/module.yaml:L210] [QMD:tea-testarch-temporal:changelog.md]
- **After v1.27.2:** a tenth workflow is added, Evaluate (`bmad-testarch-evaluate`, `EV`). [QMD:tea-testarch-temporal:changelog.md]
- **v1.26.0:** `tea_execution_mode` and `tea_capability_probe` resolve through CLI flags, then `_bmad/tea/config.yaml`, then `module.yaml`. The test-review report records the resolved execution mode. [QMD:tea-testarch-temporal:releases.md] [SRC:src/workflows/testarch/bmad-testarch-test-review/steps-c/step-04-generate-report.md:L47]

The full history is in `references/pattern-release-context.md`.

## CORRECTION

**Source:** _bmad-output/.skf-stage/tea-testarch/provenance-map.json
**Pattern:** replaced by
**Affected:** Gotchas: parallel modes use /tmp (NFR worker temp-file timestamp)
**Detail:** "description": "The temp-file timestamp is an ISO string with colons and dots replaced by hyphens.",

## CORRECTION

**Source:** _bmad-output/tea-testarch-temporal/changelog.md
**Pattern:** replaced by
**Affected:** tea-evaluate runtime (post-v1.27.2, not in this skill)
**Detail:** The runtime reads that file without following a link and without waiting on it, so a service that puts a link, a named pipe or a file longer than 16 bytes in its place stops the run with exit 12 at once, and its timers and signal handlers keep running; it reads `adapter/http-probe-port.mjs` the same way when it checks that file's digest before each call, so a port file replaced by a pipe or a link during a run fails the call with `port-failure`.

## CORRECTION

**Source:** _bmad-output/tea-testarch-temporal/changelog.md
**Pattern:** replaced by
**Affected:** tea-evaluate runtime (post-v1.27.2, not in this skill)
**Detail:** The runtime does not sandbox the target's file system (Story 1.31), so it guards its own writes to the run directory: every directory and file in it is created afresh without following a link, from inside a directory the runtime made, held open until the command ends (so its inode number cannot pass to a directory the target makes), and confirmed before and after the write by device, inode and the path the system reports for it, `run.json` is replaced by renaming a new file over it, engine stages write into a private temp directory whose output is copied in, every file is read back, without blocking, only with the bytes the runtime wrote, and the run directory must hold exactly those entries before the preflight verdict, after the trials and before `run.json` says completed (exit 12 otherwise); a link a target plants there, or a directory it replaces or moves into your project with a link left in its place, stops the run with exit 12 before the runtime writes through it.

## CORRECTION

**Source:** _bmad-output/tea-testarch-temporal/changelog.md
**Pattern:** BREAKING
**Affected:** Migration: scoped output paths (gate-decision.json location)
**Detail:** - **Breaking: output paths.** Every TEA workflow now writes into its own folder under `{test_artifacts}`, and a file produced once per scope carries that scope in its name (#228).

## CORRECTION

**Source:** _bmad-output/tea-testarch-temporal/changelog.md
**Pattern:** BREAKING
**Affected:** unknown
**Detail:** `npm run test:lockfile-age-cache` holds that independent implementation to the one contract it and `eval-quality`'s own reach into `dist/gates/audit-lockfile-age.mjs` both read: the npm registry's `time` map, confirmed from the installed package's source to be all its `fetchTimeMap` does with the response either. `wrappy@1.0.2`, already locked in `package-lock.json`, is asserted against its real, immutable publish timestamp, fetched live and pinned here since a publish time never changes once set; the check skips rather than fails when the registry is unreachable, so a disconnected run cannot turn a network gap into a false defect. This does not prove the two implementations agree on every future release: it cannot compare against `eval-quality`'s own `fetchTimeMap` without the exact unexported-internals reach this change removes, so a redefinition on `eval-quality`'s side of what "publication time" means, away from the registry's own `time` map, would pass unnoticed here. What it holds is the realistic failure: TEA's own copy regressing, proven by breaking the field read (`meta.time` to `meta.versions`) and watching the check name the wrong value it got instead.

## CORRECTION

**Source:** _bmad-output/tea-testarch-temporal/changelog.md
**Pattern:** removed in
**Affected:** unknown
**Detail:** - `npm run test:lineage`, which runs the `field-ownership` gate over `tools/`, holding the probe and contract `schemaVersion` stamp to exactly `tools/generate-probes.js` and `tools/generate-contracts.js`. Scoped to `tools/` on purpose: `schemaVersion` is a name five of `eval-quality`'s twelve published artifact kinds each carry independently, and `test/lib/eval-quality-inputs.js` legitimately stamps three of the other kinds (`evaluatorConfiguration`, `isolationManifest`, `sealedRunRecord`) that these two generators never touch, so the gate would need as many declared writers as artifact kinds if it scanned `test/` too, which would authorize exactly the cross-kind drift it exists to catch. It generalizes a real, narrower incident: a hardcoded copy of the probe schema version once drifted from what `generate-probes.js` actually stamped and passed for months, caught only when a probe's declared leg count stopped matching what the sink recorded; that stale local copy has since been removed in favor of reading the constant the generator exports.

## CORRECTION

**Source:** _bmad-output/tea-testarch-temporal/changelog.md
**Pattern:** deprecated
**Affected:** unknown
**Detail:** - The check covers every harness rather than one. It runs each of the five that write a suite-result record under the scripted clock in its cheapest no-model mode, reaches `eval-all.js` through the one branch that writes a full summary and spawns nothing, asserts every duration and the record's `generatedAt` came from the port, and scans all seven harness sources for any reintroduced host-clock read. The scan covers `Date.now`, `performance.now`, `process.hrtime` and a no-argument `new Date()`, because grepping for `Date.now()` alone missed the exact line the `generatedAt` fix removed: putting it back passed the scan while reintroducing the defect. It requires no call parenthesis, because requiring one named `process.hrtime` as refused while refusing only the deprecated tuple spelling and letting `process.hrtime.bigint()` through, which is the documented current form. `new Date(mark)` stays allowed, since an argument makes it a conversion of a mark the port already gave. The scan is the only cover for `eval-contract-strength.js`, which writes a cost report under its own shape and declines `--agent-cmd`.

## CORRECTION

**Source:** _bmad-output/tea-testarch-temporal/changelog.md
**Pattern:** replaced by
**Affected:** unknown
**Detail:** - TEA's `eval-quality` devDependency moves from 3.0.0 to 3.4.0 across four pin bumps recorded individually above: 3.1.0 carries the schema-version constants, `compareDominance` and the `eval-quality-gates` binary; 3.2.0 publishes `lockfile-age.exclude`, `licences.undeclared` and `lockfile-age.cache` in their final shapes; 3.3.0 publishes `resolveCheck` and its evidence-resolution helpers off the top-level entry point and fixes the `dependency-direction` method-shorthand false positive; 3.4.0 adds `dated.claims[].asOf`, the doc-claims staleness pin. Eight `eval-quality-gates` consumer gates are adopted end to end, each behind its own `npm run test:*` script: `doc-counts`, `doc-claims` and `doc-invocations` hold every published count, prose claim and fenced command in `docs/` and `README.md` against the source that computes it; `dependency-direction` runs at zero violations rather than report-only; `package-boundary`, `field-ownership`, `licences` and `lockfile-age` are new outright. Every hand-rolled probing mechanism TEA wrote is replaced by `eval-quality`'s shipped adapter, each proven by its own conformance arm before any call site moved onto it: the corpus, clock and file-system arms all name a check now, joining the command-probe arm TEA already ran. `test/test-port-totality.js` carries the ledger of all six published arms: those four run for real, and the remaining two, `environment-probe` (the `api` arm, over HTTP) and `mcp-probe`, are recorded as having no subject in this repository to run against, since TEA authorizes no HTTP target and no tool server. Every artifact TEA writes stamps its `schemaVersion` from the constant the installed package exports for that kind, through `test/lib/eval-quality-inputs.js`'s `SCHEMA_VERSIONS` table, rather than a hand-maintained literal, and `npm run test:schema-versions` holds every stamp TEA commits, in source and on disk, to that same reading.

## CORRECTION

**Source:** _bmad-output/tea-testarch-temporal/changelog.md
**Pattern:** superseded by
**Affected:** tea-enforce.cjs hook script
**Detail:** `eslint.config.mjs` disabled `no-undef`, `no-unused-vars` and `no-unreachable` across `cli/**`, `tools/**`, `test/**` and the hook scripts copied into user projects, conceding in its own comment that the second avoided "failing CI on incidental unused vars". `no-undef` and `no-unreachable` had zero violations once turned on: `eslint-plugin-n`'s flat config already declares the Node globals these scripts use, so the suppression was never load-bearing. `no-unused-vars` found 15 across the whole story, eight the `const { key, ...rest } = value` idiom (now covered by `ignoreRestSiblings: true` rather than a per-site exception) and seven genuine dead code, each traced to its root and deleted rather than silenced: a dead trigger-shortcut helper and an already-abandoned path-vs-module validation thread in `test/schema/agent.js` and its byte-identical `tools/schema/agent.js` (whose JSDoc is corrected to describe what the function actually does now, rather than the module slug it no longer derives), a dead `CLI` path constant, two reads made redundant by a file's own uniform helper, three tools-directory leftovers (a recursive collector called only by itself, a regex superseded by the next line's own comment, and a capture group never read), and two more surfaced by rebasing onto later work: a dead local in `test/test-contracts.js` superseded by its own error-message string, and a dead import in `test/test-eval-replay.js` made redundant by the file's own uniform `readJson` helper.

## CORRECTION

**Source:** _bmad-output/tea-testarch-temporal/changelog.md
**Pattern:** replaced by
**Affected:** unknown
**Detail:** - The four top-level keys in `test/fixtures/trace-eval/ground-truth.json` that no check read. `nonDeterministicReportedValues` said the seeded set's `tests.cases` was 10 or 11 and its api test count 5 or 6; the evidence entries give 6 api tests under the first reading and 7 under the second, so the key's own arithmetic was wrong and nothing could have noticed, and step-04 has since made the count derivable by keeping a rejected test out of every total. It is gone, replaced by an `expectedTestInventory` block per set that `--validate-only` recomputes from the evidence entries and the harness scores as `tests.files`, `tests.cases` and `coverage.by_level.*.tests`, plus a check that the recommendations name every criterion in the critical, high and partial buckets, which is what the key's fourth entry asked for and nothing did. Its stale-versus-unverifiable entry was already scored through `expectedLiveEvidence.environmentDependentPair`. `negativeControls` and `rejectedCases` stay and are bound: each control id has a row in `NEGATIVE_CONTROL_ENFORCEMENT` naming the threshold that enforces it, each rejected case has a predicate in `REJECTED_CASE_EXCLUSIONS` that every fixture set is held to, and `--validate-only` fails on an id with no row, a row with no id, or a set that carries a rejected case; verified by adding each of those and watching the check fail. The fifth rejected case, a planted quality defect, has nothing in the corpus to check against and moved to the fixture README as prose. `oracles` described the harness, had nothing to check it against, and moved to the same README, rewritten to match the checks that exist.

## Key Types

- **Gate status:** `PASS | CONCERNS | FAIL | WAIVED`; the internal default is `NOT_EVALUATED`. [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L52] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-05-gate-decision.md:L264]
- **Collection mode:** `contract_static`, `inventory_only`, `runtime_manifest`, `deferred_shared`, `waived`, `restricted`, `inaccessible`. [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L34]
- **Trace coverage per item:** `FULL`, `PARTIAL`, `NONE`, `UNIT-ONLY`, `INTEGRATION-ONLY`. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-03-map-criteria.md:L43]
- **NFR status:** `PASS`, `CONCERNS`, `FAIL`, `N/A`; a domain takes its worst finding. [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/nfr-status-definitions.md:L21] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/nfr-status-definitions.md:L23] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/nfr-status-definitions.md:L26] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/nfr-status-definitions.md:L28] [SRC:src/workflows/testarch/bmad-testarch-nfr/steps-c/nfr-status-definitions.md:L32]
- **Test-review recommendation:** `Approve`, `Approve with Comments`, `Request Changes`, `Block`. [SRC:src/workflows/testarch/bmad-testarch-test-review/test-review-template.md:L28]
- **Risk:** Probability 1–3 × Impact 1–3; a score of 6 or more is high. [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-03-risk-and-testability.md:L66] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-03-risk-and-testability.md:L67] [SRC:src/workflows/testarch/bmad-testarch-test-design/steps-c/step-03-risk-and-testability.md:L68]
- **Execution mode:** `auto`, `subagent`, `agent-team`, `sequential`. [SRC:src/module.yaml:L97]

## Architecture at a Glance

- **Workflow skill** (`src/workflows/testarch/bmad-testarch-<name>/`): `SKILL.md` (mode menu), `workflow.yaml` (variables and outputs), `customize.toml`, `instructions.md`, `checklist.md`, templates, and `steps-c/` (Create/Resume), `steps-v/` (Validate), `steps-e/` (Edit). [SRC:src/workflows/testarch/bmad-testarch-trace/SKILL.md:L82] [SRC:src/workflows/testarch/bmad-testarch-trace/SKILL.md:L83] [SRC:src/workflows/testarch/bmad-testarch-trace/SKILL.md:L84] [SRC:src/workflows/testarch/bmad-testarch-trace/SKILL.md:L85] [SRC:src/workflows/testarch/bmad-testarch-trace/workflow.yaml:L111] [SRC:src/workflows/testarch/bmad-testarch-trace/customize.toml:L38]
- **Knowledge:** each skill has a `resources/tea-index.csv` over `resources/knowledge/` fragments, loaded selectively. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-01-load-context.md:L5] [SRC:src/agents/bmad-tea/SKILL.md:L113] [SRC:src/agents/bmad-tea/resources/tea-index.csv:L1]
- **Progress:** outputs carry `stepsCompleted`, `lastStep` and `lastSaved` frontmatter, and Resume routes on `lastStep`. [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-01-load-context.md:L135] [SRC:src/workflows/testarch/bmad-testarch-trace/steps-c/step-01b-resume.md:L76]
- **Agent:** `src/agents/bmad-tea/` (`SKILL.md`, `customize.toml` menu). [SRC:src/agents/bmad-tea/SKILL.md:L3] [SRC:src/agents/bmad-tea/customize.toml:L57]
- **Registration:** `src/module.yaml` (config prompts) and `src/module-help.csv` (catalogue rows). [SRC:src/module.yaml:L25] [SRC:src/module-help.csv:L1]

## Full API Reference

Pattern-oriented reference files (Tier 2):

- `references/pattern-gate-decision.md`: trace inputs, steps, eligibility, rules, overlays, waivers, `gate-decision.json` and `e2e-trace-summary.json`.
- `references/pattern-config-and-registration.md`: `module.yaml` keys and defaults, `module-help.csv` rows, the `bmad-tea` menu, `tea-index.csv`, `customize.toml`.
- `references/pattern-test-design.md`: mode detection, outputs, risk scoring and priorities.
- `references/pattern-framework-and-ci.md`: framework selection, scaffold, the `tea-enforce.cjs` hook, CI platforms and quality gates.
- `references/pattern-atdd-and-automate.md`: ATDD red-phase contract, automate workers, shared execution-mode resolution.
- `references/pattern-test-review.md`: scoring ledger, grades, recommendation, criteria registry.
- `references/pattern-nfr.md`: thresholds, statuses, roll-up, gate YAML.
- `references/pattern-release-context.md`: release notes, upcoming changes and issues (T2).
