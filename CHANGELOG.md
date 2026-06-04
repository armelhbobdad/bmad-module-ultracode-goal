# Changelog

All notable changes to this project will be documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Cross-Session Recall** (optional): when [claude-mem](https://github.com/thedotmack/claude-mem) is installed and cross_session_recall is set to on, the executor consults prior runs of the same repo during Ingest and Preflight and records one structured outcome at Finalize — advisory only, hook-latched, never part of the gate. No effect when claude-mem is absent. Off by default.

## [0.1.1-alpha.0](https://github.com/armelhbobdad/bmad-module-ultracode-goal/compare/v0.1.0...v0.1.1-alpha.0) (2026-06-04)
## [0.1.0] - 2026-06-03

### Added

- The **ultracode-goal** skill — a six-stage autonomous epic conductor (Ingest & Scope, Preflight, Define Done, Execute, Gate, Finalize) that delivers a BMAD Epic to a machine-checked Definition-of-Done. Completion is decided by `gate_eval.py` reading TEA's deterministic `gate-decision.json`, never by the model's own judgment. Ships `PreToolUse`/`Stop` hooks that enforce git invariants and budget, plus a 72-test pytest suite covering the deterministic scripts.
- Repository standardization — the `npx bmad-module-ultracode-goal install` installer, CI quality gates, an OIDC-backed release pipeline, the docs suite, and the workflow health-check loop with fingerprint-deduped issue reporting.
