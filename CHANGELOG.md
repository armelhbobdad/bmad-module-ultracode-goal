# Changelog

All notable changes to this project will be documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Cross-Session Recall** (optional): when [claude-mem](https://github.com/thedotmack/claude-mem) is installed and cross_session_recall is set to on, the executor consults prior runs of the same repo during Ingest and Preflight and records one structured outcome at Finalize, advisory only, hook-latched, never part of the gate. No effect when claude-mem is absent. Off by default.

### Fixed

- **Gate: `--story` now fails closed on a genuine no-match** (potentially breaking). `scripts/gate_eval.py --story <id>` used to fall back to an unscoped read whenever nothing matched the requested id, so a story that produced no trace artifacts at all silently resolved a *neighbouring* story's gate: an unevaluated story could report `PASS` / `advance`. When the trace dir names its reports or gate decisions per story (`trace-2-1.md`, `gate-decision-4.json`), a `--story` that matches nothing now returns `gate_status: NOT_EVALUATED`, which routes to `escalate`, with a reason naming the absent story. The documented single-story fallback is preserved: a dir whose candidates are all generically named (`trace.md`, `gate-decision.json`) still resolves unscoped. Breaking only for anyone who relied on the silent fallback in a per-story-named dir, where the old behaviour returned another story's verdict.
- **Finalize: the gate trail refuses to render when no story is named** (potentially breaking). `scripts/gate_trail.py` treated `--story` as one of its optional sources, so an invocation naming no story exited `0` and wrote a well-formed `gate-trail.md` carrying `Stories: 0` and no sections, which the stage then names in the run report as delivered evidence: an evidence trail that traces nothing is the failure mode an evidence trail exists to prevent. A blank id (`--story ""`) rendered an anonymous section of nothing but `n/a`. At least one non-empty `--story` is now required, and both shapes exit `2` with a usage line having written nothing, the same invocation-error lane `--run-dir` and `--profile` already occupied. Fail-soft is unchanged for the *sources*: a missing or unreadable checklist, trace report, gate file or baseline still renders `n/a` and the trail still completes. Breaking only for anyone invoking the script with no story ids, where the old behaviour produced an empty document.
- **Formalize: an empty in-scope story set no longer reads `ready`.** `scripts/formalize_check.py` iterates the Epic's story files for every per-story and per-AC check, so an Epic whose story files do not exist scored zero gaps and returned `verdict: ready` with `stories_with_ac: 0`, satisfying the launch gate vacuously. An empty story set now emits a `no_in_scope_stories` mechanical gap (severity high, remediable, naming the Epic and the impl-artifacts dir searched) that counts toward `mechanical_budget` like any other, so the verdict is `remediable`.
- **Formalize: a story that declares no acceptance criteria no longer reads `ready`** (potentially breaking). The empty-story-set guard above keys on the story file being *absent*, but a story file that exists and declares no AC iterates the per-story and per-AC checks zero times just the same, so it contributed no gap and the Epic still scored a clean `verdict: ready` with `stories_with_ac: 0`, which is the verdict the launch gate treats as go. Reproduced on three shapes: an empty file, an `## Acceptance Criteria` heading with no items, and story prose with no AC section at all. Each AC-less story now emits a `story_without_ac` mechanical gap (severity high, remediable, naming the story file) that counts toward `mechanical_budget`, so the verdict is `remediable`. This also closes the landing zone of the other guard's own remediation: the create-story scaffold that clears `no_in_scope_stories` writes story files, and an AC-less stub would otherwise have flipped `remediable` straight back to `ready`. Breaking for any Epic whose stories are stubs, which now blocks at preflight instead of launching.

- **Health check: a fixed finding no longer suppresses its own regression.** `scripts/health_check_fp.py` closed its disposition vocabulary at `created` / `reacted` / `commented` / `queued`, so there was no way to record that a finding had been *fixed*. A fingerprint therefore suppressed a repeat report forever, and a genuine regression of a fixed defect was silently swallowed, which is the one report the loop most needs to surface. There is now a fifth action, `resolved`, and `seen` returns the suppression verdict rather than mere cache presence: `{"seen": bool, "status": "unseen" | "handled" | "regression" | "unrecognized", "record": ...}`. A `resolved` record does not suppress and still returns the prior record, so the recurrence is reported and linked to the original instead of filed as a first sighting. An unrecognized action does not suppress either, on the same reasoning: a duplicate report is closed automatically by the dedup Action, whereas a silenced regression is caught by nothing. The local queue path no longer overwrites a `resolved` record with `queued`, which would otherwise have re-armed the suppression on the next unattended run. The seen-cache is machine-local, so where a record carries an issue URL the health check now prefers that issue's own open or closed state, which is shared.

### Deprecated

- **`story_token_budget`** is deprecated and is now a no-op. The key is still shipped in `customize.toml`, still accepted, and still resolves, so existing team and user overrides keep working and nothing errors; it simply has no effect. Nothing reads it any more: the Stop hook counts turns only, and the preflight stage no longer injects a token budget into the hook environment. The runaway bound is `max_turns_per_story`, enforced by the "stop after N turns" clause in the run condition and by the gate's re-loop budget, with the Stop hook as the advisory recorder. Use `max_turns_per_story` instead.

## [0.5.1](https://github.com/armelhbobdad/bmad-module-ultracode-goal/compare/v0.5.0...v0.5.1) (2026-07-12)

### Bug Fixes

* **deps:** pin figlet to 1.11.0 (1.11.1 crashes at require via npx) ([03c6792](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/03c6792647f7fe287f1533485d2d975aa9ac5c29))
## [0.5.0](https://github.com/armelhbobdad/bmad-module-ultracode-goal/compare/v0.4.0...v0.5.0) (2026-07-12)

### ⚠ BREAKING CHANGES

* **ucg:** the installer no longer installs UCG to non-Claude
providers (Codex, Cursor, and the rest). UCG installs to Claude Code only.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>

### Features

* **ucg:** make UCG Claude-Code-only ([13e3e3b](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/13e3e3b9072c3603da39fb3a1d5dc5b1ff5992ec))

### Bug Fixes

* **ucg:** defer to formalize's strict sprint-status read on non-default tracks ([b3494b5](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/b3494b57af701c62425b5e2b3447eda9f6649f75))
* **ucg:** disarm stale prior-run hooks before the preflight remediation commit ([6190858](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/6190858f69ca34a0562c141f81af2a77341f194c))
* **ucg:** document hand-authored nfr/test-review shapes for the non-web gate path ([92dd7d0](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/92dd7d0580153490cc85c120fbda1dc849a84297))
* **ucg:** isolate per-story commits when stage 3 pre-generates sibling tests ([5a65690](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/5a65690b807b143f815d9d165f360b1d9a4ac6f1))
* **ucg:** key isolated tracks to a numeric epic prefix for the rollup ([447b27b](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/447b27b56daa3f198c878e94197bf1a8671ca62a)), closes [#33](https://github.com/armelhbobdad/bmad-module-ultracode-goal/issues/33)
* **ucg:** make the Epic-level gate trace-only on both execution paths ([4305d18](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/4305d1842b97d5e900465345007e9e7ee9377b75))
* **ucg:** note async-spawn result retrieval for the preflight scan subagent ([5553b0a](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/5553b0a76d79c5099d1be2178add46f92b753839))
* **ucg:** re-verify each story on the committed HEAD before advancing ([9c965e3](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/9c965e36ae44fd68eb0d9b2b55bd96bc5287b98a))
* **ucg:** run-scope the async preflight-scan retrieval file ([95ec887](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/95ec887c394a0b3f120ac70de1af402b6da29821))
* **ucg:** scope colliding/cross-file epic initiatives to an isolated track ([76128da](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/76128da0a49af92471df22cdfaf5c6028e371019))
* **ucg:** scope the per-story test run to catch cross-package regressions ([5c42d79](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/5c42d79a1589e2ca5a4107f37620f3f07d5f6378))
## [0.4.0](https://github.com/armelhbobdad/bmad-module-ultracode-goal/compare/v0.3.0...v0.4.0) (2026-06-28)

### Features

* **formalize:** formalize_check.py readiness kernel (story 1-1) ([7a93aa3](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/7a93aa37da73504d00b60accf10653cccf2d1ae2))
* **formalize:** four Epic-11 JUDGMENT floor classes + no-dark-pass catch-all (story 1-2) ([c590e31](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/c590e31fce45a051a8035fd34ee97952e8322970))
* **ucg-awareness:** four planning shaping fragments -> persistent_facts (story 1-4) ([5eafe45](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/5eafe45eb9e156e15564dc1ebdcee13982a74a25))
* **ucg-formalize:** standalone /ucg-formalize SKILL.md with five-key envelope (story 1-3) ([d435045](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/d4350456fc4c46401d0e66415b979fc636ab17fa))
* **ucg-help:** module-help.csv /ucg-formalize row with module-unique menu code (story 1-7) ([22e23be](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/22e23be911752466e9e9ec7126551df022831e3e))
* **ucg-install:** installer Step 6b wires UCG-awareness shaping into present planning workflows (story 1-6) ([600d986](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/600d986bec6e40e88c907e349e26033dfa6ddd54))
* **ucg-merge:** --remove true no-op + decline-no-op proof; harden uninstall reversibility (story 1-8) ([9720576](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/9720576e33061cf43a52786c0ab20af0066ede9e))
* **ucg-merge:** merge_customization.py stamp-scoped strip-then-reappend into workflow.persistent_facts (story 1-5) ([ef11212](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/ef1121248a83da7141d7bcfb17768b015e502905))
* **ucg-portability:** portability-honesty docs + Test Suite 6 + operator-benchmark rubric (story 1-11) ([864d238](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/864d238362c4bbc5eb5a0bd099935a8f4476478f))
* **ucg:** formalize wall-clock measurement protocol, no authored ceiling (story 2-8) ([240046e](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/240046e64a4f36a8f4c128df28e18a5227a81e07))
* **ucg:** headless envelope adapter routes formalize RED through canonical JSON (story 2-5) ([ce635e6](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/ce635e6042ec0fdedc88259ad8307ab8a338d6a9))
* **ucg:** machine-check the Phase-3 evidence gate (story 3-1) ([d7e9485](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/d7e94854c1ec0ca64a6b62e4610098a2766e38a1))
* **ucg:** preflight step-1b runs formalize_check.py readiness kernel (story 2-1) ([0ffc4d3](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/0ffc4d33844983cf647b671041c61597cf712687))
* **ucg:** SKILL launch Non-negotiable requires formalize_check.py returns ready (story 2-6) ([45c44a9](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/45c44a9c40a33e238d68b4986c6d32f18565cba3))
* **ucg:** step-2 fold-in + leaked-TEA-artifact MOVE remediation (story 2-2) ([4a15804](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/4a1580401e4d2164396fde0d02dab8af0e00d186))
* **ucg:** step-3 seeds formalize judgment_candidates into the subagent (story 2-3) ([8ba0925](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/8ba0925382fce32e0771bfecdfa17fe202eea54f))
* **ucg:** step-4 fourth AND-clause: union formalize reds + verdict==ready (story 2-4) ([3f1aba3](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/3f1aba3474ecf5816d9255c85d0590cb8fe4d587))
* **ucg:** TEA shaping fragments + formalize reader-not-evaluator (story 2-7) ([a21dd25](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/a21dd250ddcd455abc7d6a4a8c27c6634b79c208))

### Bug Fixes

* **docs:** quote frontmatter descriptions broken by the em-dash sweep ([be2a9bf](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/be2a9bff1e5273456a73493205ec4cc47b6773eb))
* **preflight:** detect pytest and npm test harnesses, not just browser configs ([9374e84](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/9374e84cfceed75e278f8458a2154a67987ae7f1))
* **ucg-gate:** --story selector resolves the right story in a shared trace dir (fp-910f0fd) ([83abd05](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/83abd05f71683046e0eaa8f21c0fa8767ec0067d))
* **ucg:** drop Claude-Code provider tokens from ucg-formalize timing prose ([88e6722](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/88e6722a0db32669d03719c35aaacf9474ca0b71))
* **ucg:** exclude UCG impl-artifacts from leaked-TEA detector; guard epic-gate for partial epics ([6d0c670](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/6d0c670aeb99bda63960ab0db0a422db462a2508))
* **ucg:** make Epic-2 timing + re-point tests Windows-portable ([bef0431](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/bef04319949ab980e9d0c1a3785768ff66543d4d)), closes [#15](https://github.com/armelhbobdad/bmad-module-ultracode-goal/issues/15)
* **ucg:** quality-scan hardening of both UCG skills (0 high/critical) ([2ae52bc](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/2ae52bc394d7100c8109d567eb97de543ac545a0))
* **ucg:** realign help-CSV source header to canonical preceded-by/followed-by ([6bf5be2](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/6bf5be2dde1d1d7ff53a8e032fc89427777f9417))
## [0.3.0](https://github.com/armelhbobdad/bmad-module-ultracode-goal/compare/v0.2.0...v0.3.0) (2026-06-04)

### Features

* **module:** register UCG in the BMad help catalog + standalone-module layout ([df1c769](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/df1c769b668faa733286ae9d7e8565c0f1885edb))

### Bug Fixes

* **skill:** clear path-standard lints in shipped content ([342db78](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/342db780baa56e43d20c115f89619991f0354338))
## [0.2.0](https://github.com/armelhbobdad/bmad-module-ultracode-goal/compare/v0.1.1-alpha.0...v0.2.0) (2026-06-04)

### Features

* **skill:** add Cross-Session Recall: optional claude-mem leverage, advisory-only and hook-latched ([dd212c8](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/dd212c8cbad14fd21b3fc9a37eaec97563e23717))
* **website:** add Astro Starlight docs site with light-first indigo theme ([f824cd4](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/f824cd422a489f11ada14a107bdd11a88b36ef6d))

### Bug Fixes

* **cli:** keep the installer banner frame intact at any terminal width ([502b690](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/502b690154880394a36760798e29c1c18b5bb9bd))
* **scripts:** pin recall/observation stdio to UTF-8: Windows cp1252 console crashed multibyte JSON output ([9b76ed5](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/9b76ed56e59ead32097cb52d4f30424216297da9))
* **website:** drop the footer background slab ([272867f](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/272867fbeacd827043dfe8ba2892cb861ef84936))
## [0.1.1-alpha.0](https://github.com/armelhbobdad/bmad-module-ultracode-goal/compare/v0.1.0...v0.1.1-alpha.0) (2026-06-04)
## [0.1.0] - 2026-06-03

### Added

- The **ultracode-goal** skill: a six-stage autonomous epic conductor (Ingest & Scope, Preflight, Define Done, Execute, Gate, Finalize) that delivers a BMAD Epic to a machine-checked Definition-of-Done. Completion is decided by `gate_eval.py` reading TEA's deterministic `gate-decision.json`, never by the model's own judgment. Ships `PreToolUse`/`Stop` hooks that enforce git invariants and budget, plus a 72-test pytest suite covering the deterministic scripts.
- Repository standardization: the `npx bmad-module-ultracode-goal install` installer, CI quality gates, an OIDC-backed release pipeline, the docs suite, and the workflow health-check loop with fingerprint-deduped issue reporting.
