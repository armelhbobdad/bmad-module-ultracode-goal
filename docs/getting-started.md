---
title: Getting Started
description: Install UltraCode Goal, point it at a BMAD Epic, and walk the first autonomous run from install through preflight, gate, and run report.
---

Install UltraCode Goal into a BMAD project, point it at an Epic, and let it run that Epic to a gate-passed Definition-of-Done. This page covers prerequisites, install, the first-run walkthrough, and the run-mode flags.

## Prerequisites

UltraCode Goal conducts BMAD and TEA skills and runs deterministic Python under `uv`. You need:

<!-- tool-requirements:start -->
<!-- Generated from tools/tool-requirements.yaml by `node tools/tool-requirements.js --write`: edit that file, not this table. -->

| Tool                         | Used for                                                                                                                                                                                                                                                                                                                                                                                   | Minimum | Tested on      | Install                                                                     |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------- | -------------- | --------------------------------------------------------------------------- |
| Claude Code                  | **The runtime: non-negotiable.** UCG composes Auto Mode, Auto Memory, and runtime hooks, which only exist in Claude Code, and writes each story's Definition-of-Done as a `/goal`-style condition; the autonomous run cannot execute anywhere else. Preflight refuses to launch below the minimum                                                                                          | 2.1.154 | 2.1.301        | <https://claude.com/product/claude-code>                                    |
| Node.js                      | Installation, `npx` commands                                                                                                                                                                                                                                                                                                                                                               | 22      | 22, 24         | <https://nodejs.org>                                                        |
| Python                       | The deterministic gate, preflight, and hook scripts (run via `uv`)                                                                                                                                                                                                                                                                                                                         | 3.11    | 3.11, 3.12     | <https://www.python.org>                                                    |
| `uv` (Python package runner) | Running the module's Python scripts with automatic dependency management                                                                                                                                                                                                                                                                                                                   | none    | 0.13.1         | <https://docs.astral.sh/uv/getting-started/installation/>                   |
| `git`                        | Epic-branch isolation and per-story commits (the real rollback)                                                                                                                                                                                                                                                                                                                            | none    | 2.55.0, 2.56.0 | <https://git-scm.com/downloads>                                             |
| `gh` (GitHub CLI)            | Submitting or queuing [health-check](./health-check.md) findings                                                                                                                                                                                                                                                                                                                           | none    | not recorded   | <https://cli.github.com>                                                    |
| BMAD Method                  | The Epic toolbox UCG conducts, `bmad-sprint-planning`, `bmad-code-review` and the rest. No deprecated shims are needed, since UCG ships its own story skills (see below)                                                                                                                                                                                                                   | 6.2     | 6.12.0         | <https://docs.bmad-method.org>                                              |
| TEA (Test Architect)         | **The gate: non-negotiable.** UCG invokes the `bmad-testarch-*` skills to produce the `gate-decision.json` that `gate_eval.py` reads. Required in both profiles: `--light` still runs test-design and trace. Supported: TEA 1.27.x with BMAD Method 6. TEA 2.0 and later, and BMAD 7, are not supported yet. Preflight refuses to launch without the skills the run's profile delegates to | none    | 1.27.2         | <https://github.com/bmad-code-org/bmad-method-test-architecture-enterprise> |
| A BMAD project with an Epic  | The unit of delivery: a `_bmad/` install, a `sprint-status.yaml`, and at least one Epic with stories                                                                                                                                                                                                                                                                                       |         |                | see <https://docs.bmad-method.org>                                          |

<!-- tool-requirements:end -->

**Minimum** is the oldest version UCG accepts; for Claude Code it is the version preflight refuses to launch below. **Tested on** lists the versions UCG's own runs use: CI, the install smoke test or a named Epic run (the README's "Tested with" table, which also records that run's profile). `none` means UCG sets no minimum for the tool yet, and `not recorded` means no UCG run has recorded a version of it yet.

The run also depends on recent Claude Code primitives: dynamic workflows and Auto Memory, plus `/goal` if you start one yourself. The preflight script version-gates these and reports a mechanical blocker if the installed Claude Code is below the minimum any of them needs (see [troubleshooting](./troubleshooting.md)).

