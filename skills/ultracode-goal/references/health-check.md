---
# UltraCode-Goal self-improvement health check — captures real workflow
# friction as GitHub issues. (No name/description keys: those belong only
# in SKILL.md frontmatter; this is a stage reference, not a skill.)
healthCheckRepo: '{workflow.health_check_repo}'  # empty = health check off
localFallbackFolder: '{workflow.health_check_queue_path}'
seenCachePath: '{workflow.health_check_seen_cache}'
liveSubmitSeverities: ['bug']  # friction/gap go local-queue-default with explicit opt-in
autosubmit: '{workflow.health_check_autosubmit}'
---

# Health Check: Workflow Self-Improvement

This is the terminal step of Stage 6 (Finalize) — Stage 7 in SKILL.md's stages table. Finalize loads it by bare path (`references/health-check.md`); it is fully self-contained and chains nowhere. Reflect on the ultracode-goal run that just completed — honestly, precisely, on evidence, reporting only what you actually experienced executing THIS run's stages. If real friction, bugs, or gaps were encountered in the *workflow instructions* (not the user's code), capture them as structured findings for review and optional submission as GitHub issues. Zero overhead for clean runs: if nothing went wrong, log one line and exit.

## Anti-fabrication rules

- **DO NOT FABRICATE ISSUES.** If the workflow ran smoothly, say so and exit. Inventing issues to appear thorough is a SYSTEM FAILURE.
- Only report issues you **ACTUALLY encountered** while following the stage instructions during THIS run.
- Every finding MUST cite the **specific stage reference file and section** where the issue occurred.
- If you are unsure whether something was a real issue or your own confusion, DO NOT report it.
- **Reporting zero issues is the EXPECTED outcome** for a well-designed workflow.

## 0. Announce arrival

Display, in `{communication_language}`: "Running a quick self-improvement check on this run. If nothing rough came up, I will close out immediately."

In headless (`-H`), skip the display and log: "headless: skipped health-check arrival announcement". The line is informational, not a commitment gate — proceed to §0.5 without waiting.

## 0.5. Enabled gate

If `{workflow.health_check_repo}` is **empty**, the health check is off — there is nowhere to file, so there is nothing to run. Log one line — "health-check disabled (health_check_repo empty); skipping" — and **exit immediately**. Do nothing else: no reflection, no files, no JSON side effects. In headless this returns control so Finalize emits its final JSON unchanged.

Otherwise continue to §1.

## 1. Read run context

From this run's `.decision-log.md` and session context, identify:

- **Stage(s) executed** — which of `ingest-and-scope`, `preflight`, `define-done`, `execute`, `gate`, `finalize` you actually followed.
- **Friction points** — moments where a stage instruction was unclear, wrong, contradictory, or silent on a scenario you hit.

The finding's `stage` is whichever of the six you were following when the issue bit you.

## 2. Reflect on execution

Silently review the run. Ask:

- Did a stage instruction lead me astray or cause unnecessary back-and-forth?
- Was a stage ambiguous, so I guessed rather than followed clear guidance?
- Did I hit a scenario no stage accounted for?
- Were any stage instructions wrong or contradictory?

If the answer to ALL is "no", display "Health Check: clean run. No workflow issues to report." and **STOP** — the run is done. In headless, log "health-check: clean run, no findings" and return.

## 3. Severity definitions

Classify each genuine finding:

- **`bug`** — Stage instructions were wrong or contradictory.
- **`friction`** — Stage worked but was unclear, ambiguous, or caused unnecessary back-and-forth.
- **`gap`** — A scenario arose that the workflow did not account for at all.

## 4. Route by run mode

The routing fork is the run mode, decided once here.

### 4a. Attended routing (HALT gate)

In an attended run there is a human at the keyboard. Present every finding, then HALT.

Present each finding:

| Field | Value |
|-------|-------|
| Severity | `bug` / `friction` / `gap` |
| Stage | one of the six |
| Step File | `skills/ultracode-goal/references/{stage}.md` |
| Section | the stable section-heading slug (never line numbers) |

Then ask:

"Submit these findings?

- **[Y]** Yes — submit all findings
- **[N]** No — discard all findings
- **[E]** Edit — let me revise before submitting

You are the final filter. Reject any finding that does not reflect a real issue you observed."

**HALT and wait for input.**

- **[Y]** → proceed to §5 (severity routing).
- **[N]** → display "Findings discarded. Workflow complete." and STOP.
- **[E]** → let the user keep, modify, or remove findings; re-present the revised list and ask again.

### 4-headless. Unattended routing (no human at the gate)

In headless (`-H`) there is no human to answer [Y]/[N]/[E], so that gate is **bypassed deterministically** — never block waiting for input:

- If `{workflow.health_check_autosubmit}` is **false** (the default): **queue EVERY finding locally** (§5c). Never live-submit in an unattended run with autosubmit off.
- If `{workflow.health_check_autosubmit}` is **true**: **live-submit `bug` findings only** (§5a) — still script-fingerprinted, remote-dedup-searched, and seen-cache-guarded; **friction and gap always queue** (§5c).

The health check must **NEVER block or delay the final headless JSON emit**. It is fire-and-queue: do the routing above, then return so Finalize emits its JSON. If `gh` is unavailable at any live-submit step, fall through to §5c — never stall.

## 5. Severity routing (attended [Y] path)

Route each confirmed finding:

- **`bug`** → live-submit (§5a). High signal, priority for maintainers.
- **`friction` / `gap`** → local queue by default (§5c). These are the most subjective categories and produce the most near-duplicates. Ask **once per session**: "Also submit the {N} friction/gap finding(s) as GitHub issues? [y/N]" — only on explicit affirm do they route through §5a.

### 5a. Live-submit: fingerprint, dedup, create

For each finding routed to live-submit:

**1. Compute the fingerprint via the script** — never inline shell. The fingerprint and seen-cache are computed and managed deterministically by `health_check_fp.py`:

```
uv run {skill-root}/scripts/health_check_fp.py fingerprint \
  --severity {severity} --stage {stage} --section-slug {slug}
```

→ `{"fp": "fp-xxxxxxx", "tuple": "<exact hashed input>"}`. The `section-slug` is a kebab-case stable heading slug (e.g. `verdict-mapping`), **never line numbers** — they drift when files are edited.

**Install-mode-invariant dedup (explicit rule):** the script's `workflow` component is `ultracode-goal/{stage}` and its `step_file` component is ALWAYS the source-repo form `skills/ultracode-goal/references/{stage}.md`, regardless of where the skill is installed (`_bmad/` tree vs. dev checkout). The same defect therefore dedups to the same `fp` across every install. Do not substitute the installed path.

**2. Check the seen-cache via the script:**

```
uv run {skill-root}/scripts/health_check_fp.py seen --fp {fp} --cache {seenCachePath}
```

→ `{"seen": true, "record": {...}}` means this user already handled this fingerprint on this machine — skip submission silently and log: `"fp-xxxxxxx: already handled on {record.date}, {record.issue_url} — skipping"`. `{"seen": false, "record": null}` means proceed.

**3. Check GitHub CLI** with `gh auth status`. If it fails, fall through to §5c (offline fallback).

**4. Remote dedup search** — one deterministic call:

```
gh search issues --repo {healthCheckRepo} --state open "{fp} in:title" --json number,url,title --limit 1
```

**5a-i. If a matching open issue exists**, present:

> "Matching report found: #{N} — {title}
>
> Your finding has the same fingerprint `{fp}`. Options:
> - **[R]** React (👍) on the existing issue — silent upvote, no comment
> - **[C]** React + comment with YOUR environment/evidence delta (only if it materially differs)
> - **[N]** Create a new issue anyway — only if you are certain this is a distinct defect
> - **[S]** Skip — do not submit this finding"

Execute the choice:

- **R:** `gh api -X POST /repos/{healthCheckRepo}/issues/{N}/reactions -f content='+1'`, then record `reacted`.
- **C:** the reaction call, then `gh issue comment {N} --body "{minimal env+delta body}"` (the Environment table plus ONE sentence on what differs; no session narrative), then record `commented`.
- **N:** proceed to §5a-ii.
- **S:** record nothing.

Record the outcome via the script:

```
uv run {skill-root}/scripts/health_check_fp.py record --fp {fp} --cache {seenCachePath} \
  --issue-url {url} --action reacted|commented --date {YYYY-MM-DD}
```

**5a-ii. If no matching open issue exists** — create one.

**First, ensure the `{fp}` label exists** — it is per-fingerprint, so the first reporter of any defect creates a brand-new label, and `gh issue create --label {fp}` hard-fails if the label is missing. Guard it idempotently:

```
gh label create "{fp}" --repo {healthCheckRepo} --color "ededed" \
  --description "Health-check fingerprint dedup key" 2>/dev/null || true
```

The `|| true` makes it idempotent: if the label already exists, `gh label create` exits non-zero and we proceed unharmed. The other labels (`health-check`, `workflow-improvement`, `bug`/`friction`/`gap`) are pre-created repo labels and need no guard.

**Then create the issue:**

```
gh issue create --repo {healthCheckRepo} \
  --title "[health-check][{severity}][{fp}] {workflow}: {short description}" \
  --label "health-check,workflow-improvement,{severity},{fp}" \
  --body "{structured body below}"
```

The `{workflow}` in the title is `ultracode-goal/{stage}`. The `{fp}` appears in both title (human-readable) and label (server-side filterable) so maintainers can query all reports for a defect via the `fp-*` label without parsing title text.

After creation, record the mapping via the script so this user never re-reports the fingerprint:

```
uv run {skill-root}/scripts/health_check_fp.py record --fp {fp} --cache {seenCachePath} \
  --issue-url {created-url} --action created --date {YYYY-MM-DD}
```

**Writing rules — non-negotiable:**

- **One issue per finding.** Two independent problems → two issues.
- **Respect length budgets.** Finding, Expected, Actual, Impact, Suggested Fix are **each ONE sentence**. Evidence is 2-5 bullets, not prose.
- **Quote, do not paraphrase.** In Evidence, cite the exact `file:line` with the quoted text in quotes.
- **Never narrate the session.** The reader wants the defect, not the story. If a sentence starts with "During my run…", delete it.
- **If unsure it is a real issue, do not submit it.**

**Issue body format:**

```markdown
## Workflow
ultracode-goal/{stage}

## Step File
`skills/ultracode-goal/references/{stage}.md`

## Severity
`{bug | friction | gap}`

## Fingerprint
`{fp}`

## Finding
<!-- ONE sentence: what is the problem? -->

## Expected
<!-- ONE sentence: what did the stage instruct or imply should happen? -->

## Actual
<!-- ONE sentence: what did you observe instead? -->

## Evidence
<!-- 2-5 bulleted `file:line` citations with quoted text. No narrative. -->
- `skills/ultracode-goal/references/{stage}.md:NN` — "quoted text from the file"

## Impact
<!-- ONE sentence: what did this cost in THIS run? -->

## Suggested Fix
<!-- ONE sentence, ONE recommendation. -->

## Environment
| Field | Value |
|-------|-------|
| Date | {ISO date} |
| OS | {e.g. Ubuntu 24.04, macOS 15.2, Windows 11} |
| AI Editor | {e.g. Claude Code, Cursor} |
| Model | {e.g. Claude Opus 4.6, Claude Sonnet 4.6} |
| Profile | {production \| light} |
| Run mode | {attended \| headless} |
| Module Version | {resolved per the order below, else N/A} |
```

**Module Version comes from the script** — never walk the file ladder in-prompt:

```
uv run {skill-root}/scripts/health_check_fp.py version --project-root {project-root} --skill-root {skill-root}
```

→ `{"version": "<resolved>", "source": "<which probe hit>"}`. Write `version` into the Environment table; when it is `null` (`source: "N/A"`), write `N/A`. The script probes the same first-hit-wins ladder deterministically: `{project-root}/_bmad/ucg/VERSION` → `{skill-root}/VERSION` → `.claude-plugin/marketplace.json` `plugins[0].version` → `package.json` `version`.

After creating all issues, display: "{N} issue(s) created on {healthCheckRepo}:" then each URL, then "Workflow complete."

### 5c. Local queue (gh unavailable, autosubmit-off headless, friction/gap default, or [S])

Findings that did not go live — `gh` unavailable, an unattended run with autosubmit off, the user declined the friction/gap opt-in, or the user chose **[S]** — are written one file per finding to `{workflow.health_check_queue_path}/`.

Even when queuing, **still compute the fingerprint via the script** (so the queue file carries the same `fp`) and **record it** with `--action queued` so a later live submission of the same defect dedups against it:

```
uv run {skill-root}/scripts/health_check_fp.py record --fp {fp} --cache {seenCachePath} \
  --issue-url "" --action queued --date {YYYY-MM-DD}
```

**Filename:** `hc-ultracode-goal-{stage}-{YYYYMMDD-HHmmss}.md`.

**File content:** the same structured body as §5a, prefixed with YAML frontmatter:

```yaml
---
type: workflow-health-finding
workflow: ultracode-goal/{stage}
step_file: skills/ultracode-goal/references/{stage}.md
severity: {bug | friction | gap}
fingerprint: {fp-xxxxxxx}
date: {ISO date}
---
```

When `gh auth status` failed, after writing the files display:

"{N} finding(s) saved locally:" then each path, then:

"GitHub CLI is not available. To submit these as issues, run:
`gh issue create --repo {healthCheckRepo} --title \"[title]\" --body-file {file-path}`

Or open one at <https://github.com/{healthCheckRepo}/issues/new/choose>

Workflow complete."

In an unattended run, do not display prompts — just write the files, log the count and paths, and return.

## CRITICAL STEP COMPLETION NOTE

This is the **terminal step of Finalize**. After it returns — clean run, findings submitted, queued, or discarded — the ultracode-goal run is **fully done**; there is nothing further to load. **In headless, Finalize emits the final five-key JSON AFTER this step returns** — so this step must never block, prompt, or stall waiting for input, and must never mutate or delay that emit.

**Master rule:** honesty is the only policy. Zero findings is the expected, healthy outcome. Fabricating issues to appear thorough undermines the entire self-improvement system and is a SYSTEM FAILURE.
