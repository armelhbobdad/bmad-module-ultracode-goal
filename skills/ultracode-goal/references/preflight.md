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
          framework_present, framework_kind, test_artifacts_dirs, sprint_status_present,
          project_context_count, tea_flags}}
```

`budget` is the count of mechanical blockers. The script does **not** decide semantic intervention — that is your job in step 3. Treat `green: true` from the script as *necessary but not sufficient*.

## 1b. Run the formalize readiness check

Step 1's `preflight_check.py` counts mechanical facts; it cannot read the planning corpus and decide whether the Epic is *formally ready*. That readiness verdict is produced here — immediately after the mechanical check of step 1 and before the remediation pass of step 2 — by the same single kernel the standalone `/ucg-formalize` entry point runs, so one readiness definition serves both entry points:

```
uv run {skill-root}/scripts/formalize_check.py --epic <id> --project-root {project-root} --planning-artifacts {planning_artifacts} --impl-artifacts {workflow.implementation_artifacts} --tea-config {workflow.tea_config_path}
```

Qualify the path with `{skill-root}` for the same cwd-safety reason step 1 does (a bare `scripts/…` resolves from the skill root, not the project cwd the conductor runs from). The `ucg-formalize` SKILL.md names the identical kernel path, so the two callers cannot drift to divergent scripts.

The verdict is computed from the **resolved artifact set on disk** — the real PRD / architecture / epic / story content the readiness resolver locates — regardless of whether any customization shaping applied; the gate reads the artifact on disk, not the shaping. The kernel is **fail-closed**: an unreadable or absent artifact is a *failing signal*, never neutral (mirroring `gate_eval.py`'s `nfr_status is None → failing`). The run is unconditional on that resolved corpus — it is the verify side that must hold even when shaping legitimately did not land.

This step only *produces* the verdict. Its mechanical gaps, judgment candidates, and reds are read downstream by steps 2–4 (sibling stories); nothing is folded in here.

Per the measurement protocol, log the formalize duration provenance — `wall_clock_ms`, `mechanical_ms`, `artifact_count` — to `.decision-log.md` on every verdict, reusing the existing step-3 scan boundary for the end-to-end split; no number gates the run (the wall-clock budget is measured, never guessed).

## 2. Auto-remediation pass

Clear each remediable blocker, then **re-run the check** so the budget reflects the fixes. Remediate:

- **Test framework absent** (`framework_present: false`): the script already counts a pytest config / root `conftest.py` or a real `package.json` `test` script as a present framework (`framework_kind` is then `pytest` / `npm-test`, or `js-config` for a Playwright/Cypress/Jest/Vitest config), so a non-browser project does **not** trip this blocker. When it *does* fire (no harness of any kind recognized), scaffold one **appropriate to the stack**: for a web/E2E project, `bmad-testarch-framework` (Playwright/Cypress per `tea_flags`); for a **pytest or npm-script** project, stand up that harness directly (a `pytest.ini` / `conftest.py`, or a real `test` script) rather than an inapplicable browser framework — then re-run the check so `framework_present` flips true. ATDD in Stage 3 hard-halts without a configured framework — this must exist before launch. **Fitness caveat:** TEA's ATDD/automate chain still assumes a browser/E2E stack, so on a non-web module the framework is *present* but not *fit*; run such a module under `--light` (trace-only gate, no browser ATDD — see define-done.md's `--light` note and gate.md).
- **CI quality pipeline absent** (production profile only): if no CI quality pipeline exists yet, scaffold it via `bmad-testarch-ci` **after** the framework exists — `bmad-testarch-ci` halts if the framework is absent, so the strict order is framework → ci. This is one-time infra (force **Create** mode); the pipeline embeds TEA's coverage thresholds so the gate also lives durably in CI, while the per-epic loop gate remains `gate_eval.py` in Stage 5. Skip under `--light`.
- **Missing acceptance criteria / story** for an in-scope story: generate via `bmad-create-story` so each story carries clear, testable ACs. TEA atdd and trace both need them; a story without ACs has nothing to trace and will stall.
- **Test-artifacts dirs absent** (`test_artifacts_dirs` incomplete): pre-create the trace/test-design/test-review output dirs (`{workflow.trace_output_dir}` and its siblings under the TEA `test_artifacts` root) so TEA writes land deterministically and `gate_eval.py` finds them in Stage 5.
- **`project-context.md` count != 1** (`project_context_count`) — advisory only: `preflight_check.py` reports it as a **check** and never appends it to `blockers[]`, so a count of `0` or `> 1` never moves `budget` and never blocks launch. Resolve to exactly **one** anyway (generate via `bmad-generate-project-context` if zero; de-dup if multiple): `{workflow.persistent_facts}` globs this file and duplicates poison Auto-Memory grounding — that is why to fix it, not the gate.
- **`sprint-status.yaml` absent** (`sprint_status_present: false`): ensure it is present (via `bmad-sprint-planning`). Its presence makes TEA test-design **auto-select Epic-Level** and skip its interactive System/Epic mode prompt — without it, Stage 3 stalls on a question no one is there to answer.
- **TEA mode**: force **Create** mode for every TEA workflow this run. Resume/Validate/Edit are interactive and will halt an unattended run. Set/confirm whatever the TEA config exposes (`tea_execution_mode`) so no workflow resumes a prior session.
- **Secrets / credentials** a story needs (test env keys, API tokens): **interactive** — prompt **once**, now, and capture them out of git. **Headless** — do not prompt; an unresolvable secret becomes a RED blocker (step 4), never a deferred question.
- **Formalize mechanical gaps** (`formalize_check.py`'s `mechanical_gaps[]` from step 1b): fold these machine-derivable, meaning-preserving fixes into *this same* pass — never a second remediation pass and never a new step heading. The genuinely-new one is the leaked-TEA-artifact **MOVE-and-re-point**: move a TEA artifact that leaked into a source/impl dir out to the `{workflow.trace_output_dir}` / test_artifacts root, then re-point every in-repo reference to the new path (content is only relocated, never rewritten) — the MOVE targets a *genuine* TEA artifact only; the kernel now excludes UCG's own story notes / run sentinels whose filename merely carries a marker token because the story slug does (`formalize_check.py:_is_ucg_impl_artifact`), so they no longer reach this remediation. Should any *other* non-TEA false positive ever surface, **verify identity before moving** and archive it *out of the impl-artifacts scan tree* — never into the trace dir (that misfiles it) and never leave it in place (it stays counted and deadlocks the `budget == 0` gate, since a remediable gap that is never cleared keeps the formalize verdict off `ready`) — recording in `.decision-log.md` what it actually is. The orphaned-index and missing-AC gaps reuse the `bmad-create-story` scaffold this step already runs. Auto-clear **only** a `mechanical_gaps[]` entry whose `remediable == true` (the kernel's human-authored `remediable` literal, never re-decided in this prose); a leaked-artifact finding the kernel emitted as a `judgment_candidates[]` entry or with `remediable: false` is **not** moved here — that residual content-soundness judgment routes to the step-3 scan / step-4 hard gate. These remediations reuse the existing remediate-then-re-run loop below ("run the script from step 1 again"), so the budget re-reflects the formalize fixes on re-run with no extra invocation.

**Stale-hook pre-arming (before any remediation commit).** A prior UCG run may have left its PreToolUse guard (`scripts/hooks/guard_pretooluse.py`) and Stop budget hook (`scripts/hooks/budget_stop.py`) armed in `{project-root}/.claude/settings.local.json` — still live *now*, because step 5 has not yet re-armed this run's hooks. That stale guard mis-governs any remediation that commits (the dirty-tree `git_clean: false` clear especially): its marker-gate keys on `.current-story` plus a `.tests-ran-<story_id>` marker in the impl-artifacts, and on a fresh run `.current-story` is either unset — so no marker resolves and the commit is **denied**, dead-ending the remediation — or still points at the prior run's last story, whose persisted marker (Finalize removes only `.mem-state.json`, never the tests-ran markers) it then **rides to a spurious green**, waving the commit through under stale, wrong-run enforcement. Both failure modes are wrong for this run. Do **not** forge a marker and do **not** wait on the gate: **disarm the prior-run hooks first** — remove the UCG `guard_pretooluse.py` / `budget_stop.py` entries from `settings.local.json` — then make the remediation commit, and let step 5 re-merge both hooks freshly with *this* run's injected env. Log the disarm and the step-5 re-arm to `.decision-log.md`.

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

**Second hypothesis stream — seed the formalize candidates.** Pass that SAME single throwaway subagent a second set of targeted hypotheses alongside the recall advisories: `formalize_check.py`'s `judgment_candidates[]` (from step 1b) as a **`source:line` list** — the references only, never the inlined artifact bodies — so the subagent confirms machine-flagged candidates *instead of scanning blind*. The kernel only *flags*; the throwaway subagent *decides* — it must **confirm-or-clear** each seeded `judgment_candidate` into `reds` or `concerns`, never recording one as a RED unprompted. Fail-closed: a `judgment_candidate` the subagent can neither confirm nor clear **defaults to RED** (JUDGMENT), mirroring `gate_eval.py`'s `nfr_status is None → failing`. This adds zero net subagent and zero net conductor context — the same single spawn, the same discarded-context discipline, and the same three-key return object below.

The subagent must return **ONLY this object — no prose, no document quotes beyond the one-line evidence fields**, so you hold the findings while the corpus stays in its discarded context:

```json
{"reds": [{"source": "<artifact path:line>",
           "kind": "undecided-product|undecided-architecture|contradiction|undefinable-done",
           "decision_needed": "<the exact decision a human must make>",
           "evidence": "<one quoted line>"}],
 "concerns": [{"source": "<artifact path:line>", "note": "<cosmetic / non-blocking gap, one line>"}],
 "advisories_checked": [{"sig": "<advisory id>", "status": "recurred|not-observed|unknown"}]}