**No BMAD shims needed.** UltraCode Goal ships its own story skills, `ucg-create-story` and `ucg-dev-story`, adapted from BMAD Method's `bmad-create-story` and `bmad-dev-story`, which BMAD 6.12 made opt-in shims (a fresh install leaves them out, and the installer recommends declining them) and v7 removes. UCG's installer copies both beside the `ultracode-goal` skill, so a BMAD install made without shims runs UCG as it is. While either is missing from `.claude/skills/`, preflight reports a non-remediable blocker and the run does not launch; run `npx bmad-module-ultracode-goal update` from the project root to restore them, or `install` where UCG was never installed in the project (a plugin-marketplace install alone ships neither). If you installed BMAD with `--shims`, its own `bmad-create-story` and `bmad-dev-story` stay yours to run by hand, and a UCG run never uses them. A team override written for them (`_bmad/custom/bmad-create-story.toml` or `bmad-dev-story.toml`) no longer reaches a UCG run: copy what it holds to `_bmad/custom/ucg-create-story.toml` or `ucg-dev-story.toml`, which UCG's skills read the same way.

**Supported BMAD and TEA.** UCG supports BMAD Method 6 with TEA 1.27.x. BMAD Method 6.12.2 and later install TEA 1.27.2, while an older BMAD 6 installer can pick a later TEA. TEA 2.0 and later, and BMAD 7, are not supported yet: TEA 2.0 moved to BMAD 7's module format, and TEA 3.0 renamed the `bmad-testarch-*` skills UCG calls to `bmad-tea-*`. Preflight refuses to launch while a TEA skill the run's profile delegates to is missing from `.claude/skills/`. It checks skill names, not the TEA version, so it does not catch TEA 2.x, which kept the old names. Production needs all eight `bmad-testarch-*` skills. `--light` needs `bmad-testarch-framework`, `bmad-testarch-test-design` and `bmad-testarch-trace`. Add TEA from the project root with `npx bmad-method install`, with the `tea` module selected.

## Install

```bash
npx bmad-module-ultracode-goal install
```

The installer is interactive: it prompts for the project name and whether to install the learning material, then installs the skill for Claude Code. As an alternative, the module can be installed from the plugin marketplace entry (`.claude-plugin/marketplace.json`) the same way as other BMAD plugins. That entry ships the `ultracode-goal` skill alone, so run `npx bmad-module-ultracode-goal install` in the project as well: it adds the story skills a run delegates to (`ucg-create-story`, `ucg-dev-story`) and the `ucg-*` commands, and preflight does not launch without the story skills.

## First run

Invoke the skill with one of its trigger phrases ("run an epic autonomously", "execute this epic", "ultracode goal", or "autonomously deliver the epic") in a BMAD project.

