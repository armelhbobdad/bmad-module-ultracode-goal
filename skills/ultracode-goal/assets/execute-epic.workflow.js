// EXPERIMENTAL — ultracode-goal --parallel worktree fan-out.
//
// This is the additive, opt-in parallel execution path. The DEFAULT
// path is the sequential /goal spine in references/execute.md; this script only runs when
// the operator passes --parallel. It shares the SAME truth sources as the sequential path:
// the deterministic gate is scripts/gate_eval.py reading TEA's gate-decision.json (never
// the model, never the transcript-only /goal evaluator), and the same PreToolUse + Stop
// hooks merged into .claude/settings.local.json at preflight enforce the invariants.
//
// WHY EXPERIMENTAL: this path leans on workflow<->skill interplay the Claude Code docs
// leave under-specified — whether worktree-isolated agents can reliably drive BMAD/TEA
// skills, and how concurrent stories interact with the single per-repo auto-memory
// directory (all worktrees of one git repo SHARE one ~/.claude/projects/<repo>/memory/,
// a known cross-writer collision risk). There is no mid-run user input here: every gate
// is resolved before launch or not at all. Validate empirically before trusting it
// unattended; on any doubt, fall back to the sequential spine.
//
// Available workflow primitives (top-level await + return supported):
//   meta            — pure literal exported below (no runtime values)
//   phase(title)    — declare the current phase for the run log/UI
//   log(msg)        — append to the run log
//   parallel([fns]) — run zero-arg thunks concurrently, returns results array
//   pipeline(items, ...stageFns) — map items through ordered stages
//   agent(prompt, { label, phase, schema, isolation }) — spawn a subagent; isolation:
//                     'worktree' runs it in .claude/worktrees/ on its own branch so
//                     concurrent stories never overwrite each other's working tree.

export const meta = {
  name: 'ultracode-goal-execute',
  description:
    'EXPERIMENTAL --parallel path: fan a BMAD Epic out across worktree-isolated per-story agents (dev-story un-skipping ATDD, tests/lint/build, production test-review + code-review, commit at green), gate each story with gate_eval.py, then run one epic-level trace gate. Shares the sequential spine gate + hooks.',
  phases: [
    { title: 'Stories', detail: 'Per-story worktree-isolated dev -> verify -> review -> commit -> gate_eval, batched to max_concurrency' },
    { title: 'EpicGate', detail: 'Epic-level TEA trace gate over the merged result via gate_eval.py' },
  ],
}

// ---------------------------------------------------------------------------
// args (supplied by the skill when it invokes this workflow):
//   epic                 — Epic id/string
//   stories[]            — ordered list of in-scope stories (id + path/context)
//   profile              — 'production' (full TEA + reviews) | 'light' (trace gate only)
//   paths.{trace_output, deferred_work, implementation_artifacts, tea_config, skill_root}
//                          skill_root is the resolved {skill-root} — the skill threads it in
//                          because this .js is run by the dynamic-workflow runtime, which has
//                          no {skill-root} resolver, so the gate_eval.py path must arrive absolute.
//   max_concurrency      — cap on simultaneous worktree agents; the GOVERNING value is the
//                          passed parallel_max_concurrency ({workflow.parallel_max_concurrency},
//                          customize.toml default 8). The literal 4 below is only a fallback when
//                          the skill invokes this workflow without supplying max_concurrency.
// ---------------------------------------------------------------------------
const {
  epic,
  stories = [],
  profile = 'production',
  paths = {},
  max_concurrency = 4,
} = args

const traceOutput = paths.trace_output
const deferredWork = paths.deferred_work
const implArtifacts = paths.implementation_artifacts
const teaConfig = paths.tea_config
// Resolved {skill-root}; substituted into the gate_eval.py prompt strings below so the
// spawned worktree agent receives an absolute script path, not an unresolved brace token.
const skillRoot = paths.skill_root
const isProduction = profile === 'production'
const concurrency = Math.max(1, Number(max_concurrency) || 1)

