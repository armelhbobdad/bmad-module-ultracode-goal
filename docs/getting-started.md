# Getting Started

Install UltraCode Goal into a BMAD project, point it at an Epic, and let it run that Epic to a gate-passed Definition-of-Done. This page covers prerequisites, install, the first-run walkthrough, and the run-mode flags.

## Prerequisites

UltraCode Goal conducts BMAD and TEA skills and runs deterministic Python under `uv`. You need:

| Tool | Required for | Install |
|------|--------------|---------|
| Node.js >= 22 | Installation, `npx` commands | <https://nodejs.org> |
| Python >= 3.10 | The deterministic gate, preflight, and hook scripts (run via `uv`) | <https://www.python.org> |
| `uv` | Running the module's Python scripts with automatic dependency management | <https://docs.astral.sh/uv/> |
| `git` | Epic-branch isolation and per-story commits (the real rollback) | <https://git-scm.com> |
| `gh` (GitHub CLI) | Submitting or queuing [health-check](health-check.md) findings | <https://cli.github.com> |
| A BMAD project with an Epic | The unit of delivery — a `_bmad/` install, a `sprint-status.yaml`, and at least one Epic with stories | see [bmad-method.org](https://docs.bmad-method.org) |

The run also depends on recent Claude Code primitives: `/goal`, dynamic workflows, and Auto Memory. The preflight script version-gates these and reports a mechanical blocker if the installed Claude Code is below the minimum any of them needs (see [troubleshooting](troubleshooting.md)).

## Install

```bash
npx bmad-module-ultracode-goal install
```

The installer is interactive — it prompts for the project name and which IDEs to configure, then copies the skill into place. As an alternative, the module can be installed from the plugin marketplace entry (`.claude-plugin/marketplace.json`) the same way as other BMAD plugins.

## First run

Invoke the skill with one of its trigger phrases — "run an epic autonomously", "execute this epic", "ultracode goal", or "autonomously deliver the epic" — in a BMAD project.

1. **Name the Epic.** Stage 1 opens the floor: name the Epic, or drop any context (a story id, a branch, a paste of the Epic body). The skill fills the gaps from the BMAD artifacts. If `_bmad/` config, `sprint-status.yaml`, and any Epic are *all* absent, this is not a BMAD project — the skill says so and stops, pointing you at `bmad-bmb-setup` and `bmad-sprint-planning`.
2. **Preflight runs.** Stage 2 is the autonomy gate. It runs a mechanical check (`preflight_check.py`), auto-remediates the fixable ambers (scaffolding the test framework, generating missing acceptance criteria, pre-creating TEA output dirs, and so on), then adds a semantic scan for undecided product or architecture decisions the script cannot see. The run launches **only** when the post-remediation intervention budget is zero and the semantic scan found no red blocker. A single undecided architecture decision stops the run here rather than letting an unattended run guess it.
3. **The launch briefing.** On an attended run, before the first unattended action the skill prints a one-screen briefing: what is about to run, the worst-case turn envelope, the autonomy line ("from here I will not ask you anything"), the kill switch (Ctrl-C, or delete the Epic branch — `/rewind` will not help), and where to watch (the run's `.decision-log.md` and `run-status.json`). One soft confirm crosses the line.

From there the run is autonomous: it defines done with TEA, executes each story to a green commit, gates each one deterministically, and finalizes with a run report and the deferred-work ledger. See [how it works](how-it-works.md) for the full stage-by-stage narration.

## Run-mode flags

| Flag | Effect |
|------|--------|
| `--light` | Trace-only gate. Downscopes from the full TEA chain to `bmad-testarch-trace` plus `gate_eval.py --profile light` — no NFR/test-review AND. |
| `--parallel` | Experimental worktree fan-out. Each story runs isolated in its own worktree; no mid-run input. The sequential `/goal` spine is the default and recommended path — see [parallel mode](parallel-mode.md). |
| `--yes` | Skips Stage 1's open-floor invite and the launch confirm. The launch briefing still prints. **Never** skips the hard preflight gate. |
| `-H` | Headless. Runs non-interactively, never prompts (an unresolvable secret becomes a red blocker, not a question), and emits one JSON object at every exit point. |
| `--retro` | Runs the close-out retrospective (`bmad-retrospective`). Interactive runs offer it at Epic close anyway; headless runs it only when `--retro` is passed. |

## Hook security

At preflight the skill auto-merges its **PreToolUse** guard and **Stop** budget hook into `.claude/settings.local.json` — a machine-local, gitignored file, honored after the workspace trust dialog. These hooks are the enforcement layer that blocks a commit on a protected branch and bounds a runaway story; they are not shared into the repo. Because they execute on your machine, review what gets merged: see [SECURITY.md](../SECURITY.md) for the hook-security model and what to check before granting trust.
