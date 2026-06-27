---
title: UltraCode Goal (UCG)
description: "Run a BMAD Epic autonomously to a machine-checked Definition-of-Done. Completion is a fact on disk: gate_eval.py reads PASS, never the model's say-so."
template: splash
hero:
  title: UltraCode Goal
  tagline: Run a BMAD Epic autonomously to a machine-checked Definition-of-Done.
  image:
    file: ./assets/ucg-logo.svg
    alt: Six stage nodes orbit a hexagonal gate; the centre verdict reads PASS.
  actions:
    - text: Why UltraCode Goal?
      link: ./why-ultracode-goal/
      icon: right-arrow
      variant: primary
    - text: Install
      link: ./getting-started/
      icon: right-arrow
      variant: secondary
---

## The problem

You hand an agent an epic and tell it to build until done. It runs, it commits, it declares victory. At review time you learn that "done" meant the model felt done, a story it wrote *about* the work, not a verdict *on* the work.

Autonomous runs that look done are not done. The thing deciding completion only ever sees the transcript; it cannot open the gate file written to disk. A model grading its own output is the weakest possible signal for a release gate, and by default it is the only signal you get.

## The fix

UltraCode Goal does not trust the transcript. It hard-gates the epic *before* launch and reads completion from a file *after* the work, three enforcement layers between "the agent stopped" and "the epic shipped":

- **A preflight gate that fails closed.** The run launches only when `preflight_check.py` returns green *after* its remediation pass, with the intervention budget at zero. A red blocker stops the run; it does not become a question for later.
- **TEA red-phase tests as the Definition-of-Done.** The Test Architect turns each story's acceptance criteria into executable, failing tests *first*, so "done" is a measurable transition from red to green, not prose.
- **A deterministic gate verdict.** A story advances only when `gate_eval.py` reads `PASS` from TEA's `gate-decision.json`. It never re-derives the thresholds and never asks the model. The verdict JSON is the truth, and you can read it yourself.

<div class="verdict-sample"><span class="verdict-sample__label">The completion verdict</span><code class="verdict-sample__chip">gate-decision.json → PASS</code><span class="verdict-sample__check" aria-label="machine-checked">✓</span></div>

If the gate file is missing or unparseable, the contract counts it as a *failing* signal; prose drift degrades to a conservative re-loop, never a silent false-advance.

<p class="cta-pill"><a href="./getting-started/">Install and run your first epic →</a></p>

## What you get

Completion stops being a feeling in the transcript and becomes a fact on disk. Every green story is one git commit on an isolated epic branch: rollback you can actually trust, not a checkpoint that misses Bash changes. The run ends with a delivered, gate-passed epic, a run report, and a deferred-work ledger of anything safely parked for later.

## Read the rest

The docs split into three buckets: **Why** (start here), **Try** (do stuff), and **Reference** (look things up).

**Why**

- [Why UltraCode Goal](./why-ultracode-goal.md): the problem in depth, the three enforcement layers, and when not to use it.

**Try**

- [Getting Started](./getting-started.md): prerequisites, install, the flags, and your first autonomous run.
- [How It Works](./how-it-works.md): the six stages, their routing conditions, and the headless emit shape.
- [Parallel Mode](./parallel-mode.md): the experimental worktree fan-out and its known limits.

**Reference**

- [Architecture](./architecture.md): the conductor model, the enforcement layers in depth, and customization resolution.
- [Gate Model](./gate-model.md): how `gate_eval.py` maps `gate_status` to a verdict, the thresholds, and the fail-closed contract.
- [Health Check](./health-check.md): the terminal self-improvement reflection: what it sends, the privacy model, and how to disable it.
- [Cross-Session Recall](./cross-session-recall.md): the optional claude-mem integration and its trust model.
- [Troubleshooting](./troubleshooting.md): real failure modes and their remediations.
