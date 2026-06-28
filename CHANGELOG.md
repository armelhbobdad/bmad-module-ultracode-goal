# Changelog

All notable changes to this project will be documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Cross-Session Recall** (optional): when [claude-mem](https://github.com/thedotmack/claude-mem) is installed and cross_session_recall is set to on, the executor consults prior runs of the same repo during Ingest and Preflight and records one structured outcome at Finalize, advisory only, hook-latched, never part of the gate. No effect when claude-mem is absent. Off by default.

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
* **ucg:** step-4 fourth AND-clause — union formalize reds + verdict==ready (story 2-4) ([3f1aba3](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/3f1aba3474ecf5816d9255c85d0590cb8fe4d587))
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