// Verdict mapping is OWNED by gate_eval.py — this schema only captures what the agent
// reports back from running it. The agent MUST NOT recompute TEA thresholds or decide the
// verdict itself; it runs the script and returns the script's stdout fields verbatim.
const STORY_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['story', 'verdict', 'gate_status', 'committed'],
  properties: {
    story: { type: 'string', description: 'the story id' },
    verdict: { type: 'string', enum: ['advance', 'defer', 'reloop', 'escalate'], description: 'verbatim gate_eval.py verdict' },
    gate_status: { type: 'string', description: 'verbatim gate_eval.py gate_status (PASS|CONCERNS|FAIL|WAIVED|NOT_EVALUATED)' },
    committed: { type: 'boolean', description: 'true only if tests/lint/build were green AND a single commit was made on the story branch' },
    branch: { type: 'string', description: 'the worktree branch this story was developed on' },
    evidence: { type: 'string', description: 'short summary of printed test/lint/build evidence' },
    deferred: {
      type: 'array',
      description: 'non-gate-blocking items to append to the deferred-work ledger; NEVER a P0/critical FAIL',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['source', 'severity', 'reason', 'suggested_action'],
        properties: {
          source: { type: 'string', enum: ['gate', 'code-review', 'nfr', 'decision'] },
          severity: { type: 'string', enum: ['low', 'med', 'high'] },
          reason: { type: 'string' },
          suggested_action: { type: 'string' },
        },
      },
    },
    reasons: { type: 'array', items: { type: 'string' }, description: 'gate_eval.py reasons[]' },
  },
}

const EPICGATE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['verdict', 'gate_status'],
  properties: {
    verdict: { type: 'string', enum: ['advance', 'defer', 'reloop', 'escalate'] },
    gate_status: { type: 'string' },
    reasons: { type: 'array', items: { type: 'string' } },
  },
}

function storyId(s, i) {
  if (typeof s === 'string') return s
  return s.id || s.story || s.path || `story-${i + 1}`
}

function storyContext(s) {
  if (typeof s === 'string') return s
  return [s.path ? `path: ${s.path}` : '', s.context || s.title || ''].filter(Boolean).join('\n')
}

// One worktree-isolated agent per story. The pipeline below batches these so no more than
// `concurrency` run at once; within a story the steps are strictly ordered.
function runStory(s, i) {
  const id = storyId(s, i)
  const reviewStep = isProduction
    ? `4. PRODUCTION reviews (skip under --light): run bmad-testarch-test-review then bmad-code-review on this story's diff. P0/critical findings are NOT deferrable — they must be fixed in this worktree before commit (re-loop within {workflow.max_turns_per_story}). Non-critical findings go into the "deferred" array.\n`
    : `4. LIGHT profile: skip test-review/code-review (trace gate only).\n`

  return agent(
    `You are delivering ONE story of BMAD Epic "${epic}" inside an ISOLATED git worktree (isolation: worktree). ` +
      `Your working tree is private — other stories run concurrently in their own worktrees on their own branches, so commit only your own story's changes. ` +
      `This is the EXPERIMENTAL --parallel path; there is NO mid-run human input. Profile: ${profile}.\n\n` +
      `STORY: ${id}\n${storyContext(s)}\n\n` +
      `Execute these steps IN ORDER, printing real evidence at each step (the printed evidence keeps the run auditable, but the GATE is gate_eval.py, not your judgment):\n` +
      `1. bmad-create-story (Create mode only — never Resume) to fully context the story file if it is not already complete.\n` +
      `2. bmad-dev-story to implement it, UN-SKIPPING the red-phase ATDD acceptance tests for this story (remove the test.skip markers that define the Definition-of-Done) so they actually run.\n` +
      `3. Run and PRINT the project's test, lint, and build commands. In a monorepo, scope the test run wide enough to catch cross-package regressions — run the full suite, or the changed package(s) plus their dependents (e.g. --affected and downstream), not just this story's own package: a story's change can regress a sibling package's conformance gate within this worktree, and a package-scoped run reports green while that sibling gate is red. Once all three are green, write the tests-ran marker file ${implArtifacts}/.tests-ran-${id} (exact name the PreToolUse hook checks, with ULTRACODE_STORY_ID=${id} for this worktree) so the hook permits the commit. Do NOT proceed to commit unless all three are green.\n` +
      reviewStep +
      `5. COMMIT AT GREEN: make exactly ONE commit on this worktree's branch capturing the story. The PreToolUse hook will deny the commit on a protected branch or without the tests-ran marker — that is expected enforcement, satisfy it rather than bypass it. Set committed=true only if the commit succeeded on green.\n` +
      `6. GATE THIS STORY — run EXACTLY:\n` +
      `   uv run ${skillRoot}/scripts/gate_eval.py --trace-output ${traceOutput} --story ${id} --profile ${profile}` +
      (isProduction ? ` --nfr <nfr-assessment.md> --test-review <test-review.md>` : ``) + `\n` +
      `   (in production, first run bmad-testarch-automate to backfill coverage, then bmad-testarch-trace, then bmad-testarch-nfr so the gate file exists before you read it). ` +
      `Return the script's verdict, gate_status, and reasons VERBATIM. Do not recompute TEA thresholds and do not override the verdict.\n\n` +
      `INVARIANT: a P0/critical FAIL NEVER goes into "deferred" — fix-and-reloop within budget, or let the verdict be reloop/escalate. Only non-gate-blocking items (CONCERNS, non-critical review/NFR findings, parked decisions) belong in "deferred".\n\n` +
      `Return ONLY the JSON object matching the schema. No prose outside it.`,
    { label: `story:${id}`, phase: 'Stories', schema: STORY_SCHEMA, isolation: 'worktree' }
  )
}