```

**Retrieving the result on an async-spawn platform.** The contract above assumes a *synchronous* spawn whose return text reaches you directly. If this run spawns the subagent as a **background teammate** instead, its plain-text return is **not** routed back to the conductor — so additionally instruct it to persist this *same* object to a file (e.g. `{workflow.implementation_artifacts}/.preflight-scan.json`) and read that file back, or to message you the object explicitly. The discarded-context discipline is unchanged: you ingest only the object, never the corpus, which stays discarded in the subagent's context. (The same retrieval rule applies to any subagent this run spawns asynchronously — e.g. a background-delegated Execute `bmad-dev-story` or a gate TEA sub-skill: route its structured result through a file or an explicit message, never an unrouted plain-text return.)

Every `reds` entry is **RED** — it cannot be auto-remediated, because the fix is a human decision, and an unattended run guessing it produces confidently wrong work. A purely cosmetic gap belongs in `concerns`, never RED; recall-derived hypotheses are attributed under `advisories_checked` and are never themselves RED and never block launch. Record each RED finding with its source and the exact decision needed in `.decision-log.md`.

## 4. Hard gate

**Launch only when ALL hold:**

- post-remediation script `budget == 0` (every mechanical blocker cleared),
- the semantic scan **and the formalize subagent** found **no RED** — the two reds streams unioned (no undecided product/architecture, no unresolvable secret, no confirmed formalize red),
- **ultracode** session effort and **Auto Mode** are on (gated to Opus/Sonnet 4.6+; required for unattended xhigh + auto-workflow execution),
- the post-remediation formalize_check.py verdict is `ready` — i.e. `mechanical_budget == 0` AND the formalize subagent found no RED — re-using the step-1b kernel's verdict after the step-2 fold-in and step-3 seed (not a fresh gate-time check); this clause holds on verdict `ready` and only `ready`, so any other verdict (`blocked`, an un-cleared `remediable`, or an unreadable / absent / unparseable / missing verdict) FAILS the gate under the "If any fails … STOP" disposition below.

If any fails: write the blockers — mechanical and semantic — to `.decision-log.md` with what each needs to clear, and **STOP**. Do not launch a partially-ready run; a single guessed architecture decision corrupts the whole Epic. In **headless**, instead emit the blocked JSON in the canonical five-key shape (every key always present; `report` and `deferred_work` are `null` because the run blocked before producing them):

```json
{"status": "blocked",
 "skill": "ultracode-goal",
 "decision_log": "<path to this run's .decision-log.md>",
 "report": null,
 "deferred_work": null,
 "reason": "<first blocker in the adapter's blocker-list order, one line>"}
