---
title: Knowledge-Graph Refresh
description: The optional graphify integration - UCG refreshes your project's knowledge graph as a run exits, so the next session starts from a current graph. Opt-in, advisory, never in the gate path, off by default.
---

> **Optional, opt-in, off by default.** The refresh is one time-boxed call on the way out of a run. It can add an artifact to your machine, and it can change nothing else: not the gate verdict, not the recorded run-status, not the headless envelope. When it is off, or when the [graphify](https://github.com/Graphify-Labs/graphify) CLI is absent, the run is byte-for-byte the same as a run without it.

## What it does

A knowledge graph of your codebase goes stale the moment a run lands eight stories of new code. With `graphify_integration = "refresh"`, Stage 6 Finalize spends one incremental rebuild refreshing it, so the next session starts from a current graph instead of a stale one.

Finalize is the only call site. No preflight step, no per-story step, and nothing in the gate path calls graphify or reads its output. See [how it works](./how-it-works.md) for where Stage 6 sits.

## What you need

The third-party [graphify](https://github.com/Graphify-Labs/graphify) CLI, whose package name is not its command name:

```bash
uv tool install graphifyy   # or: pipx install graphifyy. The command is `graphify`.
```

> graphify is a third-party tool maintained independently of this module. We don't bundle, endorse, or install it; the refresh simply uses it when you already have it.

You also need a graph to refresh. Build one once yourself (`graphify .`), which is the condition the second precondition below is really asking about.

## Turning it on

Set the knob in your project's `_bmad/custom/ultracode-goal.toml` (the same file the other knobs use):

```toml
[workflow]
# Knowledge-graph refresh: one incremental rebuild as the run exits.
# Needs the graphify CLI and an existing graphify-out/. Advisory, never gates.
graphify_integration = "refresh"
```

The `[workflow]` table header matters: the resolver extracts the `workflow` block from the merged files, so a bare top-level `graphify_integration` line is silently discarded and the feature stays off.

## Three things to know before you turn it on

- **The values are `off` and `refresh`, not `on` and `off`.** `cross_session_recall` sits directly above it in the shipped file and takes `on`, so copying that shape here produces `"on"`, which is not a legal value and leaves the step off.
- **A first-ever enable does nothing, deliberately.** Two preconditions are both required: `graphify` resolves on `PATH`, and a `graphify-out/manifest.json` already exists under the project root to increment from. Refresh means refresh: with no manifest there is nothing to increment, and a cold build walks the whole corpus and spends API budget, which is not something a bounded exit step may do. Build the graph once yourself, and the run keeps it current from then on.
- **Absence is silent, failure is logged.** When either precondition is missing, the run is byte-identical to an `off` run: no probe output, no decision-log line, nothing. When the pass does run and then fails or exceeds its 300 second time box, Finalize logs one `WARN graphify-refresh-failed` line to `.decision-log.md` and moves on. It is never retried.

## What it sends, and where it writes

Read this before enabling it on a private codebase.

graphify extracts code locally (tree-sitter, no network call), but non-code files go to an LLM. When the changed slice includes documents, papers, or images, graphify sends their content to whichever backend it auto-detects from your environment: `GEMINI_API_KEY`/`GOOGLE_API_KEY`, `MOONSHOT_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, Azure, Bedrock, or a local Ollama. Two consequences worth planning for:

- **A refresh can spend API budget**, on your key, at the end of a run you were not watching. A slice of pure code changes spends nothing and needs no key.
- **With no backend configured and a non-code file in the slice, graphify exits non-zero**, so the refresh fails and the only thing you see is the `WARN graphify-refresh-failed` line. That is the failure to suspect first if the graph never seems to update.

The output is a `graphify-out/` directory at your project root, not in the run folder, so it is not part of the run's evidence and nothing in the gate path reads it. It regenerates on every refresh and holds a `graph.json`, a `graph.html`, a report, and a cache, so **add `graphify-out/` to your `.gitignore`**: UCG commits each green story, and an untracked-but-not-ignored tree at the repo root is exactly what a story commit should never sweep up.

## What it never touches

The refresh is advisory in the same sense [Cross-Session Recall](./cross-session-recall.md) is, and the two are independent: either can be on without the other.

- The **gate verdict** is `gate_eval.py` reading TEA's `gate-decision.json`, and only that. See the [gate model](./gate-model.md).
- The **recorded run-status** and the **headless envelope** are identical whether the refresh ran, failed, or never fired.
- A graphify failure or timeout **never** blocks, re-loops, or escalates a story, and never changes a run's `complete` / `blocked` / `partial-complete` outcome.

Verified against graphify 0.9.26 on 2026-07-28. It is a pre-1.0 tool whose CLI surface moves; if the install name, the command name, or the output layout above no longer match what you have, trust `graphify --help`.
