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