// ---------------------------------------------------------------------------
// Phase 1: per-story fan-out, batched to honor max_concurrency.
// pipeline() maps each concurrency-sized chunk through one stage that fans the chunk out
// with parallel(); chunks run sequentially, stories within a chunk run in parallel.
// ---------------------------------------------------------------------------
phase('Stories')
log(`Epic ${epic}: ${stories.length} story(ies), profile=${profile}, concurrency=${concurrency} (EXPERIMENTAL --parallel)`)

const indexed = stories.map((s, i) => ({ s, i }))
const batches = []
for (let b = 0; b < indexed.length; b += concurrency) {
  batches.push(indexed.slice(b, b + concurrency))
}

const batchResults = await pipeline(
  batches,
  (batch) => parallel(batch.map(({ s, i }) => () => runStory(s, i)))
)

const perStory = batchResults.flat().filter(Boolean)
log(`Stories complete: ${perStory.map((r) => `${r.story}=${r.verdict}/${r.gate_status}`).join(', ')}`)

// Collect non-gate-blocking deferrals for the ledger (the skill, not this script, writes
// the markdown table at {workflow.deferred_work_path} using the ledger schema).
const deferred = []
for (const r of perStory) {
  for (const d of r.deferred || []) {
    deferred.push({ story: r.story, ...d })
  }
}

// ---------------------------------------------------------------------------
// Phase 2: epic-level trace gate over the whole epic once every story has landed.
// ---------------------------------------------------------------------------
phase('EpicGate')
const epicGate = await agent(
  `All stories of BMAD Epic "${epic}" have been delivered on their worktree branches. ` +
    `Run the EPIC-LEVEL TRACE gate over the consolidated epic — a trace-only read of the epic's gate_status, passing NO --nfr/--test-review (the per-story production NFR/test-review ANDs already ran at each story gate, and TEA writes no epic-level aggregate; a placeholder epic-level --test-review path would fail-closed and spuriously downgrade an epic PASS to reloop)` +
    (isProduction ? ` (run bmad-testarch-automate -> bmad-testarch-trace first to build the epic trace decision)` : ` (run bmad-testarch-trace first)`) +
    `, then run EXACTLY:\n` +
    `  uv run ${skillRoot}/scripts/gate_eval.py --trace-output ${traceOutput} --story ${epic} --profile ${profile}\n` +
    `Return the script's verdict, gate_status, and reasons VERBATIM. Do not recompute thresholds or override the verdict.\n` +
    `Per-story outcomes for context: ${JSON.stringify(perStory.map((r) => ({ story: r.story, verdict: r.verdict, gate_status: r.gate_status })))}\n\n` +
    `Return ONLY the JSON object matching the schema.`,
  { label: `epic-gate:${epic}`, phase: 'EpicGate', schema: EPICGATE_SCHEMA }
)

log(`Epic gate: ${epicGate ? `${epicGate.verdict}/${epicGate.gate_status}` : 'unavailable'}; deferred items: ${deferred.length}`)

return {
  perStory: perStory.map((r) => ({ story: r.story, verdict: r.verdict, gate_status: r.gate_status })),
  epicGate,
  deferred,
}
