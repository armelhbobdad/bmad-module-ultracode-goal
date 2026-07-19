### Launch briefing (interactive only)

This is the moment the human leaves the loop. Before the first unattended action — **interactive runs only; headless skips this subsection entirely** — surface a one-screen briefing so the operator decides "should I let go right now?" with eyes open:

- **What is about to run unattended:** the Epic (id + title), in-scope story count, profile (production / `--light`), and the Epic branch (`{workflow.epic_branch_prefix}<epic-id>`).
- **Worst-case envelope:** up to `story count × {workflow.max_turns_per_story}` turns — a smart default from context already in hand, so a first-timer can calibrate launch-now vs. launch-after-lunch.
- **The autonomy line:** state plainly — *"from here I will not ask you anything."*
- **Kill switch:** Ctrl-C, or delete the Epic branch — and note that `/rewind` will not help (its checkpoints miss the Bash-driven changes that make up the run, the same reason the branch is the real undo).
- **Where to watch:** the run's `.decision-log.md` (prose account); on the sequential spine, `{workflow.implementation_artifacts}/run-status.json` (the machine-readable heartbeat Execute updates as the spine advances); under `--parallel`, watch the workflow progress view (`/workflows`) and its run log instead — the fan-out's worktree agents do not write `run-status.json`.

Then **one soft confirm** to cross the line. With `--yes`, skip the confirm and launch straight through — but **still print the briefing** so the operator has the record. Headless never reaches this subsection.

