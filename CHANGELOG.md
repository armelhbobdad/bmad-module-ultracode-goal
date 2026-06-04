# Changelog

All notable changes to this project will be documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Cross-Session Recall** (optional): when [claude-mem](https://github.com/thedotmack/claude-mem) is installed and cross_session_recall is set to on, the executor consults prior runs of the same repo during Ingest and Preflight and records one structured outcome at Finalize — advisory only, hook-latched, never part of the gate. No effect when claude-mem is absent. Off by default.

## [0.3.0](https://github.com/armelhbobdad/bmad-module-ultracode-goal/compare/v0.2.0...v0.3.0) (2026-06-04)

### Features

* **module:** register UCG in the BMad help catalog + standalone-module layout ([df1c769](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/df1c769b668faa733286ae9d7e8565c0f1885edb))

### Bug Fixes

* **skill:** clear path-standard lints in shipped content ([342db78](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/342db780baa56e43d20c115f89619991f0354338))
## [0.2.0](https://github.com/armelhbobdad/bmad-module-ultracode-goal/compare/v0.1.1-alpha.0...v0.2.0) (2026-06-04)

### Features

* **skill:** add Cross-Session Recall — optional claude-mem leverage, advisory-only and hook-latched ([dd212c8](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/dd212c8cbad14fd21b3fc9a37eaec97563e23717))
* **website:** add Astro Starlight docs site with light-first indigo theme ([f824cd4](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/f824cd422a489f11ada14a107bdd11a88b36ef6d))

### Bug Fixes

* **cli:** keep the installer banner frame intact at any terminal width ([502b690](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/502b690154880394a36760798e29c1c18b5bb9bd))
* **scripts:** pin recall/observation stdio to UTF-8 — Windows cp1252 console crashed multibyte JSON output ([9b76ed5](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/9b76ed56e59ead32097cb52d4f30424216297da9))
* **website:** drop the footer background slab ([272867f](https://github.com/armelhbobdad/bmad-module-ultracode-goal/commit/272867fbeacd827043dfe8ba2892cb861ef84936))
## [0.1.1-alpha.0](https://github.com/armelhbobdad/bmad-module-ultracode-goal/compare/v0.1.0...v0.1.1-alpha.0) (2026-06-04)
## [0.1.0] - 2026-06-03

### Added

- The **ultracode-goal** skill — a six-stage autonomous epic conductor (Ingest & Scope, Preflight, Define Done, Execute, Gate, Finalize) that delivers a BMAD Epic to a machine-checked Definition-of-Done. Completion is decided by `gate_eval.py` reading TEA's deterministic `gate-decision.json`, never by the model's own judgment. Ships `PreToolUse`/`Stop` hooks that enforce git invariants and budget, plus a 72-test pytest suite covering the deterministic scripts.
- Repository standardization — the `npx bmad-module-ultracode-goal install` installer, CI quality gates, an OIDC-backed release pipeline, the docs suite, and the workflow health-check loop with fingerprint-deduped issue reporting.
