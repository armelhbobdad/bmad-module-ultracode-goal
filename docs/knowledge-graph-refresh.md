---
title: Knowledge-Graph Refresh
description: The optional graphify integration - UCG refreshes your project's knowledge graph as a run exits, so the next session starts from a current graph. Opt-in, advisory, never in the gate path, off by default.
---

> **Optional, opt-in, off by default.** The refresh is one time-boxed call on the way out of a run. It writes `graphify-out/` in your project (or wherever `GRAPHIFY_OUT` points) and nothing else, because Finalize turns graphify's own housekeeping off for that call ([where it writes](#what-it-runs-and-where-it-writes) has the detail). It changes nothing in the run: not the gate verdict, not the recorded run-status, not the headless envelope. When it is off, or when the [graphify](https://github.com/Graphify-Labs/graphify) CLI or an existing graph is missing, the run is byte-for-byte the same as a run without it.

## What it does

A knowledge graph of your codebase goes stale the moment a run lands eight stories of new code and the documents that came with them, which is exactly what a UCG run produces. With `graphify_integration = "refresh"`, Stage 6 Finalize spends one incremental, local rebuild, so the next session starts from a current picture instead of a stale one. graphify rescans the project but re-parses only the files that changed since its cache last saw them. The cache is kept per graphify version, so the first refresh after an upgrade re-parses every file and is the one most likely to run past the time box. It refreshes what can be parsed and leaves what needs a model alone; [what it runs](#what-it-runs-and-where-it-writes) draws that line precisely.

Finalize is the only call site. No preflight step, no per-story step, and nothing in the gate path calls graphify or reads its output. See [how it works](./how-it-works.md) for where Stage 6 sits.

## What you need

The third-party [graphify](https://github.com/Graphify-Labs/graphify) CLI, whose package name is not its command name:

```bash
uv tool install graphifyy   # or: pipx install graphifyy. The command is `graphify`.
```

> graphify is a third-party tool maintained independently of this module. We don't bundle, endorse, or install it; the refresh simply uses it when you already have it.

You also need a graph to refresh, since this step updates one and never builds one. Build it once yourself. graphify's own route is `graphify install`, then `/graphify .` in your AI assistant, which runs the semantic pass on that assistant's model. From a shell, `graphify .` runs the same full pipeline and needs an LLM backend (an API key, a local Ollama or the `claude` CLI) once the project has documents, PDFs or images, while `graphify update .` builds the parsed layer alone, offline. After that first build, the run keeps the parsed layer current.

## Turning it on

Set the knob in your project's `_bmad/custom/ultracode-goal.toml`. **No installer creates that file**, so on most projects you are creating it: `_bmad/custom/` exists already, but the `config.toml` sitting in it belongs to BMAD's own configuration, and putting a UCG knob there does nothing.

```toml
[workflow]
# Knowledge-graph refresh: one incremental rebuild as the run exits.
# Needs the graphify CLI on PATH and an existing graphify-out/graph.json. Advisory, never gates.
graphify_integration = "refresh"
```

The `[workflow]` table header matters: the resolver extracts the `workflow` block from the merged files, so a bare top-level `graphify_integration` line is silently discarded and the feature stays off.

**To let the refresh run unattended**, allow its command. Without an allow rule, the command is left to Claude Code's permission check: under Auto Mode the classifier decides whether it runs, and in a mode that asks first, such as `drive_epic.py`'s default `acceptEdits`, nobody is there to answer. A refusal is logged as a `WARN graphify-refresh-failed` line like any other failure. Add the whole command to `allowlist_commands` under the same `[workflow]` header, not a second one: TOML refuses a table declared twice, and the resolver then rejects the whole file. Arrays append to the shipped list, and preflight writes each entry as an allow rule in `.claude/settings.local.json`. The whole file then reads:

```toml
[workflow]
graphify_integration = "refresh"
allowlist_commands = ["GRAPHIFY_NO_AUTO_REFRESH=1 timeout 300 graphify update ."]
```

An entry for the binary alone, `graphify`, does not cover it: Claude Code does not match an allow rule past a leading assignment of a variable it does not know, such as `GRAPHIFY_NO_AUTO_REFRESH=1`. If you added that entry for an earlier version, replace it. Replacing it leaves the allow rule an earlier preflight wrote for it, such as `Bash(graphify:*)`, in `.claude/settings.local.json`, because preflight only adds rules. Delete that rule yourself unless you want every graphify command, `graphify extract` included, to run without asking.

## Three things to know before you turn it on

- **The values are `off` and `refresh`, not `on` and `off`.** `cross_session_recall` sits directly above it in the shipped file and takes `on`, so copying that shape here produces `"on"`, which is not a legal value: only `refresh` turns the step on.
- **A first-ever enable does nothing, deliberately.** Two preconditions are both required: `graphify` resolves on `PATH`, and a `graphify-out/graph.json` already exists under the project root to update. Refresh means refresh: the step updates a graph you already have and never creates one, because whether your project gets a graph at all is your call, not an exit step's. Build the graph once yourself, and the run keeps its parsed layer current from then on. If `GRAPHIFY_OUT` is set, graphify reads and writes the graph there, but the probe still checks only `graphify-out/graph.json`. With no graph at `graphify-out/` the step stays silently off; with an old one still there, the refresh runs against the `GRAPHIFY_OUT` location and builds a graph there if it has none.
- **Absence is silent, failure is logged.** When either precondition is missing, the run is byte-identical to an `off` run: no probe output, no decision-log line, nothing. When the pass is attempted and ends in anything but a clean exit 0 (a non-zero exit, the 300 second time box running out, or a permission or sandbox denial of the command), Finalize logs one `WARN graphify-refresh-failed` line to `.decision-log.md` and moves on. It is never retried. If the permission layer refuses the probe itself, Finalize logs one `NOTE graphify-probe-unavailable` line instead and skips the step.

## What it runs, and where it writes

The delegation is exactly one command, `GRAPHIFY_NO_AUTO_REFRESH=1 timeout 300 graphify update .`, time-boxed to 300 seconds and never retried. Its `update` subcommand re-extracts the graph's **parsed layer** against what is on disk, using graphify's local parsers (tree-sitter for most code, rule-based parsers for Markdown and package manifests): **no LLM call, no API key, no token spend** at the end of a run you were not watching, and **no network request** unless you have turned on graphify's Google Workspace export (`GRAPHIFY_GOOGLE_WORKSPACE=1`), which fetches each `.gdoc`, `.gsheet` or `.gslides` shortcut from Google Drive on every refresh.

The parsed layer covers the files graphify has a local parser for: source code and the Markdown family (`.md`, `.mdx`, `.qmd`, `.skill`). Source code here includes shell scripts, `.sql` and `.tf` files, package manifests such as `pyproject.toml` and `go.mod`, and config JSON such as `package.json` and `tsconfig.json`; a data `.json` file, such as a fixture, gets no nodes. So an Epic's new modules and the story and documentation files it wrote are both picked up, with one exception: a Markdown file the last full build already gave LLM-derived nodes is not re-parsed, so an edit to it waits for the next semantic pass. What stays as the last full build left it is the **semantic** layer: images, PDFs and papers, documents graphify has no parser for (such as `.txt`, `.rst`, `.html` and `.yaml`), and anything an LLM derived from a document, except that a source deleted from disk or newly ignored loses its nodes. That pass is the one that sends your files to an LLM and spends tokens, which is exactly what an unattended exit step should not decide to do. Run it yourself, on your own terms, when you want it.

One behaviour worth knowing, because it is the opposite of what people expect:

- **Deleting code shrinks the graph, and nothing warns.** That is correct: the rebuild accounts for sources that are gone and writes the smaller graph, exit 0.
- **What graphify refuses is a loss it cannot account for**, such as nodes vanishing from a file that is still on disk but could not be extracted this run (an unreadable file, for example), or LLM-derived nodes vanishing while their file is still there. Then graphify declines the write, exits non-zero, and you get a `WARN graphify-refresh-failed` line with the graph left intact. Whether to re-run `graphify update . --force` is a decision the run does not make for you.
- **Narrowing the scan is not refused.** When an Epic adds a `.graphifyignore` rule, or a `.gitignore` rule over files git does not track, graphify drops those files' nodes like a deletion, prints `pruned N node(s) from M newly-ignored file(s)` and exits 0. A `.gitignore` rule does not apply to files git already tracks, so those stay in the graph.

The output is a `graphify-out/` directory at your project root, not in the run folder, so it is not part of the run's evidence and nothing in the gate path reads it. It holds `graph.json`, `GRAPH_REPORT.md`, `graph.html`, `manifest.json`, a `cache/` and a few dotfiles, and a refresh that finds no change leaves the graph and the report as they were. Before a refresh rewrites the graph, graphify copies the old one into a dated folder such as `graphify-out/2026-10-20/`, one a day, if a shell `graphify .` built it with an LLM backend (graphify then leaves a `.graphify_semantic_marker`) or `.graphify_labels.json` holds community names, which a `/graphify .` build in your assistant saves. The hub names `update` fills in go to a separate file and do not count. Setting `GRAPHIFY_NO_BACKUP` turns the copy off. **Add `graphify-out/` to your `.gitignore`**: UCG commits each green story, and an untracked-but-not-ignored tree at the repo root is exactly what a story commit should never sweep up.

Before most commands, `update` included, graphify does some housekeeping outside `graphify-out/` (it skips it only for `install`, `uninstall` and the `hook-check` and `hook-guard` calls made by its editor hooks):

- On the first such command after you upgrade graphify, it re-copies any skill files `graphify install` put in your home directory, such as `~/.claude/skills/graphify/` for Claude Code, if their version stamp is older than the new package, and keeps the previous `SKILL.md` as `SKILL.md.bak` whenever it differs from the new one.
- On every such command, upgrade or not, it checks `.opencode/` in the project and in your home directory: it replaces a graphify OpenCode plugin written by graphify 0.9.74 or earlier once your OpenCode can load the current one, and drops graphify's stale plugin entry from `opencode.json`.

Each of these also leaves a lock file under `~/.cache/graphify/skill-locks/`. The `GRAPHIFY_NO_AUTO_REFRESH=1` at the start of Finalize's command turns all of it off for the refresh, so the refresh writes nothing outside `graphify-out/` (or wherever `GRAPHIFY_OUT` points): no skill, OpenCode or lock file in your home directory, and, in a project that commits `.opencode/`, no modified tracked file there after the last story commit. You don't need to set anything. The next graphify command you run yourself does the housekeeping as usual. Until you do, after a graphify upgrade the refresh prints graphify's warning that its installed skill is out of date, and Finalize does not act on it.

## What it never touches

The refresh is advisory in the same sense [Cross-Session Recall](./cross-session-recall.md) is, and the two are independent: either can be on without the other.

- The **gate verdict** is `gate_eval.py` reading TEA's gate artifacts, and nothing graphify writes is among them. See the [gate model](./gate-model.md).
- The **recorded run-status** and the **headless envelope** are identical whether the refresh ran, failed, or never fired.
- A graphify failure or timeout **never** blocks, re-loops, or escalates a story, and never changes a run's `complete` / `blocked` / `partial-complete` outcome.

Verified against graphify 0.9.92 on 2026-10-20. It is a pre-1.0 tool whose CLI surface moves; if the install name, the command name, or the output layout above no longer match what you have, trust `graphify --help`.
