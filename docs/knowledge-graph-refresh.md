---
title: Knowledge-Graph Refresh
description: The optional graphify integration - UCG refreshes your project's knowledge graph as a run exits, so the next session starts from a current graph. Opt-in, advisory, never in the gate path, off by default.
---

> **Optional, opt-in, off by default.** The refresh is one time-boxed call on the way out of a run. It can add an artifact to your machine, and it can change nothing else: not the gate verdict, not the recorded run-status, not the headless envelope. When it is off, or when the [graphify](https://github.com/Graphify-Labs/graphify) CLI is absent, the run is byte-for-byte the same as a run without it.

## What it does

A knowledge graph of your codebase goes stale the moment a run lands eight stories of new code and the documents that came with them, which is exactly what a UCG run produces. With `graphify_integration = "refresh"`, Stage 6 Finalize spends one incremental, local rebuild, so the next session starts from a current picture instead of a stale one. It refreshes what can be parsed and leaves what needs a model alone; [what it runs](#what-it-runs-and-where-it-writes) draws that line precisely.

Finalize is the only call site. No preflight step, no per-story step, and nothing in the gate path calls graphify or reads its output. See [how it works](./how-it-works.md) for where Stage 6 sits.

## What you need

The third-party [graphify](https://github.com/Graphify-Labs/graphify) CLI, whose package name is not its command name:

```bash
uv tool install graphifyy   # or: pipx install graphifyy. The command is `graphify`.
```

> graphify is a third-party tool maintained independently of this module. We don't bundle, endorse, or install it; the refresh simply uses it when you already have it.

You also need a graph to refresh, since this step updates one and never builds one. Build it once yourself (`graphify .`, which is the full pipeline and does use an LLM backend), and the run keeps its parsed layer current after that.

## Turning it on

Set the knob in your project's `_bmad/custom/ultracode-goal.toml`. **No installer creates that file**, so on most projects you are creating it: `_bmad/custom/` exists already, but the `config.toml` sitting in it belongs to BMAD's own configuration, and putting a UCG knob there does nothing.

```toml
[workflow]
# Knowledge-graph refresh: one incremental rebuild as the run exits.
# Needs the graphify CLI and an existing graphify-out/. Advisory, never gates.
graphify_integration = "refresh"
```

The `[workflow]` table header matters: the resolver extracts the `workflow` block from the merged files, so a bare top-level `graphify_integration` line is silently discarded and the feature stays off.

## Three things to know before you turn it on

- **The values are `off` and `refresh`, not `on` and `off`.** `cross_session_recall` sits directly above it in the shipped file and takes `on`, so copying that shape here produces `"on"`, which is not a legal value and leaves the step off.
- **A first-ever enable does nothing, deliberately.** Two preconditions are both required: `graphify` resolves on `PATH`, and a `graphify-out/graph.json` already exists under the project root to update. Refresh means refresh: with no graph there is nothing to update, and building one from nothing walks the whole corpus, which is not something a bounded exit step may do. Build the graph once yourself, and the run keeps its parsed layer current from then on.
- **Absence is silent, failure is logged.** When either precondition is missing, the run is byte-identical to an `off` run: no probe output, no decision-log line, nothing. When the pass does run and then fails or exceeds its 300 second time box, Finalize logs one `WARN graphify-refresh-failed` line to `.decision-log.md` and moves on. It is never retried.

## What it runs, and where it writes

The delegation is exactly one command, `graphify update .`, time-boxed to 300 seconds and never retried. That subcommand re-extracts the graph's **parsed layer** against what is on disk, using tree-sitter: **no LLM call, no API key, no network request, no token spend** at the end of a run you were not watching.

The parsed layer is everything graphify has an extractor for: your source code, plus the Markdown family (`.md`, `.mdx`, `.qmd`, `.skill`). So an Epic's new modules and the story and documentation files it wrote are both picked up. What stays as the last full build left it is the **semantic** layer: images, PDFs and papers, and anything an LLM derived from a document. That pass is the one that would send your files to a model provider and spend your API budget, which is exactly what an unattended exit step should not decide to do. Run it yourself, on your own terms, when you want it.

One behaviour worth knowing, because it is the opposite of what people expect:

- **Deleting code shrinks the graph, and nothing warns.** That is correct: the rebuild accounts for sources that are gone and writes the smaller graph, exit 0.
- **What graphify refuses is an unexplained loss**, where nodes vanish while their source is still sitting on disk. An Epic that adds a `.gitignore` rule, or otherwise narrows what gets scanned, produces exactly that. Then graphify declines the write, exits non-zero, and you get a `WARN graphify-refresh-failed` line with the graph left intact. Whether to re-run `graphify update . --force` is a decision the run does not make for you.

The output is a `graphify-out/` directory at your project root, not in the run folder, so it is not part of the run's evidence and nothing in the gate path reads it. It regenerates on every refresh and holds a `graph.json`, a `graph.html`, a report, and a cache, so **add `graphify-out/` to your `.gitignore`**: UCG commits each green story, and an untracked-but-not-ignored tree at the repo root is exactly what a story commit should never sweep up.

## What it never touches

The refresh is advisory in the same sense [Cross-Session Recall](./cross-session-recall.md) is, and the two are independent: either can be on without the other.

- The **gate verdict** is `gate_eval.py` reading TEA's `gate-decision.json`, and only that. See the [gate model](./gate-model.md).
- The **recorded run-status** and the **headless envelope** are identical whether the refresh ran, failed, or never fired.
- A graphify failure or timeout **never** blocks, re-loops, or escalates a story, and never changes a run's `complete` / `blocked` / `partial-complete` outcome.

Verified against graphify 0.9.26 on 2026-07-28. It is a pre-1.0 tool whose CLI surface moves; if the install name, the command name, or the output layout above no longer match what you have, trust `graphify --help`.