```

The log carries the full blocker list. A confirmed **formalize RED** (a formalize-subagent `reds[]` entry unioned into the no-RED clause by step 4) surfaces through this **identical** five-key channel as a semantic-scan RED — no formalize-specific key, no formalize-specific status string. `reason` is the **first blocker in the adapter's blocker-list order** — positional `blockers[0]` flattened to one line (reds carry no severity field), built by the one shared `scripts/headless_envelope.py` `build_headless_envelope` adapter so every headless exit serializes through a single envelope definition. The rich formalize verdict stays a separate script-layer object the adapter consumes; it never nests into the envelope.

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
  - **The commit/push guard string-matches the verb; it does not parse the command.** The guard scans each shell segment and flags any segment where `git` is followed by the literal `commit`/`push` verb — including the verb sitting inside an `echo`, a log line, or a here-string in a verification command, not only a real commit. So on a `{workflow.protected_branches}` branch a benign command that merely *mentions* `git commit` or `git push` is denied; and on the epic branch, before the story's `.tests-ran-<story_id>` marker exists, a command that merely mentions `git commit` is denied (the marker gate is commit-only — a `git push` mention is never marker-gated). Either way the tool call is wasted, so keep those literals out of echoes and status/verification commands during the run. (execute.md step 4 covers the narrower marker-written-in-the-same-compound-command trap.)
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
