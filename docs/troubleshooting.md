# Troubleshooting

Real failure modes, sourced from the skill's stage files and scripts, with what the run does about each and what you do. For the design behind these behaviors see [how it works](how-it-works.md), [the gate model](gate-model.md), and [architecture](architecture.md).

## Preflight can't reach budget-zero

**Symptom.** The run stops at Stage 2 (or, headless, emits `{"status":"blocked", ...}` with a one-line `reason`) and never launches.

**What happened.** Preflight is a hard gate: the run launches only when the post-remediation mechanical `budget == 0` **and** the semantic scan found no RED. The auto-remediation pass clears the *fixable* mechanical blockers — it scaffolds the test framework, generates missing acceptance criteria, pre-creates the TEA output dirs, ensures one `project-context.md`, ensures `sprint-status.yaml`, and prompts once (interactively) for secrets — then re-runs the check.

**What stays red.** Some things the remediation pass cannot fix, by design:

- **Undecided product or architecture decisions.** An open question, a "TBD"/"TODO: decide" on a load-bearing requirement, a PRD↔ADR contradiction, or a story whose "done" is undefinable. The fix is a human decision; an unattended run guessing it produces confidently wrong work. Resolve the decision in the artifacts, then re-run.
- **Missing secrets in headless.** Headless never prompts, so a secret that cannot be resolved becomes a RED blocker rather than a question. Provide the secret (out of git) before the headless run, or run attended so preflight can prompt once.
- **Claude Code below the minimum versions.** The primitive-version blocker is marked non-remediable — the script can't upgrade the host. Update Claude Code.

The decision log carries the full blocker list with what each needs to clear. Read it, clear the items, re-run.

## gate_eval reports blocked / escalate on a missing gate-decision.json

**Symptom.** Stage 5 returns `gate_status: NOT_EVALUATED` and verdict `escalate`, with a `reasons` entry like `neither gate-decision.json nor e2e-trace-summary.json present in <dir>`.

**What happened.** `gate_eval.py` reads TEA's gate artifact from the trace output directory. `NOT_EVALUATED` means neither the slim `gate-decision.json` nor the fallback `e2e-trace-summary.json` was found there, or the run carried no gate fields. Almost always this is one of:

- **The TEA trace gate did not run.** In production, Stage 5 must backfill evidence first (`bmad-testarch-automate` → `bmad-testarch-trace` → `bmad-testarch-nfr`) before the gate; `bmad-testarch-trace` is what writes the gate decision. If it didn't run, there is nothing to read.
- **Wrong `trace_output_dir`.** The script reads the directory passed as `--trace-output` (resolved from `{workflow.trace_output_dir}`). If TEA wrote elsewhere — or the output dirs were never pre-created at preflight — the artifact is real but in a different place. Confirm `trace_output_dir` matches where TEA actually wrote.

Note this is fail-closed on purpose: a missing or unreadable gate artifact escalates rather than being assumed green. The slim file's *absence alone* is not the problem — the script falls back to the summary, and that fallback is explicitly not a failure.

## Hooks not firing

**Symptom.** A commit lands on a protected branch, or a commit lands before a story's tests ran — the invariants the PreToolUse hook should enforce did not block.

**What to check.**

- **Older Claude Code.** The hook returns a `deny` decision in the hook JSON and *also* exits 2 with the reason on stderr precisely so older clients that ignore the JSON still block. If neither path fired, the client may not be honoring PreToolUse hooks at all — update Claude Code.
- **`settings.local.json` not merged.** The hooks are merged into `{project-root}/.claude/settings.local.json` at preflight, and the skill asserts they are active before going unattended. If the file wasn't merged (or the workspace trust dialog wasn't accepted), the hooks aren't loaded. Re-run preflight; verify the two hook entries are present in the resolved settings.
- **A `customize.toml` override that silently no-ops.** Both hooks read config from env first and fall back to hardcoded defaults (`main`/`master`, `25`, `1_500_000`, `ultracode/epic-`). A `protected_branches` or budget override in `customize.toml` only reaches the hook if preflight injected it into the hook env (`ULTRACODE_PROTECTED_BRANCHES`, etc.). If your custom protected branch isn't being guarded, the override didn't reach the enforcement layer — confirm preflight passed it through.

## Budget exhausted mid-story

**Symptom.** A story stops re-looping; an escalation marker (`<impl-artifacts>/.escalation-<story>.md`) appears; the run surfaces a budget message.

**What happened.** A runaway story is bounded three ways. The real in-loop bound is the literal "…or stop after N turns" clause inside the `/goal` condition. The gate's re-loop budget is deterministic: a `reloop` that would exceed `max_turns_per_story` or `story_token_budget` becomes an `escalate` instead. The **Stop** hook (`budget_stop.py`) is the defensive third layer — it counts turns and tokens and, on overrun, writes the escalation marker and lets the stop proceed.

**Its documented limitation.** A Stop hook fires only when Claude is *already* trying to stop — it **cannot interrupt a `/goal` condition mid-turn**. So at this layer the ceiling is advisory; the hard bounds are the in-condition turn clause and the gate re-loop budget. If a story keeps consuming budget, that is the signal to re-scope, split, or hand it off — not to raise the budget and hope.

## Resume after an interruption

**Symptom.** A run was interrupted (Ctrl-C, a crash, a compaction) and you want to continue rather than restart.

**What happens.** The run's `.decision-log.md` is canonical memory and recovers full state regardless of compaction. On resume the skill surfaces the existing log with its last session date and offers to resume. Execute re-enters at the **first story whose last logged gate verdict is not `advance`**; already-advanced stories are not re-run. The Epic branch, hooks, and allowlist are **re-asserted, not rebuilt**, before continuing. You do not need to reconstruct state by hand — point the skill at the same Epic and accept the resume offer.

## `--parallel` issues

`--parallel` is experimental and opt-in; the sequential spine is the default. If dynamic workflows are unavailable (wrong Claude Code version, the feature off, or the saved command doesn't resolve), the skill **automatically falls back to the spine** and logs why in `.decision-log.md` — the Epic still ships. For the known limits (shared Auto Memory across worktrees, the under-documented workflow↔skill interplay, no `run-status.json` heartbeat), see [parallel mode](parallel-mode.md).