1. **Name the Epic.** Stage 1 opens the floor: name the Epic, or drop any context (a story id, a branch, a paste of the Epic body). The skill fills the gaps from the BMAD artifacts. If `_bmad/` config, `sprint-status.yaml`, and any Epic are *all* absent, this is not a BMAD project; the skill says so and stops, pointing you at `bmad-bmb-setup` and `bmad-sprint-planning`.
2. **Preflight runs.** Stage 2 is the autonomy gate. It runs a mechanical check (`preflight_check.py`), auto-remediates the fixable ambers (scaffolding the test framework, generating missing acceptance criteria, pre-creating TEA output dirs, and so on), then adds a semantic scan for undecided product or architecture decisions the script cannot see. The run launches **only** when the post-remediation intervention budget is zero and the semantic scan found no red blocker. A single undecided architecture decision stops the run here rather than letting an unattended run guess it.
3. **The launch briefing.** On an attended run, before the first unattended action the skill prints a one-screen briefing: what is about to run, the per-story turn ceiling (it sizes stories; it does not cap time or cost), the autonomy line ("from here I will not ask you anything"), the kill switch (Ctrl-C, or delete the Epic branch; `/rewind` will not help; on a project that gitignores its BMAD output, the branch undoes the code only), and where to watch (the run's `.decision-log.md` and `run-status.json`). One soft confirm crosses the line.

From there the run is autonomous: it defines done with TEA, executes each story to a green commit, gates each one deterministically, and finalizes with a run report and the deferred-work ledger. See [how it works](./how-it-works.md) for the full stage-by-stage narration and the routing diagram.

## Run-mode flags

| Flag | Effect |
|------|--------|
| `--light` | Trace-only gate. Downscopes from the full TEA chain to `bmad-testarch-trace` plus `gate_eval.py --profile light`: no NFR/test-review AND. |
| `--parallel` | Retired. The flag is still accepted so an old invocation does not error: the run logs one note that it was accepted and ignored, then executes the sequential `/goal` spine. |
| `--yes` | Skips Stage 1's open-floor invite and the launch confirm. The launch briefing still prints. **Never** skips the hard preflight gate. |
| `-H` | Headless. Runs non-interactively, never prompts (an unresolvable secret becomes a red blocker, not a question), and emits one JSON object at every exit point the permission layer lets it reach (see [hook security](#hook-security)). |
| `--retro` | Runs the close-out retrospective (`bmad-retrospective`). Interactive runs offer it at Epic close anyway; headless runs it only when `--retro` is passed. |
| `--max-stories N` | Bounds this **invocation** to N stories, then finalizes normally (report, ledger, terminal JSON). It is a work bound, not a scope narrowing: in-scope stays every not-`done` story, so the next invocation resumes at the story this one stopped before. No Epic-level gate is authored while stories remain. See [one story per process](#one-story-per-process). |

## One story per process

A headless run drives every remaining story in one Claude Code session, and that session's context only grows: by the fifth story it carries four stories of transcript it will never need again. `scripts/drive_epic.py` moves that boundary into the process table. It spawns one `claude -p` per story under `--max-stories 1`, so each story's context dies with the process that held it:

```bash
uv run .claude/skills/ultracode-goal/scripts/drive_epic.py \
  --epic 7 \
  --impl-artifacts _bmad-output/implementation-artifacts \
  --profile light \
  --dry-run
```

Run it from your project root. The path above is the Claude Code skill copy the installer writes; the module copy under your resolved UCG folder (`_bmad/ucg/ultracode-goal/scripts/drive_epic.py` by default) is the same file, and in a clone of this repository it is `skills/ultracode-goal/scripts/drive_epic.py`.

Drop `--dry-run` to actually spawn. Point `--impl-artifacts` at the directory holding your `sprint-status.yaml`; the driver refuses to start if it is not there, since that is the sprint plan it reads. That directory also has to be the one your config resolves `implementation_artifacts` to, because the spawned session writes its terminal `run-result.json` where the config says, not where the driver was pointed. The driver cannot check that half for you: it would have to re-implement the skill's own config resolution to do it.

The driver is read-only on your tree with exactly one exception: it deletes the pinned `run-result.json` before each spawn, so the file's presence means *that* spawn reached a terminal. It stops on anything it cannot verify, and says why: no readable terminal, a `blocked` envelope (with the reason), a status it does not recognize, a `complete` whose story did not reach `done`, or a session that outran `--session-timeout` (2 hours by default; `0` disables it).

**One of those is retried rather than fatal.** A `claude -p` can be terminated in flight by the API layer, leaving no terminal, and that is not a story problem: the same row lands on the next attempt against identical state. The driver retries a no-terminal stop up to `--max-abort-retries` times (default 2, `0` disables), but **only** when its post-stop triage finds the tree clean and HEAD unmoved, so a retry can never re-spawn over work in progress.

**Every post-spawn stop now prints a triage block** describing the tree the session left: clean with HEAD advanced (the work committed and only close-out is missing, so verify and mark it done rather than re-driving), clean and unmoved (nothing landed), or dirty (which may hold a suite that is already green). It reports and never decides. It also names any intent-to-add path, because `git checkout -- <path>` truncates those to zero bytes and exits `0`.

Useful flags: `--limit N` caps how many sessions it spawns, retries included, `--permission-mode` defaults to `acceptEdits` and refuses `bypassPermissions` unless you also pass `--allow-full-autonomy`, and `--skill-command` overrides the invocation string for a plugin-marketplace install (`/bmad-module-ultracode-goal:ultracode-goal`).

## Hook security

At preflight the skill auto-merges its **PreToolUse** guard and **Stop** budget hook into `.claude/settings.local.json`, a machine-local, gitignored file, honored after the workspace trust dialog. These hooks are the enforcement layer that blocks a commit on a protected branch and records each story's turn count; they are not shared into the repo. Because they execute on your machine, review what gets merged: see [SECURITY.md](https://github.com/armelhbobdad/bmad-module-ultracode-goal/blob/main/SECURITY.md) for the hook-security model and what to check before granting trust.

**Take a new Epic through preflight attended.** The same write adds allow rules built from `allowlist_commands`, and Claude Code treats `.claude/settings.local.json` as a protected file. A headless session cannot approve that write: under Auto Mode, which the run requires, the permission classifier may refuse it (or the calls after it) as self-modification, and under `drive_epic.py`'s default `acceptEdits` mode the write prompts with nobody there to answer. Either way the run stops at arming. So run the first invocation of a new Epic attended, in Auto Mode, through the launch briefing and on to at least one story's gate verdict; if a settings write is refused, approve it under `/permissions` (on its Recently denied tab) or apply it yourself, as the decision log describes. From then on, a session that resumes the Epic routes into Execute and only re-checks the hooks, so `-H` and `drive_epic.py` can take over.
