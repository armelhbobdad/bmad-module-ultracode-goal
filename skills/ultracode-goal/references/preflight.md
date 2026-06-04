# Stage 2 — Preflight (the autonomy gate)

This is the load-bearing gate. After this stage the run goes **unattended**: a sequential `/goal` spine or an experimental `--parallel` worktree fan-out, neither of which takes mid-run human input. So everything that would otherwise stall or ask a question must be resolved **now**, or the run must refuse to launch. The posture is **hard gate with auto-remediation**: the script reports mechanical blockers, this stage clears the remediable ones, you add the semantic judgment the script cannot, and launch happens only when the post-remediation intervention budget is zero. Converse in `{communication_language}`; produced markers/docs use `{document_output_language}`.

## 1. Run the mechanical check

```
uv run {skill-root}/scripts/preflight_check.py --project-root {project-root} --epic <id> --tea-config {workflow.tea_config_path} --impl-artifacts {workflow.implementation_artifacts} --protected-branch <name> [--protected-branch <name> …]
```

Qualify the script path with `{skill-root}` (per SKILL.md Conventions a bare `scripts/…` resolves from the skill root, but the conductor runs from the project working directory) so it resolves regardless of cwd. Emit one `--protected-branch <name>` per entry in `{workflow.protected_branches}` (the flag is `action='append'`); without it the check falls back to its hardcoded `main, master` and silently no-ops a `protected_branches` override — the mechanical gate would then fail to flag being on a custom protected branch.

`<id>` is the Epic resolved in Stage 1. The script is **plumbing only** — it parses tool versions, git state, and file existence, and reports TEA config flags. It returns JSON:

```
{green: bool, budget: int,
 blockers: [{id, kind, severity, detail, remediable: bool}],
 checks: {cc_version, goal_ok, workflows_ok, automemory_ok, git_branch, git_clean,
          framework_present, test_artifacts_dirs, sprint_status_present,
          project_context_count, tea_flags}}
```

`budget` is the count of mechanical blockers. The script does **not** decide semantic intervention — that is your job in step 3. Treat `green: true` from the script as *necessary but not sufficient*.

## 2. Auto-remediation pass

Clear each remediable blocker, then **re-run the check** so the budget reflects the fixes. Remediate:

- **Test framework absent** (`framework_present: false`): scaffold it via `bmad-testarch-framework` (Playwright/Cypress per `tea_flags`). ATDD in Stage 3 hard-halts without a configured framework — this must exist before launch.
- **CI quality pipeline absent** (production profile only): if no CI quality pipeline exists yet, scaffold it via `bmad-testarch-ci` **after** the framework exists — `bmad-testarch-ci` halts if the framework is absent, so the strict order is framework → ci. This is one-time infra (force **Create** mode); the pipeline embeds TEA's coverage thresholds so the gate also lives durably in CI, while the per-epic loop gate remains `gate_eval.py` in Stage 5. Skip under `--light`.
- **Missing acceptance criteria / story** for an in-scope story: generate via `bmad-create-story` so each story carries clear, testable ACs. TEA atdd and trace both need them; a story without ACs has nothing to trace and will stall.
- **Test-artifacts dirs absent** (`test_artifacts_dirs` incomplete): pre-create the trace/test-design/test-review output dirs (`{workflow.trace_output_dir}` and its siblings under the TEA `test_artifacts` root) so TEA writes land deterministically and `gate_eval.py` finds them in Stage 5.
- **`project-context.md` count != 1** (`project_context_count`): ensure exactly **one** `project-context.md` exists (generate via `bmad-generate-project-context` if zero; if multiple, this is ambiguous AI-rules state — resolve to one before launch). `{workflow.persistent_facts}` globs this file; duplicates poison Auto Memory grounding.
- **`sprint-status.yaml` absent** (`sprint_status_present: false`): ensure it is present (via `bmad-sprint-planning`). Its presence makes TEA test-design **auto-select Epic-Level** and skip its interactive System/Epic mode prompt — without it, Stage 3 stalls on a question no one is there to answer.
- **TEA mode**: force **Create** mode for every TEA workflow this run. Resume/Validate/Edit are interactive and will halt an unattended run. Set/confirm whatever the TEA config exposes (`tea_execution_mode`) so no workflow resumes a prior session.
- **Secrets / credentials** a story needs (test env keys, API tokens): **interactive** — prompt **once**, now, and capture them out of git. **Headless** — do not prompt; an unresolvable secret becomes a RED blocker (step 4), never a deferred question.

**Ordering: only framework → ci is load-bearing** (the CI scaffold halts without a framework, as its bullet states). Every other remediation above is mutually independent — run them in any order, or concurrently; do not serialize them defensively.

**Remediation halt catch-all.** If a remediation sub-skill itself fails or blocks on interactive input, do not re-invoke it blind and do not answer its prompt — record a **RED** blocker naming the sub-skill and the exact input or decision it needed, and let the hard gate (step 4) stop the run. This mirrors Execute's sub-skill halt catch-all; a bare re-report of "budget still N" with no cause is not an account.

Log each remediation to `.decision-log.md` as you do it. After remediating, run the script from step 1 again and read the new `budget`.

## 3. Semantic intervention scan (the part the script cannot do)

The script counts mechanical facts; it cannot read a PRD and tell that a product decision is still open, or read an ADR and tell that an architecture choice is unresolved. That judgment happens now — but **not in your context**. The artifacts this scan reads are the same multi-thousand-token corpus the run is about to delegate to sub-skills; reading them here would make the conductor carry it through the entire unattended Execute phase (Stage 1's "do not open story or planning files for deep reading" rule exists for exactly this trap).

**Delegate the read to one throwaway subagent.** Spawn a single subagent with the artifact paths noted in Stage 1 (the Epic's stories, PRD, ADR/architecture) and — when Stage 1 Cross-Session Recall produced advisories — the typed `records`/`recurrence` output of the Stage 1 filter, as prior-failure **hypotheses to check** (attributed and advisory; re-use that filtered output, never a fresh MCP call). Instruct it to read the corpus and hunt **undecided product or architecture decisions** that an autonomous run would have to *guess*:

- open questions, "TBD" / "TODO: decide" / "to be determined" / "(?)" placeholders on a load-bearing requirement,
- contradictions between PRD and ADR,
- acceptance criteria that presuppose a decision no artifact actually makes,
- a story whose "done" is undefinable from the artifacts.

The subagent must return **ONLY this object — no prose, no document quotes beyond the one-line evidence fields**, so you hold the findings while the corpus stays in its discarded context:

```json
{"reds": [{"source": "<artifact path:line>",
           "kind": "undecided-product|undecided-architecture|contradiction|undefinable-done",
           "decision_needed": "<the exact decision a human must make>",
           "evidence": "<one quoted line>"}],
 "concerns": [{"source": "<artifact path:line>", "note": "<cosmetic / non-blocking gap, one line>"}],
 "advisories_checked": [{"sig": "<advisory id>", "status": "recurred|not-observed|unknown"}]}
```

Every `reds` entry is **RED** — it cannot be auto-remediated, because the fix is a human decision, and an unattended run guessing it produces confidently wrong work. A purely cosmetic gap belongs in `concerns`, never RED; recall-derived hypotheses are attributed under `advisories_checked` and are never themselves RED and never block launch. Record each RED finding with its source and the exact decision needed in `.decision-log.md`.

## 4. Hard gate

**Launch only when ALL hold:**

- post-remediation script `budget == 0` (every mechanical blocker cleared),
- the semantic scan found **no RED** (no undecided product/architecture, no unresolvable secret),
- **ultracode** session effort and **Auto Mode** are on (gated to Opus/Sonnet 4.6+; required for unattended xhigh + auto-workflow execution).

If any fails: write the blockers — mechanical and semantic — to `.decision-log.md` with what each needs to clear, and **STOP**. Do not launch a partially-ready run; a single guessed architecture decision corrupts the whole Epic. In **headless**, instead emit the blocked JSON in the canonical five-key shape (every key always present; `report` and `deferred_work` are `null` because the run blocked before producing them):

```json
{"status": "blocked",
 "skill": "ultracode-goal",
 "decision_log": "<path to this run's .decision-log.md>",
 "report": null,
 "deferred_work": null,
 "reason": "<first/most-severe blocker, one line>"}
```

The log carries the full blocker list.

## 5. Arm the environment (only when the gate passes)

Do these in order; each must be asserted, not assumed:

- **Epic branch.** Create the working branch off `{workflow.epic_branch_prefix}<epic-id>` from a clean tree. Rollback for this run is git (per-story commits, worktree isolation under `--parallel`) — `/rewind` checkpoints miss Bash-driven changes, so the branch is the real undo. If the tree is dirty (`git_clean: false`), resolve before branching.
- **Hooks.** Idempotently merge the **PreToolUse** guard (`scripts/hooks/guard_pretooluse.py`) and the **Stop** budget hook (`scripts/hooks/budget_stop.py`) into `{project-root}/.claude/settings.local.json` (gitignored, machine-local, honored after the workspace trust dialog). Re-merge every run — do not assume a prior run left them. Then **assert they are active** (present in resolved settings); invariants that live only in memory are context, not enforcement, and memory does not block a `git commit`.
  - **Inject the hook env from the resolved scalars.** Both hooks read config from env first ("env wins so the conductor can inject per run") and fall back to hardcoded defaults (`main/master`, `25`, `1_500_000`, `ultracode/epic-`) otherwise — so a `customize.toml` override of any of these **silently no-ops at the enforcement layer** unless you pass it through. Set these on the hook commands (in the `settings.local.json` hook `command`, e.g. `KEY=value uv run …`) or in the process env the hooks inherit:
    - `ULTRACODE_PROTECTED_BRANCHES={workflow.protected_branches}` (comma-separated)
    - `ULTRACODE_IMPL_ARTIFACTS={workflow.implementation_artifacts}`
    - `ULTRACODE_MAX_TURNS={workflow.max_turns_per_story}`
    - `ULTRACODE_TOKEN_BUDGET={workflow.story_token_budget}`
    - `ULTRACODE_EPIC_BRANCH_PREFIX={workflow.epic_branch_prefix}`
  - The same PreToolUse guard now also enforces the Cross-Session Recall latch from `{workflow.implementation_artifacts}/.mem-state.json` — the merged hook reads it automatically, fail-closed; no new env var to inject.
- **Allowlist.** Pre-populate the tool allowlist with `{workflow.allowlist_commands}` so the unattended run (and any fan-out subagents, which inherit the allowlist) can run tests/lint/build/commit without a permission prompt that no one is there to approve.

### Launch briefing (interactive only)

This is the moment the human leaves the loop. Before the first unattended action — **interactive runs only; headless skips this subsection entirely** — surface a one-screen briefing so the operator decides "should I let go right now?" with eyes open:

- **What is about to run unattended:** the Epic (id + title), in-scope story count, profile (production / `--light`), and the Epic branch (`{workflow.epic_branch_prefix}<epic-id>`).
- **Worst-case envelope:** up to `story count × {workflow.max_turns_per_story}` turns — a smart default from context already in hand, so a first-timer can calibrate launch-now vs. launch-after-lunch.
- **The autonomy line:** state plainly — *"from here I will not ask you anything."*
- **Kill switch:** Ctrl-C, or delete the Epic branch — and note that `/rewind` will not help (its checkpoints miss the Bash-driven changes that make up the run, the same reason the branch is the real undo).
- **Where to watch:** the run's `.decision-log.md` (prose account); on the sequential spine, `{workflow.implementation_artifacts}/run-status.json` (the machine-readable heartbeat Execute updates as the spine advances); under `--parallel`, watch the workflow progress view (`/workflows`) and its run log instead — the fan-out's worktree agents do not write `run-status.json`.

Then **one soft confirm** to cross the line. With `--yes`, skip the confirm and launch straight through — but **still print the briefing** so the operator has the record. Headless never reaches this subsection.

## Progression

Proceed to `references/define-done.md` only after the gate passed AND the Epic branch, both hooks (asserted active), and the allowlist are in place — all recorded in `.decision-log.md`. If the gate did not pass, the run has stopped here (interactive) or returned blocked JSON (headless); there is no progression.
